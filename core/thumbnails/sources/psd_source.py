"""Origen de miniaturas para los archivos de Photoshop (PSD), con Pillow.

Este módulo NO depende de Qt. Un PSD guarda, además de sus capas, la IMAGEN COMBINADA
(todas las capas ya fundidas, como se ve en Photoshop) cuando se guarda con la opción
«Maximizar compatibilidad», que viene activada de fábrica. Pillow sabe leer esa imagen
combinada, y es la que se usa: las capas no se tocan ni se combinan aquí.

Lo que Pillow NO sabe leer, y este origen detecta ANTES de abrir el archivo para dar un
mensaje claro (si no, Pillow diría que no es una imagen o que está dañada):

    - los PSB (el «documento grande» de Photoshop, versión 2 del formato);
    - los PSD de 16 o 32 bits por canal (Pillow solo lee los de 8, y los de 1 bit en
      modo mapa de bits);
    - los guardados SIN «Maximizar compatibilidad»: la imagen combinada no es real y
      saldría vacía. Se sabe por el recurso 1057 ('Version Info'), que dice si la
      imagen combinada es real. Si el archivo no lo trae (programas que no son
      Photoshop), se da por buena.

En esos casos se lanza 'ThumbnailError' con el motivo, como con un archivo que no se
puede leer, y NO 'UnsupportedSourceError': ese es para lo que se arregla instalando algo
(pillow-heif, ExifTool), y así lo explica el resumen del trabajo de miniaturas. Si algún
día se añade otro origen que sí los lea, la cadena lo probará igual detrás de este. La
tarjeta muestra el icono del paisaje, como cualquier miniatura que falla.

Un detalle de la transparencia: Pillow toma el cuarto canal de un PSD RGB como
transparencia, pero en Photoshop puede ser una SELECCIÓN GUARDADA (un canal alfa). La
imagen combinada solo lleva transparencia si el número de capas está guardado en
negativo (así lo indica la especificación de Adobe); si no, ese canal se descarta, para
que la miniatura no salga con zonas grises donde no estaba la selección.

Un PSD muy grande se decodifica entero (la decodificación reducida solo existe para los
JPEG) y, por encima de unos 179 megapíxeles, Pillow lo rechaza ('pillow_source.py').

1.0.0 Primera versión (GEN 4.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.thumbnails.sources.psd_source
"""

__version__ = "1.0.0"
__all__ = ["PsdInfo", "PsdSource", "read_psd_info"]

# Librerías estándar
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import IO, ClassVar

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.thumbnails.sources.base import (
    LoadedImage,
    ThumbnailError,
    ThumbnailRequest,
    ThumbnailSource,
)
from core.thumbnails.sources.pillow_source import load_pillow_image, translated_errors

# Cabecera del archivo (26 bytes): firma, versión, 6 bytes reservados, canales, alto,
# ancho, bits por canal y modo de color
_HEADER = struct.Struct(">4sH6xHIIHH")
_SIGNATURE = b"8BPS"
_VERSION_PSD = 1
_VERSION_PSB = 2

# Firmas posibles de un recurso de la sección «Image Resources» (casi siempre '8BIM')
_RESOURCE_SIGNATURES = frozenset({b"8BIM", b"MeSa", b"AgHg", b"PHUT", b"DCSR"})
# Recurso 'Version Info': versión (4 bytes) y, detrás, si la imagen combinada es real (1 byte)
_VERSION_INFO_ID = 1057

# Lo que lee Pillow ('PIL.PsdImagePlugin.MODES' en Pillow 12): (modo de color, bits por
# canal). Los modos de Photoshop: 0 mapa de bits, 1 escala de grises, 2 color indexado,
# 3 RGB, 4 CMYK, 7 multicanal, 8 duotono y 9 Lab. La autoprueba avisa si Pillow cambia.
_PILLOW_MODES: frozenset[tuple[int, int]] = frozenset(
    {(0, 1), (0, 8), (1, 8), (2, 8), (3, 8), (4, 8), (7, 8), (8, 8), (9, 8)}
)

_NOT_A_PSD = "No es un archivo de Photoshop válido"


@dataclass(frozen=True, slots=True)
class PsdInfo:
    """Lo que dice la cabecera de un PSD, sin leer sus píxeles.

    Attributes:
        version: 1 en un PSD; 2 en un PSB (documento grande).
        channels: Número de canales de la imagen combinada (incluidos los alfa).
        width: Ancho, en píxeles.
        height: Alto, en píxeles.
        depth: Bits por canal (1, 8, 16 o 32).
        color_mode: Modo de color de Photoshop (3 = RGB, 4 = CMYK...).
        composite_is_real: Si la imagen combinada es real (recurso 1057); None si el
            archivo no lo dice (se da por buena) o si es un PSB (no se mira).
        composite_has_alpha: Si el primer canal alfa de la imagen combinada es su
            transparencia (número de capas en negativo).
    """

    version: int
    channels: int
    width: int
    height: int
    depth: int
    color_mode: int
    composite_is_real: bool | None
    composite_has_alpha: bool


def read_psd_info(path: Path) -> PsdInfo:
    """Lee la cabecera de un PSD (y dos datos de sus secciones) sin decodificar la imagen.

    Lee unos pocos bytes: los recursos y las capas se saltan sin leerlos.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ThumbnailError: Si no es un archivo de Photoshop o no se puede leer.
    """
    with translated_errors(), path.open("rb") as file:
        header = file.read(_HEADER.size)
        if len(header) < _HEADER.size:
            raise ThumbnailError(_NOT_A_PSD)
        signature, version, channels, height, width, depth, color_mode = _HEADER.unpack(header)
        if signature != _SIGNATURE or version not in (_VERSION_PSD, _VERSION_PSB):
            raise ThumbnailError(_NOT_A_PSD)
        composite_is_real, composite_has_alpha = None, False
        if version == _VERSION_PSD:
            # En un PSB las secciones de capas tienen otro tamaño; no se leen (se rechaza)
            composite_is_real, composite_has_alpha = _read_sections(file)
    return PsdInfo(
        version, channels, width, height, depth, color_mode, composite_is_real, composite_has_alpha
    )


def _read_u32(file: IO[bytes]) -> int | None:
    """Entero de 32 bits sin signo; None si el archivo se acaba antes."""
    data = file.read(4)
    return int.from_bytes(data) if len(data) == 4 else None


def _read_sections(file: IO[bytes]) -> tuple[bool | None, bool]:
    """Recorre las secciones que siguen a la cabecera de un PSD.

    El archivo debe estar justo detrás de la cabecera. Un archivo truncado o raro no da
    error aquí: se devuelve lo que se haya podido saber y Pillow dirá después si la
    imagen se puede leer.

    Returns:
        (composite_is_real, composite_has_alpha), como en 'PsdInfo'.
    """
    # Datos del modo de color (la paleta de un PSD indexado): se saltan
    color_data = _read_u32(file)
    if color_data is None:
        return None, False
    file.seek(color_data, os.SEEK_CUR)

    # Recursos: se busca el 1057 y se saltan los demás
    composite_is_real: bool | None = None
    section = _read_u32(file)
    if section is None:
        return None, False
    end = file.tell() + section
    while file.tell() + 12 <= end:  # firma (4), id (2), nombre (2 o más), tamaño (4)
        head = file.read(7)
        if len(head) < 7 or head[:4] not in _RESOURCE_SIGNATURES:
            break
        resource_id = int.from_bytes(head[4:6])
        name_length = head[6]
        # Nombre en Pascal (el byte de la longitud y el texto), rellenado hasta un total par
        file.seek(name_length + (name_length + 1) % 2, os.SEEK_CUR)
        size = _read_u32(file)
        if size is None:
            break
        if resource_id == _VERSION_INFO_ID:
            data = file.read(5)
            if len(data) == 5:
                composite_is_real = data[4] != 0
            break
        file.seek(size + size % 2, os.SEEK_CUR)  # los datos, rellenados hasta un total par
    file.seek(end)

    # Capas: el número de capas en negativo indica que la imagen combinada lleva su
    # transparencia en el primer canal alfa
    layers_and_masks = _read_u32(file)
    if not layers_and_masks:
        return composite_is_real, False
    layer_info = _read_u32(file)
    if not layer_info:
        return composite_is_real, False
    count = file.read(2)
    has_alpha = len(count) == 2 and int.from_bytes(count, signed=True) < 0
    return composite_is_real, has_alpha


def _unsupported_reason(info: PsdInfo) -> str | None:
    """Por qué Pillow no puede leer este PSD; None si puede."""
    if info.version == _VERSION_PSB:
        return "Los PSB (documentos grandes de Photoshop) aún no se pueden leer"
    if (info.color_mode, info.depth) not in _PILLOW_MODES:
        if info.depth not in (1, 8):
            return f"Los PSD de {info.depth} bits por canal aún no se pueden leer (solo los de 8)"
        return f"Modo de color de Photoshop no admitido (modo {info.color_mode}, {info.depth} bits)"
    if info.composite_is_real is False:
        return "El PSD se guardó sin «Maximizar compatibilidad»: no lleva la imagen combinada"
    return None


class PsdSource(ThumbnailSource):
    """Lee con Pillow la imagen combinada de un PSD."""

    name: ClassVar[str] = "psd"
    media_type: ClassVar[MediaType] = MediaType.PHOTO
    extensions: ClassVar[frozenset[str] | None] = frozenset({"psd", "psb"})

    def load(self, request: ThumbnailRequest, target_side: int) -> LoadedImage:
        """Carga la imagen combinada del PSD. Ver 'ThumbnailSource.load'."""
        info = read_psd_info(request.path)
        reason = _unsupported_reason(info)
        if reason is not None:
            raise ThumbnailError(reason)
        loaded = load_pillow_image(str(request.path), target_side, source_name=self.name)
        if loaded.image.mode == "RGBA" and not info.composite_has_alpha:
            # El cuarto canal es una selección guardada, no la transparencia
            loaded.image = loaded.image.convert("RGB")
        return loaded


if __name__ == "__main__":
    # Autoprueba con PSD fabricados en una carpeta temporal (sin ExifTool ni archivos reales).
    # Ejecutar desde la raíz del proyecto:  python -m core.thumbnails.sources.psd_source
    import tempfile

    from PIL import PsdImagePlugin

    from core.thumbnails.cache import ThumbnailCache
    from core.thumbnails.generator import generate_thumbnails
    from core.thumbnails.registry import SourceRegistry
    from core.thumbnails.sources.base import UnsupportedSourceError

    def psd_bytes(
        size: tuple[int, int] = (6, 4),
        planes: tuple[int, ...] = (200, 30, 40),
        *,
        color_mode: int = 3,
        depth: int = 8,
        version: int = _VERSION_PSD,
        composite_is_real: bool | None = True,
        layer_count: int = 0,
        icc_profile: bytes | None = None,
    ) -> bytes:
        """PSD mínimo: cada canal, de un solo valor (sin comprimir), y la mitad izquierda
        del primero a 0, para comprobar que se lee la imagen y no un color cualquiera."""
        width, height = size
        header = _SIGNATURE + struct.pack(
            ">H6xHIIHH", version, len(planes), height, width, depth, color_mode
        )

        def resource(resource_id: int, data: bytes) -> bytes:
            padding = b"\0" * (len(data) % 2)  # los datos, hasta un total par
            # firma, id, nombre vacío (su longitud y un byte de relleno) y tamaño
            head = b"8BIM" + struct.pack(">H", resource_id) + b"\0\0" + struct.pack(">I", len(data))
            return head + data + padding

        resources = resource(1005, b"x" * 15)  # uno cualquiera delante, de tamaño impar
        if icc_profile is not None:
            resources += resource(1039, icc_profile)
        if composite_is_real is not None:
            # versión, la marca, dos textos Unicode vacíos y la versión del archivo
            info = struct.pack(">IBIII", 1, int(composite_is_real), 0, 0, 1)
            resources += resource(_VERSION_INFO_ID, info)
        if layer_count:
            # Pillow no lee las capas al abrir: basta con que la sección tenga su tamaño
            layers = struct.pack(">h", layer_count) + b"\0" * 40
            layer_section = struct.pack(">I", len(layers)) + layers
        else:
            layer_section = b""
        pixels = b""
        for index, value in enumerate(planes):
            row = bytes([0 if index == 0 else value] * (width // 2))
            row += bytes([value] * (width - width // 2))
            pixels += row * height
        return (
            header
            + struct.pack(">I", 0)  # sin datos del modo de color
            + struct.pack(">I", len(resources)) + resources
            + struct.pack(">I", len(layer_section)) + layer_section
            + struct.pack(">H", 0)  # imagen combinada sin comprimir
            + pixels
        )  # fmt: skip

    # Lo que admite este origen debe ser lo que lee Pillow: si Pillow cambia, avisa
    assert set(PsdImagePlugin.MODES) == _PILLOW_MODES, sorted(PsdImagePlugin.MODES)

    source = PsdSource()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        def request_for(name: str, data: bytes | None = None, media_id: int = 1) -> ThumbnailRequest:
            if data is not None:
                (base / name).write_bytes(data)
            return ThumbnailRequest(media_id, MediaType.PHOTO, base / name)

        # ---- 1. RGB de 8 bits: se lee la imagen combinada ----
        loaded = source.load(request_for("plano.psd", psd_bytes((6, 4))), 2560)
        assert loaded.image.mode == "RGB" and loaded.image.size == (6, 4), loaded.image
        assert loaded.image.getpixel((5, 0)) == (200, 30, 40)
        assert loaded.image.getpixel((0, 0)) == (0, 30, 40)  # la mitad izquierda del rojo, a 0
        assert loaded.source_name == "psd" and loaded.icc_profile is None
        info = read_psd_info(base / "plano.psd")
        assert (info.width, info.height, info.depth, info.color_mode) == (6, 4, 8, 3)
        assert info.composite_is_real is True and not info.composite_has_alpha
        print("RGB de 8 bits:", loaded.image.mode, loaded.image.size, loaded.image.getpixel((5, 0)))

        # ---- 2. El perfil de color llega a la miniatura; CMYK y grises se leen ----
        profile = b"perfil-de-prueba"
        loaded = source.load(request_for("perfil.psd", psd_bytes(icc_profile=profile)), 2560)
        assert loaded.icc_profile == profile
        loaded = source.load(request_for("cmyk.psd", psd_bytes(planes=(0, 0, 0, 0), color_mode=4)), 2560)
        assert loaded.image.mode == "CMYK"
        loaded = source.load(request_for("gris.psd", psd_bytes(planes=(128,), color_mode=1)), 2560)
        assert loaded.image.mode == "L"
        print("Perfil de color, CMYK y escala de grises: bien")

        # ---- 3. El cuarto canal: transparencia solo si las capas están en negativo ----
        four = (200, 30, 40, 0)
        loaded = source.load(request_for("seleccion.psd", psd_bytes(planes=four, layer_count=2)), 2560)
        assert loaded.image.mode == "RGB", "una selección guardada no es transparencia"
        loaded = source.load(request_for("sin_capas.psd", psd_bytes(planes=four)), 2560)
        assert loaded.image.mode == "RGB"
        loaded = source.load(request_for("transparente.psd", psd_bytes(planes=four, layer_count=-2)), 2560)
        assert loaded.image.mode == "RGBA"
        assert read_psd_info(base / "transparente.psd").composite_has_alpha
        print("Cuarto canal: selección guardada descartada; transparencia conservada")

        # ---- 4. Sin el recurso 1057 (otros programas), se da por buena ----
        loaded = source.load(request_for("otro_programa.psd", psd_bytes(composite_is_real=None)), 2560)
        assert loaded.image.size == (6, 4)
        assert read_psd_info(base / "otro_programa.psd").composite_is_real is None

        # ---- 5. Lo que Pillow no lee: el motivo, como error del archivo (no se arregla
        #         instalando nada, así que no es 'UnsupportedSourceError') ----
        unsupported = {
            "sin_compatibilidad.psd": (psd_bytes(composite_is_real=False), "Maximizar compatibilidad"),
            "16bits.psd": (psd_bytes(depth=16), "16 bits"),
            "32bits.psd": (psd_bytes(depth=32), "32 bits"),
            "grande.psb": (psd_bytes(version=_VERSION_PSB), "PSB"),
            "modo_raro.psd": (psd_bytes(color_mode=5), "modo 5"),
        }
        for name, (data, expected) in unsupported.items():
            try:
                source.load(request_for(name, data), 2560)
            except ThumbnailError as error:
                assert not isinstance(error, UnsupportedSourceError), name
                assert expected in str(error), (name, str(error))
                print(f"{name}: {error}")
            else:
                raise AssertionError(f"{name} debería avisar")

        # ---- 6. Lo que no es un PSD, o está cortado: error del archivo ----
        good = psd_bytes((40, 30))
        broken = {
            "texto.psd": b"esto no es un psd" * 10,
            "corto.psd": good[:10],
            "cortado.psd": good[: len(good) - 500],  # la imagen combinada, a medias
        }
        for name, data in broken.items():
            try:
                source.load(request_for(name, data), 2560)
            except UnsupportedSourceError as error:
                raise AssertionError(f"{name}: no es un fallo del origen ({error})") from error
            except ThumbnailError as error:
                print(f"{name}: {error}")
            else:
                raise AssertionError(f"{name} debería fallar")
        try:
            source.load(request_for("no_existe.psd"), 2560)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Un archivo que no existe debe lanzar FileNotFoundError")

        # ---- 7. De punta a punta: la escalera de miniaturas en la caché ----
        registry = SourceRegistry()
        registry.register(source)
        cache = ThumbnailCache(base / "cache")
        request = request_for("grande.psd", psd_bytes((900, 600)), media_id=7)
        result = generate_thumbnails(request, cache, registry)
        sides = sorted(max(t.width, t.height) for t in result.thumbnails)
        assert result.source_name == "psd" and sides == [160, 480, 900, 900], sides
        print("De punta a punta:", sides)

    print("Autoprueba finalizada correctamente.")
