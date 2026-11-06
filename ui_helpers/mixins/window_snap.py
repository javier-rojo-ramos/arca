"""Extensión (mixin) para añadir comportamiento de ajuste magnético a las ventanas.

Este módulo proporciona una clase complementaria ('WindowSnapMixin') diseñada para
integrarse con componentes visuales de Qt ('QWidget' o 'QMainWindow'). Su función
es calcular la proximidad de la ventana a los bordes de la pantalla utilizable durante
los eventos de desplazamiento, aplicando un efecto "magnético". Incluye soporte
nativo para escalado dinámico en pantallas de alta densidad de píxeles (High-DPI) y
restricciones por plataforma (desactivado automáticamente en macOS).

1.0.1 Se usa una adaptación nativa al calcular el ratio para resoluciones HIGH-DPI (PySide6).
1.0.2 Protección contra NoneType en transiciones de monitor.
"""

__version__ = "1.0.2"
__all__ = ["WindowSnapMixin"]

# Nota: En def __init__(self): se desactiva el ajuste magnético en macOS

# Librerías estándar
import sys

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QApplication

# Módulos del proyecto
from config import app_constants


class WindowSnapMixin:
    """Mixin que añade comportamiento de ajuste magnético a los bordes de la pantalla.

    La clase que herede de este Mixin debe ser un QWidget o QMainWindow.
    """

    def __init__(self):
        self.usar_ajuste_magnetico = True
        # Se desactiva el ajuste magnético en macOS
        if sys.platform == "darwin":
            self.usar_ajuste_magnetico = False
        self._is_snapping = False
        self.is_fully_loaded = False

    def check_snap_and_move(self, event):
        """Llamar a este método dentro del moveEvent original de la ventana."""
        # Si el usuario ha decidido desactivar el ajuste por código, se ignora
        if (
            not self.usar_ajuste_magnetico
            or not self.is_fully_loaded
            or self._is_snapping
        ):
            return

        # Se ignora si la ventana ya está maximizada, minimizada o en pantalla completa
        if self.isMaximized() or self.isMinimized() or self.isFullScreen():
            return

        # Se ignora si la ventana se está moviendo por una animación del sistema,
        # solo se aplica si el usuario está arrastrando la ventana con el ratón
        if not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            return

        # Protección contra NoneType en transiciones de monitor
        screen = self.screen()
        if not screen:
            return

        screen_geom = self.screen().availableGeometry()
        win_geom = self.frameGeometry()

        current_x, current_y = win_geom.x(), win_geom.y()
        w, h = win_geom.width(), win_geom.height()
        new_x, new_y = current_x, current_y

        # Adaptación para resoluciones HIGH-DPI (ej: escalado en Windows al 150%), se
        # obtiene el factor de escala de la pantalla actual para ajustar el umbral
        ratio = self.devicePixelRatio()
        # Se escala el umbral y el gap dinámicamente
        snap_threshold = int(app_constants.SNAP_THRESHOLD * ratio)
        gap = int(app_constants.SNAP_GAP * ratio)

        screen_top = screen_geom.y()
        screen_bottom = screen_geom.y() + screen_geom.height()
        screen_left = screen_geom.x()
        screen_right = screen_geom.x() + screen_geom.width()

        # Ajuste eje Y superior
        if abs(current_y - screen_top) < snap_threshold:
            new_y = screen_top + gap
        # Ajuste eje Y inferior
        elif abs((current_y + h) - screen_bottom) < snap_threshold:
            new_y = screen_bottom - h - gap

        # Ajuste eje X izquierdo
        if abs(current_x - screen_left) < snap_threshold:
            new_x = screen_left + gap
        # Ajuste eje X derecho
        elif abs((current_x + w) - screen_right) < snap_threshold:
            new_x = screen_right - w - gap

        # Si las coordenadas han cambiado debido al "magnetismo" se mueve la ventana
        if new_x != current_x or new_y != current_y:
            self._is_snapping = True
            self.move(new_x, new_y)
            self._is_snapping = False
