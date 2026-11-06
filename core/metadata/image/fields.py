"""La lista de campos de IMAGEN que se extraen con ExifTool.

>>> ESTE ES EL SITIO DONDE SE AÑADEN CAMPOS DE IMAGEN. <<<

Cada línea dice "esta columna de la base de datos sale de estas etiquetas de ExifTool".
Las etiquetas se prueban por orden: gana la primera que exista. Ese orden es la regla
de prioridad (la que recomienda el Metadata Working Group y sigue Lightroom):

    Datos descriptivos (título, pie de foto, ubicación, autor...):  XMP > IPTC > EXIF
    Datos técnicos de la toma (cámara, exposición, ISO...):          EXIF > XMP
    Fecha de captura, tamaño y recorte: son reglas especiales (ver 'rules.py').

Cómo añadir un campo (el detalle, en 'core/metadata/LEEME.md'):
    1. Si la columna no existe, añadirla con una migración en 'catalog_schema.py'.
    2. Añadir UNA línea a 'IMAGE_FIELDS'.
    3. Subir 'IMAGE_FIELDS_VERSION'. Al abrir el catálogo, las fotos con una versión
       anterior se vuelven a leer (el "reescaneo").
Con 'python -m core.metadata.inspect_cli foto.jpg' se ven las etiquetas y grupos que
trae un archivo, y 'python -m core.metadata.image.fields' comprueba que todas las
columnas de esta lista existen en la base de datos.

Las etiquetas de esta lista están comprobadas con la salida real de ExifTool 13.59 para
un JPEG de iPhone exportado desde Lightroom (grupos IFD0, ExifIFD, GPS, IPTC, XMP-*,
Composite). Las de otros formatos (HEIC, RAW) se comprobarán con sus propias salidas.
"""

__version__ = "1.1.0"
__all__ = ["IMAGE_FIELDS", "IMAGE_FIELDS_VERSION", "IMAGE_USER_FIELDS"]

# Módulos del proyecto
from core.catalog.color_labels import normalize_color_label
from core.metadata.field_spec import (
    FieldSpec,
    common,
    datetime_text,
    detail,
    image_height,
    image_width,
    integer,
    pick_flag,
    rating_value,
    real,
    text,
)

# Versión de la lista: SÚBELA cada vez que cambies IMAGE_FIELDS o 'rules.py', para que
# las fotos ya leídas se vuelvan a leer. (Las versiones 1 a 3 fueron las del extractor
# con Pillow; esta lista empieza en la 4 para que esas fotos se relean con ExifTool.)
# 7: dimensiones del recorte de Lightroom (regla en 'rules.py').
# 8: palabras clave (se leen como datos del usuario: ver core/metadata/keyword_tags.py).
IMAGE_FIELDS_VERSION = 8

# Datos del USUARIO que viajan dentro del archivo (verificado con Lightroom Classic 15.6
# sobre HEIC: valoración 3 y 5, etiqueta roja y azul, marca de rechazo y de aceptado).
# Van aparte de 'IMAGE_FIELDS' porque no son metadatos extraídos (BLOQUE B) sino del
# usuario (BLOQUE C): el extractor los lee y el procesador decide si los aplica.
#   - Valoración: 'xmp:Rating' (0 a 5; el 0 escrito significa "sin estrellas").
#   - Marca: 'xmpDM:Pick' (1 aceptada, 0 sin marca, -1 rechazada). 'xmpDM:Good' es redundante.
#   - Color: 'photoshop:LabelColor' (nombre en inglés, no depende del idioma) y, si
#     falta, 'xmp:Label' (texto que Lightroom traduce: "Roja", "Azul"...).
IMAGE_USER_FIELDS: tuple[FieldSpec, ...] = (
    common("rating", ("XMP-xmp:Rating",), rating_value),
    common("flag", ("XMP-xmpDM:Pick",), pick_flag),
    common(
        "color_label",
        ("XMP-photoshop:LabelColor", "XMP-xmp:Label"),
        normalize_color_label,
    ),
)

IMAGE_FIELDS: tuple[FieldSpec, ...] = (
    # =========================================================================
    # Descripción y autoría (columnas de 'media_items')       XMP > IPTC > EXIF
    # =========================================================================
    common("title", ("XMP-dc:Title", "IPTC:ObjectName"), text),
    common(
        "description",
        ("XMP-dc:Description", "IPTC:Caption-Abstract", "IFD0:ImageDescription"),
        text,
    ),
    common("creator", ("XMP-dc:Creator", "IPTC:By-line", "IFD0:Artist"), text),
    common("copyright", ("XMP-dc:Rights", "IPTC:CopyrightNotice", "IFD0:Copyright"), text),
    common(
        "intellectual_genre",
        ("XMP-iptcCore:IntellectualGenre", "IPTC:ObjectAttributeReference"),
        text,
    ),
    common("scene", ("XMP-iptcCore:Scene",), text),
    # "Fecha de creación" de Lightroom (IPTC / XMP photoshop:DateCreated)
    common(
        "iptc_created_at",
        ("XMP-photoshop:DateCreated", "Composite:DateTimeCreated", "IPTC:DateCreated"),
        datetime_text,
    ),
    # =========================================================================
    # Ubicación (columnas de 'media_items')                    XMP > IPTC
    # =========================================================================
    common("sublocation", ("XMP-iptcCore:Location", "IPTC:Sub-location"), text),
    common("city", ("XMP-photoshop:City", "IPTC:City"), text),
    common("region", ("XMP-photoshop:State", "IPTC:Province-State"), text),
    common("country", ("XMP-photoshop:Country", "IPTC:Country-PrimaryLocationName"), text),
    common(
        "country_code",
        ("XMP-iptcCore:CountryCode", "IPTC:Country-PrimaryLocationCode"),
        text,
    ),
    # GPS: el compuesto de ExifTool ya lleva el signo (sur y oeste, negativos)
    common("latitude", ("Composite:GPSLatitude", "XMP-exif:GPSLatitude"), real),
    common("longitude", ("Composite:GPSLongitude", "XMP-exif:GPSLongitude"), real),
    common(
        "altitude",
        ("Composite:GPSAltitude", "GPS:GPSAltitude", "XMP-exif:GPSAltitude"),
        real,
    ),
    # =========================================================================
    # Tamaño (columnas de 'media_items'). El giro por orientación está en 'rules.py'.
    # =========================================================================
    # DNG: 'DefaultCropSize' es el área útil que Lightroom muestra como "Dimensiones de
    # archivo" (el sensor completo, 'Composite:ImageSize', es algo mayor). Solo existe en
    # los DNG, así que para el resto de formatos no cambia nada.
    common(
        "width",
        (
            "DefaultCropSize",
            "Composite:ImageSize",
            "File:ImageWidth",
            "ExifIFD:ExifImageWidth",
        ),
        image_width,
    ),
    common(
        "height",
        (
            "DefaultCropSize",
            "Composite:ImageSize",
            "File:ImageHeight",
            "ExifIFD:ExifImageHeight",
        ),
        image_height,
    ),
    # =========================================================================
    # Detalles de la foto (tabla 'photo_details')              EXIF > XMP
    # =========================================================================
    # --- Cámara y objetivo ---
    detail("camera_make", ("IFD0:Make", "XMP-tiff:Make"), text),
    detail("camera_model", ("IFD0:Model", "XMP-tiff:Model"), text),
    detail(
        "body_serial_number",
        ("ExifIFD:SerialNumber", "XMP-exifEX:BodySerialNumber", "XMP-aux:SerialNumber"),
        text,
    ),
    detail(
        "lens_model",
        ("ExifIFD:LensModel", "XMP-exifEX:LensModel", "XMP-aux:Lens", "Composite:LensID"),
        text,
    ),
    detail("software", ("IFD0:Software", "XMP-xmp:CreatorTool"), text),
    detail("user_comment", ("ExifIFD:UserComment",), text),
    # --- La toma ---
    detail("focal_length_mm", ("ExifIFD:FocalLength", "XMP-exif:FocalLength"), real),
    detail(
        "focal_length_35mm",
        ("ExifIFD:FocalLengthIn35mmFormat", "XMP-exif:FocalLengthIn35mmFilm"),
        real,
    ),
    detail("f_number", ("ExifIFD:FNumber", "XMP-exif:FNumber"), real),
    detail("exposure_time_s", ("ExifIFD:ExposureTime", "XMP-exif:ExposureTime"), real),
    detail("iso", ("ExifIFD:ISO", "XMP-exif:ISO"), integer),
    detail(
        "exposure_bias_ev",
        ("ExifIFD:ExposureCompensation", "XMP-exif:ExposureBiasValue"),
        real,
    ),
    detail("brightness_value", ("ExifIFD:BrightnessValue", "XMP-exif:BrightnessValue"), real),
    # Programa de exposición, modo de medición y flash: se guardan como el código
    # numérico estándar de EXIF. La interfaz los traduce a texto ("Matricial"...).
    detail("exposure_program", ("ExifIFD:ExposureProgram", "XMP-exif:ExposureProgram"), integer),
    detail("metering_mode", ("ExifIFD:MeteringMode", "XMP-exif:MeteringMode"), integer),
    detail("flash_code", ("ExifIFD:Flash",), integer),  # 'flash_fired' se deriva en rules.py
    detail("gps_direction", ("GPS:GPSImgDirection", "XMP-exif:GPSImgDirection"), real),
    # --- Fechas EXIF ("digitalizadas" y "Fecha y hora" de Lightroom) ---
    detail("digitized_at", ("ExifIFD:CreateDate", "XMP-xmp:CreateDate"), datetime_text),
    detail("exif_modified_at", ("IFD0:ModifyDate", "XMP-xmp:ModifyDate"), datetime_text),
)


if __name__ == "__main__":
    # Comprueba que todas las columnas de la lista existen en la base de datos.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.image.fields
    import sqlite3
    from collections import Counter

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.metadata.base import PROTECTED_COLUMNS

    connection = sqlite3.connect(":memory:")
    configure_connection(connection)
    apply_migrations(connection)

    columns = {
        table: {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for table in ("media_items", "photo_details")
    }
    target_table = {"common": "media_items", "details": "photo_details"}

    problems: list[str] = []
    for spec in IMAGE_FIELDS:
        table = target_table[spec.target]
        if spec.column not in columns[table]:
            problems.append(f"'{spec.column}' no existe en '{table}': falta la migración")
        if spec.target == "common" and spec.column in PROTECTED_COLUMNS:
            problems.append(f"'{spec.column}' es una columna protegida (del archivo o del usuario)")
    for column, count in Counter(spec.column for spec in IMAGE_FIELDS).items():
        if count > 1:
            problems.append(f"'{column}' aparece {count} veces en la lista")
    for spec in IMAGE_FIELDS:
        if not spec.sources:
            problems.append(f"'{spec.column}' no tiene ninguna fuente")

    if problems:
        print("PROBLEMAS EN IMAGE_FIELDS:")
        for problem in problems:
            print("  -", problem)
        raise SystemExit(1)
    print(f"IMAGE_FIELDS correcta: {len(IMAGE_FIELDS)} campos, todas las columnas existen.")
    print(f"Versión de la lista: {IMAGE_FIELDS_VERSION}")
