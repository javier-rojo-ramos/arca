"""Colecciones del usuario: conjuntos y colecciones estáticas (leer, crear, renombrar...).

Este módulo NO depende de Qt. Todas las funciones que tocan la base de datos reciben la
conexión como primer parámetro, así que se envían tal cual a
'CatalogDatabaseManager.execute_async' (el gestor hace el commit).

Tipos (columna 'collections.kind'):
    KIND_SET     conjunto de colecciones: solo agrupa (puede contener colecciones y otros
                 conjuntos). No contiene archivos.
    KIND_STATIC  colección estática: los archivos que el usuario añade a mano (arrastrando
                 tarjetas, o desde el menú de la cuadrícula). Un archivo puede estar en
                 varias colecciones.
    KIND_SMART   colección inteligente: un conjunto de reglas ('smart_rules.RuleSet'),
                 guardado en 'collections.rules_json'. Sus archivos no se guardan: son
                 los que cumplen las reglas en cada momento.

Reglas que se comprueban aquí (y no en la interfaz, para que valgan siempre):
    - El nombre no puede estar vacío ni repetirse entre las colecciones del mismo nivel
      (sin distinguir mayúsculas ni acentos: 'Álbum' y 'album' se consideran iguales).
    - Una colección solo puede estar dentro de un CONJUNTO.
    - Solo se añaden archivos a colecciones ESTÁTICAS.
    - Una colección inteligente tiene al menos una regla, y todas válidas.
Si algo no se cumple se lanza 'CollectionError' con un mensaje listo para el usuario.

Las colecciones viven solo en la base de datos (decisión tomada): exportarlas o guardarlas
fuera del catálogo queda para más adelante.

1.1.0 Colecciones inteligentes: crear con reglas, 'update_smart_collection' (nombre,
      reglas y conjunto) y, al leer el árbol, sus reglas y su contador.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.user_collections
"""

__version__ = "1.1.0"
# ruff: noqa: RUF022
__all__ = [
    "KIND_SET",
    "KIND_SMART",
    "KIND_STATIC",
    "MAX_NAME_LENGTH",
    "CollectionError",
    "CollectionNode",
    "add_to_collection",
    "create_collection",
    "delete_collection",
    "fetch_collection_tree",
    "iter_nodes",
    "remove_from_collection",
    "rename_collection",
    "update_smart_collection",
]

# Librerías estándar
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

# Módulos del proyecto
from core.catalog.folder_tree import sort_key
from core.catalog.grid_source import GridSource, SourceKind
from core.catalog.media_queries import count_grid_items
from core.catalog.smart_rules import RuleSet, rules_from_json, rules_to_json

# Tipos de colección (valores de 'collections.kind')
KIND_SET = "set"
KIND_STATIC = "static"
KIND_SMART = "smart"

# Longitud máxima del nombre (para que quepa con holgura en la barra lateral y los menús)
MAX_NAME_LENGTH = 120

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500


class CollectionError(ValueError):
    """Operación no válida sobre una colección (mensaje en español, para el usuario)."""


@dataclass(frozen=True, slots=True)
class CollectionNode:
    """Una colección o un conjunto, con lo que contiene.

    Es inmutable, así que dos árboles se pueden comparar con '==' (la barra lateral no se
    reconstruye si no ha cambiado nada).

    Attributes:
        id: 'collections.id'.
        name: Nombre.
        kind: KIND_SET, KIND_STATIC o KIND_SMART.
        parent_id: Conjunto que la contiene (None = primer nivel).
        count: Archivos de la colección (None en los conjuntos, que no tienen).
        children: Lo que contiene (solo en los conjuntos): primero los conjuntos y después
            las colecciones, cada grupo por nombre.
        path_name: Nombre con sus conjuntos delante ('Viajes › 2024 › Pirineo'), para
            los menús.
        rules: KIND_SMART: sus reglas (None si las guardadas no se pueden leer).
        rules_error: KIND_SMART: por qué no se pueden leer sus reglas (None si se leen).
    """

    id: int
    name: str
    kind: str
    parent_id: int | None
    count: int | None
    children: tuple["CollectionNode", ...] = ()
    path_name: str = ""
    rules: RuleSet | None = None
    rules_error: str | None = None


# -----------------------------------------------------------------------------
# Lectura
# -----------------------------------------------------------------------------


def fetch_collection_tree(conn: sqlite3.Connection) -> tuple[CollectionNode, ...]:
    """Lee todas las colecciones y conjuntos del usuario, en forma de árbol.

    Los contadores cuentan todo lo que hay en la colección, también los archivos ausentes
    o de discos desconectados (como el resto de la barra lateral). Los de las colecciones
    inteligentes se calculan con sus reglas (lo mismo que mostrará la cuadrícula).

    Unas reglas guardadas que no se pueden leer (JSON dañado, un campo que ya no existe)
    no impiden leer el árbol: esa colección llega con 'rules' None, 'rules_error' con el
    motivo y sin contador.

    Returns:
        Las colecciones de primer nivel (con sus hijos dentro), ordenadas.
    """
    rows = conn.execute("SELECT id, parent_id, kind, name, rules_json FROM collections").fetchall()
    counts = dict(
        conn.execute(
            "SELECT collection_id, COUNT(*) FROM collection_items GROUP BY collection_id"
        ).fetchall()
    )

    # Reglas de las inteligentes (y su contador, con las mismas reglas que la cuadrícula)
    smart_rules: dict[int, tuple[RuleSet | None, str | None]] = {}
    for collection_id, _parent_id, kind, _name, rules_json in rows:
        if kind != KIND_SMART:
            continue
        try:
            rules = rules_from_json(rules_json)
        except ValueError as error:
            smart_rules[collection_id] = (None, str(error))
            continue
        smart_rules[collection_id] = (rules, None)
        source = GridSource(kind=SourceKind.SMART, rules=rules)
        counts[collection_id] = count_grid_items(conn, [source])[source]

    children_of: dict[int | None, list[tuple[int, str, str]]] = {}
    for collection_id, parent_id, kind, name, _rules_json in rows:
        children_of.setdefault(parent_id, []).append((collection_id, kind, name))

    def build(parent_id: int | None, prefix: str, seen: frozenset[int]) -> tuple[CollectionNode, ...]:
        # Primero los conjuntos y después las colecciones; cada grupo, por nombre
        entries = sorted(
            children_of.get(parent_id, []),
            key=lambda entry: (entry[1] != KIND_SET, sort_key(entry[2])),
        )
        nodes = []
        for collection_id, kind, name in entries:
            if collection_id in seen:
                continue  # protección ante un ciclo (no debería existir)
            path_name = f"{prefix} › {name}" if prefix else name
            rules, rules_error = smart_rules.get(collection_id, (None, None))
            if kind == KIND_SET:
                count = None
            elif kind == KIND_SMART and rules is None:
                count = None  # reglas ilegibles: no se puede contar
            else:
                count = int(counts.get(collection_id, 0))
            nodes.append(
                CollectionNode(
                    id=collection_id,
                    name=name,
                    kind=kind,
                    parent_id=parent_id,
                    count=count,
                    children=build(collection_id, path_name, seen | {collection_id}),
                    path_name=path_name,
                    rules=rules,
                    rules_error=rules_error,
                )
            )
        return tuple(nodes)

    return build(None, "", frozenset())


def iter_nodes(nodes: Sequence[CollectionNode]) -> Iterator[CollectionNode]:
    """Recorre el árbol de arriba abajo (cada nodo antes que sus hijos)."""
    for node in nodes:
        yield node
        yield from iter_nodes(node.children)


# -----------------------------------------------------------------------------
# Crear, renombrar, borrar
# -----------------------------------------------------------------------------


def create_collection(
    conn: sqlite3.Connection,
    name: str,
    kind: str = KIND_STATIC,
    parent_id: int | None = None,
    media_ids: Sequence[int] = (),
    *,
    rules: RuleSet | None = None,
) -> int:
    """Crea una colección (estática o inteligente) o un conjunto.

    Todo va en la misma transacción: si algo falla, no se crea nada.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        name: Nombre (se quitan los espacios de los extremos).
        kind: KIND_STATIC, KIND_SMART o KIND_SET.
        parent_id: Conjunto donde se crea (None = primer nivel).
        media_ids: Archivos que se añaden al crearla (solo en las estáticas).
        rules: Reglas (obligatorias en las inteligentes; se ignoran en las demás).

    Returns:
        El 'id' de la colección creada.

    Raises:
        CollectionError: Nombre vacío o repetido, tipo no válido, conjunto inexistente o
            reglas que faltan o no son válidas.
    """
    if kind not in (KIND_STATIC, KIND_SMART, KIND_SET):
        raise CollectionError(f"Tipo de colección no válido: {kind!r}")
    clean = _clean_name(name)
    rules_json = _rules_json(rules) if kind == KIND_SMART else None
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
    _check_parent(conn, parent_id)
    _check_unique_name(conn, clean, parent_id)

    cursor = conn.execute(
        "INSERT INTO collections(parent_id, kind, name, rules_json) VALUES (?, ?, ?, ?)",
        (parent_id, kind, clean, rules_json),
    )
    collection_id = int(cursor.lastrowid)
    if media_ids and kind == KIND_STATIC:
        add_to_collection(conn, collection_id, media_ids)
    return collection_id


def update_smart_collection(
    conn: sqlite3.Connection,
    collection_id: int,
    name: str,
    rules: RuleSet,
    parent_id: int | None,
) -> None:
    """Cambia el nombre, las reglas y el conjunto de una colección inteligente.

    Raises:
        CollectionError: Si no existe o no es inteligente, el nombre está vacío o repetido
            en el conjunto de destino, el conjunto no existe o las reglas no son válidas.
    """
    clean = _clean_name(name)
    rules_json = _rules_json(rules)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
    _old_parent, kind = _get(conn, collection_id)
    if kind != KIND_SMART:
        raise CollectionError("Solo se pueden editar las reglas de una colección inteligente.")
    _check_parent(conn, parent_id)  # (una colección no contiene nada: no puede haber ciclos)
    _check_unique_name(conn, clean, parent_id, exclude_id=collection_id)
    conn.execute(
        """UPDATE collections
              SET name = ?, rules_json = ?, parent_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?""",
        (clean, rules_json, parent_id, collection_id),
    )


def rename_collection(conn: sqlite3.Connection, collection_id: int, name: str) -> None:
    """Cambia el nombre de una colección o un conjunto.

    Raises:
        CollectionError: Si no existe, o el nombre está vacío o repetido en su nivel.
    """
    clean = _clean_name(name)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
    parent_id, _kind = _get(conn, collection_id)
    _check_unique_name(conn, clean, parent_id, exclude_id=collection_id)
    conn.execute(
        "UPDATE collections SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (clean, collection_id),
    )


def delete_collection(conn: sqlite3.Connection, collection_id: int) -> int:
    """Borra una colección, o un conjunto con TODO lo que contiene.

    Los archivos no se tocan (ni del disco ni del catálogo): solo dejan de estar en esas
    colecciones.

    Returns:
        Número de colecciones y conjuntos borrados (incluidos los que contenía).

    Raises:
        CollectionError: Si no existe.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
    _get(conn, collection_id)  # comprueba que existe
    # Cuántos se van a borrar: ella y todos sus descendientes (consulta recursiva)
    total = conn.execute(
        """WITH RECURSIVE tree(id) AS (
               SELECT ?
               UNION ALL
               SELECT c.id FROM collections c JOIN tree t ON c.parent_id = t.id
           )
           SELECT COUNT(*) FROM tree""",
        (collection_id,),
    ).fetchone()[0]
    # El resto lo borra SQLite en cascada (hijos y 'collection_items')
    conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
    return int(total)


# -----------------------------------------------------------------------------
# Archivos de una colección
# -----------------------------------------------------------------------------


def add_to_collection(
    conn: sqlite3.Connection, collection_id: int, media_ids: Sequence[int]
) -> int:
    """Añade archivos a una colección estática (los que ya estaban se ignoran).

    Returns:
        Cuántos se han añadido de verdad (sin contar los que ya estaban ni los 'id' que no
        existen en el catálogo).

    Raises:
        CollectionError: Si la colección no existe o no es estática.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")
    _parent_id, kind = _get(conn, collection_id)
    if kind != KIND_STATIC:
        raise CollectionError(
            "Solo se pueden añadir archivos a una colección normal "
            "(no a un conjunto ni a una colección inteligente)."
        )

    # Se añaden detrás de los que ya hay, en el orden recibido
    next_position = conn.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM collection_items WHERE collection_id = ?",
        (collection_id,),
    ).fetchone()[0]

    added = 0
    for offset, media_id in enumerate(dict.fromkeys(int(i) for i in media_ids)):
        # 'SELECT ... FROM media_items' solo inserta si el archivo existe (un 'id' que ya
        # no está en el catálogo daría un error de clave foránea, que OR IGNORE no evita)
        cursor = conn.execute(
            """INSERT OR IGNORE INTO collection_items(collection_id, media_id, position)
               SELECT ?, id, ? FROM media_items WHERE id = ?""",
            (collection_id, next_position + offset, media_id),
        )
        added += cursor.rowcount
    if added:
        conn.execute(
            "UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (collection_id,)
        )
    return added


def remove_from_collection(
    conn: sqlite3.Connection, collection_id: int, media_ids: Sequence[int]
) -> int:
    """Quita archivos de una colección (no los borra del catálogo ni del disco).

    Returns:
        Cuántos se han quitado.
    """
    ids = [int(i) for i in media_ids]
    removed = 0
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        cursor = conn.execute(
            f"DELETE FROM collection_items WHERE collection_id = ? AND media_id IN ({marks})",
            (collection_id, *chunk),
        )
        removed += cursor.rowcount
    return removed


# -----------------------------------------------------------------------------
# Comprobaciones internas
# -----------------------------------------------------------------------------


def _clean_name(name: str) -> str:
    """Nombre sin espacios en los extremos; CollectionError si queda vacío o es muy largo."""
    clean = " ".join((name or "").split())  # también colapsa espacios repetidos
    if not clean:
        raise CollectionError("El nombre no puede estar vacío.")
    if len(clean) > MAX_NAME_LENGTH:
        raise CollectionError(f"El nombre es demasiado largo (máximo {MAX_NAME_LENGTH} caracteres).")
    return clean


def _rules_json(rules: RuleSet | None) -> str:
    """Reglas de una colección inteligente en JSON; CollectionError si faltan o no valen."""
    if rules is None or not rules.rules:
        raise CollectionError("Una colección inteligente necesita al menos una regla.")
    try:
        return rules_to_json(rules)
    except ValueError as error:
        raise CollectionError(str(error)) from None


def _get(conn: sqlite3.Connection, collection_id: int) -> tuple[int | None, str]:
    """(parent_id, kind) de una colección; CollectionError si no existe."""
    row = conn.execute(
        "SELECT parent_id, kind FROM collections WHERE id = ?", (collection_id,)
    ).fetchone()
    if row is None:
        raise CollectionError("La colección ya no existe.")
    return row[0], row[1]


def _check_parent(conn: sqlite3.Connection, parent_id: int | None) -> None:
    """Comprueba que el conjunto donde se va a crear existe y ES un conjunto."""
    if parent_id is None:
        return
    _grandparent, kind = _get(conn, parent_id)
    if kind != KIND_SET:
        raise CollectionError("Una colección solo puede estar dentro de un conjunto de colecciones.")


def _check_unique_name(
    conn: sqlite3.Connection, name: str, parent_id: int | None, exclude_id: int | None = None
) -> None:
    """Comprueba que no hay otra colección con el mismo nombre en el mismo nivel.

    Se compara sin mayúsculas ni acentos (con la misma clave que se usa para ordenar).
    """
    siblings = conn.execute(
        "SELECT id, name FROM collections WHERE parent_id IS ?", (parent_id,)
    ).fetchall()
    wanted = sort_key(name)[0]
    for sibling_id, sibling_name in siblings:
        if sibling_id != exclude_id and sort_key(sibling_name)[0] == wanted:
            raise CollectionError(f"Ya hay una colección o un conjunto llamado «{sibling_name}» aquí.")


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.user_collections
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('P', '/p')")
    for n in range(1, 6):
        db.execute(
            """INSERT INTO media_items(id, storage_location_id, relative_path, file_name,
                   media_type, mime_type, file_size, file_mtime_ns, title)
               VALUES (?, 1, ?, ?, 'photo', 'image/jpeg', 1, 0, 'x')""",
            (n, f"{n}.jpg", f"{n}.jpg"),
        )

    def expect_error(call, text: str) -> None:
        try:
            call()
        except CollectionError as error:
            assert text in str(error), error
        else:
            raise AssertionError(f"debía fallar: {text}")

    # 1. Crear: un conjunto, colecciones dentro y fuera, con archivos al crearla
    albums = create_collection(db, "  Álbumes  ", KIND_SET)
    trips = create_collection(db, "Viajes", KIND_SET, parent_id=albums)
    routes = create_collection(db, "Rutas", parent_id=albums, media_ids=[1, 2, 2, 99])
    food = create_collection(db, "Comidas")
    db.commit()
    tree = fetch_collection_tree(db)
    # Primer nivel: el conjunto antes que la colección
    assert [(n.name, n.kind, n.count) for n in tree] == [("Álbumes", "set", None), ("Comidas", "static", 0)]
    inside = tree[0].children
    assert [(n.name, n.count) for n in inside] == [("Viajes", None), ("Rutas", 2)]  # 99 no existe
    assert inside[1].path_name == "Álbumes › Rutas"
    assert [n.name for n in iter_nodes(tree)] == ["Álbumes", "Viajes", "Rutas", "Comidas"]
    assert fetch_collection_tree(db) == tree  # comparable (no se reconstruye si no cambia)

    # 2. Nombres: vacíos, repetidos (sin mayúsculas ni acentos) y por niveles
    expect_error(lambda: create_collection(db, "   "), "vacío")
    expect_error(lambda: create_collection(db, "albumes", KIND_SET), "Álbumes")
    expect_error(lambda: create_collection(db, "x" * 200), "largo")
    create_collection(db, "Rutas")  # mismo nombre, otro nivel: sí se puede
    expect_error(lambda: create_collection(db, "Dentro", parent_id=routes), "conjunto")
    expect_error(lambda: create_collection(db, "Lista", "playlist"), "no válido")

    # 3. Añadir y quitar archivos
    assert add_to_collection(db, food, [3, 4]) == 2
    assert add_to_collection(db, food, [4, 5]) == 1  # el 4 ya estaba
    positions = [r[0] for r in db.execute(
        "SELECT media_id FROM collection_items WHERE collection_id = ? ORDER BY position", (food,))]
    assert positions == [3, 4, 5]
    expect_error(lambda: add_to_collection(db, albums, [1]), "conjunto")
    expect_error(lambda: add_to_collection(db, 999, [1]), "ya no existe")
    assert remove_from_collection(db, food, [4, 1]) == 1

    # 4. Renombrar
    rename_collection(db, food, "Comidas y cenas")
    rename_collection(db, food, "comidas Y cenas")  # cambiar solo mayúsculas: se permite
    expect_error(lambda: rename_collection(db, routes, "VIAJES"), "Viajes")

    # 5. Quitar un archivo del catálogo lo saca de sus colecciones
    db.execute("DELETE FROM media_items WHERE id = 1")
    counts = {n.id: n.count for n in iter_nodes(fetch_collection_tree(db))}
    assert counts[routes] == 1  # tenía el 1 y el 2

    # 6. Borrar un conjunto borra lo que contiene (y nunca los archivos)
    assert delete_collection(db, albums) == 3  # Álbumes, Viajes y Rutas
    assert [n.name for n in fetch_collection_tree(db)] == ["comidas Y cenas", "Rutas"]
    assert db.execute("SELECT COUNT(*) FROM media_items").fetchone()[0] == 4
    expect_error(lambda: delete_collection(db, albums), "ya no existe")

    # 7. Colecciones inteligentes: crear, contar, editar y reglas dañadas
    from core.catalog.smart_rules import Rule

    db.execute("UPDATE media_items SET rating = 4 WHERE id IN (2, 3)")
    four = RuleSet(rules=(Rule("rating", "gte", 4),))
    expect_error(lambda: create_collection(db, "Vacía", KIND_SMART), "al menos una regla")
    expect_error(
        lambda: create_collection(db, "Mala", KIND_SMART, rules=RuleSet(rules=(Rule("rating", "eq", 9),))),
        "Valoración",
    )
    best = create_collection(db, "Las mejores", KIND_SMART, rules=four)
    holder = create_collection(db, "Inteligentes", KIND_SET)
    db.commit()
    node = next(n for n in iter_nodes(fetch_collection_tree(db)) if n.id == best)
    assert (node.kind, node.count, node.rules, node.rules_error) == (KIND_SMART, 2, four, None)
    expect_error(lambda: add_to_collection(db, best, [2]), "inteligente")  # no admite archivos

    five = RuleSet(rules=(Rule("rating", "eq", 5),))
    update_smart_collection(db, best, "Cinco estrellas", five, holder)
    node = next(n for n in iter_nodes(fetch_collection_tree(db)) if n.id == best)
    assert (node.name, node.parent_id, node.count, node.path_name) == (
        "Cinco estrellas", holder, 0, "Inteligentes › Cinco estrellas"
    )
    expect_error(lambda: update_smart_collection(db, food, "x", five, None), "inteligente")
    expect_error(lambda: update_smart_collection(db, best, "x", five, best), "conjunto")

    # Reglas dañadas (p. ej. editadas a mano): el árbol se lee igual, sin contador
    db.execute("UPDATE collections SET rules_json = '{roto' WHERE id = ?", (best,))
    node = next(n for n in iter_nodes(fetch_collection_tree(db)) if n.id == best)
    assert node.rules is None and node.count is None and "JSON" in node.rules_error
    print("Autoprueba finalizada correctamente.")
