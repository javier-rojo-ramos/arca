"""Fuente de la aplicación (Inter) y sus tamaños, en px: un único sitio para todo ello.

Como 'theme_colors.py' con los colores: cada tamaño tiene un NOMBRE según su función
(texto normal, título de una ventana...) y el resto del programa usa esos nombres, nunca
una fuente o un número sueltos ('QFont("Arial", 8)', 'setPointSize(...)').

Por qué Inter y en px (decidido por el autor el 24/11/2026; docs/DECISIONES.md, GEN 21):
    - Con la fuente del sistema, la aplicación se ve distinta en cada uno (Segoe UI en
      Windows, otra en macOS y Linux). Inter va dentro de la aplicación
      ('resources/fonts/', con su licencia OFL).
    - Qt pasa los puntos a píxeles con los ppp lógicos del sistema (96 en Windows y Linux,
      72 en macOS): «9 pt» son 12 px en Windows y 9 px en un Mac. Los px son iguales en
      los tres y siguen escalando con el 125 % o el 150 % de la pantalla.
    - La negrita es la SemiBold (la Bold de Inter queda pesada a 12 px). Se registran la
      Regular, la SemiBold y la cursiva (Italic), así que 'setBold(True)' también da la
      SemiBold. La cursiva va incluida para no depender del sistema: sin ella, cada uno la
      inclinaría a su manera (DirectWrite, Core Text, FreeType).

Cuidado: con la fuente en px, 'font.pointSize()' y 'font.pointSizeF()' devuelven -1. Nada
de 'pointSize() + 2': se pide el tamaño por su nombre (docs/TRAMPAS.md).

Uso:
    # Al arrancar, antes de crear la ventana (lo hace 'ui_theme.apply_theme()'):
    apply_app_font()

    # Un texto con otro tamaño, o en negrita:
    from ui_helpers.helpers.theme_fonts import FONT_SIZES, ui_font

    title.setFont(ui_font(FONT_SIZES.dialog_title))
    header.setFont(ui_font(FONT_SIZES.settings_header, semibold=True))

Las fuentes de Qt (QFont) no se crean al importar el módulo, porque Qt necesita antes la
aplicación: 'FONT_SIZES' guarda solo números y 'ui_font' crea la fuente al pedirla.

Si faltan los archivos de la fuente, se usa la del sistema (también en px) y se avisa en el
registro: la aplicación funciona igual; solo cambia el aspecto.

Los símbolos que la interfaz escribe dentro de un texto ('UI_SYMBOLS') tienen que estar en
Inter, o el sistema los pondría con otra fuente; la autoprueba lo comprueba. Las marcas que
se dibujan muchas veces (estrellas, marca...) se dibujan con QPainter ('card_marks.py').

1.1.0 También la cursiva ('Inter-Italic.ttf'): la de los textos de ayuda (<i>), igual en
      todos los sistemas (pedido por el autor).
1.0.0 Primera versión (GEN 21.1, 24/11/2026): Inter Regular y SemiBold; el texto normal, a
      12 px, y los tamaños de los títulos de las ventanas, la cabecera de Opciones, el
      aviso de la vista individual y la insignia al arrastrar.

Prueba rápida (sin ventana):
    python -m ui_helpers.helpers.theme_fonts
"""

__version__ = "1.1.0"
__all__ = [
    "FONTS_DIR",
    "FONT_FAMILY",
    "FONT_FILES",
    "FONT_SIZES",
    "UI_SYMBOLS",
    "FontSizes",
    "apply_app_font",
    "load_fonts",
    "register_fonts",
    "ui_font",
]

# Librerías estándar
from dataclasses import dataclass
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtGui import QFont, QFontDatabase
from qtpy.QtWidgets import QApplication

# Módulos del proyecto
from config import app_paths

# Dónde están los archivos de la fuente (se leen del disco, como el icono de la aplicación)
FONTS_DIR = app_paths.RESOURCES_DIR / "fonts"
FONT_FAMILY = "Inter"
FONT_FILES = ("Inter-Regular.ttf", "Inter-SemiBold.ttf", "Inter-Italic.ttf")

# Los símbolos que la interfaz escribe como caracteres, dentro de un texto. Al usar uno
# nuevo, se añade aquí: la autoprueba comprueba que Inter lo tiene. La flecha «▾» no está
# en Inter: se dibuja (GEN 21.3)
UI_SYMBOLS = "«»©·×–—•…›→↑↓−≤≥★☆⚠"


@dataclass(frozen=True)
class FontSizes:
    """Tamaños de la fuente, en px, por su función.

    Attributes:
        base: El texto normal de toda la aplicación.
        dialog_title: El título de las ventanas «Cambiar nombre», «Nueva carpeta» y
            «Eliminar» (antes, 3 puntos más que el normal: 12 pt, 16 px).
        settings_header: La cabecera de cada página de Opciones (antes, 1,3 veces el
            normal: 15,6 px).
        notice: El aviso de archivo no disponible de la vista individual (antes, un punto
            más que el normal: 13,3 px).
        drag_badge: El número de la insignia al arrastrar varias tarjetas (antes, el 85 %
            del normal: 10,2 px).
    """

    base: int
    dialog_title: int
    settings_header: int
    notice: int
    drag_badge: int


FONT_SIZES = FontSizes(base=12, dialog_title=16, settings_header=16, notice=13, drag_badge=10)

# Si Inter está registrada: None mientras no se ha intentado (ver 'load_fonts')
_loaded: bool | None = None


def register_fonts(fonts_dir: Path) -> bool:
    """Registra en Qt los archivos de la fuente de 'fonts_dir'.

    Returns:
        True si se registraron todos y Qt conoce la familia; False si falta alguno (se
        avisa en el registro de cuál).
    """
    complete = True
    for file_name in FONT_FILES:
        path = fonts_dir / file_name
        if not path.is_file():
            logger.warning(f"Falta el archivo de la fuente de la aplicación: {path}")
            complete = False
            continue
        if QFontDatabase.addApplicationFont(str(path)) == -1:
            logger.warning(f"Qt no ha podido cargar la fuente de la aplicación: {path}")
            complete = False
    return complete and FONT_FAMILY in QFontDatabase.families()


def load_fonts() -> bool:
    """Registra Inter una sola vez (las siguientes, devuelve lo de la primera).

    Returns:
        True si Inter está disponible; False si no (se usará la fuente del sistema).
    """
    global _loaded
    if _loaded is None:
        _loaded = register_fonts(FONTS_DIR)
        if _loaded:
            logger.info(f"Fuente de la aplicación: {FONT_FAMILY}, {FONT_SIZES.base} px.")
        else:
            logger.warning("Sin la fuente de la aplicación: se usa la del sistema.")
    return _loaded


def ui_font(size: int, *, semibold: bool = False) -> QFont:
    """La fuente de la aplicación, de 'size' px (en SemiBold si se pide).

    Sin Inter, la familia del sistema (la que tenía la aplicación al arrancar), también en
    px. Necesita la aplicación de Qt ya creada.
    """
    family = FONT_FAMILY if load_fonts() else _system_family()
    font = QFont(family)
    font.setPixelSize(size)
    if semibold:
        font.setWeight(QFont.Weight.DemiBold)
    return font


def apply_app_font() -> QFont:
    """Pone la fuente de la aplicación (el texto normal) a todos los widgets.

    Llamar una vez al arrancar, antes de crear la ventana (lo hace 'apply_theme').
    'QApplication.setFont' sin nombre de clase sustituye también las fuentes propias que
    el sistema da a algunas clases (menús, textos emergentes, barra de estado).

    Returns:
        La fuente puesta.
    """
    if QApplication.instance() is None:
        raise RuntimeError("apply_app_font() requiere un QApplication ya creado.")
    font = ui_font(FONT_SIZES.base)
    QApplication.setFont(font)
    return font


# Familia de la fuente del sistema, apuntada la primera vez que se pide (antes de cambiar
# la de la aplicación)
_system_family_name: str | None = None


def _system_family() -> str:
    global _system_family_name
    if _system_family_name is None:
        _system_family_name = QApplication.font().family()
    return _system_family_name


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'). Desde la raíz del proyecto:
    #     python -m ui_helpers.helpers.theme_fonts
    import os
    import sys
    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtGui import QFontInfo, QRawFont

    test_app = QApplication(sys.argv)

    # 1. Sin los archivos: no se registra nada (y se avisa)
    with tempfile.TemporaryDirectory() as empty_dir:
        assert register_fonts(Path(empty_dir)) is False
    print("1. Sin los archivos de la fuente: False")

    # 2. Los de la aplicación: Inter, con la Regular, la SemiBold y la cursiva
    assert load_fonts() is True
    assert load_fonts() is True  # la segunda vez, lo mismo (sin volver a registrar)
    styles = set(QFontDatabase.styles(FONT_FAMILY))
    assert {"Regular", "SemiBold", "Italic"} <= styles, styles
    print(f"2. Inter registrada: {sorted(styles)}")

    # 3. 'ui_font': en px (pointSize, -1), Inter, y la SemiBold al pedirla o con setBold
    normal = ui_font(FONT_SIZES.base)
    assert normal.pixelSize() == 12 and normal.pointSize() == -1, normal
    assert QFontInfo(normal).family() == FONT_FAMILY, QFontInfo(normal).family()
    assert QFontInfo(normal).styleName() == "Regular", QFontInfo(normal).styleName()
    semibold = ui_font(FONT_SIZES.dialog_title, semibold=True)
    assert semibold.pixelSize() == 16 and QFontInfo(semibold).styleName() == "SemiBold"
    bold = ui_font(FONT_SIZES.base)
    bold.setBold(True)  # 700: Qt elige la más cercana de las registradas
    assert QFontInfo(bold).styleName() == "SemiBold", QFontInfo(bold).styleName()
    italic = ui_font(FONT_SIZES.base)
    italic.setItalic(True)  # la de verdad, no la Regular inclinada por el sistema
    assert QFontInfo(italic).styleName() == "Italic", QFontInfo(italic).styleName()
    print("3. ui_font: 12 px (pointSize -1), Regular; SemiBold al pedirla y con setBold; "
          "la cursiva, la de Inter")

    # 4. La de la aplicación
    applied = apply_app_font()
    assert QApplication.font().family() == FONT_FAMILY and QApplication.font().pixelSize() == 12
    assert applied.pixelSize() == FONT_SIZES.base
    print("4. apply_app_font: la aplicación, en Inter 12 px")

    # 5. Los símbolos que se escriben como texto están en Inter; la flecha «▾», no (se dibuja)
    raw = QRawFont.fromFont(normal)
    missing = [symbol for symbol in UI_SYMBOLS if not raw.supportsCharacter(ord(symbol))]
    assert not missing, f"Inter no tiene: {missing}"
    assert not raw.supportsCharacter(ord("▾"))
    print(f"5. Inter tiene los {len(UI_SYMBOLS)} símbolos de la interfaz (y no la flecha ▾)")

    # 6. Tamaños: enteros positivos (setPixelSize no admite decimales)
    for name, value in vars(FONT_SIZES).items():
        assert isinstance(value, int) and value > 0, (name, value)
    print("6. Tamaños: enteros positivos")

    print("Autoprueba finalizada correctamente.")
