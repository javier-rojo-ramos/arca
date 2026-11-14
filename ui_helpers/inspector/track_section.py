"""Sección «Track» del inspector: los datos del recorrido de los tracks seleccionados.

Aparece cuando todo lo seleccionado es de la biblioteca Tracks (en cualquier módulo: en
Tracks y también en el Catálogo), debajo de «Selección»:

    ▼ TRACK
       Distancia   14,5 km
        Desnivel   ↑ 850 m   ↓ 830 m
         Altitud   1.200 – 2.100 m
        Duración   5:32:10
       Velocidad   2,6 km/h
          Puntos   2.566 · 2 segmentos · 3 waypoints
       Actividad   hiking
      Creado con   Wikiloc

Con VARIOS tracks seleccionados el título pasa a «TRACKS» y los números se juntan: se
suman la distancia, el desnivel, la duración y los puntos; la altitud es la mínima y la
máxima de todos; la actividad y el programa, el valor común o «Varios» en gris. Si algún
dato no lo tienen todos (una ruta planificada no tiene horas; un GPX puede venir sin
altitud), el texto emergente de esa fila lo dice.

Los números son los del catálogo: los calcula el extractor al leer el GPX
('track_details'; el desnivel, con su umbral contra el ruido del GPS) y aquí solo se
piden ('core/catalog/track_stats.fetch_track_stats', en segundo plano: 'data_request')
y se escriben. No se edita nada.

Las filas son siempre las mismas (las que no tienen dato quedan en blanco): así la
sección no cambia de alto al pasar de un track a otro.

1.0.0 Primera versión (14/11/2026; docs/MAPA.md, paso 4.4).
"""

__version__ = "1.0.0"
__all__ = ["TrackSection"]

# Librerías estándar
from collections.abc import Callable, Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.libraries import Library
from core.catalog.selection_summary import SelectionSummary
from core.catalog.track_stats import MIXED, TrackStats, fetch_track_stats
from ui_helpers.inspector.base_section import (
    InfoGrid,
    InfoRow,
    InspectorSection,
    set_secondary_text,
)
from ui_helpers.inspector.formatting import (
    format_altitude_range,
    format_count,
    format_distance,
    format_duration,
    format_elevation_change,
    format_speed,
)

# Texto de un dato que no es el mismo en todos los seleccionados
_MIXED_TEXT = "Varios"


def _partial_note(have: int, total: int, missing: str) -> str:
    """Aviso de que un dato no es de todos: «De 2 de los 3 tracks (...)»; vacío si lo
    tienen todos o si solo hay uno."""
    if total <= 1 or have >= total:
        return ""
    return f"De {have} de los {total} tracks (los demás {missing})"


class TrackSection(InspectorSection):
    """Sección «Track» (ver el docstring del módulo)."""

    title = "Track"
    key = "track"
    # Título con varios tracks seleccionados
    plural_title = "Tracks"
    libraries = (Library.TRACKS.value,)  # solo si todo lo seleccionado es de Tracks

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._grid = InfoGrid(self)
        layout.addWidget(self._grid)

        self._distance = self._grid.add_row("Distancia")
        self._elevation = self._grid.add_row("Desnivel")
        self._altitude = self._grid.add_row("Altitud")
        self._duration = self._grid.add_row("Duración")
        self._speed = self._grid.add_row("Velocidad")
        self._points = self._grid.add_row("Puntos")
        self._activity = self._grid.add_row("Actividad")
        self._creator = self._grid.add_row("Creado con")
        self._rows: tuple[InfoRow, ...] = (
            self._distance, self._elevation, self._altitude, self._duration,
            self._speed, self._points, self._activity, self._creator,
        )  # fmt: skip

    # -------------------------------------------------------------------------
    # InspectorSection
    # -------------------------------------------------------------------------

    def title_for(self, summary: SelectionSummary) -> str:
        """«Track» con uno seleccionado; «Tracks» con varios."""
        return self.plural_title if summary.count > 1 else self.title

    def applies_to(self, summary: SelectionSummary) -> bool:
        """Solo con selección (que todo sea de Tracks lo comprueba 'fits')."""
        return summary.scope == "selection" and not summary.is_empty

    def show_summary(self, summary: SelectionSummary) -> None:
        """Nada que hacer con el resumen: los valores llegan con 'show_data'."""

    def data_request(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> tuple[Callable[..., Any], tuple[Any, ...]] | None:
        """Los datos, juntos, de los tracks seleccionados."""
        if not ids:
            return None
        return fetch_track_stats, (list(ids),)

    def show_data(self, result: Any) -> None:
        """Escribe las filas con los datos que llegan (un 'TrackStats')."""
        stats = result if isinstance(result, TrackStats) else TrackStats()
        total = stats.count

        exact = f"{format_count(round(stats.distance_m))} m" if stats.distance_m is not None else ""
        self._distance.value.set_full_text(format_distance(stats.distance_m), exact)

        no_elevation = _partial_note(stats.with_elevation, total, "no tienen altitud")
        self._elevation.value.set_full_text(
            format_elevation_change(stats.elevation_gain_m, stats.elevation_loss_m),
            "\n".join(
                line
                for line in (
                    "Subida y bajada acumuladas (sin contar el ruido del GPS)"
                    if stats.elevation_gain_m is not None
                    else "",
                    no_elevation,
                )
                if line
            ),
        )
        self._altitude.value.set_full_text(
            format_altitude_range(stats.elevation_min_m, stats.elevation_max_m),
            "\n".join(
                line
                for line in (
                    "Altitud mínima y máxima" if stats.elevation_min_m is not None else "",
                    no_elevation,
                )
                if line
            ),
        )

        no_time = _partial_note(stats.with_duration, total, "no tienen horas")
        has_duration = stats.duration_s is not None
        self._duration.value.set_full_text(
            format_duration(stats.duration_s),
            "\n".join(
                line
                for line in (
                    "Del primer punto al último, con las paradas" if has_duration else "",
                    no_time,
                )
                if line
            ),
        )
        speed = stats.average_speed_kmh
        self._speed.value.set_full_text(
            format_speed(speed),
            "\n".join(
                line
                for line in (
                    "Velocidad media: la distancia entre la duración, con las paradas"
                    if speed is not None
                    else "",
                    no_time,
                )
                if line
            ),
        )

        self._points.value.set_full_text(self._points_text(stats))
        self._show_text(self._activity, stats.activity_type)
        self._show_text(self._creator, stats.creator_app)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    @staticmethod
    def _points_text(stats: TrackStats) -> str:
        """«2.566 · 2 segmentos · 3 waypoints» (los segmentos, solo si hay más de uno por
        track; los waypoints, solo si hay); «Ruta planificada» delante si lo es."""
        if stats.count == 0:
            return ""
        parts = [format_count(stats.point_count)]
        if stats.segment_count > stats.count:
            parts.append(f"{format_count(stats.segment_count)} segmentos")
        if stats.waypoint_count:
            word = "waypoint" if stats.waypoint_count == 1 else "waypoints"
            parts.append(f"{format_count(stats.waypoint_count)} {word}")
        if stats.planned_routes and stats.planned_routes == stats.count:
            parts.append("ruta planificada" if stats.count == 1 else "rutas planificadas")
        return " · ".join(parts)

    @staticmethod
    def _show_text(row: InfoRow, value: str | None) -> None:
        """Un texto: el valor, «Varios» en gris si no es el mismo en todos, o en blanco."""
        mixed = value == MIXED
        row.value.set_full_text(_MIXED_TEXT if mixed else (value or ""))
        set_secondary_text(row.value, mixed)
