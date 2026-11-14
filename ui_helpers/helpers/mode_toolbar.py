"""Botones de modo de la toolbar lateral (Catálogo, Imagen, Vídeo, Audio...).

Cada botón es un MODO de la aplicación: al pulsarlo se muestra su barra lateral y su icono
se queda en el color de acento, para que siempre se vea en qué modo se está (como las
carpetas desplegadas de la barra lateral). Solo puede haber un modo activo.

Iconos (SVG monocromos de 'AppIcons', teñidos con 'tinted_icon'):
    - Normal y ratón encima: color normal (el del texto de la paleta). Con el ratón solo
                             cambia la caja del botón (QSS de 'ui_theme.py').
    - Modo activo:           color de acento fijo (solo al pulsarlo; decidido por el autor
                             el 07/11/2026).
El acento es 'TOOLBAR_ICON_ACCENT_COLOR' (ui_theme.py); None = el color de selección del
sistema, el mismo que usan las carpetas desplegadas de la barra lateral.

Los modos que aún no tienen barra lateral propia (Imagen, Vídeo, Audio) muestran una
página provisional ("próximamente"), creada aquí: así el botón ya funciona y, cuando
exista su barra, basta con pasarla en 'pages'.

Uso (en el controlador):
    self.mode_toolbar = ModeToolbar(
        {"catalog": (self.btn_catalog, AppIcons.LIB_ALL, "Catálogo"), ...},
        stack=self.stacked_widget_sidebar_catalog,
        pages={"catalog": self.page_catalog_default},
        parent=self,
    )
    self.mode_toolbar.mode_changed.connect(...)

1.2.0 Modo Tracks ('MODE_TRACKS').
1.1.0 El icono ya no se pone en el acento al pasar el ratón: solo el del modo activo.
"""

__version__ = "1.2.0"
__all__ = [
    "MODE_AUDIO",
    "MODE_CATALOG",
    "MODE_IMAGE",
    "MODE_TRACKS",
    "MODE_VIDEO",
    "ModeToolbar",
    "toolbar_accent_color",
]

# Librerías de terceros (Qt)
from qtpy.QtCore import QFile, QObject, Qt, Signal
from qtpy.QtGui import QColor, QGuiApplication, QIcon, QPalette
from qtpy.QtWidgets import QButtonGroup, QLabel, QStackedWidget, QToolButton, QWidget

# Módulos del proyecto
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_theme import TOOLBAR_ICON_ACCENT_COLOR

# Claves de los modos
MODE_CATALOG = "catalog"
MODE_IMAGE = "image"
MODE_VIDEO = "video"
MODE_AUDIO = "audio"
MODE_TRACKS = "tracks"


def toolbar_accent_color() -> QColor:
    """Color de acento de los iconos de la toolbar ('TOOLBAR_ICON_ACCENT_COLOR' o el del sistema)."""
    if TOOLBAR_ICON_ACCENT_COLOR:
        return QColor(TOOLBAR_ICON_ACCENT_COLOR)
    return QGuiApplication.palette().color(QPalette.ColorRole.Highlight)


class ModeToolbar(QObject):
    """Grupo exclusivo de botones de modo, con su icono y su página de barra lateral.

    Signals:
        mode_changed(str): el usuario (o 'set_mode') ha cambiado de modo; lleva su clave.
    """

    mode_changed = Signal(str)

    def __init__(
        self,
        buttons: dict[str, tuple[QToolButton, str | None, str]],
        *,
        stack: QStackedWidget,
        pages: dict[str, QWidget],
        parent: QObject | None = None,
    ) -> None:
        """Configura los botones.

        Args:
            buttons: Por modo: (botón, ruta del SVG o None, nombre para el usuario). El
                orden es el de la toolbar; el primero es el modo inicial.
            stack: Donde se muestran las barras laterales de cada modo.
            pages: Barra lateral de cada modo que ya la tiene (los demás reciben una
                página provisional).
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._buttons: dict[str, QToolButton] = {}
        self._icons: dict[str, tuple[QIcon, QIcon]] = {}  # (normal, activo)
        self._pages = dict(pages)
        self._stack = stack
        self._current = ""

        accent = toolbar_accent_color()
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)  # solo un modo activo a la vez

        for mode, (button, icon_path, title) in buttons.items():
            button.setCheckable(True)
            button.setToolTip(title)
            if icon_path and QFile.exists(icon_path):
                normal = tinted_icon(icon_path)  # sin acento al pasar el ratón
                active = tinted_icon(icon_path, accent)
                self._icons[mode] = (normal, active)
                button.setIcon(normal)
            else:
                # Sin SVG todavía: la inicial, para que el botón se vea y se pueda usar
                button.setText(title[:1])
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self._group.addButton(button)
            self._buttons[mode] = button
            button.toggled.connect(lambda checked, m=mode: self._on_toggled(m, checked))

            if mode not in self._pages:
                self._pages[mode] = self._placeholder_page(title)
                stack.addWidget(self._pages[mode])

        if buttons:
            self.set_mode(next(iter(buttons)))

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def current_mode(self) -> str:
        """Modo activo."""
        return self._current

    def set_mode(self, mode: str) -> None:
        """Activa un modo (como si se pulsara su botón)."""
        button = self._buttons.get(mode)
        if button is None:
            return
        if button.isChecked():
            self._apply(mode)  # ya estaba marcado: solo se asegura su página
        else:
            button.setChecked(True)  # -> '_on_toggled'

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _on_toggled(self, mode: str, checked: bool) -> None:
        """Un botón se marca o se desmarca: cambia su icono y, si se marca, el modo."""
        icons = self._icons.get(mode)
        if icons is not None:
            self._buttons[mode].setIcon(icons[1] if checked else icons[0])
        if checked:
            self._apply(mode)

    def _apply(self, mode: str) -> None:
        """Muestra la barra lateral del modo y avisa si ha cambiado."""
        page = self._pages.get(mode)
        if page is not None:
            self._stack.setCurrentWidget(page)
        if mode != self._current:
            self._current = mode
            self.mode_changed.emit(mode)

    @staticmethod
    def _placeholder_page(title: str) -> QWidget:
        """Página provisional para un modo que aún no tiene barra lateral."""
        label = QLabel(f"{title}\n\n(próximamente)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setEnabled(False)  # texto atenuado
        return label
