"""Etiqueta de una línea que recorta su texto con '…' cuando no cabe.

QLabel no recorta: si el texto es largo, ensancha el panel o se sale. Esta etiqueta guarda
el texto completo y, cada vez que cambia de ancho, muestra la parte que cabe:

    - Qt.TextElideMode.ElideRight   'Fotos y vídeos perso…'   (por defecto)
    - Qt.TextElideMode.ElideLeft    '…\\Fotos & Videos\\2024'  (rutas: se ve el final)
    - Qt.TextElideMode.ElideMiddle  'IMG_20240601…_0001.jpg'

Si se recorta y no hay un texto emergente propio, el emergente muestra el texto completo.

Uso:
    label = ElidedLabel(parent, mode=Qt.TextElideMode.ElideLeft)
    label.set_full_text(r"D:\\Fotos\\2024\\Viaje")
"""

__version__ = "1.0.0"
__all__ = ["ElidedLabel"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QSize, Qt
from qtpy.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    """QLabel de una línea que recorta el texto al ancho disponible (ver el módulo)."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
    ) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._mode = mode
        self._own_tooltip = ""  # el que se pone desde fuera (manda sobre el automático)
        # Puede encoger hasta casi nada: el ancho lo decide el panel, no el texto
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(10)
        self.setTextFormat(Qt.TextFormat.PlainText)

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def set_full_text(self, text: str, tooltip: str = "") -> None:
        """Cambia el texto (completo) y, opcionalmente, el texto emergente propio."""
        self._full_text = text
        self._own_tooltip = tooltip
        self._update_elided()

    def full_text(self) -> str:
        """Texto completo (sin recortar)."""
        return self._full_text

    # -------------------------------------------------------------------------
    # Qt
    # -------------------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802 - nombre de Qt
        super().resizeEvent(event)
        self._update_elided()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - nombre de Qt
        # Solo el alto: a lo ancho puede encoger (el texto se recorta)
        hint = super().minimumSizeHint()
        return QSize(10, hint.height())

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _update_elided(self) -> None:
        """Muestra la parte del texto que cabe y ajusta el texto emergente."""
        available = max(0, self.contentsRect().width())
        shown = self.fontMetrics().elidedText(self._full_text, self._mode, available)
        super().setText(shown)
        if self._own_tooltip:
            self.setToolTip(self._own_tooltip)
        else:
            self.setToolTip(self._full_text if shown != self._full_text else "")
