"""Origen de la cuadrícula: QUÉ elementos del catálogo se muestran.

Este módulo NO depende de Qt: es Python puro.

Cada elemento de la barra lateral del catálogo ("Todos los archivos", una carpeta, una
colección...) lleva asociado un 'GridSource'. Al hacer clic, la barra lateral lo emite y
el modelo de la cuadrícula se lo pasa a 'media_queries.fetch_grid_rows', que es el ÚNICO
sitio que lo traduce a SQL. Así:
    - la barra lateral no sabe nada de SQL, y
    - la cuadrícula no sabe nada de la barra lateral.

Es un dataclass inmutable ('frozen'): se puede comparar ('==') para saber si el usuario ha
vuelto a pulsar lo mismo, y usar como clave de un diccionario.

Tipos de origen:
    ALL         todo el catálogo                                          (paso 1a)
    FOLDER      una carpeta de una ubicación (con o sin sus subcarpetas)   (paso 1b)
    SMART       colección inteligente: un conjunto de reglas (smart_rules.py)  (paso 1c)
    COLLECTION  colección estática del usuario (user_collections.py)       (paso 1d)
    QUICK       la "Selección rápida": los archivos marcados con el círculo de la tarjeta
    KEYWORD     una palabra clave Y SUS HIJAS, dentro de una biblioteca (módulo Imagen)
Cada tipo nuevo necesita: un valor en 'SourceKind', sus campos aquí (con un constructor
como 'folder_source') y su caso en 'media_queries._source_condition'.

1.10.0 La selección rápida también puede limitarse a una biblioteca ('quick_source'): la
       del módulo Imagen solo muestra lo de la biblioteca Imagen. Sigue siendo UNA sola
       selección rápida para todo el catálogo; solo cambia lo que se ve.
1.9.0 Una carpeta puede limitarse a una biblioteca ('folder_source(..., library=...)'): las
      «Carpetas» del módulo Imagen solo muestran lo de la biblioteca Imagen.
1.8.0 Origen KEYWORD ('keyword_source'): una palabra clave con sus hijas, en una biblioteca.
1.7.0 'UNCLASSIFIED': elementos sin biblioteca (fila «Sin clasificar» de la sección Catálogo).
1.6.0 'source_to_dict' / 'source_from_dict': guardar en JSON qué estaba elegido (para
      volver a mostrarlo al abrir de nuevo el catálogo).
1.5.0 Origen QUICK ('QUICK_SELECTION'): la selección rápida.
1.4.0 'smart_collection_source': colección inteligente DEL USUARIO (reglas + su 'id').
1.3.0 Origen COLLECTION ('collection_source'): colección estática del usuario.
1.2.0 Origen SMART ('smart_source'): colecciones inteligentes por reglas.
1.1.0 Origen FOLDER ('folder_source').
"""

__version__ = "1.10.0"
__all__ = [
    "ALL_ITEMS",
    "GridSource",
    "QUICK_SELECTION",
    "SourceKind",
    "UNCLASSIFIED",
    "collection_source",
    "folder_source",
    "keyword_source",
    "library_source",
    "quick_source",
    "smart_collection_source",
    "smart_source",
    "source_from_dict",
    "source_to_dict",
]

# Librerías estándar
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# Módulos del proyecto
from core.catalog.smart_rules import MATCH_ALL, Rule, RuleSet, rules_from_json, rules_to_json


class SourceKind(StrEnum):
    """Tipo de origen de la cuadrícula."""

    ALL = "all"  # todo el catálogo (incluidos los archivos ausentes o desconectados)
    FOLDER = "folder"  # una carpeta de una ubicación de almacenamiento
    SMART = "smart"  # colección inteligente: un conjunto de reglas
    COLLECTION = "collection"  # colección estática del usuario
    QUICK = "quick"  # selección rápida ('media_items.in_quick_selection = 1')
    KEYWORD = "keyword"  # una palabra clave y sus hijas (tablas 'keywords' y 'media_keywords')


@dataclass(frozen=True, slots=True)
class GridSource:
    """Qué elementos del catálogo muestra la cuadrícula.

    Los campos que no usa un tipo de origen se quedan con su valor por defecto (así dos
    orígenes iguales siempre son '=='). Para crear uno, mejor usar 'ALL_ITEMS' o
    'folder_source(...)' que el constructor directamente.

    Attributes:
        kind: Tipo de origen (ver 'SourceKind').
        location_id: FOLDER: 'storage_locations.id' de la ubicación.
        folder: FOLDER: carpeta relativa a la ubicación, con '/' ('' = su raíz).
        include_subfolders: FOLDER: si también se muestran los elementos de las
            subcarpetas (por defecto sí, como los contadores del árbol).
        rules: SMART: las reglas de la colección inteligente.
        collection_id: COLLECTION: 'collections.id' de la colección. SMART: el de la
            colección inteligente del usuario (None en las del sistema). No cambia el SQL
            (lo deciden las reglas), pero distingue dos colecciones con las mismas reglas
            y permite encontrar la fila de la barra lateral aunque se editen sus reglas.
        keyword_id: KEYWORD: 'keywords.id' de la palabra (se incluyen sus hijas).
        library: KEYWORD: biblioteca a la que se limita ('image'...; None = todas).
    """

    kind: SourceKind = SourceKind.ALL
    location_id: int | None = None
    folder: str = ""
    include_subfolders: bool = True
    rules: RuleSet | None = None
    collection_id: int | None = None
    keyword_id: int | None = None
    library: str | None = None


def folder_source(
    location_id: int,
    folder: str = "",
    *,
    include_subfolders: bool = True,
    library: str | None = None,
) -> GridSource:
    """Origen de una carpeta de una ubicación.

    Args:
        location_id: 'storage_locations.id'.
        folder: Carpeta relativa a la ubicación ('' = toda la ubicación). Se admiten
            '/' o '\\' y se quitan las barras de los extremos.
        include_subfolders: Si se incluyen los elementos de las subcarpetas.
        library: Solo los elementos de esa biblioteca ('image'...); None = todos.
    """
    normalized = folder.replace("\\", "/").strip("/")
    return GridSource(
        kind=SourceKind.FOLDER,
        location_id=int(location_id),
        folder=normalized,
        include_subfolders=include_subfolders,
        library=library,
    )


def smart_source(*rules: Rule, match: str = MATCH_ALL) -> GridSource:
    """Origen de una colección inteligente.

    Ejemplo: 'smart_source(Rule("rating", "gte", 3), Rule("flag", "eq", 1))'
    (tres estrellas o más Y marcadas).

    Args:
        rules: Las reglas.
        match: MATCH_ALL (todas) o MATCH_ANY (alguna).
    """
    return GridSource(kind=SourceKind.SMART, rules=RuleSet(match=match, rules=tuple(rules)))


# Elementos sin biblioteca (hoy, vídeos de carpetas automáticas cuyo nombre no dice si son
# clips o películas): fila «Sin clasificar» de la sección Catálogo. Es una colección
# inteligente fija, como las del sistema ('core/catalog/system_collections.py')
UNCLASSIFIED = smart_source(Rule("library", "is_not_set"))


def smart_collection_source(collection_id: int, rules: RuleSet) -> GridSource:
    """Origen de una colección inteligente del usuario ('collections.id' y sus reglas)."""
    return GridSource(kind=SourceKind.SMART, rules=rules, collection_id=int(collection_id))


def keyword_source(keyword_id: int, library: str | None = None) -> GridSource:
    """Origen de una palabra clave y sus hijas ('keywords.id'), opcionalmente en una biblioteca."""
    return GridSource(kind=SourceKind.KEYWORD, keyword_id=int(keyword_id), library=library)


def library_source(library: str) -> GridSource:
    """Todo lo de una biblioteca ('image', 'video'...): una colección inteligente fija."""
    return smart_source(Rule("library", "eq", library))


def collection_source(collection_id: int) -> GridSource:
    """Origen de una colección estática del usuario ('collections.id')."""
    return GridSource(kind=SourceKind.COLLECTION, collection_id=int(collection_id))


# Origen por defecto: todo el catálogo ("Todos los archivos" en la barra lateral)
ALL_ITEMS = GridSource()

# La "Selección rápida" (sección Catálogo de la barra lateral). Solo hay una: no lleva datos
QUICK_SELECTION = GridSource(kind=SourceKind.QUICK)


def quick_source(library: str | None = None) -> GridSource:
    """La selección rápida, opcionalmente solo con lo de una biblioteca ('image'...)."""
    return GridSource(kind=SourceKind.QUICK, library=library) if library else QUICK_SELECTION


# -----------------------------------------------------------------------------
# Guardar y recuperar un origen (JSON)
# -----------------------------------------------------------------------------


def source_to_dict(source: GridSource) -> dict[str, Any]:
    """Convierte un origen en un diccionario que se puede guardar en JSON.

    Solo guarda lo necesario para encontrarlo otra vez:
        ALL, QUICK                 -> solo el tipo (QUICK de una biblioteca: y cuál)
        FOLDER                     -> ubicación y carpeta ('include_subfolders' no: lo
                                      decide la opción actual al recuperarlo)
        COLLECTION                 -> su id
        KEYWORD                    -> id de la palabra y biblioteca
        SMART del usuario          -> su id (sus reglas se leen de la base de datos)
        SMART del sistema          -> sus reglas (no tienen id)
    """
    data: dict[str, Any] = {"kind": str(source.kind)}
    match source.kind:
        case SourceKind.QUICK if source.library is not None:
            data["library"] = source.library
        case SourceKind.FOLDER:
            data["location_id"] = source.location_id
            data["folder"] = source.folder
            if source.library is not None:
                data["library"] = source.library
        case SourceKind.COLLECTION:
            data["collection_id"] = source.collection_id
        case SourceKind.KEYWORD:
            data["keyword_id"] = source.keyword_id
            data["library"] = source.library
        case SourceKind.SMART if source.collection_id is not None:
            data["collection_id"] = source.collection_id
        case SourceKind.SMART if source.rules is not None:
            data["rules"] = rules_to_json(source.rules)
    return data


def source_from_dict(data: object, *, include_subfolders: bool = True) -> GridSource | None:
    """Recupera un origen guardado con 'source_to_dict'.

    OJO: una colección inteligente DEL USUARIO vuelve SIN reglas (solo su id): no se puede
    mostrar hasta completarla con las de la base de datos (lo hace la barra lateral al
    recibir el árbol de colecciones).

    Args:
        data: Lo guardado (si no se entiende, se devuelve None).
        include_subfolders: Para una carpeta, la opción actual de subcarpetas.

    Returns:
        El origen, o None si los datos no son válidos (de otra versión, editados a mano...).
    """
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    collection_id = data.get("collection_id")
    valid_id = isinstance(collection_id, int) and not isinstance(collection_id, bool)
    if kind == SourceKind.ALL:
        return ALL_ITEMS
    if kind == SourceKind.QUICK:
        library = data.get("library")
        return quick_source(library) if isinstance(library, str) else QUICK_SELECTION
    if kind == SourceKind.FOLDER:
        location_id, folder, library = data.get("location_id"), data.get("folder"), data.get("library")
        if (
            isinstance(location_id, int)
            and not isinstance(location_id, bool)
            and isinstance(folder, str)
            and (library is None or isinstance(library, str))
        ):
            return folder_source(location_id, folder, include_subfolders=include_subfolders, library=library)
        return None
    if kind == SourceKind.COLLECTION:
        return collection_source(collection_id) if valid_id else None
    if kind == SourceKind.KEYWORD:
        keyword_id, library = data.get("keyword_id"), data.get("library")
        if isinstance(keyword_id, int) and not isinstance(keyword_id, bool) and (
            library is None or isinstance(library, str)
        ):
            return keyword_source(keyword_id, library)
        return None
    if kind == SourceKind.SMART:
        if valid_id:
            return GridSource(kind=SourceKind.SMART, collection_id=collection_id)
        try:
            return GridSource(kind=SourceKind.SMART, rules=rules_from_json(data.get("rules")))
        except ValueError:
            return None  # reglas ilegibles (p. ej. un campo que ya no existe)
    return None


if __name__ == "__main__":
    # Autoprueba. Ejecutar desde la raíz del proyecto:  python -m core.catalog.grid_source
    # OJO: al ejecutarse como '__main__', las clases de este archivo NO son las mismas que
    # las de 'core.catalog.grid_source' (que usan las colecciones del sistema): se prueba
    # el módulo importado para comparar objetos de la misma clase
    import json

    from core.catalog.grid_source import (  # noqa: F811 - a propósito (ver arriba)
        ALL_ITEMS,
        QUICK_SELECTION,
        GridSource,
        SourceKind,
        collection_source,
        folder_source,
        keyword_source,
        library_source,
        quick_source,
        smart_collection_source,
        source_from_dict,
        source_to_dict,
    )
    from core.catalog.system_collections import all_sources

    samples = [
        ALL_ITEMS,
        QUICK_SELECTION,
        folder_source(3, "Fotos/2024"),
        folder_source(3, ""),
        collection_source(12),
        keyword_source(5, "image"),
        keyword_source(5),
        library_source("image"),
        *all_sources(),  # colecciones del sistema: se recuperan por sus reglas
    ]
    for original in samples:
        text = json.dumps(source_to_dict(original))  # tiene que poder guardarse en JSON
        assert source_from_dict(json.loads(text)) == original, original
    # La opción de subcarpetas la decide quien recupera
    restored = source_from_dict(source_to_dict(folder_source(3, "a")), include_subfolders=False)
    assert restored == folder_source(3, "a", include_subfolders=False)
    # Selección rápida de una biblioteca: se guarda y se recupera con ella
    image_quick = quick_source("image")
    assert source_from_dict(json.loads(json.dumps(source_to_dict(image_quick)))) == image_quick
    assert image_quick != QUICK_SELECTION and quick_source() == QUICK_SELECTION
    # Carpeta de una biblioteca: se guarda y se recupera con ella
    image_folder = folder_source(3, "a", library="image")
    assert source_from_dict(json.loads(json.dumps(source_to_dict(image_folder)))) == image_folder
    assert image_folder != folder_source(3, "a")  # otra cuadrícula: no es el mismo origen
    # Inteligente del usuario: vuelve solo con su id
    user_smart = smart_collection_source(7, RuleSet(rules=(Rule("rating", "gte", 4),)))
    assert source_from_dict(source_to_dict(user_smart)) == GridSource(
        kind=SourceKind.SMART, collection_id=7
    )
    # Datos que no se entienden: None (nunca una excepción)
    for bad in (None, [], {}, {"kind": "nope"}, {"kind": "folder", "location_id": "1"},
                {"kind": "collection", "collection_id": True}, {"kind": "smart", "rules": "{"},
                {"kind": "keyword", "keyword_id": "5"}, {"kind": "keyword", "keyword_id": 5, "library": 3}):  # fmt: skip
        assert source_from_dict(bad) is None, bad
    print("Autoprueba finalizada correctamente.")
