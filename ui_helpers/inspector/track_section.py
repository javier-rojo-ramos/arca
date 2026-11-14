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
       Actividad   [Senderismo        ▾]      <- desplegable: se cambia aquí
      Creado con   Wikiloc

Con VARIOS tracks seleccionados el título pasa a «TRACKS» y los números se juntan: se
suman la distancia, el desnivel, la duración y los puntos; la altitud es la mínima y la
máxima de todos; la actividad y el programa, el valor común o «Varios» en gris. La
actividad se muestra en español ('core/tracks/activities.py': el GPX y el catálogo guardan
su clave en inglés, «hiking»; una que no esté en la lista sale tal cual). Si algún
dato no lo tienen todos (una ruta planificada no tiene horas; un GPX puede venir sin
altitud), el texto emergente de esa fila lo dice.

Los números son los del catálogo: los calcula el extractor al leer el GPX
('track_details'; el desnivel, con su umbral contra el ruido del GPS) y aquí solo se
piden ('core/catalog/track_stats.fetch_track_stats', en segundo plano: 'data_request')
y se escriben.

Lo único que se EDITA es la ACTIVIDAD (paso 4.6b): un desplegable con la lista de
'core/tracks/activities.py' y «Sin actividad»; no admite escribir (decidido por el autor).
Al elegir una, se pone a todos los tracks seleccionados ('update_metadata_fields', por la
cola de cambios del inspector: 'edit_requested'); si tenían actividades distintas
(«Varios»), antes se pregunta, como en «Metadatos» (la misma opción «Preguntar antes de
cambiar varios archivos con valores distintos»). Se guarda en el catálogo y en el
'.arca.json' de la carpeta; el GPX no se toca. El desplegable no coge el teclado ni cambia
con la rueda del ratón (pasaría sin querer al desplazar el inspector).

Las filas son siempre las mismas (las que no tienen dato quedan en blanco): así la
sección no cambia de alto al pasar de un track a otro.

1.2.0 La actividad se edita: un desplegable con la lista (paso 4.6b).
1.1.0 La actividad, en español ('activity_label'; paso 4.6a).
1.0.0 Primera versión (14/11/2026; docs/MAPA.md, paso 4.4).
"""

__version__ = "1.2.0"
__all__ = ["TrackSection"]

# Librerías estándar
from collections.abc import Callable, Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt
from qtpy.QtGui import QWheelEvent
from qtpy.QtWidgets import QComboBox, QSizePolicy, QVBoxLayout, QWidget

# Módulos del proyecto
from config.app_config import config
from config.app_constants import SETTING_CONFIRM_MULTI_EDIT
from core.catalog.libraries import Library
from core.catalog.media_queries import update_metadata_fields
from core.catalog.selection_summary import SelectionSummary
from core.catalog.track_stats import MIXED, TrackStats, fetch_track_stats
from core.tracks.activities import ACTIVITIES, activity_label
from ui_helpers.helpers.ui_message import MessageBoxHelper
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
from ui_helpers.inspector.metadata_section import (
    MULTI_EDIT_ACCEPT,
    MULTI_EDIT_CANCEL,
    MULTI_EDIT_DONT_ASK,
    MULTI_EDIT_TITLE,
    multi_edit_question,
)

# Texto de un dato que no es el mismo en todos los seleccionados
_MIXED_TEXT = "Varios"
# Primera opción del desplegable de la actividad: quitarla
_NO_ACTIVITY_TEXT = "Sin actividad"
# Columna editable de la actividad ('core/userdata/editable_fields.py')
_ACTIVITY_COLUMN = "activity_type"


class _ActivityCombo(QComboBox):
    """El desplegable de la actividad: no coge el teclado (los atajos siguen en los
    archivos) y la rueda del ratón no lo cambia (desplaza el inspector, como en cualquier
    otro sitio del panel)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("combo_inspector_activity")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.addItem(_NO_ACTIVITY_TEXT, None)
        for activity in ACTIVITIES:
            self.addItem(activity.label, activity.key)

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()  # que siga hasta el área con desplazamiento

    def show_value(self, value: str | None) -> None:
        """Muestra una actividad (su clave), «Sin actividad» (None) o, si no es la misma
        en todos, «Varios» (sin ninguna opción elegida)."""
        if value == MIXED:
            self.setPlaceholderText(_MIXED_TEXT)
            self.setCurrentIndex(-1)
            return
        index = self.findData(value) if value is not None else 0
        if index < 0:
            # Una que no está en la lista (escrita a mano en un '.arca.json'): se enseña
            # tal cual, sin elegir ninguna opción
            self.setPlaceholderText(activity_label(value))
        self.setCurrentIndex(index)


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
        # La actividad se edita: un desplegable en lugar de un texto
        self._activity = _ActivityCombo()
        self._activity.setEnabled(False)  # hasta que lleguen los datos
        self._grid.add_editor_row("Actividad", self._activity)
        # 'activated': solo cuando la elige el usuario (no al ponerla desde el código)
        self._activity.activated.connect(self._on_activity_chosen)
        self._creator = self._grid.add_row("Creado con")
        self._rows: tuple[InfoRow, ...] = (
            self._distance, self._elevation, self._altitude, self._duration,
            self._speed, self._points, self._creator,
        )  # fmt: skip

        # A quién se aplica un cambio de actividad: los 'id' de los datos que se muestran
        # (los de la última petición, hasta que llegan)
        self._ids: tuple[int, ...] = ()
        self._pending_ids: tuple[int, ...] = ()
        # La actividad que se muestra (clave, None o MIXED): para deshacer en el
        # desplegable una elección que el usuario cancela
        self._shown_activity: str | None = None
        # Pregunta antes de cambiar varios con valores distintos (se sustituye en las pruebas)
        self.confirm_multi_edit = self._ask_multi_edit

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
        self._pending_ids = tuple(ids)
        return fetch_track_stats, (list(ids),)

    def show_data(self, result: Any) -> None:
        """Escribe las filas con los datos que llegan (un 'TrackStats')."""
        stats = result if isinstance(result, TrackStats) else TrackStats()
        total = stats.count
        self._ids = self._pending_ids

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
        self._shown_activity = stats.activity_type
        self._activity.show_value(stats.activity_type)
        self._activity.setEnabled(total > 0)
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

    def _on_activity_chosen(self, index: int) -> None:
        """El usuario ha elegido una actividad en el desplegable: se pone a los tracks
        mostrados. Si tenían varias distintas, antes se pregunta; con «Cancelar», el
        desplegable vuelve a como estaba."""
        ids = self._ids
        key = self._activity.itemData(index)
        if not ids or key == self._shown_activity:
            return
        label = self._activity.itemText(index) if key is not None else None
        if self._shown_activity == MIXED and not self.confirm_multi_edit("Actividad", len(ids), label):
            self._activity.show_value(self._shown_activity)
            return
        self._shown_activity = key
        self.edit_requested.emit(update_metadata_fields, (list(ids), {_ACTIVITY_COLUMN: key}))

    def _ask_multi_edit(self, label: str, count: int, value: str | None) -> bool:
        """Aviso «Edición múltiple», el mismo de «Metadatos» (salvo que se pidiera no
        volver a mostrarlo)."""
        if config.get(SETTING_CONFIRM_MULTI_EDIT, True) is False:
            return True
        clicked, dont_ask = MessageBoxHelper(self).question_with_checkbox(
            multi_edit_question(label, count, value),
            MULTI_EDIT_DONT_ASK,
            title=MULTI_EDIT_TITLE,
            buttons=[MULTI_EDIT_ACCEPT, MULTI_EDIT_CANCEL],
        )
        accepted = clicked == MULTI_EDIT_ACCEPT
        # «No volver a mostrar» solo cuenta si se aceptó (con «Cancelar» no se guarda)
        if accepted and dont_ask:
            config.set(SETTING_CONFIRM_MULTI_EDIT, False)
        return accepted

    @staticmethod
    def _show_text(row: InfoRow, value: str | None) -> None:
        """Un texto: el valor, «Varios» en gris si no es el mismo en todos, o en blanco."""
        mixed = value == MIXED
        row.value.set_full_text(_MIXED_TEXT if mixed else (value or ""))
        set_secondary_text(row.value, mixed)
