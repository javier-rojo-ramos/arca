"""Utilidades para la gestión centralizada de cuadros de diálogo y alertas visuales.

Este módulo proporciona una capa de abstracción sobre 'QMessageBox' para simplificar
la creación de ventanas emergentes interactivas. Centraliza y estandariza la
configuración de iconos, textos y roles de botones para mensajes de información,
advertencias, errores críticos y preguntas, garantizando además la compatibilidad
retroactiva en la ejecución de diálogos entre distintas versiones de Qt.

1.08 Se armonizan los nombres de las variables y métodos para mantener consistencia.
1.07 Se elimina compatibilidad con PyQt5 / PySide2, manteniendo solo PyQt6 / PySide6.
1.06 Flag configurable para el centrado mediante la variable 'ajuste_manual':
    True: el diálogo se centra manualmente, en función de las coordenadas, dentro del
        área visible de la pantalla actual. Este flag puede ser ignorado en algunas
        distribuciones Linux modernas que usan Wayland en vez de X11.
    False: el diálogo se posiciona automáticamente por parte de Qt.
1.05 Se añade QTimer para cálculo exacto de geometría y sobreescritura de centrado.
1.04 Se ajusta el centrado al área visible de la pantalla actual.
1.03 Cálculo explícito para centrado preciso respecto al 'parent'.
1.02 Requiere importar app_paths para mostrar el APP_NAME_COMERCIAL como título.
1.01 Se incorpora el título de la aplicación como título por defecto.
"""

__version__ = "1.07"
__all__ = ["MessageBoxHelper"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QTimer
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import QMessageBox, QWidget

# Módulos del proyecto
from config import app_paths


class MessageBoxHelper:
    """Gestor centralizado de diálogos QMessageBox.

    Incluye mensajes 'info', 'warning', 'critical', y 'question'.
    """

    def __init__(
        self,
        parent: QWidget | None,
        app_name: str = app_paths.APP_NAME_COMERCIAL,
        centered: bool = False,  # Por defecto Qt posiciona el mensaje
    ):
        self.parent = parent
        self.app_name = app_name
        self.centered = centered

    def info(
        self,
        text: str,
        title: str | None = None,
        buttons: list[str] | None = None,
        centered: bool | None = None,
    ) -> str | None:
        return self._show("info", text, title, buttons, centered)

    def warning(
        self,
        text: str,
        title: str | None = None,
        buttons: list[str] | None = None,
        centered: bool | None = None,
    ) -> str | None:
        return self._show("warning", text, title, buttons, centered)

    def critical(
        self,
        text: str,
        title: str | None = None,
        buttons: list[str] | None = None,
        centered: bool | None = None,
    ) -> str | None:
        return self._show("critical", text, title, buttons, centered)

    def question(
        self,
        text: str,
        title: str | None = None,
        buttons: list[str] | None = None,
        centered: bool | None = None,
    ) -> str | None:
        return self._show("question", text, title, buttons, centered)

    def _show(
        self,
        type: str,
        text: str,
        title: str | None = None,
        buttons: list[str] | None = None,
        centered: bool | None = None,
    ) -> str | None:
        title_to_show = title if title is not None else self.app_name

        # Prioriza el parámetro del método; si no se pasa, usa el de la instancia
        use_adjust_centered = centered if centered is not None else self.centered

        parent_window = self.parent.window() if self.parent else None
        msg = QMessageBox(parent_window)
        msg.setWindowTitle(title_to_show)

        icon_map = {
            "info": QMessageBox.Icon.Information,
            "warning": QMessageBox.Icon.Warning,
            "critical": QMessageBox.Icon.Critical,
            "question": QMessageBox.Icon.Question,
        }
        msg.setIcon(icon_map.get(type, QMessageBox.Icon.Information))
        msg.setText(text)

        if buttons:
            for i, btn_text in enumerate(buttons):
                role = (
                    QMessageBox.ButtonRole.AcceptRole
                    if i == 0
                    else QMessageBox.ButtonRole.RejectRole
                )
                msg.addButton(btn_text, role)
        else:
            msg.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)

        if use_adjust_centered and parent_window and parent_window.isVisible():

            def apply_center_alignment():
                screen = None
                handler = parent_window.windowHandle()
                if handler:
                    screen = handler.screen()

                if not screen:
                    screen = QGuiApplication.primaryScreen()

                if screen:
                    geo = screen.availableGeometry()
                    parent_rect = parent_window.geometry()

                    msg_width = msg.width()
                    msg_height = msg.height()

                    x = parent_rect.x() + (parent_rect.width() - msg_width) // 2
                    y = parent_rect.y() + (parent_rect.height() - msg_height) // 2

                    x = max(geo.left(), min(x, geo.right() - msg_width))
                    y = max(geo.top(), min(y, geo.bottom() - msg_height))

                    msg.move(x, y)

            QTimer.singleShot(0, apply_center_alignment)

        msg.exec()

        clicked = msg.clickedButton()
        return clicked.text() if clicked else None
