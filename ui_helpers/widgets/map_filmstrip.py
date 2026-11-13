"""Tira de fotos debajo del mapa: las tarjetas de la cuadrícula, en una sola fila.

Como la tira de Lightroom (decidido por el autor el 13/11/2026; docs/MAPA.md, paso 3.1):
muestra LO MISMO que la cuadrícula (su modelo) y comparte su SELECCIÓN (su
'selectionModel'): lo que se elige aquí se elige en la cuadrícula, en el mapa y en el
inspector. Desde aquí se arrastran las fotos al mapa para ubicarlas.

    ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
    │ foto ││ foto ││ foto ││ foto ││ foto │   <- una fila; la rueda la mueve a los lados
    └──────┘└──────┘└──────┘└──────┘└──────┘

Es una 'MediaGridView' (las mismas tarjetas, zonas activas y «No hay archivos») con:
    - su propio delegado, del alto de la tira (el de la cuadrícula lo marca el deslizador),
      con tarjetas COMPACTAS: solo la imagen, sin la banda del nombre, las estrellas y la
      marca ni el círculo de la selección rápida, que de lo seleccionado ya se ven en la
      barra inferior (el autor, 13/11/2026, como Lightroom); el nombre, al pasar el ratón;
    - arrastre SIN imagen: sobre el mapa solo se ve el círculo ámbar de dónde caen las
      fotos (el autor, 13/11/2026).

Uso:
    tira = MapFilmstrip(parent)
    tira.attach(modelo_de_la_cuadricula, cuadricula.selectionModel())

1.1.1 La barra de desplazamiento, siempre: sin ella, la tira podía entrar en un bucle
      de tamaños y montar unas tarjetas sobre otras.
1.1.0 Tarjetas compactas (sin banda ni círculo de la selección rápida) y alto mínimo de
      100 px (miniaturas de 72 px).
1.0.0 Primera versión (docs/MAPA.md, paso 3.1).
"""

__version__ = "1.1.1"
__all__ = ["MIN_HEIGHT", "MapFilmstrip"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QAbstractItemModel, QItemSelectionModel, QSize, Qt
from qtpy.QtGui import QResizeEvent, QWheelEvent
from qtpy.QtWidgets import QAbstractItemView, QListView, QWidget

# Módulos del proyecto
from ui_helpers.delegates.thumbnails_delegate import ThumbnailsDelegate
from ui_helpers.widgets.media_grid_view import MediaGridView

# Tarjeta compacta: el hueco de la miniatura, cuadrado, más los márgenes del delegado
# ('ThumbnailsDelegate.PAD' a los lados; 'PAD' y el borde arriba y abajo)
_CARD_EXTRA_HEIGHT = 2 * (ThumbnailsDelegate.PAD + 1)
_CARD_EXTRA_WIDTH = 2 * ThumbnailsDelegate.PAD
_MIN_THUMBNAIL = 72  # lado mínimo del hueco de la miniatura
# Alto mínimo de la tira: una tarjeta con el hueco mínimo y la barra de desplazamiento
MIN_HEIGHT = 100


class MapFilmstrip(MediaGridView):
    """La tira de fotos (ver el docstring del archivo)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("list_map_filmstrip")
        self._delegate = ThumbnailsDelegate(self)
        self._delegate.compact = True  # solo la imagen (ver el docstring del archivo)
        self.setItemDelegate(self._delegate)
        # Una sola fila, de izquierda a derecha, que se desplaza a los lados
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setSpacing(0)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # La barra, SIEMPRE (como en Lightroom): las tarjetas toman su alto del espacio que
        # queda; si la barra apareciera y desapareciera, ese espacio cambiaría con ella y la
        # tira entraría en un bucle (más tarjetas que caben -> barra -> tarjetas más bajas y
        # estrechas -> caben -> sin barra -> más altas...), que con algunos números de fotos
        # las dejaba montadas unas sobre otras (lo vio el autor el 13/11/2026)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        # Como la cuadrícula: solo se arrastra hacia fuera y solo se copia (va DESPUÉS de
        # 'setMovement(Static)', que desactiva el arrastre por su cuenta)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.set_drag_image(False)
        self.setMinimumHeight(MIN_HEIGHT)

    def attach(self, model: QAbstractItemModel, selection_model: QItemSelectionModel) -> None:
        """Usa el modelo y la selección de la cuadrícula (la selección es la misma)."""
        self.setModel(model)
        own = self.selectionModel()
        self.setSelectionModel(selection_model)
        if own is not None and own is not selection_model:
            own.deleteLater()  # el que creó 'setModel' ya no sirve
        self._fit_cards()

    def card_size(self) -> QSize:
        """Tamaño de cada tarjeta (el alto, el de la tira)."""
        return self._delegate.item_size

    # -------------------------------------------------------------------------
    # Tarjetas del alto de la tira
    # -------------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:  # nombre de Qt
        super().resizeEvent(event)
        self._fit_cards()

    def _fit_cards(self) -> None:
        """Las tarjetas, del alto de la tira (menos la barra de desplazamiento), con el
        hueco de la miniatura cuadrado."""
        thumbnail = max(_MIN_THUMBNAIL, self.viewport().height() - _CARD_EXTRA_HEIGHT)
        size = QSize(thumbnail + _CARD_EXTRA_WIDTH, thumbnail + _CARD_EXTRA_HEIGHT)
        if size != self._delegate.item_size:
            self._delegate.item_size = size
            # Cambiar el tamaño del icono rehace la colocación de las tarjetas
            self.setIconSize(QSize(thumbnail, thumbnail))

    # -------------------------------------------------------------------------
    # La rueda mueve la tira a los lados
    # -------------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # nombre de Qt
        delta = event.angleDelta()
        if delta.x() == 0 and delta.y() != 0:
            # Cada «clic» de la rueda (120), una tarjeta
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - round(delta.y() / 120 * self._delegate.item_size.width()))
            event.accept()
            return
        super().wheelEvent(event)
