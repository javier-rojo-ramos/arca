"""Sección «Fechas» de la barra de un módulo: la línea de tiempo (año > mes > día).

Este módulo NO depende de Qt. 'fetch_timeline' recibe la conexión SQLite como primer
parámetro, así que se puede enviar tal cual a 'CatalogDatabaseManager.execute_async'.

Cuenta los archivos de una biblioteca por su fecha de captura ('content_created_at', en
hora local: el día es el del lugar de la foto) y da el origen de la cuadrícula de cada
fila. No tiene SQL propio: reutiliza la columna «Fecha de captura» de «Metadatos»
('metadata_values.fetch_metadata_values') y su regla ('grid_filter.metadata_rule'). Así,
cada fila cuenta exactamente lo que la cuadrícula muestra al elegirla (lo comprueba la
autoprueba) y la sección coincide siempre con el filtro.

Uso:
    timeline = fetch_timeline(conn, "image")     # en segundo plano
    timeline.values      # años, del más reciente al más antiguo; al final, si hay archivos
                         # sin fecha, la fila «Sin fecha» (valor NO_DATE)
    year = timeline.values[0]
    year.value, year.count   # '2024', 412
    year.children            # sus meses, en el orden del calendario ('2024-01'...); en
                             # cada mes, sus días con archivos ('2024-01-10'...)
    date_source("image", "2024-03")   # origen de la cuadrícula de una fila
    is_date_source(source, "image")   # si un origen (p. ej. el guardado) es de la sección

Valores de las filas (los de 'metadata_rule'): 'AAAA' (año), 'AAAA-MM' (mes), 'AAAA-MM-DD'
(día) o NO_DATE (None: archivos sin fecha de captura). Una fecha de la que solo se sabe el
año o el mes se guarda completada con el día 1 ('catalog_schema'): cuenta en ese día, igual
que en el filtro (decidido por el autor el 12/11/2026).

Los textos que ve el usuario («01 Enero», «01 Martes», «Sin fecha»...) no están aquí: los
pone la interfaz.

1.0.0 Primera versión (paso A.4, sección «Fechas» del módulo Imagen).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.timeline
"""

__version__ = "1.0.0"
__all__ = ["DATE_FIELD", "NO_DATE", "date_source", "fetch_timeline", "is_date_source"]

# Librerías estándar
import sqlite3

# Módulos del proyecto
from core.catalog.grid_filter import METADATA_UNKNOWN, metadata_rule
from core.catalog.grid_source import GridSource, SourceKind, library_source, smart_source
from core.catalog.metadata_values import MetadataValues, fetch_metadata_values
from core.catalog.smart_rules import MATCH_ALL, Rule

# Campo de 'smart_fields' por el que se ordena la línea de tiempo ('content_created_at')
DATE_FIELD = "captured_at"
# Valor de la fila «Sin fecha» (el «Desconocido» de las columnas de «Metadatos»)
NO_DATE = METADATA_UNKNOWN


def fetch_timeline(conn: sqlite3.Connection, library: str) -> MetadataValues:
    """Años > meses > días con sus recuentos, entre los archivos de una biblioteca.

    Args:
        conn: Conexión (la pone el gestor de la base de datos).
        library: Biblioteca ('image'...).

    Returns:
        Lo mismo que la columna «Fecha de captura» de «Metadatos» con el origen
        «Todas las imágenes» (ver el docstring del módulo). 'total' cuenta toda la
        biblioteca, también lo que no tiene fecha.
    """
    return fetch_metadata_values(conn, library_source(library), DATE_FIELD)


def date_source(library: str, value: str | None) -> GridSource:
    """Origen de la cuadrícula de una fila: lo de la biblioteca con esa fecha de captura.

    Es una colección inteligente fija (como «Todas las imágenes»): la biblioteca y la
    regla de la fecha. Se guarda y se recupera con 'source_to_dict' / 'source_from_dict'.

    Args:
        library: Biblioteca ('image'...).
        value: 'AAAA', 'AAAA-MM', 'AAAA-MM-DD' o NO_DATE («Sin fecha»).

    Raises:
        ValueError: Si el valor no es un año, un mes ni un día válidos, ni NO_DATE.
    """
    rule = metadata_rule(DATE_FIELD, value)
    if rule is None:
        raise ValueError(f"Fecha no válida para la línea de tiempo: {value!r}")
    return smart_source(Rule("library", "eq", library), rule)


def is_date_source(source: GridSource, library: str) -> bool:
    """Si un origen es el de una fila de la sección de esa biblioteca ('date_source').

    Sirve para recuperar la fila elegida al abrir el catálogo: el árbol llega después
    (se lee en segundo plano) y hasta entonces no se puede buscar la fila.
    """
    rules = source.rules
    if source.kind != SourceKind.SMART or source.collection_id is not None or rules is None:
        return False
    if rules.match != MATCH_ALL or len(rules.rules) != 2:
        return False
    library_rule, date_rule = rules.rules
    return (
        library_rule == Rule("library", "eq", library)
        and isinstance(date_rule, Rule)
        and date_rule.field == DATE_FIELD
    )


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.timeline
    import json
    from typing import Any

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.grid_source import source_from_dict, source_to_dict
    from core.catalog.media_queries import source_condition
    from core.catalog.metadata_values import MetadataValue

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('P', '/tmp/p')")

    def add(name: str, created: str | None, library: str | None = "image",
            media_type: str = "photo") -> None:  # fmt: skip
        columns: dict[str, Any] = {
            "storage_location_id": 1, "relative_path": name, "file_name": name,
            "media_type": media_type, "mime_type": "x/y", "file_size": 1, "file_mtime_ns": 0,
            "title": name, "library": library, "content_created_at": created,
        }  # fmt: skip
        db.execute(
            f"INSERT INTO media_items({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
            tuple(columns.values()),
        )

    add("a.jpg", "2024-01-10 10:00:00")
    add("b.jpg", "2024-01-10 18:30:00")
    add("c.jpg", "2024-01-19 09:00:00")
    add("d.mov", "2024-02-11 12:00:00", media_type="video")  # vídeo del móvil: también cuenta
    add("e.jpg", "2023-12-31 23:59:59")
    add("f.jpg", "2003-01-01 00:00:00")  # solo se sabe el año: cuenta el 1 de enero
    add("g.jpg", None)  # sin fecha
    add("h.mp4", "2024-01-10 10:00:00", library="video", media_type="video")  # otra biblioteca
    add("i.mp4", "2024-03-01 10:00:00", library=None, media_type="video")  # sin clasificar

    # 1. El árbol: años del más reciente al más antiguo; meses y días, en su orden
    timeline = fetch_timeline(db, "image")
    assert timeline.total == 7, timeline.total
    years = [(v.value, v.count) for v in timeline.values]
    assert years == [("2024", 4), ("2023", 1), ("2003", 1), (NO_DATE, 1)], years
    months = timeline.values[0].children
    assert [(m.value, m.count) for m in months] == [("2024-01", 3), ("2024-02", 1)]
    assert [(d.value, d.count) for d in months[0].children] == [
        ("2024-01-10", 2), ("2024-01-19", 1)]  # fmt: skip
    assert timeline.values[2].children[0].children == (MetadataValue("2003-01-01", 1),)
    # Una biblioteca sin nada: sin filas
    assert fetch_timeline(db, "audio").values == ()

    # 2. Lo importante: elegir una fila muestra EXACTAMENTE los archivos que cuenta
    def check(value: MetadataValue) -> None:
        where, params = source_condition(date_source("image", value.value))
        (found,) = db.execute(f"SELECT COUNT(*) FROM media_items AS m WHERE {where}", params).fetchone()
        assert found == value.count, (value.value, found, value.count)
        for child in value.children:
            check(child)

    for value in timeline.values:
        check(value)

    # 3. Los orígenes se guardan en JSON y se recuperan iguales (la fila elegida, por catálogo)
    for value in ("2024", "2024-01", "2024-01-10", NO_DATE):
        source = date_source("image", value)
        restored = source_from_dict(json.loads(json.dumps(source_to_dict(source))))
        assert restored == source, (value, restored)
        assert is_date_source(restored, "image")
        assert not is_date_source(restored, "video")  # de otra biblioteca
    # «Todas las imágenes» y las demás colecciones fijas no son de la sección
    assert not is_date_source(library_source("image"), "image")
    rated = smart_source(Rule("library", "eq", "image"), Rule("rating", "gte", 3))
    assert not is_date_source(rated, "image")

    # 4. Un valor que no es fecha, rechazado
    for bad in ("2024-13", "2024-02-30", "24", 2024, "", "2024-1"):
        try:
            date_source("image", bad)
            raise AssertionError(f"debía rechazar {bad!r}")
        except ValueError:
            pass
    print("Autoprueba finalizada correctamente.")
