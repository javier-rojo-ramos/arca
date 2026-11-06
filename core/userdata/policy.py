"""Dónde vive, FUERA de la base de datos, cada dato del usuario de un archivo.

>>> AQUÍ SE DECIDE EL DESTINO DE UN FORMATO NUEVO (una línea por extensión). <<<

Este módulo NO depende de Qt ni de la base de datos: es Python puro.

Los datos del usuario (valoración, marca y etiqueta de color; más adelante colecciones,
palabras clave, notas...) deben sobrevivir a recrear el catálogo. Por eso, además de en
la base de datos, se guardan en UN único sitio por formato:

    XMP_EMBEDDED  XMP dentro del propio archivo (JPEG, TIFF, PNG, WebP, DNG, HEIC...).
                  Es lo que hace Lightroom Classic: el dato viaja con el archivo y otros
                  programas lo leen.
    XMP_SIDECAR   Archivo '.xmp' junto al original ('IMG_0001.xmp', convención de Adobe).
                  Para los RAW propietarios (CR2, CR3, NEF, ARW...), donde Lightroom
                  tampoco escribe dentro.
    FOLDER_FILE   Un único archivo oculto por carpeta ('.arca.json', ver 'folder_file.py')
                  con una entrada por archivo. Para todo lo demás (vídeo, audio, ebooks,
                  GPX...): nunca un sidecar por archivo.

Un solo destino por formato, a propósito: si el mismo dato viviera en dos sitios,
podrían acabar distintos sin saber cuál vale.

Cómo añadir un formato:
    - Si ExifTool sabe escribir XMP dentro de él y otros programas lo leen de ahí:
      añadir su extensión a '_EMBEDDED_EXTENSIONS'.
    - Si es un RAW propietario: añadirla a '_SIDECAR_EXTENSIONS'.
    - Si no: no hay que hacer nada (el destino por defecto es FOLDER_FILE).
Cambiar el destino de una extensión que ya tiene datos escritos NO los mueve: se
leerían del destino nuevo (vacío). Si algún día hiciera falta, habría que migrarlos.

Prueba rápida (desde la raíz del proyecto):
    python -m core.userdata.policy
"""

__version__ = "1.0.1"
__all__ = [
    "UserDataDestination",
    "destination_for",
    "sidecar_path_for_writing",
    "uses_xmp",
]

# Librerías estándar
from enum import StrEnum
from pathlib import Path

# Módulos del proyecto
from core.metadata.exiftool_runner import find_sidecars


class UserDataDestination(StrEnum):
    """Sitio donde se guardan, fuera del catálogo, los datos del usuario de un archivo."""

    XMP_EMBEDDED = "xmp_embedded"
    XMP_SIDECAR = "xmp_sidecar"
    FOLDER_FILE = "folder_file"


# Formatos en los que el XMP va DENTRO del archivo. ExifTool sabe escribir XMP en todos
# ellos y Lightroom lo lee de ahí (lo comprobamos con HEIC: Lightroom Classic 15.6 escribe
# el XMP dentro, sin sidecar).
_EMBEDDED_EXTENSIONS: frozenset[str] = frozenset(
    {
        "jpg", "jpeg", "jpe",           # JPEG
        "tif", "tiff",                  # TIFF
        "png",
        "webp",
        "gif",
        "psd",                          # Photoshop
        "dng",                          # Adobe DNG (RAW abierto: Lightroom escribe dentro)
        "heic", "heif", "hif", "avif",  # HEIF (Apple, Canon .hif) y AVIF
        # JPEG XL NO: si el archivo es un códec "desnudo", ExifTool tendría que cambiar su
        # contenedor para escribir el XMP (no es solo añadir etiquetas). Va a FOLDER_FILE.
    }
)  # fmt: skip

# RAW propietarios: nunca se modifican; sus datos van al sidecar '.xmp' (como Lightroom)
_SIDECAR_EXTENSIONS: frozenset[str] = frozenset(
    {
        "cr2", "cr3", "crw",            # Canon
        "nef", "nrw",                   # Nikon
        "arw", "srf", "sr2",            # Sony
        "orf",                          # Olympus / OM System
        "rw2", "raw",                   # Panasonic / Leica
        "raf",                          # Fujifilm
        "pef",                          # Pentax
        "srw",                          # Samsung
        "x3f",                          # Sigma
        "3fr", "fff",                   # Hasselblad
        "iiq",                          # Phase One
        "rwl",                          # Leica
        "mrw",                          # Minolta
        "erf", "kdc", "dcr", "mos",     # Epson, Kodak, Leaf
    }
)  # fmt: skip

assert not _EMBEDDED_EXTENSIONS & _SIDECAR_EXTENSIONS  # cada extensión, un solo destino


def _normalize_extension(extension_or_path: str | Path | None) -> str:
    """Extensión en minúsculas y sin punto, a partir de 'jpg', '.JPG' o una ruta."""
    if extension_or_path is None:
        return ""
    if isinstance(extension_or_path, Path):
        return extension_or_path.suffix.lower().lstrip(".")
    text = str(extension_or_path)
    if "/" in text or "\\" in text or text.count(".") > 1 or (
        "." in text and not text.startswith(".")
    ):
        # Parece un nombre o una ruta ('IMG_1.CR3', 'a/b.jpg'): se toma su extensión
        return Path(text).suffix.lower().lstrip(".")
    return text.lower().lstrip(".")


def destination_for(extension_or_path: str | Path | None) -> UserDataDestination:
    """Devuelve dónde se guardan los datos del usuario de un archivo.

    Args:
        extension_or_path: La extensión ('jpg', '.CR3'), tal como está en la columna
            'file_extension', o la ruta/nombre del archivo.

    Returns:
        El destino. Lo que no está en ninguna lista va a FOLDER_FILE: es la opción
        segura, porque nunca modifica el archivo original.
    """
    extension = _normalize_extension(extension_or_path)
    if extension in _EMBEDDED_EXTENSIONS:
        return UserDataDestination.XMP_EMBEDDED
    if extension in _SIDECAR_EXTENSIONS:
        return UserDataDestination.XMP_SIDECAR
    return UserDataDestination.FOLDER_FILE


def uses_xmp(extension_or_path: str | Path | None) -> bool:
    """True si los datos de este archivo viven en XMP (incrustado o sidecar)."""
    return destination_for(extension_or_path) is not UserDataDestination.FOLDER_FILE


def sidecar_path_for_writing(path: Path) -> Path:
    """Sidecar '.xmp' donde se escriben los datos de un RAW.

    Si ya existe uno, se usa ese (el de la convención de Adobe, 'IMG_0001.xmp', tiene
    prioridad sobre 'IMG_0001.CR3.xmp'): así no se crea un segundo sidecar que
    contradiga al que ya usa otro programa. Si no existe ninguno, se usa la convención
    de Adobe, que es la que lee Lightroom.
    """
    existing = find_sidecars(path)
    if existing:
        return existing[0]
    return path.with_suffix(".xmp")


if __name__ == "__main__":
    # Autoprueba. Ejecutar desde la raíz del proyecto:  python -m core.userdata.policy
    import tempfile

    D = UserDataDestination
    cases = {
        "jpg": D.XMP_EMBEDDED, ".JPG": D.XMP_EMBEDDED, "heic": D.XMP_EMBEDDED,
        "dng": D.XMP_EMBEDDED, "cr3": D.XMP_SIDECAR, ".NEF": D.XMP_SIDECAR,
        "mp4": D.FOLDER_FILE, "mkv": D.FOLDER_FILE, "mp3": D.FOLDER_FILE,
        "gpx": D.FOLDER_FILE, "epub": D.FOLDER_FILE, "bmp": D.FOLDER_FILE,
        "jxl": D.FOLDER_FILE,
        "": D.FOLDER_FILE, None: D.FOLDER_FILE,
        "IMG_0001.CR3": D.XMP_SIDECAR, "a/b/foto.Jpeg": D.XMP_EMBEDDED,
        Path("x/peli.MKV"): D.FOLDER_FILE,
    }  # fmt: skip
    for value, expected in cases.items():
        assert destination_for(value) is expected, (value, destination_for(value))
    assert uses_xmp("tif") and uses_xmp("orf") and not uses_xmp("flac")

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "IMG_0001.CR3"
        raw.write_bytes(b"")
        # Sin sidecar: convención de Adobe
        assert sidecar_path_for_writing(raw) == Path(tmp) / "IMG_0001.xmp"
        # Con un sidecar de otro programa: se reutiliza ese
        other = Path(tmp) / "IMG_0001.CR3.xmp"
        other.write_text("x")
        assert sidecar_path_for_writing(raw) == other
        # Si aparece el de Adobe, tiene prioridad
        adobe = Path(tmp) / "IMG_0001.xmp"
        adobe.write_text("x")
        assert sidecar_path_for_writing(raw) == adobe
    print("Autoprueba finalizada correctamente.")
