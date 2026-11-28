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

EDITABLES desde MUS 7.1c (plan acordado con el autor el 28/11/2026): los diez campos de
arriba son cajas ('editable_row.EditableValue'; el comentario, de tres líneas), como en
«Metadatos». Qué enseñan y qué guarda lo escrito, en 'audio_values.py': el año, como un
año («2001»); la pista y el disco con su total y dos cifras («03/12»); varios valores
con «; ». Lo escrito se aplica a las canciones PARA LAS QUE SE MOSTRARON los valores con
'edit_requested' ('media_queries.update_metadata_fields'), que atiende el controlador del
inspector: queda pendiente de escribir en los archivos. Si la caja mostraba «Varios»,
antes se pregunta (el aviso «Edición múltiple» de «Metadatos»; con «Cancelar», vuelve a
«Varios»). Lo que no vale (un año o una pista imposibles) vuelve a su valor con el aviso
junto a la caja, sin preguntar ni guardar nada. Al refrescar, lo que el usuario está
escribiendo no se pisa. Los datos técnicos, de debajo de la raya, de solo lectura.

Los valores NO están en el resumen de la selección: la sección los pide con
'data_request' ('core/catalog/audio_stats.fetch_audio_stats', en segundo plano) y los
escribe en 'show_data'. Mientras llegan, se ven los anteriores (sin parpadeo).

Las filas son siempre las mismas (las que no tienen dato quedan en blanco): así la
sección no cambia de alto al pasar de una canción a otra. «Artista del álbum», la
etiqueta más larga del inspector, ensancha la columna de etiquetas de todas las
secciones (aceptado por el autor el 26/11/2026).

1.1.1 La pista y el disco, «03/12» (sin espacios, pedido por el autor).
1.1.0 Los diez campos de la canción, editables (MUS 7.1c): cajas, también con varias
      canciones («Varios» y el aviso «Edición múltiple»). Autoprueba sin ventana.
1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 2.1).

Prueba rápida (sin ventana; necesita PySide6):
    python -m ui_helpers.inspector.audio_section
"""

__version__ = "1.1.1"
__all__ = ["AudioSection"]

# Librerías estándar
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from config.app_config import config
from config.app_constants import SETTING_CONFIRM_MULTI_EDIT
from core.catalog.audio_stats import AudioStats, fetch_audio_stats
from core.catalog.libraries import Library
from core.catalog.media_queries import update_metadata_fields
from core.catalog.selection_metadata import MIXED, VALUE, FieldValue
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.inspector.audio_values import editor_text, parse_audio_value
from ui_helpers.inspector.base_section import (
    InfoGrid,
    InfoRow,
    InspectorSection,
    set_secondary_text,
)
from ui_helpers.inspector.editable_row import EditableValue
from ui_helpers.inspector.formatting import (
    format_audio_format,
    format_audio_quality,
    format_duration,
)
from ui_helpers.inspector.metadata_fields import MIXED_TEXT
from ui_helpers.inspector.metadata_section import (
    MULTI_EDIT_ACCEPT,
    MULTI_EDIT_CANCEL,
    MULTI_EDIT_DONT_ASK,
    MULTI_EDIT_TITLE,
    multi_edit_question,
)

# Las cajas de los campos de la canción, en su orden: (clave de 'audio_stats', etiqueta)
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

# La caja de varias líneas (las demás, de una)
_MULTILINE_KEYS = frozenset({"comment"})

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

        # Los campos de la canción: cajas (ver el docstring del módulo)
        self._editors: dict[str, EditableValue] = {}
        for key, label in _FIELD_ROWS:
            multiline = key in _MULTILINE_KEYS
            editor = EditableValue(multiline=multiline)
            self._grid.add_editor_row(label, editor, align_top=multiline)
            editor.committed.connect(partial(self._on_committed, key, label, editor))
            self._editors[key] = editor
        self._grid.add_separator()
        self._duration = self._grid.add_row("Duración")
        self._format = self._grid.add_row("Formato")
        self._quality = self._grid.add_row("Calidad")
        self._tag_type = self._grid.add_row("Etiqueta")

        self._ids: tuple[int, ...] = ()  # a quién se aplica lo escrito (lo mostrado)
        self._pending_ids: tuple[int, ...] = ()  # los de la última petición de datos
        # Pregunta antes de cambiar un campo con «Varios»: (campo, canciones, valor) ->
        # sí/no. Se puede sustituir (p. ej. en las pruebas)
        self.confirm_multi_edit: Callable[[str, int, str | None], bool] = self._ask_multi_edit

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
        self._pending_ids = tuple(ids)
        return fetch_audio_stats, (list(ids),)

    def show_data(self, result: Any) -> None:
        """Escribe las cajas y las filas con los datos que llegan (un 'AudioStats').

        Una caja en la que el usuario está escribiendo para ESTAS mismas canciones no se
        toca (p. ej. un refresco por otra causa).
        """
        stats = result if isinstance(result, AudioStats) else AudioStats()
        same = self._pending_ids == self._ids
        self._ids = self._pending_ids
        for key, editor in self._editors.items():
            if same and editor.is_editing():
                continue
            text, mixed = editor_text(key, stats.value(key))
            editor.set_value(text, mixed=mixed)
        self._show_duration(stats)
        self._show_field(self._format, stats.value("format"), format_audio_format)
        self._show_quality(stats)
        self._show_field(self._tag_type, stats.value("tag_type"))

    # -------------------------------------------------------------------------
    # Edición
    # -------------------------------------------------------------------------

    def _on_committed(
        self, key: str, label: str, editor: EditableValue, value: str | None
    ) -> None:
        """El usuario ha aplicado un texto en una caja: se guarda para las mostradas.

        Lo escrito se interpreta antes ('audio_values.parse_audio_value'): si no vale, la
        caja vuelve a su valor y avisa junto a ella. Si la caja mostraba «Varios», antes
        se pregunta; con «Cancelar», vuelve a «Varios».
        """
        ids = self._ids
        if not ids:
            editor.revert()
            return
        try:
            values = parse_audio_value(key, value)
        except ValueError as error:
            editor.reject(str(error))
            return
        if editor.mixed and not self.confirm_multi_edit(label, len(ids), value):
            editor.revert()
            return
        editor.mark_applied()
        self.edit_requested.emit(update_metadata_fields, (list(ids), values))

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

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    @staticmethod
    def _show_field(
        row: InfoRow, value: FieldValue, to_text: Callable[..., str] | None = None
    ) -> None:
        """Un dato técnico: su texto, «Varios» en gris si no es el mismo en todas, o en
        blanco. Un texto de varias líneas sale en una; el emergente lo muestra entero."""
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


if __name__ == "__main__":
    # Autoprueba sin ventana (no se muestra nada ni se toca settings.json): las cajas, lo
    # que piden al catálogo, el aviso de «Varios» y lo que no vale.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.inspector.audio_section
    import sys

    from qtpy.QtWidgets import QApplication

    from core.catalog.selection_metadata import MIXED, VALUE, FieldValue
    from ui_helpers.inspector.audio_values import INVALID_TEXTS

    app = QApplication.instance() or QApplication(sys.argv)
    section = AudioSection()
    assert list(section._editors) == [key for key, _label in _FIELD_ROWS]
    assert section._editors["comment"].editor().__class__.__name__ == "_TextEditor"
    assert section._editors["title"].editor().__class__.__name__ == "_LineEditor"
    edits: list[tuple[Any, Any]] = []
    section.edit_requested.connect(lambda function, arguments: edits.append((function, arguments)))
    asked: list[tuple[str, int, str | None]] = []
    answer = [False]

    def confirm(label: str, count: int, value: str | None) -> bool:
        asked.append((label, count, value))
        return answer[0]

    section.confirm_multi_edit = confirm
    rejected: list[str] = []
    for box in section._editors.values():
        box.reject = rejected.append  # sin el aviso emergente (no hay ventana)

    # 1. Dos canciones de un álbum: lo común en las cajas, «Varios» en lo distinto
    section.data_request(None, [1, 2])  # type: ignore[arg-type]  # el resumen no se usa
    section.show_data(AudioStats(count=2, fields={
        "title": FieldValue(MIXED), "artist": FieldValue(VALUE, ("Estopa",)),
        "album": FieldValue(VALUE, ("Destrangis",)),
        "year": FieldValue(VALUE, ("2001-01-01 00:00:00", "year")),
        "track": FieldValue(MIXED), "disc": FieldValue(VALUE, (1, 2)),
        "comment": FieldValue(VALUE, ("Una\nDos",)),
    }))  # fmt: skip
    boxes = section._editors
    assert boxes["artist"].text() == "Estopa" and boxes["year"].text() == "2001"
    assert boxes["disc"].text() == "01/2" and boxes["comment"].text() == "Una\nDos"
    assert boxes["title"].mixed and boxes["track"].mixed and boxes["genre"].text() == ""

    # 2. Sin «Varios»: se aplica sin preguntar, a las dos, ya interpretado
    for key, written, expected in (
        ("album", "Destrangis (reedición)", {"album": "Destrangis (reedición)"}),
        ("genre", "Rock;Pop", {"genre": "Rock; Pop"}),
        ("year", "1999", {"content_created_at": 1999}),
        ("disc", "1/2", {"disc_number": 1, "disc_total": 2}),
        ("comment", "", {"description": None}),
    ):  # fmt: skip
        if key in _MULTILINE_KEYS:
            boxes[key].editor().setPlainText(written)
        else:
            boxes[key].editor().setText(written)
        boxes[key].editor().commit_requested.emit()
        assert edits[-1] == (update_metadata_fields, ([1, 2], expected)), (key, edits[-1])
    assert asked == [] and len(edits) == 5

    # 3. Con «Varios»: se pregunta con el nombre de la fila; «Cancelar» vuelve a «Varios»
    boxes["track"].editor().setText("3/12")
    boxes["track"].editor().commit_requested.emit()
    assert asked == [("Pista", 2, "3/12")] and len(edits) == 5 and boxes["track"].mixed
    answer[0] = True
    boxes["track"].editor().setText("3/12")
    boxes["track"].editor().commit_requested.emit()
    assert edits[-1] == (update_metadata_fields, ([1, 2], {"track_number": 3, "track_total": 12}))
    print("1-3. Cajas: lo común, «Varios», aplicar ya interpretado y el aviso de «Varios»")

    # 4. Lo que no vale: vuelve, con su aviso, sin preguntar ni guardar nada
    asked.clear()
    count = len(edits)
    for key, bad in (("year", "99"), ("track", "/12"), ("disc", "cero")):
        shown = boxes[key].text()
        boxes[key].editor().setText(bad)
        boxes[key].editor().commit_requested.emit()
        assert rejected[-1] == INVALID_TEXTS[key] and len(edits) == count and asked == [], key
        boxes[key].revert()  # lo que hace 'reject' (sustituido arriba)
        assert boxes[key].text() == shown, key
    print("4. Lo que no vale: su aviso y nada guardado")

    # 5. Otra selección: los valores nuevos y lo escrito va a las nuevas
    section.data_request(None, [7])  # type: ignore[arg-type]
    section.show_data(AudioStats(count=1, fields={"title": FieldValue(VALUE, ("Vino Tinto",))}))
    assert boxes["title"].text() == "Vino Tinto" and not boxes["title"].mixed
    assert boxes["album"].text() == ""
    boxes["title"].editor().setText("Vino tinto")
    boxes["title"].editor().commit_requested.emit()
    assert edits[-1] == (update_metadata_fields, ([7], {"title": "Vino tinto"}))
    print("5. Otra selección: lo escrito va a las que se muestran")

    section.deleteLater()
    app.processEvents()
    print("Autoprueba finalizada correctamente.")
