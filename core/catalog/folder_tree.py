"""Árbol de carpetas del catálogo, con el número de elementos de cada carpeta.

Este módulo NO depende de Qt. 'fetch_folder_tree' recibe la conexión como primer
parámetro, así que se envía tal cual a 'CatalogDatabaseManager.execute_async'.

Lo usa la sección "Carpetas" de la barra lateral del catálogo. El árbol es el del
CATÁLOGO, no el del disco: solo aparecen las carpetas que contienen algún elemento del
catálogo (directamente o en sus subcarpetas), y los contadores cuentan todo lo que hay
en la base de datos, también los archivos ausentes o de discos desconectados (como en
Lightroom). Una carpeta vacía en disco, o con solo archivos que no se catalogan, no sale.

Estructura que devuelve:

    LocationNode  "IMAGENES"  (una por ubicación de almacenamiento)
    └── root: FolderNode ''                 22607  (todo lo de la ubicación)
        ├── FolderNode 'Álbumes'              209
        └── FolderNode 'Organizadas'        20474
            ├── FolderNode 'Organizadas/2000'  53
            └── ...

Cada carpeta lleva dos contadores: 'count' INCLUYE las subcarpetas (como Lightroom) y
'direct_count' solo lo que está directamente en ella (el que se muestra cuando la opción
"Mostrar los elementos de las subcarpetas" está desactivada). Para no cargar todas las rutas
en memoria, la consulta agrupa por carpeta en SQLite y aquí solo se suman los totales
de cada carpeta hacia sus carpetas padre.

1.2.0 'fetch_folder_tree(conn, library)': el árbol de una sola biblioteca (las «Carpetas»
      del módulo Imagen): cuenta solo sus elementos y deja fuera las ubicaciones y
      carpetas sin ninguno (por su CONTENIDO, no por el tipo declarado al añadirlas;
      decidido por el autor el 04/11/2026).
1.1.0 'FolderNode.direct_count': elementos de la carpeta sin contar sus subcarpetas.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.folder_tree
"""

__version__ = "1.2.0"
__all__ = ["FolderNode", "LocationNode", "build_folder_tree", "fetch_folder_tree", "sort_key"]

# Librerías estándar
import re
import sqlite3
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

# Trozos de un nombre: números y texto por separado (para el orden natural)
_NUMBER_PARTS = re.compile(r"(\d+)")


def sort_key(name: str) -> tuple:
    """Clave para ordenar nombres como lo haría una persona (y como el Explorador).

    - Sin distinguir mayúsculas ni acentos: 'Álbumes' va antes que 'Organizadas'
      (comparando el texto tal cual, la 'Á' iría después de todas las letras sin acento).
    - Orden natural de los números: 'Viaje 2' antes que 'Viaje 10'.
    Al final se añade el nombre original para que el orden sea siempre el mismo.
    """
    decomposed = unicodedata.normalize("NFD", name.casefold())
    folded = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    parts = tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in _NUMBER_PARTS.split(folded)
        if part
    )
    return parts, name


@dataclass(frozen=True, slots=True)
class FolderNode:
    """Una carpeta del árbol.

    Es inmutable, así que dos árboles se pueden comparar con '==' (la barra lateral no
    reconstruye el árbol si no ha cambiado nada).

    Attributes:
        name: Nombre de la carpeta ('' en la raíz de la ubicación).
        relative_path: Ruta relativa a la ubicación, con '/' ('' = la raíz).
        count: Elementos del catálogo en esta carpeta Y en sus subcarpetas.
        children: Subcarpetas, ordenadas por nombre (ver 'sort_key').
        direct_count: Elementos que están directamente en esta carpeta (sin los de sus
            subcarpetas).
    """

    name: str
    relative_path: str
    count: int
    children: tuple["FolderNode", ...] = ()
    direct_count: int = 0


@dataclass(frozen=True, slots=True)
class LocationNode:
    """Una ubicación de almacenamiento con su árbol de carpetas.

    Attributes:
        location_id: 'storage_locations.id'.
        name: Nombre de la ubicación (normalmente, el de su carpeta raíz).
        absolute_path: Ruta absoluta de la carpeta raíz (para mostrarla en el tooltip).
        is_online: False si el disco o la unidad de red no está conectado.
        root: La carpeta raíz; su 'count' es el total de la ubicación.
    """

    location_id: int
    name: str
    absolute_path: str
    is_online: bool
    root: FolderNode


def fetch_folder_tree(conn: sqlite3.Connection, library: str | None = None) -> tuple[LocationNode, ...]:
    """Lee las ubicaciones y el número de elementos de cada carpeta.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        library: Solo los elementos de esa biblioteca ('image'...). None = todos.

    Returns:
        Las ubicaciones ordenadas por nombre, cada una con su árbol de carpetas. Sin
        biblioteca, las ubicaciones sin elementos también aparecen (con 0); con una
        biblioteca, solo las que tienen algo de ella (y solo sus carpetas con algo).
    """
    # Carpeta de cada archivo, sin sacar las rutas a Python: 'rtrim(ruta, caracteres)'
    # quita del final todos los caracteres que estén en el conjunto dado. Si el conjunto
    # son los caracteres de la ruta SIN las '/', se detiene justo en la última '/':
    #     'Organizadas/2000/foto.jpg'  ->  'Organizadas/2000/'
    #     'foto.jpg' (en la raíz)      ->  ''
    where, params = ("WHERE library = ?", (library,)) if library is not None else ("", ())
    rows = conn.execute(
        f"""SELECT storage_location_id,
                  rtrim(relative_path, replace(relative_path, '/', '')) AS folder,
                  COUNT(*)
             FROM media_items
             {where}
         GROUP BY storage_location_id, folder""",  # noqa: S608 - 'where' es fijo
        params,
    ).fetchall()

    direct: dict[int, dict[str, int]] = {}
    for location_id, folder, count in rows:
        # Sin la '/' final: 'Organizadas/2000/' -> 'Organizadas/2000'
        direct.setdefault(location_id, {})[folder.rstrip("/")] = int(count)

    locations = conn.execute(
        "SELECT id, name, absolute_path, is_online FROM storage_locations"
    ).fetchall()
    nodes = [
        LocationNode(
            location_id=location_id,
            name=name,
            absolute_path=absolute_path,
            is_online=bool(is_online),
            root=build_folder_tree(direct.get(location_id, {})),
        )
        for location_id, name, absolute_path, is_online in locations
    ]
    if library is not None:
        nodes = [node for node in nodes if node.root.count > 0]
    nodes.sort(key=lambda node: (sort_key(node.name), node.location_id))
    return tuple(nodes)


def build_folder_tree(direct_counts: Mapping[str, int]) -> FolderNode:
    """Construye el árbol a partir de los elementos que hay DIRECTAMENTE en cada carpeta.

    Es la parte "pura" de 'fetch_folder_tree' (sin base de datos), para poder probarla.

    Args:
        direct_counts: Carpeta relativa ('' = raíz) -> elementos que están directamente
            en ella (sin contar sus subcarpetas).

    Returns:
        La carpeta raíz, con los totales ya sumados hacia arriba y las carpetas
        intermedias sin archivos propios creadas (p. ej. 'Organizadas' si solo tiene
        archivos en 'Organizadas/2000').
    """
    # 1. Total de cada carpeta = lo suyo + lo de todas sus subcarpetas: cada carpeta suma
    #    su número a ella misma y a todas sus carpetas padre (hasta la raíz, '')
    totals: dict[str, int] = {"": 0}
    for folder, count in direct_counts.items():
        parts = folder.split("/") if folder else []
        for depth in range(len(parts) + 1):
            prefix = "/".join(parts[:depth])
            totals[prefix] = totals.get(prefix, 0) + count

    # 2. Hijos de cada carpeta (las carpetas intermedias ya están en 'totals')
    children: dict[str, list[str]] = {}
    for folder in totals:
        if folder:
            parent = folder.rpartition("/")[0]  # 'a/b' -> 'a';  'a' -> ''
            children.setdefault(parent, []).append(folder)

    def make(folder: str) -> FolderNode:
        names = sorted(children.get(folder, []), key=lambda path: sort_key(path.rpartition("/")[2]))
        return FolderNode(
            name=folder.rpartition("/")[2],
            relative_path=folder,
            count=totals[folder],
            children=tuple(make(child) for child in names),
            direct_count=direct_counts.get(folder, 0),
        )

    return make("")


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.folder_tree
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    # 1. Árbol puro: carpetas intermedias, totales con subcarpetas y orden por nombre
    tree = build_folder_tree({"": 2, "b/2001": 3, "b/2000": 4, "A": 1, "b/2000/sub": 5})
    assert tree.count == 15 and [c.name for c in tree.children] == ["A", "b"]
    b = tree.children[1]
    assert (b.relative_path, b.count) == ("b", 12)  # sin archivos propios: 3 + 4 + 5
    assert [(c.name, c.count) for c in b.children] == [("2000", 9), ("2001", 3)]
    assert b.children[0].children[0] == FolderNode("sub", "b/2000/sub", 5, (), 5)
    assert (tree.direct_count, b.direct_count, b.children[0].direct_count) == (2, 0, 4)
    assert build_folder_tree({}) == FolderNode("", "", 0)
    # Orden natural y sin acentos: 2 < 10, 'Álbumes' < 'Organizadas' < 'zeta'
    names = sorted(["Viaje 10", "zeta", "Viaje 2", "Organizadas", "Álbumes"], key=sort_key)
    assert names == ["Álbumes", "Organizadas", "Viaje 2", "Viaje 10", "zeta"], names
    # Comparables: dos árboles iguales son '==' (la barra lateral se ahorra reconstruir)
    assert build_folder_tree({"x": 1}) == build_folder_tree({"x": 1})

    # 2. Con la base de datos
    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('IMAGENES', 'D:/IMAGENES')")
    db.execute("INSERT INTO storage_locations(name, absolute_path, is_online) VALUES ('Tracks', 'E:/T', 0)")
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Vacía', 'F:/V')")
    for path, missing in (("raiz.jpg", 0), ("Organizadas/2000/a.jpg", 0), ("Organizadas/2000/b.jpg", 1),
                          ("Organizadas/2001/c.jpg", 0), ("Álbumes/d.jpg", 0)):  # fmt: skip
        db.execute(
            """INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type,
                   mime_type, file_size, file_mtime_ns, title, is_missing)
               VALUES (1, ?, ?, 'photo', 'image/jpeg', 1, 0, 'x', ?)""",
            (path, path.rsplit("/", 1)[-1], missing),
        )
    db.execute(
        """INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type,
               mime_type, file_size, file_mtime_ns, title)
           VALUES (2, 'Pirineo/ruta.gpx', 'ruta.gpx', 'track', 'application/gpx+xml', 1, 0, 'r')"""
    )

    locations = fetch_folder_tree(db)
    assert [loc.name for loc in locations] == ["IMAGENES", "Tracks", "Vacía"]
    images = locations[0]
    assert images.root.count == 5  # el ausente también cuenta (como en Lightroom)
    assert [c.name for c in images.root.children] == ["Álbumes", "Organizadas"]
    organized = images.root.children[1]
    assert organized.count == 3 and [(c.name, c.count) for c in organized.children] == [
        ("2000", 2), ("2001", 1)
    ]  # fmt: skip
    assert organized.children[0].relative_path == "Organizadas/2000"
    tracks = locations[1]
    assert not tracks.is_online and tracks.root.count == 1
    assert tracks.root.children[0].name == "Pirineo"
    assert locations[2].root == FolderNode("", "", 0)  # ubicación sin elementos
    print("Ubicaciones:", [(loc.name, loc.root.count) for loc in locations])

    # 3. Solo una biblioteca: sin las ubicaciones ni carpetas que no tienen nada de ella
    db.execute("UPDATE media_items SET library = 'image' WHERE media_type = 'photo'")
    db.execute("UPDATE media_items SET library = 'document' WHERE file_name = 'd.jpg'")  # p. ej. un escaneo
    only = fetch_folder_tree(db, "image")
    assert [loc.name for loc in only] == ["IMAGENES"], only  # ni «Tracks» ni «Vacía»
    assert only[0].root.count == 4 and [c.name for c in only[0].root.children] == ["Organizadas"]
    assert fetch_folder_tree(db, "video") == ()
    print("Solo una biblioteca: carpetas por su contenido")
    print("Autoprueba finalizada correctamente.")
