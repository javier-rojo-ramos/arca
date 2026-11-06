import re
import subprocess
from pathlib import Path

UI_DIR = Path("ui")
RESOURCES_DIR = Path("resources")

# Línea que debe aparecer EXACTAMENTE una vez en cada .py generado desde un .ui.
# El "noqa" evita el aviso de ruff por importación no usada (se importa solo
# para que Qt registre los recursos del .qrc: rutas tipo ":/img/xxx.svg").
IMPORT_RECURSOS = "import resources.recursos_rc  # noqa: F401"

# Cualquier variante de importación del módulo de recursos que pueda haber:
#   - "import recursos_rc"            -> la que genera pyside6-uic si el .ui incluye el .qrc
#   - "import resources.recursos_rc"  -> la nuestra, de una ejecución anterior
#   - "from resources import recursos_rc"
# Se eliminan todas y luego se añade una sola, así el resultado es siempre el
# mismo y no depende de si el .ui referencia o no el .qrc.
PATRON_IMPORT_RECURSOS = re.compile(
    r"^(?:import\s+(?:resources\.)?recursos_rc|from\s+resources\s+import\s+recursos_rc)\b.*\n?",
    re.MULTILINE,
)


def asegurar_import_recursos(contenido: str) -> str:
    """Devuelve el código con 'import resources.recursos_rc' presente una sola vez."""
    # 1. Quitar cualquier importación de recursos previa (propia o de uic)
    contenido = PATRON_IMPORT_RECURSOS.sub("", contenido)

    # 2. Insertarla justo antes de la primera clase (class Ui_MainWindow...),
    #    es decir, tras el bloque de imports de PySide6
    coincidencia = re.search(r"^class ", contenido, re.MULTILINE)
    if coincidencia is None:
        # Caso raro (no hay clase): se añade al final del archivo
        return contenido.rstrip("\n") + f"\n\n{IMPORT_RECURSOS}\n"

    # Se normalizan los saltos de línea de alrededor para que ejecutar el script
    # varias veces dé siempre el mismo resultado (sin acumular líneas en blanco)
    antes = contenido[: coincidencia.start()].rstrip("\n")
    despues = contenido[coincidencia.start() :]
    resultado = f"{antes}\n\n{IMPORT_RECURSOS}\n\n\n{despues}"
    return resultado.rstrip("\n") + "\n"


def compilar_ui():
    # 1. Compilar archivos .ui a .py
    for ui_file in UI_DIR.glob("*.ui"):
        py_file = ui_file.with_suffix(".py")
        print(f"Compilando {ui_file} -> {py_file}...")

        # Ejecutamos pyside6-uic
        subprocess.run(["pyside6-uic", str(ui_file), "-o", str(py_file)], check=True)

        # Corrección automática de la importación de recursos: se garantiza que
        # exista 'import resources.recursos_rc' (una sola vez) en el .py resultante
        contenido = py_file.read_text(encoding="utf-8")
        corregido = asegurar_import_recursos(contenido)

        if corregido != contenido:
            py_file.write_text(corregido, encoding="utf-8")
            print(f"  -> Importación de recursos asegurada en {py_file.name}")


def compilar_qrc():
    # 2. Compilar recursos .qrc a .py (si usas pyside6-rcc)
    qrc_file = RESOURCES_DIR / "recursos.qrc"
    if qrc_file.exists():
        py_rc_file = RESOURCES_DIR / "recursos_rc.py"
        print(f"Compilando recursos {qrc_file} -> {py_rc_file}...")
        subprocess.run(
            ["pyside6-rcc", str(qrc_file), "-o", str(py_rc_file)], check=True
        )


if __name__ == "__main__":
    compilar_ui()
    compilar_qrc()
    print("Compilación finalizada con éxito!")
