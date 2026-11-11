"""Escritura en XMP con ExifTool: valoración, marca, color, palabras clave y metadatos editados.

Este módulo NO depende de Qt ni de la base de datos: recibe rutas y valores, escribe y
comprueba. Quién decide QUÉ escribir y CUÁNDO es 'sync.py'.

Etiquetas que se escriben (las mismas que Lightroom Classic y que lee el extractor):

    rating       XMP-xmp:Rating               0 a 5 (el 0 se escribe: "sin estrellas")
    flag         XMP-xmpDM:Pick               1 marcada, 0 sin marca, -1 rechazada
                 XMP-xmpDM:Good               True / False (Lightroom escribe las dos;
                                              sin marca, se borra)
    color_label  XMP-photoshop:LabelColor     'red', 'blue'... (inglés)
                 XMP-xmp:Label                texto del juego de etiquetas de Lightroom
                                              ('Roja', 'Azul'...; ver XMP_LABEL_TEXTS)
    keywords     XMP-lr:HierarchicalSubject   las rutas asignadas ('Coche|Opel Astra')
                 XMP-dc:Subject               lista plana: cada palabra y sus padres
                                              ('Coche', 'Opel Astra'), como Lightroom
                 IPTC:Keywords                la misma lista plana, SOLO si el archivo ya
                                              la tenía (si no, al quitar todas las palabras
                                              del XMP volverían a leerse las viejas de IPTC)
    title, description, creator, copyright, sublocation, city, region, country,
    country_code (los metadatos editables: 'editable_fields.py')
                 su etiqueta XMP, siempre ('XMP-dc:Title'...), y las antiguas (IPTC, EXIF:
                 'IPTC:ObjectName'...) SOLO si el archivo ya las tiene, por lo mismo que
                 'IPTC:Keywords'. Vacío = se borran. Para saber si ya está al día y para
                 comprobar lo escrito se lee como el extractor: la primera etiqueta no
                 vacía (XMP > IPTC > EXIF). Así lo recortado del IPTC (límites de longitud)
                 o cambiado por '?' (IPTC en Latin) no cuenta: manda el XMP, que va entero.
    latitude, longitude, altitude, gps_direction (el GPS: números; docs/DECISIONES.md, 11/11/2026)
                 en las etiquetas de GPS que ya tenga el archivo ('XMP-exif:GPS*', 'GPS:GPS*'
                 del EXIF, o los dos) y, si no tiene ninguna, en el EXIF, como Lightroom;
                 en un sidecar o un GIF, solo el XMP. Con su referencia: N/S y E/O en el
                 EXIF (en el XMP van con signo), sobre o bajo el nivel del mar (0/1) y la
                 dirección respecto al norte verdadero (T). Vacío = se borran, valor y
                 referencia, allí donde estén. Se comprueba como lo lee el extractor
                 ('gps_from_tags', XMP primero) y con margen (el EXIF guarda fracciones:
                 42,682089 vuelve como 42,6820889999).

Resumen IPTC ('Photoshop:IPTCDigest'): si el archivo lo tiene y se toca alguna etiqueta
IPTC (también 'IPTC:Keywords'), se recalcula ('=new'): ExifTool no lo hace solo, y con el
resumen desajustado Lightroom toma el IPTC antes que el XMP (comprobado el 10/11/2026).

Saltos de línea (el pie de ilustración): el archivo de argumentos de ExifTool lleva un
argumento por línea, así que esas líneas van escapadas y con '#[CSTR]' delante.

Por qué el 0 se escribe y no se borra la etiqueta: al releer, una etiqueta AUSENTE
significa "el archivo no dice nada" y no toca el catálogo; un 0 escrito significa "sin
estrellas" y sí lo cambia. Así un RAW cuya cámara guardó una valoración dentro no la
recupera al quitarle las estrellas aquí (se crea su sidecar con Rating = 0).

Medidas de seguridad:
    - Solo se tocan los campos que se piden (los PENDIENTES del elemento: si en la
      aplicación solo se cambió el color, la valoración del archivo no se toca) y, de
      ellos, solo los que CAMBIAN. Antes de escribir se
      leen los valores actuales del archivo: si ya coinciden, el archivo no se toca
      (ni siquiera cambia su fecha de modificación). Una etiqueta personalizada de
      Lightroom (un texto en 'xmp:Label' que no es un color) no se borra si el color no
      cambia.
    - Nunca se reescribe el XMP entero ni la imagen: ExifTool modifica solo esas
      etiquetas y conserva todo lo demás (ajustes de revelado de Lightroom, EXIF...).
    - ExifTool escribe en un archivo temporal y lo cambia por el original al final
      ('-overwrite_original'): si algo se corta a mitad, el original queda intacto.
    - Después de escribir se VUELVE A LEER el archivo: solo cuenta como escrito si
      ahora tiene exactamente los valores pedidos.
    - Un archivo que falla no afecta a los demás del lote.
    - Si una escritura anterior se cortó y dejó el temporal de ExifTool
      ('foto.jpg_exiftool_tmp'), ExifTool se negaría a escribir para siempre: un temporal
      de más de 10 minutos se borra (el original nunca llegó a sustituirse: está intacto).

Rendimiento: arrancar ExifTool tarda unos cientos de milisegundos, así que cada lote
de archivos se escribe con UNA sola llamada ('-execute' separa los archivos dentro de
la misma llamada) y se lee con otra antes y otra después.

1.3.0 El GPS editado (latitud, longitud, altitud y dirección): donde ya esté y, si no está,
      en el EXIF; con sus referencias; comprobado como el extractor y con margen.
1.2.1 Los metadatos editados que se leen y escriben aquí son los de TEXTO: el GPS (números)
      lleva su propia regla, en el paso 4 de su edición.
1.2.0 Metadatos editados (título, pie, ubicación...): XMP y antiguas que existan,
      comprobados como los lee el extractor; resumen IPTC recalculado al tocar el IPTC
      (también con las palabras clave, que antes lo dejaban desajustado); '#[CSTR]' en los
      valores con saltos de línea; los avisos '[Minor]' de ExifTool también se ignoran.
1.1.2 Marca de la salida de ExifTool con el nombre nuevo de la aplicación ('@@ARCA ').
1.1.1 Las palabras clave se comparan letra a letra para decidir si se escribe: renombrar
      solo con mayúsculas o acentos («Familia» -> «Família») también llega al archivo.

Prueba rápida (necesita ExifTool instalado; trabaja sobre archivos de prueba temporales):
    python -m core.userdata.xmp_writer
"""

__version__ = "1.3.0"
__all__ = [
    "XMP_READ_TAGS",
    "XmpWriteOutcome",
    "XmpWriteRequest",
    "XmpUserDataWriter",
    "edited_values_from_tags",
    "keyword_paths_from_tags",
    "user_values_from_tags",
]

# Librerías estándar
import re
import subprocess
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.color_labels import (
    XMP_LABEL_TEXTS,
    color_label_from_xmp,
    normalize_color_label,
)
from core.catalog.keywords import flat_keyword_names, same_keywords
from core.metadata.exiftool_runner import (
    ExifToolError,
    ExifToolFileError,
    ExifToolLaunchError,
    ExifToolRunner,
)
from core.metadata.field_spec import common, pick_flag, rating_value, read_field, text
from core.metadata.image.rules import GPS_SOURCE_TAGS, gps_from_tags
from core.metadata.keyword_tags import HIERARCHY_SEPARATOR, read_keywords
from core.userdata.editable_fields import EDITABLE_FIELDS, NUMBER, TEXT, EditableField, field_for

# Resumen del bloque IPTC que guardan Photoshop y Lightroom (ver la cabecera)
_IPTC_DIGEST_TAG = "Photoshop:IPTCDigest"

# Metadatos editables de TEXTO (título, pie, ubicación...): XMP y las antiguas que existan.
# Los del GPS son números y se escriben con otra regla (docs/DECISIONES.md, 11/11/2026)
_TEXT_FIELDS = tuple(spec for spec in EDITABLE_FIELDS if spec.kind == TEXT)

# El GPS (números): latitud, longitud, altitud y dirección
_GPS_FIELDS = tuple(spec for spec in EDITABLE_FIELDS if spec.kind == NUMBER)
_GPS_COLUMNS = frozenset(spec.column for spec in _GPS_FIELDS)

# En el XMP, la latitud y la longitud llevan el signo en el propio valor ('41,23.244N'):
# no tienen etiqueta de referencia. En el EXIF, el valor va sin signo y la referencia aparte
_SIGNED_IN_XMP = frozenset({"latitude", "longitude"})

# Destinos donde no se puede escribir el EXIF: un sidecar (es solo XMP) y el GIF
_XMP_ONLY_SUFFIXES = frozenset({".xmp", ".gif"})

# Margen al comparar el GPS del archivo con el pedido: el EXIF guarda fracciones (grados,
# minutos y segundos) y el XMP, minutos con decimales. 1e-6° son unos 11 cm
_GPS_TOLERANCE: dict[str, float] = {
    "latitude": 1e-6, "longitude": 1e-6, "altitude": 0.05, "gps_direction": 0.01,
}  # fmt: skip


def _gps_targets(spec: EditableField) -> tuple[tuple[str, str | None, bool], ...]:
    """Dónde va un campo del GPS: (etiqueta del valor, su referencia o None, es del XMP)."""
    exif_tag = spec.legacy_tags[0]
    xmp_ref = None if spec.column in _SIGNED_IN_XMP else f"{spec.xmp_tag}Ref"
    return ((spec.xmp_tag, xmp_ref, True), (exif_tag, f"{exif_tag}Ref", False))

# Etiquetas que se leen para saber qué valores tiene ya un archivo
XMP_READ_TAGS: tuple[str, ...] = (
    "-XMP-xmp:Rating",
    "-XMP-xmpDM:Pick",
    "-XMP-xmpDM:Good",
    "-XMP-photoshop:LabelColor",
    "-XMP-xmp:Label",
    "-XMP-dc:Subject",
    "-XMP-lr:HierarchicalSubject",
    "-IPTC:Keywords",
    *(f"-{tag}" for spec in _TEXT_FIELDS for tag in (spec.xmp_tag, *spec.legacy_tags)),
    # El GPS: lo que lee el extractor y, para saber dónde está, cada etiqueta y su referencia
    *dict.fromkeys(
        f"-{tag}"
        for tag in (
            *GPS_SOURCE_TAGS,
            *(t for spec in _GPS_FIELDS for target in _gps_targets(spec) for t in target[:2] if t),
        )
    ),
    f"-{_IPTC_DIGEST_TAG}",
)

# Cómo se lee cada metadato editable: igual que el extractor ('IMAGE_FIELDS'), la primera
# etiqueta no vacía en el orden XMP > antiguas
_EDITABLE_READ = {
    spec.column: common(spec.column, (spec.xmp_tag, *spec.legacy_tags), text)
    for spec in _TEXT_FIELDS
}

# Un texto que parece un número (ExifTool lo entrega como número: '1.50' -> 1.5)
_NUMBER_TEXT = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)")

# Archivos por llamada de escritura
_WRITE_BATCH_SIZE = 25

# Segundos máximos por llamada de escritura (ExifTool copia el archivo entero: 25 TIFF o
# DNG grandes en una unidad de red pueden tardar)
_WRITE_TIMEOUT_SECONDS = 600.0

# Antigüedad a partir de la cual un temporal de ExifTool se considera abandonado
_STALE_TEMP_SECONDS = 600.0

# Marca que se escribe en la salida de errores antes de cada archivo, para saber a qué
# archivo pertenece cada mensaje de ExifTool
_MARK = "@@ARCA "

# En Windows, evita que aparezca una ventana de consola en cada llamada
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True, slots=True)
class XmpWriteRequest:
    """Valores que debe tener un archivo XMP (o un archivo con XMP incrustado).

    Attributes:
        path: Archivo donde se escribe: el propio original (XMP incrustado) o su
            sidecar '.xmp' (que se crea si no existe).
        values: SOLO los campos que hay que dejar con ese valor ('rating' 0-5, 'flag'
            -1/0/1, 'color_label' nombre canónico o None, 'keywords' las rutas asignadas,
            p. ej. (('Coche', 'Opel Astra'),), y las columnas editables con su texto o
            None para vaciarlas; el título, ya sin el nombre del archivo: 'file_title';
            el GPS, con su número: latitud y longitud con signo, altitud negativa bajo
            el nivel del mar).
            Los que no estén no se tocan.
    """

    path: Path
    values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class XmpWriteOutcome:
    """Qué ha pasado con un archivo.

    Attributes:
        request: Lo que se pidió.
        ok: True si el archivo tiene ya los valores pedidos (escritos ahora o antes).
        written: True si se ha modificado el archivo (False si ya los tenía o si falló).
        message: Motivo del fallo (texto de ExifTool), o '' si fue bien.
    """

    request: XmpWriteRequest
    ok: bool
    written: bool = False
    message: str = ""


def user_values_from_tags(tags: Mapping[str, Any]) -> dict[str, Any]:
    """Valores del usuario que tiene un archivo, con los valores por defecto si faltan.

    Usa las mismas reglas que la lectura al importar ('IMAGE_USER_FIELDS'): rating 0-5,
    marca de 'xmpDM:Pick' y color de 'photoshop:LabelColor' o, si falta, de 'xmp:Label'.
    """
    rating = rating_value(tags.get("XMP-xmp:Rating"))
    flag = pick_flag(tags.get("XMP-xmpDM:Pick"))
    color = color_label_from_xmp(tags.get("XMP-xmp:Label"), tags.get("XMP-photoshop:LabelColor"))
    return {"rating": rating or 0, "flag": flag or 0, "color_label": color}


def keyword_paths_from_tags(tags: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    """Palabras clave que tiene un archivo, como rutas (con la misma regla que al importar:
    'keyword_tags.read_keywords'). Las sueltas, como rutas de una palabra."""
    found = read_keywords(tags)
    return (*found.paths, *((name,) for name in found.flat))


def edited_values_from_tags(tags: Mapping[str, Any]) -> dict[str, str | None]:
    """Metadatos editables que tiene un archivo, leídos como los lee el extractor.

    De cada campo, la primera etiqueta no vacía (XMP > IPTC > EXIF), como texto; None si
    no tiene ninguna.
    """
    return {column: read_field(spec, tags) for column, spec in _EDITABLE_READ.items()}


def _same_text(current: str | None, wanted: str | None) -> bool:
    """True si el texto del archivo es el pedido.

    ExifTool entrega como número un texto que lo parece ('1.50' llega como 1.5): en ese
    caso se comparan como números, para no reintentar para siempre un título como «1.50».
    """
    if current == wanted:
        return True
    if current is None or wanted is None or not _NUMBER_TEXT.fullmatch(wanted):
        return False
    try:
        return float(current) == float(wanted)
    except ValueError:
        return False


def _edited_arguments(
    column: str, value: str | None, current_tags: Mapping[str, Any]
) -> list[str]:
    """Argumentos para dejar un metadato editable con ese valor (None = vaciarlo).

    La etiqueta XMP siempre; las antiguas, solo las que el archivo ya tiene (si no, al
    vaciar el campo volvería a leerse su valor antiguo).
    """
    spec = field_for(column)
    tags = [spec.xmp_tag, *(tag for tag in spec.legacy_tags if current_tags.get(tag) is not None)]
    new_text = "" if value is None else value
    return [f"-{tag}={new_text}" for tag in tags]


def _same_number(column: str, current: float | None, wanted: float | None) -> bool:
    """True si el número del archivo es el pedido, con el margen de su campo."""
    if current is None or wanted is None:
        return current is None and wanted is None
    return abs(current - wanted) <= _GPS_TOLERANCE[column]


def _gps_reference(column: str, value: float) -> str:
    """Valor de la etiqueta de referencia de un campo del GPS (sin conversión: con '#')."""
    if column == "latitude":
        return "N" if value >= 0 else "S"
    if column == "longitude":
        return "E" if value >= 0 else "W"
    if column == "altitude":
        return "1" if value < 0 else "0"  # 1 = bajo el nivel del mar
    return "T"  # dirección: respecto al norte verdadero, como las cámaras y Lightroom


def _number_text(value: float) -> str:
    """Número para ExifTool: punto decimal, sin notación científica ni ceros de más."""
    return f"{value:.8f}".rstrip("0").rstrip(".") or "0"


def _gps_arguments(
    path: Path, wanted: Mapping[str, Any], current_tags: Mapping[str, Any]
) -> list[str]:
    """Argumentos para dejar el GPS pedido (solo los campos que cambian).

    Regla (docs/DECISIONES.md, 11/11/2026): en los grupos de GPS que ya tenga el archivo
    (XMP, EXIF o los dos) y, si no tiene ninguno, en el EXIF, como Lightroom; en un
    sidecar o un GIF, solo el XMP. Vaciar borra el valor y su referencia allí donde
    estén. Los valores van con '#' (sin la conversión de texto de ExifTool: «1» como
    referencia de la altitud se escribiría 0; ver docs/TRAMPAS.md).
    """
    columns = [spec for spec in _GPS_FIELDS if spec.column in wanted]
    if not columns:
        return []
    current = gps_from_tags(current_tags)
    xmp_only = path.suffix.lower() in _XMP_ONLY_SUFFIXES
    has_xmp = any(current_tags.get(spec.xmp_tag) is not None for spec in _GPS_FIELDS)
    has_exif = any(current_tags.get(spec.legacy_tags[0]) is not None for spec in _GPS_FIELDS)
    if xmp_only:
        use_xmp, use_exif = True, False
    elif has_xmp or has_exif:
        use_xmp, use_exif = has_xmp, has_exif
    else:
        use_xmp, use_exif = False, True  # sin GPS: en el EXIF, como Lightroom

    args: list[str] = []
    for spec in columns:
        value = wanted[spec.column]
        if _same_number(spec.column, current[spec.column], value):
            continue
        for tag, ref_tag, is_xmp in _gps_targets(spec):
            if not is_xmp and xmp_only:
                continue
            if value is None:
                # Se borra donde esté (si quedara en un grupo, al releer volvería)
                if current_tags.get(tag) is not None:
                    args.append(f"-{tag}=")
                    if ref_tag:
                        args.append(f"-{ref_tag}=")
            elif use_xmp if is_xmp else use_exif:
                number = value if is_xmp and spec.column in _SIGNED_IN_XMP else abs(value)
                args.append(f"-{tag}#={_number_text(number)}")
                if ref_tag:
                    args.append(f"-{ref_tag}#={_gps_reference(spec.column, value)}")
    return args


def _keyword_arguments(wanted: Sequence[Sequence[str]], current_tags: Mapping[str, Any]) -> list[str]:
    """Argumentos para dejar EXACTAMENTE esas palabras (las listas se vacían y se rellenan)."""
    args = ["-XMP-lr:HierarchicalSubject="]
    args += [f"-XMP-lr:HierarchicalSubject={HIERARCHY_SEPARATOR.join(path)}" for path in wanted]
    flat = flat_keyword_names(wanted)
    args.append("-XMP-dc:Subject=")
    args += [f"-XMP-dc:Subject={name}" for name in flat]
    if current_tags.get("IPTC:Keywords") is not None:
        args.append("-IPTC:Keywords=")
        args += [f"-IPTC:Keywords={name}" for name in flat]
    return args


def _arguments_for(
    request: XmpWriteRequest, current_tags: Mapping[str, Any], *, creating: bool
) -> list[str]:
    """Argumentos de ExifTool para dejar el archivo con los valores pedidos.

    Args:
        request: Lo que se pide (solo los campos pendientes).
        current_tags: Etiquetas que tiene ahora el archivo.
        creating: True si el archivo aún no existe (un sidecar nuevo). Entonces se
            escriben la valoración y la marca aunque valgan 0: así el sidecar dice
            explícitamente "sin estrellas" y no vale lo que la cámara guardó en el RAW.

    Returns:
        Solo las etiquetas de los campos pedidos que cambian (vacío = nada que hacer).
    """
    current = user_values_from_tags(current_tags)
    wanted = request.values
    args: list[str] = []

    if "rating" in wanted and (creating or current["rating"] != wanted["rating"]):
        args.append(f"-XMP-xmp:Rating={wanted['rating']}")

    if "flag" in wanted and (creating or current["flag"] != wanted["flag"]):
        if wanted["flag"] == 0:
            args += ["-XMP-xmpDM:Pick=0", "-XMP-xmpDM:Good="]
        else:
            good = "true" if wanted["flag"] == 1 else "false"
            args += [f"-XMP-xmpDM:Pick={wanted['flag']}", f"-XMP-xmpDM:Good={good}"]

    if "color_label" in wanted and current["color_label"] != wanted["color_label"]:
        color = wanted["color_label"]
        if color is None:
            args.append("-XMP-photoshop:LabelColor=")
            # 'xmp:Label' solo se borra si es un color: un texto personalizado de
            # Lightroom ('Revisar', 'Para imprimir'...) no es una etiqueta de color
            if normalize_color_label(current_tags.get("XMP-xmp:Label")) is not None:
                args.append("-XMP-xmp:Label=")
        else:
            # Si el archivo ya tiene un texto de ese mismo color (p. ej. 'Rojo' en otro
            # juego de etiquetas), se conserva; si no, el texto de Lightroom en español
            label_text = current_tags.get("XMP-xmp:Label")
            if normalize_color_label(label_text) != color:
                label_text = XMP_LABEL_TEXTS[color]
            args += [f"-XMP-photoshop:LabelColor={color}", f"-XMP-xmp:Label={label_text}"]

    # Letra a letra: un cambio solo de mayúsculas o acentos (renombrar) también se escribe
    if "keywords" in wanted and not same_keywords(
        keyword_paths_from_tags(current_tags), wanted["keywords"], exact=True
    ):
        args += _keyword_arguments(wanted["keywords"], current_tags)

    # Metadatos editables: solo los que, leídos como el extractor, no tienen ya ese valor
    current_edits = edited_values_from_tags(current_tags)
    for column, current_value in current_edits.items():
        if column in wanted and not _same_text(current_value, wanted[column]):
            args += _edited_arguments(column, wanted[column], current_tags)

    # El GPS (números), con su propia regla
    args += _gps_arguments(request.path, wanted, current_tags)

    # Si se toca el IPTC de un archivo con resumen IPTC, se recalcula (ver la cabecera)
    if current_tags.get(_IPTC_DIGEST_TAG) is not None and any(
        arg.startswith("-IPTC:") for arg in args
    ):
        args.append(f"-{_IPTC_DIGEST_TAG}=new")
    return args


def _matches(tags: Mapping[str, Any], wanted: Mapping[str, Any]) -> bool:
    """True si el archivo tiene ya los valores pedidos (solo se comparan esos campos)."""
    current = user_values_from_tags(tags)
    edits = edited_values_from_tags(tags)
    gps = gps_from_tags(tags) if _GPS_COLUMNS & wanted.keys() else {}
    for field, value in wanted.items():
        if field == "keywords":
            if not same_keywords(keyword_paths_from_tags(tags), value, exact=True):
                return False
        elif field in edits:
            if not _same_text(edits[field], value):
                return False
        elif field in _GPS_COLUMNS:
            if not _same_number(field, gps[field], value):
                return False
        elif current[field] != value:
            return False
    return True


def _remove_stale_temp(path: Path) -> None:
    """Borra el temporal que deja ExifTool si una escritura anterior se cortó.

    ExifTool escribe en 'archivo_exiftool_tmp' y solo al final lo cambia por el original;
    si se corta (cierre, apagado, tiempo agotado), el temporal se queda y ExifTool ya no
    escribe ese archivo nunca más ("Temporary file already exists"). El original sigue
    intacto. Solo se borra si tiene más de unos minutos (no es de una escritura en curso).
    """
    temp = path.with_name(path.name + "_exiftool_tmp")
    try:
        if temp.is_file() and time.time() - temp.stat().st_mtime > _STALE_TEMP_SECONDS:
            temp.unlink()
            logger.warning(f"Borrado un temporal antiguo de ExifTool: {temp}")
    except OSError as error:
        logger.debug(f"No se pudo revisar el temporal {temp}: {error}")


class XmpUserDataWriter:
    """Escribe en XMP (incrustado o sidecar) con ExifTool los datos que se le piden."""

    def __init__(self, runner: ExifToolRunner) -> None:
        """Crea el escritor.

        Args:
            runner: Lector de ExifTool ya configurado (se usa su comando y su lectura).
        """
        self._runner = runner
        self.calls = 0  # llamadas de escritura a ExifTool (para pruebas y diagnóstico)

    def write(
        self,
        requests: Sequence[XmpWriteRequest],
        cancel_event: threading.Event | None = None,
    ) -> list[XmpWriteOutcome]:
        """Deja cada archivo con los valores pedidos.

        Args:
            requests: Un 'XmpWriteRequest' por archivo.
            cancel_event: Si se activa, no se empiezan lotes nuevos.

        Returns:
            Un resultado por cada petición tratada, en el mismo orden (si se cancela o
            ExifTool deja de funcionar a mitad, las que no se llegaron a tratar no
            aparecen).

        Raises:
            ExifToolLaunchError: Si ExifTool no se puede ejecutar ya en el primer lote
                (fallo general: no tiene sentido seguir con más archivos).
        """
        outcomes: list[XmpWriteOutcome] = []
        for start in range(0, len(requests), _WRITE_BATCH_SIZE):
            if cancel_event is not None and cancel_event.is_set():
                break
            try:
                outcomes += self._write_batch(list(requests[start : start + _WRITE_BATCH_SIZE]))
            except ExifToolLaunchError:
                if not outcomes:
                    raise
                # Lo ya escrito se conserva (quien llama lo anota); el resto queda sin tratar
                logger.exception("ExifTool dejó de funcionar a mitad de la escritura")
                break
        return outcomes

    # -------------------------------------------------------------------------
    # Pasos internos
    # -------------------------------------------------------------------------

    def _write_batch(self, batch: list[XmpWriteRequest]) -> list[XmpWriteOutcome]:
        """Lee, escribe lo que haga falta y comprueba un lote de archivos."""
        # 1. Valores actuales. Un sidecar que aún no existe no tiene ninguno.
        existing = [request.path for request in batch if request.path.exists()]
        before = self._read(existing)

        results: dict[int, XmpWriteOutcome] = {}
        to_write: list[tuple[int, XmpWriteRequest, list[str]]] = []
        for index, request in enumerate(batch):
            tags: Mapping[str, Any] = {}
            if request.path.exists():
                metadata = before.get(request.path)
                if metadata is None or metadata.error:
                    message = metadata.error if metadata else "ExifTool no pudo leerlo"
                    results[index] = XmpWriteOutcome(request, ok=False, message=message)
                    continue
                tags = metadata.tags
            elif request.path.suffix.lower() != ".xmp":
                # El original ha desaparecido (solo un sidecar se puede crear de cero)
                results[index] = XmpWriteOutcome(request, ok=False, message="El archivo no existe")
                continue

            _remove_stale_temp(request.path)
            args = _arguments_for(request, tags, creating=not request.path.exists())
            if not args:
                results[index] = XmpWriteOutcome(request, ok=True)  # ya los tenía
            else:
                to_write.append((index, request, args))

        if to_write:
            # 2. Escritura de todo el lote en una sola llamada
            messages = self._run_write([(request.path, args) for _, request, args in to_write])

            # 3. Comprobación: se vuelve a leer lo escrito
            after = self._read([request.path for _, request, _ in to_write if request.path.exists()])
            for position, (index, request, _) in enumerate(to_write):
                message = messages.get(position, "")
                metadata = after.get(request.path)
                if metadata is not None and not metadata.error:
                    if _matches(metadata.tags, request.values):
                        results[index] = XmpWriteOutcome(request, ok=True, written=True)
                        continue
                    message = message or "Tras escribir, el archivo no tiene los valores pedidos"
                results[index] = XmpWriteOutcome(
                    request, ok=False, message=message or "ExifTool no pudo escribirlo"
                )

        return [results[index] for index in range(len(batch))]

    def _read(self, paths: list[Path]) -> dict[Path, Any]:
        """Lee las etiquetas del usuario de varios archivos (aislando un lote que falle)."""
        if not paths:
            return {}
        try:
            return self._runner.read(paths, tags=XMP_READ_TAGS)
        except ExifToolFileError:
            if len(paths) == 1:
                return {}
            middle = len(paths) // 2
            return {**self._read(paths[:middle]), **self._read(paths[middle:])}

    def _run_write(self, items: list[tuple[Path, list[str]]]) -> dict[int, str]:
        """Ejecuta ExifTool con un bloque de argumentos por archivo ('-execute').

        Returns:
            Posición del archivo en 'items' -> mensajes de error/aviso de ExifTool sobre
            él (solo los que tienen alguno).

        Raises:
            ExifToolLaunchError: Si ExifTool no se puede ejecutar.
        """
        lines: list[str] = []
        for position, (path, args) in enumerate(items):
            # Antes de cada archivo, una marca en la salida de errores para saber a quién
            # pertenece cada mensaje
            arg_lines = [_argument_line(arg) for arg in args]
            lines += ["-echo2", f"{_MARK}{position}", *arg_lines, str(path), "-execute"]

        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", suffix=".txt", delete=False
        ) as arg_file:
            arg_file.write("\n".join(lines) + "\n")
            arg_name = arg_file.name

        command = [
            *self._runner.command,
            "-@",
            arg_name,
            # Opciones comunes a todos los bloques (deben ir al final)
            "-common_args",
            "-overwrite_original",
            "-charset",
            "utf8",
            "-charset",
            "filename=utf8",
        ]
        try:
            self.calls += 1
            completed = subprocess.run(  # comando fijo, sin shell
                command,
                capture_output=True,
                timeout=_WRITE_TIMEOUT_SECONDS,
                creationflags=_CREATE_NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired:
            # Lo que se haya escrito se comprobará al releer; el resto contará como fallo
            logger.warning(f"ExifTool tardó demasiado escribiendo {len(items)} archivos")
            return {position: "ExifTool tardó demasiado" for position in range(len(items))}
        except OSError as exc:
            raise ExifToolLaunchError(f"No se pudo ejecutar ExifTool: {exc}") from exc
        finally:
            Path(arg_name).unlink(missing_ok=True)

        return _split_messages(completed.stderr.decode("utf-8", errors="replace"))


def _argument_line(arg: str) -> str:
    """Un argumento como línea del archivo de argumentos de ExifTool ('-@').

    Cada línea es un argumento, así que uno con saltos de línea (un pie de varias líneas)
    va escapado como en C ('\\n', '\\\\') y con '#[CSTR]' delante de ESA línea (no es una
    cabecera del archivo: ver docs/TRAMPAS.md).
    """
    if "\n" not in arg and "\r" not in arg:
        return arg
    escaped = arg.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    return f"#[CSTR]{escaped}"


def _split_messages(stderr: str) -> dict[int, str]:
    """Reparte la salida de errores de ExifTool entre los archivos (por sus marcas).

    Los avisos menores ('Warning: [minor] ...' o '[Minor]', como el recorte de un valor
    largo en el IPTC) no se guardan.
    """
    messages: dict[int, list[str]] = {}
    current: int | None = None
    for line in stderr.splitlines():
        if line.startswith(_MARK):
            try:
                current = int(line[len(_MARK) :].strip())
            except ValueError:
                current = None
            continue
        line_text = line.strip()
        if (
            current is not None
            and line_text
            and not line_text.lower().startswith("warning: [minor]")
        ):
            messages.setdefault(current, []).append(line_text)
    return {position: " | ".join(texts) for position, texts in messages.items()}


if __name__ == "__main__":
    # Autoprueba con ExifTool real sobre archivos temporales (no toca nada tuyo).
    # Ejecutar desde la raíz del proyecto:  python -m core.userdata.xmp_writer
    import os
    import sys

    from PIL import Image

    try:
        runner = ExifToolRunner()
        runner.version()
    except ExifToolError as error:
        print(f"Sin ExifTool no se puede probar la escritura: {error}")
        sys.exit(0)

    def read_tags(path: Path) -> dict[str, Any]:
        return runner.read([path], tags=XMP_READ_TAGS)[path].tags

    def exiftool(*args: str) -> None:
        subprocess.run([*runner.command, "-overwrite_original", *args], capture_output=True, check=True)

    ALL = ("rating", "flag", "color_label")

    def req(path: Path, rating: int, flag: int, color: str | None, fields=ALL) -> XmpWriteRequest:
        values = {"rating": rating, "flag": flag, "color_label": color}
        return XmpWriteRequest(path, {field: values[field] for field in fields})

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        jpeg = folder / "foto ñ.jpg"  # con acento: comprueba la codificación de rutas
        Image.new("RGB", (32, 24), "red").save(jpeg, quality=90)
        png = folder / "foto.png"
        Image.new("RGB", (32, 24), "blue").save(png)
        raw_sidecar = folder / "IMG_0001.xmp"  # sidecar que todavía no existe
        broken = folder / "roto.jpg"
        broken.write_bytes(b"esto no es un jpeg")

        # 1. Un lote con formatos distintos, un sidecar nuevo y un archivo roto
        writer = XmpUserDataWriter(runner)
        outcomes = writer.write([
            req(jpeg, 3, -1, "red"), req(png, 5, 1, "blue"),
            req(raw_sidecar, 0, 0, None), req(broken, 1, 0, None),
        ])  # fmt: skip
        for outcome in outcomes:
            print(f"{outcome.request.path.name}: ok={outcome.ok} written={outcome.written} {outcome.message}")
        assert [o.ok for o in outcomes] == [True, True, True, False]
        assert writer.calls == 1  # todo el lote en una sola llamada de escritura
        tags = read_tags(jpeg)
        assert tags["XMP-xmp:Label"] == "Roja" and tags["XMP-xmpDM:Good"] is False
        # El sidecar nuevo dice EXPLÍCITAMENTE "sin estrellas y sin marca"
        sidecar_tags = read_tags(raw_sidecar)
        assert sidecar_tags["XMP-xmp:Rating"] == 0 and sidecar_tags["XMP-xmpDM:Pick"] == 0

        # 2. Mismos valores otra vez: no se toca el archivo (ni su fecha)
        mtime = jpeg.stat().st_mtime_ns
        again = writer.write([req(jpeg, 3, -1, "red")])
        assert again[0].ok and not again[0].written and jpeg.stat().st_mtime_ns == mtime
        assert writer.calls == 1  # no hizo falta ninguna escritura

        # 3. Solo se tocan los campos pedidos: otro programa pone 4 estrellas y aquí solo
        #    se cambia el color -> las 4 estrellas siguen en el archivo
        exiftool("-XMP-xmp:Rating=4", str(jpeg))
        only_color = writer.write([req(jpeg, 0, 0, "blue", fields=("color_label",))])
        assert only_color[0].ok and only_color[0].written
        assert user_values_from_tags(read_tags(jpeg)) == {"rating": 4, "flag": -1, "color_label": "blue"}

        # 4. Quitar valores: el 0 se escribe (no se borra la etiqueta); el color sí se borra
        cleared = writer.write([req(jpeg, 0, 0, None)])
        assert cleared[0].ok and cleared[0].written
        tags = read_tags(jpeg)
        assert tags["XMP-xmp:Rating"] == 0 and tags["XMP-xmpDM:Pick"] == 0
        assert "XMP-xmpDM:Good" not in tags and "XMP-photoshop:LabelColor" not in tags

        # 5. Etiqueta personalizada de Lightroom: al quitar el color, se conserva
        exiftool("-XMP-xmp:Label=Revisar", str(png))
        kept = writer.write([req(png, 4, 1, None)])
        assert kept[0].ok and read_tags(png).get("XMP-xmp:Label") == "Revisar"

        # 6. Un texto de otro idioma del mismo color se conserva
        exiftool("-XMP-xmp:Label=Rot", "-XMP-photoshop:LabelColor=", str(png))
        recolored = writer.write([req(png, 2, 1, "red")])  # 'Rot' ya es rojo: solo cambia el 2
        assert recolored[0].ok and recolored[0].written
        png_tags = read_tags(png)
        assert png_tags.get("XMP-xmp:Label") == "Rot" and png_tags["XMP-xmp:Rating"] == 2

        # 7. Temporal abandonado por una escritura cortada: se borra y se puede escribir
        stale = png.with_name(png.name + "_exiftool_tmp")
        stale.write_bytes(b"resto de una escritura cortada")
        old = time.time() - 3600
        os.utime(stale, (old, old))
        after_crash = writer.write([req(png, 5, 1, "red")])
        assert after_crash[0].ok and after_crash[0].written and not stale.exists()

        # 8. Palabras clave, como Lightroom: rutas en la jerárquica; palabra y padres en la plana
        astra = (("Coche", "Opel Astra"), ("Familia", "Isa"), ("Familia", "Javi"))
        tagged = writer.write([XmpWriteRequest(jpeg, {"keywords": astra})])
        assert tagged[0].ok and tagged[0].written, tagged
        tags = read_tags(jpeg)
        assert tags["XMP-lr:HierarchicalSubject"] == ["Coche|Opel Astra", "Familia|Isa", "Familia|Javi"], tags
        assert tags["XMP-dc:Subject"] == ["Coche", "Opel Astra", "Familia", "Isa", "Javi"], tags
        assert "IPTC:Keywords" not in tags  # no tenía IPTC: no se crea
        assert read_tags(jpeg)["XMP-xmp:Rating"] == 0  # lo demás, intacto
        # Las mismas en otro orden: no se toca el archivo
        mtime = jpeg.stat().st_mtime_ns
        same = writer.write([XmpWriteRequest(jpeg, {"keywords": (("Familia", "Javi"), ("Familia", "Isa"), ("Coche", "Opel Astra"))})])
        assert same[0].ok and not same[0].written and jpeg.stat().st_mtime_ns == mtime
        # Con otras mayúsculas (una palabra renombrada en la aplicación): SÍ se escribe
        renamed = writer.write([XmpWriteRequest(jpeg, {"keywords": (("familia", "javi"), ("Familia", "Isa"), ("Coche", "Opel Astra"))})])
        assert renamed[0].ok and renamed[0].written, renamed
        assert "Familia|Isa" in read_tags(jpeg)["XMP-lr:HierarchicalSubject"]
        assert "familia|javi" in read_tags(jpeg)["XMP-lr:HierarchicalSubject"]
        # Un archivo con IPTC antiguo: se actualiza también; y quitar todas vacía las listas
        exiftool("-IPTC:Keywords=Vieja", str(jpeg))
        emptied = writer.write([XmpWriteRequest(jpeg, {"keywords": ()})])
        assert emptied[0].ok and emptied[0].written, emptied
        tags = read_tags(jpeg)
        assert "XMP-dc:Subject" not in tags and "XMP-lr:HierarchicalSubject" not in tags, tags
        assert "IPTC:Keywords" not in tags, tags  # no vuelve a aparecer «Vieja» al releer
        # En un sidecar nuevo de RAW
        raw2 = folder / "IMG_0002.xmp"
        made = writer.write([XmpWriteRequest(raw2, {"rating": 0, "flag": 0, "keywords": (("Playa",),)})])
        assert made[0].ok and read_tags(raw2)["XMP-dc:Subject"] in ("Playa", ["Playa"])
        print("Palabras clave: escritas como Lightroom, sin tocar lo demás; IPTC al día")

        # 9. Metadatos editados en un JPEG «de Lightroom»: IPTC antiguo en Latin, EXIF de
        #    cámara y resumen IPTC al día (como los archivos de prueba del 10/11/2026)
        def exiftool_args(path: Path, *args: str) -> None:
            """Como 'exiftool', con archivo de argumentos UTF-8 (en Windows, la línea de
            órdenes estropea las tildes: ver docs/TRAMPAS.md)."""
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".txt", delete=False
            ) as arg_file:
                arg_file.write("\n".join([*args, str(path)]) + "\n")
            try:
                subprocess.run(
                    [*runner.command, "-overwrite_original", "-charset", "utf8",
                     "-charset", "filename=utf8", "-@", arg_file.name],
                    capture_output=True, check=True,
                )  # fmt: skip
            finally:
                Path(arg_file.name).unlink(missing_ok=True)

        def digests(path: Path) -> tuple[Any, Any]:
            """(resumen guardado, resumen del IPTC actual)."""
            found = runner.read([path], tags=(f"-{_IPTC_DIGEST_TAG}", "-CurrentIPTCDigest"))
            tags = found[path].tags
            current = next(v for k, v in tags.items() if k.endswith("CurrentIPTCDigest"))
            return tags.get(_IPTC_DIGEST_TAG), current

        lightroom = folder / "lightroom.jpg"
        Image.new("RGB", (32, 24), "green").save(lightroom, quality=90)
        exiftool_args(
            lightroom, "-IFD0:ImageDescription=OLYMPUS DIGITAL CAMERA", "-IPTC:ObjectName=Viejo",
            "-IPTC:Caption-Abstract=Pie viejo con eñe", "-IPTC:City=Málaga",
            "-IPTC:Keywords=Señal",
        )  # fmt: skip
        exiftool_args(lightroom, f"-{_IPTC_DIGEST_TAG}=new")
        wanted = {
            "title": "Atardecer en Castilla y León",
            "description": "Primera línea con eñe\nSegunda línea → con flecha",
            "city": "Villanueva de la Cañada del Río Grande",  # más de 32 bytes: el IPTC la recorta
            "creator": "Rojo, Javier",  # con coma: un solo creador
        }
        outcome = writer.write([XmpWriteRequest(lightroom, wanted)])[0]
        assert outcome.ok and outcome.written, outcome
        tags = read_tags(lightroom)
        assert edited_values_from_tags(tags) == {**dict.fromkeys(_EDITABLE_READ), **wanted}
        assert tags["IPTC:ObjectName"] == wanted["title"]  # las antiguas, al día
        assert tags["IFD0:ImageDescription"] == wanted["description"]
        assert tags["XMP-photoshop:City"] == wanted["city"]  # el XMP, entero
        assert wanted["city"].startswith(tags["IPTC:City"]) and tags["IPTC:City"] != wanted["city"]
        assert "IPTC:By-line" not in tags and "IFD0:Artist" not in tags  # no se crean
        assert tags["IPTC:Keywords"] == "Señal"  # lo demás del IPTC, intacto
        saved, current = digests(lightroom)
        assert saved == current, (saved, current)  # resumen recalculado
        # Lo mismo otra vez: no se toca el archivo
        mtime = lightroom.stat().st_mtime_ns
        assert not writer.write([XmpWriteRequest(lightroom, wanted)])[0].written
        assert lightroom.stat().st_mtime_ns == mtime
        # Vaciar: se borran el XMP y las antiguas (si no, volverían «Viejo» o «OLYMPUS...»)
        emptied = writer.write([XmpWriteRequest(lightroom, dict.fromkeys(wanted))])[0]
        assert emptied.ok and emptied.written, emptied
        tags = read_tags(lightroom)
        assert set(edited_values_from_tags(tags).values()) == {None}, tags
        assert digests(lightroom)[0] == digests(lightroom)[1]
        # Las palabras clave también dejan el resumen al día (antes lo desajustaban)
        assert writer.write([XmpWriteRequest(lightroom, {"keywords": (("Playa",),)})])[0].ok
        assert read_tags(lightroom)["IPTC:Keywords"] == "Playa"
        assert digests(lightroom)[0] == digests(lightroom)[1]
        print("Metadatos editados: XMP y antiguas al día, resumen IPTC recalculado")

        # 9b. GPS (casos de las pruebas con Lightroom del 11/11/2026)
        def gps_tags(path: Path) -> dict[str, Any]:
            return {k: v for k, v in read_tags(path).items() if "GPS" in k and "Composite" not in k}

        south = {"latitude": -33.4569, "longitude": -70.6483, "altitude": -12.5, "gps_direction": 292.47}
        # Sin GPS: se crea en el EXIF, con sus referencias (como Lightroom); nada en el XMP
        no_gps = folder / "sin_gps.jpg"
        Image.new("RGB", (32, 24), "white").save(no_gps, quality=90)
        outcome = writer.write([XmpWriteRequest(no_gps, south)])[0]
        assert outcome.ok and outcome.written, outcome
        tags = gps_tags(no_gps)
        assert (tags["GPS:GPSLatitudeRef"], tags["GPS:GPSLongitudeRef"]) == ("S", "W"), tags
        assert (tags["GPS:GPSAltitude"], tags["GPS:GPSAltitudeRef"]) == (12.5, 1), tags
        assert (tags["GPS:GPSImgDirection"], tags["GPS:GPSImgDirectionRef"]) == (292.47, "T"), tags
        assert not any(k.startswith("XMP-exif:") for k in tags), tags
        assert gps_from_tags(read_tags(no_gps)) == south
        # Otra vez lo mismo: no se toca (el EXIF devuelve fracciones: se compara con margen)
        mtime = no_gps.stat().st_mtime_ns
        assert not writer.write([XmpWriteRequest(no_gps, south)])[0].written
        assert no_gps.stat().st_mtime_ns == mtime
        # Con el EXIF y el XMP distintos (foto A): se cambian los dos
        both = folder / "ambos.jpg"
        Image.new("RGB", (32, 24), "white").save(both, quality=90)
        exiftool("-GPS:GPSLatitude#=40.4168", "-GPS:GPSLatitudeRef#=N", "-GPS:GPSLongitude#=3.7038",
                 "-GPS:GPSLongitudeRef#=W", "-XMP-exif:GPSLatitude#=41.3874",
                 "-XMP-exif:GPSLongitude#=2.1686", str(both))  # fmt: skip
        place = {"latitude": 43.4623, "longitude": -3.81}
        assert writer.write([XmpWriteRequest(both, place)])[0].written
        tags = gps_tags(both)
        assert (tags["XMP-exif:GPSLatitude"], tags["XMP-exif:GPSLongitude"]) == (43.4623, -3.81), tags
        assert (tags["GPS:GPSLatitude"], tags["GPS:GPSLongitudeRef"]) == (43.4623, "W"), tags
        # Solo con XMP (foto C): la altitud y la dirección van al XMP; no se crea el EXIF
        only_xmp = folder / "solo_xmp.jpg"
        Image.new("RGB", (32, 24), "white").save(only_xmp, quality=90)
        exiftool("-XMP-exif:GPSLatitude#=31.559", "-XMP-exif:GPSLongitude#=35.4732", str(only_xmp))
        assert writer.write([XmpWriteRequest(only_xmp, {"altitude": -430.0, "gps_direction": 0.0})])[0].ok
        tags = gps_tags(only_xmp)
        assert (tags["XMP-exif:GPSAltitude"], tags["XMP-exif:GPSAltitudeRef"]) == (430, 1), tags
        assert tags["XMP-exif:GPSImgDirection"] == 0 and not any(k.startswith("GPS:") for k in tags)
        assert gps_from_tags(read_tags(only_xmp))["altitude"] == -430.0
        # Vaciar la ubicación: se borra (valor y referencia) en los dos grupos; lo demás queda
        exiftool("-GPS:GPSAltitude#=650", "-GPS:GPSAltitudeRef#=0", str(both))
        emptied = writer.write([XmpWriteRequest(both, {"latitude": None, "longitude": None})])[0]
        assert emptied.ok and emptied.written, emptied
        tags = gps_tags(both)
        assert not {"GPS:GPSLatitude", "GPS:GPSLatitudeRef", "XMP-exif:GPSLatitude",
                    "XMP-exif:GPSLongitude"} & tags.keys(), tags  # fmt: skip
        assert tags["GPS:GPSAltitude"] == 650
        # Sidecar nuevo de un RAW y GIF: solo el XMP
        sidecar = folder / "IMG_0002.xmp"
        gif = folder / "dibujo.gif"
        Image.new("RGB", (32, 24), "white").save(gif)
        outcomes = writer.write([XmpWriteRequest(sidecar, place), XmpWriteRequest(gif, place)])
        assert all(o.ok and o.written for o in outcomes), outcomes
        for path in (sidecar, gif):
            tags = gps_tags(path)
            assert tags["XMP-exif:GPSLatitude"] == 43.4623, (path, tags)
            assert not any(k.startswith("GPS:") for k in tags), (path, tags)
        print("GPS: donde ya está o, si no, en el EXIF; referencias; vaciar; sidecar y GIF, solo XMP")

    # 10. Detalles sin ExifTool: números como texto, saltos de línea y avisos menores
    assert _same_text("1.5", "1.50") and _same_text("7", "007") and not _same_text("1.5", "1,5")
    assert not _same_text(None, "1") and _same_text(None, None)
    assert _argument_line("-XMP-dc:Title=Una") == "-XMP-dc:Title=Una"
    assert _argument_line("-A=x\\y\nz") == "#[CSTR]-A=x\\\\y\\nz"
    stderr = f"{_MARK}0\nWarning: [Minor] IPTC:City exceeds length limit (truncated)\n{_MARK}1\nError: x"
    assert _split_messages(stderr) == {1: "Error: x"}
    assert _number_text(41.3874) == "41.3874" and _number_text(100.0) == "100"
    assert _number_text(0.000001) == "0.000001" and _number_text(0.0) == "0"
    assert _same_number("latitude", 42.6820889999083, 42.682089)  # el EXIF, con su margen
    assert not _same_number("latitude", 42.6821, 42.682089) and _same_number("altitude", None, None)
    assert _gps_reference("latitude", -0.5) == "S" and _gps_reference("altitude", 0.0) == "0"

    print("Autoprueba finalizada correctamente.")
