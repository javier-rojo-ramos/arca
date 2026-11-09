"""Estilo visual de la aplicación: tema oscuro sobre el estilo Fusion.

Centraliza aquí el aspecto de la aplicación para que NO quede repartido por los
controladores. Los colores salen TODOS de 'theme_colors.py' (un nombre por función:
fondo de panel, texto secundario, acento...) y se aplican de dos formas:
    - Paleta de Qt (build_palette): cubre casi todo (texto, fondos, selección, menús,
      diálogos, tooltips, campos) sin escribir QSS. Los iconos y los delegados ya leen
      sus colores de la paleta, así que se adaptan solos.
    - Hoja de estilos QSS global (STYLESHEET), solo para lo que la paleta no cubre, con
      selectores acotados por nombre de objeto (#frame_toolbar, #list_view_grid...) o
      por tipo de widget. Usa 'palette(...)' siempre que puede.

Los botones de opción y las casillas los dibuja un estilo propio sobre Fusion
('theme_style.ThemeStyle'): con la paleta oscura, Fusion los deja casi invisibles.

Todo se aplica de una vez con apply_theme(), que se llama una sola vez al
arrancar. Al ser una hoja de estilos de aplicación, también afecta a las
ventanas que se creen después (ajustes, diálogos...) sin que sus controladores
tengan que hacer nada.

1.12.0 Textos de las ventanas: aviso en el color de aviso ('#lbl_dialog_warning') y texto
       de estado en rojo con la propiedad 'error' ('#lbl_dialog_status'); los usa el
       editor de colecciones inteligentes (antes, con colores sueltos).
1.11.0 Textos de las ventanas: ayuda en gris ('#lbl_dialog_hint') y aviso en rojo
       ('#lbl_dialog_error'); los usa «Gestionar ajustes personalizados».
1.10.0 Desplegable de los ajustes personalizados de la barra de filtros
       ('#btn_filter_presets'): texto como las pestañas, sin la flecha de Fusion.
1.9.2 Raya entre dos paneles de la barra de filtros ('#line_filter_panel').
1.9.1 Raya fina entre las columnas de «Metadatos» ('#line_metadata_separator').
1.9.0 Columnas de «Metadatos» de la barra de filtros ('#widget_metadata_column'): cabecera
      con el campo en texto y el engranaje; lista sin marco sobre el fondo de la franja.
1.8.1 La franja de la barra de filtros, con el fondo de la barra inferior y de la
      cuadrícula ('GRID_BG'); lo pidió el autor el 08/11/2026.
1.8.0 Barra de filtros ('#widget_filter_bar'): pestañas de texto en gris, la encendida en
      el acento; candado en caja como los botones de vista; raya sobre los paneles (A.3).
1.7.0 Botones de vista de la barra inferior ('#widget_view_buttons', como los de la toolbar)
      y su raya de separación ('#line_bottom_views'); paso A.1.
1.6.0 Zonas pegadas, separadas por rayas de 1 px ('divider'): toolbar, franja de filtros,
      cuadrícula, barra inferior y barra de estado; botones de la toolbar en cajas
      redondeadas (borde suave, más claro con el ratón; el activo, relleno gris). Decidido
      por el autor el 07/11/2026, con LightTable como referencia.
1.5.1 Botón «Cancelar» compacto de los trabajos de la barra de estado ('#btn_job_cancel').
1.5.0 Estilo propio sobre Fusion ('ThemeStyle'): botones de opción y casillas visibles
      en el tema oscuro (borde gris claro, relleno del acento al marcarlos).
1.4.0 Botones de «Últimas palabras clave» del inspector y su cabecera plegable (K4c).
1.3.0 Paso T3: colores de la cuadrícula y de las tarjetas ('CARD_COLORS') y deslizador.
1.2.0 Paso T2: componentes generales (barras de desplazamiento, separadores, botones,
      campos, menús...) en 'theme_qss.py'; marcos de la zona central y barra de estado.
1.1.0 Tema oscuro (paso T1): paleta completa de Fusion a partir de 'theme_colors.DARK',
      barra de título oscura en Windows y tooltips oscuros. El aspecto de cada pieza
      (QSS) se repasa en T2 y las tarjetas en T3.
"""

__version__ = "1.12.0"
__all__ = [
    "CARD_COLORS",
    "COLORS",
    "ACCENT_COLOR",
    "GRID_BG",
    "GRID_LINE",
    "SIDEBAR_ICON_COLOR",
    "SIDEBAR_ICON_OPEN_COLOR",
    "TOOLBAR_ICON_ACCENT_COLOR",
    "TOOLBAR_MARGIN",
    "STYLESHEET",
    "apply_theme",
    "apply_tooltip_style",
    "build_palette",
]

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QGuiApplication, QPalette
from qtpy.QtWidgets import QApplication, QToolTip

# Módulos del proyecto
from ui_helpers.helpers.theme_colors import DARK, DARK_CARDS, CardColors, ThemeColors
from ui_helpers.helpers.theme_qss import general_stylesheet
from ui_helpers.helpers.theme_style import ThemeStyle

# Tema en uso (de momento solo hay uno, el oscuro: ver 'theme_colors.py')
COLORS: ThemeColors = DARK
# Colores de la cuadrícula y de las tarjetas ('ThumbnailsDelegate')
CARD_COLORS: CardColors = DARK_CARDS

# Color de acento de la aplicación (hover de iconos, elementos activos...). Es el del
# tema; se mantiene el nombre porque lo importan varios módulos.
ACCENT_COLOR = COLORS.accent

# Color de los iconos de las barras laterales (carpetas, colecciones...). None = el color
# del texto de la paleta (se adapta solo a un tema claro u oscuro). Para que vayan en el
# color de acento, basta con poner aquí ACCENT_COLOR (o cualquier "#rrggbb").
SIDEBAR_ICON_COLOR: str | None = None
# Color de la carpeta DESPLEGADA (carpeta abierta). None = el color de selección de la
# paleta (el acento del sistema). Para que sea igual que las demás: SIDEBAR_ICON_COLOR
SIDEBAR_ICON_OPEN_COLOR: str | None = None
# Acento de los iconos de la toolbar lateral (solo el modo activo; ver
# ui_helpers/helpers/mode_toolbar.py). None = el color de selección del sistema
TOOLBAR_ICON_ACCENT_COLOR: str | None = None
# Aire (px) alrededor de los botones de la toolbar lateral: el mismo en los cuatro lados
# (izquierda y derecha, por encima del primer botón y por debajo del de ajustes)
TOOLBAR_MARGIN = 4
# Esquinas de los botones de la toolbar lateral (cajas redondeadas)
TOOLBAR_BUTTON_RADIUS = 6
# Esquinas de los botones de vista de la barra inferior (más pequeños: menos redondeados)
VIEW_BUTTON_RADIUS = 4

# Fondo de la cuadrícula de miniaturas, algo más hundido que las tarjetas (paso T3); también
# es el fondo de la barra inferior ('frame_main_bottom'), para que formen un solo bloque.
# Se mantiene el nombre porque lo importan varios módulos: el valor está en 'theme_colors'
GRID_BG = CARD_COLORS.grid_bg

# Línea que delimita cada tarjeta en reposo (el delegado la usa como borde)
GRID_LINE = CARD_COLORS.line

# Colores del tooltip (los del tema; Fusion usaría un amarillo pálido)
TOOLTIP_BG = COLORS.bg_tooltip  # Fondo
TOOLTIP_FG = COLORS.text  # Texto

# Hoja de estilos global: primero los componentes generales ('theme_qss.py') y después las
# piezas propias de la aplicación. Cada regla se acota con un selector para que solo
# afecte a lo que debe.
STYLESHEET = general_stylesheet(COLORS) + f"""
/* Zona central: la franja de arriba (barra de filtros y sus paneles) con el fondo de la
   barra inferior y de la cuadrícula, separada de esta por una raya de 1 px; sin el marco
   claro de 'StyledPanel' */
QFrame#frame_main_top {{
    background-color: {GRID_BG};
    border: none;
    border-bottom: 1px solid {COLORS.divider};
}}

/* Barra de filtros (ui_helpers/widgets/filter_bar.py), dentro de la franja de arriba:
   «Filtro activo:» y las pestañas son texto, sin caja. Las pestañas, en gris; con el
   ratón, más claras; las encendidas (o «Ninguno»), en el acento; las que aún no tienen
   panel, apagadas. El candado, en una caja como los botones de vista (el icono del
   cerrado, en el acento: lo pone 'tinted_icon'). Los paneles, debajo de una raya */
QLabel#lbl_filter_title {{
    color: {COLORS.text_dim};
}}
QToolButton#btn_filter_tab {{
    border: none;
    background: transparent;
    color: {COLORS.text_dim};
    padding: 2px 2px;
}}
QToolButton#btn_filter_tab:hover {{
    color: {COLORS.text};
}}
QToolButton#btn_filter_tab:checked {{
    color: {COLORS.accent};
}}
QToolButton#btn_filter_tab:disabled {{
    color: {COLORS.text_disabled};
}}
QToolButton#btn_filter_lock {{
    border: 1px solid {COLORS.divider};
    border-radius: {VIEW_BUTTON_RADIUS}px;
    background: transparent;
}}
QToolButton#btn_filter_lock:hover {{
    border-color: {COLORS.line};
    background: {COLORS.bg_raised};
}}
/* Desplegable de los ajustes personalizados (filter_preset_button.py): texto como las
   pestañas («Ubicación ▾»; la flecha la lleva el texto, sin la de Fusion) */
QToolButton#btn_filter_presets {{
    border: none;
    background: transparent;
    color: {COLORS.text_dim};
    padding: 2px 2px;
}}
QToolButton#btn_filter_presets:hover {{
    color: {COLORS.text};
}}
QToolButton#btn_filter_presets:disabled {{
    color: {COLORS.text_disabled};
}}
QToolButton#btn_filter_presets::menu-indicator {{
    image: none;
    width: 0px;
}}

/* Textos de las ventanas (p. ej. «Gestionar ajustes personalizados»): la ayuda, en gris;
   el aviso de algo que no vale, en rojo; un aviso de arriba (p. ej. «las reglas guardadas
   no se podían leer»), en el color de aviso. El texto de estado de una ventana (p. ej. el
   recuento de las colecciones inteligentes) se pone en rojo con la propiedad 'error' */
QLabel#lbl_dialog_hint {{
    color: {COLORS.text_dim};
}}
QLabel#lbl_dialog_error {{
    color: {COLORS.error};
}}
QLabel#lbl_dialog_warning {{
    color: {COLORS.warning};
}}
QLabel#lbl_dialog_status[error="true"] {{
    color: {COLORS.error};
}}
QWidget#widget_filter_panels {{
    border-top: 1px solid {COLORS.divider};
}}
/* Raya entre dos paneles encendidos (p. ej. entre «Texto» y «Atributos») */
QFrame#line_filter_panel {{
    background-color: {COLORS.divider};
    border: none;
}}

/* Columnas de «Metadatos» (ui_helpers/widgets/metadata_column.py): la cabecera, con el
   fondo de los paneles y una raya debajo; el campo, en texto (sin caja; con el ratón, en
   el acento) y sin la flecha de Fusion (la lleva el texto: «Ciudad ▾»); la lista, sin
   marco, sobre el fondo de la franja */
QWidget#widget_metadata_header {{
    background-color: {COLORS.bg_panel};
    border-bottom: 1px solid {COLORS.divider};
}}
QToolButton#btn_metadata_field {{
    border: none;
    background: transparent;
    color: {COLORS.text};
    padding: 2px 2px;
}}
QToolButton#btn_metadata_field:hover {{
    color: {COLORS.accent};
}}
QToolButton#btn_metadata_field::menu-indicator {{
    image: none;
    width: 0px;
}}
QToolButton#btn_metadata_settings {{
    border: none;
    background: transparent;
}}
QToolButton#btn_metadata_settings::menu-indicator {{
    image: none;
    width: 0px;
}}
QTreeWidget#tree_metadata_values {{
    background: transparent;
    border: none;
}}
/* Lo elegido, siempre con el color de selección (como en las barras laterales: la lista
   nunca tiene el foco y, sin esto, la selección inactiva no se leería); bajo el ratón,
   un gris un poco más claro */
QTreeWidget#tree_metadata_values::item:selected,
QTreeWidget#tree_metadata_values::item:selected:!active {{
    background-color: palette(highlight);
}}
QTreeWidget#tree_metadata_values::item:hover:!selected {{
    background-color: {COLORS.bg_hover};
}}
/* Raya entre dos columnas: la de 1 px entre zonas */
QFrame#line_metadata_separator {{
    background-color: {COLORS.divider};
    border: none;
}}

/* Línea encima de la barra de estado: la raya de 1 px entre zonas, no el relieve de Fusion */
QFrame#frame_separator_bottom {{
    border: none;
    background-color: {COLORS.divider};
    max-height: 1px;
}}

/* Toolbar lateral: una franja propia, más oscura que las barras laterales y separada de
   ellas por la raya de 1 px. 'alternate-base' es 'bg_base' (ver 'build_palette') */
QFrame#frame_toolbar {{
    background-color: palette(alternate-base);
    border: none;
    border-right: 1px solid {COLORS.divider};
}}

/* Botones de la toolbar: cajas redondeadas con un borde casi invisible; al pasar el
   ratón, el borde y el fondo se aclaran un poco (y el icono pasa al acento: lo pone
   'mode_toolbar.py'). El modo activo, con un relleno gris discreto además del icono en el
   acento */
QFrame#frame_toolbar QToolButton {{
    border: 1px solid {COLORS.divider};
    border-radius: {TOOLBAR_BUTTON_RADIUS}px;
    background: transparent;
}}
QFrame#frame_toolbar QToolButton:hover {{
    border-color: {COLORS.line};
    background: {COLORS.bg_panel};
}}
QFrame#frame_toolbar QToolButton:checked,
QFrame#frame_toolbar QToolButton:pressed {{
    border-color: {COLORS.line};
    background: {COLORS.bg_raised};
}}

/* Botones de vista de la barra inferior (cuadrícula, individual...): las mismas cajas que
   los de la toolbar; el icono de la vista elegida, en el acento (lo pone 'tinted_icon') */
QWidget#widget_view_buttons QToolButton {{
    border: 1px solid {COLORS.divider};
    border-radius: {VIEW_BUTTON_RADIUS}px;
    background: transparent;
}}
QWidget#widget_view_buttons QToolButton:hover {{
    border-color: {COLORS.line};
    background: {COLORS.bg_panel};
}}
QWidget#widget_view_buttons QToolButton:checked,
QWidget#widget_view_buttons QToolButton:pressed {{
    border-color: {COLORS.line};
    background: {COLORS.bg_raised};
}}

/* Raya vertical entre los botones de vista y el orden: la de 1 px entre zonas, no el
   relieve de Fusion */
QFrame#line_bottom_views {{
    border: none;
    background-color: {COLORS.divider};
    max-width: 1px;
}}

/* Cuadrícula de miniaturas: fondo oscuro en lugar del blanco por defecto. Las tarjetas
   se pintan solas en el delegado, así que solo se define el color de fondo */
QListView#list_view_grid {{
    background-color: {GRID_BG};
    border: none;
}}

/* Barra inferior (debajo de la cuadrícula): el mismo fondo oscuro que la cuadrícula, para
   que formen un solo bloque y se vean las marcas de la barra (recuadro, X, anillo del
   color), pensadas para fondo oscuro como en las tarjetas. Las zonas izquierda y derecha
   y la propia barra son transparentes: toman este fondo */
QFrame#frame_main_bottom {{
    background-color: {GRID_BG};
    border: none;
    border-top: 1px solid {COLORS.divider};
}}

/* Ventana de opciones: la columna de secciones toma el color de la ventana (sin el
   fondo blanco de una lista) y cada sección lleva un poco de aire a la izquierda */
QListWidget#list_settings_sections {{
    background: transparent;
}}
QListWidget#list_settings_sections::item {{
    padding-left: 8px;
}}

/* Barras laterales (catálogo, y en el futuro Imagen, Vídeo...): sin el fondo blanco de
   las listas, para que tomen el color de la ventana (como los paneles de Lightroom).
   'SidebarTreeView' es el árbol de cada sección (ui_helpers/widgets/sidebar_tree_view.py) */
QScrollArea#scroll_catalog_sidebar,
QWidget#widget_catalog_sidebar_content,
QScrollArea#scroll_image_sidebar,
QWidget#widget_image_sidebar_content,
QScrollArea#scroll_inspector,
QWidget#widget_inspector_content,
SidebarTreeView {{
    background: transparent;
    border: none;
}}

/* Fila seleccionada de las barras laterales: siempre con el color de selección, también
   cuando el foco está en otro sitio (p. ej. en la cuadrícula). Si no, con el fondo
   transparente la selección inactiva quedaba casi blanca y el texto (blanco) no se leía.
   El texto lo pinta 'CountDelegate' con el color 'HighlightedText' de la paleta */
SidebarTreeView::item:selected,
SidebarTreeView::item:selected:!active {{
    background-color: palette(highlight);
}}

/* Cabecera de cada sección plegable (ui_helpers/widgets/collapsible_section.py): franja
   algo más clara que el fondo, SIN línea debajo, y el título en MAYÚSCULAS (lo pone la
   sección) y en negrita, como las interfaces actuales */
QFrame#frame_section_header {{
    background-color: palette(button);
    border: none;
}}
QToolButton#btn_section_header {{
    border: none;
    background: transparent;
    font-weight: bold;
    padding: 4px 2px;
}}

/* Botones "+" de las cabeceras de Carpetas y Colecciones: sin marco ni relleno, solo el
   icono (o el signo, si falta el SVG). El de Colecciones abre un menú: se oculta su
   flechita. Al pasar el ratón, el icono toma el color de acento (ver catalog_sidebar.py) */
QToolButton#btn_sidebar_add_folder,
QToolButton#btn_sidebar_add_collection {{
    border: none;
    background: transparent;
    font-weight: bold;
    font-size: 15px;
    padding: 0px;
}}
QToolButton#btn_sidebar_add_folder:hover,
QToolButton#btn_sidebar_add_collection:hover {{
    color: {ACCENT_COLOR};
}}
QToolButton#btn_sidebar_add_collection::menu-indicator {{
    image: none;
    width: 0px;
}}

/* Inspector (panel derecho, ui_helpers/inspector/): nombre del archivo algo mayor y en
   negrita; la extensión, en una etiqueta con borde fino (como en la tarjeta); la inicial
   de un módulo sin icono, en negrita. Los iconos y el botón de la carpeta son 'IconCell'
   (base_section.py): no necesitan estilo */
/* Líneas que separan los grupos de filas (p. ej. en «Metadatos»): un gris discreto, que se
   aprecia sin llamar la atención (Fusion las dibujaría con el color del texto) */
QFrame#line_inspector_separator {{
    border: none;
    background-color: {COLORS.line};
    max-height: 1px;
}}

QLabel#lbl_inspector_name {{
    font-weight: bold;
    font-size: 13px;
}}
QLabel#lbl_inspector_extension {{
    border: 1px solid palette(mid);
    border-radius: 3px;
    padding: 0px 4px;
    font-size: 10px;
}}
QLabel#lbl_inspector_library_icon {{
    font-weight: bold;
}}

/* «Últimas palabras clave» del inspector (ui_helpers/widgets/recent_keywords.py): botones
   compactos, todos del mismo tamaño. Marcado (la tienen todos los seleccionados): borde y
   texto en el color de acento; con «*» (la tienen algunos): borde de acento discontinuo */
QPushButton#btn_recent_keyword {{
    padding: 2px 6px;
    min-height: 16px;
}}
QPushButton#btn_recent_keyword:checked {{
    border-color: {COLORS.accent};
    color: {COLORS.accent};
}}
QPushButton#btn_recent_keyword[partial="true"] {{
    border: 1px dashed {COLORS.accent};
}}
/* Su cabecera plegable: sin marco, como texto secundario */
QToolButton#btn_recent_keywords_toggle {{
    border: none;
    background: transparent;
    color: {COLORS.text_dim};
    padding: 2px 0px;
}}
QToolButton#btn_recent_keywords_toggle:hover {{
    color: {COLORS.text};
}}

/* ===== Botón «Cancelar» de los trabajos en la barra de estado: el de los diálogos, pero
   sin el relleno vertical, para que quepa entero en la barra (misma altura que la barra de
   progreso: 'JobProgressWidget.ROW_HEIGHT') */
QPushButton#btn_job_cancel {{
    padding: 0px 10px;
    min-height: 0px;
}}
"""


def apply_tooltip_style() -> None:
    """Cambia el fondo y el texto de los tooltips de toda la aplicación.

    Con el estilo Fusion, Qt dibuja los tooltips él mismo (no son tooltips
    nativos), así que se ven igual en Windows y macOS y se pueden personalizar
    sin perder coherencia entre sistemas.

    Se usa la paleta de QToolTip (no una hoja de estilos QSS) para que encaje
    con el futuro tema basado en QPalette, del que también leen los iconos.
    Importante: no añadir una regla QSS 'QToolTip' en STYLESHEET, porque
    anularía esta paleta.
    """
    palette = QToolTip.palette()
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(TOOLTIP_BG))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TOOLTIP_FG))
    QToolTip.setPalette(palette)


def build_palette(colors: ThemeColors) -> QPalette:
    """Paleta de Qt completa a partir de los colores del tema.

    Fusion dibuja casi todo con estos papeles ('roles'); los que no se rellenan los
    tomaría del sistema (claros en Windows), por eso se definen TODOS, también los de
    los relieves (Light, Midlight, Mid, Dark, Shadow) y los de lo desactivado.

    Papeles y su uso en la aplicación:
        Window / WindowText        fondo y texto de paneles, diálogos y menús
        Base / Text                campos, listas y desplegables
        AlternateBase              filas alternas y la toolbar lateral (QSS)
        Button / ButtonText        botones y cabeceras de sección (QSS)
        Highlight / HighlightedText selección y acento (iconos activos, ver ui_icons.py)
        PlaceholderText            texto secundario (etiquetas del inspector, contadores)
        Mid / Dark                 bordes finos y separación entre zonas (QSS)
    """
    palette = QPalette()

    def put(role: QPalette.ColorRole, color: str) -> None:
        """Un papel con el mismo color en todos los estados (activo, inactivo, desactivado)."""
        palette.setColor(role, QColor(color))

    put(QPalette.ColorRole.Window, colors.bg_panel)
    put(QPalette.ColorRole.WindowText, colors.text)
    put(QPalette.ColorRole.Base, colors.bg_input)
    put(QPalette.ColorRole.AlternateBase, colors.bg_base)
    put(QPalette.ColorRole.Text, colors.text)
    put(QPalette.ColorRole.Button, colors.bg_raised)
    put(QPalette.ColorRole.ButtonText, colors.text)
    put(QPalette.ColorRole.BrightText, colors.text_on_accent)
    put(QPalette.ColorRole.PlaceholderText, colors.text_dim)
    put(QPalette.ColorRole.ToolTipBase, colors.bg_tooltip)
    put(QPalette.ColorRole.ToolTipText, colors.text)
    put(QPalette.ColorRole.Highlight, colors.accent)
    put(QPalette.ColorRole.HighlightedText, colors.text_on_accent)
    put(QPalette.ColorRole.Link, colors.link)
    put(QPalette.ColorRole.LinkVisited, colors.link)
    # Relieves que Fusion usa en bordes de botones, campos y marcos
    put(QPalette.ColorRole.Light, colors.bg_hover)
    put(QPalette.ColorRole.Midlight, colors.bg_raised)
    put(QPalette.ColorRole.Mid, colors.line)
    put(QPalette.ColorRole.Dark, colors.line_dark)
    put(QPalette.ColorRole.Shadow, "#000000")
    # Qt 6.6+: color de acento propio (algunos estilos lo usan en vez de Highlight)
    accent_role = getattr(QPalette.ColorRole, "Accent", None)
    if accent_role is not None:
        put(accent_role, colors.accent)

    # Lo desactivado: texto apagado y la selección en gris (no en el color de acento)
    disabled = QPalette.ColorGroup.Disabled
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(disabled, role, QColor(colors.text_disabled))
    palette.setColor(disabled, QPalette.ColorRole.Highlight, QColor(colors.bg_hover))
    palette.setColor(disabled, QPalette.ColorRole.HighlightedText, QColor(colors.text_disabled))
    return palette


def _use_dark_title_bar() -> None:
    """Pide al sistema la barra de título y los diálogos nativos en oscuro (Qt 6.8+).

    En Windows 10/11 la barra de título la dibuja el sistema: sin esto, saldría clara
    sobre una ventana oscura. En versiones de Qt anteriores no hace nada.
    """
    hints = QGuiApplication.styleHints()
    scheme = getattr(Qt, "ColorScheme", None)
    if scheme is not None and hasattr(hints, "setColorScheme"):
        hints.setColorScheme(scheme.Dark)


# Estilo de la aplicación. Se guarda aquí para que Python no lo libere mientras Qt lo usa
_app_style: ThemeStyle | None = None


def apply_theme() -> None:
    """Aplica el aspecto global de la aplicación. Llamar una vez al arrancar, antes de
    crear la ventana principal.

    Instala el estilo propio (Fusion con los botones de opción y las casillas del tema)
    ANTES de la paleta: cambiar de estilo reinicia la paleta de la aplicación.
    """
    global _app_style
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        raise RuntimeError("apply_theme() requiere un QApplication ya creado.")

    _app_style = ThemeStyle(COLORS)
    app.setStyle(_app_style)
    _use_dark_title_bar()
    app.setPalette(build_palette(COLORS))
    apply_tooltip_style()
    app.setStyleSheet(STYLESHEET)
