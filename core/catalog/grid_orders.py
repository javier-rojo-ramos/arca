"""Órdenes de la cuadrícula: por qué campo y en qué dirección se ordenan las tarjetas.

Este módulo NO depende de Qt: es Python puro.

Dos piezas:
    - 'SORT_FIELDS': el registro de campos por los que se puede ordenar (clave estable,
      texto del desplegable y columnas de 'media_items'). Es la ÚNICA lista: el
      desplegable de la barra inferior y el SQL salen de aquí.
    - 'GridOrder(field, descending)': un orden concreto. Es inmutable y valida la clave al
      crearse, así que lo que llega a 'order_by_sql' es siempre un campo conocido (nunca
      se interpola en el SQL un texto que venga de fuera).

Cómo se usa:
    order = GridOrder("captured_at", descending=True)
    sql = order_by_sql(order)          # para el ORDER BY de 'media_queries.fetch_grid_rows'
    state = order.to_state()           # para guardarlo en el estado del módulo (JSON)
    order = GridOrder.from_state(state, NAME_ORDER)   # al recuperarlo

Reglas del ORDER BY (ver 'order_by_sql'):
    - Los NULL van SIEMPRE al final, también en descendente (un archivo sin fecha de
      captura no tiene por qué aparecer el primero al invertir el orden).
    - Desempate por nombre e id, en la MISMA dirección: así el orden es estable (varias
      fotos con la misma fecha no bailan entre consultas) y la flecha invierte la lista
      exactamente.

Añadir un campo: una línea en '_FIELD_LIST'. Si ordena por una columna de otra tabla
('photo_details', 'video_details'...), hará falta antes un JOIN en 'fetch_grid_rows'.
Las claves son las de las colecciones inteligentes ('smart_fields.py') cuando existen.

1.0.1 Textos como en las colecciones inteligentes: «Extensión» y «Fecha de importación».
1.0.0 Primera versión (07/11/2026): seis campos, con dirección; sustituye a
      'media_queries.GRID_ORDERS'.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.grid_orders
"""

__version__ = "1.0.1"
__all__ = [
    "CAPTURE_TIME_ORDER",
    "NAME_ORDER",
    "SORT_FIELDS",
    "GridOrder",
    "SortColumn",
    "SortField",
    "order_by_sql",
]

# Librerías estándar
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SortColumn:
    """Una columna de 'media_items' dentro del orden de un campo.

    Attributes:
        name: Nombre de la columna (sin alias: 'order_by_sql' le pone 'm.').
        nocase: Comparar sin distinguir mayúsculas (texto).
        nullable: La columna puede ser NULL: se añade 'IS NULL' delante para mandarlos
            al final.
    """

    name: str
    nocase: bool = False
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class SortField:
    """Un campo por el que se puede ordenar la cuadrícula.

    Attributes:
        key: Clave estable (se guarda en settings.json): 'captured_at', 'file_name'...
        label: Texto del desplegable.
        columns: Columnas por las que ordena, de más a menos importante (un campo puede
            tener varias: artista, álbum y pista).
    """

    key: str
    label: str
    columns: tuple[SortColumn, ...]


# Desempate común a todos los campos (orden estable)
_TIEBREAK = (SortColumn("file_name", nocase=True), SortColumn("id"))

# Registro de campos, en el orden del desplegable
_FIELD_LIST: tuple[SortField, ...] = (
    # Hora de captura (EXIF; hora local), como la de Lightroom. Sin ella (aún sin leer
    # sus metadatos, o sin EXIF), al final
    SortField("captured_at", "Hora de captura",
              (SortColumn("content_created_at", nullable=True),)),
    SortField("file_name", "Nombre", (SortColumn("file_name", nocase=True),)),
    # Por la extensión (ya normalizada en minúsculas): JPG, DNG, MP4... juntos
    SortField("file_extension", "Extensión",
              (SortColumn("file_extension", nullable=True),)),
    SortField("file_size", "Tamaño", (SortColumn("file_size"),)),
    # 'file_mtime_ns' es la fecha de modificación del archivo según el sistema
    SortField("file_modified_at", "Fecha de modificación", (SortColumn("file_mtime_ns"),)),
    # Cuándo entró en el catálogo (la «Hora de adición» de Lightroom)
    SortField("added_at", "Fecha de importación", (SortColumn("added_at"),)),
)  # fmt: skip

SORT_FIELDS: dict[str, SortField] = {field.key: field for field in _FIELD_LIST}


@dataclass(frozen=True, slots=True)
class GridOrder:
    """Un orden de la cuadrícula: campo y dirección.

    Se puede comparar ('==') para no recargar si no ha cambiado.

    Attributes:
        field: Clave de 'SORT_FIELDS'.
        descending: True = de mayor a menor (Z-A, lo más reciente primero...).

    Raises:
        ValueError: Si 'field' no está en 'SORT_FIELDS'.
    """

    field: str
    descending: bool = False

    def __post_init__(self) -> None:
        if self.field not in SORT_FIELDS:
            raise ValueError(f"Campo de orden desconocido: {self.field!r}")

    @property
    def label(self) -> str:
        """Texto del campo para la interfaz."""
        return SORT_FIELDS[self.field].label

    def reversed(self) -> "GridOrder":
        """El mismo campo en la dirección contraria (lo que hace el botón de la flecha)."""
        return GridOrder(self.field, not self.descending)

    def to_state(self) -> dict[str, Any]:
        """Lo que se guarda en JSON (estado del módulo)."""
        return {"field": self.field, "descending": self.descending}

    @classmethod
    def from_state(cls, state: object, default: "GridOrder") -> "GridOrder":
        """Recupera un orden guardado con 'to_state'.

        Tolera datos incompletos o de otra versión: si el campo ya no existe o el estado
        no se entiende, devuelve 'default'.
        """
        if not isinstance(state, dict):
            return default
        field = state.get("field")
        if not isinstance(field, str) or field not in SORT_FIELDS:
            return default
        return cls(field, state.get("descending") is True)


# Órdenes de partida de los módulos (paso 2)
NAME_ORDER = GridOrder("file_name")
CAPTURE_TIME_ORDER = GridOrder("captured_at")


def order_by_sql(order: GridOrder, alias: str = "m") -> str:
    """Devuelve la cláusula ORDER BY (sin 'ORDER BY') de un orden.

    Args:
        order: Orden (ya validado al crearse).
        alias: Alias de 'media_items' en la consulta.

    Ejemplo: «Hora de captura» descendente ->
        m.content_created_at IS NULL, m.content_created_at DESC,
        m.file_name COLLATE NOCASE DESC, m.id DESC
    """
    direction = " DESC" if order.descending else ""
    columns = SORT_FIELDS[order.field].columns
    # El desempate no repite columnas del campo (el nombre ya ordena por nombre)
    names = {column.name for column in columns}
    parts = []
    for column in (*columns, *(c for c in _TIEBREAK if c.name not in names)):
        qualified = f"{alias}.{column.name}"
        if column.nullable:
            # 'X IS NULL' vale 0 o 1 y va siempre ascendente: los NULL, al final
            parts.append(f"{qualified} IS NULL")
        collate = " COLLATE NOCASE" if column.nocase else ""
        parts.append(f"{qualified}{collate}{direction}")
    return ", ".join(parts)


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.grid_orders
    import sqlite3

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    # Validación: un campo desconocido no se puede ni crear
    try:
        GridOrder("id; DROP TABLE media_items")
        raise AssertionError("debía rechazar un campo desconocido")
    except ValueError:
        pass

    # SQL generado
    assert order_by_sql(NAME_ORDER) == "m.file_name COLLATE NOCASE, m.id"
    assert order_by_sql(GridOrder("captured_at", descending=True)) == (
        "m.content_created_at IS NULL, m.content_created_at DESC, "
        "m.file_name COLLATE NOCASE DESC, m.id DESC"
    )
    assert order_by_sql(GridOrder("file_size"), alias="x").startswith("x.file_size, x.file_name")

    # Estado guardado: ida y vuelta, y tolerancia a lo que no se entiende
    order = GridOrder("added_at", descending=True)
    assert GridOrder.from_state(order.to_state(), NAME_ORDER) == order
    for bad in (None, [], {}, {"field": "ya_no_existe"}, {"field": 3}):
        assert GridOrder.from_state(bad, NAME_ORDER) == NAME_ORDER, bad
    assert GridOrder.from_state({"field": "file_size", "descending": "sí"}, NAME_ORDER) == (
        GridOrder("file_size")
    )  # solo True cuenta como descendente
    assert order.reversed() == GridOrder("added_at") and order.reversed().reversed() == order
    assert CAPTURE_TIME_ORDER.label == "Hora de captura"

    # Todos los campos existen en el esquema y la consulta funciona en las dos direcciones
    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('P', '/tmp/p')")
    items = (  # nombre, extensión, tamaño, mtime, captura
        ("b.jpg", "jpg", 30, 2, "2021-01-01 08:00:00"),
        ("A.dng", "dng", 10, 3, None),
        ("c.mp4", "mp4", 20, 1, "2019-01-01 08:00:00"),
    )
    for name, ext, size, mtime, captured in items:
        db.execute(
            "INSERT INTO media_items(storage_location_id, relative_path, file_name, title, "
            "file_extension, media_type, mime_type, file_size, file_mtime_ns, "
            "content_created_at) VALUES (1, ?, ?, ?, ?, 'photo', 'image/jpeg', ?, ?, ?)",
            (name, name, name, ext, size, mtime, captured),
        )

    def names(order: GridOrder) -> list[str]:
        sql = f"SELECT m.file_name FROM media_items AS m ORDER BY {order_by_sql(order)}"
        return [r[0] for r in db.execute(sql)]

    for key in SORT_FIELDS:
        up, down = names(GridOrder(key)), names(GridOrder(key, descending=True))
        assert len(up) == 3, key
        if key != "captured_at":  # sin NULL: invertir es exactamente la lista al revés
            assert down == up[::-1], (key, up, down)
    assert names(NAME_ORDER) == ["A.dng", "b.jpg", "c.mp4"]  # sin distinguir mayúsculas
    assert names(GridOrder("file_extension")) == ["A.dng", "b.jpg", "c.mp4"]
    assert names(GridOrder("file_size")) == ["A.dng", "c.mp4", "b.jpg"]
    assert names(GridOrder("file_modified_at", descending=True)) == ["A.dng", "b.jpg", "c.mp4"]
    # Sin hora de captura, al final en las dos direcciones
    assert names(CAPTURE_TIME_ORDER) == ["c.mp4", "b.jpg", "A.dng"]
    assert names(CAPTURE_TIME_ORDER.reversed()) == ["b.jpg", "c.mp4", "A.dng"]
    # Fecha de importación: todas iguales en la prueba (CURRENT_TIMESTAMP) -> desempata por nombre
    assert names(GridOrder("added_at")) == ["A.dng", "b.jpg", "c.mp4"]

    print("Autoprueba finalizada correctamente.")
