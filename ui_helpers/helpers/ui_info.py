"""Utilidades para mostrar ventanas de información con contenido rico (HTML/RichText).

1.02 Se armonizan los nombres de las variables y métodos para mantener consistencia.
1.01 Se incorpora center_on_screen como argumento para centrar en la pantalla activa.
"""

__version__ = "1.02"
__all__ = ["show_info_window"]

# Librerías de terceros (Qt)
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QStyle,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


def show_info_window(
    parent: QWidget | None,
    title: str,
    html_content: str,
    width: int = 360,
    height: int = 320,
    center_on_screen: bool = False,
) -> None:
    """Abre un diálogo modal reutilizable para mostrar HTML.

    Args:
        parent: Ventana padre.
        title: Título de la ventana emergente.
        html_content: Cadena con marcado HTML a renderizar.
        width: Ancho inicial en píxeles.
        height: Alto inicial en píxeles.
        center_on_screen: Si es 'True', centra el diálogo en la pantalla activa.
            Si es 'False', lo centra respecto al parent impidiendo que salga de pantalla.
    """
    # Se crea el diálogo modal
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(width, height)

    try:
        # Métricas estándar del estilo activo (margin y spacing)
        style = dialog.style()
        m_left = style.pixelMetric(QStyle.PixelMetric.PM_LayoutLeftMargin, None, dialog)
        m_top = style.pixelMetric(QStyle.PixelMetric.PM_LayoutTopMargin, None, dialog)
        m_right = style.pixelMetric(
            QStyle.PixelMetric.PM_LayoutRightMargin, None, dialog
        )
        m_bottom = style.pixelMetric(
            QStyle.PixelMetric.PM_LayoutBottomMargin, None, dialog
        )
        spacing = style.pixelMetric(
            QStyle.PixelMetric.PM_LayoutVerticalSpacing, None, dialog
        )

        # Un único layout principal con márgenes y espaciado nativo
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(m_left, m_top, m_right, m_bottom)
        main_layout.setSpacing(spacing)

        # Visor para mostrar el contenido HTML
        text_browser = QTextBrowser(dialog)
        text_browser.setOpenExternalLinks(True)
        text_browser.setHtml(html_content)
        main_layout.addWidget(text_browser)

        # Botón de cierre
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.reject)
        main_layout.addWidget(button_box)

        # Detección del monitor activo (compatible con entornos multimonitor)
        screen = None
        if parent and parent.window():
            handler = parent.window().windowHandle()
            if handler:
                screen = handler.screen()

        if not screen:
            screen = QGuiApplication.primaryScreen()

        if screen:
            geo = screen.availableGeometry()

            if center_on_screen or not parent or not parent.isVisible():
                # Centrado absoluto en el área útil del monitor
                x = geo.left() + (geo.width() - dialog.width()) // 2
                y = geo.top() + (geo.height() - dialog.height()) // 2
            else:
                # Centrado relativo a la ventana principal
                x = parent.x() + (parent.width() - dialog.width()) // 2
                y = parent.y() + (parent.height() - dialog.height()) // 2

                # Clamping: impide salir por los límites útiles de la pantalla
                x = max(geo.left(), min(x, geo.right() - dialog.width()))
                y = max(geo.top(), min(y, geo.bottom() - dialog.height()))

            dialog.move(x, y)

        dialog.exec()

    finally:
        # Se garantiza la limpieza en memoria C++
        dialog.deleteLater()
