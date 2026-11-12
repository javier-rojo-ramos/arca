"""Palabras clave en el catálogo: el árbol ('keywords') y sus asignaciones ('media_keywords').

Este módulo NO depende de Qt. Las funciones reciben una conexión abierta y NO hacen
commit (como las demás de 'core/catalog/'): las llama el procesador de metadatos dentro
de su transacción, o el gestor asíncrono.

Las palabras clave son datos del USUARIO (como la valoración): las asigna él, en esta
aplicación o en Lightroom. Al leer un archivo, MANDA EL ARCHIVO ('set_media_keywords'
deja exactamente las que trae), salvo que estén pendientes de escribir. Al asignarlas o
quitarlas aquí ('assign_keyword', 'remove_keyword'; paso K4a) el elemento queda pendiente
('media_items.keywords_pending = 1') y el trabajo de 'core/userdata/sync.py' las escribe
en su XMP o en el '.arca.json' de su carpeta, como la valoración.

Igual que Lightroom (comprobado el 03/11/2026), a un archivo se le asigna solo la palabra
(«Opel Astra»): sus padres («Coche») se deducen del árbol. Al escribirlas en el archivo,
la lista jerárquica lleva la ruta asignada («Coche|Opel Astra») y la plana, la palabra y
sus padres («Coche», «Opel Astra»): ver 'flat_keyword_names'.

Dónde va cada palabra leída (ver 'core/metadata/keyword_tags.py'):
    - Con ruta («Familia|Papá»): se crea o reutiliza cada nivel y se asigna la última.
      Los padres quedan en el árbol, pero NO asignados al archivo.
    - Suelta (de la lista plana, sin jerarquía; la escribió otro programa):
        * si en el árbol hay UNA sola palabra con ese nombre, es esa;
        * si hay varias («Ana» en Familia y en Amigos), la del primer nivel (se crea si
          no existe) marcada para revisar ('needs_review');
        * si no hay ninguna, se crea en el primer nivel.
Los nombres se comparan sin mayúsculas ni acentos ('fold_text'): «árbol» encuentra
«Árbol». Se conserva cómo se escribió la primera vez.

1.8.0 «Purgar» enseña antes lo que va a borrar: 'fetch_unused_keywords' (las palabras sin
      usar, con su ruta) y 'delete_unused_keywords' (borra esas, salvo las que se hayan
      usado entretanto). 'purge_unused_keywords' sigue igual.
1.7.0 'fetch_keyword_usage' (para la pregunta de «Borrar»): también el nombre y los
      elementos por tipo ('KeywordUsage.media_types'), de TODAS las bibliotecas.

Prueba rápida:
    python -m core.catalog.keywords
"""

__version__ = "1.8.0"
__all__ = [
    "KEYWORD_MEDIA_SQL",
    "KeywordChanges",
    "KeywordError",
    "KeywordUsage",
    "UnusedKeywords",
    "create_keyword",
    "delete_keyword",
    "delete_unused_keywords",
    "fetch_keyword_usage",
    "fetch_unused_keywords",
    "mark_keyword_reviewed",
    "move_keyword",
    "purge_unused_keywords",
    "rename_keyword",
    "validate_keyword_name",
    "KeywordEditorData",
    "RECENT_LIMIT",
    "fetch_descendant_marks",
    "fetch_keyword_names",
    "fetch_recent_keywords",
    "apply_keyword_changes",
    "diff_keyword_text",
    "fetch_keyword_editor_data",
    "filter_keyword_tree",
    "keyword_tokens",
    "assign_keyword",
    "flat_keyword_names",
    "remove_keyword",
    "same_keywords",
    "KeywordNode",
    "KeywordTreeNode",
    "fetch_keyword_tree",
    "SelectionKeywords",
    "fetch_selection_keywords",
    "ensure_keyword_path",
    "keyword_path",
    "keyword_tree",
    "media_keyword_paths",
    "resolve_flat_keyword",
    "set_media_keywords",
]

# Librerías estándar
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# Módulos del proyecto
from core.catalog.catalog_schema import fold_text
from core.catalog.media_types import MediaType
from core.metadata.keyword_tags import HIERARCHY_SEPARATOR


@dataclass(frozen=True, slots=True)
class KeywordNode:
    """Una palabra del árbol, para mostrarlo o recorrerlo.

    Attributes:
        id: Id de la palabra.
        name: Nombre tal como se escribió.
        depth: Nivel (0 = primer nivel).
        path: Ruta de la raíz a la palabra (('Familia', 'Papá')).
        direct_count: Archivos que la tienen asignada directamente.
        needs_review: Palabra suelta con el nombre de otras del árbol.
    """

    id: int
    name: str
    depth: int
    path: tuple[str, ...]
    direct_count: int
    needs_review: bool


# Elementos que tienen asignada una palabra ('?' = su id) O ALGUNA DE SUS HIJAS, a cualquier
# profundidad (CTE recursiva; 'UNION' evita bucles si hubiera un ciclo). Subconsulta no
# correlacionada: SQLite la calcula una vez. La usa el origen KEYWORD de la cuadrícula
# ('media_queries._source_condition').
KEYWORD_MEDIA_SQL = (
    "WITH RECURSIVE kw(id) AS (SELECT ? UNION SELECT k.id FROM keywords AS k JOIN kw ON k.parent_id = kw.id) "
    "SELECT mk.media_id FROM media_keywords AS mk WHERE mk.keyword_id IN (SELECT id FROM kw)"
)


def _find_child(conn: sqlite3.Connection, parent_id: int | None, name: str) -> int | None:
    """Id de la palabra 'name' bajo 'parent_id' (None = primer nivel), o None."""
    row = conn.execute(
        "SELECT id FROM keywords WHERE IFNULL(parent_id, 0) = ? AND name_folded = ?",
        (parent_id or 0, fold_text(name)),
    ).fetchone()
    return row[0] if row else None


def _create(conn: sqlite3.Connection, parent_id: int | None, name: str, *, review: bool = False) -> int:
    """Crea una palabra bajo 'parent_id' y devuelve su id."""
    cursor = conn.execute(
        "INSERT INTO keywords(parent_id, name, name_folded, needs_review) VALUES (?, ?, ?, ?)",
        (parent_id, name, fold_text(name), 1 if review else 0),
    )
    return int(cursor.lastrowid)


def ensure_keyword_path(conn: sqlite3.Connection, path: Sequence[str]) -> int:
    """Id de la última palabra de la ruta, creando los niveles que falten.

    Args:
        path: Ruta de la raíz a la palabra (('Familia', 'Papá')). No puede estar vacía.
    """
    if not path:
        raise ValueError("Ruta de palabra clave vacía")
    parent_id: int | None = None
    for name in path:
        found = _find_child(conn, parent_id, name)
        parent_id = found if found is not None else _create(conn, parent_id, name)
    assert parent_id is not None
    return parent_id


def resolve_flat_keyword(conn: sqlite3.Connection, name: str) -> int:
    """Id de una palabra suelta (sin ruta), según la regla de la cabecera."""
    rows = conn.execute(
        "SELECT id, parent_id FROM keywords WHERE name_folded = ? ORDER BY id",
        (fold_text(name),),
    ).fetchall()
    if len(rows) == 1:
        return int(rows[0][0])  # una sola en todo el árbol: es esa, esté donde esté
    root = next((row[0] for row in rows if row[1] is None), None)
    if not rows:
        return _create(conn, None, name)
    # Varias con ese nombre: no se sabe cuál es; va al primer nivel, para revisar
    if root is None:
        return _create(conn, None, name, review=True)
    conn.execute("UPDATE keywords SET needs_review = 1 WHERE id = ?", (root,))
    return int(root)


def set_media_keywords(
    conn: sqlite3.Connection,
    media_id: int,
    paths: Iterable[Sequence[str]],
    flat: Iterable[str] = (),
) -> bool:
    """Deja asignadas a un archivo EXACTAMENTE estas palabras (manda el archivo).

    Args:
        media_id: Elemento.
        paths: Palabras con su ruta (('Coche', 'Toyota Corolla')).
        flat: Palabras sueltas (ver 'resolve_flat_keyword').

    Returns:
        True si cambió alguna asignación.
    """
    wanted = {ensure_keyword_path(conn, path) for path in paths if path}
    wanted |= {resolve_flat_keyword(conn, name) for name in flat if name}
    current = {
        row[0]
        for row in conn.execute("SELECT keyword_id FROM media_keywords WHERE media_id = ?", (media_id,))
    }
    if wanted == current:
        return False
    removed, added = current - wanted, wanted - current
    conn.executemany(
        "DELETE FROM media_keywords WHERE media_id = ? AND keyword_id = ?",
        [(media_id, keyword_id) for keyword_id in removed],
    )
    conn.executemany(
        "INSERT INTO media_keywords(media_id, keyword_id) VALUES (?, ?)",
        [(media_id, keyword_id) for keyword_id in added],
    )
    return True


def same_keywords(
    first: Iterable[Sequence[str]], second: Iterable[Sequence[str]], *, exact: bool = False
) -> bool:
    """True si dos listas de rutas son las mismas palabras (sin orden).

    Por defecto sin distinguir mayúsculas ni acentos (para reconocer una palabra). Con
    'exact=True', letra a letra: para decidir si hay que ESCRIBIR un archivo (renombrar
    «familia» a «Familia» debe llegar al XMP; paso K4c-2).
    """

    def normalize(name: str) -> str | None:
        return " ".join(str(name).split()) if exact else fold_text(name)

    def key(paths: Iterable[Sequence[str]]) -> frozenset[tuple[str | None, ...]]:
        return frozenset(tuple(normalize(name) for name in path) for path in paths if path)

    return key(first) == key(second)


def flat_keyword_names(paths: Iterable[Sequence[str]]) -> list[str]:
    """Lista plana de una lista de rutas: cada palabra Y SUS PADRES, sin repetir.

    Es lo que Lightroom escribe en 'dc:subject' (comprobado con «Coche|Opel Astra» ->
    «Coche», «Opel Astra», y con «Familia|Isa» + «Familia|Javi» -> «Familia», «Isa»,
    «Javi»; también con una categoría como «[Familia]»).
    """
    names: list[str] = []
    seen: set[str | None] = set()
    for path in paths:
        for name in path:
            key = fold_text(name)
            if key not in seen:
                seen.add(key)
                names.append(name)
    return names


def _mark_pending(conn: sqlite3.Connection, media_ids: Iterable[int]) -> None:
    """Deja esos elementos con las palabras clave pendientes de escribir fuera."""
    ids = list(media_ids)
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        conn.execute(
            f"UPDATE media_items SET keywords_pending = 1, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id IN ({marks})",
            chunk,
        )


def assign_keyword(conn: sqlite3.Connection, media_ids: Sequence[int], keyword_id: int) -> int:
    """Asigna una palabra a varios elementos (los que ya la tenían no cambian).

    Los que cambian quedan pendientes de escribir en su archivo. No hace commit.

    Returns:
        Cuántos elementos han cambiado.

    Raises:
        ValueError: Si la palabra no existe.
    """
    if conn.execute("SELECT 1 FROM keywords WHERE id = ?", (keyword_id,)).fetchone() is None:
        raise ValueError(f"La palabra clave {keyword_id} no existe")
    ids = list(dict.fromkeys(int(i) for i in media_ids))
    changed: list[int] = []
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        have = {
            row[0]
            for row in conn.execute(
                f"SELECT media_id FROM media_keywords WHERE keyword_id = ? AND media_id IN ({marks})",
                (keyword_id, *chunk),
            )
        }
        new = [media_id for media_id in chunk if media_id not in have]
        conn.executemany(
            "INSERT INTO media_keywords(media_id, keyword_id) VALUES (?, ?)",
            [(media_id, keyword_id) for media_id in new],
        )
        changed += new
    _mark_pending(conn, changed)
    # Usada ahora (para «Últimas palabras clave»), aunque ya la tuvieran todos: el usuario
    # la ha elegido. Con milésimas, para ordenar las de un mismo segundo
    conn.execute(
        "UPDATE keywords SET last_used_at = strftime('%Y-%m-%dT%H:%M:%f', 'now') WHERE id = ?",
        (keyword_id,),
    )
    return len(changed)


def remove_keyword(conn: sqlite3.Connection, media_ids: Sequence[int], keyword_id: int) -> int:
    """Quita una palabra a varios elementos (solo la asignada: sus hijas no se tocan).

    Los que cambian quedan pendientes de escribir en su archivo. La palabra se queda en
    el árbol aunque ya no la tenga ningún archivo. No hace commit.

    Returns:
        Cuántos elementos han cambiado.
    """
    ids = list(dict.fromkeys(int(i) for i in media_ids))
    changed: list[int] = []
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        had = [
            row[0]
            for row in conn.execute(
                f"SELECT media_id FROM media_keywords WHERE keyword_id = ? AND media_id IN ({marks})",
                (keyword_id, *chunk),
            )
        ]
        conn.executemany(
            "DELETE FROM media_keywords WHERE media_id = ? AND keyword_id = ?",
            [(media_id, keyword_id) for media_id in had],
        )
        changed += had
    _mark_pending(conn, changed)
    return len(changed)


def keyword_path(conn: sqlite3.Connection, keyword_id: int) -> tuple[str, ...]:
    """Ruta de la raíz a una palabra (('Familia', 'Papá'))."""
    names: list[str] = []
    current: int | None = keyword_id
    while current is not None:
        row = conn.execute("SELECT name, parent_id FROM keywords WHERE id = ?", (current,)).fetchone()
        if row is None:
            break
        names.append(row[0])
        current = row[1]
    return tuple(reversed(names))


def media_keyword_paths(conn: sqlite3.Connection, media_id: int) -> list[tuple[str, ...]]:
    """Palabras asignadas a un archivo, con su ruta, por orden alfabético de la ruta."""
    ids = [
        row[0]
        for row in conn.execute("SELECT keyword_id FROM media_keywords WHERE media_id = ?", (media_id,))
    ]
    return sorted((keyword_path(conn, keyword_id) for keyword_id in ids), key=lambda p: [fold_text(n) for n in p])


@dataclass(frozen=True, slots=True)
class SelectionKeywords:
    """Palabras asignadas a una selección (lo que muestra el inspector).

    Attributes:
        total: Elementos seleccionados.
        items: (ruta, cuántos de los seleccionados la tienen), por orden alfabético de la
            ruta. Si el recuento es menor que 'total', no la tienen todos.
    """

    total: int = 0
    items: tuple[tuple[tuple[str, ...], int], ...] = ()
    # 'keywords.id' de cada elemento de 'items', en el mismo orden
    keyword_ids: tuple[int, ...] = ()


# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500


def fetch_selection_keywords(conn: sqlite3.Connection, media_ids: Sequence[int]) -> SelectionKeywords:
    """Palabras asignadas a unos elementos y en cuántos de ellos está cada una.

    Pensada para el inspector (se ejecuta en segundo plano con 'execute_async'): una
    consulta por cada 500 elementos y otra para las rutas de todo el árbol.
    """
    ids = list(dict.fromkeys(media_ids))
    counts: dict[int, int] = {}
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT keyword_id, COUNT(*) FROM media_keywords WHERE media_id IN ({marks}) "
            "GROUP BY keyword_id",
            chunk,
        )
        for keyword_id, count in rows:
            counts[keyword_id] = counts.get(keyword_id, 0) + count
    if not counts:
        return SelectionKeywords(total=len(ids))

    # Rutas: el árbol entero de una vez (es pequeño) en vez de una consulta por palabra
    tree = {row[0]: (row[1], row[2]) for row in conn.execute("SELECT id, parent_id, name FROM keywords")}

    def path_of(keyword_id: int) -> tuple[str, ...]:
        names: list[str] = []
        current: int | None = keyword_id
        while current is not None and current in tree and len(names) < 100:  # 100: por si un ciclo
            parent_id, name = tree[current]
            names.append(name)
            current = parent_id
        return tuple(reversed(names))

    rows = sorted(
        ((path_of(keyword_id), count, keyword_id) for keyword_id, count in counts.items()),
        key=lambda item: [fold_text(name) for name in item[0]],
    )
    return SelectionKeywords(
        total=len(ids),
        items=tuple((path, count) for path, count, _id in rows),
        keyword_ids=tuple(keyword_id for _path, _count, keyword_id in rows),
    )


@dataclass(frozen=True, slots=True)
class KeywordTreeNode:
    """Una palabra del árbol de la barra lateral, con sus hijas.

    Es inmutable: dos árboles iguales son '==' (la barra no lo reconstruye si no cambia).

    Attributes:
        id: Id de la palabra.
        name: Nombre tal como se escribió.
        count: Elementos con la palabra O ALGUNA DE SUS HIJAS (cada elemento cuenta una
            vez aunque tenga varias), en la biblioteca pedida.
        direct_count: Elementos con la palabra asignada directamente.
        needs_review: Palabra suelta con el nombre de otras (ver la cabecera).
        children: Sus hijas, por orden alfabético.
    """

    id: int
    name: str
    count: int
    direct_count: int
    needs_review: bool
    children: tuple["KeywordTreeNode", ...] = ()


def fetch_keyword_tree(conn: sqlite3.Connection, library: str | None = None) -> tuple[KeywordTreeNode, ...]:
    """El árbol de palabras clave con sus recuentos (para la barra lateral).

    Los recuentos INCLUYEN las hijas («Coche» cuenta también las fotos que solo tienen
    «Toyota Corolla»; decidido el 03/11/2026) y son de los elementos de 'library' (None =
    de todas). Se muestran TODAS las palabras, también las que tienen 0.

    Se calcula en Python con dos consultas (las palabras y las asignaciones): con decenas
    de miles de fotos son unas decenas de miles de filas, mucho más rápido que una
    consulta recursiva por palabra.
    """
    rows = conn.execute("SELECT id, parent_id, name, name_folded, needs_review FROM keywords").fetchall()
    parent_of = {row[0]: row[1] for row in rows}
    if library is None:
        assignments = conn.execute("SELECT media_id, keyword_id FROM media_keywords")
    else:
        assignments = conn.execute(
            "SELECT mk.media_id, mk.keyword_id FROM media_keywords AS mk "
            "JOIN media_items AS m ON m.id = mk.media_id WHERE m.library = ?",
            (library,),
        )

    direct: dict[int, int] = {}
    with_children: dict[int, set[int]] = {}
    for media_id, keyword_id in assignments:
        direct[keyword_id] = direct.get(keyword_id, 0) + 1
        # La palabra y todos sus padres cuentan este elemento (el set evita contarlo dos
        # veces si tiene, p. ej., «Coche» y «Toyota Corolla»)
        current: int | None = keyword_id
        steps = 0
        while current is not None and steps < 100:  # 100: por si hubiera un ciclo
            with_children.setdefault(current, set()).add(media_id)
            current = parent_of.get(current)
            steps += 1

    children: dict[int | None, list[tuple]] = {}
    for row in rows:
        children.setdefault(row[1], []).append(row)

    def build(parent_id: int | None, depth: int) -> tuple[KeywordTreeNode, ...]:
        if depth > 100:
            return ()
        siblings = sorted(children.get(parent_id, []), key=lambda row: row[3])
        return tuple(
            KeywordTreeNode(
                id=row[0],
                name=row[2],
                count=len(with_children.get(row[0], ())),
                direct_count=direct.get(row[0], 0),
                needs_review=bool(row[4]),
                children=build(row[0], depth + 1),
            )
            for row in siblings
        )

    return build(None, 0)


def filter_keyword_tree(nodes: Iterable[KeywordTreeNode], text: str) -> tuple[KeywordTreeNode, ...]:
    """Las palabras cuyo nombre contiene 'text' (sin mayúsculas ni acentos) y sus padres.

    Un padre que coincide conserva TODAS sus hijas (filtrar «coche» deja ver los modelos);
    uno que no coincide se queda solo con las ramas que sí. Texto vacío = el árbol entero.
    (Lo usan la barra lateral del módulo Imagen y el árbol con casillas del inspector.)
    """
    needle = fold_text(text.strip()) or ""
    if not needle:
        return tuple(nodes)

    def visit(node: KeywordTreeNode) -> KeywordTreeNode | None:
        if needle in (fold_text(node.name) or ""):
            return node
        kept = tuple(child for child in (visit(c) for c in node.children) if child is not None)
        if not kept:
            return None
        return KeywordTreeNode(node.id, node.name, node.count, node.direct_count, node.needs_review, kept)

    return tuple(found for found in (visit(node) for node in nodes) if found is not None)


# -----------------------------------------------------------------------------
# Edición desde la interfaz (paso K4b): caja de texto y árbol con casillas
# -----------------------------------------------------------------------------

# Separadores de la caja de texto: entre palabras, y entre los niveles de una ruta
TEXT_SEPARATOR = ","
PATH_SEPARATOR = ">"
# Marca de las palabras que no tienen todos los seleccionados (como Lightroom)
PARTIAL_MARK = "*"


@dataclass(frozen=True, slots=True)
class KeywordChanges:
    """Cambios de palabras clave que se aplican a TODA una selección.

    Attributes:
        add_ids: Palabras del árbol que se asignan.
        add_paths: Palabras escritas como ruta o nombre nuevo (se crean si no existen).
        remove_ids: Palabras que se quitan.
    """

    add_ids: tuple[int, ...] = ()
    add_paths: tuple[tuple[str, ...], ...] = ()
    remove_ids: tuple[int, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.add_ids or self.add_paths or self.remove_ids)


def keyword_tokens(selection: SelectionKeywords) -> list[str]:
    """Texto de cada palabra de una selección para la caja: el nombre (o «Padre > Nombre»
    si dos se llaman igual) y un asterisco si no la tienen todos."""
    leaves: dict[str | None, int] = {}
    for path, _count in selection.items:
        leaves[fold_text(path[-1])] = leaves.get(fold_text(path[-1]), 0) + 1
    tokens = []
    for path, count in selection.items:
        name = f" {PATH_SEPARATOR} ".join(path) if leaves[fold_text(path[-1])] > 1 else path[-1]
        tokens.append(f"{name}{PARTIAL_MARK}" if count < selection.total else name)
    return tokens


def _parse_token(token: str) -> tuple[tuple[str, ...], bool]:
    """('Coche > Opel Astra*') -> (('Coche', 'Opel Astra'), True): ruta y si lleva asterisco."""
    text = token.strip()
    partial = text.endswith(PARTIAL_MARK)
    if partial:
        text = text[: -len(PARTIAL_MARK)].strip()
    path = tuple(part.strip() for part in text.split(PATH_SEPARATOR) if part.strip())
    return path, partial


def diff_keyword_text(text: str, selection: SelectionKeywords) -> KeywordChanges:
    """Qué cambia al editar la caja de texto (como el panel de Lightroom).

    Se compara con lo que mostraba la caja ('selection'), palabra a palabra:
        - Una palabra que ya no está: se QUITA de todos los seleccionados.
        - Una con asterisco que sigue con asterisco: no se toca.
        - Una con asterisco a la que se le quita: se asigna a TODOS.
        - Una nueva: se asigna a todos. Con «>» es una ruta («Coche > Seat Ibiza»: se crea
          dentro de «Coche»); sin ella, un nombre (el del árbol si hay uno solo con ese
          nombre; si no existe, se crea en el primer nivel: ver 'resolve_flat_keyword').
    Se reconoce una palabra existente por su nombre o por su ruta completa, sin
    mayúsculas ni acentos.
    """
    shown: list[tuple[tuple[str | None, ...], tuple[str | None, ...], int, bool]] = []
    for (path, count), keyword_id in zip(selection.items, selection.keyword_ids, strict=False):
        folded = tuple(fold_text(name) for name in path)
        shown.append((folded, folded[-1:], keyword_id, count < selection.total))
    leaf_count: dict[tuple[str | None, ...], int] = {}
    for _full, leaf, _id, _partial in shown:
        leaf_count[leaf] = leaf_count.get(leaf, 0) + 1

    kept: set[int] = set()
    add_ids: list[int] = []
    add_paths: list[tuple[str, ...]] = []
    for token in text.split(TEXT_SEPARATOR):
        path, marked = _parse_token(token)
        if not path:
            continue
        folded = tuple(fold_text(name) for name in path)
        match = next(
            (
                (keyword_id, partial)
                for full, leaf, keyword_id, partial in shown
                if folded == full or (len(folded) == 1 and folded == leaf and leaf_count[leaf] == 1)
            ),
            None,
        )
        if match is None:
            if path not in add_paths:
                add_paths.append(path)
            continue
        keyword_id, partial = match
        kept.add(keyword_id)
        if partial and not marked and keyword_id not in add_ids:
            add_ids.append(keyword_id)  # se le quitó el asterisco: para todos

    remove_ids = tuple(keyword_id for _full, _leaf, keyword_id, _p in shown if keyword_id not in kept)
    return KeywordChanges(tuple(add_ids), tuple(add_paths), remove_ids)


def apply_keyword_changes(conn: sqlite3.Connection, media_ids: Sequence[int], changes: KeywordChanges) -> int:
    """Aplica los cambios a todos los elementos (una transacción: la del gestor).

    Las rutas nuevas se crean (una ruta de un solo nombre se coloca como una palabra
    suelta: 'resolve_flat_keyword'). Los que cambian quedan pendientes de escribir.

    Returns:
        Cuántas asignaciones han cambiado (0 = nada que hacer).
    """
    changed = 0
    for keyword_id in changes.remove_ids:
        changed += remove_keyword(conn, media_ids, keyword_id)
    targets = list(changes.add_ids)
    for path in changes.add_paths:
        targets.append(resolve_flat_keyword(conn, path[0]) if len(path) == 1 else ensure_keyword_path(conn, path))
    for keyword_id in dict.fromkeys(targets):
        changed += assign_keyword(conn, media_ids, keyword_id)
    return changed


# Cuántas «Últimas palabras clave» se muestran en el inspector (dos filas de tres)
RECENT_LIMIT = 6


@dataclass(frozen=True, slots=True)
class KeywordEditorData:
    """Lo que necesitan las secciones de palabras clave del inspector (módulo Imagen).

    Attributes:
        selection: Las palabras de los seleccionados y en cuántos está cada una.
        tree: El árbol entero, con los recuentos de la biblioteca.
        recent: Las últimas palabras asignadas desde la interfaz: (id, ruta), la más
            reciente primero (como mucho 'RECENT_LIMIT').
        descendants: Para cada palabra con alguna hija (o nieta...) asignada a los
            seleccionados: (en cuántos de ellos, rutas de esas hijas). Ver
            'fetch_descendant_marks'.
    """

    selection: SelectionKeywords = SelectionKeywords()
    tree: tuple[KeywordTreeNode, ...] = ()
    recent: tuple[tuple[int, tuple[str, ...]], ...] = ()
    descendants: dict[int, tuple[int, tuple[tuple[str, ...], ...]]] | None = None


def _keyword_table(conn: sqlite3.Connection) -> dict[int, tuple[int | None, str]]:
    """{id: (padre, nombre)} de todo el árbol (es pequeño: se lee de una vez)."""
    return {row[0]: (row[1], row[2]) for row in conn.execute("SELECT id, parent_id, name FROM keywords")}


def _path_in(table: dict[int, tuple[int | None, str]], keyword_id: int) -> tuple[str, ...]:
    """Ruta de una palabra con la tabla de '_keyword_table'."""
    names: list[str] = []
    current: int | None = keyword_id
    while current is not None and current in table and len(names) < 100:  # 100: por si un ciclo
        parent_id, name = table[current]
        names.append(name)
        current = parent_id
    return tuple(reversed(names))


def fetch_recent_keywords(
    conn: sqlite3.Connection, limit: int = RECENT_LIMIT
) -> tuple[tuple[int, tuple[str, ...]], ...]:
    """Las últimas palabras asignadas desde la interfaz: (id, ruta), la más reciente primero."""
    rows = conn.execute(
        "SELECT id FROM keywords WHERE last_used_at IS NOT NULL "
        "ORDER BY last_used_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    if not rows:
        return ()
    table = _keyword_table(conn)
    return tuple((row[0], _path_in(table, row[0])) for row in rows)


def fetch_descendant_marks(
    conn: sqlite3.Connection, media_ids: Sequence[int]
) -> dict[int, tuple[int, tuple[tuple[str, ...], ...]]]:
    """Palabras que tienen alguna hija (o nieta...) asignada a los seleccionados.

    Para resaltarlas en el árbol con casillas: «Familia» si una foto tiene «Ana». Su
    casilla no cambia (dice si «Familia» está asignada); esto es aparte.

    Returns:
        {id del antepasado: (en cuántos de los seleccionados hay alguna de sus hijas,
        rutas de esas hijas por orden alfabético)}. Cada elemento cuenta una vez aunque
        tenga varias hijas de la misma palabra.
    """
    ids = list(dict.fromkeys(media_ids))
    table = _keyword_table(conn)
    media_by_ancestor: dict[int, set[int]] = {}
    keywords_by_ancestor: dict[int, set[int]] = {}
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT media_id, keyword_id FROM media_keywords WHERE media_id IN ({marks})",
            chunk,
        )
        for media_id, keyword_id in rows:
            parent = table.get(keyword_id, (None, ""))[0]
            steps = 0
            while parent is not None and steps < 100:  # 100: por si un ciclo
                media_by_ancestor.setdefault(parent, set()).add(media_id)
                keywords_by_ancestor.setdefault(parent, set()).add(keyword_id)
                parent = table.get(parent, (None, ""))[0]
                steps += 1
    result = {}
    for ancestor, media in media_by_ancestor.items():
        paths = sorted(
            (_path_in(table, keyword_id) for keyword_id in keywords_by_ancestor[ancestor]),
            key=lambda path: [fold_text(name) for name in path],
        )
        result[ancestor] = (len(media), tuple(paths))
    return result


def fetch_keyword_names(conn: sqlite3.Connection) -> list[str]:
    """Nombres de todas las palabras, sin repetir y por orden alfabético (para el
    autocompletado del editor de reglas, que compara nombres, no rutas)."""
    names: dict[str | None, str] = {}
    for (name,) in conn.execute("SELECT name FROM keywords"):
        names.setdefault(fold_text(name), name)
    return sorted(names.values(), key=lambda name: fold_text(name) or "")


def fetch_keyword_editor_data(
    conn: sqlite3.Connection, media_ids: Sequence[int], library: str | None = None
) -> KeywordEditorData:
    """Lo que necesitan las secciones de palabras clave del inspector: las palabras de
    la selección, el árbol entero (recuentos de 'library'; None = de todas), las últimas
    usadas y las palabras con hijas asignadas."""
    return KeywordEditorData(
        selection=fetch_selection_keywords(conn, media_ids),
        tree=tuple(fetch_keyword_tree(conn, library)),
        recent=fetch_recent_keywords(conn),
        descendants=fetch_descendant_marks(conn, media_ids),
    )


# -----------------------------------------------------------------------------
# Gestionar el árbol (paso K4c-2): crear, renombrar, mover, borrar, purgar
# -----------------------------------------------------------------------------
# Todas sin commit (la transacción es la del gestor). Cuando cambia la ruta de una palabra
# (renombrar, mover) o desaparece (borrar), los archivos que la tienen, o tienen alguna
# de sus hijas, quedan PENDIENTES de escribir: su 'HierarchicalSubject' ya no es el mismo.

# Caracteres que no puede llevar un nombre: los separadores de la caja de texto («,» y
# «>») y el de la jerarquía en los archivos («|», como Lightroom)
FORBIDDEN_NAME_CHARS = (TEXT_SEPARATOR, PATH_SEPARATOR, HIERARCHY_SEPARATOR)


class KeywordError(ValueError):
    """Operación del árbol no válida; el mensaje está pensado para el usuario."""


@dataclass(frozen=True, slots=True)
class KeywordUsage:
    """Lo que afectaría borrar una palabra (para la pregunta de confirmación).

    Attributes:
        media: Elementos (de TODAS las bibliotecas) con la palabra o alguna de sus hijas.
        descendants: Cuántas palabras hay debajo (hijas, nietas...).
        keyword_id: La palabra.
        name: Su nombre.
        media_types: Esos elementos por tipo ((tipo, cuántos), en el orden de
            'MediaType': fotos, vídeos, audio...).
    """

    media: int = 0
    descendants: int = 0
    keyword_id: int = 0
    name: str = ""
    media_types: tuple[tuple[str, int], ...] = ()


def validate_keyword_name(name: str) -> str:
    """El nombre limpio (sin espacios de más) o KeywordError si no vale."""
    clean = " ".join(str(name).split())
    if not clean:
        raise KeywordError("El nombre no puede estar vacío.")
    bad = [char for char in FORBIDDEN_NAME_CHARS if char in clean]
    if bad:
        shown = " ".join(f"«{char}»" for char in bad)
        raise KeywordError(f"El nombre no puede llevar {shown} (separan palabras y niveles).")
    return clean


def _subtree_ids(conn: sqlite3.Connection, keyword_id: int) -> list[int]:
    """La palabra y todas las que tiene debajo."""
    rows = conn.execute(
        "WITH RECURSIVE sub(id) AS (SELECT ? UNION ALL "
        "SELECT k.id FROM keywords k JOIN sub ON k.parent_id = sub.id) SELECT id FROM sub",
        (keyword_id,),
    ).fetchall()
    return [row[0] for row in rows]


def _media_with_any(conn: sqlite3.Connection, keyword_ids: Sequence[int]) -> list[int]:
    """Elementos que tienen alguna de esas palabras."""
    found: set[int] = set()
    ids = list(keyword_ids)
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        found.update(
            row[0]
            for row in conn.execute(
                f"SELECT DISTINCT media_id FROM media_keywords WHERE keyword_id IN ({marks})",
                chunk,
            )
        )
    return sorted(found)


def _require(conn: sqlite3.Connection, keyword_id: int) -> tuple[int | None, str]:
    """(padre, nombre) de una palabra, o KeywordError si ya no existe."""
    row = conn.execute("SELECT parent_id, name FROM keywords WHERE id = ?", (keyword_id,)).fetchone()
    if row is None:
        raise KeywordError("La palabra clave ya no existe (¿se ha borrado?).")
    return row[0], row[1]


def _check_free(conn: sqlite3.Connection, parent_id: int | None, name: str, *, except_id: int | None = None) -> None:
    """KeywordError si ya hay otra palabra con ese nombre bajo ese padre."""
    found = _find_child(conn, parent_id, name)
    if found is not None and found != except_id:
        where = f"dentro de «{_require(conn, parent_id)[1]}»" if parent_id is not None else "en el primer nivel"
        raise KeywordError(f"Ya hay una palabra clave «{name}» {where}.")


def create_keyword(conn: sqlite3.Connection, parent_id: int | None, name: str) -> int:
    """Crea una palabra vacía bajo 'parent_id' (None = primer nivel) y devuelve su id."""
    clean = validate_keyword_name(name)
    if parent_id is not None:
        _require(conn, parent_id)
    _check_free(conn, parent_id, clean)
    return _create(conn, parent_id, clean)


def rename_keyword(conn: sqlite3.Connection, keyword_id: int, name: str) -> int:
    """Cambia el nombre de una palabra (sus hijas la siguen).

    Returns:
        Cuántos elementos quedan pendientes de escribir (los que la tienen a ella o a
        alguna de sus hijas). Solo cambiar mayúsculas también cuenta.
    """
    clean = validate_keyword_name(name)
    parent_id, old = _require(conn, keyword_id)
    if clean == old:
        return 0
    _check_free(conn, parent_id, clean, except_id=keyword_id)
    conn.execute(
        "UPDATE keywords SET name = ?, name_folded = ? WHERE id = ?",
        (clean, fold_text(clean), keyword_id),
    )
    media = _media_with_any(conn, _subtree_ids(conn, keyword_id))
    _mark_pending(conn, media)
    return len(media)


def move_keyword(conn: sqlite3.Connection, keyword_id: int, new_parent_id: int | None) -> int:
    """Mueve una palabra (con sus hijas) dentro de otra (None = al primer nivel).

    Deja de estar «a revisar» (se ha colocado a mano).

    Returns:
        Cuántos elementos quedan pendientes de escribir.

    Raises:
        KeywordError: Si se mueve dentro de sí misma o de una de sus hijas, o si ya hay
            una con su nombre en el destino.
    """
    parent_id, name = _require(conn, keyword_id)
    subtree = _subtree_ids(conn, keyword_id)
    if new_parent_id is not None:
        _require(conn, new_parent_id)
        if new_parent_id in subtree:
            raise KeywordError(f"No se puede mover «{name}» dentro de sí misma ni de una de sus hijas.")
    if new_parent_id == parent_id:
        conn.execute("UPDATE keywords SET needs_review = 0 WHERE id = ?", (keyword_id,))
        return 0
    _check_free(conn, new_parent_id, name, except_id=keyword_id)
    conn.execute(
        "UPDATE keywords SET parent_id = ?, needs_review = 0 WHERE id = ?", (new_parent_id, keyword_id)
    )
    media = _media_with_any(conn, subtree)
    _mark_pending(conn, media)
    return len(media)


def mark_keyword_reviewed(conn: sqlite3.Connection, keyword_id: int) -> int:
    """Quita la marca «a revisar» de una palabra suelta (está bien donde está). Devuelve 0
    (ningún archivo cambia)."""
    _require(conn, keyword_id)
    conn.execute("UPDATE keywords SET needs_review = 0 WHERE id = ?", (keyword_id,))
    return 0


def fetch_keyword_usage(conn: sqlite3.Connection, keyword_id: int) -> KeywordUsage:
    """Cuántos elementos (de TODAS las bibliotecas, por tipo) y cuántas palabras afectaría
    borrar esta palabra: lo que dice la pregunta de «Borrar» antes de hacerlo.

    Raises:
        KeywordError: Si la palabra ya no existe.
    """
    _parent, name = _require(conn, keyword_id)
    subtree = _subtree_ids(conn, keyword_id)
    media = _media_with_any(conn, subtree)
    by_type: dict[str, int] = {}
    for start in range(0, len(media), _CHUNK):
        chunk = media[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        for media_type, count in conn.execute(
            f"SELECT media_type, COUNT(*) FROM media_items WHERE id IN ({marks}) GROUP BY 1", chunk
        ):
            by_type[media_type] = by_type.get(media_type, 0) + count
    # En el orden de los tipos (fotos, vídeos, audio...); uno desconocido, al final
    order = {kind.value: index for index, kind in enumerate(MediaType)}
    ordered = sorted(by_type.items(), key=lambda item: (order.get(item[0], len(order)), item[0]))
    return KeywordUsage(
        media=len(media), descendants=len(subtree) - 1, keyword_id=keyword_id, name=name,
        media_types=tuple(ordered),
    )  # fmt: skip


def delete_keyword(conn: sqlite3.Connection, keyword_id: int) -> int:
    """Borra una palabra y todas sus hijas; se quitan de los elementos que las tenían.

    Returns:
        Cuántos elementos quedan pendientes de escribir (se les quita en sus archivos).
    """
    _require(conn, keyword_id)
    media = _media_with_any(conn, _subtree_ids(conn, keyword_id))
    _mark_pending(conn, media)  # antes de borrar: después ya no se sabe quién la tenía
    conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))  # hijas en cascada
    return len(media)


@dataclass(frozen=True, slots=True)
class UnusedKeywords:
    """Lo que borraría «Purgar» (para enseñarlo en la pregunta antes de hacerlo).

    Attributes:
        ids: Las palabras sin usar (ni ellas ni sus hijas), en el orden de 'paths'.
        paths: Su ruta de la raíz a la palabra, en orden alfabético (sin mayúsculas ni
            acentos).
    """

    ids: tuple[int, ...] = ()
    paths: tuple[tuple[str, ...], ...] = ()


def _unused_ids(conn: sqlite3.Connection) -> list[int]:
    """Las palabras que no tiene ningún elemento, ni ellas ni sus hijas (un padre que solo
    agrupa hijas usadas no está entre ellas)."""
    rows = conn.execute("SELECT id, parent_id FROM keywords").fetchall()
    used = {row[0] for row in conn.execute("SELECT DISTINCT keyword_id FROM media_keywords")}
    parent_of = {row[0]: row[1] for row in rows}
    keep: set[int] = set()
    for keyword_id in used:
        current: int | None = keyword_id
        steps = 0
        while current is not None and current not in keep and steps < 100:  # 100: por si un ciclo
            keep.add(current)
            current = parent_of.get(current)
            steps += 1
    return [keyword_id for keyword_id in parent_of if keyword_id not in keep]


def _delete_ids(conn: sqlite3.Connection, keyword_ids: Sequence[int]) -> None:
    """Borra esas palabras (sus hijas, en cascada), por lotes."""
    ids = list(keyword_ids)
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ", ".join("?" * len(chunk))
        conn.execute(f"DELETE FROM keywords WHERE id IN ({marks})", chunk)


def purge_unused_keywords(conn: sqlite3.Connection) -> int:
    """Borra las palabras que no tiene ningún elemento, ni ellas ni sus hijas (como
    «Purgar palabras clave no utilizadas» de Lightroom). Un padre que solo sirve para
    agrupar hijas usadas se queda.

    Returns:
        Cuántas palabras se han borrado (ningún archivo cambia).
    """
    unused = _unused_ids(conn)
    _delete_ids(conn, unused)
    return len(unused)


def fetch_unused_keywords(conn: sqlite3.Connection) -> UnusedKeywords:
    """Las palabras que borraría 'purge_unused_keywords', con su ruta, en orden alfabético
    (para enseñarlas en la pregunta de «Purgar» antes de borrarlas)."""
    unused = _unused_ids(conn)
    rows = conn.execute("SELECT id, parent_id, name FROM keywords").fetchall()
    parent_of = {row[0]: row[1] for row in rows}
    name_of = {row[0]: row[2] for row in rows}

    def path(keyword_id: int) -> tuple[str, ...]:
        names: list[str] = []
        current: int | None = keyword_id
        while current is not None and current in name_of and len(names) < 100:  # por si un ciclo
            names.append(name_of[current])
            current = parent_of.get(current)
        return tuple(reversed(names))

    found = sorted(((path(keyword_id), keyword_id) for keyword_id in unused),
                   key=lambda item: tuple(fold_text(name) for name in item[0]))  # fmt: skip
    return UnusedKeywords(
        ids=tuple(keyword_id for _path, keyword_id in found),
        paths=tuple(found_path for found_path, _id in found),
    )


def delete_unused_keywords(conn: sqlite3.Connection, keyword_ids: Sequence[int]) -> int:
    """Borra esas palabras (las que enseñó la pregunta de «Purgar»), salvo las que ya no
    estén sin usar (p. ej. se asignaron a una foto mientras se contestaba).

    Returns:
        Cuántas se han borrado (ningún archivo cambia).
    """
    still = set(_unused_ids(conn))
    chosen = [keyword_id for keyword_id in keyword_ids if keyword_id in still]
    _delete_ids(conn, chosen)
    return len(chosen)


def keyword_tree(conn: sqlite3.Connection) -> list[KeywordNode]:
    """El árbol entero en orden de recorrido (cada palabra seguida de sus hijas),
    alfabético en cada nivel, con el recuento de asignaciones directas.

    (El árbol de la interfaz, con recuentos que incluyen a las hijas, llega en K3.)
    """
    rows = conn.execute(
        "SELECT k.id, k.parent_id, k.name, k.name_folded, k.needs_review, "
        "(SELECT COUNT(*) FROM media_keywords mk WHERE mk.keyword_id = k.id) "
        "FROM keywords k"
    ).fetchall()
    children: dict[int | None, list[tuple]] = {}
    for row in rows:
        children.setdefault(row[1], []).append(row)
    for siblings in children.values():
        siblings.sort(key=lambda row: row[3])

    nodes: list[KeywordNode] = []

    def visit(parent_id: int | None, prefix: tuple[str, ...]) -> None:
        for row in children.get(parent_id, []):
            path = (*prefix, row[2])
            nodes.append(KeywordNode(row[0], row[2], len(prefix), path, row[5], bool(row[4])))
            visit(row[0], path)

    visit(None, ())
    return nodes


if __name__ == "__main__":
    # Autoprueba con un catálogo en memoria. Ejecutar desde la raíz del proyecto:
    #     python -m core.catalog.keywords
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Fotos', '/fotos')")
    media = [
        db.execute(
            "INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type, "
            "mime_type, file_size, file_mtime_ns, title) VALUES (1, ?, ?, 'photo', 'image/jpeg', 1, 0, ?)",
            (f"{n}.jpg", f"{n}.jpg", str(n)),
        ).lastrowid
        for n in range(5)
    ]

    # 1. El HEIC del autor: «Coche» y «Coche > Toyota Corolla» asignadas
    assert set_media_keywords(db, media[0], [("Coche",), ("Coche", "Toyota Corolla")])
    assert media_keyword_paths(db, media[0]) == [("Coche",), ("Coche", "Toyota Corolla")]
    # Otra foto solo con el modelo: «Coche» queda como padre, sin asignar a ella
    set_media_keywords(db, media[1], [("Coche", "Opel Astra"), ("coche", "toyota corolla")])
    assert media_keyword_paths(db, media[1]) == [("Coche", "Opel Astra"), ("Coche", "Toyota Corolla")]
    tree = keyword_tree(db)
    assert [(n.path, n.direct_count) for n in tree] == [
        (("Coche",), 1),
        (("Coche", "Opel Astra"), 1),
        (("Coche", "Toyota Corolla"), 2),  # «toyota corolla» es la misma palabra
    ], tree
    print("Rutas: el árbol se crea y se reutiliza (sin mayúsculas ni acentos)")

    # 2. Repetir no cambia nada; manda el archivo (quitar y poner)
    assert not set_media_keywords(db, media[1], [("Coche", "Toyota Corolla"), ("Coche", "Opel Astra")])
    assert set_media_keywords(db, media[1], [("Coche", "Opel Astra")])
    assert media_keyword_paths(db, media[1]) == [("Coche", "Opel Astra")]
    assert set_media_keywords(db, media[1], [])
    assert media_keyword_paths(db, media[1]) == []
    # La palabra sin fotos se conserva en el árbol (como en Lightroom)
    assert any(n.path == ("Coche", "Opel Astra") for n in keyword_tree(db))
    print("Manda el archivo: asignar, quitar y vaciar; el árbol se conserva")

    # 3. Palabras sueltas: una sola con ese nombre -> esa; ninguna -> primer nivel
    set_media_keywords(db, media[2], [("Familia", "Papá")])
    set_media_keywords(db, media[3], [], flat=["papa", "Playa"])
    assert media_keyword_paths(db, media[3]) == [("Familia", "Papá"), ("Playa",)]
    # Varias con ese nombre -> primer nivel, marcada para revisar
    set_media_keywords(db, media[4], [("Amigos", "Ana"), ("Familia", "Ana")])
    set_media_keywords(db, media[2], [("Familia", "Papá")], flat=["Ana"])
    assert ("Ana",) in media_keyword_paths(db, media[2])
    review = [n.path for n in keyword_tree(db) if n.needs_review]
    assert review == [("Ana",)], review
    # Y una tercera «Ana» suelta reutiliza esa del primer nivel
    set_media_keywords(db, media[3], [], flat=["ANA"])
    assert media_keyword_paths(db, media[3]) == [("Ana",)]
    print("Palabras sueltas: colocadas según el árbol; las dudosas, para revisar")

    # 4. Palabras de una selección, con cuántos la tienen (para el inspector)
    selection = fetch_selection_keywords(db, [media[2], media[3], media[3]])
    assert selection.total == 2, selection
    assert selection.items == ((("Ana",), 2), (("Familia", "Papá"), 1)), selection
    assert fetch_selection_keywords(db, [media[1]]) == SelectionKeywords(total=1)
    print("Selección: palabras de varios elementos con su recuento")

    # 5. Árbol de la barra lateral: los recuentos incluyen las hijas, sin repetir
    db.execute("UPDATE media_items SET library = 'image'")
    db.execute("UPDATE media_items SET library = 'video' WHERE id = ?", (media[4],))
    set_media_keywords(db, media[0], [("Coche",), ("Coche", "Toyota Corolla")])
    set_media_keywords(db, media[1], [("Coche", "Opel Astra")])
    tree = {node.name: node for node in fetch_keyword_tree(db)}
    coche = tree["Coche"]
    assert (coche.count, coche.direct_count) == (2, 1), coche  # la foto 0 cuenta una vez
    assert [(c.name, c.count) for c in coche.children] == [("Opel Astra", 1), ("Toyota Corolla", 1)]
    assert tree["Familia"].count == 2  # «Ana» (foto 4, vídeo) y «Papá» (foto 2)
    in_images = {node.name: node for node in fetch_keyword_tree(db, "image")}
    assert in_images["Familia"].count == 1 and in_images["Amigos"].count == 0  # el vídeo no
    assert fetch_keyword_tree(db, "image") == fetch_keyword_tree(db, "image")  # comparable
    # La misma condición que usa la cuadrícula (palabra y sus hijas)
    found = {row[0] for row in db.execute(f"SELECT m.id FROM media_items m WHERE m.id IN ({KEYWORD_MEDIA_SQL})", (coche.id,))}
    assert found == {media[0], media[1]}, found
    print("Árbol con recuentos (incluyen las hijas) y la condición de la cuadrícula")

    # 6. Asignar y quitar desde la aplicación: pendientes de escribir (solo los que cambian)
    db.execute("UPDATE media_items SET keywords_pending = 0")
    astra = ensure_keyword_path(db, ("Coche", "Opel Astra"))
    assert assign_keyword(db, [media[0], media[1], media[1]], astra) == 1  # la 1 ya la tenía
    pending = dict(db.execute("SELECT id, keywords_pending FROM media_items"))
    assert pending[media[0]] == 1 and pending[media[1]] == 0, pending
    assert remove_keyword(db, [media[0], media[3]], astra) == 1
    assert ("Coche", "Opel Astra") not in media_keyword_paths(db, media[0])
    try:
        assign_keyword(db, [media[0]], 99999)
        raise AssertionError("palabra inexistente aceptada")
    except ValueError:
        pass
    # La lista plana, como Lightroom: la palabra y sus padres, sin repetir
    assert flat_keyword_names([("Familia", "Isa"), ("Familia", "Javi")]) == ["Familia", "Isa", "Javi"]
    assert flat_keyword_names([("Coche", "Opel Astra"), ("coche",)]) == ["Coche", "Opel Astra"]
    assert same_keywords([("Coche", "Opel Astra")], [("coche", "opel astra")])
    assert not same_keywords([("Coche",)], [("Coche", "Opel Astra")])
    assert not same_keywords([("Familia",)], [("Família",)], exact=True)  # para escribir: letra a letra
    assert same_keywords([("Familia",)], [(" Familia ",)], exact=True)
    print("Asignar y quitar: pendientes de escribir; lista plana como Lightroom")

    # 7. Caja de texto: lo que se muestra y lo que cambia al editarla (como Lightroom)
    for media_id in media:
        set_media_keywords(db, media_id, [])
    set_media_keywords(db, media[0], [("Coche", "Opel Astra"), ("Playa",)])
    set_media_keywords(db, media[1], [("Playa",), ("Amigos", "Ana")])
    sel = fetch_selection_keywords(db, [media[0], media[1]])
    assert keyword_tokens(sel) == ["Ana*", "Opel Astra*", "Playa"], keyword_tokens(sel)  # una sola «Ana»
    unchanged = diff_keyword_text(", ".join(keyword_tokens(sel)), sel)
    assert unchanged.is_empty, unchanged
    # Quitar «Playa», quitar el asterisco de «Opel Astra» y añadir «Coche > Seat Ibiza» y «Nieve»
    changes = diff_keyword_text("Ana*, opel astra, Coche > Seat Ibiza, Nieve", sel)
    playa_id = sel.keyword_ids[2]
    assert changes.remove_ids == (playa_id,) and changes.add_ids == (sel.keyword_ids[1],), changes
    assert changes.add_paths == (("Coche", "Seat Ibiza"), ("Nieve",)), changes
    assert apply_keyword_changes(db, [media[0], media[1]], changes) == 2 + 1 + 2 + 2  # quitar 2, astra 1, ibiza 2, nieve 2
    assert media_keyword_paths(db, media[1]) == [("Amigos", "Ana"), ("Coche", "Opel Astra"), ("Coche", "Seat Ibiza"), ("Nieve",)]
    # Por su ruta completa también se reconoce; vaciar la caja lo quita todo
    sel = fetch_selection_keywords(db, [media[0]])
    assert diff_keyword_text("Coche > Opel Astra, Coche > Seat Ibiza, Nieve", sel).is_empty
    assert len(diff_keyword_text("", sel).remove_ids) == 3
    # Últimas usadas (la más reciente primero) y antepasados con hijas asignadas
    recent = fetch_recent_keywords(db)
    assert [path for _id, path in recent][:2] == [("Nieve",), ("Coche", "Seat Ibiza")], recent
    marks = fetch_descendant_marks(db, [media[0], media[1], media[2]])
    coche = next(n.id for n in fetch_keyword_tree(db) if n.name == "Coche")
    assert marks[coche] == (2, (("Coche", "Opel Astra"), ("Coche", "Seat Ibiza"))), marks[coche]
    assert "Nieve" not in {path[-1] for _c, paths in marks.values() for path in paths}  # sin padre
    data = fetch_keyword_editor_data(db, [media[0]])
    assert data.selection.total == 1 and data.recent == recent and coche in data.descendants
    assert "Coche" in fetch_keyword_names(db) and len(fetch_keyword_names(db)) == len(set(fetch_keyword_names(db)))
    # El filtro del árbol
    tree = fetch_keyword_tree(db)
    assert [n.name for n in filter_keyword_tree(tree, "IBIZA")] == ["Coche"]
    print("Caja de texto: lo mostrado, lo que cambia y su aplicación a la selección")

    # 8. Gestionar el árbol (K4c-2)
    for media_id in media:
        set_media_keywords(db, media_id, [])
    db.execute("UPDATE media_items SET keywords_pending = 0")
    purge_unused_keywords(db)  # árbol limpio: sin asignaciones, no queda ninguna
    assert keyword_tree(db) == []
    set_media_keywords(db, media[0], [("Familia", "Ana")])
    set_media_keywords(db, media[1], [("Amigos", "Luis")])
    familia = _find_child(db, None, "Familia")
    ana = _find_child(db, familia, "Ana")
    pending = lambda: [r[0] for r in db.execute("SELECT id FROM media_items WHERE keywords_pending = 1 ORDER BY id")]
    # Crear: vacía, con nombre limpio; repetida o con separadores, no
    javi = create_keyword(db, familia, "  Javi  ")
    assert keyword_path(db, javi) == ("Familia", "Javi")
    for bad in ("Javi", "a, b", "a > b", "a|b", "   "):
        try:
            create_keyword(db, familia, bad)
            raise AssertionError(f"aceptado: {bad!r}")
        except KeywordError:
            pass
    assert pending() == []
    # Renombrar el padre: la foto con «Ana» queda pendiente (cambia su ruta)
    assert rename_keyword(db, familia, "Família") == 1 and pending() == [media[0]]
    assert media_keyword_paths(db, media[0]) == [("Família", "Ana")]
    assert rename_keyword(db, familia, "Família") == 0
    # Mover «Ana» al primer nivel y luego dentro de «Amigos»; no dentro de sí misma
    db.execute("UPDATE media_items SET keywords_pending = 0")
    amigos = _find_child(db, None, "Amigos")
    assert move_keyword(db, ana, None) == 1 and keyword_path(db, ana) == ("Ana",)
    assert move_keyword(db, ana, amigos) == 1 and keyword_path(db, ana) == ("Amigos", "Ana")
    try:
        move_keyword(db, familia, javi)
        raise AssertionError("movida dentro de su hija")
    except KeywordError:
        pass
    other = create_keyword(db, None, "Luis")
    try:
        move_keyword(db, other, amigos)  # ya hay un «Luis» en Amigos
        raise AssertionError("nombre repetido en el destino")
    except KeywordError:
        pass
    # Uso y borrado: «Amigos» tiene 2 hijas y está en 2 fotos
    usage = fetch_keyword_usage(db, amigos)
    summary = (usage.media, usage.descendants, usage.keyword_id, usage.name)
    assert summary == (2, 2, amigos, "Amigos"), summary
    assert sum(count for _type, count in usage.media_types) == 2, usage.media_types
    db.execute("UPDATE media_items SET keywords_pending = 0")
    assert delete_keyword(db, amigos) == 2 and pending() == [media[0], media[1]]
    assert media_keyword_paths(db, media[0]) == [] and _find_child(db, amigos, "Ana") is None
    # Purgar: quedan solo las usadas y sus padres
    set_media_keywords(db, media[2], [("Coche", "Opel Astra")])
    before = {n.path for n in keyword_tree(db)}
    # Lo que se purgaría, con su ruta y en orden; si entretanto se usa una, esa se queda
    unused = fetch_unused_keywords(db)
    assert len(unused.ids) == len(before) - 2 and len(unused.ids) == len(unused.paths)
    assert list(unused.paths) == sorted(unused.paths, key=lambda path: [fold_text(n) for n in path])
    assert ("Coche",) not in unused.paths and ("Coche", "Opel Astra") not in unused.paths
    rescued_path = unused.paths[0]
    rescued = unused.ids[0]
    db.execute(
        "INSERT INTO media_keywords(media_id, keyword_id) VALUES (?, ?)", (media[2], rescued)
    )
    removed = delete_unused_keywords(db, unused.ids)
    after = {n.path for n in keyword_tree(db)}
    assert rescued_path in after and removed == len(before) - len(after), (removed, after)
    db.execute("DELETE FROM media_keywords WHERE keyword_id = ?", (rescued,))
    # Y la purga de siempre, sin preguntar: quedan solo las usadas y sus padres
    removed = purge_unused_keywords(db)
    after = {n.path for n in keyword_tree(db)}
    assert after == {("Coche",), ("Coche", "Opel Astra")}, after
    assert fetch_unused_keywords(db) == UnusedKeywords()
    # Revisada: sin la marca
    loose = _create(db, None, "Suelta", review=True)
    mark_keyword_reviewed(db, loose)
    assert db.execute("SELECT needs_review FROM keywords WHERE id = ?", (loose,)).fetchone()[0] == 0
    print("Árbol: crear, renombrar, mover, borrar y purgar; pendientes donde cambia la ruta")

    # 9. Borrar un archivo borra sus asignaciones (no las palabras)
    db.execute("DELETE FROM media_items WHERE id = ?", (media[2],))
    assert db.execute("SELECT COUNT(*) FROM media_keywords WHERE media_id = ?", (media[2],)).fetchone()[0] == 0
    assert any(n.path == ("Coche", "Opel Astra") for n in keyword_tree(db))
    try:
        ensure_keyword_path(db, ())
        raise AssertionError("ruta vacía aceptada")
    except ValueError:
        pass
    db.close()
    print("Autoprueba finalizada correctamente.")
