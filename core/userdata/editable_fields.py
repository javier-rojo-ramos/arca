"""Metadatos descriptivos que el usuario edita en la aplicación y se escriben en los archivos.

Este módulo NO depende de Qt ni de la base de datos: es una lista declarativa.

UN CAMPO, VARIOS ESCRITORES (decidido con el autor el 14/11/2026, pensando en los módulos
que vienen: Audio con sus etiquetas ID3, Vídeo con las de su contenedor o un '.nfo'): el
campo se declara aquí UNA vez (dónde se guarda, de qué tipo es, a qué tipos de archivo se
aplica) y cada escritor dice qué campos sabe guardar. Hoy hay dos escritores: el de XMP
('xmp_writer.py': los campos con 'xmp_tag') y el archivo de carpeta ('.arca.json': todos,
por su 'folder_key'). Lo que el escritor de un formato no sabe guardar va al '.arca.json'.
Un campo puede estar en 'media_items' o en una tabla de detalles ('table'), y no tener
etiqueta XMP: el primero así es la ACTIVIDAD de un track ('track_details.activity_type').

Cada campo editable (título, pie de ilustración, creador, copyright, ubicación, GPS, la
actividad de los tracks y los campos de las canciones) es una línea de 'EDITABLE_FIELDS', y
de esa línea sale todo lo demás:
    - 'update_metadata_fields' (core/catalog/media_queries.py) guarda el valor en su
      columna (de 'media_items' o de su tabla de detalles) y pone el BIT del campo en
      'media_items.metadata_edit_pending' (pendiente de escribir en el archivo);
    - al releer el archivo no se pisan las columnas con su bit puesto;
    - el escritor pone el valor en la etiqueta XMP y en las antiguas que el archivo ya
      tenga, o en la clave del '.arca.json' (según el destino del formato, 'policy.py');
    - el inspector lo edita en una línea o en varias ('multiline').

Reglas (ver docs/DECISIONES.md, 10/11/2026, y «Escritura de los metadatos descriptivos»
en docs/METADATOS.md):
    - Las etiquetas son las MISMAS de las que se lee el campo (core/metadata/image/fields.py)
      y en el mismo orden: primero la XMP, después las antiguas (IPTC, EXIF).
    - La XMP se escribe SIEMPRE y es la única que se comprueba al releer. Las antiguas solo
      se actualizan si el archivo ya las tiene: si no, al vaciar un campo volvería su valor
      antiguo (la lectura cae a la siguiente fuente). Su valor puede quedar recortado (el
      IPTC tiene límites de longitud) o con «?» (IPTC en Latin): por eso no se comprueban.
    - Un valor vacío es None ('normalize_value').
    - Los campos de texto son la mayoría. Los del GPS (latitud, longitud, altitud y
      dirección) son NÚMEROS ('kind' = NUMBER), con sus límites, y se escriben con otra
      regla (ver docs/DECISIONES.md, 11/11/2026): en las etiquetas de GPS que ya tenga el
      archivo y, si no tiene ninguna, en el EXIF; ahí 'legacy_tags' es su etiqueta EXIF.
      La latitud y la longitud van siempre juntas ('PAIRED_COLUMNS').
    - El título no puede quedar vacío en el catálogo ('title' es NOT NULL): sin título vale
      el nombre del archivo sin extensión ('default_title'), y un título igual a ese nombre
      cuenta como «sin título» ('file_title'): es lo que se escribe en el archivo y lo que
      muestra el inspector (vacío, en lugar de «IMG_0001»).
    - El AÑO de una canción (MUS 7.1a) está en la columna de la fecha, que en las fotos y
      los vídeos es la de captura: por eso es solo de las canciones ('media_types') y
      todo lo que guarda un campo editable mira a qué tipos se aplica ('applies_sql',
      'applies_to'). Se edita como un año (el autor, 28/11/2026: «el año en música es
      simplemente un año»): el 1 de enero de ese año, con precisión 'year'. Su precisión
      y su origen VAN CON ÉL ('LINKED_COLUMNS', 'linked_values'): se guardan al editarlo
      y lo leído del archivo no los pisa mientras está pendiente. En el '.arca.json',
      el año como número ("year": 1999; 'folder_value').

Cómo añadir un campo:
    1. Una línea más en 'EDITABLE_FIELDS' con un BIT NUEVO (el doble del último). Un bit
       no se cambia ni se reutiliza nunca: los catálogos lo tienen guardado en
       'metadata_edit_pending'.
    2. La columna tiene que existir en 'media_items' o en su tabla de detalles ('table';
       si no, una migración). Si tiene etiqueta XMP, se lee de las mismas etiquetas (la
       autoprueba lo comprueba con 'IMAGE_FIELDS'). Si es de un solo tipo de archivo,
       'media_types' (en los demás ni se guarda ni queda pendiente).
    3. La clave del '.arca.json' tampoco se cambia después: está en los archivos de los
       usuarios.

1.5.0 El año de las canciones, editable (MUS 7.1a): tipo YEAR, en 'content_created_at'
      (bit 4194304) y solo de las canciones, con su precisión y su origen
      ('LINKED_COLUMNS', 'linked_values', 'GUARDED_MAIN_COLUMNS'; 'unless_pending_sql'
      vale también para ellas); 'applies_to' y 'folder_value'.
1.4.0 Los campos de las canciones sin columna común, en 'audio_details' y solo de las
      canciones: álbum, artista del álbum, pista y total, disco y total, género y
      compositor (bits 16384 a 2097152; MUS 6.2b). Tipo nuevo, INTEGER (entero positivo),
      para la pista y el disco.
1.3.0 Un campo puede no tener etiqueta XMP, estar en una tabla de detalles ('table') y ser
      solo de algunos tipos de archivo ('media_types'): la actividad de los tracks
      ('activity_type', bit 8192). 'XMP_COLUMNS', 'MAIN_COLUMNS', 'read_sql', 'upsert_sql' y
      'applies_sql'; 'unless_pending_sql' vale también para una tabla de detalles.
1.2.0 GPS: latitud, longitud, altitud y dirección (bits 512 a 4096), campos NUMÉRICOS con
      sus límites ('kind', 'limits', 'circular'); la latitud y la longitud, juntas
      ('PAIRED_COLUMNS', 'incomplete_pairs').
1.1.0 'unless_pending_sql': asignación que no pisa una columna pendiente de escribir.
1.0.0 Primera versión: título, pie de ilustración, creador, copyright y ubicación.

Prueba rápida (desde la raíz del proyecto):
    python -m core.userdata.editable_fields
"""

__version__ = "1.5.0"
__all__ = [
    "ALL_EDIT_BITS",
    "EDITABLE_COLUMNS",
    "EDITABLE_FIELDS",
    "GUARDED_MAIN_COLUMNS",
    "INTEGER",
    "LINKED_COLUMNS",
    "MAIN_COLUMNS",
    "MAIN_TABLE",
    "NUMBER",
    "PAIRED_COLUMNS",
    "TEXT",
    "XMP_COLUMNS",
    "YEAR",
    "EditableField",
    "applies_sql",
    "applies_to",
    "bits_for",
    "default_title",
    "field_for",
    "file_title",
    "folder_value",
    "incomplete_pairs",
    "linked_values",
    "normalize_value",
    "pending_columns",
    "read_sql",
    "unless_pending_sql",
    "upsert_sql",
]

# Librerías estándar
import math
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

# Tipos de valor de un campo editable
TEXT = "text"
NUMBER = "number"
INTEGER = "integer"  # un entero positivo (la pista y el disco de una canción)
YEAR = "year"  # un año, en una columna de fecha (el de una canción)

# La tabla de los elementos: la de los campos comunes y la que lleva las marcas de pendiente
MAIN_TABLE = "media_items"


@dataclass(frozen=True, slots=True)
class EditableField:
    """Un metadato descriptivo editable.

    Attributes:
        column: Columna que guarda el valor (de 'media_items', o de 'table'). Única entre
            todos los campos: es su nombre en todo el mecanismo.
        bit: Su bit en 'media_items.metadata_edit_pending' (una potencia de 2, fija).
        xmp_tag: Etiqueta XMP (con su grupo, como la pide ExifTool) que se escribe siempre
            y se comprueba al releer. En los numéricos (GPS), la del XMP, que se escribe
            con la regla del GPS (ver la cabecera). Vacía = el campo no se guarda en XMP
            (solo en el '.arca.json'): el escritor de XMP no lo conoce.
        legacy_tags: Etiquetas antiguas (IPTC, EXIF) que se actualizan solo si el archivo
            ya las tiene. En los numéricos (GPS), su etiqueta EXIF.
        folder_key: Clave del valor en la entrada del archivo de carpeta ('.arca.json').
        multiline: True si admite saltos de línea (el pie de ilustración).
        kind: TEXT (texto), NUMBER (número decimal: el GPS), INTEGER (entero positivo:
            la pista y el disco) o YEAR (un año en una columna de fecha: el de una canción).
        limits: En los numéricos, (mínimo, máximo) admitidos; None = sin límites.
        circular: En los numéricos con límites, True si el valor da la vuelta (la
            dirección: 360° = 0°, −90° = 270°) en lugar de rechazarse.
        table: Tabla de detalles en la que está la columna (1:1 con 'media_items' por
            'media_id': 'track_details'...); None = en 'media_items'.
        media_types: Tipos de archivo a los que se aplica ('track'...); vacío = a todos.
            En los demás, el campo ni se guarda ni queda pendiente.
    """

    column: str
    bit: int
    xmp_tag: str
    legacy_tags: tuple[str, ...]
    folder_key: str
    multiline: bool = False
    kind: str = TEXT
    limits: tuple[float, float] | None = None
    circular: bool = False
    table: str | None = None
    media_types: tuple[str, ...] = ()


# Los campos editables, en el orden en que se escriben. Las claves del '.arca.json' son
# las mismas que las columnas (como 'rating' o 'keywords'), pero van aparte porque no
# pueden cambiar aunque cambie una columna.
EDITABLE_FIELDS: tuple[EditableField, ...] = (
    EditableField("title", 1, "XMP-dc:Title", ("IPTC:ObjectName",), "title"),
    EditableField(
        "description",
        2,
        "XMP-dc:Description",
        ("IPTC:Caption-Abstract", "IFD0:ImageDescription"),
        "description",
        multiline=True,
    ),
    # 'dc:creator' es una lista: se escribe como un solo elemento (con varios, se leen
    # unidos con ", " y, al editarlos, quedan en uno)
    EditableField("creator", 4, "XMP-dc:Creator", ("IPTC:By-line", "IFD0:Artist"), "creator"),
    EditableField(
        "copyright", 8, "XMP-dc:Rights", ("IPTC:CopyrightNotice", "IFD0:Copyright"), "copyright"
    ),
    EditableField(
        "sublocation", 16, "XMP-iptcCore:Location", ("IPTC:Sub-location",), "sublocation"
    ),
    EditableField("city", 32, "XMP-photoshop:City", ("IPTC:City",), "city"),
    EditableField("region", 64, "XMP-photoshop:State", ("IPTC:Province-State",), "region"),
    EditableField(
        "country", 128, "XMP-photoshop:Country", ("IPTC:Country-PrimaryLocationName",), "country"
    ),
    EditableField(
        "country_code",
        256,
        "XMP-iptcCore:CountryCode",
        ("IPTC:Country-PrimaryLocationCode",),
        "country_code",
    ),
    # GPS (números). La latitud y la longitud con signo (sur y oeste, negativos); la
    # altitud en metros (bajo el nivel del mar, negativa); la dirección en grados
    EditableField(
        "latitude", 512, "XMP-exif:GPSLatitude", ("GPS:GPSLatitude",), "latitude",
        kind=NUMBER, limits=(-90.0, 90.0),
    ),
    EditableField(
        "longitude", 1024, "XMP-exif:GPSLongitude", ("GPS:GPSLongitude",), "longitude",
        kind=NUMBER, limits=(-180.0, 180.0),
    ),
    EditableField(
        "altitude", 2048, "XMP-exif:GPSAltitude", ("GPS:GPSAltitude",), "altitude",
        kind=NUMBER,
    ),
    EditableField(
        "gps_direction", 4096, "XMP-exif:GPSImgDirection", ("GPS:GPSImgDirection",),
        "gps_direction", kind=NUMBER, limits=(0.0, 360.0), circular=True,
    ),
    # La actividad de un track: su clave ('hiking', 'mountain_biking'...; ver
    # 'core/tracks/activities.py'). Sin etiqueta XMP (un GPX no lleva XMP): va al
    # '.arca.json'. Está en la tabla de detalles de los tracks, que también rellena el
    # extractor con lo que diga el GPX
    EditableField(
        "activity_type", 8192, "", (), "activity",
        table="track_details", media_types=("track",),
    ),
    # Los campos de las canciones que no tienen columna común (MUS 6.2b): en su tabla de
    # detalles y solo de las canciones. Sin XMP (una canción no lleva XMP): en un MP3 van a
    # sus etiquetas ('audio_fields.py'); en los demás formatos, al '.arca.json'. El título,
    # el artista ('creator') y el comentario ('description') son los campos comunes de arriba
    EditableField("album", 16384, "", (), "album", table="audio_details", media_types=("audio",)),
    EditableField(
        "album_artist", 32768, "", (), "album_artist",
        table="audio_details", media_types=("audio",),
    ),
    EditableField(
        "track_number", 65536, "", (), "track_number",
        kind=INTEGER, table="audio_details", media_types=("audio",),
    ),
    EditableField(
        "track_total", 131072, "", (), "track_total",
        kind=INTEGER, table="audio_details", media_types=("audio",),
    ),
    EditableField(
        "disc_number", 262144, "", (), "disc_number",
        kind=INTEGER, table="audio_details", media_types=("audio",),
    ),
    EditableField(
        "disc_total", 524288, "", (), "disc_total",
        kind=INTEGER, table="audio_details", media_types=("audio",),
    ),
    EditableField("genre", 1048576, "", (), "genre", table="audio_details", media_types=("audio",)),
    EditableField(
        "composer", 2097152, "", (), "composer", table="audio_details", media_types=("audio",)
    ),
    # El año de una canción (MUS 7.1a): en la columna de la fecha de 'media_items' (en las
    # fotos y los vídeos, la de captura, que no se edita), solo de las canciones y como un
    # año. Su precisión y su origen van con él ('LINKED_COLUMNS')
    EditableField(
        "content_created_at", 4194304, "", (), "year", kind=YEAR, media_types=("audio",),
    ),
)  # fmt: skip

# Columnas que se editan siempre juntas (una sola caja del inspector, «GPS»): o las dos
# con valor, o las dos vacías. Media pareja no es una ubicación.
PAIRED_COLUMNS: tuple[tuple[str, str], ...] = (("latitude", "longitude"),)

# Columnas que van con un campo editable (no son campos: no tienen bit ni van al archivo):
# se guardan al editarlo ('linked_values') y, mientras está pendiente, lo leído del archivo
# no las pisa ('unless_pending_sql'). La precisión y el origen de la fecha van con el año
LINKED_COLUMNS: dict[str, tuple[str, ...]] = {
    "content_created_at": ("content_date_precision", "content_date_source"),
}
# Cada una, con el campo con el que va
_LINKED_OWNER: dict[str, str] = {
    linked: owner for owner, columns in LINKED_COLUMNS.items() for linked in columns
}

# Columnas editables, en el mismo orden
EDITABLE_COLUMNS: tuple[str, ...] = tuple(spec.column for spec in EDITABLE_FIELDS)

# Las que están en 'media_items' (las demás, cada una en su tabla de detalles)
MAIN_COLUMNS: tuple[str, ...] = tuple(spec.column for spec in EDITABLE_FIELDS if spec.table is None)

# Las de 'media_items' que lo leído de un archivo no pisa si su campo está pendiente: las
# editables y las que van con ellas ('unless_pending_sql' en el procesador)
GUARDED_MAIN_COLUMNS: frozenset[str] = frozenset(MAIN_COLUMNS) | frozenset(
    linked for owner in MAIN_COLUMNS for linked in LINKED_COLUMNS.get(owner, ())
)

# Las que sabe guardar el escritor de XMP (las que tienen etiqueta)
XMP_COLUMNS: tuple[str, ...] = tuple(spec.column for spec in EDITABLE_FIELDS if spec.xmp_tag)

# Todos los bits juntos (para quitar del pendiente lo que ya no es de ningún campo)
ALL_EDIT_BITS: int = sum(spec.bit for spec in EDITABLE_FIELDS)

_BY_COLUMN: dict[str, EditableField] = {spec.column: spec for spec in EDITABLE_FIELDS}

# Caracteres de control que se conservan: el salto de línea (solo en los campos de varias
# líneas) y el tabulador. Los demás (NUL, retroceso...) no tienen sentido en un texto y
# podrían romper el archivo de argumentos de ExifTool.
_KEPT_CONTROLS = frozenset("\n\t")

# Los años que valen: cuatro cifras («0000» es lo que escriben algunos programas sin dato)
_FIRST_YEAR = 1000
_LAST_YEAR = 9999


def field_for(column: str) -> EditableField:
    """El campo editable de una columna.

    Raises:
        ValueError: Si la columna no es un metadato editable.
    """
    try:
        return _BY_COLUMN[column]
    except KeyError:
        raise ValueError(f"Campo no editable: {column!r}") from None


def bits_for(columns: Iterable[str]) -> int:
    """Máscara de bits de unas columnas editables (ValueError si alguna no lo es)."""
    mask = 0
    for column in columns:
        mask |= field_for(column).bit
    return mask


def pending_columns(mask: int) -> tuple[str, ...]:
    """Columnas cuyo bit está puesto en una máscara, en el orden de 'EDITABLE_FIELDS'.

    Los bits que no son de ningún campo se ignoran.
    """
    return tuple(spec.column for spec in EDITABLE_FIELDS if mask & spec.bit)


def _pending_sql(spec: EditableField) -> str:
    """Expresión SQL (verdadera o falsa) de si el campo está pendiente de escribir, vista
    desde una sentencia sobre SU tabla."""
    if spec.table is None:
        return f"metadata_edit_pending & {spec.bit}"
    # Desde la tabla de detalles, la marca está en la fila de 'media_items' del elemento
    return (
        f"(SELECT m.metadata_edit_pending FROM {MAIN_TABLE} AS m "
        f"WHERE m.id = {spec.table}.media_id) & {spec.bit}"
    )


def unless_pending_sql(column: str) -> str:
    """Asignación SQL que no pisa una columna editable si su bit está pendiente.

    Para un UPDATE de la tabla del campo ('media_items' o su tabla de detalles) con lo
    leído de un archivo: el cambio del usuario aún sin escribir es más nuevo. Se comprueba
    en la misma sentencia, así que tampoco se pierde una edición hecha mientras se leía
    el archivo. Lleva un parámetro ('?').

    Ejemplo: 'title = CASE WHEN metadata_edit_pending & 1 THEN title ELSE ? END'.

    Vale también para una columna que va con un campo ('LINKED_COLUMNS'): se protege con
    el bit de ese campo (la precisión de la fecha, con el del año).

    Raises:
        ValueError: Si la columna no es editable ni va con un campo editable (así el
            nombre es siempre de la lista cerrada y se puede poner en el SQL sin riesgo).
    """
    spec = field_for(_LINKED_OWNER.get(column, column))
    return f"{column} = CASE WHEN {_pending_sql(spec)} THEN {column} ELSE ? END"


def upsert_sql(table: str, column: str) -> str:
    """Asignación para el 'ON CONFLICT ... DO UPDATE SET' con el que el procesador guarda
    una tabla de detalles: el valor nuevo ('excluded'), salvo que la columna sea un campo
    editable de esa tabla pendiente de escribir (entonces se queda como está)."""
    spec = _BY_COLUMN.get(column)
    if spec is None or spec.table != table:
        return f"{column} = excluded.{column}"
    return (
        f"{column} = CASE WHEN {_pending_sql(spec)} THEN {table}.{column} "
        f"ELSE excluded.{column} END"
    )


def read_sql(column: str) -> str:
    """Expresión SQL que LEE una columna editable desde una consulta sobre 'media_items'
    (sin alias): la propia columna o, si está en una tabla de detalles, una subconsulta
    por su clave primaria.

    Raises:
        ValueError: Si la columna no es editable.
    """
    spec = field_for(column)
    if spec.table is None:
        return column
    return f"(SELECT d.{column} FROM {spec.table} AS d WHERE d.media_id = {MAIN_TABLE}.id)"


def applies_sql(column: str) -> tuple[str, tuple[str, ...]]:
    """Condición SQL (para un WHERE sobre 'media_items', empieza por ' AND ') y sus
    parámetros que deja solo los elementos a los que se aplica un campo; vacía si se aplica
    a todos."""
    types = field_for(column).media_types
    if not types:
        return "", ()
    return f" AND media_type IN ({', '.join('?' * len(types))})", types


def applies_to(column: str, media_type: str | None) -> bool:
    """True si un campo editable se aplica a ese tipo de archivo ('audio', 'image'...).

    Raises:
        ValueError: Si la columna no es editable.
    """
    types = field_for(column).media_types
    return not types or media_type in types


def linked_values(column: str, value: object) -> dict[str, str | None]:
    """Lo que se guarda, junto a un campo editable ya normalizado, en las columnas que van
    con él ('LINKED_COLUMNS'): con un año, su precisión ('year'; el origen se queda como
    estaba); sin año, ni precisión ni origen (una fecha que no está no sale de ningún
    sitio). Vacío si no tiene ninguna."""
    if column not in LINKED_COLUMNS:
        return {}
    if value is None:
        return dict.fromkeys(LINKED_COLUMNS[column])
    return {"content_date_precision": "year"}


def folder_value(column: str, value: object) -> object:
    """Un valor ya normalizado tal como se guarda en el '.arca.json': el año, como número
    (1999); los demás, tal cual ('normalize_value' lo devuelve a la columna al leerlo).

    Raises:
        ValueError: Si la columna no es editable.
    """
    if field_for(column).kind == YEAR and isinstance(value, str):
        return int(value[:4])
    return value


def normalize_value(column: str, value: object) -> str | float | int | None:
    """Valor editado tal como se guarda: texto limpio o número, o None si queda vacío.

    Entero (la pista, el disco): un int positivo; vacío, None ('_normalize_integer').

    Año (el de una canción): un int de cuatro cifras, como la fecha de su 1 de enero
    («1999-01-01 00:00:00», el formato de la columna); vacío, None ('_normalize_year').

    Texto:
    - Los finales de línea pasan a ser '\\n'; en un campo de una línea, cada salto de
      línea pasa a ser un espacio.
    - Se quitan los caracteres de control (salvo el salto de línea y el tabulador) y los
      espacios del principio y del final.

    Número (el GPS): un int o un float finito, dentro de los límites del campo (la
    dirección da la vuelta: 360° = 0°). "" o solo espacios = vacío, que es como el
    '.arca.json' guarda un campo vaciado. Un número escrito como texto ('41.3') NO se
    acepta: lo que escribe el usuario lo interpreta el inspector.

    Args:
        column: Columna editable.
        value: Lo escrito por el usuario (None = vacío).

    Raises:
        ValueError: Si la columna no es editable, o el número no es finito o se sale de
            los límites del campo.
        TypeError: Si el valor no es del tipo del campo (texto, o número en el GPS).
    """
    spec = field_for(column)
    if spec.kind == NUMBER:
        return _normalize_number(spec, value)
    if spec.kind == INTEGER:
        return _normalize_integer(spec, value)
    if spec.kind == YEAR:
        return _normalize_year(spec, value)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"Valor no válido para {column!r}: {value!r} (se esperaba texto)")
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if not spec.multiline:
        text = text.replace("\n", " ")
    text = "".join(
        ch for ch in text if ch in _KEPT_CONTROLS or unicodedata.category(ch) != "Cc"
    )
    text = text.strip()
    return text or None


def _normalize_number(spec: EditableField, value: object) -> float | None:
    """Valor de un campo numérico: float dentro de sus límites, o None si está vacío."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    # 'bool' es un 'int' en Python: True no es una altitud
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Valor no válido para {spec.column!r}: {value!r} (se esperaba un número)")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Valor no válido para {spec.column!r}: {value!r}")
    if spec.limits is None:
        return number
    low, high = spec.limits
    if spec.circular:
        number = low + (number - low) % (high - low)
    elif not low <= number <= high:
        raise ValueError(f"{spec.column!r} debe estar entre {low:g} y {high:g}: {number:g}")
    return number


def _normalize_integer(spec: EditableField, value: object) -> int | None:
    """Valor de un campo entero (la pista, el disco): un entero positivo, o None si está
    vacío. Como en el GPS, un número escrito como texto ('3') no se acepta."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Valor no válido para {spec.column!r}: {value!r} (se esperaba un entero)")
    if value <= 0:
        raise ValueError(f"{spec.column!r} debe ser un número positivo: {value}")
    return value


def _normalize_year(spec: EditableField, value: object) -> str | None:
    """Valor de un año: la fecha de su 1 de enero, o None si está vacío. Como en el GPS, un
    año escrito como texto ('1999') no se acepta: lo que escribe el usuario lo interpreta
    el inspector."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Valor no válido para {spec.column!r}: {value!r} (se esperaba un año)")
    if not _FIRST_YEAR <= value <= _LAST_YEAR:
        raise ValueError(f"{spec.column!r} debe ser un año de cuatro cifras: {value}")
    return f"{value:04d}-01-01 00:00:00"


def incomplete_pairs(values: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Parejas de 'PAIRED_COLUMNS' a las que les falta una mitad.

    Una pareja está incompleta si solo viene una de sus columnas, o si una está vacía
    (None) y la otra no. Las que no vienen en absoluto no cuentan.
    """
    incomplete = []
    for pair in PAIRED_COLUMNS:
        present = [column in values for column in pair]
        if not any(present):
            continue
        if not all(present) or (values[pair[0]] is None) != (values[pair[1]] is None):
            incomplete.append(pair)
    return tuple(incomplete)


def default_title(file_name: str) -> str:
    """Título de un archivo sin título: su nombre sin extensión.

    Es el mismo que pone el escáner al catalogarlo ('ScanCandidate.default_title' en
    core/catalog/folder_scanner.py): si cambia uno, tiene que cambiar el otro.
    """
    return Path(file_name).stem


def file_title(title: str | None, file_name: str) -> str | None:
    """Título PROPIO de un archivo: None si no tiene (vacío o igual a su nombre).

    Es lo que se escribe en el archivo y lo que se muestra al editar. Un título escrito a
    propósito igual al nombre del archivo cuenta también como «sin título» (aproximación
    aceptada: así una foto sin título no muestra «IMG_0001»).
    """
    if not title or title == default_title(file_name):
        return None
    return title


if __name__ == "__main__":
    # Autoprueba sin archivos ni base de datos.
    # Ejecutar desde la raíz del proyecto:  python -m core.userdata.editable_fields

    from core.metadata.image.fields import IMAGE_FIELDS

    # 1. Bits: potencias de 2 distintas; columnas y claves sin repetir
    bits = [spec.bit for spec in EDITABLE_FIELDS]
    assert all(bit > 0 and bit & (bit - 1) == 0 for bit in bits), bits
    assert len(set(bits)) == len(bits) and ALL_EDIT_BITS == sum(bits) == (1 << 23) - 1
    assert len(set(EDITABLE_COLUMNS)) == len(EDITABLE_COLUMNS)
    assert len({spec.folder_key for spec in EDITABLE_FIELDS}) == len(EDITABLE_FIELDS)
    # Las claves de los datos del usuario que ya están en el '.arca.json' no se reutilizan
    assert not {spec.folder_key for spec in EDITABLE_FIELDS} & {
        "rating", "flag", "color_label", "keywords", "updated_at",
    }  # fmt: skip
    print("Campos editables:", ", ".join(EDITABLE_COLUMNS))

    # 2. Se escribe en las mismas etiquetas de las que se lee, y en el mismo orden. En el
    #    GPS, la lectura empieza también por el XMP, y lo antiguo es su etiqueta EXIF (la
    #    lectura usa el compuesto de ExifTool, que sale de ella)
    sources = {spec.column: spec.sources for spec in IMAGE_FIELDS}
    for spec in EDITABLE_FIELDS:
        if not spec.xmp_tag:
            # Sin XMP: solo va al '.arca.json' (no tiene etiquetas antiguas que mantener)
            assert spec.legacy_tags == () and spec.column not in XMP_COLUMNS, spec.column
            continue
        assert spec.xmp_tag.startswith("XMP-"), spec.xmp_tag
        if spec.kind == TEXT:
            assert sources[spec.column] == (spec.xmp_tag, *spec.legacy_tags), spec.column
        else:
            assert spec.kind == NUMBER and sources[spec.column][0] == spec.xmp_tag, spec.column
            assert len(spec.legacy_tags) == 1 and spec.legacy_tags[0].startswith("GPS:"), spec
    print("Etiquetas: las mismas que la lectura de imagen (IMAGE_FIELDS)")
    # Los campos de imagen de siempre están en 'media_items', con XMP y para todos los
    # tipos; el año de las canciones, también en 'media_items', pero solo de ellas
    assert XMP_COLUMNS == EDITABLE_COLUMNS[:13]
    assert MAIN_COLUMNS == (*XMP_COLUMNS, "content_created_at")
    assert all(not field_for(c).media_types for c in XMP_COLUMNS)
    # La actividad: en su tabla de detalles, sin XMP y solo de los tracks
    activity = field_for("activity_type")
    assert (activity.table, activity.xmp_tag, activity.folder_key) == ("track_details", "", "activity")
    assert activity.media_types == ("track",) and activity.bit == 8192
    # Los de las canciones: en 'audio_details', sin XMP y solo de las canciones; la pista y
    # el disco, enteros
    audio_columns = EDITABLE_COLUMNS[14:-1]
    assert audio_columns == (
        "album", "album_artist", "track_number", "track_total", "disc_number", "disc_total",
        "genre", "composer",
    ), audio_columns  # fmt: skip
    for column in audio_columns:
        spec = field_for(column)
        assert (spec.table, spec.xmp_tag, spec.media_types) == ("audio_details", "", ("audio",))
        assert spec.folder_key == column
        assert (spec.kind == INTEGER) == column.endswith(("_number", "_total")), column

    # 3. Máscaras de bits
    assert bits_for(["title", "city"]) == 1 | 32
    assert bits_for([]) == 0
    assert pending_columns(1 | 32) == ("title", "city")
    assert pending_columns(ALL_EDIT_BITS) == EDITABLE_COLUMNS
    assert pending_columns((1 << 40) | 2) == ("description",)  # un bit desconocido se ignora
    assert pending_columns(512 | 1024 | 4096) == ("latitude", "longitude", "gps_direction")
    for bad in (lambda: bits_for(["rating"]), lambda: field_for("file_name")):
        try:
            bad()
            raise AssertionError("debía rechazar una columna no editable")
        except ValueError:
            pass
    print("Máscaras de bits: correctas")

    # 3b. La asignación que protege lo pendiente, probada en SQLite
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE media_items (id INTEGER, city TEXT, metadata_edit_pending INTEGER)")
    db.executemany("INSERT INTO media_items VALUES (?, 'Soria', ?)", [(1, 0), (2, 32), (3, 1)])
    db.execute(f"UPDATE media_items SET {unless_pending_sql('city')}", ("León",))
    assert dict(db.execute("SELECT id, city FROM media_items")) == {
        1: "León", 2: "Soria", 3: "León"
    }  # fmt: skip
    try:
        unless_pending_sql("file_name")
        raise AssertionError("debía rechazar una columna no editable")
    except ValueError:
        pass
    db.close()

    # 3c. Un campo de una tabla de detalles: leerlo, protegerlo y a quién se aplica
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE media_items (id INTEGER PRIMARY KEY, media_type TEXT, city TEXT, "
        "metadata_edit_pending INTEGER)"
    )
    db.execute(
        "CREATE TABLE track_details (media_id INTEGER PRIMARY KEY, activity_type TEXT, "
        "distance_m REAL)"
    )
    # 1: sin editar; 2: actividad pendiente (8192); 3: otro campo pendiente; 4: una foto
    db.executemany(
        "INSERT INTO media_items VALUES (?, ?, 'Soria', ?)",
        [(1, "track", 0), (2, "track", 8192), (3, "track", 32), (4, "photo", 0)],
    )
    db.executemany(
        "INSERT INTO track_details VALUES (?, 'hiking', 1.0)", [(1,), (2,), (3,)]
    )
    assert read_sql("city") == "city"
    read = dict(db.execute(f"SELECT id, {read_sql('activity_type')} FROM media_items"))
    assert read == {1: "hiking", 2: "hiking", 3: "hiking", 4: None}, read
    # Lo leído del archivo no pisa la actividad pendiente (ni en un UPDATE ni en el
    # 'INSERT ... ON CONFLICT' del procesador); las columnas normales, sí se actualizan
    db.execute(f"UPDATE track_details SET {unless_pending_sql('activity_type')}", ("cycling",))
    assert dict(db.execute("SELECT media_id, activity_type FROM track_details")) == {
        1: "cycling", 2: "hiking", 3: "cycling"
    }  # fmt: skip
    assert upsert_sql("track_details", "distance_m") == "distance_m = excluded.distance_m"
    assert upsert_sql("video_details", "activity_type") == "activity_type = excluded.activity_type"
    for media_id in (1, 2, 5):
        db.execute(
            "INSERT INTO track_details (media_id, activity_type, distance_m) VALUES (?, 'walking', 9.0) "
            f"ON CONFLICT(media_id) DO UPDATE SET {upsert_sql('track_details', 'activity_type')}, "
            f"{upsert_sql('track_details', 'distance_m')}",
            (media_id,),
        )
    rows = {r[0]: r[1:] for r in db.execute("SELECT * FROM track_details")}
    assert rows == {1: ("walking", 9.0), 2: ("hiking", 9.0), 3: ("cycling", 1.0), 5: ("walking", 9.0)}, rows
    # A quién se aplica: la actividad, solo a los tracks; los campos de siempre, a todos
    condition, parameters = applies_sql("activity_type")
    ids = [r[0] for r in db.execute(f"SELECT id FROM media_items WHERE 1{condition}", parameters)]
    assert ids == [1, 2, 3] and applies_sql("city") == ("", ())
    db.close()

    # 4. Valores: limpios, vacío = None, saltos de línea solo donde caben
    assert normalize_value("title", "  Atardecer en León  ") == "Atardecer en León"
    assert normalize_value("title", "   ") is None
    assert normalize_value("title", "") is None
    assert normalize_value("title", None) is None
    assert normalize_value("title", "Una\nlínea") == "Una línea"
    assert normalize_value("description", "Primera\r\nSegunda\rTercera\n") == (
        "Primera\nSegunda\nTercera"
    )
    assert normalize_value("copyright", "© 2026\x00 Javier\tRojo") == "© 2026 Javier\tRojo"
    for bad in (("title", 3), ("title", ["a"]), ("rating", "3")):
        try:
            normalize_value(*bad)
            raise AssertionError(f"debía rechazar {bad}")
        except (ValueError, TypeError):
            pass
    print("Valores: normalizados")

    # 4b. Números (GPS): float, vacío = None, límites; la dirección da la vuelta
    assert normalize_value("latitude", 41.3874) == 41.3874
    assert normalize_value("longitude", -3) == -3.0 and isinstance(normalize_value("altitude", 100), float)
    assert normalize_value("altitude", -430.5) == -430.5  # bajo el nivel del mar
    for empty in (None, "", "   "):  # "" = vaciado en el '.arca.json'
        assert normalize_value("latitude", empty) is None
    assert normalize_value("gps_direction", 360) == 0.0
    assert normalize_value("gps_direction", -90) == 270.0
    assert normalize_value("gps_direction", 292.47) == 292.47
    assert normalize_value("latitude", 90) == 90.0 and normalize_value("longitude", -180) == -180.0
    for bad, error in ((("latitude", 90.5), ValueError), (("longitude", -181), ValueError),
                       (("altitude", float("nan")), ValueError), (("altitude", float("inf")), ValueError),
                       (("latitude", "41.3"), TypeError), (("altitude", True), TypeError),
                       (("gps_direction", [90]), TypeError)):  # fmt: skip
        try:
            normalize_value(*bad)
            raise AssertionError(f"debía rechazar {bad}")
        except error:
            pass
    print("Números del GPS: normalizados y dentro de sus límites")

    # 4b'. Enteros (la pista, el disco): positivos; vacío = None
    assert normalize_value("track_number", 3) == 3 and normalize_value("disc_total", 12) == 12
    for empty in (None, "", "  "):
        assert normalize_value("track_total", empty) is None
    for bad, error in ((("track_number", 0), ValueError), (("track_number", -2), ValueError),
                       (("track_number", 3.0), TypeError), (("disc_number", "3"), TypeError),
                       (("track_total", True), TypeError)):  # fmt: skip
        try:
            normalize_value(*bad)
            raise AssertionError(f"debía rechazar {bad}")
        except error:
            pass
    assert normalize_value("album", "  Destrangis ") == "Destrangis"
    print("Enteros de la pista y el disco: positivos")

    # 4b''. El año de una canción: solo de las canciones, como la fecha de su 1 de enero;
    #       su precisión y su origen van con él; en el '.arca.json', como número
    year = field_for("content_created_at")
    assert (year.kind, year.bit, year.folder_key, year.table, year.xmp_tag) == (
        YEAR, 4194304, "year", None, ""
    )  # fmt: skip
    assert applies_to("content_created_at", "audio") and not applies_to("content_created_at", "image")
    assert applies_to("city", "image") and applies_to("album", "audio") and not applies_to("album", "video")
    assert normalize_value("content_created_at", 1999) == "1999-01-01 00:00:00"
    assert normalize_value("content_created_at", 1000) == "1000-01-01 00:00:00"
    for empty in (None, "", "  "):
        assert normalize_value("content_created_at", empty) is None
    for bad, error in (((999,), ValueError), ((10000,), ValueError), ((0,), ValueError),
                       (("1999",), TypeError), ((1999.0,), TypeError), ((True,), TypeError)):  # fmt: skip
        try:
            normalize_value("content_created_at", *bad)
            raise AssertionError(f"debía rechazar {bad}")
        except error:
            pass
    assert linked_values("content_created_at", "1999-01-01 00:00:00") == {
        "content_date_precision": "year"
    }  # fmt: skip
    assert linked_values("content_created_at", None) == {
        "content_date_precision": None, "content_date_source": None
    }  # fmt: skip
    assert linked_values("title", "x") == {} and linked_values("album", None) == {}
    assert folder_value("content_created_at", "1999-01-01 00:00:00") == 1999
    assert folder_value("content_created_at", None) is None and folder_value("city", "León") == "León"
    # De ida y vuelta por el '.arca.json'
    assert normalize_value("content_created_at", folder_value("content_created_at", "1999-01-01 00:00:00")) == (
        "1999-01-01 00:00:00"
    )  # fmt: skip
    # Lo leído del archivo no pisa la fecha ni su precisión ni su origen si el año está
    # pendiente; las demás columnas, sí
    assert GUARDED_MAIN_COLUMNS == frozenset(MAIN_COLUMNS) | {"content_date_precision", "content_date_source"}
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE media_items (id INTEGER, content_created_at TEXT, content_date_precision TEXT, "
        "content_date_source TEXT, duration REAL, metadata_edit_pending INTEGER)"
    )
    db.executemany(
        "INSERT INTO media_items VALUES (?, '1999-01-01 00:00:00', 'year', 'id3', 1.0, ?)",
        [(1, 0), (2, 4194304)],
    )
    columns = ("content_created_at", "content_date_precision", "content_date_source")
    sets = ", ".join(unless_pending_sql(column) for column in columns)
    db.execute(f"UPDATE media_items SET {sets}, duration = 2.0", ("2001-05-04 00:00:00", "day", "mp4"))
    rows = {r[0]: r[1:] for r in db.execute("SELECT * FROM media_items")}
    assert rows == {
        1: ("2001-05-04 00:00:00", "day", "mp4", 2.0, 0),
        2: ("1999-01-01 00:00:00", "year", "id3", 2.0, 4194304),
    }, rows  # fmt: skip
    db.close()
    print("El año de las canciones: un año, con su precisión y su origen")

    # 4c. La latitud y la longitud, siempre juntas
    assert incomplete_pairs({"title": "x"}) == ()
    assert incomplete_pairs({"latitude": 41.0, "longitude": 2.0}) == ()
    assert incomplete_pairs({"latitude": None, "longitude": None}) == ()  # vaciar el GPS
    for half in ({"latitude": 41.0}, {"longitude": 2.0}, {"latitude": 41.0, "longitude": None}):
        assert incomplete_pairs(half) == (("latitude", "longitude"),), half
    print("Latitud y longitud: juntas o ninguna")

    # 5. Título: sin título propio, el nombre del archivo
    assert default_title("IMG_0001.HEIC") == "IMG_0001"
    assert default_title("Vacaciones 2026.final.jpg") == "Vacaciones 2026.final"
    assert file_title("IMG_0001", "IMG_0001.HEIC") is None
    assert file_title(None, "IMG_0001.HEIC") is None
    assert file_title("Atardecer", "IMG_0001.HEIC") == "Atardecer"
    print("Título por defecto: el nombre sin extensión, que cuenta como «sin título»")

    print("Autoprueba finalizada correctamente.")
