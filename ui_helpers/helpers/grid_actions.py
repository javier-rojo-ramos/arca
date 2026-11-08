"""Atajos de teclado (estilo Lightroom) y menú contextual de la cuadrícula de miniaturas.

Todo actúa sobre la SELECCIÓN de la cuadrícula y escribe a través del modelo
('MediaGridModel.set_field'), que es quien avisa al controlador para guardar en la base
de datos. Este módulo no conoce la base de datos.

Atajos (con la cuadrícula enfocada, o con otra vista que se le dé con 'watch', como la
vista individual; sin Ctrl/Alt/Mayús):
    0-5   valoración                    P  marcar          X  rechazar        U  quitar marca
    6-9   etiqueta roja/amarilla/verde/azul (pulsarla otra vez la quita; la púrpura, por menú)
    B     selección rápida: mete la selección; si TODA ya estaba dentro, la saca (como Lightroom)
    Supr  dentro de una colección estática, quitar de la colección; en cualquier otra vista,
          "Eliminar..." (como Lightroom)

Colecciones (paso 1d): el menú contextual tiene "Añadir a la colección" (con las
colecciones estáticas del catálogo y "Nueva colección...") y, si se está viendo una
colección, "Quitar de la colección". Este módulo solo EMITE señales con los 'id' de la
selección; quien las atiende es 'controllers/collection_actions.py', que le pasa la
lista de colecciones ('set_collections') y la colección que se está viendo
('set_current_collection').

Biblioteca (paso 2b): submenú "Biblioteca" con las bibliotecas donde encaja lo
seleccionado y la actual marcada; en los vídeos sirve para clasificarlos a mano (clip
personal o película) o devolverlos a la detección automática. Solo emite
'library_change_requested'; lo guarda el controlador ('core/catalog/libraries.set_library').

Eliminar: "Eliminar..." al final del menú y la tecla Supr fuera de las colecciones
estáticas. Solo emite 'remove_requested' con los 'id'; la ventana (quitar del catálogo o
enviar a la papelera) y el trabajo los pone el controlador.

1.5.0 'watch': los atajos también con otra vista enfocada (la vista individual, paso A.1).
1.4.0 "Eliminar..." en el menú y tecla Supr fuera de las colecciones estáticas.
1.3.1 Los nombres de las bibliotecas pasan por 'qt_text' (por si alguno lleva '&', que en
      un menú de Qt marca la tecla de acceso y no se ve).
1.3.0 Submenú "Biblioteca": bibliotecas posibles, la actual marcada y corrección de vídeos.
1.2.0 Selección rápida: tecla B y "Incluir en / Eliminar de la selección rápida" en el menú.
1.1.0 Colecciones: añadir a una colección, quitar de la colección (menú y tecla Supr).
"""

__version__ = "1.5.0"
__all__ = ["GridActions"]

# Librerías de terceros (Qt)
from qtpy.QtCore import QEvent, QObject, QPoint, Qt, Signal
from qtpy.QtWidgets import QListView, QMenu, QWidget

# Módulos del proyecto
from core.catalog.color_labels import COLOR_LABELS
from core.catalog.libraries import (
    ALLOWED_MEDIA_TYPES,
    CLASSIFIABLE_MEDIA_TYPES,
    FOLDER_AUTO,
    Library,
)
from core.catalog.media_queries import FLAG_NONE, FLAG_PICKED, FLAG_REJECTED
from ui_helpers.dialogs.folder_content_dialog import FOLDER_CONTENT_TEXTS, qt_text
from ui_helpers.helpers.ui_color_labels import LABEL_TEXTS, label_icon
from ui_helpers.models.media_grid_model import QUICK_SELECTION_FIELD, MediaGridModel

# Teclas -> acción. Las de color siguen a Lightroom (6 roja, 7 amarilla, 8 verde, 9 azul)
_KEY = Qt.Key
_RATING_KEYS = {getattr(_KEY, f"Key_{n}"): n for n in range(6)}
_FLAG_KEYS = {_KEY.Key_P: FLAG_PICKED, _KEY.Key_X: FLAG_REJECTED, _KEY.Key_U: FLAG_NONE}
_COLOR_KEYS = {_KEY.Key_6: "red", _KEY.Key_7: "yellow", _KEY.Key_8: "green", _KEY.Key_9: "blue"}
# Quitar de la colección o eliminar (Retroceso: la tecla equivalente en los teclados de Mac)
_REMOVE_KEYS = {_KEY.Key_Delete, _KEY.Key_Backspace}
# Meter o sacar de la selección rápida
_QUICK_SELECTION_KEY = _KEY.Key_B


class GridActions(QObject):
    """Conecta teclado y menú contextual de la cuadrícula con el modelo.

    Signals:
        regenerate_requested(list): el usuario pidió regenerar las miniaturas de esos 'id'.
        add_to_collection_requested(int, list): añadir esos 'id' a la colección indicada.
        remove_from_collection_requested(int, list): quitar esos 'id' de la colección.
        new_collection_requested(): "Nueva colección..." (con la selección dentro).
        library_change_requested(list, object): poner esos 'id' en una biblioteca
            ('image', 'video'...) o, con None, volver a la detección automática.
        remove_requested(list): "Eliminar..." esos 'id' (quitar del catálogo o papelera).
    """

    regenerate_requested = Signal(list)
    library_change_requested = Signal(list, object)
    add_to_collection_requested = Signal(int, list)
    remove_from_collection_requested = Signal(int, list)
    new_collection_requested = Signal()
    remove_requested = Signal(list)

    def __init__(self, view: QListView, model: MediaGridModel) -> None:
        super().__init__(view)
        self._view = view
        self._model = model
        # Colecciones estáticas del catálogo: (id, nombre con sus conjuntos delante)
        self._collections: list[tuple[int, str]] = []
        # Colección que se está viendo en la cuadrícula (None si no es una colección)
        self._current_collection: int | None = None
        # Vistas cuyas teclas se atienden (la cuadrícula y las que se añadan con 'watch')
        self._watched: list[QObject] = [view]
        view.installEventFilter(self)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self._show_menu)

    def watch(self, widget: QWidget) -> None:
        """Atiende también las teclas de 'widget' (p. ej. la vista individual), que debe
        mostrar la misma selección que la cuadrícula: los atajos actúan sobre ella."""
        if widget not in self._watched:
            self._watched.append(widget)
            widget.installEventFilter(self)

    # -------------------------------------------------------------------------
    # Datos que pone el gestor de colecciones
    # -------------------------------------------------------------------------

    def set_collections(self, collections: list[tuple[int, str]]) -> None:
        """Colecciones estáticas que se ofrecen en "Añadir a la colección": (id, nombre)."""
        self._collections = list(collections)

    def set_current_collection(self, collection_id: int | None) -> None:
        """Colección estática que se está viendo (None si la cuadrícula muestra otra cosa)."""
        self._current_collection = collection_id

    # -------------------------------------------------------------------------
    # Selección
    # -------------------------------------------------------------------------

    def _selected_rows(self) -> list[int]:
        selection = self._view.selectionModel()
        if selection is None:
            return []
        return sorted({index.row() for index in selection.selectedIndexes()})

    def _toggle_color(self, rows: list[int], color: str) -> None:
        """Pone la etiqueta; si TODAS las filas ya la tenían, la quita."""
        already = all(value == color for value in self._model.field_values("color_label", rows))
        self._model.set_field("color_label", None if already else color, rows)

    def _quick_selection_state(self, rows: list[int]) -> tuple[bool, bool]:
        """(alguna fila FUERA de la selección rápida, alguna fila DENTRO)."""
        values = self._model.field_values(QUICK_SELECTION_FIELD, rows)
        return any(not value for value in values), any(bool(value) for value in values)

    def _set_quick_selection(self, rows: list[int], selected: bool) -> None:
        """Mete (True) o saca (False) esas filas de la selección rápida."""
        self._model.set_field(QUICK_SELECTION_FIELD, 1 if selected else 0, rows)

    def _toggle_quick_selection(self, rows: list[int]) -> None:
        """Tecla B: si todas ya estaban en la selección rápida, las saca; si no, las mete."""
        some_out, _some_in = self._quick_selection_state(rows)
        self._set_quick_selection(rows, some_out)

    def _remove_from_current(self, rows: list[int]) -> None:
        """Quita la selección de la colección que se está viendo."""
        if self._current_collection is not None and rows:
            self.remove_from_collection_requested.emit(
                self._current_collection, self._model.media_ids(rows)
            )

    # -------------------------------------------------------------------------
    # Teclado
    # -------------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched not in self._watched or event.type() != QEvent.Type.KeyPress:
            return False
        # Con cualquier modificador (salvo el del teclado numérico) no se interviene
        no_modifier = (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier)
        if event.modifiers() not in no_modifier:
            return False

        key = event.key()
        rows = self._selected_rows()
        if not rows:
            return False

        if key in _RATING_KEYS:
            self._model.set_field("rating", _RATING_KEYS[key], rows)
        elif key in _FLAG_KEYS:
            self._model.set_field("flag", _FLAG_KEYS[key], rows)
        elif key in _COLOR_KEYS:
            self._toggle_color(rows, _COLOR_KEYS[key])
        elif key == _QUICK_SELECTION_KEY:
            self._toggle_quick_selection(rows)
        elif key in _REMOVE_KEYS:
            # Dentro de una colección estática, Supr solo la saca de la colección (como
            # Lightroom); en cualquier otra vista, abre "Eliminar..."
            if self._current_collection is not None:
                self._remove_from_current(rows)
            else:
                self.remove_requested.emit(self._model.media_ids(rows))
        else:
            return False
        return True  # tecla consumida

    # -------------------------------------------------------------------------
    # Menú contextual
    # -------------------------------------------------------------------------

    def _show_menu(self, position: QPoint) -> None:
        index = self._view.indexAt(position)
        if not index.isValid():
            return
        # Como en un explorador de archivos: si se pulsa sobre algo que no está seleccionado,
        # pasa a ser lo único seleccionado
        if not self._view.selectionModel().isSelected(index):
            self._view.setCurrentIndex(index)
        rows = self._selected_rows()
        if not rows:
            return

        menu = QMenu(self._view)
        count = len(rows)

        menu.addAction("Marcar\tP", lambda: self._model.set_field("flag", FLAG_PICKED, rows))
        menu.addAction("Rechazar\tX", lambda: self._model.set_field("flag", FLAG_REJECTED, rows))
        menu.addAction("Quitar marca\tU", lambda: self._model.set_field("flag", FLAG_NONE, rows))
        menu.addSeparator()

        # Selección rápida: cada opción solo se activa si tiene algo que hacer (con varias
        # tarjetas, unas pueden estar dentro y otras fuera: entonces se activan las dos).
        # El atajo B va en la que haría la tecla
        some_out, some_in = self._quick_selection_state(rows)
        include = menu.addAction(
            "Incluir en la selección rápida" + ("\tB" if some_out else ""),
            lambda: self._set_quick_selection(rows, True),
        )
        include.setEnabled(some_out)
        remove = menu.addAction(
            "Eliminar de la selección rápida" + ("" if some_out else "\tB"),
            lambda: self._set_quick_selection(rows, False),
        )
        remove.setEnabled(some_in)
        menu.addSeparator()

        rating_menu = menu.addMenu("Valoración")
        for stars in range(6):
            text = "Sin valoración" if stars == 0 else "★" * stars
            rating_menu.addAction(
                f"{text}\t{stars}",
                lambda stars=stars: self._model.set_field("rating", stars, rows),
            )

        color_menu = menu.addMenu("Etiqueta de color")
        for color in COLOR_LABELS:
            color_menu.addAction(
                label_icon(color),
                LABEL_TEXTS[color],
                lambda color=color: self._model.set_field("color_label", color, rows),
            )
        color_menu.addSeparator()
        color_menu.addAction("Ninguna", lambda: self._model.set_field("color_label", None, rows))

        # --- Biblioteca (vídeos: clip personal o película) ---
        self._add_library_actions(menu, rows)

        # --- Colecciones ---
        menu.addSeparator()
        self._add_collection_actions(menu, rows)

        menu.addSeparator()
        label = "Regenerar miniatura" if count == 1 else f"Regenerar {count} miniaturas"
        menu.addAction(label, lambda: self.regenerate_requested.emit(self._model.media_ids(rows)))

        # --- Eliminar (al final, separado: es lo más delicado) ---
        menu.addSeparator()
        text = "Eliminar..." if count == 1 else f"Eliminar {count} archivos..."
        # El atajo solo vale fuera de las colecciones (dentro, Supr quita de la colección)
        shortcut = "" if self._current_collection is not None else "\tSupr"
        menu.addAction(
            f"{text}{shortcut}", lambda: self.remove_requested.emit(self._model.media_ids(rows))
        )

        menu.exec(self._view.viewport().mapToGlobal(position))

    def _add_library_actions(self, menu: QMenu, rows: list[int]) -> None:
        """Submenú "Biblioteca": a cuál pertenece lo seleccionado, con la actual marcada.

        - Opciones: las bibliotecas donde encaja TODO lo seleccionado por su tipo (una
          foto solo puede ser de «Imágenes»; un vídeo, de esa o de
          «Vídeos»). Si la selección mezcla tipos sin biblioteca en común
          (p. ej. fotos y canciones), el submenú se desactiva.
        - Marca (✓): la biblioteca actual, si todo lo seleccionado está en la misma. Sin
          marca: sin clasificar, o una mezcla.
        - Si nada de lo seleccionado puede cambiar de biblioteca (solo fotos, solo
          música...), las opciones solo informan: se ven desactivadas.
        - "Detectar automáticamente": solo si algo se clasificó a mano (para deshacerlo).
        """
        media_types = set(self._model.field_values("media_type", rows))
        libraries = set(self._model.field_values("library", rows))
        any_manual = any(self._model.field_values("library_manual", rows))
        fitting = [library for library in Library if media_types <= ALLOWED_MEDIA_TYPES[library]]

        library_menu = menu.addMenu("Biblioteca")
        if not fitting:
            library_menu.setEnabled(False)
            library_menu.setToolTip("Lo seleccionado es de bibliotecas distintas.")
            return

        current = next(iter(libraries)) if len(libraries) == 1 else None
        can_change = bool(media_types & CLASSIFIABLE_MEDIA_TYPES)
        for library in fitting:
            action = library_menu.addAction(
                qt_text(FOLDER_CONTENT_TEXTS[library][0]),
                lambda library=library: self.library_change_requested.emit(
                    self._model.media_ids(rows), library.value
                ),
            )
            action.setCheckable(True)
            action.setChecked(library == current)
            action.setEnabled(can_change)

        if any_manual:
            library_menu.addSeparator()
            library_menu.addAction(
                qt_text(FOLDER_CONTENT_TEXTS[FOLDER_AUTO][0]),
                lambda: self.library_change_requested.emit(self._model.media_ids(rows), None),
            )

    def _add_collection_actions(self, menu: QMenu, rows: list[int]) -> None:
        """Submenú "Añadir a la colección" y, si se está viendo una colección, "Quitar de ella"."""
        add_menu = menu.addMenu("Añadir a la colección")
        add_menu.addAction("Nueva colección...", self.new_collection_requested.emit)
        add_menu.addSeparator()
        targets = [(cid, name) for cid, name in self._collections if cid != self._current_collection]
        if not targets:
            empty = add_menu.addAction("(no hay otras colecciones)")
            empty.setEnabled(False)
        for collection_id, name in targets:
            add_menu.addAction(
                name,
                lambda collection_id=collection_id: self.add_to_collection_requested.emit(
                    collection_id, self._model.media_ids(rows)
                ),
            )

        if self._current_collection is not None:
            count = len(rows)
            text = "Quitar de la colección" if count == 1 else f"Quitar {count} de la colección"
            menu.addAction(f"{text}\tSupr", lambda: self._remove_from_current(rows))
