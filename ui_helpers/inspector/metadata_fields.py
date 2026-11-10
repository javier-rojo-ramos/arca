"""Campos y vistas de la sección «Metadatos» del inspector.

>>> AQUÍ SE AÑADEN CAMPOS Y VISTAS. <<<

Este módulo NO depende de Qt: solo declara QUÉ se muestra. Lo usa la sección
('metadata_section.py'), que pide los valores a 'core/catalog/selection_metadata.py' y
pinta las filas.

CAMPO ('InspectorField'): una línea en '_FIELD_LIST' con
    key         clave estable en inglés (la de las colecciones inteligentes cuando existe:
                'iso', 'city'...). Se guardará en 'settings.json' para la vista personalizada.
    label       etiqueta corta de la fila («Exposición»).
    long_label  nombre completo, para el texto emergente de la etiqueta.
    columns     de qué columnas sale para cada tipo de medio ('photo', 'video' o '*'):
                ver 'core/catalog/selection_metadata.py'. Un tipo sin columnas no tiene
                ese campo (la ISO de un vídeo): con solo vídeos, la fila sale en blanco.
    format      función que recibe los valores de sus columnas (en ese orden) y devuelve
                el texto de la fila (ver 'formatting.py').
    tooltip     (opcional) función como 'format' para el texto emergente del valor
                (p. ej. los grados exactos de la dirección).

VISTA ('MetadataPreset'): una línea en 'PRESETS': clave, nombre del desplegable y la
lista de campos, con 'SEPARATOR' donde se quiera una línea de separación. Arriba de TODAS
las vistas va 'COMMON_HEAD' (dimensiones y recorte; fechas de captura, digitalización y
modificación).

Las filas son SIEMPRE las de la vista, con lo que haya: el valor común, «Varios» si hay
valores distintos, o en blanco. Así la sección no cambia de alto al cambiar la selección
(decidido por el autor el 02/11/2026).

Cómo añadir:
    - Un campo: una línea en '_FIELD_LIST' (y, si hace falta, su función en
      'formatting.py') y su clave en las vistas donde deba salir.
    - Una vista (IPTC, DNG...): una línea en 'PRESETS'. Sale sola en el desplegable.
    - La vista personalizada (más adelante): una lista de claves guardada en
      'settings.json'; 'preset_rows' ya acepta cualquier lista de claves.

1.5.0 'EDITABLE_KEYS' (los campos que se editan en la sección: título, pie, creador y
      copyright) y 'editor_value' (lo que muestra su caja).
1.4.0 Título, Pie (de ilustración), Creador y Copyright, de solo lectura por ahora, en
      «Por defecto» y «Ubicación» (paso C.5). El título es el propio ('m.file_title'): sin
      título, en blanco, no el nombre del archivo.
1.3.1 «Lugar» también como nombre completo de 'sublocation' (antes «Ubicación
      secundaria»): el mismo en todas partes (decidido por el autor el 09/11/2026).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.inspector.metadata_fields
"""

__version__ = "1.5.0"
__all__ = [
    "COMMON_HEAD",
    "DEFAULT_PRESET",
    "EDITABLE_KEYS",
    "FIELDS",
    "MIXED_TEXT",
    "PRESETS",
    "SEPARATOR",
    "DisplayValue",
    "InspectorField",
    "MetadataPreset",
    "display_value",
    "editor_value",
    "preset_rows",
    "sources_for",
]

# Librerías estándar
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

# Módulos del proyecto
from core.catalog.selection_metadata import MIXED, VALUE, FieldSource, FieldValue
from core.userdata.editable_fields import EDITABLE_COLUMNS
from ui_helpers.inspector.formatting import (
    EXPOSURE_PROGRAMS,
    FLASH_STATES,
    METERING_MODES,
    format_altitude,
    format_camera,
    format_codec,
    format_datetime,
    format_dimensions,
    format_direction,
    format_duration,
    format_exposure,
    format_exposure_exact,
    format_exposure_bias,
    format_focal_length,
    format_frame_rate,
    format_gps,
    format_iso,
)

# Marca de "línea de separación" en las listas de campos de las vistas
SEPARATOR = "-"

# Texto de un campo con valores distintos en la selección
MIXED_TEXT = "Varios"


@dataclass(frozen=True, slots=True)
class InspectorField:
    """Un campo de la sección «Metadatos» (ver el docstring del módulo)."""

    key: str
    label: str
    long_label: str
    columns: Mapping[str, tuple[str, ...]]
    format: Callable[..., str]
    tooltip: Callable[..., str] | None = None

    @property
    def source(self) -> FieldSource:
        """De dónde sale (lo que necesita 'selection_metadata.fetch_field_values')."""
        return FieldSource(self.key, self.columns)


@dataclass(frozen=True, slots=True)
class MetadataPreset:
    """Una vista de la sección: su nombre en el desplegable y sus campos (sin la cabecera común).

    Attributes:
        key: Clave estable (se guarda en 'settings.json').
        title: Nombre en el desplegable.
        keys: Claves de sus campos, con 'SEPARATOR' donde vaya una línea.
    """

    key: str
    title: str
    keys: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DisplayValue:
    """Lo que se pinta en el valor de una fila.

    Attributes:
        text: Texto ('' = en blanco).
        tooltip: Texto emergente ('' = ninguno).
        secondary: True para «Varios» (se pinta en gris, como las etiquetas).
    """

    text: str = ""
    tooltip: str = ""
    secondary: bool = False


# --- Funciones de formato propias de algún campo -------------------------------------


def _code_text(table: Mapping[int, str]) -> Callable[[Any], str]:
    """Formato de un código EXIF traducido con una tabla (un código desconocido, tal cual)."""

    def text(code: Any) -> str:
        if code is None:
            return ""
        try:
            return table.get(int(code), str(code))
        except (TypeError, ValueError):
            return str(code)

    return text


def _plain(value: Any) -> str:
    """Texto tal cual ('' si no hay)."""
    return "" if value is None else str(value).strip()


def _one_line(value: Any) -> str:
    """Texto de varias líneas en una sola (el pie, en una fila de una línea)."""
    return " ".join(_plain(value).split("\n"))


def _multiline_tooltip(value: Any) -> str:
    """El texto completo, con sus saltos de línea, si tiene más de una."""
    text = _plain(value)
    return text if "\n" in text else ""


def _direction_tooltip(degrees: Any) -> str:
    """Grados exactos de la dirección («292,5°»)."""
    if degrees is None:
        return ""
    return f"{float(degrees):.1f}°".replace(".", ",")


def _gps_tooltip(latitude: Any, longitude: Any) -> str:
    """Coordenadas en grados decimales («42,682089, 0,069991»), útiles para copiarlas."""
    if latitude is None or longitude is None:
        return ""
    return f"{latitude:.6f}, {longitude:.6f}".replace(".", ",")


# --- Campos --------------------------------------------------------------------------
# Columnas habituales: lo común del elemento en 'media_items' ("*") y lo de la cámara en la
# tabla de detalles de su tipo (fotos y vídeos de la biblioteca Imagen)
_ANY = "*"


def _photo_video(column: str) -> dict[str, tuple[str, ...]]:
    """La misma columna en 'photo_details' y en 'video_details'."""
    return {"photo": (f"photo.{column}",), "video": (f"video.{column}",)}


# fmt: off
_FIELD_LIST: tuple[InspectorField, ...] = (
    # --- Cabecera común (todas las vistas) ---
    InspectorField("dimensions", "Dimensiones", "Dimensiones", {_ANY: ("m.width", "m.height")}, format_dimensions),
    # Recorte de Lightroom («Dimensiones actuales»); en blanco si no hay recorte
    InspectorField("crop_dimensions", "Recorte", "Dimensiones del recorte (Lightroom)",
                   {"photo": ("photo.crop_width", "photo.crop_height")}, format_dimensions),
    InspectorField("captured_at", "Captura", "Fecha de captura", {_ANY: ("m.content_created_at",)}, format_datetime),

    # --- Cámara y exposición ---
    InspectorField("camera", "Cámara", "Cámara (marca y modelo)",
                   {"photo": ("photo.camera_make", "photo.camera_model"),
                    "video": ("video.camera_make", "video.camera_model")}, format_camera),
    InspectorField("lens_model", "Objetivo", "Objetivo", _photo_video("lens_model"), _plain),
    InspectorField("focal_length", "Focal", "Distancia focal", {"photo": ("photo.focal_length_mm",)}, format_focal_length),
    InspectorField("focal_length_35mm", "Focal 35 mm", "Distancia focal equivalente en 35 mm",
                   _photo_video("focal_length_35mm"), format_focal_length),
    InspectorField("exposure", "Exposición", "Exposición (tiempo y apertura)",
                   {"photo": ("photo.exposure_time_s", "photo.f_number")}, format_exposure,
                   format_exposure_exact),
    InspectorField("iso", "Sensibilidad", "Sensibilidad ISO", {"photo": ("photo.iso",)}, format_iso),
    InspectorField("exposure_bias", "Compensación", "Compensación de exposición",
                   {"photo": ("photo.exposure_bias_ev",)}, format_exposure_bias),
    InspectorField("flash", "Flash", "Flash", {"photo": ("photo.flash_fired",)}, _code_text(FLASH_STATES)),
    InspectorField("exposure_program", "Programa", "Programa de exposición",
                   {"photo": ("photo.exposure_program",)}, _code_text(EXPOSURE_PROGRAMS)),
    InspectorField("metering_mode", "Medición", "Modo de medición",
                   {"photo": ("photo.metering_mode",)}, _code_text(METERING_MODES)),

    # --- Descripción (IPTC); el título, solo el propio (no el nombre del archivo) ---
    InspectorField("title", "Título", "Título", {_ANY: ("m.file_title",)}, _plain),
    InspectorField("description", "Pie", "Pie de ilustración", {_ANY: ("m.description",)},
                   _one_line, _multiline_tooltip),
    InspectorField("creator", "Creador", "Creador", {_ANY: ("m.creator",)}, _plain),
    InspectorField("copyright", "Copyright", "Copyright", {_ANY: ("m.copyright",)}, _plain),

    # --- Ubicación (IPTC) ---
    InspectorField("sublocation", "Lugar", "Lugar", {_ANY: ("m.sublocation",)}, _plain),
    InspectorField("city", "Ciudad", "Ciudad", {_ANY: ("m.city",)}, _plain),
    InspectorField("region", "Región", "Estado / región", {_ANY: ("m.region",)}, _plain),
    InspectorField("country", "País", "País / región", {_ANY: ("m.country",)}, _plain),
    InspectorField("country_code", "Código país", "Código de país ISO", {_ANY: ("m.country_code",)}, _plain),

    # --- GPS ---
    InspectorField("gps", "GPS", "Coordenadas GPS", {_ANY: ("m.latitude", "m.longitude")}, format_gps, _gps_tooltip),
    InspectorField("altitude", "Altitud", "Altitud", {_ANY: ("m.altitude",)}, format_altitude),
    InspectorField("direction", "Dirección", "Dirección de la cámara",
                   {"photo": ("photo.gps_direction",)}, format_direction, _direction_tooltip),

    # --- Fechas EXIF ---
    InspectorField("digitized_at", "Digitalización", "Fecha de digitalización (EXIF)",
                   {"photo": ("photo.digitized_at",)}, format_datetime),
    InspectorField("exif_modified_at", "Modificación", "Fecha de modificación (EXIF)",
                   {"photo": ("photo.exif_modified_at",)}, format_datetime),

    # --- Vídeo ---
    InspectorField("duration", "Duración", "Duración", {"video": ("m.duration",)}, format_duration),
    InspectorField("frame_rate", "Fotogramas", "Fotogramas por segundo",
                   {"video": ("video.frame_rate",)}, format_frame_rate),
    InspectorField("video_codec", "Códec", "Códec de vídeo", {"video": ("video.video_codec",)}, format_codec),
)
# fmt: on

# Campos por clave
FIELDS: dict[str, InspectorField] = {f.key: f for f in _FIELD_LIST}
assert len(FIELDS) == len(_FIELD_LIST), "Hay dos campos con la misma clave"

# Cabecera de TODAS las vistas: tamaño y las tres fechas (decidido por el autor el
# 02/11/2026: las fechas EXIF van junto a la de captura, no solo en la vista EXIF)
COMMON_HEAD: tuple[str, ...] = (
    "dimensions", "crop_dimensions", SEPARATOR,
    "captured_at", "digitized_at", "exif_modified_at", SEPARATOR,
)  # fmt: skip

# Bloques que se repiten en varias vistas
_EXPOSURE_BLOCK = (
    "camera", "lens_model", "focal_length", "focal_length_35mm", "exposure", "iso",
    "exposure_bias", "flash", "exposure_program", "metering_mode",
)  # fmt: skip
_DESCRIPTION_BLOCK = ("title", "description", "creator", "copyright")
_PLACE_BLOCK = ("sublocation", "city", "region", "country", "country_code")
_GPS_BLOCK = ("gps", "altitude", "direction")

# Vistas, en el orden del desplegable. Título, pie, creador y copyright (decidido por el
# autor el 10/11/2026): en «Por defecto», tras la exposición y antes del lugar; en
# «Ubicación», entre las fechas y el lugar; en «EXIF», no
PRESETS: dict[str, MetadataPreset] = {
    preset.key: preset
    for preset in (
        MetadataPreset(
            "default", "Por defecto",
            (*_EXPOSURE_BLOCK, SEPARATOR, *_DESCRIPTION_BLOCK, SEPARATOR, *_PLACE_BLOCK,
             SEPARATOR, *_GPS_BLOCK),
        ),
        MetadataPreset(
            "location", "Ubicación",
            (*_DESCRIPTION_BLOCK, SEPARATOR, *_PLACE_BLOCK, SEPARATOR, *_GPS_BLOCK),
        ),
        MetadataPreset(
            "exif", "EXIF",
            (*_EXPOSURE_BLOCK, SEPARATOR, "duration", "frame_rate", "video_codec"),
        ),
    )
}  # fmt: skip
DEFAULT_PRESET = "default"

# Campos que se EDITAN en la sección (con una caja en lugar de un texto; paso C.5). Su
# clave es la columna de 'core/userdata/editable_fields.py', que dice además si admite
# varias líneas. La ubicación se añadirá aquí en el paso 5
EDITABLE_KEYS: tuple[str, ...] = ("title", "description", "creator", "copyright")
assert set(EDITABLE_KEYS) <= set(EDITABLE_COLUMNS) and set(EDITABLE_KEYS) <= set(FIELDS)


def editor_value(value: FieldValue) -> tuple[str, bool]:
    """Lo que muestra la caja de un campo editable: (texto, hay valores distintos).

    Sin formato: el texto tal cual está en el catálogo (con sus saltos de línea).
    """
    if value.state == MIXED:
        return "", True
    if value.state != VALUE or not value.value or value.value[0] is None:
        return "", False
    return str(value.value[0]), False


def preset_rows(preset_key: str | Iterable[str]) -> tuple[str, ...]:
    """Filas de una vista: la cabecera común + sus campos (con separadores).

    Args:
        preset_key: Clave de una vista de 'PRESETS' o, para la vista personalizada, la
            lista de claves de campo. Una vista desconocida usa la de por defecto; una
            clave de campo desconocida (p. ej. de una versión futura) se descarta.
    """
    if isinstance(preset_key, str):
        preset = PRESETS.get(preset_key, PRESETS[DEFAULT_PRESET])
        keys: Iterable[str] = preset.keys
    else:
        keys = preset_key
    rows = [*COMMON_HEAD, *(k for k in keys if k == SEPARATOR or k in FIELDS)]
    # Sin separadores repetidos ni al final (p. ej. si se descartó un campo entre dos)
    cleaned: list[str] = []
    for key in rows:
        if key == SEPARATOR and (not cleaned or cleaned[-1] == SEPARATOR):
            continue
        cleaned.append(key)
    while cleaned and cleaned[-1] == SEPARATOR:
        cleaned.pop()
    return tuple(cleaned)


def sources_for(rows: Iterable[str]) -> list[FieldSource]:
    """De dónde sale cada campo de esas filas (los separadores se saltan)."""
    return [FIELDS[key].source for key in rows if key != SEPARATOR]


def display_value(field_key: str, value: FieldValue) -> DisplayValue:
    """Texto, texto emergente y color de la fila de un campo.

    Valor común -> su texto con formato; valores distintos -> «Varios» en gris; sin valor
    -> en blanco. Si el formato falla con un dato raro, la fila sale en blanco (nunca
    rompe el panel).
    """
    if value.state == MIXED:
        return DisplayValue(MIXED_TEXT, "Los elementos seleccionados tienen valores distintos.", True)
    if value.state != VALUE or value.value is None:
        return DisplayValue()
    field_def = FIELDS[field_key]
    try:
        text = field_def.format(*value.value)
        tooltip = field_def.tooltip(*value.value) if field_def.tooltip else ""
    except (TypeError, ValueError, ArithmeticError):
        return DisplayValue()
    return DisplayValue(text, tooltip if tooltip and tooltip != text else "")


if __name__ == "__main__":
    # Autoprueba con un catálogo en memoria: todas las vistas se leen y se formatean.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.inspector.metadata_fields
    import sqlite3

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.selection_metadata import fetch_field_values

    # 1. Coherencia: las vistas solo usan campos que existen, y todas empiezan igual
    for preset in PRESETS.values():
        unknown = [k for k in preset.keys if k != SEPARATOR and k not in FIELDS]
        assert not unknown, (preset.key, unknown)
        assert preset_rows(preset.key)[: len(COMMON_HEAD)] == COMMON_HEAD
    assert preset_rows("no_existe") == preset_rows(DEFAULT_PRESET)
    # Una lista personalizada con claves desconocidas y separadores sobrantes
    assert preset_rows(["iso", "-", "-", "futuro", "-"]) == (*COMMON_HEAD, "iso")
    print("1. Vistas coherentes")

    # 2. Un catálogo con una foto (Nikon Df) y un vídeo del iPhone
    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('L', '/l')")

    def add(name: str, media_type: str, **columns: Any) -> int:
        names = "".join(f", {k}" for k in columns)
        marks = "".join(", ?" for _ in columns)
        return int(db.execute(
            f"""INSERT INTO media_items(storage_location_id, relative_path, file_name, media_type,
                    mime_type, file_size, file_mtime_ns, title{names})
                VALUES (1, ?, ?, ?, 'x', 1, 0, 't'{marks})""",
            (name, name, media_type, *columns.values()),
        ).lastrowid)  # fmt: skip

    photo = add("DSC_9140.dng", "photo", width=3200, height=2128,
                content_created_at="2026-10-19 18:44:05", sublocation="Valle de Ordesa",
                city="Torla", region="Huesca", country="España", country_code="ES",
                latitude=42.682089, longitude=0.069991, altitude=1418.1)  # fmt: skip
    db.execute(
        """INSERT INTO photo_details(media_id, camera_make, camera_model, lens_model,
               focal_length_mm, focal_length_35mm, exposure_time_s, f_number, iso,
               exposure_bias_ev, flash_fired, exposure_program, metering_mode, gps_direction)
           VALUES (?, 'NIKON CORPORATION', 'NIKON Df', 'AF-S NIKKOR 20mm f/1.8G ED',
                   20, 20, 0.0008, 8, 100, -0.333, 0, 3, 5, 2.3)""",
        (photo,),
    )
    # Sin título propio (el nombre del archivo), con pie de dos líneas y creador
    db.execute(
        "UPDATE media_items SET title = 'DSC_9140', description = ?, creator = 'Javier Rojo' "
        "WHERE id = ?",
        ("Primera línea\nSegunda línea", photo),
    )
    video = add("IMG_6755.mov", "video", width=1080, height=1920, duration=4.03,
                content_created_at="2026-10-31 18:15:43")  # fmt: skip
    db.execute(
        """INSERT INTO video_details(media_id, camera_make, camera_model, video_codec,
               frame_rate, lens_model, focal_length_35mm)
           VALUES (?, 'Apple', 'iPhone 17 Pro', 'hvc1', 30, 'iPhone 17 Pro back camera', 24)""",
        (video,),
    )

    def show(ids: list[int], preset: str) -> dict[str, str]:
        """Texto de cada fila de una vista para esos elementos."""
        rows = preset_rows(preset)
        values = fetch_field_values(db, ids, sources_for(rows))
        return {k: display_value(k, values[k]).text for k in rows if k != SEPARATOR}

    # 3. La foto, vista por defecto: como en el ejemplo del autor
    shown = show([photo], "default")
    expected = {
        "dimensions": "3200 × 2128 (6,8 MP)", "crop_dimensions": "",
        "captured_at": "19/10/2026 18:44:05", "digitized_at": "", "exif_modified_at": "",
        "camera": "NIKON Df",
        "lens_model": "AF-S NIKKOR 20mm f/1.8G ED", "focal_length": "20 mm",
        "focal_length_35mm": "20 mm", "exposure": "1/1250 s a f/8,0", "iso": "ISO 100",
        "exposure_bias": "−1/3 EV", "flash": "No disparado", "exposure_program": "Prioridad de apertura",
        "metering_mode": "Matricial",
        "title": "", "description": "Primera línea Segunda línea", "creator": "Javier Rojo",
        "copyright": "",
        "sublocation": "Valle de Ordesa", "city": "Torla",
        "region": "Huesca", "country": "España", "country_code": "ES",
        "gps": "42°40'55,5204\" N 0°4'11,9676\" E", "altitude": "1.418,1 m", "direction": "Norte",
    }  # fmt: skip
    assert shown == expected, {k: (shown[k], expected[k]) for k in expected if shown[k] != expected[k]}
    # El pie de varias líneas, entero en el texto emergente
    values = fetch_field_values(db, [photo], sources_for(["description"]))
    assert display_value("description", values["description"]).tooltip == "Primera línea\nSegunda línea"
    # En su caja editable, tal cual (con el salto de línea); «Varios» y vacío
    assert editor_value(values["description"]) == ("Primera línea\nSegunda línea", False)
    assert editor_value(FieldValue(MIXED)) == ("", True)
    assert editor_value(FieldValue()) == ("", False)
    print("3. Foto, vista por defecto: como el ejemplo")
    # Título, pie, creador y copyright: tras la exposición en «Por defecto», tras las fechas
    # en «Ubicación» y nunca en «EXIF»; siempre antes del lugar
    for preset, before in (("default", "metering_mode"), ("location", SEPARATOR)):
        rows = preset_rows(preset)
        start = rows.index("title")
        assert rows[start : start + 4] == _DESCRIPTION_BLOCK, preset
        assert rows[start - 1] == SEPARATOR and rows[start + 5] == "sublocation", preset
        assert before in rows[:start], preset
    assert not set(_DESCRIPTION_BLOCK) & set(preset_rows("exif"))
    # Las fechas EXIF van en la cabecera común: en todas las vistas, tras la de captura
    for preset in PRESETS:
        assert preset_rows(preset)[:7] == (
            "dimensions", "crop_dimensions", SEPARATOR,
            "captured_at", "digitized_at", "exif_modified_at", SEPARATOR,
        ), preset  # fmt: skip

    # 4. El vídeo, vista EXIF: cámara y objetivo de 'video_details'; duración, fps y códec
    shown = show([video], "exif")
    assert shown["camera"] == "Apple iPhone 17 Pro" and shown["focal_length_35mm"] == "24 mm"
    assert shown["duration"] == "0:04" and shown["frame_rate"] == "30 fps"
    assert shown["video_codec"] == "HEVC (H.265)" and shown["iso"] == "" and shown["exposure"] == ""
    print("4. Vídeo, vista EXIF: cámara, duración, fps y códec")

    # 5. Foto y vídeo juntos: lo que difiere, «Varios» en gris; lo que no hay, en blanco
    rows = preset_rows("exif")
    values = fetch_field_values(db, [photo, video], sources_for(rows))
    camera = display_value("camera", values["camera"])
    assert camera.text == MIXED_TEXT and camera.secondary
    assert display_value("crop_dimensions", values["crop_dimensions"]).text == ""
    # Todas las vistas tienen las mismas filas sea cual sea la selección
    assert set(fetch_field_values(db, [], sources_for(rows))) == set(values)
    print("5. Selección mixta: «Varios» y filas en blanco")

    # 6. Un dato raro no rompe el panel
    assert display_value("exposure", FieldValue(VALUE, ("abc", None))).text == ""
    assert display_value("exposure_program", FieldValue(VALUE, (42,))).text == "42"
    assert display_value("direction", FieldValue(VALUE, (292.47,))) == DisplayValue("Oeste", "292,5°")
    # Exposición redondeada como Lightroom, con el valor exacto en el texto emergente
    assert display_value("exposure", FieldValue(VALUE, (1 / 54, 2.2))) == DisplayValue(
        "1/50 s a f/2,2", "Tiempo exacto: 1/54 s"
    )
    db.close()
    print("Autoprueba finalizada correctamente.")
