"""Menú contextual de los árboles de palabras clave: crear, renombrar, mover, borrar (K4c-2).

    ┌──────────────────────────────────────────────┐
    │ Crear palabra clave dentro de «Familia»…     │
    │ Crear palabra clave en el primer nivel…      │
    ├──────────────────────────────────────────────┤
    │ Renombrar «Familia»…                         │
    │ Mover «Familia» a…                           │
    │ Marcar como revisada        (solo si lo está)│
    ├──────────────────────────────────────────────┤
    │ Borrar «Familia»…                            │
    ├──────────────────────────────────────────────┤
    │ Purgar palabras clave no usadas…             │
    └──────────────────────────────────────────────┘

Lo usan los dos árboles del módulo Imagen: la «Lista de palabras clave» de la barra
izquierda ('ImageSidebar') y la del inspector ('KeywordChecklist'). Pulsando en un hueco
del árbol (sin palabra), solo «Crear en el primer nivel» y «Purgar».

Aquí solo se pregunta (el nombre, el destino, la confirmación); la base de datos NO se
toca: 'ask_keyword_operation' devuelve (función, argumentos) de 'core/catalog/keywords.py'
y el árbol la emite ('operation_requested'). La ejecuta el controlador del inspector en su
cola de cambios (como el resto de cambios del usuario), que avisa si falla (p. ej. «Ya hay
una palabra clave "Ana" dentro de "Familia"») y refresca los árboles al terminar.

Los archivos que tienen una palabra renombrada, movida o borrada (o alguna de sus hijas)
quedan pendientes de escribir: su jerarquía en el XMP ha cambiado.

Prueba rápida de la lógica (sin Qt):
    python -m ui_helpers.helpers.keyword_menu
"""

__version__ = "1.0.0"
__all__ = ["ROOT_LABEL", "ask_keyword_operation", "move_targets", "tree_index"]

# Librerías estándar
from collections.abc import Callable, Iterable
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QPoint
from qtpy.QtWidgets import QInputDialog, QLineEdit, QMenu, QWidget

# Módulos del proyecto
from core.catalog.catalog_schema import fold_text
from core.catalog.keywords import (
    PATH_SEPARATOR,
    KeywordTreeNode,
    create_keyword,
    delete_keyword,
    mark_keyword_reviewed,
    move_keyword,
    purge_unused_keywords,
    rename_keyword,
)
from ui_helpers.helpers.ui_message import MessageBoxHelper

# Destino «primer nivel» en la lista de «Mover a…»
ROOT_LABEL = "(Primer nivel)"

# (función de 'keywords', argumentos): lo que se pide al controlador
Operation = tuple[Callable[..., Any], tuple[Any, ...]]


def tree_index(nodes: Iterable[KeywordTreeNode]) -> dict[int, tuple[KeywordTreeNode, tuple[str, ...], int | None]]:
    """{id: (nodo, ruta, id del padre)} de todo el árbol."""
    index: dict[int, tuple[KeywordTreeNode, tuple[str, ...], int | None]] = {}

    def visit(node: KeywordTreeNode, parents: tuple[str, ...], parent_id: int | None) -> None:
        path = (*parents, node.name)
        index[node.id] = (node, path, parent_id)
        for child in node.children:
            visit(child, path, node.id)

    for node in nodes:
        visit(node, (), None)
    return index


def _subtree_ids(node: KeywordTreeNode) -> set[int]:
    found = {node.id}
    for child in node.children:
        found |= _subtree_ids(child)
    return found


def move_targets(nodes: Iterable[KeywordTreeNode], keyword_id: int) -> list[tuple[str, int | None]]:
    """Destinos posibles para mover una palabra: el primer nivel y todas las palabras que
    no son ella ni sus hijas, por su ruta («Familia > Abuelos») y en orden alfabético."""
    index = tree_index(nodes)
    excluded = _subtree_ids(index[keyword_id][0]) if keyword_id in index else {keyword_id}
    targets = [
        (f" {PATH_SEPARATOR} ".join(path), node_id)
        for node_id, (_node, path, _parent) in index.items()
        if node_id not in excluded
    ]
    targets.sort(key=lambda item: fold_text(item[0]) or "")
    return [(ROOT_LABEL, None), *targets]


def _count_descendants(node: KeywordTreeNode) -> int:
    return sum(1 + _count_descendants(child) for child in node.children)


def _delete_question(node: KeywordTreeNode) -> str:
    """Texto de la confirmación de borrar (con sus hijas y sus fotos de Imagen)."""
    children = _count_descendants(node)
    what = f"«{node.name}»"
    if children:
        what += f" y {'su palabra hija' if children == 1 else f'sus {children} palabras hijas'}"
    text = f"¿Borrar {what}?"
    if node.count:
        photos = "1 imagen la tiene" if node.count == 1 else f"{node.count} imágenes las tienen"
        text += (
            f"\n\n{photos} (o alguna de sus hijas): se les quitará, también en sus archivos "
            "si está activado «Guardar en los archivos»."
        )
    return text + "\n\nNo se puede deshacer."


def _ask_name(parent: QWidget, title: str, label: str, text: str = "") -> str | None:
    """Pide un nombre; None si se cancela o se deja igual de vacío."""
    name, accepted = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Normal, text)
    name = " ".join(name.split())
    return name if accepted and name else None


def ask_keyword_operation(
    parent: QWidget,
    tree: Iterable[KeywordTreeNode],
    keyword_id: int | None,
    global_pos: QPoint,
) -> Operation | None:
    """Muestra el menú en 'global_pos', pregunta lo necesario y devuelve la operación.

    Args:
        parent: Widget del árbol (padre del menú y de las ventanas).
        tree: El árbol entero (para nombres, hijas y destinos de «Mover a…»).
        keyword_id: Palabra pulsada, o None si se pulsó en un hueco.
        global_pos: Dónde abrir el menú (coordenadas de pantalla).

    Returns:
        (función, argumentos) para 'execute_async', o None si se cancela.
    """
    nodes = tuple(tree)
    index = tree_index(nodes)
    entry = index.get(keyword_id) if keyword_id is not None else None

    menu = QMenu(parent)
    actions: dict[Any, str] = {}

    def add(text: str, key: str) -> None:
        actions[menu.addAction(text)] = key

    if entry is not None:
        node = entry[0]
        add(f"Crear palabra clave dentro de «{node.name}»…", "create_child")
    add("Crear palabra clave en el primer nivel…", "create_root")
    if entry is not None:
        menu.addSeparator()
        add(f"Renombrar «{node.name}»…", "rename")
        add(f"Mover «{node.name}» a…", "move")
        if node.needs_review:
            add("Marcar como revisada", "reviewed")
        menu.addSeparator()
        add(f"Borrar «{node.name}»…", "delete")
    menu.addSeparator()
    add("Purgar palabras clave no usadas…", "purge")

    chosen = menu.exec(global_pos)
    key = actions.get(chosen)
    if key is None:
        return None

    if key == "create_root":
        name = _ask_name(parent, "Crear palabra clave", "Nombre (en el primer nivel):")
        return (create_keyword, (None, name)) if name else None
    if key == "purge":
        answer = MessageBoxHelper(parent).question(
            "¿Borrar las palabras clave que no tiene ningún archivo del catálogo (ni ellas ni "
            "sus hijas)?\n\nUn padre que agrupa palabras usadas se queda.",
            title="Purgar palabras clave no usadas",
            buttons=["Purgar", "Cancelar"],
        )
        # Devuelve el número de palabras borradas, no de archivos: se envuelve para que
        # no se tome por archivos cambiados
        return (_purge_without_count, ()) if answer == "Purgar" else None

    assert entry is not None
    node, path, parent_id = entry
    if key == "create_child":
        name = _ask_name(parent, "Crear palabra clave", f"Nombre (dentro de «{node.name}»):")
        return (create_keyword, (node.id, name)) if name else None
    if key == "rename":
        name = _ask_name(parent, "Renombrar palabra clave", "Nombre nuevo:", node.name)
        return (rename_keyword, (node.id, name)) if name and name != node.name else None
    if key == "move":
        targets = move_targets(nodes, node.id)
        labels = [label for label, _id in targets]
        current = next((i for i, (_l, target) in enumerate(targets) if target == parent_id), 0)
        label, accepted = QInputDialog.getItem(
            parent, "Mover palabra clave", f"Mover «{node.name}» (con sus hijas) dentro de:",
            labels, current, False,
        )
        if not accepted:
            return None
        target = dict(targets).get(label)
        if target == parent_id and not node.needs_review:
            return None  # mismo sitio
        return move_keyword, (node.id, target)
    if key == "reviewed":
        return mark_keyword_reviewed, (node.id,)
    if key == "delete":
        answer = MessageBoxHelper(parent).warning(
            _delete_question(node), title="Borrar palabra clave", buttons=["Borrar", "Cancelar"]
        )
        return (delete_keyword, (node.id,)) if answer == "Borrar" else None
    return None


def _purge_without_count(conn: Any) -> int:
    """'purge_unused_keywords' sin devolver el número de palabras (ningún archivo cambia)."""
    purge_unused_keywords(conn)
    return 0


if __name__ == "__main__":
    # Autoprueba de la lógica (no necesita Qt real). Desde la raíz del proyecto:
    #     python -m ui_helpers.helpers.keyword_menu
    abuelos = KeywordTreeNode(3, "Abuelos", 0, 0, False, (KeywordTreeNode(4, "Abuela Cruz", 2, 2, False, ()),))
    tree = (
        KeywordTreeNode(1, "Familia", 5, 0, False, (KeywordTreeNode(2, "Ana", 3, 3, False, ()), abuelos)),
        KeywordTreeNode(5, "Coche", 1, 1, False, ()),
    )
    assert tree_index(tree)[4][1:] == (("Familia", "Abuelos", "Abuela Cruz"), 3)
    # Mover «Abuelos»: ni ella ni su hija; el primer nivel, el primero
    labels = [label for label, _id in move_targets(tree, 3)]
    assert labels == [ROOT_LABEL, "Coche", "Familia", "Familia > Ana"], labels
    assert "dos" not in _delete_question(tree[1]) and "1 imagen la tiene" in _delete_question(tree[1])
    assert "sus 3 palabras hijas" in _delete_question(tree[0]) and "5 imágenes" in _delete_question(tree[0])
    assert "su palabra hija" in _delete_question(abuelos) and "imagen" not in _delete_question(abuelos)
    print("Autoprueba finalizada correctamente.")
