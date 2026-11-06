"""Colecciones del sistema: las que trae la aplicación en la sección "Colecciones".

Este módulo NO depende de Qt: describe el árbol (nombres, orden y reglas) y la barra
lateral lo dibuja. Son colecciones INTELIGENTES (por reglas, ver 'smart_rules.py'), así
que se actualizan solas y usan el mismo motor que las que creará el usuario (paso 1e):

    Clasificación              (con alguna estrella)
        Clasificación 1        (exactamente 1 estrella)
        ...
        Clasificación 5
    Etiqueta                   (con alguna etiqueta de color)
        Etiqueta 1 - Rojo
        Etiqueta 2 - Amarillo
        Etiqueta 3 - Verde
        Etiqueta 4 - Azul
        Etiqueta 5 - Púrpura
    Marcadas
    Rechazadas

El número de cada etiqueta es la tecla de Lightroom menos 5 (6 = roja... 9 = azul; la
púrpura no tiene tecla).

No se pueden borrar ni editar: no viven en la base de datos.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.system_collections
"""

__version__ = "1.0.0"
__all__ = ["SYSTEM_COLLECTIONS", "SystemCollection", "all_sources"]

# Librerías estándar
from collections.abc import Iterator
from dataclasses import dataclass

# Módulos del proyecto
from core.catalog.color_labels import COLOR_LABELS
from core.catalog.grid_source import GridSource, smart_source
from core.catalog.media_queries import FLAG_PICKED, FLAG_REJECTED
from core.catalog.smart_rules import Rule

# Nombre de cada color en la barra lateral (mismo orden que COLOR_LABELS)
_COLOR_NAMES: dict[str, str] = {
    "red": "Rojo",
    "yellow": "Amarillo",
    "green": "Verde",
    "blue": "Azul",
    "purple": "Púrpura",
}


@dataclass(frozen=True, slots=True)
class SystemCollection:
    """Una colección del sistema (o un grupo de ellas).

    Attributes:
        name: Texto que se muestra.
        source: Qué muestra al pulsarla.
        color_label: Si es la colección de un color, su nombre canónico ('red'...), para
            que la barra lateral pinte su muestra de color. None en las demás.
        children: Colecciones que cuelgan de esta (p. ej. las 5 clasificaciones).
    """

    name: str
    source: GridSource
    color_label: str | None = None
    children: tuple["SystemCollection", ...] = ()


def _build() -> tuple[SystemCollection, ...]:
    """Construye el árbol de colecciones del sistema."""
    ratings = SystemCollection(
        name="Clasificación",
        source=smart_source(Rule("rating", "gte", 1)),
        children=tuple(
            SystemCollection(f"Clasificación {stars}", smart_source(Rule("rating", "eq", stars)))
            for stars in range(1, 6)
        ),
    )
    labels = SystemCollection(
        name="Etiqueta",
        source=smart_source(Rule("color_label", "is_set")),
        children=tuple(
            SystemCollection(
                f"Etiqueta {number} - {_COLOR_NAMES[color]}",
                smart_source(Rule("color_label", "eq", color)),
                color_label=color,
            )
            for number, color in enumerate(COLOR_LABELS, start=1)
        ),
    )
    picked = SystemCollection("Marcadas", smart_source(Rule("flag", "eq", FLAG_PICKED)))
    rejected = SystemCollection("Rechazadas", smart_source(Rule("flag", "eq", FLAG_REJECTED)))
    return (ratings, labels, picked, rejected)


# Árbol de colecciones del sistema, en el orden en que aparecen
SYSTEM_COLLECTIONS: tuple[SystemCollection, ...] = _build()


def all_sources(collections: tuple[SystemCollection, ...] = SYSTEM_COLLECTIONS) -> Iterator[GridSource]:
    """Todos los orígenes del árbol (para contarlos), de arriba abajo."""
    for collection in collections:
        yield collection.source
        yield from all_sources(collection.children)


if __name__ == "__main__":
    # Autoprueba. Ejecutar desde la raíz del proyecto:  python -m core.catalog.system_collections
    names = [c.name for c in SYSTEM_COLLECTIONS]
    assert names == ["Clasificación", "Etiqueta", "Marcadas", "Rechazadas"], names
    assert [c.name for c in SYSTEM_COLLECTIONS[0].children] == [
        f"Clasificación {n}" for n in range(1, 6)
    ]
    assert [c.name for c in SYSTEM_COLLECTIONS[1].children] == [
        "Etiqueta 1 - Rojo", "Etiqueta 2 - Amarillo", "Etiqueta 3 - Verde",
        "Etiqueta 4 - Azul", "Etiqueta 5 - Púrpura",
    ]  # fmt: skip
    assert SYSTEM_COLLECTIONS[1].children[0].color_label == "red"
    sources = list(all_sources())
    assert len(sources) == 14 and len(set(sources)) == 14  # todos distintos
    print("Autoprueba finalizada correctamente.")
