"""Hoja de estilos (QSS) de los componentes GENERALES del tema oscuro (paso T2).

Lo que la paleta de Qt no cubre por sí sola: barras de desplazamiento finas, separadores
de paneles, botones, campos de texto, menús, barra de menús y de estado, barras de
progreso y el hover de las filas de las barras laterales. Las piezas propias de la
aplicación (toolbar lateral, cabeceras de sección, inspector...) siguen en 'ui_theme.py',
que junta las dos hojas.

Todo sale de los colores con nombre de 'theme_colors.py' ('ThemeColors'): para otro tema
(p. ej. uno claro) basta con llamar a 'general_stylesheet' con otro juego de colores.

Lo que NO se estiliza a propósito, porque Fusion ya lo dibuja bien con la paleta y un
QSS con bordes obliga a Qt a redibujar el control entero (y se pierden sus flechas):
    - QComboBox, QSpinBox y QDateEdit (desplegables y campos con flechas).
    - QCheckBox y QRadioButton: sus indicadores los dibuja 'theme_style.ThemeStyle'
      (aquí no puede haber reglas '::indicator', o Qt dejaría de pasárselos).
    - QToolTip: va por la paleta ('ui_theme.apply_tooltip_style').

1.3.0 Icono de las opciones de los menús, separado del borde izquierdo ('MENU_ICON_LEFT';
      antes, pegado al borde).
1.2.1 Asa del deslizador con el ratón: en el acento (con el texto sobre el acento ya
      oscuro, se perdía sobre el carril).
1.2.0 Separadores de paneles: una raya de 1 px ('divider'), en azul al pasar el ratón; las
      zonas van pegadas (07/11/2026, el autor, como LightTable).

Prueba rápida (que la hoja se construye y que todas las llaves están cerradas):
    python -m ui_helpers.helpers.theme_qss
"""

__version__ = "1.3.0"
__all__ = ["CONTROL_RADIUS", "MENU_ICON_LEFT", "SCROLLBAR_WIDTH", "SPLITTER_WIDTH", "general_stylesheet"]

# Módulos del proyecto
from ui_helpers.helpers.theme_colors import ThemeColors

# Medidas comunes (px lógicos)
CONTROL_RADIUS = 3  # esquinas de botones, campos y menús
SCROLLBAR_WIDTH = 10  # grosor de las barras de desplazamiento
# Distancia del icono de una opción de menú a su borde izquierdo: el texto empieza hacia los
# 46 px, así que el icono (16 px) queda más o menos centrado en el hueco de delante
MENU_ICON_LEFT = 12
# Separador entre las barras laterales y la zona central: una raya de 1 px, como la que
# separa la franja de filtros, la cuadrícula y la barra inferior. Con 1 px, Qt amplía él
# solo la zona donde se puede coger a 5 px ("tiny mode" de QSplitterHandle): se sigue
# pudiendo arrastrar sin que se vea un hueco
SPLITTER_WIDTH = 1


def general_stylesheet(colors: ThemeColors) -> str:
    """QSS de los componentes generales con los colores de un tema."""
    c = colors
    return f"""
/* ===== Barras de desplazamiento: finas, sin flechas; el asa se aclara al pasar el ratón
   (como las de LightTable o macOS). El carril es transparente: toma el fondo de debajo */
QScrollBar:vertical {{
    background: transparent;
    width: {SCROLLBAR_WIDTH}px;
    margin: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: {SCROLLBAR_WIDTH}px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {c.bg_hover};
    min-height: 30px;
    margin: 2px;
    border-radius: {(SCROLLBAR_WIDTH - 4) // 2}px;
}}
QScrollBar::handle:horizontal {{
    background: {c.bg_hover};
    min-width: 30px;
    margin: 2px;
    border-radius: {(SCROLLBAR_WIDTH - 4) // 2}px;
}}
QScrollBar::handle:hover,
QScrollBar::handle:pressed {{
    background: {c.line};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}

/* ===== Separadores de paneles (splitter): una raya de 1 px algo más clara que los paneles
   (las zonas van pegadas, como en LightTable), sin los puntitos de Fusion; al pasar el
   ratón, en el color de acento (se ve que se puede arrastrar) */
QSplitter::handle {{
    background: {c.divider};
}}
QSplitter::handle:horizontal {{
    width: {SPLITTER_WIDTH}px;
}}
QSplitter::handle:vertical {{
    height: {SPLITTER_WIDTH}px;
}}
QSplitter::handle:hover {{
    background: {c.accent};
}}

/* ===== Botones de texto (Aceptar, Cancelar, los de los diálogos): planos, con borde fino
   y esquinas suaves. El botón por defecto (el que responde a Intro) lleva el borde en el
   color de acento */
QPushButton {{
    background: {c.bg_raised};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: {CONTROL_RADIUS}px;
    padding: 4px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {c.bg_hover};
}}
QPushButton:pressed {{
    background: {c.bg_base};
}}
QPushButton:default {{
    border-color: {c.accent};
}}
QPushButton:disabled {{
    color: {c.text_disabled};
    background: {c.bg_panel};
}}
QPushButton:focus {{
    outline: none;
}}

/* ===== Campos de texto: un poco hundidos (fondo de 'input'), borde fino; con el foco, el
   borde en el color de acento */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {c.bg_input};
    color: {c.text};
    border: 1px solid {c.line};
    border-radius: {CONTROL_RADIUS}px;
    padding: 2px 6px;
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c.accent};
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    color: {c.text_disabled};
}}
/* El campo interno de los QSpinBox, QDateEdit y desplegables editables también es un
   QLineEdit: sin borde ni fondo propios, o se vería un recuadro dentro del control */
QAbstractSpinBox QLineEdit, QComboBox QLineEdit {{
    background: transparent;
    border: none;
    padding: 0px;
}}

/* ===== Menús (contextuales y de la barra): flotan algo más claros que el panel, con borde
   fino; la opción bajo el ratón, en el color de acento */
QMenu {{
    background: {c.bg_raised};
    color: {c.text};
    border: 1px solid {c.line};
    padding: 4px 0px;
}}
QMenu::item {{
    padding: 4px 24px 4px 24px;
    background: transparent;
}}
QMenu::item:selected {{
    background: {c.accent};
    color: {c.text_on_accent};
}}
QMenu::item:disabled {{
    color: {c.text_disabled};
}}
/* El icono de una opción: con el 'padding' de QMenu::item, Qt lo deja pegado al borde
   izquierdo (el padding solo aparta el texto). Así queda en el hueco que el menú reserva
   delante del texto, más o menos centrado */
QMenu::icon {{
    position: absolute;
    left: {MENU_ICON_LEFT}px;
}}
QMenu::separator {{
    height: 1px;
    background: {c.line};
    margin: 4px 8px;
}}

/* ===== Barra de menús y barra de estado: del color del marco (como la toolbar lateral),
   para que el contenido quede "dentro" */
QMenuBar {{
    background: {c.bg_base};
    color: {c.text};
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 8px;
}}
QMenuBar::item:selected {{
    background: {c.bg_hover};
}}
QMenuBar::item:pressed {{
    background: {c.bg_raised};
}}
QStatusBar {{
    background: {c.bg_base};
    color: {c.text_dim};
}}
QStatusBar::item {{
    border: none;
}}

/* ===== Barras de progreso (trabajos en la barra de estado): planas, en el acento */
QProgressBar {{
    background: {c.bg_input};
    border: 1px solid {c.line};
    border-radius: {CONTROL_RADIUS}px;
    color: {c.text};
    text-align: center;
}}
QProgressBar::chunk {{
    background: {c.accent};
    border-radius: {CONTROL_RADIUS - 1}px;
}}

/* ===== Deslizadores horizontales (tamaño de las miniaturas): carril fino, la parte
   recorrida en el acento y un asa redonda clara (paso T3) */
QSlider::groove:horizontal {{
    height: 4px;
    background: {c.bg_hover};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c.accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c.text};
    width: 12px;
    height: 12px;
    margin: -4px 0px;
    border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{
    background: {c.accent};
}}

/* ===== Cabeceras de tablas (vista de lista, diálogos) */
QHeaderView::section {{
    background: {c.bg_raised};
    color: {c.text_dim};
    border: none;
    border-right: 1px solid {c.bg_panel};
    padding: 3px 6px;
}}

/* ===== Filas de las barras laterales bajo el ratón: un gris un poco más claro (la
   seleccionada conserva su color de acento; ver 'SidebarTreeView' en ui_theme.py) */
SidebarTreeView::item:hover:!selected {{
    background-color: {c.bg_hover};
}}
"""


if __name__ == "__main__":
    # Autoprueba: la hoja se construye, las llaves cuadran y no queda ningún color suelto
    # que no sea del tema. Ejecutar desde la raíz:  python -m ui_helpers.helpers.theme_qss
    import re

    from ui_helpers.helpers.theme_colors import DARK

    sheet = general_stylesheet(DARK)
    assert sheet.count("{") == sheet.count("}"), "llaves sin cerrar"
    theme_values = {getattr(DARK, name) for name in DARK.__dataclass_fields__}
    loose = set(re.findall(r"#[0-9a-fA-F]{6}\b", sheet)) - theme_values
    assert not loose, f"colores que no son del tema: {loose}"
    # Cada regla tiene selector y al menos una propiedad
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", sheet)
    assert rules and all(body.strip() for _selector, body in rules)
    print(f"Hoja general: {len(rules)} reglas, solo colores del tema.")
    print("Autoprueba finalizada correctamente.")
