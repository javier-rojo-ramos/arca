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

LAS PREGUNTAS QUE SE LE HACEN A UN DESTINO (antes, todas eran «¿es FOLDER_FILE?»; separadas
el 28/11/2026, MUS 6.2a, para el primer formato partido, el MP3: sus etiquetas, dentro del
archivo, y la valoración, la marca, el color y las palabras clave, en el '.arca.json'):
    uses_xmp              ¿sus datos van en XMP (incrustado o sidecar)? El extractor los
                          lee de ahí (la valoración, las palabras clave...)
    has_folder_entry      ¿tiene entrada en el '.arca.json'? Entonces la entrada va con el
                          archivo al renombrarlo o moverlo, y se borra al eliminarlo
    folder_file_fields    ¿qué datos guarda esa entrada? (None, todos)
    waits_for_first_read  ¿su destino lo lee el extractor? Entonces no se escribe hasta la
                          primera lectura del archivo (lo que trae aún no está en el
                          catálogo); 'first_read_extensions', las mismas, para el SQL
Hoy las respuestas siguen siendo las de antes: solo FOLDER_FILE tiene entrada (con todo), y
los destinos con XMP esperan a la primera lectura.

Cómo añadir un formato:
    - Si ExifTool sabe escribir XMP dentro de él y otros programas lo leen de ahí:
      añadir su extensión a '_EMBEDDED_EXTENSIONS'.
    - Si es un RAW propietario: añadirla a '_SIDECAR_EXTENSIONS'.
    - Si no: no hay que hacer nada (el destino por defecto es FOLDER_FILE).
Cambiar el destino de una extensión que ya tiene datos escritos NO los mueve: se
leerían del destino nuevo (vacío). Si algún día hiciera falta, habría que migrarlos.

Prueba rápida (desde la raíz del proyecto):
    python -m core.userdata.policy

1.3.0 Las preguntas a un destino, separadas: 'has_folder_entry', 'folder_file_fields',
      'waits_for_first_read' y 'first_read_extensions'; 'uses_xmp', solo los destinos con
      XMP (antes, todo lo que no era FOLDER_FILE). Nada cambia (MUS 6.2a).
1.2.0 '.jfif' (un JPEG con otra extensión) con el XMP dentro, como los demás JPEG (antes
      iba al '.arca.json'); comprobado con ExifTool el 19/11/2026.
1.1.0 'xmp_extensions': las extensiones cuyos datos van en XMP (para filtrar en SQL; la
      usa la escritura para no escribir en un archivo que aún no se ha leído).
"""

__version__ = "1.3.0"
__all__ = [
    "UserDataDestination",
    "destination_for",
    "first_read_extensions",
    "folder_file_fields",
    "has_folder_entry",
    "sidecar_path_for_writing",
    "uses_xmp",
    "waits_for_first_read",
    "xmp_extensions",
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
        "jpg", "jpeg", "jpe", "jfif",   # JPEG
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

# Las respuestas de cada destino a las preguntas de la cabecera
_XMP_DESTINATIONS: frozenset[UserDataDestination] = frozenset(
    {UserDataDestination.XMP_EMBEDDED, UserDataDestination.XMP_SIDECAR}
)
# Qué guarda la entrada del '.arca.json' de un archivo, por su destino: None = todo; vacío =
# nada (no tiene entrada). Un destino partido dirá aquí los datos que se quedan en ella
_FOLDER_FILE_FIELDS: dict[UserDataDestination, frozenset[str] | None] = {
    UserDataDestination.XMP_EMBEDDED: frozenset(),
    UserDataDestination.XMP_SIDECAR: frozenset(),
    UserDataDestination.FOLDER_FILE: None,
}
# Los destinos que lee el extractor: no se escriben hasta la primera lectura del archivo
_FIRST_READ_DESTINATIONS: frozenset[UserDataDestination] = _XMP_DESTINATIONS


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
    """True si los datos de este archivo viven en XMP (incrustado o sidecar): el extractor
    los lee de ahí (la valoración, la marca, el color, las palabras clave)."""
    return destination_for(extension_or_path) in _XMP_DESTINATIONS


def has_folder_entry(extension_or_path: str | Path | None) -> bool:
    """True si el archivo tiene entrada en el '.arca.json' de su carpeta: entonces la
    entrada va con él al renombrarlo o moverlo, y se borra al eliminarlo."""
    return folder_file_fields(extension_or_path) != frozenset()


def folder_file_fields(extension_or_path: str | Path | None) -> frozenset[str] | None:
    """Qué datos del archivo guarda su entrada del '.arca.json': None, todos (los de
    FOLDER_FILE); vacío, ninguno (no tiene entrada). Los nombres son las claves de
    'writers.WriteItem.wanted': 'rating', 'flag', 'color_label', 'keywords' y las
    columnas editables."""
    return _FOLDER_FILE_FIELDS[destination_for(extension_or_path)]


def waits_for_first_read(extension_or_path: str | Path | None) -> bool:
    """True si el destino de este archivo lo lee el extractor (hoy, el XMP): no se escribe
    hasta la primera lectura del archivo, porque lo que trae aún no está en el catálogo y
    escribir lo del catálogo podría borrarlo."""
    return destination_for(extension_or_path) in _FIRST_READ_DESTINATIONS


def first_read_extensions() -> frozenset[str]:
    """Las extensiones (en minúsculas y sin punto, como 'file_extension') a las que
    'waits_for_first_read' dice que sí: para filtrar en una consulta SQL."""
    extensions: set[str] = set()
    if UserDataDestination.XMP_EMBEDDED in _FIRST_READ_DESTINATIONS:
        extensions |= _EMBEDDED_EXTENSIONS
    if UserDataDestination.XMP_SIDECAR in _FIRST_READ_DESTINATIONS:
        extensions |= _SIDECAR_EXTENSIONS
    return frozenset(extensions)


def xmp_extensions() -> frozenset[str]:
    """Extensiones (en minúsculas y sin punto, como 'file_extension') cuyos datos van en XMP.

    Son las mismas que 'uses_xmp' da por buenas: para filtrar en una consulta SQL.
    """
    return _EMBEDDED_EXTENSIONS | _SIDECAR_EXTENSIONS


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
    # 'xmp_extensions': exactamente las que 'uses_xmp' acepta, ya normalizadas
    assert {"jpg", "heic", "dng", "nef", "cr3"} <= xmp_extensions()
    assert not xmp_extensions() & {"mp4", "gpx", "bmp", "jxl", ""}
    assert all(uses_xmp(ext) and ext == ext.lower() and "." not in ext for ext in xmp_extensions())
    # Las preguntas a un destino (hoy, las mismas respuestas que antes de separarlas): solo
    # FOLDER_FILE tiene entrada en el '.arca.json', con todo; los de XMP esperan a la
    # primera lectura
    for value in cases:
        destination = destination_for(value)
        folder = destination is D.FOLDER_FILE
        assert has_folder_entry(value) is folder, value
        assert uses_xmp(value) is not folder, value
        assert waits_for_first_read(value) is not folder, value
        assert folder_file_fields(value) == (None if folder else frozenset()), value
    assert first_read_extensions() == xmp_extensions()
    assert all(waits_for_first_read(ext) for ext in first_read_extensions())
    # Cada destino tiene su respuesta (uno nuevo tiene que decir qué guarda el '.arca.json')
    assert set(_FOLDER_FILE_FIELDS) == set(D)

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
