"""Árbol de carpetas del catálogo, con el número de elementos de cada carpeta.

Este módulo NO depende de Qt. 'fetch_folder_tree' recibe la conexión como primer
parámetro, así que se envía tal cual a 'CatalogDatabaseManager.execute_async'.

Lo usa la sección "Carpetas" de la barra lateral del catálogo. El árbol replica las
carpetas del disco tal como estaban al sincronizar, como en Lightroom (CAT 5): las de los
elementos del catálogo y las apuntadas en la tabla 'folders' (las vacías o con solo archivos
que no se catalogan, con 0; ver 'catalog_folders.py'). Los contadores cuentan todo lo que
hay en la base de datos, también los archivos ausentes o de discos desconectados (como en
Lightroom). Con una biblioteca (las «Carpetas» del módulo Imagen) solo salen las carpetas
con algo de ella.

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

Además, mira en el disco qué carpetas ya no están (borradas, renombradas o movidas fuera de
la aplicación): 'FolderNode.is_missing', solo en la de más arriba de las que faltan (las de
dentro faltan con ella; la barra las atenúa). Es barato (915 carpetas en unos 6 ms, en un
disco local) y no escribe nada. Ver 'find_missing_folders'.

1.4.0 'FolderNode.is_missing' y 'find_missing_folders': las carpetas que ya no están en el
      disco (CAT 6.2).
1.3.0 Las carpetas sin elementos también (CAT 5): las de la tabla 'folders', con 0
      ('build_folder_tree(..., folders)'); no con una biblioteca.
1.2.0 'fetch_folder_tree(conn, library)': el árbol de una sola biblioteca (las «Carpetas»
      del módulo Imagen): cuenta solo sus elementos y deja fuera las ubicaciones y
      carpetas sin ninguno (por su CONTENIDO, no por el tipo declarado al añadirlas;
      decidido por el autor el 04/11/2026).
1.1.0 'FolderNode.direct_count': elementos de la carpeta sin contar sus subcarpetas.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.folder_tree
"""

__version__ = "1.4.0"
__all__ = [
    "FolderNode",
    "LocationNode",
    "build_folder_tree",
    "fetch_folder_tree",
    "find_missing_folders",
    "sort_key",
]

# Librerías estándar
import os
import re
import sqlite3
import stat
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

# Módulos del proyecto
from core.catalog.catalog_folders import folder_paths

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
        is_missing: La carpeta ya no está en el disco (con la ubicación conectada). Solo
            en la de más arriba de las que faltan: las de dentro siguen en False.
    """

    name: str
    relative_path: str
    count: int
    children: tuple["FolderNode", ...] = ()
    direct_count: int = 0
    is_missing: bool = False


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
        biblioteca, las ubicaciones y las carpetas sin elementos también aparecen (con 0);
        con una biblioteca, solo las que tienen algo de ella (y solo sus carpetas con algo).
        En las ubicaciones conectadas, las carpetas que ya no están en el disco llevan
        'is_missing' (ver 'find_missing_folders').
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
         GROUP BY storage_location_id, folder""",  # 'where' es fijo
        params,
    ).fetchall()

    direct: dict[int, dict[str, int]] = {}
    for location_id, folder, count in rows:
        # Sin la '/' final: 'Organizadas/2000/' -> 'Organizadas/2000'
        direct.setdefault(location_id, {})[folder.rstrip("/")] = int(count)

    # Las carpetas sin elementos (vacías, o solo con lo que no se cataloga): solo en el
    # árbol del Catálogo, que replica el disco
    empty = folder_paths(conn) if library is None else {}

    locations = conn.execute(
        "SELECT id, name, absolute_path, is_online FROM storage_locations"
    ).fetchall()
    nodes = []
    for location_id, name, absolute_path, is_online in locations:
        root = build_folder_tree(direct.get(location_id, {}), empty.get(location_id, ()))
        if is_online:
            root = _mark_missing(root, find_missing_folders(absolute_path, root))
        nodes.append(
            LocationNode(
                location_id=location_id,
                name=name,
                absolute_path=absolute_path,
                is_online=bool(is_online),
                root=root,
            )
        )
    if library is not None:
        nodes = [node for node in nodes if node.root.count > 0]
    nodes.sort(key=lambda node: (sort_key(node.name), node.location_id))
    return tuple(nodes)


def build_folder_tree(
    direct_counts: Mapping[str, int], folders: Iterable[str] = ()
) -> FolderNode:
    """Construye el árbol a partir de los elementos que hay DIRECTAMENTE en cada carpeta.

    Es la parte "pura" de 'fetch_folder_tree' (sin base de datos), para poder probarla.

    Args:
        direct_counts: Carpeta relativa ('' = raíz) -> elementos que están directamente
            en ella (sin contar sus subcarpetas).
        folders: Más carpetas, aunque no tengan elementos (salen con 0).

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
    for folder in folders:  # las que no tienen elementos (y las de encima), con 0
        parts = folder.split("/") if folder else []
        for depth in range(1, len(parts) + 1):
            totals.setdefault("/".join(parts[:depth]), 0)

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


def find_missing_folders(location_path: str | Path, root: FolderNode) -> frozenset[str]:
    """Carpetas del árbol que ya no están en el disco (solo las de más arriba).

    Se mira de arriba abajo y, si una carpeta falta, no se mira lo de dentro (falta con
    ella). Solo cuenta como que falta lo que el sistema dice que no existe (o que ya no es
    una carpeta): un error de otro tipo (permisos, una unidad de red que no responde) no
    permite saberlo, y esa carpeta ni se marca ni se mira por dentro.

    Con la misma precaución que el escáner ('mark_missing'), no se marca nada si la raíz
    de la ubicación no está o está vacía: un disco desmontado puede dejar su carpeta (el
    punto de montaje) vacía, y entonces faltaría todo.

    Args:
        location_path: Ruta absoluta de la raíz de la ubicación.
        root: Su árbol ('build_folder_tree').

    Returns:
        Las rutas relativas ('a/b') de las carpetas que faltan.
    """
    base = Path(location_path)
    try:
        with os.scandir(base) as entries:
            if next(entries, None) is None:
                return frozenset()
    except OSError:
        return frozenset()  # sin raíz (desconectada) o ilegible: no se sabe nada

    missing: set[str] = set()
    pending = list(root.children)
    while pending:
        node = pending.pop()
        try:
            info = os.stat(base / node.relative_path)
        except (FileNotFoundError, NotADirectoryError):
            missing.add(node.relative_path)
            continue
        except OSError:
            continue  # no se sabe: ni se marca ni se mira por dentro
        if not stat.S_ISDIR(info.st_mode):
            missing.add(node.relative_path)  # en su lugar hay un archivo
            continue
        pending.extend(node.children)
    return frozenset(missing)


def _mark_missing(node: FolderNode, missing: frozenset[str]) -> FolderNode:
    """El mismo árbol con 'is_missing' en las carpetas de 'missing' (el resto, igual)."""
    if not missing:
        return node
    if node.relative_path in missing:
        return replace(node, is_missing=True)
    if not node.children:
        return node
    return replace(node, children=tuple(_mark_missing(child, missing) for child in node.children))


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
    # Carpetas sin elementos (CAT 5): con 0, y las de encima; una con elementos no cambia
    tree = build_folder_tree({"b/2000": 4}, ["Vacía/Sub", "b", "b/2000"])
    assert [(c.name, c.count) for c in tree.children] == [("b", 4), ("Vacía", 0)], tree
    assert tree.children[1].children == (FolderNode("Sub", "Vacía/Sub", 0),)

    # 2. Con la base de datos
    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('IMAGENES', 'D:/IMAGENES')")
    db.execute("INSERT INTO storage_locations(name, absolute_path, is_online) VALUES ('Tracks', 'E:/T', 0)")
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Vacía', 'F:/V')")
    db.execute("INSERT INTO folders(storage_location_id, relative_path) VALUES (1, 'Sin fotos')")
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
    assert [c.name for c in images.root.children] == ["Álbumes", "Organizadas", "Sin fotos"]
    assert images.root.children[2].count == 0  # sin elementos: con 0 (CAT 5)
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

    # 4. Carpetas que faltan en el disco (CAT 6.2), con carpetas de verdad
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        disk = Path(tmp) / "Disco"
        for folder in ("A/A1", "B/B1/B11", "C"):
            (disk / folder).mkdir(parents=True)
        (disk / "D").write_bytes(b"")  # un archivo donde había una carpeta
        tree = build_folder_tree({"A/A1": 1, "B/B1/B11": 2, "C": 1, "D": 1, "E/E1": 3})
        assert find_missing_folders(disk, tree) == {"D", "E"}  # E1 falta con E: no se mira
        shutil.rmtree(disk / "B" / "B1")
        assert find_missing_folders(disk, tree) == {"B/B1", "D", "E"}
        marked = _mark_missing(tree, find_missing_folders(disk, tree))
        b = marked.children[1]
        assert not b.is_missing and b.children[0].is_missing  # B sigue; B1, no
        assert not b.children[0].children[0].is_missing  # B11 falta con B1 (sin marca)
        assert marked.children[0] == tree.children[0]  # lo que no falta, igual
        assert _mark_missing(tree, frozenset()) is tree
        # Sin raíz o con la raíz vacía (un disco desmontado): nada
        assert find_missing_folders(Path(tmp) / "No existe", tree) == frozenset()
        empty_root = Path(tmp) / "Vacía"
        empty_root.mkdir()
        assert find_missing_folders(empty_root, tree) == frozenset()

        # Con la base de datos: solo en las ubicaciones conectadas
        db.execute("UPDATE storage_locations SET absolute_path = ? WHERE id = 1", (str(disk),))
        db.execute("UPDATE storage_locations SET absolute_path = ? WHERE id = 2", (str(disk / "C"),))
        (disk / "Organizadas" / "2000").mkdir(parents=True)  # faltan 2001, Álbumes y Sin fotos
        images, tracks, _empty = fetch_folder_tree(db)
        flags = {c.name: c.is_missing for c in images.root.children}
        assert flags == {"Álbumes": True, "Organizadas": False, "Sin fotos": True}, flags
        organized = images.root.children[1]
        assert [(c.name, c.is_missing) for c in organized.children] == [
            ("2000", False), ("2001", True)
        ]  # fmt: skip
        assert not tracks.root.children[0].is_missing  # desconectada: no se mira
        assert [c.is_missing for c in fetch_folder_tree(db, "image")[0].root.children] == [False]
    print("Carpetas que faltan: solo la de más arriba y con la ubicación conectada")
    print("Autoprueba finalizada correctamente.")
