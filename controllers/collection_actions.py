"""Gestión de las colecciones del usuario desde la interfaz (crear, renombrar, añadir...).

Está aparte de 'main_window_controller.py' para no seguir engordándolo: reúne en un solo
sitio todo lo que une la barra lateral ('CatalogSidebar'), el menú de la cuadrícula
('GridActions') y la base de datos ('core/catalog/user_collections.py'):

    Barra lateral                          Cuadrícula (menú y teclado)
    ├── "+" Crear conjunto / colección /   ├── Añadir a la colección ▸ (o Nueva colección...)
    │       colección inteligente          └── Quitar de la colección (o tecla Supr)
    ├── menú: Editar (inteligente) / Renombrar / Eliminar
    └── soltar tarjetas sobre una colección
                         │
                         ▼
               CollectionActions  ──►  user_collections.py (en segundo plano)

El controlador principal solo tiene que:
    - crearlo (cuando ya existen la cuadrícula y sus atajos),
    - llamar a 'attach(db, carpeta)' al abrir un catálogo y a 'detach()' al cerrarlo,
    - llamar a 'refresh()' cuando haya que releer el árbol (lo hace al actualizar la barra).

Todas las operaciones con la base de datos van en segundo plano ('execute_async'). Los
errores previstos (nombre repetido, colección que ya no existe...) llegan como
'CollectionError' y se muestran tal cual: su mensaje ya está pensado para el usuario.

1.2.0 El editor de reglas sugiere los nombres de las palabras clave: se leen en segundo
      plano antes de abrirlo ('_with_keyword_names'; paso K4c).
1.1.0 Colecciones inteligentes: crear y editar con 'SmartCollectionDialog' (con el número
      de elementos que coinciden, contado en segundo plano).
"""

__version__ = "1.2.0"
__all__ = ["CollectionActions"]

# Librerías estándar
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QInputDialog, QLineEdit, QListView, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from core.catalog.grid_source import GridSource, SourceKind
from core.catalog.keywords import fetch_keyword_names
from core.catalog.media_queries import count_grid_items
from core.catalog.smart_rules import RuleSet
from core.catalog.user_collections import (
    KIND_SET,
    KIND_SMART,
    KIND_STATIC,
    MAX_NAME_LENGTH,
    CollectionError,
    CollectionNode,
    add_to_collection,
    create_collection,
    delete_collection,
    fetch_collection_tree,
    iter_nodes,
    remove_from_collection,
    rename_collection,
    update_smart_collection,
)
from ui_helpers.dialogs.collection_dialog import CollectionDialog
from ui_helpers.dialogs.smart_collection_dialog import SmartCollectionDialog
from ui_helpers.helpers.grid_actions import GridActions
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.helpers.ui_status import message_bar
from ui_helpers.models.media_grid_model import MediaGridModel
from ui_helpers.models.media_mime import MediaDrag
from ui_helpers.sidebars.catalog_sidebar import CatalogSidebar


class CollectionActions(QObject):
    """Une la barra lateral y la cuadrícula con las colecciones del catálogo abierto."""

    def __init__(
        self,
        window: QWidget,
        sidebar: CatalogSidebar,
        grid_view: QListView,
        grid_model: MediaGridModel,
        grid_actions: GridActions,
        message_box: MessageBoxHelper,
    ) -> None:
        """Conecta las señales (todavía sin catálogo: ver 'attach').

        Args:
            window: Ventana principal (padre de los diálogos y dueña de la barra de estado).
            sidebar: Barra lateral del catálogo.
            grid_view: Vista de la cuadrícula (para saber qué hay seleccionado).
            grid_model: Modelo de la cuadrícula (para recargarla si cambia lo que se ve).
            grid_actions: Atajos y menú de la cuadrícula.
            message_box: Ayudante de mensajes de la ventana.
        """
        super().__init__(window)
        self._window = window
        self._sidebar = sidebar
        self._grid_view = grid_view
        self._grid_model = grid_model
        self._grid_actions = grid_actions
        self._message_box = message_box

        self._db: Any = None
        self._catalog_key = ""  # carpeta del catálogo, en texto (para validar lo arrastrado)
        self._tree: tuple[CollectionNode, ...] = ()
        # Colección (id) que se seleccionará en cuanto se relea el árbol (p. ej. la recién creada)
        self._select_after_refresh: int | None = None

        # Barra lateral
        sidebar.create_collection_requested.connect(self._on_create_requested)
        sidebar.rename_collection_requested.connect(self._on_rename_requested)
        sidebar.delete_collection_requested.connect(self._on_delete_requested)
        sidebar.media_dropped.connect(self._on_media_dropped)
        sidebar.edit_smart_collection_requested.connect(self._on_edit_smart_requested)
        sidebar.source_selected.connect(self._on_source_selected)
        # Cuadrícula
        grid_actions.add_to_collection_requested.connect(self._add_items)
        grid_actions.remove_from_collection_requested.connect(self._remove_items)
        grid_actions.new_collection_requested.connect(
            lambda: self._on_create_requested(KIND_STATIC, None)
        )

    # -------------------------------------------------------------------------
    # Catálogo abierto
    # -------------------------------------------------------------------------

    def attach(self, db: Any, catalog_dir: Path) -> None:
        """Empieza a trabajar con un catálogo recién abierto."""
        self._db = db
        self._catalog_key = str(catalog_dir)
        self.refresh()

    def detach(self) -> None:
        """El catálogo se ha cerrado: se olvida todo lo suyo."""
        self._db = None
        self._catalog_key = ""
        self._tree = ()
        self._select_after_refresh = None
        self._grid_actions.set_collections([])
        self._grid_actions.set_current_collection(None)

    def refresh(self) -> None:
        """Relee en segundo plano el árbol de colecciones (con sus contadores)."""
        if self._db is None:
            return
        self._db.execute_async(
            fetch_collection_tree,
            on_result=self._on_tree,
            on_error=lambda error: logger.warning(f"No se pudieron leer las colecciones: {error}"),
        )

    def _on_tree(self, tree: tuple[CollectionNode, ...]) -> None:
        """Pone el árbol en la barra lateral y la lista de colecciones en el menú de la cuadrícula."""
        if self._db is None:
            return  # el catálogo se cerró mientras se leía
        self._tree = tree
        self._sidebar.set_collection_tree(tree)
        self._grid_actions.set_collections(
            [(node.id, node.path_name) for node in iter_nodes(tree) if node.kind == KIND_STATIC]
        )
        if self._select_after_refresh is not None:
            collection_id, self._select_after_refresh = self._select_after_refresh, None
            self._sidebar.select_collection(collection_id, emit=True)

    def _on_source_selected(self, source: GridSource) -> None:
        """La cuadrícula muestra otra cosa: el menú y la tecla Supr lo tienen que saber."""
        is_collection = source.kind == SourceKind.COLLECTION
        self._grid_actions.set_current_collection(source.collection_id if is_collection else None)

    # -------------------------------------------------------------------------
    # Crear, renombrar, eliminar
    # -------------------------------------------------------------------------

    def _on_create_requested(self, kind: str, parent_id: int | None) -> None:
        """Pide nombre y ubicación, y crea la colección (con la selección, si se quiere)."""
        if self._db is None:
            self._message_box.warning("Primero hay que crear o abrir un catálogo.")
            return
        if kind == KIND_SMART:
            self._create_smart(parent_id)
            return
        selected = self._selected_media_ids()
        sets = self._sets()
        choice = CollectionDialog.ask(
            self._window,
            kind=kind,
            sets=sets,
            parent_id=parent_id,
            selection_count=len(selected),
        )
        if choice is None:
            return
        media_ids = selected if choice.include_selection else []
        self._run(
            create_collection,
            choice.name,
            kind,
            choice.parent_id,
            media_ids,
            on_result=lambda new_id: self._on_created(new_id, kind, choice.name),
        )

    def _on_created(self, new_id: int, kind: str, name: str) -> None:
        """Colección creada: se relee el árbol y, si es una colección, se muestra."""
        what = {
            KIND_SET: "Conjunto creado",
            KIND_SMART: "Colección inteligente creada",
        }.get(kind, "Colección creada")
        message_bar(self._window, f"{what}: «{name}»", AppIcons.CHECK_CIRCLE)
        if kind != KIND_SET:
            self._select_after_refresh = new_id
        self.refresh()

    # -------------------------------------------------------------------------
    # Colecciones inteligentes
    # -------------------------------------------------------------------------

    def _with_keyword_names(self, then: Callable[[list[str]], None]) -> None:
        """Lee en segundo plano los nombres de las palabras clave (para el autocompletado
        del editor de reglas) y llama a 'then' con ellos; si falla, con ninguno."""
        if self._db is None:
            then([])
            return

        def failed(error: Exception) -> None:
            logger.warning(f"No se pudieron leer las palabras clave: {error}")
            then([])

        self._db.execute_async(fetch_keyword_names, on_result=then, on_error=failed)

    def _create_smart(self, parent_id: int | None) -> None:
        """Pide nombre, conjunto y reglas, y crea la colección inteligente."""
        self._with_keyword_names(lambda names: self._create_smart_with(parent_id, names))

    def _create_smart_with(self, parent_id: int | None, keyword_names: list[str]) -> None:
        """Abre el editor (ya con los nombres de las palabras) y crea la colección."""
        choice = SmartCollectionDialog.ask(
            self._window,
            sets=self._sets(),
            parent_id=parent_id,
            counter=self._count_rules,
            keyword_names=keyword_names,
        )
        if choice is None:
            return
        self._run(
            # 'rules' va por nombre: 'partial' lo añade a la llamada (conn, nombre, tipo...)
            partial(create_collection, rules=choice.rules),
            choice.name,
            KIND_SMART,
            choice.parent_id,
            (),
            on_result=lambda new_id: self._on_created(new_id, KIND_SMART, choice.name),
        )

    def _on_edit_smart_requested(self, collection_id: int) -> None:
        """Abre las reglas de una colección inteligente para cambiarlas."""
        if self._db is None:
            return
        node = self._node(collection_id)
        if node is None or node.kind != KIND_SMART:
            return
        note = ""
        if node.rules is None:
            # Reglas ilegibles (p. ej. de una versión más nueva): se empieza de cero
            note = (
                f"No se pudieron leer las reglas guardadas ({node.rules_error}). "
                "Al guardar se sustituirán por las que pongas aquí."
            )
        self._with_keyword_names(
            lambda names: self._edit_smart_with(collection_id, node, note, names)
        )

    def _edit_smart_with(self, collection_id: int, node: Any, note: str, keyword_names: list[str]) -> None:
        """Abre el editor con las reglas guardadas (y los nombres de las palabras) y guarda."""
        choice = SmartCollectionDialog.ask(
            self._window,
            sets=self._sets(),
            parent_id=node.parent_id,
            name=node.name,
            rules=node.rules,
            editing=True,
            counter=self._count_rules,
            note=note,
            keyword_names=keyword_names,
        )
        if choice is None:
            return
        self._run(
            update_smart_collection,
            collection_id,
            choice.name,
            choice.rules,
            choice.parent_id,
            on_result=lambda _none: self._on_smart_updated(choice.name),
        )

    def _on_smart_updated(self, name: str) -> None:
        """Guardada: se relee el árbol (si se está viendo, la barra recarga la cuadrícula)."""
        message_bar(self._window, f"Colección inteligente guardada: «{name}»", AppIcons.CHECK_CIRCLE)
        self.refresh()

    def _count_rules(self, rule_set: RuleSet, callback: Callable[[int | None], None]) -> None:
        """Cuenta en segundo plano los elementos que cumplen unas reglas (para el editor)."""
        if self._db is None:
            callback(None)
            return
        source = GridSource(kind=SourceKind.SMART, rules=rule_set)
        self._db.execute_async(
            count_grid_items,
            [source],
            on_result=lambda counts: callback(counts.get(source)),
            on_error=lambda error: (logger.warning(f"No se pudo contar: {error}"), callback(None)),
        )

    def _on_rename_requested(self, collection_id: int, current_name: str) -> None:
        """Pide el nombre nuevo y renombra."""
        name, accepted = QInputDialog.getText(
            self._window,
            "Renombrar",
            "Nombre nuevo:",
            QLineEdit.EchoMode.Normal,
            current_name,
        )
        name = " ".join(name.split())
        if not accepted or not name or name == current_name:
            return
        if len(name) > MAX_NAME_LENGTH:
            self._message_box.warning(f"El nombre es demasiado largo (máximo {MAX_NAME_LENGTH} caracteres).")
            return
        self._run(rename_collection, collection_id, name, on_result=lambda _none: self.refresh())

    def _on_delete_requested(self, collection_id: int, name: str, kind: str) -> None:
        """Pide confirmación y elimina (un conjunto, con todo lo que contiene)."""
        if kind == KIND_SET:
            text = (
                f"¿Eliminar el conjunto «{name}» y TODAS las colecciones que contiene?\n\n"
                "Los archivos no se tocan: solo dejan de estar en esas colecciones."
            )
        elif kind == KIND_SMART:
            text = f"¿Eliminar la colección inteligente «{name}»?\n\nLos archivos no se tocan."
        else:
            text = (
                f"¿Eliminar la colección «{name}»?\n\n"
                "Los archivos no se tocan: solo dejan de estar en la colección."
            )
        answer = self._message_box.question(text, buttons=["Eliminar", "Cancelar"])
        if answer != "Eliminar":
            return
        self._run(
            delete_collection,
            collection_id,
            on_result=lambda _count: self._on_deleted(name),
        )

    def _on_deleted(self, name: str) -> None:
        """Eliminada: se relee el árbol (si se estaba viendo, la barra vuelve a "Todos")."""
        message_bar(self._window, f"Eliminada: «{name}»", AppIcons.CHECK_CIRCLE)
        self.refresh()

    # -------------------------------------------------------------------------
    # Archivos de una colección
    # -------------------------------------------------------------------------

    def _on_media_dropped(self, collection_id: int, drag: MediaDrag) -> None:
        """Se han soltado tarjetas sobre una colección de la barra lateral."""
        if drag.catalog != self._catalog_key:
            # P. ej. tarjetas arrastradas desde otra ventana con otro catálogo
            self._message_box.warning("Esos elementos son de otro catálogo: no se pueden añadir.")
            return
        self._add_items(collection_id, list(drag.ids))

    def _add_items(self, collection_id: int, media_ids: list[int]) -> None:
        """Añade archivos a una colección (desde la cuadrícula o soltándolos)."""
        if self._db is None or not media_ids:
            return
        self._run(
            add_to_collection,
            collection_id,
            media_ids,
            on_result=lambda added: self._on_items_added(collection_id, added, len(media_ids)),
        )

    def _on_items_added(self, collection_id: int, added: int, requested: int) -> None:
        """Informa de lo añadido y actualiza contadores (y la cuadrícula si se está viendo)."""
        name = self._name_of(collection_id)
        if added == 0:
            text = f"Ya estaban todos en «{name}»."
        elif added < requested:
            text = f"Añadidos {added} a «{name}» (los demás ya estaban)."
        else:
            text = f"Añadidos {added} a «{name}»."
        message_bar(self._window, text, AppIcons.CHECK_CIRCLE)
        self._after_items_changed(collection_id)

    def _remove_items(self, collection_id: int, media_ids: list[int]) -> None:
        """Quita archivos de la colección que se está viendo (menú o tecla Supr)."""
        if self._db is None or not media_ids:
            return
        self._run(
            remove_from_collection,
            collection_id,
            media_ids,
            on_result=lambda removed: self._on_items_removed(collection_id, removed),
        )

    def _on_items_removed(self, collection_id: int, removed: int) -> None:
        message_bar(
            self._window,
            f"Quitados {removed} de «{self._name_of(collection_id)}».",
            AppIcons.CHECK_CIRCLE,
        )
        self._after_items_changed(collection_id)

    def _after_items_changed(self, collection_id: int) -> None:
        """Tras añadir o quitar: si se está viendo esa colección se recarga la cuadrícula
        (al recargar, la barra lateral se actualiza sola); si no, solo los contadores."""
        source = self._grid_model.source
        if source.kind == SourceKind.COLLECTION and source.collection_id == collection_id:
            self._grid_model.reload()
        else:
            self.refresh()

    # -------------------------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------------------------

    def _selected_media_ids(self) -> list[int]:
        """'id' de las tarjetas seleccionadas en la cuadrícula, en su orden."""
        selection = self._grid_view.selectionModel()
        if selection is None:
            return []
        rows = sorted({index.row() for index in selection.selectedIndexes()})
        return self._grid_model.media_ids(rows)

    def _name_of(self, collection_id: int) -> str:
        """Nombre de una colección (según el último árbol leído)."""
        node = self._node(collection_id)
        return node.name if node is not None else "la colección"

    def _node(self, collection_id: int) -> CollectionNode | None:
        """Nodo de una colección en el último árbol leído (None si no está)."""
        return next((node for node in iter_nodes(self._tree) if node.id == collection_id), None)

    def _sets(self) -> list[tuple[int, str]]:
        """Conjuntos donde se puede crear algo: (id, nombre con sus conjuntos delante)."""
        return [(node.id, node.path_name) for node in iter_nodes(self._tree) if node.kind == KIND_SET]

    def _run(self, func: Callable[..., Any], *args: Any, on_result: Callable[[Any], None]) -> None:
        """Ejecuta una operación de 'user_collections' en segundo plano.

        Los 'CollectionError' (previstos) se muestran como aviso; cualquier otro error,
        como error grave.
        """
        if self._db is None:
            return
        self._db.execute_async(func, *args, on_result=on_result, on_error=self._on_error)

    def _on_error(self, error: Exception) -> None:
        if isinstance(error, CollectionError):
            self._message_box.warning(str(error))
        else:
            logger.error(f"Error en una operación con colecciones: {error}")
            self._message_box.critical(f"No se pudo completar la operación.\n\nDetalle: {error}")
        self.refresh()  # por si el árbol que se muestra ya no es el real
