"""Sección «Audio» del inspector: las etiquetas y los datos técnicos de las canciones.

Aparece cuando hay algo seleccionado y TODO es de la biblioteca Música (en cualquier
módulo: en Audio y también en el Catálogo), detrás de las secciones comunes. La forma, la
acordada con el autor el 25/11/2026 tras ver una muestra (docs/MOD_MUSICA.md §7.1): una
fila por campo y, debajo de una raya, los datos técnicos:

    ▼ AUDIO
       Título              Vino Tinto
       Artista             Estopa
       Álbum               Destrangis
       Año                 2001
       Pista               1 / 12
       Disco
       Género              Pop Folk
       Artista del álbum
       Compositor
       Comentario
       ────────────────────────────────────────
       Duración            3:18
       Formato             AAC LC
       Calidad             138 kbps · 44,1 kHz · Estéreo
       Etiqueta            MP4

Con VARIAS canciones, cada campo enseña el valor común, «Varios» en gris (distintos, o
unas con valor y otras sin él) o nada; la duración se suma (el texto emergente lo dice) y
la tasa de bits de «Calidad» es el intervalo («239 – 277 kbps»); de lo demás de «Calidad»
(el modo, la frecuencia, los bits y los canales) solo sale lo que tienen todas.

De SOLO LECTURA (`MUS 2.1`): los diez campos de arriba serán editables con `MUS 7`, como
los de «Metadatos»; los técnicos, nunca. El «Comentario», mientras tanto, en una línea
(recortada con «…»; entero en el texto emergente); su caja de tres líneas, con la
edición.

Los valores NO están en el resumen de la selección: la sección los pide con
'data_request' ('core/catalog/audio_stats.fetch_audio_stats', en segundo plano) y los
escribe en 'show_data'. Mientras llegan, se ven los anteriores (sin parpadeo).

Las filas son siempre las mismas (las que no tienen dato quedan en blanco): así la
sección no cambia de alto al pasar de una canción a otra. «Artista del álbum», la
etiqueta más larga del inspector, ensancha la columna de etiquetas de todas las
secciones (aceptado por el autor el 26/11/2026).

1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 2.1).
"""

__version__ = "1.0.0"
__all__ = ["AudioSection"]

# Librerías estándar
from collections.abc import Callable, Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.audio_stats import AudioStats, fetch_audio_stats
from core.catalog.libraries import Library
from core.catalog.selection_metadata import MIXED, VALUE, FieldValue
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.inspector.base_section import (
    InfoGrid,
    InfoRow,
    InspectorSection,
    set_secondary_text,
)
from ui_helpers.inspector.formatting import (
    format_audio_format,
    format_audio_quality,
    format_date,
    format_duration,
    format_part,
)
from ui_helpers.inspector.metadata_fields import MIXED_TEXT

# Las filas de los campos de la canción, en su orden: (clave de 'audio_stats', etiqueta)
_FIELD_ROWS: tuple[tuple[str, str], ...] = (
    ("title", "Título"),
    ("artist", "Artista"),
    ("album", "Álbum"),
    ("year", "Año"),
    ("track", "Pista"),
    ("disc", "Disco"),
    ("genre", "Género"),
    ("album_artist", "Artista del álbum"),
    ("composer", "Compositor"),
    ("comment", "Comentario"),
)

# Cómo se escribe el valor de cada campo (la tupla de sus columnas); los que no están, el
# texto de su única columna
_FIELD_TEXTS: dict[str, Callable[..., str]] = {
    "year": lambda text, precision: format_date(text, precision),
    "track": format_part,
    "disc": format_part,
    # El comentario, en una línea: los saltos, como espacios (entero, en el emergente)
    "comment": lambda text: " ".join(str(text or "").split()),
}

# Partes de «Calidad» que se comparan entre las canciones (la tasa va aparte: intervalo)
_QUALITY_KEYS = ("bitrate_mode", "sample_rate", "bit_depth", "channels")


def _single(value: FieldValue) -> Any:
    """La única columna de un campo con valor común; None si no lo tienen todas igual."""
    return value.value[0] if value.state == VALUE and value.value else None


class AudioSection(InspectorSection):
    """Sección «Audio» (ver el docstring del módulo)."""

    title = "Audio"
    key = "audio"
    libraries = (Library.AUDIO.value,)  # solo si todo lo seleccionado es de Música

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._grid = InfoGrid(self)
        layout.addWidget(self._grid)

        self._field_rows: dict[str, InfoRow] = {
            key: self._grid.add_row(label) for key, label in _FIELD_ROWS
        }
        self._grid.add_separator()
        self._duration = self._grid.add_row("Duración")
        self._format = self._grid.add_row("Formato")
        self._quality = self._grid.add_row("Calidad")
        self._tag_type = self._grid.add_row("Etiqueta")

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
        """Los datos, juntos, de las canciones seleccionadas."""
        if not ids:
            return None
        return fetch_audio_stats, (list(ids),)

    def show_data(self, result: Any) -> None:
        """Escribe las filas con los datos que llegan (un 'AudioStats')."""
        stats = result if isinstance(result, AudioStats) else AudioStats()
        for key, row in self._field_rows.items():
            self._show_field(row, stats.value(key), _FIELD_TEXTS.get(key))
        self._show_duration(stats)
        self._show_field(self._format, stats.value("format"), format_audio_format)
        self._show_quality(stats)
        self._show_field(self._tag_type, stats.value("tag_type"))

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    @staticmethod
    def _show_field(
        row: InfoRow, value: FieldValue, to_text: Callable[..., str] | None = None
    ) -> None:
        """Un campo: su texto, «Varios» en gris si no es el mismo en todas, o en blanco.

        Un texto de varias líneas (el comentario) sale en una; el emergente lo muestra
        entero, con sus saltos de línea."""
        mixed = value.state == MIXED
        text, tooltip = "", ""
        if mixed:
            text = MIXED_TEXT
        elif value.state == VALUE and value.value is not None:
            if to_text is not None:
                text = to_text(*value.value)
            else:
                text = str(value.value[0] or "")
            original = value.value[0]
            if isinstance(original, str) and "\n" in original.strip():
                tooltip = original.strip()
        row.value.set_full_text(text, tooltip)
        set_secondary_text(row.value, mixed)

    def _show_duration(self, stats: AudioStats) -> None:
        """La duración (con varias canciones, la suma; el emergente lo dice)."""
        tooltip = ""
        if stats.count > 1 and stats.duration_s is not None:
            if stats.with_duration < stats.count:
                tooltip = (
                    f"Suma de {stats.with_duration} de las {stats.count} canciones "
                    "(las demás no tienen duración)"
                )
            else:
                tooltip = f"Suma de las {stats.count} canciones"
        self._duration.value.set_full_text(format_duration(stats.duration_s), tooltip)
        set_secondary_text(self._duration.value, False)

    def _show_quality(self, stats: AudioStats) -> None:
        """«Calidad»: la tasa (o su intervalo) y lo que tienen igual todas; si no queda
        nada y las canciones no coinciden, «Varios»."""
        parts = [_single(stats.value(key)) for key in _QUALITY_KEYS]
        mode, sample_rate, bit_depth, channels = parts
        text = format_audio_quality(
            mode, stats.bitrate_min, stats.bitrate_max, sample_rate, bit_depth, channels
        )
        mixed = not text and any(stats.value(key).state == MIXED for key in _QUALITY_KEYS)
        self._quality.value.set_full_text(MIXED_TEXT if mixed else text)
        set_secondary_text(self._quality.value, mixed)
