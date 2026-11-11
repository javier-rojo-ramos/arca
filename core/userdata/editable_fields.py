"""Metadatos descriptivos que el usuario edita en la aplicación y se escriben en los archivos.

Este módulo NO depende de Qt ni de la base de datos: es una lista declarativa.

Cada campo editable (título, pie de ilustración, creador, copyright, ubicación y GPS) es
una línea de 'EDITABLE_FIELDS', y de esa línea sale todo lo demás:
    - 'update_metadata_fields' (core/catalog/media_queries.py) guarda el valor en su
      columna de 'media_items' y pone el BIT del campo en 'metadata_edit_pending'
      (pendiente de escribir en el archivo);
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

Cómo añadir un campo:
    1. Una línea más en 'EDITABLE_FIELDS' con un BIT NUEVO (el doble del último). Un bit
       no se cambia ni se reutiliza nunca: los catálogos lo tienen guardado en
       'metadata_edit_pending'.
    2. La columna tiene que existir en 'media_items' (si no, una migración) y leerse de
       las mismas etiquetas (la autoprueba lo comprueba con 'IMAGE_FIELDS').
    3. La clave del '.arca.json' tampoco se cambia después: está en los archivos de los
       usuarios.

1.2.0 GPS: latitud, longitud, altitud y dirección (bits 512 a 4096), campos NUMÉRICOS con
      sus límites ('kind', 'limits', 'circular'); la latitud y la longitud, juntas
      ('PAIRED_COLUMNS', 'incomplete_pairs').
1.1.0 'unless_pending_sql': asignación que no pisa una columna pendiente de escribir.
1.0.0 Primera versión: título, pie de ilustración, creador, copyright y ubicación.

Prueba rápida (desde la raíz del proyecto):
    python -m core.userdata.editable_fields
"""

__version__ = "1.2.0"
__all__ = [
    "ALL_EDIT_BITS",
    "EDITABLE_COLUMNS",
    "EDITABLE_FIELDS",
    "NUMBER",
    "PAIRED_COLUMNS",
    "TEXT",
    "EditableField",
    "bits_for",
    "default_title",
    "field_for",
    "file_title",
    "incomplete_pairs",
    "normalize_value",
    "pending_columns",
    "unless_pending_sql",
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


@dataclass(frozen=True, slots=True)
class EditableField:
    """Un metadato descriptivo editable.

    Attributes:
        column: Columna de 'media_items' que guarda el valor.
        bit: Su bit en 'media_items.metadata_edit_pending' (una potencia de 2, fija).
        xmp_tag: Etiqueta XMP (con su grupo, como la pide ExifTool) que se escribe siempre
            y se comprueba al releer. En los numéricos (GPS), la del XMP, que se escribe
            con la regla del GPS (ver la cabecera).
        legacy_tags: Etiquetas antiguas (IPTC, EXIF) que se actualizan solo si el archivo
            ya las tiene. En los numéricos (GPS), su etiqueta EXIF.
        folder_key: Clave del valor en la entrada del archivo de carpeta ('.arca.json').
        multiline: True si admite saltos de línea (el pie de ilustración).
        kind: TEXT (texto) o NUMBER (número decimal: el GPS).
        limits: En los numéricos, (mínimo, máximo) admitidos; None = sin límites.
        circular: En los numéricos con límites, True si el valor da la vuelta (la
            dirección: 360° = 0°, −90° = 270°) en lugar de rechazarse.
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
)  # fmt: skip

# Columnas que se editan siempre juntas (una sola caja del inspector, «GPS»): o las dos
# con valor, o las dos vacías. Media pareja no es una ubicación.
PAIRED_COLUMNS: tuple[tuple[str, str], ...] = (("latitude", "longitude"),)

# Columnas editables, en el mismo orden
EDITABLE_COLUMNS: tuple[str, ...] = tuple(spec.column for spec in EDITABLE_FIELDS)

# Todos los bits juntos (para quitar del pendiente lo que ya no es de ningún campo)
ALL_EDIT_BITS: int = sum(spec.bit for spec in EDITABLE_FIELDS)

_BY_COLUMN: dict[str, EditableField] = {spec.column: spec for spec in EDITABLE_FIELDS}

# Caracteres de control que se conservan: el salto de línea (solo en los campos de varias
# líneas) y el tabulador. Los demás (NUL, retroceso...) no tienen sentido en un texto y
# podrían romper el archivo de argumentos de ExifTool.
_KEPT_CONTROLS = frozenset("\n\t")


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


def unless_pending_sql(column: str) -> str:
    """Asignación SQL que no pisa una columna editable si su bit está pendiente.

    Para un UPDATE de 'media_items' con lo leído de un archivo: el cambio del usuario aún
    sin escribir es más nuevo. Se comprueba en la misma sentencia, así que tampoco se
    pierde una edición hecha mientras se leía el archivo. Lleva un parámetro ('?').

    Ejemplo: 'title = CASE WHEN metadata_edit_pending & 1 THEN title ELSE ? END'.

    Raises:
        ValueError: Si la columna no es editable (así el nombre es siempre de la lista
            cerrada y se puede poner en el SQL sin riesgo).
    """
    bit = field_for(column).bit
    return f"{column} = CASE WHEN metadata_edit_pending & {bit} THEN {column} ELSE ? END"


def normalize_value(column: str, value: object) -> str | float | None:
    """Valor editado tal como se guarda: texto limpio o número, o None si queda vacío.

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
    assert len(set(bits)) == len(bits) and ALL_EDIT_BITS == sum(bits) == 8191
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
        assert spec.xmp_tag.startswith("XMP-"), spec.xmp_tag
        if spec.kind == TEXT:
            assert sources[spec.column] == (spec.xmp_tag, *spec.legacy_tags), spec.column
        else:
            assert spec.kind == NUMBER and sources[spec.column][0] == spec.xmp_tag, spec.column
            assert len(spec.legacy_tags) == 1 and spec.legacy_tags[0].startswith("GPS:"), spec
    print("Etiquetas: las mismas que la lectura de imagen (IMAGE_FIELDS)")

    # 3. Máscaras de bits
    assert bits_for(["title", "city"]) == 1 | 32
    assert bits_for([]) == 0
    assert pending_columns(1 | 32) == ("title", "city")
    assert pending_columns(ALL_EDIT_BITS) == EDITABLE_COLUMNS
    assert pending_columns((1 << 20) | 2) == ("description",)  # un bit desconocido se ignora
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
