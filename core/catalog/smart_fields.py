"""Catálogo de CAMPOS que se pueden usar en las reglas de las colecciones inteligentes.

Este módulo NO depende de Qt ni de la base de datos: es una lista declarativa. El motor
('smart_rules.py') la usa para validar las reglas y traducirlas a SQL, y el editor
('ui_helpers/dialogs/smart_collection_dialog.py') para construir sus menús y sus campos de
valor. Ninguno de los dos tiene campos escritos a mano: AÑADIR UN CAMPO ES AÑADIR UNA
LÍNEA AQUÍ.

Organización (lo que ve el usuario en el menú "campo" del editor):

    Estándar ▸        común a todos los archivos
        Archivo         Nombre de archivo, Extensión, Tipo de archivo, Carpeta...
        Fechas          Fecha de captura, Fecha de importación
        Clasificación   Valoración, Marca, Etiqueta de color, Selección rápida
        Descripción     Título, Descripción, Autor, Copyright
        Ubicación       Ciudad, Región, País, Lugar, Coordenadas GPS
        Palabras clave  Palabra clave (cualquier tipo de archivo)
    Imagen ▸          solo fotos (cámara, objetivo, ISO...)
    Vídeo ▸           (previsto)
    Audio ▸           (previsto)
    Libros ▸          (previsto)
    Tracks GPS ▸      distancia, desnivel, actividad...

Los grupos sin campos no se muestran. Un grupo de un tipo de medio ('media_types') hace
que sus reglas solo coincidan con archivos de ese tipo: p. ej. "ISO no es 100" no
incluye los vídeos (que no tienen ISO).

Cómo añadir un campo:
    1. Una línea 'SmartField(...)' en '_FIELD_LIST' con:
         key      clave ESTABLE (se guarda en la base de datos; no cambiarla nunca)
         label    texto para el usuario
         group / section   dónde aparece en el menú
         kind     tipo de valor (KIND_*): decide los operadores y el editor del valor
         column   expresión SQL sobre 'media_items' (alias 'm'). Para las tablas de
                  detalles, '_detail("photo_details", "iso")' (subconsulta por media_id)
       y, según el tipo: 'choices' (KIND_ENUM), 'unit' / 'scale' / 'decimals'
       (KIND_NUMBER), 'clock' (KIND_DATE). Con 'browse=True' se ofrece además como
       columna en «Metadatos» de la barra de filtros (solo campos con pocos valores y
       muy repetidos: no el nombre de archivo ni un tamaño).
    2. Nada más: el motor, el editor y la descripción de la regla lo toman de aquí.
Cómo añadir un grupo (p. ej. vídeo, cuando exista 'video_details'): una línea en
'GROUPS' con sus 'media_types'; sus campos, con 'group=' su clave.

1.5.1 «Lugar» (antes «Ubicación secundaria»): el mismo nombre que en el inspector
      (decidido por el autor el 09/11/2026; la clave 'sublocation' no cambia).
1.5.0 'SmartField.browse' y 'browse_fields()': los 29 campos que se ofrecen como columnas
      en «Metadatos» de la barra de filtros (paso A.3, «Metadatos»).
1.4.0 Campo «Selección rápida» (sí / no; 'media_items.in_quick_selection'): lo usa la
      fila «Atributos» de la barra de filtros y también el editor (paso A.3).
1.3.0 «empieza con» y «termina con» (antes «empieza por» y «termina en»; mismos textos que
      la barra de filtros) y «termina con» también en «Palabra clave» (paso A.3).
1.2.0 Campo «Palabra clave» (KIND_KEYWORD): «es» con o sin sus hijas, «contiene»...
1.1.1 Las opciones del campo «Biblioteca» usan los nombres de 'LIBRARY_NAMES'.
1.1.0 Campo «Biblioteca» ('media_items.library'; «está vacío» = sin clasificar).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.smart_fields
"""

__version__ = "1.5.1"
# ruff: noqa: RUF022
__all__ = [
    "KIND_BOOL",
    "KIND_DATE",
    "KIND_ENUM",
    "KIND_KEYWORD",
    "KIND_NUMBER",
    "KIND_RATING",
    "KIND_TEXT",
    "FIELDS",
    "GROUPS",
    "OPERATORS",
    "OPERATORS_BY_KIND",
    "FieldGroup",
    "Operator",
    "SmartField",
    "browse_fields",
    "fields_in_group",
    "visible_groups",
]

# Librerías estándar
from dataclasses import dataclass
from typing import Any

# Módulos del proyecto
from core.catalog.libraries import LIBRARY_NAMES, Library
from core.catalog.media_types import MediaType

# -----------------------------------------------------------------------------
# Tipos de valor (cada uno tiene sus operadores y su editor en la interfaz)
# -----------------------------------------------------------------------------

KIND_TEXT = "text"  # texto: contiene, empieza con... (sin distinguir mayúsculas ni acentos)
KIND_NUMBER = "number"  # número (entero o decimal), con unidad opcional
KIND_DATE = "date"  # fecha (las columnas guardan 'YYYY-MM-DD HH:MM:SS')
KIND_ENUM = "enum"  # uno de una lista cerrada de valores ('choices')
KIND_RATING = "rating"  # valoración de 0 a 5 estrellas
KIND_BOOL = "bool"  # sí / no
# Palabra clave: el valor es un NOMBRE de palabra; se busca en las tablas 'keywords' y
# 'media_keywords' (no en una columna). Su SQL está en 'smart_rules._keyword_condition'
KIND_KEYWORD = "keyword"


@dataclass(frozen=True, slots=True)
class Operator:
    """Un operador de las reglas.

    Attributes:
        key: Clave estable (se guarda en la base de datos).
        label: Texto para el usuario ("contiene", "es mayor que"...).
        arity: Valores que necesita: 0 (p. ej. "está vacío"), 1 o 2 ("está entre").
    """

    key: str
    label: str
    arity: int = 1


# Todos los operadores. El SQL de cada uno está en 'smart_rules.py'
OPERATORS: dict[str, Operator] = {
    op.key: op
    for op in (
        Operator("eq", "es"),
        Operator("ne", "no es"),
        Operator("contains", "contiene"),
        Operator("not_contains", "no contiene"),
        Operator("starts_with", "empieza con"),
        Operator("ends_with", "termina con"),
        Operator("gt", "es mayor que"),
        Operator("gte", "es mayor o igual que"),
        Operator("lt", "es menor que"),
        Operator("lte", "es menor o igual que"),
        Operator("between", "está entre", 2),
        Operator("on", "es el día"),
        Operator("before", "es anterior a"),
        Operator("after", "es posterior a"),
        Operator("in_last", "en los últimos (días)"),
        Operator("is_true", "sí", 0),
        Operator("is_false", "no", 0),
        Operator("is_set", "tiene valor", 0),
        Operator("is_not_set", "está vacío", 0),
        # Palabras clave: «Coche» con sus hijas = las fotos de cualquier modelo de coche,
        # aunque no lleven «Coche» asignada (decidido el 03/11/2026)
        Operator("kw_is", "es (con sus hijas)"),
        Operator("kw_is_only", "es (sin sus hijas)"),
        Operator("kw_is_not", "no es (ni sus hijas)"),
    )
}

# Operadores de cada tipo, en el orden en que aparecen en el editor
OPERATORS_BY_KIND: dict[str, tuple[str, ...]] = {
    KIND_TEXT: ("contains", "not_contains", "eq", "ne", "starts_with", "ends_with", "is_set", "is_not_set"),
    KIND_NUMBER: ("eq", "ne", "gt", "gte", "lt", "lte", "between", "is_set", "is_not_set"),
    KIND_DATE: ("on", "before", "after", "between", "in_last", "is_set", "is_not_set"),
    KIND_ENUM: ("eq", "ne"),
    KIND_RATING: ("eq", "ne", "gt", "gte", "lt", "lte"),
    KIND_BOOL: ("is_true", "is_false"),
    # "contiene", "no contiene", "empieza con" y "termina con" también miran las hijas:
    # «contiene coche» incluye las fotos con solo «Toyota Corolla» (dentro de «Coche»)
    KIND_KEYWORD: (
        "kw_is", "kw_is_only", "kw_is_not", "contains", "not_contains", "starts_with",
        "ends_with", "is_set", "is_not_set",
    ),
}


# -----------------------------------------------------------------------------
# Grupos y campos
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldGroup:
    """Un grupo de campos (un submenú del editor).

    Attributes:
        key: Clave del grupo.
        label: Texto del submenú.
        media_types: Tipos de medio a los que se aplican sus campos (vacío = a todos).
    """

    key: str
    label: str
    media_types: tuple[str, ...] = ()


# Grupos, en el orden del menú. Los que no tienen campos (aún) no se muestran
GROUPS: tuple[FieldGroup, ...] = (
    FieldGroup("standard", "Estándar"),
    FieldGroup("image", "Imagen", (MediaType.PHOTO.value,)),
    FieldGroup("video", "Vídeo", (MediaType.VIDEO.value,)),
    FieldGroup("audio", "Audio", (MediaType.AUDIO.value,)),
    FieldGroup("ebook", "Libros electrónicos", (MediaType.EBOOK.value,)),
    FieldGroup("track", "Tracks GPS", (MediaType.TRACK.value,)),
)
_GROUPS_BY_KEY = {group.key: group for group in GROUPS}


@dataclass(frozen=True, slots=True)
class SmartField:
    """Un campo que se puede usar en una regla.

    Attributes:
        key: Clave estable (se guarda en 'collections.rules_json'; no cambiarla nunca).
        label: Texto para el usuario.
        group: Clave del grupo (ver 'GROUPS').
        section: Subtítulo dentro del grupo ("Archivo", "Fechas"...).
        kind: Tipo de valor (KIND_*).
        column: Expresión SQL sobre 'media_items' (alias 'm'). Sale SIEMPRE de esta lista
            cerrada: nunca de un texto que venga de fuera.
        choices: KIND_ENUM: (valor, texto) de cada opción, en orden.
        unit: KIND_NUMBER: unidad que ve el usuario ("km", "MB", "mm"...).
        scale: KIND_NUMBER: cuántas unidades de la BD hay en una unidad del usuario (p. ej.
            1000 si la BD guarda metros y el usuario escribe kilómetros). Las reglas
            guardan el valor en unidades de la BD.
        decimals: KIND_NUMBER: decimales que se muestran en el editor.
        clock: KIND_DATE: 'local' (hora local, como 'content_created_at') o 'utc' (como
            'added_at'); decide qué es "hoy" en "en los últimos N días".
        operators: Operadores admitidos (vacío = los de su tipo, 'OPERATORS_BY_KIND').
        browse: Se ofrece como columna en «Metadatos» de la barra de filtros (lista de
            sus valores con recuentos; ver 'grid_filter.metadata_rule').
    """

    key: str
    label: str
    group: str
    section: str
    kind: str
    column: str
    choices: tuple[tuple[Any, str], ...] = ()
    unit: str = ""
    scale: float = 1.0
    decimals: int = 0
    clock: str = "local"
    operators: tuple[str, ...] = ()
    browse: bool = False

    @property
    def allowed_operators(self) -> tuple[str, ...]:
        """Operadores que admite el campo, en el orden del editor."""
        return self.operators or OPERATORS_BY_KIND[self.kind]

    @property
    def media_types(self) -> tuple[str, ...]:
        """Tipos de medio a los que se aplica (los de su grupo; vacío = todos)."""
        return _GROUPS_BY_KEY[self.group].media_types

    def choice_label(self, value: Any) -> str:
        """Texto de una opción de KIND_ENUM (o el propio valor si no está en la lista)."""
        for choice_value, text in self.choices:
            if choice_value == value:
                return text
        return str(value)


def _detail(table: str, column: str) -> str:
    """Columna de una tabla de detalles (1:1 con 'media_items' por 'media_id').

    Se usa una subconsulta para que las reglas no necesiten JOIN: así la condición vale
    tal cual en la cuadrícula y en los contadores. Va por la clave primaria: es rápida.
    """
    return f"(SELECT d.{column} FROM {table} AS d WHERE d.media_id = m.id)"


# Opciones de los campos de tipo lista
_MEDIA_TYPE_CHOICES = (
    (MediaType.PHOTO.value, "Foto"),
    (MediaType.VIDEO.value, "Vídeo"),
    (MediaType.AUDIO.value, "Audio"),
    (MediaType.EBOOK.value, "Libro electrónico"),
    (MediaType.TRACK.value, "Track GPS"),
)
# Bibliotecas (core/catalog/libraries.py): qué módulo gestiona cada elemento
_LIBRARY_CHOICES = tuple((library.value, LIBRARY_NAMES[library]) for library in Library)
_FLAG_CHOICES = ((1, "Marcada"), (0, "Sin marca"), (-1, "Rechazada"))
# Mismo orden que 'color_labels.COLOR_LABELS' (la BD guarda el nombre en inglés)
_COLOR_CHOICES = (
    ("red", "Rojo"),
    ("yellow", "Amarillo"),
    ("green", "Verde"),
    ("blue", "Azul"),
    ("purple", "Púrpura"),
)
_ORIENTATION_CHOICES = (("h", "Horizontal"), ("v", "Vertical"), ("s", "Cuadrada"))
_ORIENTATION_SQL = (
    "(CASE WHEN m.width > m.height THEN 'h' WHEN m.width < m.height THEN 'v' "
    "WHEN m.width = m.height THEN 's' END)"
)

_MB = 1024 * 1024  # bytes en un MB (como el Explorador de Windows)

# Lista de campos, en el orden en que aparecen en el menú (dentro de su grupo y sección)
# fmt: off
_FIELD_LIST: tuple[SmartField, ...] = (
    # --- Estándar ---------------------------------------------------------------------
    SmartField("file_name", "Nombre de archivo", "standard", "Archivo", KIND_TEXT, "m.file_name"),
    SmartField("file_extension", "Extensión", "standard", "Archivo", KIND_TEXT, "m.file_extension",
               browse=True),
    SmartField("media_type", "Tipo de archivo", "standard", "Archivo", KIND_ENUM, "m.media_type",
               choices=_MEDIA_TYPE_CHOICES, browse=True),
    # «está vacío» = sin clasificar (p. ej. vídeos de carpetas automáticas)
    SmartField("library", "Biblioteca", "standard", "Archivo", KIND_ENUM, "m.library",
               choices=_LIBRARY_CHOICES, operators=("eq", "ne", "is_set", "is_not_set"),
               browse=True),
    SmartField("folder", "Carpeta (ruta)", "standard", "Archivo", KIND_TEXT, "m.relative_path",
               operators=("contains", "not_contains", "starts_with")),
    SmartField("file_size", "Tamaño", "standard", "Archivo", KIND_NUMBER, "m.file_size",
               unit="MB", scale=_MB, decimals=1,
               operators=("gt", "gte", "lt", "lte", "between")),
    SmartField("is_missing", "Archivo ausente", "standard", "Archivo", KIND_BOOL, "m.is_missing",
               browse=True),

    SmartField("captured_at", "Fecha de captura", "standard", "Fechas", KIND_DATE,
               "m.content_created_at", clock="local", browse=True),
    SmartField("added_at", "Fecha de importación", "standard", "Fechas", KIND_DATE,
               "m.added_at", clock="utc",
               operators=("on", "before", "after", "between", "in_last"), browse=True),

    SmartField("rating", "Valoración", "standard", "Clasificación", KIND_RATING, "m.rating",
               browse=True),
    SmartField("flag", "Marca", "standard", "Clasificación", KIND_ENUM, "m.flag",
               choices=_FLAG_CHOICES, browse=True),
    SmartField("color_label", "Etiqueta de color", "standard", "Clasificación", KIND_ENUM,
               "m.color_label", choices=_COLOR_CHOICES,
               operators=("eq", "ne", "is_set", "is_not_set"), browse=True),
    # Solo vive en el catálogo (el círculo de la tarjeta): no se escribe en los archivos
    SmartField("in_quick_selection", "Selección rápida", "standard", "Clasificación", KIND_BOOL,
               "m.in_quick_selection", browse=True),

    SmartField("title", "Título", "standard", "Descripción", KIND_TEXT, "m.title"),
    SmartField("description", "Descripción", "standard", "Descripción", KIND_TEXT, "m.description"),
    SmartField("creator", "Autor", "standard", "Descripción", KIND_TEXT, "m.creator",
               browse=True),
    SmartField("copyright", "Copyright", "standard", "Descripción", KIND_TEXT, "m.copyright",
               browse=True),

    SmartField("city", "Ciudad", "standard", "Ubicación", KIND_TEXT, "m.city", browse=True),
    SmartField("region", "Región o provincia", "standard", "Ubicación", KIND_TEXT, "m.region",
               browse=True),
    SmartField("country", "País", "standard", "Ubicación", KIND_TEXT, "m.country", browse=True),
    SmartField("sublocation", "Lugar", "standard", "Ubicación", KIND_TEXT,
               "m.sublocation", browse=True),
    SmartField("has_gps", "Tiene coordenadas GPS", "standard", "Ubicación", KIND_BOOL,
               "(m.latitude IS NOT NULL AND m.longitude IS NOT NULL)", browse=True),
    # Palabras clave (cualquier tipo de archivo): 'column' no se usa (ver KIND_KEYWORD)
    SmartField("keyword", "Palabra clave", "standard", "Palabras clave", KIND_KEYWORD, "m.id",
               browse=True),

    # --- Imagen (solo fotos) ------------------------------------------------------------
    SmartField("camera_make", "Marca de la cámara", "image", "Cámara", KIND_TEXT,
               _detail("photo_details", "camera_make"), browse=True),
    SmartField("camera_model", "Modelo de la cámara", "image", "Cámara", KIND_TEXT,
               _detail("photo_details", "camera_model"), browse=True),
    SmartField("lens_model", "Objetivo", "image", "Cámara", KIND_TEXT,
               _detail("photo_details", "lens_model"), browse=True),
    SmartField("iso", "ISO", "image", "Exposición", KIND_NUMBER, _detail("photo_details", "iso"),
               browse=True),
    SmartField("f_number", "Apertura (f/)", "image", "Exposición", KIND_NUMBER,
               _detail("photo_details", "f_number"), decimals=1, browse=True),
    SmartField("focal_length", "Distancia focal", "image", "Exposición", KIND_NUMBER,
               _detail("photo_details", "focal_length_mm"), unit="mm", browse=True),
    SmartField("exposure_time", "Tiempo de exposición", "image", "Exposición", KIND_NUMBER,
               _detail("photo_details", "exposure_time_s"), unit="s", decimals=4, browse=True),
    SmartField("flash_fired", "Flash disparado", "image", "Exposición", KIND_BOOL,
               _detail("photo_details", "flash_fired"), browse=True),
    SmartField("orientation", "Orientación", "image", "Imagen", KIND_ENUM, _ORIENTATION_SQL,
               choices=_ORIENTATION_CHOICES, browse=True),
    SmartField("width", "Ancho", "image", "Imagen", KIND_NUMBER, "m.width", unit="px"),
    SmartField("height", "Alto", "image", "Imagen", KIND_NUMBER, "m.height", unit="px"),

    # --- Tracks GPS -----------------------------------------------------------------------
    SmartField("track_distance", "Distancia", "track", "Recorrido", KIND_NUMBER,
               _detail("track_details", "distance_m"), unit="km", scale=1000, decimals=1),
    SmartField("track_gain", "Desnivel positivo", "track", "Recorrido", KIND_NUMBER,
               _detail("track_details", "elevation_gain_m"), unit="m"),
    SmartField("track_loss", "Desnivel negativo", "track", "Recorrido", KIND_NUMBER,
               _detail("track_details", "elevation_loss_m"), unit="m"),
    SmartField("track_max_elevation", "Altitud máxima", "track", "Recorrido", KIND_NUMBER,
               _detail("track_details", "elevation_max_m"), unit="m"),
    SmartField("track_activity", "Actividad", "track", "Recorrido", KIND_TEXT,
               _detail("track_details", "activity_type"), browse=True),
    SmartField("track_creator_app", "Creado con", "track", "Recorrido", KIND_TEXT,
               _detail("track_details", "creator_app"), browse=True),
)
# fmt: on

# Campos por clave (lo que usa el motor)
FIELDS: dict[str, SmartField] = {field.key: field for field in _FIELD_LIST}


def fields_in_group(group_key: str) -> list[SmartField]:
    """Campos de un grupo, en el orden del menú."""
    return [field for field in _FIELD_LIST if field.group == group_key]


def browse_fields(group_key: str | None = None) -> list[SmartField]:
    """Campos que se ofrecen como columnas en «Metadatos» (de un grupo o de todos), en el
    orden del menú."""
    return [
        field for field in _FIELD_LIST
        if field.browse and (group_key is None or field.group == group_key)
    ]


def visible_groups() -> list[FieldGroup]:
    """Grupos que tienen algún campo (los que muestra el editor)."""
    return [group for group in GROUPS if fields_in_group(group.key)]


if __name__ == "__main__":
    # Autoprueba: la lista es coherente. Ejecutar desde la raíz:  python -m core.catalog.smart_fields
    assert len(FIELDS) == len(_FIELD_LIST), "claves repetidas en _FIELD_LIST"
    for field in _FIELD_LIST:
        assert field.group in _GROUPS_BY_KEY, field
        assert field.kind in OPERATORS_BY_KIND, field
        for op in field.allowed_operators:
            assert op in OPERATORS, (field.key, op)
        if field.operators:
            # Los operadores propios tienen que tener sentido para su tipo ("tiene valor" y
            # "está vacío" valen para cualquiera: p. ej. una etiqueta de color)
            valid = set(OPERATORS_BY_KIND[field.kind]) | {"is_set", "is_not_set"}
            assert set(field.operators) <= valid, field.key
        if field.kind == KIND_ENUM:
            assert field.choices, field.key
        assert field.scale > 0, field.key
        assert field.clock in ("local", "utc"), field.key
    assert [g.key for g in visible_groups()] == ["standard", "image", "track"]
    assert FIELDS["iso"].media_types == ("photo",)
    assert FIELDS["rating"].media_types == ()
    assert FIELDS["flag"].choice_label(-1) == "Rechazada"
    assert FIELDS["keyword"].media_types == () and FIELDS["keyword"].allowed_operators[0] == "kw_is"
    # Columnas de «Metadatos»: 29 campos; fuera los de casi un valor por archivo y los continuos
    browse = {field.key for field in browse_fields()}
    assert len(browse) == 29, len(browse)
    assert not browse & {"file_name", "title", "description", "folder", "file_size", "width",
                         "height", "track_distance", "track_gain", "track_loss",
                         "track_max_elevation"}
    assert [f.key for f in browse_fields("track")] == ["track_activity", "track_creator_app"]
    print(f"{len(FIELDS)} campos en {len(visible_groups())} grupos visibles.")
    print("Autoprueba finalizada correctamente.")
