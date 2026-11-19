"""Las carpetas del catálogo: las del disco, tengan o no archivos que se catalogan (CAT 5).

Este módulo NO depende de Qt. Las funciones reciben la conexión como primer parámetro y no
hacen 'commit' (las llama quien tiene la transacción: el escáner, mover, quitar...).

El árbol de «Carpetas» del Catálogo replica las carpetas del disco, como Lightroom Classic:
también las vacías o con solo archivos que no se catalogan (documentos, por ejemplo), que
salen con 0. Se guardan en la tabla 'folders' (migración 6; la raíz de una ubicación no, que
es la propia ubicación) y el árbol las junta con las de los archivos
('folder_tree.fetch_folder_tree'). Quién las pone al día:

    - Añadir o sincronizar una carpeta ('folder_importer.add_folder'): 'sync_folders' con
      las que ha recorrido el escáner. Las que ya no están en el disco salen del catálogo,
      salvo si el recorrido no fue completo (cancelado, una carpeta que no se pudo leer...).
    - Crear una carpeta ('core/file_ops/moves.py'): 'add_folders'. Mover archivos a una
      carpeta también la apunta (y las de encima), por si no lo estuviera.
    - Renombrar una carpeta: sus filas y las de debajo cambian de ruta ('moves.py').
    - Quitar una carpeta del catálogo ('folder_removal.py'): 'remove_folders'. Una que se
      queda en el disco (no estaba vacía) vuelve a aparecer al sincronizar la de encima,
      como sus archivos (no hay lista de excluidos).
    - Quitar una ubicación: sus carpetas se van con ella (ON DELETE CASCADE).

Una carpeta que se queda sin archivos al mover los suyos o al eliminarlos del disco SIGUE en
el árbol con 0 (decisión del autor, 19/11/2026, como en Lightroom): para quitarla, «Quitar
del catálogo...», que la elimina también del disco si está vacía ('empty_folders.py').

Las rutas, relativas a la ubicación, con '/' y como se escriben en el disco.

1.0.0 Primera versión (CAT 5).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.catalog_folders
"""

__version__ = "1.0.0"
__all__ = [
    "add_folders",
    "folder_paths",
    "folders_under",
    "remove_folders",
    "sync_folders",
    "with_parents",
]

# Librerías estándar
import sqlite3
from collections.abc import Iterable
from typing import Any


def _normalize(folder: str) -> str:
    """Ruta relativa con '/' y sin barras en los extremos ('' = la raíz de la ubicación)."""
    return folder.replace("\\", "/").strip("/")


def with_parents(folders: Iterable[str]) -> set[str]:
    """Las carpetas y todas las de encima, sin la raíz: 'a/b' -> {'a', 'a/b'}."""
    result: set[str] = set()
    for folder in folders:
        parts = _normalize(folder).split("/")
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            if prefix:
                result.add(prefix)
    return result


def _under(folder: str, *, include_self: bool = True) -> tuple[str, list[Any]]:
    """Condición SQL (con 'relative_path'): la carpeta y las de debajo ('' = todas).

    Por RANGO, como en el resto del catálogo ('carpeta/' <= ruta < 'carpeta0'): sin
    comodines y con el índice. '0' es el carácter siguiente a '/', así que '2024b' no cae
    dentro de '2024'.
    """
    if not folder:
        return "", []
    below = "(relative_path >= ? AND relative_path < ?)"
    if include_self:
        return f" AND (relative_path = ? OR {below})", [folder, f"{folder}/", f"{folder}0"]
    return f" AND {below}", [f"{folder}/", f"{folder}0"]


def add_folders(conn: sqlite3.Connection, location_id: int, folders: Iterable[str]) -> int:
    """Apunta unas carpetas (y las de encima). Las que ya estaban no cambian.

    Returns:
        Cuántas se han apuntado nuevas.
    """
    paths = sorted(with_parents(folders))
    if not paths:
        return 0
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO folders(storage_location_id, relative_path) VALUES (?, ?)",
        ((location_id, path) for path in paths),
    )
    return conn.total_changes - before


def folders_under(
    conn: sqlite3.Connection, location_id: int, folder: str = "", *, include_self: bool = True
) -> list[str]:
    """Las carpetas apuntadas dentro de una ('' = toda la ubicación), ella incluida."""
    where, params = _under(_normalize(folder), include_self=include_self)
    rows = conn.execute(
        f"SELECT relative_path FROM folders WHERE storage_location_id = ?{where}",
        [location_id, *params],
    )
    return [row[0] for row in rows]


def remove_folders(conn: sqlite3.Connection, location_id: int, folder: str = "") -> int:
    """Quita del catálogo una carpeta y las de debajo ('' = todas las de la ubicación).

    Returns:
        Cuántas se han quitado.
    """
    where, params = _under(_normalize(folder))
    cursor = conn.execute(
        f"DELETE FROM folders WHERE storage_location_id = ?{where}", [location_id, *params]
    )
    return cursor.rowcount


def sync_folders(
    conn: sqlite3.Connection,
    location_id: int,
    within: str,
    seen: Iterable[str],
    *,
    unreadable: Iterable[str] = (),
    complete: bool = True,
) -> tuple[int, int]:
    """Pone al día las carpetas de 'within' con las que el escáner ha visto en el disco.

    Args:
        conn: Conexión (con la transacción de quien llama).
        location_id: La ubicación.
        within: La carpeta recorrida ('' = toda la ubicación). Se apunta ella también.
        seen: Las subcarpetas que se han recorrido (rutas relativas a la ubicación).
        unreadable: Rutas que no se pudieron leer: lo de debajo no se sabe si sigue, así
            que no se quita.
        complete: False si el recorrido no vio todo (cancelado, la raíz ilegible...): solo
            se apuntan las vistas, no se quita nada.

    Returns:
        (apuntadas nuevas, quitadas).
    """
    within = _normalize(within)
    seen_paths = with_parents([*seen, within])  # una carpeta vista, también las de encima
    added = add_folders(conn, location_id, seen_paths)
    if not complete:
        return added, 0
    blocked = [_normalize(path) for path in unreadable]
    gone = [
        path
        for path in folders_under(conn, location_id, within, include_self=False)
        if path not in seen_paths
        and not any(path == block or path.startswith(f"{block}/") for block in blocked)
    ]
    conn.executemany(
        "DELETE FROM folders WHERE storage_location_id = ? AND relative_path = ?",
        ((location_id, path) for path in gone),
    )
    return added, len(gone)


def folder_paths(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """Todas las carpetas apuntadas, por ubicación (para el árbol)."""
    result: dict[int, list[str]] = {}
    for location_id, path in conn.execute(
        "SELECT storage_location_id, relative_path FROM folders"
    ):
        result.setdefault(location_id, []).append(path)
    return result


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.catalog_folders
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('F', '/f')")
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('G', '/g')")

    def paths(location: int = 1) -> set[str]:
        return set(folders_under(db, location))

    # 1. Las de encima, nunca la raíz; apuntar dos veces no repite
    assert with_parents(["a/b/c", "\\x\\", ""]) == {"a", "a/b", "a/b/c", "x"}
    assert add_folders(db, 1, ["2024/Viaje", "Vacía"]) == 3
    assert add_folders(db, 1, ["2024"]) == 0
    assert paths() == {"2024", "2024/Viaje", "Vacía"}
    print("1. Apuntar carpetas, con las de encima")

    # 2. Dentro de una, sin confundir '2024' con '2024b'; quitar una con lo de debajo
    add_folders(db, 1, ["2024b/x", "2024/Viaje/Día 1"])
    add_folders(db, 2, ["2024"])
    assert set(folders_under(db, 1, "2024")) == {"2024", "2024/Viaje", "2024/Viaje/Día 1"}
    assert set(folders_under(db, 1, "2024", include_self=False)) == {"2024/Viaje", "2024/Viaje/Día 1"}
    assert remove_folders(db, 1, "2024/Viaje") == 2
    assert paths() == {"2024", "2024b", "2024b/x", "Vacía"} and paths(2) == {"2024"}
    print("2. Las de dentro de una y quitarlas, sin tocar las que empiezan igual")

    # 3. Tras recorrer: las vistas se apuntan; las que ya no están, fuera (salvo bajo una
    #    ilegible); sin un recorrido completo no se quita nada
    add_folders(db, 1, ["Viejo/Sub", "Ilegible/Dentro"])
    added, removed = sync_folders(
        db, 1, "", ["2024", "Nueva/Sub", "Ilegible"], unreadable=["Ilegible"]
    )
    assert paths() == {"2024", "Nueva", "Nueva/Sub", "Ilegible", "Ilegible/Dentro"}, paths()
    assert (added, removed) == (2, 5), (added, removed)  # fuera: 2024b, 2024b/x, Vacía, Viejo...
    assert sync_folders(db, 1, "Nueva", [], complete=False) == (0, 0)
    assert "Nueva/Sub" in paths()
    assert sync_folders(db, 1, "Nueva", []) == (0, 1)  # recorrida entera: «Sub» ya no está
    assert paths() == {"2024", "Nueva", "Ilegible", "Ilegible/Dentro"}
    assert sync_folders(db, 1, "Otra/Honda", ["Otra/Honda/x"]) == (3, 0)  # con las de encima
    assert paths(2) == {"2024"}  # la otra ubicación, intacta
    print("3. Sincronizar: apuntar las vistas, quitar las que ya no están")

    # 4. Para el árbol, por ubicación; se van con su ubicación
    assert folder_paths(db)[2] == ["2024"] and "Otra/Honda/x" in folder_paths(db)[1]
    db.execute("DELETE FROM storage_locations WHERE id = 2")
    assert 2 not in folder_paths(db)
    print("4. Todas, por ubicación; se van con ella")
    print("Autoprueba finalizada correctamente.")
