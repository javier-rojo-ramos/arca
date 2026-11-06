"""Detección del tipo de medio de un archivo (foto, vídeo, audio, libro, track...).

Este módulo NO depende de Qt: es Python puro, así que se puede probar desde la
consola y ejecutar sin problema en un hilo secundario (no toca la interfaz).

Es la FASE 2 del embudo de importación (después del filtro previo al escaneo):

Devuelve siempre un valor de 'MediaType' (core/catalog/media_types.py), que es el
único sitio donde se definen los tipos de medio. Si el archivo no se reconoce,
el tipo devuelto es 'MediaType.OTHER'. Para saber si un archivo se debe procesar
y añadir al catálogo, se comprueba si su tipo está en 'CACHEABLE_MEDIA_TYPES'
(ver 'DetectionResult.is_supported').

La detección se hace en dos capas, de la más barata a la más cara:

    CAPA 1 (sin leer el archivo): extensión y MIME estimado por nombre.
        a) Tabla propia de extensiones (RAW, HEIC, MKV, FLAC, GPX...). Tiene prioridad.
        b) 'mimetypes' de la librería estándar. Si el MIME es conocido pero no es
           de un tipo de medio (p. ej. "text/plain"), se descarta sin abrir el archivo.
    CAPA 2 (lee la cabecera): solo para archivos sin extensión o con una extensión
        que nadie conoce. Se usa 'puremagic' (Python puro, sin DLLs externas, ideal
        para empaquetar con PyInstaller en Windows y macOS).

Dependencia externa:
    pip install puremagic

1.2.0 '.mts' y '.m2ts' (vídeo AVCHD de videocámara) como vídeo, con MIME 'video/mp2t'.
1.1.0 Tracks GPS: '.gpx' -> MediaType.TRACK. MIME propio por extensión
      (DEFAULT_EXTENSION_MIME) para los formatos que 'mimetypes' no conoce o que cada
      sistema operativo conoce de una forma distinta.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.media_detector
"""

__version__ = "1.2.0"
__all__ = ["DetectionResult", "MediaTypeDetector"]

# Librerías estándar
import mimetypes
from dataclasses import dataclass
from pathlib import Path

# Librerías de terceros
import puremagic
from loguru import logger

# Módulos del proyecto
from core.catalog.media_types import CACHEABLE_MEDIA_TYPES, MediaType

# MIME genérico para cuando no se conoce el real (la columna 'mime_type' de la
# base de datos es NOT NULL, así que siempre hace falta algún valor)
FALLBACK_MIME = "application/octet-stream"

# Prefijo MIME estándar -> tipo de medio
MIME_PREFIX_TO_TYPE: dict[str, MediaType] = {
    "image/": MediaType.PHOTO,
    "video/": MediaType.VIDEO,
    "audio/": MediaType.AUDIO,
}

# MIME exacto -> tipo de medio, para los que no se pueden deducir por prefijo
# (los libros electrónicos y los tracks son "application/...", sin un prefijo propio)
MIME_EXACT_TO_TYPE: dict[str, MediaType] = {
    "application/epub+zip": MediaType.EBOOK,
    "application/x-mobipocket-ebook": MediaType.EBOOK,
    "application/gpx+xml": MediaType.TRACK,
}

# Extensiones que se resuelven directamente, sin consultar 'mimetypes'. Sirve para
# formatos que el sistema operativo suele desconocer (RAW, GPX) o confundir.
# Se puede ampliar en tiempo de ejecución con 'MediaTypeDetector.register_extension'.
DEFAULT_EXTENSION_TO_TYPE: dict[str, MediaType] = {
    # --- Fotos RAW / profesionales ---
    ".dng": MediaType.PHOTO,  # Digital Negative (Adobe)
    ".nef": MediaType.PHOTO,  # Nikon
    ".cr2": MediaType.PHOTO,  # Canon RAW 2
    ".cr3": MediaType.PHOTO,  # Canon RAW 3
    ".arw": MediaType.PHOTO,  # Sony
    ".orf": MediaType.PHOTO,  # Olympus
    ".rw2": MediaType.PHOTO,  # Panasonic
    ".pef": MediaType.PHOTO,  # Pentax
    ".raf": MediaType.PHOTO,  # Fujifilm
    ".heic": MediaType.PHOTO,  # High Efficiency Image Format (Apple)
    ".webp": MediaType.PHOTO,  # Google WebP
    # --- Vídeo ---
    ".mkv": MediaType.VIDEO,
    # AVCHD de videocámara: según el sistema, 'mimetypes' no los conoce o los toma por
    # otra cosa (en Linux, 'model/vnd.mts'), y se quedaban sin catalogar
    ".mts": MediaType.VIDEO,
    ".m2ts": MediaType.VIDEO,
    # --- Audio ---
    ".m4a": MediaType.AUDIO,
    ".flac": MediaType.AUDIO,
    ".ogg": MediaType.AUDIO,
    ".opus": MediaType.AUDIO,
    # --- Libros electrónicos ---
    ".epub": MediaType.EBOOK,
    ".mobi": MediaType.EBOOK,
    ".azw3": MediaType.EBOOK,
    ".fb2": MediaType.EBOOK,
    # --- Tracks GPS ---
    # (más adelante, si hace falta: .tcx, .fit, .kml)
    ".gpx": MediaType.TRACK,  # GPS Exchange Format (XML)
}

# MIME que se guarda para estas extensiones, en lugar del que diga 'mimetypes'. Para
# formatos que 'mimetypes' no conoce (se guardaría 'application/octet-stream') o que
# cada sistema operativo conoce de una forma distinta (en Windows, 'mimetypes' también
# lee el registro del sistema). Así el catálogo guarda lo mismo en todos los equipos.
DEFAULT_EXTENSION_MIME: dict[str, str] = {
    ".gpx": "application/gpx+xml",
    ".mts": "video/mp2t",  # AVCHD: flujo de transporte MPEG-2
    ".m2ts": "video/mp2t",
}


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Resultado de analizar un archivo.

    Attributes:
        media_type: Tipo de medio detectado ('MediaType.OTHER' si no se reconoce).
        mime_type: MIME estimado o real. Es el valor que irá a la columna
            'mime_type' de 'media_items' (nunca está vacío).
    """

    media_type: MediaType
    mime_type: str

    @property
    def is_supported(self) -> bool:
        """True si el tipo de medio es uno de los que gestiona el catálogo."""
        return self.media_type in CACHEABLE_MEDIA_TYPES


# Resultado para archivos que no existen o no se reconocen
_UNKNOWN = DetectionResult(MediaType.OTHER, FALLBACK_MIME)


class MediaTypeDetector:
    """Determina el tipo de medio de un archivo de forma multiplataforma.

    No guarda estado entre archivos (salvo la tabla de extensiones), así que una
    sola instancia se puede reutilizar para recorrer miles de archivos.
    """

    def __init__(self) -> None:
        # Copia propia: registrar extensiones nuevas no modifica la tabla por defecto
        self._extension_map: dict[str, MediaType] = dict(DEFAULT_EXTENSION_TO_TYPE)

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def register_extension(self, extension: str, media_type: MediaType) -> None:
        """Añade (o cambia) el tipo de medio asociado a una extensión.

        Args:
            extension: Con o sin punto, en mayúsculas o minúsculas ("cr2", ".CR2").
            media_type: Un 'MediaType' (o su valor en texto, p. ej. "photo").

        Raises:
            ValueError: Si 'media_type' no es un tipo de medio válido.
        """
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        self._extension_map[ext] = MediaType(media_type)

    def detect(self, file_path: str | Path) -> MediaType:
        """Devuelve solo el tipo de medio del archivo ('OTHER' si no se reconoce)."""
        return self.detect_with_mime(file_path).media_type

    def detect_with_mime(self, file_path: str | Path) -> DetectionResult:
        """Analiza el archivo y devuelve su tipo de medio junto con su MIME.

        Es preferible a 'detect' cuando se va a guardar el archivo en la base de
        datos, porque así el MIME se calcula una sola vez.

        Nunca lanza excepciones por problemas de disco o permisos: en ese caso
        devuelve 'MediaType.OTHER' y lo deja anotado en el log.
        """
        path = Path(file_path)

        try:
            if not path.is_file():
                return _UNKNOWN
        except OSError:
            # Puede ocurrir en unidades de red desconectadas o con permisos raros
            logger.opt(exception=True).warning(f"No se pudo acceder a: {path}")
            return _UNKNOWN

        extension = path.suffix.lower()
        # Se consulta por nombre (no por ruta completa) y sin tocar el disco
        guessed_mime, _ = mimetypes.guess_type(path.name)

        # --- CAPA 1a: tabla propia de extensiones (tiene prioridad) ---
        if extension in self._extension_map:
            # MIME: el propio de la extensión si lo hay; si no, el de 'mimetypes'
            mime = DEFAULT_EXTENSION_MIME.get(extension) or guessed_mime or FALLBACK_MIME
            return DetectionResult(self._extension_map[extension], mime)

        # --- CAPA 1b: MIME estimado por 'mimetypes' ---
        # Si el sistema conoce la extensión, se confía en él aunque no sea un medio
        # (p. ej. .txt, .docx): así no se abren miles de archivos de otros tipos
        if guessed_mime is not None:
            return DetectionResult(self._type_from_mime(guessed_mime), guessed_mime)

        # --- CAPA 2: sin extensión, o extensión que nadie conoce ---
        return self._inspect_content(path)

    # -------------------------------------------------------------------------
    # Pasos internos
    # -------------------------------------------------------------------------

    @staticmethod
    def _type_from_mime(mime: str) -> MediaType:
        """Convierte un MIME en un 'MediaType' ('OTHER' si no corresponde a ninguno)."""
        if mime in MIME_EXACT_TO_TYPE:
            return MIME_EXACT_TO_TYPE[mime]

        for prefix, media_type in MIME_PREFIX_TO_TYPE.items():
            if mime.startswith(prefix):
                return media_type

        return MediaType.OTHER

    def _inspect_content(self, path: Path) -> DetectionResult:
        """Lee la cabecera del archivo y deduce su tipo por la firma binaria.

        'puremagic' solo lee los primeros bytes necesarios, no el archivo entero.
        Cualquier fallo de lectura se trata como "tipo desconocido".
        """
        try:
            # Un archivo vacío no tiene cabecera que analizar. Se descarta antes de
            # llamar a 'puremagic', que en ese caso lanza 'PureValueError'
            if path.stat().st_size == 0:
                return _UNKNOWN

            real_mime = puremagic.from_file(str(path), mime=True) or ""
        except puremagic.PureError:
            # Ninguna firma conocida coincide con la cabecera del archivo
            return _UNKNOWN
        except ValueError:
            # 'PureValueError' (p. ej. "Input was empty") no hereda de 'PureError'
            # sino de 'ValueError': se trata igual, como tipo desconocido
            return _UNKNOWN
        except OSError:
            # Incluye PermissionError y FileNotFoundError (el archivo pudo borrarse
            # entre la comprobación de existencia y la lectura)
            logger.opt(exception=True).warning(
                f"No se pudo leer la cabecera de: {path}"
            )
            return _UNKNOWN

        # Los RAW basados en TIFF (CR2, NEF...) devuelven "image/tiff": ya entran
        # por el prefijo "image/", no hace falta un caso especial
        return DetectionResult(
            self._type_from_mime(real_mime), real_mime or FALLBACK_MIME
        )


if __name__ == "__main__":
    # Autoprueba: crea archivos falsos en una carpeta temporal y comprueba que cada
    # uno se clasifica como se espera.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.media_detector
    import tempfile

    # Cabecera mínima de un PNG, para probar la detección por contenido (CAPA 2)
    PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 20

    # GPX mínimo (el contenido da igual: se detecta por la extensión)
    GPX_CONTENT = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<gpx version="1.1" creator="prueba"><trk><name>Ruta</name></trk></gpx>'
    )

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        detector = MediaTypeDetector()

        # nombre -> (contenido, tipo esperado)
        casos: dict[str, tuple[bytes, MediaType]] = {
            "foto.jpg": (b"", MediaType.PHOTO),  # CAPA 1b: mimetypes
            "raw.CR2": (b"", MediaType.PHOTO),  # CAPA 1a: tabla propia (mayúsculas)
            "cancion.mp3": (b"", MediaType.AUDIO),
            "pelicula.mkv": (b"", MediaType.VIDEO),
            "00001.MTS": (b"", MediaType.VIDEO),  # videocámara AVCHD (en mayúsculas)
            "libro.epub": (b"", MediaType.EBOOK),
            "ruta.gpx": (GPX_CONTENT, MediaType.TRACK),  # CAPA 1a: tabla propia
            "RUTA2.GPX": (GPX_CONTENT, MediaType.TRACK),  # extensión en mayúsculas
            "notas.txt": (b"hola", MediaType.OTHER),  # MIME conocido, no es un medio
            "sin_extension": (PNG_HEADER, MediaType.PHOTO),  # CAPA 2: contenido
            "renombrado.zzz": (PNG_HEADER, MediaType.PHOTO),  # CAPA 2: ext. desconocida
            "basura.zzz": (b"\x00\x01\x02\x03", MediaType.OTHER),  # sin firma conocida
            "vacio.zzz": (b"", MediaType.OTHER),  # vacío: puremagic fallaría
        }

        for nombre, (contenido, esperado) in casos.items():
            (base / nombre).write_bytes(contenido)
            obtenido = detector.detect(base / nombre)
            estado = "OK " if obtenido == esperado else "MAL"
            print(f"[{estado}] {nombre:<16} -> {obtenido.value}")
            assert obtenido == esperado, (
                f"{nombre}: esperado {esperado}, obtenido {obtenido}"
            )

        # Archivo inexistente y carpeta: nunca deben lanzar excepción
        assert detector.detect(base / "no_existe.jpg") == MediaType.OTHER
        assert detector.detect(base) == MediaType.OTHER

        # Registro de una extensión nueva en tiempo de ejecución
        (base / "datos.xyz").write_bytes(b"")
        assert detector.detect(base / "datos.xyz") == MediaType.OTHER
        detector.register_extension("xyz", MediaType.PHOTO)
        assert detector.detect(base / "datos.xyz") == MediaType.PHOTO

        # El resultado con MIME indica si el archivo se debe procesar
        resultado = detector.detect_with_mime(base / "foto.jpg")
        print(f"foto.jpg -> {resultado}")
        assert resultado.is_supported
        assert not detector.detect_with_mime(base / "notas.txt").is_supported

        # Los tracks se catalogan, con su MIME propio (igual en todos los sistemas)
        track = detector.detect_with_mime(base / "ruta.gpx")
        print(f"ruta.gpx -> {track}")
        assert track.is_supported and track.mime_type == "application/gpx+xml"
        assert MediaType.TRACK in CACHEABLE_MEDIA_TYPES

        print("Todas las pruebas pasaron.")
