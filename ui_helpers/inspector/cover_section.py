"""Sección «Carátula» del inspector: la carátula de las canciones seleccionadas.

Aparece cuando hay algo seleccionado y TODO es de la biblioteca Música (en cualquier
módulo: en Audio y también en el Catálogo), como «Audio», y de partida detrás de ella. La
forma, la acordada con el autor el 25/11/2026 tras ver una muestra y el 26/11/2026
(docs/MOD_MUSICA.md §6):

    ▼ CARÁTULA
       ┌──────────────────────────────┐
       │                              │
       │  la imagen, a todo el ancho  │
       │                              │
       └──────────────────────────────┘
       Tipo                Portada
       Imagen              JPEG · 600 × 600 · 117 KB

La imagen ('ui_helpers/widgets/cover_image.py': un cuadrado, con las pequeñas ampliadas
y una raya fina alrededor) sale de la caché de miniaturas, NUNCA del archivo: la de 1200
px, con un 'FullImageLoader' propio y la caché que da el panel ('bind_thumbnails'). Si
se regenera ('thumbnails_changed'), se vuelve a leer. Mientras llega, se ve la anterior
(sin parpadeo); si la canción aún no tiene miniatura, el marcador, y la carátula llega
sola al generarse.

Con VARIAS canciones, cada fila con su regla (las de «Audio»; 'core/catalog/cover_stats'):
«Tipo», el común o «Varios»; «Imagen», la de todas si es la misma (un álbum) o «Varios»,
con «2 carátulas distintas» al pasar el ratón. La imagen, solo si es la misma en todas;
si no, el marcador. Si ninguna tiene carátula, el marcador y «Sin carátula» en gris. Si
un archivo trae más de una imagen, «Tipo» lo dice al pasar el ratón: se enseña la que
hace de carátula.

De SOLO LECTURA (`MUS 9.1`): cambiarla, extraerla y quitarla llegan con `MUS 9.2`–`9.4`;
el tipo será un desplegable cuando se pueda cambiar.

Los valores NO están en el resumen de la selección: la sección los pide con
'data_request' ('fetch_cover_stats', en segundo plano) y los escribe en 'show_data'.

1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 9.1).
"""

__version__ = "1.0.0"
__all__ = ["NO_COVER_TEXT", "CoverSection"]

# Librerías estándar
from collections.abc import Callable, Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtGui import QImage
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from core.audio.picture_types import picture_type_label
from core.catalog.cover_stats import CoverStats, fetch_cover_stats
from core.catalog.libraries import Library
from core.catalog.media_types import MediaType
from core.catalog.selection_metadata import EMPTY, MIXED, VALUE
from core.catalog.selection_summary import SelectionSummary
from core.thumbnails.sizes import ThumbnailSize
from ui_helpers.inspector.base_section import (
    InfoGrid,
    InspectorSection,
    ThumbnailCacheProvider,
    set_secondary_text,
)
from ui_helpers.inspector.formatting import format_count, format_cover_image
from ui_helpers.inspector.metadata_fields import MIXED_TEXT
from ui_helpers.models.full_image_loader import FullImageLoader
from ui_helpers.widgets.cover_image import CoverImage

# La fila «Imagen» cuando ninguna canción tiene carátula
NO_COVER_TEXT = "Sin carátula"

# El tamaño de la caché que se lee: la de 1200 px, nítida con el panel a su ancho de siempre
# también con la pantalla escalada (la de 480 se quedaría corta a partir del 150 %)
_WANTED = ThumbnailSize.PREVIEW
_AUDIO = MediaType.AUDIO.value


def _songs(count: int) -> str:
    """'1 canción', '3 canciones'."""
    return "1 canción" if count == 1 else f"{format_count(count)} canciones"


class CoverSection(InspectorSection):
    """Sección «Carátula» (ver el docstring del módulo)."""

    title = "Carátula"
    key = "cover"
    libraries = (Library.AUDIO.value,)  # solo si todo lo seleccionado es de Música

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._grid = InfoGrid(self)
        layout.addWidget(self._grid)

        # La imagen, a todo el ancho de las filas (con su mismo margen a los dos lados)
        self._cover = CoverImage(self._grid, media_type=_AUDIO)
        self._grid.add_widget_row(self._cover)
        self._type = self._grid.add_row("Tipo")
        self._image = self._grid.add_row("Imagen")

        self._loader: FullImageLoader | None = None  # hasta 'bind_thumbnails'
        self._shown_id: int | None = None  # la canción cuya carátula se quiere ver

    # -------------------------------------------------------------------------
    # InspectorSection
    # -------------------------------------------------------------------------

    def applies_to(self, summary: SelectionSummary) -> bool:
        """Solo con selección (que todo sea de Música lo comprueba 'fits')."""
        return summary.scope == "selection" and not summary.is_empty

    def show_summary(self, summary: SelectionSummary) -> None:
        """Nada que hacer con el resumen: los valores llegan con 'show_data'."""

    def data_request(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> tuple[Callable[..., Any], tuple[Any, ...]] | None:
        """La carátula, junta, de las canciones seleccionadas."""
        if not ids:
            return None
        return fetch_cover_stats, (list(ids),)

    def show_data(self, result: Any) -> None:
        """Escribe las filas y pide la imagen (un 'CoverStats')."""
        stats = result if isinstance(result, CoverStats) else CoverStats()
        self._show_type(stats)
        self._show_image_row(stats)
        self._shown_id = stats.shown_id
        self._show_cover()

    def bind_thumbnails(self, provider: ThumbnailCacheProvider) -> None:
        """La caché del catálogo abierto: de ella se lee la imagen."""
        if self._loader is not None:
            self._loader.shutdown()
            self._loader.deleteLater()
        self._loader = FullImageLoader(provider, self, wanted=_WANTED)
        self._loader.loaded.connect(self._on_loaded)

    def thumbnails_changed(self, media_ids: Sequence[int] | None) -> None:
        """Se han regenerado esas miniaturas (None: se vuelven a buscar las que faltaban)."""
        if self._loader is None:
            return
        if media_ids is None:
            self._loader.forget_missing()
            if not self._cover.has_image():
                self._show_cover()  # quizá ya se ha generado
        else:
            self._loader.forget(media_ids)
            if self._shown_id is not None and self._shown_id in media_ids:
                self._show_cover()

    def shutdown(self) -> None:
        """Para la lectura de la imagen (al cerrar la aplicación)."""
        if self._loader is not None:
            self._loader.shutdown()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _show_type(self, stats: CoverStats) -> None:
        """«Tipo»: el común o «Varios»; si un archivo trae varias imágenes, se avisa."""
        value = stats.cover_type
        mixed = value.state == MIXED
        text = ""
        if mixed:
            text = MIXED_TEXT
        elif value.state == VALUE and value.value:
            text = picture_type_label(str(value.value[0]))
        tooltip = ""
        if stats.most_pictures > 1:
            if stats.count == 1:
                tooltip = (
                    f"El archivo trae {stats.most_pictures} imágenes: esta es la que hace de "
                    "carátula"
                )
            else:
                tooltip = (
                    "Alguna canción trae varias imágenes: de cada una, la que hace de carátula"
                )
        self._type.value.set_full_text(text, tooltip)
        set_secondary_text(self._type.value, mixed)

    def _show_image_row(self, stats: CoverStats) -> None:
        """«Imagen»: formato, tamaño y peso de la común; «Varios» (con el porqué al pasar
        el ratón) o «Sin carátula»."""
        value = stats.image
        tooltip = ""
        secondary = True
        if value.state == VALUE and value.value:
            text = format_cover_image(*value.value)
            secondary = False
        elif value.state == MIXED:
            text = MIXED_TEXT
            reasons = []
            if stats.covers > 1:
                reasons.append(f"{format_count(stats.covers)} carátulas distintas")
            missing = stats.count - stats.with_cover
            if missing:
                reasons.append(f"{_songs(missing)} sin carátula")
            tooltip = " y ".join(reasons)  # «2 carátulas distintas y 1 canción sin carátula»
        elif value.state == EMPTY and stats.count:
            text = NO_COVER_TEXT
        else:
            text = ""
        self._image.value.set_full_text(text, tooltip)
        set_secondary_text(self._image.value, secondary)

    def _show_cover(self) -> None:
        """La imagen de la canción que toca (o el marcador). Si hay que leerla, llega por
        'loaded' y, mientras, se queda la anterior."""
        if self._shown_id is None or self._loader is None:
            self._cover.set_image(None)
            return
        image = self._loader.image(_AUDIO, self._shown_id)
        if image is not None:
            self._cover.set_image(image)  # una nula (sin miniatura todavía): el marcador

    def _on_loaded(self, media_id: int, image: QImage) -> None:
        """Ha llegado una imagen de la caché: se pone si es la que se quiere ver."""
        if media_id == self._shown_id:
            self._cover.set_image(image)
