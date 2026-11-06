"""Utilidades para la barra de estado e información contextual en la interfaz.

Este módulo proporciona una solución desacoplada y eficiente para mostrar
notificaciones enriquecidas con iconos y temporizadores en la barra de estado de
la ventana principal ('QStatusBar'). Implementa un patrón de reutilización de widgets
(mediante la búsqueda de hijos en el árbol de Qt) que previene la fragmentación de
memoria, fugas y comportamientos inesperados derivados de la recreación constante
de controles gráficos.

El icono se tiñe con 'tinted_pixmap' (da igual el color en que esté guardado el SVG): verde
si es la marca de «hecho», amarillo si es un aviso, rojo si es un error y, el resto, del
color del texto. Los colores salen del tema ('theme_colors.py').

1.1.1 El icono se tiñe con 'tinted_pixmap' (directo, sin pasar por QIcon) y a la escala
      de la pantalla.
1.1.0 Icono teñido con los colores del tema (antes salía del color del SVG y, sobre el
      fondo oscuro, apenas se veía).
1.0.1 Tipado de la ventana padre 'parent' en la firma de 'message_bar'
"""

__version__ = "1.1.1"
__all__ = ["message_bar"]

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import QHBoxLayout, QLabel, QWidget

# Módulos del proyecto
from config import app_constants
from config.app_constants import AppIcons
from ui_helpers.helpers.ui_icons import tinted_pixmap
from ui_helpers.helpers.ui_theme import COLORS

# Color de cada icono de la barra de estado; los que no están aquí (información...), del
# color del texto. Las variantes ya coloreadas del .qrc ('__green', '__red') se tiñen igual
_ICON_COLORS: dict[str, str] = {
    AppIcons.CHECK_CIRCLE: COLORS.success,
    AppIcons.CHECK_CIRCLE__GREEN: COLORS.success,
    AppIcons.WARNING: COLORS.warning,
    AppIcons.ERROR: COLORS.error,
    AppIcons.ERROR__RED: COLORS.error,
}


def message_bar(
    parent: QWidget | None,
    texto: str,
    icono: str = AppIcons.INFO,
    duracion: int = app_constants.STATUSBAR_DURATION,
) -> None:
    """Muestra un mensaje personalizado en la barra de estado inferior.

    Reutiliza los widgets para evitar fugas de memoria y cierres inesperados.
    Si 'duracion' es 0, el mensaje se mantendrá fijo de forma indefinida.
    """

    # Se intenta recuperar el contenedor si ya se ha creado en una instancia previa
    contenedor = parent.statusBar().findChild(QWidget, "CustomMessageContainer")

    # Si no existe, se crea (sólo ocurre una vez)
    if not contenedor:
        contenedor = QWidget()
        contenedor.setObjectName("CustomMessageContainer")

        layout = QHBoxLayout(contenedor)
        # Ajuste visual, 5px a la izquierda y 3 px desde abajo para centrado vertical
        layout.setContentsMargins(5, 0, 0, 3)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Label para el icono
        label_icono = QLabel()
        label_icono.setObjectName("CustomMessageIcon")
        layout.addWidget(label_icono)

        # Label para el texto
        label_texto = QLabel()
        label_texto.setObjectName("CustomMessageText")
        label_texto.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(label_texto)

        # Temporizador persistente atado al contenedor
        timer = QTimer(contenedor)
        timer.setObjectName("CustomMessageTimer")
        # Cuando el timer se agote, simplemente ocultamos el contenedor (no lo destruimos)
        timer.timeout.connect(contenedor.hide)

        # Se añade de forma permanente a la barra de estado
        parent.statusBar().addWidget(contenedor)

    # Se recuperan los componentes (si se acaban de crear o si ya existían)
    label_icono = contenedor.findChild(QLabel, "CustomMessageIcon")
    label_texto = contenedor.findChild(QLabel, "CustomMessageText")
    timer = contenedor.findChild(QTimer, "CustomMessageTimer")

    # Se actualiza el contenido
    if icono:
        color = _ICON_COLORS.get(icono, COLORS.text)
        label_icono.setPixmap(tinted_pixmap(icono, color, 16, label_icono.devicePixelRatioF()))
        label_icono.show()
    else:
        label_icono.hide()

    label_texto.setText(texto)

    # Se muestra el contenedor
    contenedor.show()

    # Se gestiona el temporizador
    timer.stop()  # Detiene el timer anterior si estaba corriendo

    if duracion > 0:
        timer.start(duracion)  # Inicia la nueva cuenta atrás
