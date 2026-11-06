"""La lista de campos de VÍDEO que se extraen con ExifTool.

>>> ESTE ES EL SITIO DONDE SE AÑADEN CAMPOS DE VÍDEO. <<<

Funciona igual que 'core/metadata/image/fields.py': cada línea dice "esta columna sale
de estas etiquetas de ExifTool" y gana la primera que exista. Las etiquetas SIN grupo
('Make') se buscan en cualquier grupo: hace falta porque cada marca guarda los datos en
un sitio distinto:

    iPhone                  Keys:Make, Keys:Model, Keys:CreationDate (con zona horaria);
                            objetivo en VideoKeys:LensModel, FocalLengthIn35mmFormat y
                            CameraLensIrisfnumber (la apertura como texto: "F1.78")
    Android                 Keys:AndroidMake, Keys:AndroidModel (no siempre)
    Cámaras Sony (MP4)      XML:DeviceManufacturer, XML:DeviceModelName
    Videocámaras (MTS)      H264:Make, H264:Model
    Otros (GoPro, DJI...)   UserData:Make, UserData:Model

La fecha de captura, el tamaño (con la rotación de los vídeos de móvil) y el GPS son
reglas especiales (ver 'rules.py').

Cómo añadir un campo: como en las imágenes (ver 'core/metadata/LEEME.md'): columna (con
una migración, si no existe), una línea aquí y subir 'VIDEO_FIELDS_VERSION'. Para ver las
etiquetas reales de un vídeo:
    python -m core.metadata.inspect_cli video.mov --todo
    python -m core.metadata.inspect_cli video.mov --campos

COMPROBADO con vídeos reales de iPhone 17 Pro (horizontal y vertical, 31/10/2026). Las
etiquetas de Android, cámaras y películas salen todavía de la documentación de ExifTool.

1.1.0 Objetivo del vídeo: 'lens_model', 'focal_length_35mm' y 'f_number' (migración 13).
"""

__version__ = "1.1.0"
__all__ = ["VIDEO_FIELDS", "VIDEO_FIELDS_VERSION", "aperture"]

# Módulos del proyecto
from core.metadata.field_spec import (
    FieldSpec,
    common,
    detail,
    image_height,
    image_width,
    real,
    text,
)

# Versión de la lista: SÚBELA cada vez que cambies VIDEO_FIELDS o 'rules.py', para que
# los vídeos ya leídos se vuelvan a leer
VIDEO_FIELDS_VERSION = 2  # 2: objetivo (lens_model, focal_length_35mm, f_number)


def aperture(value: object) -> float | None:
    """Apertura como número: acepta 1.78, "1.78", "F1.78" y "f/1.78".

    Los iPhone la guardan como texto con una "F" delante ('CameraLensIrisfnumber' =
    "F1.78"), que el conversor 'real' no entiende.
    """
    if isinstance(value, str):
        # Se quita el prefijo "F" o "f/" (y espacios) y se deja el número
        value = value.strip().removeprefix("f/").removeprefix("F/")
        value = value.removeprefix("F").removeprefix("f").strip()
    number = real(value)
    # Una apertura de 0 o negativa no es un dato
    return number if number is not None and number > 0 else None


# fmt: off
VIDEO_FIELDS: tuple[FieldSpec, ...] = (
    # --- Descriptivos (media_items): XMP primero, después las etiquetas de QuickTime ---
    common("title", ("XMP-dc:Title", "ItemList:Title", "UserData:Title", "QuickTime:Title"), text),
    common("description", ("XMP-dc:Description", "ItemList:Description",
                           "UserData:Description", "QuickTime:Description"), text),
    common("creator", ("XMP-dc:Creator", "ItemList:Artist", "UserData:Artist",
                       "QuickTime:Author"), text),
    common("copyright", ("XMP-dc:Rights", "ItemList:Copyright", "UserData:Copyright"), text),

    # --- Métricas (media_items) ---
    # Duración en segundos (con '-n', ExifTool la da como número)
    common("duration", ("QuickTime:Duration", "Composite:Duration", "Duration"), real),
    # Tamaño del fotograma TAL COMO SE GUARDA; la rotación se aplica en 'rules.py'
    common("width", ("Composite:ImageSize", "ImageWidth", "SourceImageWidth"), image_width),
    common("height", ("Composite:ImageSize", "ImageHeight", "SourceImageHeight"), image_height),

    # --- Geolocalización (media_items): el compuesto de ExifTool ya trae el signo ---
    common("latitude", ("Composite:GPSLatitude", "XMP-exif:GPSLatitude", "GPSLatitude"), real),
    common("longitude", ("Composite:GPSLongitude", "XMP-exif:GPSLongitude", "GPSLongitude"), real),
    common("altitude", ("Composite:GPSAltitude", "XMP-exif:GPSAltitude", "GPSAltitude"), real),

    # --- Propios del vídeo (video_details) ---
    # Cámara: primero los grupos conocidos; después, el mismo nombre en cualquier grupo
    detail("camera_make", ("Keys:Make", "UserData:Make", "XML:DeviceManufacturer", "H264:Make",
                           "Keys:AndroidMake", "Make", "AndroidMake", "DeviceManufacturer"), text),
    detail("camera_model", ("Keys:Model", "UserData:Model", "XML:DeviceModelName", "H264:Model",
                            "Keys:AndroidModel", "Model", "AndroidModel", "DeviceModelName"), text),
    detail("software", ("Keys:Software", "UserData:Software", "Software", "Encoder"), text),
    # Códec ('avc1' = H.264, 'hvc1'/'hev1' = H.265) y fotogramas por segundo
    detail("video_codec", ("CompressorID", "VideoCodec", "CompressorName"), text),
    detail("frame_rate", ("VideoFrameRate", "FrameRate"), real),
    # Objetivo (iPhone: grupo 'VideoKeys'; sin grupo = cualquiera). Mismas columnas que
    # en 'photo_details'. No se leen las variantes con idioma ('LensModel-eng-US'): son
    # copias de las mismas etiquetas.
    detail("lens_model", ("VideoKeys:LensModel", "Keys:LensModel", "LensModel",
                          "Composite:LensID"), text),
    detail("focal_length_35mm", ("VideoKeys:FocalLengthIn35mmFormat",
                                 "Keys:FocalLengthIn35mmFormat", "FocalLengthIn35mmFormat"), real),
    detail("f_number", ("VideoKeys:CameraLensIrisfnumber", "Keys:CameraLensIrisfnumber",
                        "CameraLensIrisfnumber", "FNumber"), aperture),
)
# fmt: on


if __name__ == "__main__":
    # Autoprueba: todas las columnas de la lista existen en la base de datos.
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.video.fields
    import sqlite3

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    db = sqlite3.connect(":memory:")
    configure_connection(db)
    apply_migrations(db)
    columns = {
        "common": {row[1] for row in db.execute("PRAGMA table_info(media_items)")},
        "details": {row[1] for row in db.execute("PRAGMA table_info(video_details)")},
    }
    for spec in VIDEO_FIELDS:
        assert spec.column in columns[spec.target], f"Falta la columna '{spec.column}' ({spec.target})"
    db.close()

    # El conversor de la apertura entiende los formatos que se han visto
    assert aperture("F1.78") == 1.78 and aperture("F2.20") == 2.2
    assert aperture("f/2.8") == 2.8 and aperture(4) == 4.0 and aperture("1.8") == 1.8
    assert aperture("F") is None and aperture(0) is None and aperture(None) is None
    print(f"{len(VIDEO_FIELDS)} campos de vídeo; versión {VIDEO_FIELDS_VERSION}.")
    print("Autoprueba finalizada correctamente.")
