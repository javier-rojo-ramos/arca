"""Lectura de las PALABRAS CLAVE de un archivo (etiquetas de ExifTool).

Este módulo NO depende de Qt ni de la base de datos: recibe las etiquetas que ExifTool
ha leído (con el sidecar ya combinado) y devuelve qué palabras clave trae el archivo.
Guardarlas en el catálogo es cosa de 'core/catalog/keywords.py'.

Cómo las guarda Lightroom Classic (comprobado el 03/11/2026 con un HEIC y un NEF con su
sidecar, Lightroom Classic 15.6):

    XMP-lr:HierarchicalSubject   ["Coche", "Coche|Toyota Corolla"]
        Las palabras ASIGNADAS, cada una con su ruta completa separada por '|'. Los padres
        de la ruta (aquí «Coche» en la segunda) NO están asignados por estar en ella: si
        aparecen solos, como la primera entrada, es porque también se asignaron.
    XMP-dc:Subject               ["Coche", "Toyota Corolla"]
        La lista plana, la que entienden todos los programas (sin jerarquía).
    XMP-lr:WeightedFlatSubject   copia interna de Lightroom: no se usa.
    IPTC:Keywords                la lista plana en IPTC (otros programas y archivos antiguos).

Regla de lectura:
    1. Cada entrada de 'HierarchicalSubject' es una palabra asignada con su ruta.
    2. De la lista plana ('dc:Subject' o, si falta, 'IPTC:Keywords') solo cuentan las
       palabras que NO aparecen ya en esas rutas (son la copia plana). Las que quedan las
       escribió otro programa sin jerarquía: se devuelven aparte ('flat') para que el
       catálogo las coloque (ver 'core/catalog/keywords.py').

Prueba rápida (con las etiquetas reales de los archivos del autor):
    python -m core.metadata.keyword_tags
"""

__version__ = "1.0.0"
__all__ = ["HIERARCHY_SEPARATOR", "FileKeywords", "read_keywords"]

# Librerías estándar
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Módulos del proyecto
from core.catalog.catalog_schema import fold_text
from core.metadata.field_spec import lookup

# Separador de la ruta en 'lr:hierarchicalSubject' («Familia|Papá»)
HIERARCHY_SEPARATOR = "|"

# Etiquetas, por orden de prioridad
_HIERARCHICAL_SOURCES = ("XMP-lr:HierarchicalSubject",)
_FLAT_SOURCES = ("XMP-dc:Subject", "IPTC:Keywords")


@dataclass(frozen=True, slots=True)
class FileKeywords:
    """Palabras clave que trae un archivo.

    Attributes:
        paths: Palabras asignadas con su ruta completa, de la raíz a la palabra
            (('Coche', 'Toyota Corolla') = «Toyota Corolla» dentro de «Coche»).
        flat: Palabras sueltas de la lista plana que no están en ninguna ruta (sin
            jerarquía conocida: el catálogo decide dónde van).
    """

    paths: tuple[tuple[str, ...], ...] = ()
    flat: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True si el archivo no trae ninguna palabra clave."""
        return not self.paths and not self.flat


def _as_list(value: Any) -> list[str]:
    """Una etiqueta de lista de ExifTool como lista de textos.

    Con una sola palabra, ExifTool puede devolver un texto suelto en vez de una lista; y
    una palabra numérica («2005») llega como número.
    """
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    return [str(item).strip() for item in items if item is not None and str(item).strip()]


def _first_list(tags: Mapping[str, Any], sources: tuple[str, ...]) -> list[str]:
    """La primera etiqueta de 'sources' que exista, como lista."""
    for source in sources:
        values = _as_list(lookup(tags, source))
        if values:
            return values
    return []


def read_keywords(tags: Mapping[str, Any]) -> FileKeywords:
    """Palabras clave de un archivo a partir de sus etiquetas de ExifTool (ver cabecera).

    Las repetidas (ignorando mayúsculas y acentos) se cuentan una vez, en el orden en
    que aparecen.
    """
    paths: list[tuple[str, ...]] = []
    seen_paths: set[tuple[str, ...]] = set()
    covered: set[str] = set()  # nombres (normalizados) que ya están en alguna ruta
    for entry in _first_list(tags, _HIERARCHICAL_SOURCES):
        parts = tuple(part.strip() for part in entry.split(HIERARCHY_SEPARATOR) if part.strip())
        if not parts:
            continue
        key = tuple(fold_text(part) for part in parts)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        paths.append(parts)
        covered.update(key)

    flat: list[str] = []
    for name in _first_list(tags, _FLAT_SOURCES):
        key = fold_text(name)
        if key in covered:
            continue  # copia plana de una palabra de las rutas
        covered.add(key)
        flat.append(name)
    return FileKeywords(paths=tuple(paths), flat=tuple(flat))


if __name__ == "__main__":
    # Autoprueba con las etiquetas REALES de los archivos del autor (03/11/2026).
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.keyword_tags

    # 1. HEIC con «Coche» y «Coche > Toyota Corolla» asignadas
    heic = {
        "XMP-dc:Subject": ["Coche", "Toyota Corolla"],
        "XMP-lr:WeightedFlatSubject": ["Toyota Corolla", "Coche"],
        "XMP-lr:HierarchicalSubject": ["Coche", "Coche|Toyota Corolla"],
    }
    result = read_keywords(heic)
    assert result.paths == (("Coche",), ("Coche", "Toyota Corolla")), result
    assert result.flat == (), result  # la lista plana es la copia de las rutas
    print("HEIC: Coche y Coche > Toyota Corolla")

    # 2. NEF: sus palabras vienen del sidecar (ya combinado), sin jerarquía
    nef = {
        "XMP-dc:Subject": ["Prueba Key 1", "Prueba Key 2"],
        "XMP-lr:HierarchicalSubject": ["Prueba Key 1", "Prueba Key 2"],
    }
    assert read_keywords(nef).paths == (("Prueba Key 1",), ("Prueba Key 2",))
    print("NEF: dos palabras de primer nivel")

    # 3. Solo «Toyota Corolla» asignada: el padre está en la ruta, pero no asignado
    child_only = {
        "XMP-dc:Subject": ["Toyota Corolla"],
        "XMP-lr:HierarchicalSubject": "Coche|Toyota Corolla",  # una sola: texto suelto
    }
    assert read_keywords(child_only).paths == (("Coche", "Toyota Corolla"),)

    # 4. Otro programa: solo la lista plana (o solo IPTC), sin jerarquía
    other_app = read_keywords({"XMP-dc:Subject": ["Papá", "Playa"]})
    assert other_app.paths == () and other_app.flat == ("Papá", "Playa")
    assert read_keywords({"IPTC:Keywords": "Nieve"}).flat == ("Nieve",)
    # La plana de XMP manda sobre la de IPTC
    assert read_keywords({"XMP-dc:Subject": ["A"], "IPTC:Keywords": ["B"]}).flat == ("A",)

    # 5. Mezcla: lo que no está en las rutas queda aparte; repetidas y vacías, fuera
    mixed = read_keywords(
        {
            "XMP-lr:HierarchicalSubject": ["Familia|Papá", "familia|papá", " | ", "Familia| Papá "],
            "XMP-dc:Subject": ["Papá", "Familia", "Atardecer", "atardecer", 2005],
        }
    )
    assert mixed.paths == (("Familia", "Papá"),), mixed
    assert mixed.flat == ("Atardecer", "2005"), mixed

    # 6. Sin palabras
    assert read_keywords({}).is_empty and read_keywords({"XMP-dc:Subject": []}).is_empty
    print("Autoprueba finalizada correctamente.")
