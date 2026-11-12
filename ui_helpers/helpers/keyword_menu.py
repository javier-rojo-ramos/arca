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

Lo usa el árbol con casillas del inspector ('KeywordChecklist'); la barra izquierda no
tiene menú desde el 04/11/2026 (solo navega). Pulsando en un hueco del árbol (sin
palabra), solo «Crear en el primer nivel» y «Purgar».

Aquí solo se pregunta (el nombre, el destino, la confirmación); la base de datos NO se
toca: 'ask_keyword_operation' devuelve (función, argumentos) de 'core/catalog/keywords.py'
y el árbol la emite ('operation_requested'). La ejecuta el controlador del inspector en su
cola de cambios (como el resto de cambios del usuario), que avisa si falla (p. ej. «Ya hay
una palabra clave "Ana" dentro de "Familia"») y refresca los árboles al terminar.

«Borrar» es la excepción (12/11/2026): la pregunta tiene que decir cuántos archivos de
TODO el catálogo la tienen (también vídeos, canciones o tracks, que los recuentos del
árbol no cuentan), y eso hay que leerlo de la base de datos. Así que el menú devuelve el
recuento ('fetch_keyword_usage'); el controlador del inspector, al recibir el
'KeywordUsage', pregunta con 'confirm_keyword_deletion' y, si se acepta, borra.

«Purgar» igual (pedido por el autor el 12/11/2026): el menú devuelve la lista de las
palabras sin usar ('fetch_unused_keywords') y el controlador pregunta con
'ask_keyword_purge', que las nombra (las PURGE_SHOWN primeras; todas, en «Mostrar
detalles…») y devuelve la operación que borra exactamente esas.

Los archivos que tienen una palabra renombrada, movida o borrada (o alguna de sus hijas)
quedan pendientes de escribir: su jerarquía en el XMP ha cambiado.

1.2.0 «Purgar»: la pregunta dice cuántas palabras se borran y cuáles ('purge_question',
      'ask_keyword_purge'); sin ninguna sin usar, un aviso.
1.1.0 «Borrar»: la pregunta cuenta los archivos de todo el catálogo, por tipo (antes,
      solo las imágenes del árbol: unos vídeos con la palabra perdían la palabra sin
      aviso). 'delete_question' y 'confirm_keyword_deletion'.

Prueba rápida de la lógica (sin Qt):
    python -m ui_helpers.helpers.keyword_menu
"""

__version__ = "1.2.0"
__all__ = [
    "PURGE_SHOWN",
    "ROOT_LABEL",
    "ask_keyword_operation",
    "ask_keyword_purge",
    "confirm_keyword_deletion",
    "delete_question",
    "move_targets",
    "purge_question",
    "tree_index",
]

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
    KeywordUsage,
    UnusedKeywords,
    create_keyword,
    delete_unused_keywords,
    fetch_keyword_usage,
    fetch_unused_keywords,
    mark_keyword_reviewed,
    move_keyword,
    rename_keyword,
)
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.inspector.formatting import format_media_types

# Palabras que se nombran en la pregunta de «Purgar» (todas, en «Mostrar detalles…»)
PURGE_SHOWN = 20

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


def delete_question(usage: KeywordUsage) -> str:
    """Texto de la confirmación de borrar: sus hijas y los archivos de TODO el catálogo que
    la tienen (o alguna de sus hijas), por tipo."""
    children = usage.descendants
    what = f"«{usage.name}»"
    if children:
        what += f" y {'su palabra hija' if children == 1 else f'sus {children} palabras hijas'}"
    text = f"¿Borrar {what}?"
    if usage.media:
        verb = "la tiene" if usage.media == 1 else "la tienen"
        which = " (o alguna de sus hijas)" if children else ""
        text += (
            f"\n\n{format_media_types(usage.media_types)} {verb}{which}: se les quitará, también "
            "en sus archivos si está activado «Guardar en los archivos»."
        )
    return text + "\n\nNo se puede deshacer."


def confirm_keyword_deletion(parent: QWidget, usage: KeywordUsage) -> bool:
    """Pregunta si se borra la palabra (con lo que afecta: 'delete_question')."""
    answer = MessageBoxHelper(parent).warning(
        delete_question(usage), title="Borrar palabra clave", buttons=["Borrar", "Cancelar"]
    )
    return answer == "Borrar"


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
        # Antes de preguntar, cuáles son (ver el docstring del módulo)
        return fetch_unused_keywords, ()

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
        # Antes de preguntar, lo que tiene todo el catálogo (ver el docstring del módulo)
        return fetch_keyword_usage, (node.id,)
    return None


def purge_question(unused: UnusedKeywords) -> tuple[str, str | None]:
    """La pregunta de «Purgar»: cuántas palabras y cuáles (las PURGE_SHOWN primeras), y la
    lista entera para «Mostrar detalles…» si no caben (None si caben)."""
    names = [f" {PATH_SEPARATOR} ".join(path) for path in unused.paths]
    count = len(names)
    if count == 1:
        head = (
            "¿Borrar esta palabra clave? No la tiene ningún archivo del catálogo "
            "(ni ella ni sus hijas):"
        )
    else:
        head = (
            f"¿Borrar estas {count} palabras clave? No las tiene ningún archivo del catálogo "
            "(ni ellas ni sus hijas):"
        )
    listed = ", ".join(names[:PURGE_SHOWN])
    if count > PURGE_SHOWN:
        listed += f" y {count - PURGE_SHOWN} más"
    text = f"{head}\n\n{listed}.\n\nUn padre que agrupa palabras usadas se queda."
    return text, ("\n".join(names) if count > PURGE_SHOWN else None)


def ask_keyword_purge(parent: QWidget, unused: UnusedKeywords) -> Operation | None:
    """Pregunta si se purgan esas palabras ('purge_question') y devuelve la operación que
    borra exactamente esas (None si se cancela). Sin ninguna sin usar, solo lo avisa."""
    title = "Purgar palabras clave no usadas"
    if not unused.ids:
        MessageBoxHelper(parent).info("No hay palabras clave sin usar.", title=title)
        return None
    text, details = purge_question(unused)
    answer = MessageBoxHelper(parent).question(
        text, title=title, buttons=["Purgar", "Cancelar"], details=details
    )
    return (_delete_unused_without_count, (unused.ids,)) if answer == "Purgar" else None


def _delete_unused_without_count(conn: Any, keyword_ids: tuple[int, ...]) -> int:
    """'delete_unused_keywords' sin devolver el número de palabras: no se tomaría por el
    de archivos cambiados (ninguno cambia)."""
    delete_unused_keywords(conn, keyword_ids)
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
    # La pregunta de borrar: hijas y archivos de todo el catálogo, por tipo
    coche = KeywordUsage(1, 0, 5, "Coche", (("photo", 1),))
    expected = "¿Borrar «Coche»?\n\n1 foto la tiene: se les quitará"
    assert delete_question(coche).startswith(expected), delete_question(coche)
    familia = KeywordUsage(8, 3, 1, "Familia", (("photo", 5), ("video", 3)))
    text = delete_question(familia)
    assert "¿Borrar «Familia» y sus 3 palabras hijas?" in text, text
    assert "5 fotos · 3 vídeos la tienen (o alguna de sus hijas)" in text, text
    # Solo vídeos (antes, sin aviso): ahora lo dice
    clips = delete_question(KeywordUsage(3, 0, 6, "Viaje", (("video", 3),)))
    assert "3 vídeos la tienen:" in clips, clips
    # Sin archivos: solo la pregunta
    alone = delete_question(KeywordUsage(0, 1, 3, "Abuelos"))
    assert alone == "¿Borrar «Abuelos» y su palabra hija?\n\nNo se puede deshacer.", alone
    # La pregunta de purgar: cuántas y cuáles (con su ruta); las que no caben, en detalles
    one, details = purge_question(UnusedKeywords((7,), (("Abel",),)))
    assert one.startswith("¿Borrar esta palabra clave? No la tiene") and "\n\nAbel.\n\n" in one
    assert details is None
    few, details = purge_question(UnusedKeywords((1, 2), (("Abel",), ("Familia", "Abuelos"))))
    assert "¿Borrar estas 2 palabras clave?" in few and "Abel, Familia > Abuelos." in few, few
    many_paths = tuple((f"P{i:02}",) for i in range(25))
    many, details = purge_question(UnusedKeywords(tuple(range(25)), many_paths))
    assert "P19 y 5 más." in many and "P20" not in many, many
    assert details is not None and details.splitlines() == [f"P{i:02}" for i in range(25)]
    print("Autoprueba finalizada correctamente.")
