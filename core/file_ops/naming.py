"""Nombres de archivos y carpetas: si valen en Windows, macOS y Linux; renombrar sin la extensión.

Este módulo NO depende de Qt ni de la base de datos: son funciones puras.

Lo usan las operaciones con archivos (docs/PENDIENTE.md, CAT 4; reglas en docs/DECISIONES.md,
19/11/2026): al renombrar un archivo o una carpeta, el nombre nuevo tiene que valer en los
TRES sistemas, no solo en el que se está usando, porque un catálogo y sus discos pueden
pasar de un equipo a otro. Las reglas son las de Windows, que es el más estricto:

    - ni vacío, ni '.' ni '..';
    - sin los caracteres  < > : " / \\ | ? *  ni caracteres de control;
    - que no acabe en un espacio ni en un punto (Windows los quita y el archivo se pierde);
    - que no sea un nombre reservado de Windows (CON, PRN, AUX, NUL, COM1 a COM9, LPT1 a
      LPT9; también con extensión: 'CON.txt');
    - como mucho 255 bytes en UTF-8 (el límite de ext4; NTFS y APFS admiten algo más).

Al renombrar un archivo se cambia el nombre, NUNCA la extensión ('rename_keeping_extension').

Uso:
    name = clean_name(texto_del_usuario)                  # sin espacios alrededor, en NFC
    problem = name_problem(name)                          # None si vale
    new_file_name = rename_keeping_extension("IMG_1.CR3", name)   # 'Boda.CR3'

1.0.0 Primera versión (CAT 4.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.file_ops.naming
"""

__version__ = "1.0.0"
__all__ = [
    "FORBIDDEN_CHARACTERS",
    "MAX_NAME_BYTES",
    "clean_name",
    "name_problem",
    "rename_keeping_extension",
    "split_extension",
]

# Librerías estándar
import unicodedata

# Caracteres que Windows no admite en un nombre ('/' tampoco en macOS ni en Linux)
FORBIDDEN_CHARACTERS = '<>:"/\\|?*'

# Longitud máxima de un nombre, en bytes de UTF-8 (ext4; el más corto de los tres)
MAX_NAME_BYTES = 255

# Nombres reservados de Windows (sin distinguir mayúsculas, con o sin extensión). Los
# superíndices ¹²³ también cuentan como dígito en COM y LPT
_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"{prefix}{digit}" for prefix in ("com", "lpt") for digit in "123456789¹²³"}
)


def clean_name(text: str) -> str:
    """Nombre escrito por el usuario, sin espacios alrededor y en NFC.

    NFC: la forma compuesta de los acentos ('á' como un solo carácter), la que escribe el
    teclado; macOS puede devolver la descompuesta, y dos nombres iguales no lo parecerían.
    Los puntos del final NO se quitan: 'name_problem' avisa (quitarlos en silencio
    cambiaría lo que se escribió).
    """
    return unicodedata.normalize("NFC", text).strip()


def name_problem(name: str) -> str | None:
    """Por qué un nombre de archivo o de carpeta no vale en los tres sistemas, o None si vale.

    El mensaje es corto y en español, para mostrarlo debajo de la caja del nombre.
    """
    if not name or not name.strip():
        return "El nombre no puede estar vacío."
    if name in (".", ".."):
        return "El nombre no puede ser «.» ni «..»."
    if any(character in FORBIDDEN_CHARACTERS for character in name):
        return f"El nombre no puede llevar estos caracteres: {' '.join(FORBIDDEN_CHARACTERS)}"
    if any(ord(character) < 32 for character in name):
        return "El nombre no puede llevar caracteres de control."
    if name.endswith((" ", ".")):
        return "El nombre no puede acabar en un espacio ni en un punto."
    if name.split(".", 1)[0].rstrip(" ").casefold() in _RESERVED_NAMES:
        return f"«{name}» es un nombre reservado de Windows."
    if len(name.encode("utf-8")) > MAX_NAME_BYTES:
        return "El nombre es demasiado largo."
    return None


def split_extension(file_name: str) -> tuple[str, str]:
    """Separa el nombre y la extensión (con su punto): 'IMG_1.CR3' -> ('IMG_1', '.CR3').

    Un nombre que empieza por punto y no tiene otro ('.arca.json' sí lo tiene) no tiene
    extensión: '.oculto' -> ('.oculto', '').
    """
    dot = file_name.rfind(".")
    if dot <= 0:
        return file_name, ""
    return file_name[:dot], file_name[dot:]


def rename_keeping_extension(file_name: str, new_stem: str) -> str:
    """El nombre nuevo de un archivo: 'new_stem' con la extensión que ya tenía."""
    return new_stem + split_extension(file_name)[1]


if __name__ == "__main__":
    # Autoprueba sin archivos.  Ejecutar desde la raíz:  python -m core.file_ops.naming
    valid = ["Boda 2024", "IMG_0001", "Viaje (copia)", "Árbol", "a.b.c", ".oculto", "COM10",
             "consola", "CON-1", "x" * 255, "ñ" * 127]  # fmt: skip
    for name in valid:
        assert name_problem(name) is None, (name, name_problem(name))
    invalid = {
        "": "vacío",
        "   ": "vacío",
        ".": "«.»",
        "..": "«..»",
        "a/b": "caracteres",
        "a:b": "caracteres",
        'di "hola"': "caracteres",
        "¿qué?": "caracteres",
        "tab\tulador": "control",
        "final.": "acabar",
        "final ": "acabar",
        "CON": "reservado",
        "con.txt": "reservado",
        "Lpt1": "reservado",
        "COM¹": "reservado",
        "nul .jpg": "reservado",
        "x" * 256: "largo",
        "ñ" * 128: "largo",  # 256 bytes en UTF-8
    }
    for name, expected in invalid.items():
        problem = name_problem(name)
        assert problem is not None and expected in problem, (name, problem)
    print(f"1. Nombres: {len(valid)} válidos y {len(invalid)} rechazados con su motivo")

    assert clean_name("  Boda  ") == "Boda"
    decomposed = unicodedata.normalize("NFD", "Árbol")
    assert decomposed != "Árbol" and clean_name(decomposed) == "Árbol"
    assert clean_name("final. ") == "final."  # el punto se queda: 'name_problem' avisa
    print("2. Limpiar lo escrito: espacios alrededor y NFC")

    assert split_extension("IMG_1.CR3") == ("IMG_1", ".CR3")
    assert split_extension("foto.tar.gz") == ("foto.tar", ".gz")
    assert split_extension("sin_extension") == ("sin_extension", "")
    assert split_extension(".oculto") == (".oculto", "")
    assert rename_keeping_extension("IMG_1.CR3", "Boda") == "Boda.CR3"
    assert rename_keeping_extension("clip.MOV", "Clip final") == "Clip final.MOV"
    assert rename_keeping_extension("LEEME", "Nota") == "Nota"
    print("3. Renombrar sin tocar la extensión")
    print("Autoprueba finalizada correctamente.")
