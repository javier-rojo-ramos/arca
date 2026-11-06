"""Reglas especiales de los vídeos: lo que no es un simple "etiqueta -> columna".

Se ejecutan DESPUÉS de rellenar la lista de campos ('fields.py') y ajustan los valores en
el sitio. Son tres:

    1. Tamaño y rotación: los móviles graban el fotograma apaisado y anotan una ROTACIÓN
       (90 o 270 en los vídeos en vertical). Se guarda el tamaño "de pantalla" (ancho y
       alto intercambiados si hace falta), igual que con las fotos giradas. La columna
       'orientation' (código EXIF) se deja en 1: en los vídeos no se usa.
    2. Fecha de captura ('content_created_at', hora LOCAL, como en las fotos):
         a) Etiquetas que guardan la hora local (y a veces su zona): la de los iPhone
            ('Keys:CreationDate', con zona), las cámaras Sony ('XML:CreationDateValue'),
            las videocámaras AVCHD ('H264:DateTimeOriginal') y las XMP.
         b) 'QuickTime:CreateDate' y similares: según la especificación de QuickTime van
            en UTC (así las escriben los Android), de modo que se pasan a la hora local
            del EQUIPO, como las de los GPX. Origen: 'quicktime_utc'.
         c) Si no hay ninguna: la fecha de modificación del archivo ('file_mtime').
    3. GPS: se descartan las coordenadas imposibles y el '0, 0'.

Limitación conocida (b): algunas cámaras escriben la hora LOCAL en 'QuickTime:CreateDate'
(contra la especificación). En ese caso la hora sale desplazada lo que valga la zona
horaria. Se verá con vídeos reales ('inspect_cli') y se corregirá por marca si hace falta.

Si cambias algo aquí, sube 'VIDEO_FIELDS_VERSION' (en 'fields.py').
"""

__version__ = "1.0.0"
__all__ = ["apply_video_rules"]

# Librerías estándar
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Módulos del proyecto
from core.metadata.field_spec import integer, lookup, parse_datetime, parse_offset

# (a) Fechas en hora LOCAL (con o sin zona), por orden de fiabilidad: (etiqueta, origen)
_LOCAL_DATE_SOURCES: tuple[tuple[str, str], ...] = (
    ("Keys:CreationDate", "quicktime_keys"),  # iPhone: "2024:06:01 12:00:00+02:00"
    ("XML:CreationDateValue", "xml"),  # cámaras Sony
    ("H264:DateTimeOriginal", "h264"),  # videocámaras AVCHD (.MTS)
    ("XMP-exif:DateTimeOriginal", "xmp"),
    ("XMP-xmp:CreateDate", "xmp"),
)

# (b) Fechas de QuickTime en UTC (según la especificación)
_UTC_DATE_SOURCES: tuple[str, ...] = (
    "QuickTime:CreateDate",
    "QuickTime:MediaCreateDate",
    "Track1:MediaCreateDate",
    "QuickTime:TrackCreateDate",
)

# Una fecha de QuickTime anterior a esta es un valor vacío (el "cero" de QuickTime es
# 1904-01-01, y muchos programas escriben 1970-01-01)
_MIN_VALID_YEAR = 1971

# Formato de fecha de la base de datos
_DB_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def apply_video_rules(
    tags: Mapping[str, Any], common_values: dict[str, Any], details: dict[str, Any], path: Path
) -> None:
    """Aplica las reglas especiales de vídeo. Ver la cabecera del módulo."""
    _size_and_rotation(tags, common_values)
    _capture_date(tags, common_values, path)
    _gps(common_values)


def _size_and_rotation(tags: Mapping[str, Any], common_values: dict[str, Any]) -> None:
    """Tamaño de pantalla: con rotación de 90 o 270 grados, se intercambian ancho y alto."""
    common_values["orientation"] = 1
    rotation = integer(lookup(tags, "Composite:Rotation") or lookup(tags, "Rotation"))
    width, height = common_values.get("width"), common_values.get("height")
    if rotation is not None and rotation % 180 == 90 and width and height:
        common_values["width"], common_values["height"] = height, width


def _capture_date(tags: Mapping[str, Any], common_values: dict[str, Any], path: Path) -> None:
    """Fecha de captura con su zona horaria, origen y precisión (ver la cabecera)."""
    # (a) Hora local tal como la escribió el dispositivo
    for tag, origin in _LOCAL_DATE_SOURCES:
        parsed = parse_datetime(lookup(tags, tag))
        if parsed is None or int(parsed.text[:4]) < _MIN_VALID_YEAR:
            continue
        common_values.update(
            content_created_at=parsed.text,
            content_date_precision=parsed.precision,
            content_date_source=origin,
            timezone_offset=parsed.offset,
        )
        return

    # (b) QuickTime: UTC -> hora local del equipo
    for tag in _UTC_DATE_SOURCES:
        parsed = parse_datetime(lookup(tags, tag))
        if parsed is None or int(parsed.text[:4]) < _MIN_VALID_YEAR:
            continue
        if parsed.offset is not None:
            # Trae su zona (raro en QuickTime): ya es la hora local de la grabación
            local_text, offset = parsed.text, parsed.offset
        else:
            moment = datetime.strptime(parsed.text, _DB_DATE_FORMAT).replace(tzinfo=UTC)
            local_text, offset = _utc_to_local(moment)
        common_values.update(
            content_created_at=local_text,
            content_date_precision=parsed.precision,
            content_date_source="quicktime_utc",
            timezone_offset=offset,
        )
        return

    # (c) Sin fecha en el archivo: la de modificación (hora local), como en las fotos
    try:
        # Hora local del equipo, a propósito (como las fechas EXIF): sin zona
        modified = datetime.fromtimestamp(path.stat().st_mtime)  # noqa: DTZ006
        common_values.update(
            content_created_at=modified.replace(microsecond=0).isoformat(sep=" "),
            content_date_precision="second",
            content_date_source="file_mtime",
            timezone_offset=None,
        )
    except (OSError, OverflowError, ValueError):
        common_values.update(
            content_created_at=None,
            content_date_precision=None,
            content_date_source=None,
            timezone_offset=None,
        )


def _utc_to_local(moment: datetime) -> tuple[str, str | None]:
    """Hora local del EQUIPO (texto de la base de datos) y su desfase ('+02:00').

    'astimezone()' sin argumentos usa la zona del sistema y aplica el horario de verano
    que corresponda a ESA fecha (no el de hoy). Igual que con los GPX.
    """
    local = moment.astimezone()
    delta = local.utcoffset()
    if delta is None:
        return local.strftime(_DB_DATE_FORMAT), None
    minutes = int(delta.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return local.strftime(_DB_DATE_FORMAT), parse_offset(f"{sign}{minutes // 60:02d}:{minutes % 60:02d}")


def _gps(common_values: dict[str, Any]) -> None:
    """Descarta coordenadas fuera de rango o '0, 0' (sin cobertura GPS al grabar)."""
    latitude, longitude = common_values.get("latitude"), common_values.get("longitude")
    invalid = (
        latitude is None
        or longitude is None
        or abs(latitude) > 90
        or abs(longitude) > 180
        or (latitude == 0 and longitude == 0)
    )
    if invalid:
        common_values["latitude"] = None
        common_values["longitude"] = None
        common_values["altitude"] = None


if __name__ == "__main__":
    # Autoprueba con etiquetas inventadas (con los nombres que da ExifTool -G1 -n).
    # Ejecutar desde la raíz del proyecto:  python -m core.metadata.video.rules
    import os
    import tempfile
    import time

    from core.metadata.field_spec import read_field
    from core.metadata.video.fields import VIDEO_FIELDS

    os.environ["TZ"] = "Europe/Madrid"
    if hasattr(time, "tzset"):
        time.tzset()  # (en Windows no existe: allí se usa la zona del equipo)

    def run(tags: dict, path: Path) -> tuple[dict, dict]:
        """Rellena la lista de campos y aplica las reglas, como el extractor."""
        common_values: dict = {}
        details: dict = {}
        for spec in VIDEO_FIELDS:
            target = common_values if spec.target == "common" else details
            target[spec.column] = read_field(spec, tags)
        apply_video_rules(tags, common_values, details, path)
        return common_values, details

    with tempfile.TemporaryDirectory() as tmp:
        clip = Path(tmp) / "IMG_0001.MOV"
        clip.write_bytes(b"x")

        # 1. iPhone en vertical: fecha local con zona, rotación 90 y GPS
        iphone = {
            "QuickTime:CreateDate": "2024:06:01 10:00:00",  # UTC
            "Keys:CreationDate": "2024:06:01 12:00:00+02:00",
            "Keys:Make": "Apple", "Keys:Model": "iPhone 15 Pro", "Keys:Software": "17.5",
            "QuickTime:Duration": 12.5, "Composite:ImageSize": "1920 1080",
            "Composite:Rotation": 90, "Composite:GPSLatitude": 43.3,
            "Composite:GPSLongitude": -3.2, "Composite:GPSAltitude": 12.0,
            "Track1:CompressorID": "hvc1", "Track1:VideoFrameRate": 29.97,
            # Objetivo, como lo guarda un iPhone 17 Pro real (la apertura, como texto)
            "VideoKeys:LensModel": "iPhone 17 Pro back triple camera 6.765mm f/1.78",
            "VideoKeys:LensModel-eng-US": "iPhone 17 Pro back triple camera 6.765mm f/1.78",
            "VideoKeys:FocalLengthIn35mmFormat": 24, "VideoKeys:CameraLensIrisfnumber": "F1.78",
        }  # fmt: skip
        values, details = run(iphone, clip)
        assert values["content_created_at"] == "2024-06-01 12:00:00", values
        assert values["timezone_offset"] == "+02:00" and values["content_date_source"] == "quicktime_keys"
        assert (values["width"], values["height"]) == (1080, 1920)  # vertical
        assert values["duration"] == 12.5 and values["latitude"] == 43.3
        assert details == {"camera_make": "Apple", "camera_model": "iPhone 15 Pro",
                           "software": "17.5", "video_codec": "hvc1", "frame_rate": 29.97,
                           "lens_model": "iPhone 17 Pro back triple camera 6.765mm f/1.78",
                           "focal_length_35mm": 24.0, "f_number": 1.78}

        # 2. Android: solo QuickTime:CreateDate (UTC) -> hora local de Madrid en verano
        android = {"QuickTime:CreateDate": "2024:06:01 10:00:00", "Keys:AndroidMake": "Google",
                   "Keys:AndroidModel": "Pixel 8", "Composite:ImageSize": "1920 1080"}
        values, details = run(android, clip)
        if hasattr(time, "tzset"):
            assert values["content_created_at"] == "2024-06-01 12:00:00", values
            assert values["timezone_offset"] == "+02:00"
        assert values["content_date_source"] == "quicktime_utc"
        assert (details["camera_make"], details["camera_model"]) == ("Google", "Pixel 8")
        assert (values["width"], values["height"]) == (1920, 1080)  # sin rotación

        # 3. Película: fecha QuickTime "cero", sin cámara ni GPS -> fecha del archivo
        movie = {"QuickTime:CreateDate": "1904:01:01 00:00:00", "QuickTime:Duration": 7200.0,
                 "Composite:GPSLatitude": 0.0, "Composite:GPSLongitude": 0.0}
        values, details = run(movie, clip)
        assert values["content_date_source"] == "file_mtime"
        assert values["latitude"] is None and values["longitude"] is None
        assert details["camera_make"] is None and values["duration"] == 7200.0

        # 4. Videocámara AVCHD: marca y fecha del flujo H.264
        avchd = {"H264:Make": "Sony", "H264:Model": "HDR-CX405",
                 "H264:DateTimeOriginal": "2019:08:15 18:30:00+02:00", "Composite:Rotation": 0}
        values, details = run(avchd, clip)
        assert values["content_created_at"] == "2019-08-15 18:30:00"
        assert details["camera_make"] == "Sony" and values["content_date_source"] == "h264"
    print("Autoprueba finalizada correctamente.")
