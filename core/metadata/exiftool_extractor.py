"""Extractor genérico basado en ExifTool: sirve para cualquier tipo de medio.

Este módulo NO depende de Qt ni de la base de datos. Aquí está TODO lo que no
cambia de un tipo de medio a otro (foto, vídeo, audio...):

    - Lee los archivos de ExifTool por lotes (una llamada para ~100 archivos).
    - Busca los archivos sidecar .xmp de cada archivo y los lee con él. Para las
      etiquetas XMP, el sidecar manda sobre el XMP incrustado (así es como Lightroom
      guarda las ediciones de los RAW y de los HEIC).
    - Aplica la lista de campos del tipo ('fields': qué etiqueta va a qué columna).
    - Aplica las reglas especiales del tipo ('apply_rules').
    - Si ExifTool falla con un lote, lo reintenta por partes para aislar al archivo
      culpable, de modo que un archivo problemático no impide leer los demás.

Un tipo de medio nuevo solo tiene que heredar de 'ExifToolExtractor' y definir qué
tipo es, su versión, su tabla de detalles y su lista de campos. Ver
'core/metadata/image/' como ejemplo y 'LEEME.md' para los pasos.

Prueba rápida (usa un ExifTool simulado):
    python -m core.metadata.exiftool_extractor
"""

__version__ = "1.2.0"
__all__ = ["ExifToolExtractor"]

# Librerías estándar
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import EllipsisType
from typing import Any, ClassVar

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.metadata.base import ExtractionResult, MetadataError, MetadataExtractor
from core.metadata.exiftool_runner import (
    ExifToolFileError,
    ExifToolRunner,
    FileMetadata,
    find_sidecars,
)
from core.metadata.field_spec import FieldSpec, read_field
from core.metadata.keyword_tags import read_keywords
from core.userdata.policy import UserDataDestination, destination_for


class ExifToolExtractor(MetadataExtractor):
    """Extractor de metadatos basado en ExifTool y en una lista declarativa de campos.

    Attributes:
        fields: La lista de campos del tipo de medio (ver 'field_spec.py').
    """

    fields: ClassVar[tuple[FieldSpec, ...]] = ()
    # Campos del usuario (rating, flag, color_label) que este extractor sabe leer del
    # archivo. Vacío = ninguno. Se devuelven en 'ExtractionResult.user_data'.
    user_fields: ClassVar[tuple[FieldSpec, ...]] = ()
    # Si lee las palabras clave del archivo (ver 'keyword_tags.py'). Van en
    # 'ExtractionResult.user_data["keywords"]', de las MISMAS etiquetas que la valoración
    # (el sidecar en los RAW, el propio archivo en los demás).
    reads_keywords: ClassVar[bool] = False

    def __init__(self, runner: ExifToolRunner) -> None:
        """Crea el extractor.

        Args:
            runner: Lector de ExifTool ya configurado.
        """
        self._runner = runner

    # -------------------------------------------------------------------------
    # Punto de extensión: reglas especiales de cada tipo
    # -------------------------------------------------------------------------

    def apply_rules(
        self,
        tags: Mapping[str, Any],
        common: dict[str, Any],
        details: dict[str, Any],
        path: Path,
    ) -> None:
        """Ajusta los valores leídos con las reglas propias del tipo de medio.

        Se ejecuta después de rellenar los campos de la lista. Sirve para lo que no
        es un simple "esta etiqueta va a esta columna": valores que dependen de
        varias etiquetas (fecha de captura con su zona horaria), que se derivan de
        otros (flash disparado a partir del código de flash) o que hay que validar.
        Por defecto no hace nada.

        Args:
            tags: Todas las etiquetas del archivo (con el sidecar ya combinado).
            common: Valores para 'media_items'; se modifica en el sitio.
            details: Valores para la tabla de detalles; se modifica en el sitio.
            path: Ruta del archivo.
        """

    # -------------------------------------------------------------------------
    # Lectura
    # -------------------------------------------------------------------------

    def extract(self, path: Path) -> ExtractionResult:
        """Lee los metadatos de un archivo (ver 'MetadataExtractor.extract')."""
        result = self.extract_batch([path])[0]
        if result is None:
            raise MetadataError("Lectura cancelada")
        if isinstance(result, Exception):
            raise result
        return result

    def extract_batch(
        self, paths: Sequence[Path], cancel_event: threading.Event | None = None
    ) -> list[ExtractionResult | Exception | None]:
        """Lee los metadatos de varios archivos con las menos llamadas posibles a ExifTool.

        Ver 'MetadataExtractor.extract_batch'. Un fallo general de ExifTool (no se
        puede ejecutar) se propaga como excepción: no tiene sentido seguir.
        """
        existing = [path for path in paths if path.exists()]
        sidecars_of = {path: find_sidecars(path) for path in existing}
        to_read = [*existing, *(sidecar for found in sidecars_of.values() for sidecar in found)]

        metadata = self._read_isolating(to_read, cancel_event)

        outputs: list[ExtractionResult | Exception | None] = []
        for path in paths:
            if path not in sidecars_of:  # no existe
                outputs.append(FileNotFoundError(str(path)))
                continue
            main = metadata.get(path)
            if main is None:  # no se llegó a leer (cancelado)
                outputs.append(None)
            elif main.error:
                outputs.append(MetadataError(f"ExifTool no pudo leerlo: {main.error}"))
            elif any(sidecar not in metadata for sidecar in sidecars_of[path]):
                # Se leyó el archivo pero no su sidecar (se canceló entre medias): se trata
                # como no leído, para no guardar unos datos a medias
                outputs.append(None)
            else:
                found = sidecars_of[path]
                sidecar_metadata = [
                    metadata[sidecar]
                    for sidecar in found
                    if sidecar in metadata and not metadata[sidecar].error
                ]
                tags = self._combine(main.tags, sidecar_metadata)
                user_tags = self._user_data_source(
                    path, main.tags, sidecar_metadata, complete=len(sidecar_metadata) == len(found)
                )
                outputs.append(
                    self._build(path, tags, has_sidecar=bool(found), user_tags=user_tags)
                )
        return outputs

    # -------------------------------------------------------------------------
    # Pasos internos
    # -------------------------------------------------------------------------

    def _read_isolating(
        self, paths: list[Path], cancel_event: threading.Event | None
    ) -> dict[Path, FileMetadata]:
        """Lee con ExifTool; si falla un lote, lo divide para aislar al archivo culpable."""
        if not paths:
            return {}
        try:
            return self._runner.read(paths, cancel_event=cancel_event)
        except ExifToolFileError as error:
            if len(paths) == 1:
                # Este es el culpable: se anota como un fallo de ese archivo
                logger.warning(f"ExifTool no pudo leer '{paths[0]}': {error}")
                return {paths[0]: FileMetadata(paths[0], error=str(error))}
            middle = len(paths) // 2
            logger.debug(f"ExifTool falló con {len(paths)} archivos; se reintenta por partes")
            results = self._read_isolating(paths[:middle], cancel_event)
            results.update(self._read_isolating(paths[middle:], cancel_event))
            return results

    @staticmethod
    def _user_data_source(
        path: Path,
        own_tags: Mapping[str, Any],
        sidecars: Sequence[FileMetadata],
        *,
        complete: bool,
    ) -> Mapping[str, Any] | None:
        """De dónde se leen la valoración, la marca y el color: de donde la aplicación los
        escribe (ver core/userdata/policy.py).

        - RAW (destino sidecar): del sidecar SOLO, si existe (como Lightroom; el XMP que
          la cámara guardó dentro del RAW no cuenta). Sin sidecar, del propio RAW.
        - Los demás (destino incrustado): del propio archivo SOLO. En una pareja RAW +
          JPEG ('IMG_1.CR3' + 'IMG_1.JPG'), el sidecar 'IMG_1.xmp' es del RAW y su
          valoración no debe pasar al JPEG (Lightroom tampoco lo hace).

        Returns:
            Las etiquetas de las que leerlos, o None si NO se pueden leer con seguridad
            (algún sidecar no se leyó: cancelado o con error). None no es "sin datos":
            es "no se sabe", y entonces no se toca nada del catálogo.
        """
        if destination_for(path) is not UserDataDestination.XMP_SIDECAR:
            return own_tags
        if not complete:
            return None
        if sidecars:
            return ExifToolExtractor._combine({}, sidecars)
        return own_tags

    @staticmethod
    def _combine(
        tags: Mapping[str, Any], sidecars: Sequence[FileMetadata]
    ) -> dict[str, Any]:
        """Combina las etiquetas del archivo con las de sus sidecars.

        Solo se toman las etiquetas XMP del sidecar, y pisan a las del XMP incrustado
        con el mismo nombre. Las EXIF e IPTC siguen siendo las del archivo. Si hay
        varios sidecars, el primero (convención de Adobe) gana.
        """
        combined = dict(tags)
        for sidecar in reversed(sidecars):  # el de mayor prioridad se aplica el último
            combined.update({k: v for k, v in sidecar.tags.items() if k.startswith("XMP")})
        return combined

    def _build(
        self,
        path: Path,
        tags: Mapping[str, Any],
        *,
        has_sidecar: bool,
        user_tags: Mapping[str, Any] | None | EllipsisType = ...,
    ) -> ExtractionResult:
        """Rellena los campos de la lista y aplica las reglas especiales.

        Args:
            path: Ruta del archivo.
            tags: Etiquetas del archivo con las de sus sidecars ya combinadas.
            has_sidecar: Si tiene algún sidecar .xmp.
            user_tags: Etiquetas de las que leer los datos del usuario (ver
                '_user_data_source'). None = no se pueden leer con seguridad
                ('user_data' queda vacío y el catálogo no se toca). Si no se indica,
                se usan 'tags'.
        """
        common: dict[str, Any] = {}
        details: dict[str, Any] = {}
        for spec in self.fields:
            target = common if spec.target == "common" else details
            target[spec.column] = read_field(spec, tags)
        common["has_xmp_sidecar"] = 1 if has_sidecar else 0
        self.apply_rules(tags, common, details, path)
        # Datos del usuario presentes en el archivo (None = el archivo no dice nada de ese
        # campo). Vacío si no se pueden leer con seguridad.
        source = tags if user_tags is ... else user_tags
        user_data: dict[str, Any] = (
            {}
            if source is None
            else {spec.column: read_field(spec, source) for spec in self.user_fields}
        )
        if source is not None and self.reads_keywords:
            user_data["keywords"] = read_keywords(source)
        return ExtractionResult(common=common, details=details, user_data=user_data)


if __name__ == "__main__":
    # Autoprueba con un ExifTool SIMULADO y un tipo de medio inventado.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.exiftool_extractor
    import sys
    import tempfile

    from core.catalog.media_types import MediaType
    from core.metadata.base import UnsupportedFormatError
    from core.metadata.exiftool_runner import ExifToolLaunchError
    from core.metadata.field_spec import common, detail, integer, text

    FAKE_EXIFTOOL = r'''
import json, os, sys
args = sys.argv[1:]
if "-ver" in args:
    print("12.99"); sys.exit(0)
files = open(args[args.index("-@") + 1], encoding="utf-8").read().splitlines()
if any("explota" in f for f in files):
    sys.stderr.write("caída"); sys.exit(1)
entries = []
for f in files:
    name = os.path.basename(f)
    if f.endswith(".xmp"):
        entries.append({"SourceFile": f, "XMP-photoshop:City": "Getafe", "XMP-dc:Title": "Título del sidecar"})
    elif "corrupto" in name:
        entries.append({"SourceFile": f, "ExifTool:Error": "File format error"})
    else:
        entries.append({"SourceFile": f, "IFD0:Make": "Apple", "ExifIFD:ISO": 200,
                        "XMP-photoshop:City": "Madrid", "IPTC:City": "Alcobendas", "XMP-dc:Title": "Título incrustado"})
sys.stdout.buffer.write(json.dumps(entries, ensure_ascii=False).encode("utf-8"))
'''

    class TestExtractor(ExifToolExtractor):
        """Tipo de medio inventado para la prueba."""

        media_type = MediaType.PHOTO
        version = 1
        details_table = "photo_details"
        fields = (
            common("city", ("XMP-photoshop:City", "IPTC:City"), text),
            common("title", ("XMP-dc:Title",), text),
            detail("camera_make", ("IFD0:Make",), text),
            detail("iso", ("ExifIFD:ISO",), integer),
        )

        def apply_rules(self, tags, common, details, path):
            common["description"] = f"regla aplicada a {path.name}"  # una regla cualquiera

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        fake = base / "fake_exiftool.py"
        fake.write_text(FAKE_EXIFTOOL, encoding="utf-8")
        runner = ExifToolRunner(command=[sys.executable, str(fake)], batch_size=100)
        extractor = TestExtractor(runner)

        names = ["a.jpg", "b.dng", "corrupto.jpg", "con_sidecar.cr3", "explota.jpg", "c.heic"]
        for name in names:
            (base / name).write_bytes(b"x")
        (base / "con_sidecar.xmp").write_text("<x/>")  # sidecar con la convención de Adobe
        paths = [base / name for name in names] + [base / "no_existe.jpg"]

        # 1. Un lote con casos mezclados: el que "explota" tira ExifTool entero
        results = extractor.extract_batch(paths)
        by_name = {path.name: result for path, result in zip(paths, results, strict=True)}
        calls_for_batch = runner.calls
        print(f"Lote de {len(paths)} archivos: {calls_for_batch} llamadas a ExifTool (con aislamiento del culpable)")

        good = by_name["a.jpg"]
        assert isinstance(good, ExtractionResult)
        assert good.common["city"] == "Madrid"  # XMP antes que IPTC (orden de la lista)
        assert good.common["title"] == "Título incrustado" and good.common["has_xmp_sidecar"] == 0
        assert good.details == {"camera_make": "Apple", "iso": 200}
        assert good.common["description"] == "regla aplicada a a.jpg"  # la regla se aplicó

        # El sidecar manda sobre el XMP incrustado y se anota que existe
        with_sidecar = by_name["con_sidecar.cr3"]
        assert with_sidecar.common["city"] == "Getafe" and with_sidecar.common["title"] == "Título del sidecar"
        assert with_sidecar.common["has_xmp_sidecar"] == 1
        assert with_sidecar.details["camera_make"] == "Apple"  # lo que no es XMP viene del archivo
        print("Sidecar: su XMP manda sobre el incrustado; EXIF sigue siendo el del archivo")

        # Errores por archivo, sin parar a los demás
        assert isinstance(by_name["no_existe.jpg"], FileNotFoundError)
        assert isinstance(by_name["corrupto.jpg"], MetadataError)
        assert "File format error" in str(by_name["corrupto.jpg"])
        assert isinstance(by_name["explota.jpg"], MetadataError)  # aislado: solo ese falla
        assert isinstance(by_name["c.heic"], ExtractionResult) and isinstance(by_name["b.dng"], ExtractionResult)
        print("Aislamiento: el archivo que hace caer ExifTool falla solo; los demás se leen")

        # 2. Si todo va bien, una sola llamada para todo el lote
        healthy = [base / "a.jpg", base / "b.dng", base / "c.heic"]
        runner.calls = 0
        assert all(isinstance(r, ExtractionResult) for r in extractor.extract_batch(healthy))
        assert runner.calls == 1
        print("Lote sano de 3 archivos: 1 sola llamada a ExifTool")

        # 3. 'extract' (un archivo) lanza las excepciones en vez de devolverlas
        assert isinstance(extractor.extract(base / "a.jpg"), ExtractionResult)
        for name, expected in (("no_existe.jpg", FileNotFoundError), ("corrupto.jpg", MetadataError)):
            try:
                extractor.extract(base / name)
            except expected:
                pass
            else:
                raise AssertionError(f"{name} debería lanzar {expected.__name__}")

        # 4. Cancelación: lo que no se llegó a leer vuelve como None
        event = threading.Event()
        event.set()
        assert extractor.extract_batch([base / "a.jpg"], cancel_event=event) == [None]

        # 5. Un fallo GENERAL de ExifTool no se aísla archivo a archivo: se propaga
        broken = TestExtractor(ExifToolRunner(command=[str(base / "no_existe_exiftool")]))
        try:
            broken.extract_batch([base / "a.jpg", base / "b.dng"])
        except ExifToolLaunchError as error:
            print("Fallo general de ExifTool: se propaga (", str(error)[:45], "...)")
        else:
            raise AssertionError("Un fallo general debería propagarse")
        assert not isinstance(UnsupportedFormatError("x"), ExifToolLaunchError)

    print("Autoprueba finalizada correctamente.")
