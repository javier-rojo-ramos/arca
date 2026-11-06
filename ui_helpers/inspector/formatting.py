"""Textos del inspector: tamaños, fechas, tipos de medio, origen de las fechas y metadatos.

Funciones puras (sin Qt), para que se puedan probar solas y reutilizar en otras secciones
o en los textos emergentes. Formato español: coma decimal, punto de miles y fechas
'dd/mm/aaaa'.

Metadatos (sección «Metadatos»), como los muestra Lightroom pero con coma decimal:
    dimensiones   '5712 × 4284 (24 MP)'        exposición     '1/1250 s a f/8,0'
    focal         '20 mm'                      sensibilidad   'ISO 100'
    compensación  '−1/3 EV', '0 EV', '+1 EV'   programa       'Prioridad de apertura'
    medición      'Matricial'                  cámara         'NIKON Df' (sin la marca repetida)
    GPS           '42°40'55,5204" N 0°4'11,9676" E'      altitud   '1.418,1 m'
    dirección     'Norte'                      duración       '0:15', '1:32:05'
    fotogramas    '29,97 fps'                  códec          'HEVC (H.265)'
    fecha         '19/10/2026 18:44:05'

1.1.1 Focal con hasta dos decimales y programa «Normal», como Lightroom.
1.1.0 Formatos de los metadatos (sección «Metadatos»).

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.inspector.formatting
"""

__version__ = "1.3.1"
__all__ = [
    "DATE_SOURCE_TEXTS",
    "EXPOSURE_PROGRAMS",
    "FLASH_STATES",
    "METERING_MODES",
    "format_altitude",
    "format_bytes_exact",
    "format_camera",
    "format_codec",
    "format_date",
    "format_date_range",
    "format_datetime",
    "format_dimensions",
    "format_direction",
    "format_duration",
    "format_exposure",
    "format_exposure_exact",
    "format_exposure_bias",
    "format_focal_length",
    "format_frame_rate",
    "format_gps",
    "format_iso",
    "format_media_types",
    "format_size",
    "media_type_count",
]

# Librerías estándar
import math
from collections.abc import Iterable

# Unidades de tamaño (base 1024, como el Explorador de Windows y el Finder antiguo)
_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB")

# De dónde salió la fecha de un elemento ('media_items.content_date_source'): texto del
# tooltip de la fila «Fecha». Si aparece un origen nuevo, se muestra tal cual
DATE_SOURCE_TEXTS: dict[str, str] = {
    "exif": "metadatos de la cámara (EXIF)",
    "xmp": "metadatos XMP",
    "iptc": "metadatos IPTC",
    "quicktime_keys": "metadatos del vídeo",
    "quicktime_utc": "metadatos del vídeo (hora UTC pasada a la hora local de este equipo)",
    "xml": "metadatos de la cámara (XML)",
    "h264": "metadatos de la videocámara (AVCHD)",
    "gpx": "primer punto del track",
    "id3": "etiquetas de audio",
    "filename": "nombre del archivo",
    "file_mtime": "fecha de modificación del archivo (no hay fecha en los metadatos)",
}

# Nombre de cada tipo de medio en singular y plural (para «434 fotos · 20 vídeos»)
_MEDIA_TYPE_NAMES: dict[str, tuple[str, str]] = {
    "photo": ("foto", "fotos"),
    "video": ("vídeo", "vídeos"),
    "audio": ("audio", "audios"),
    "ebook": ("libro", "libros"),
    "track": ("track", "tracks"),
}


# Programa de exposición: código EXIF ('ExposureProgram') -> texto (como Lightroom)
EXPOSURE_PROGRAMS: dict[int, str] = {
    0: "No definido",
    1: "Manual",
    2: "Normal",
    3: "Prioridad de apertura",
    4: "Prioridad de obturación",
    5: "Programa creativo",
    6: "Programa de acción",
    7: "Modo retrato",
    8: "Modo paisaje",
}

# Modo de medición: código EXIF ('MeteringMode') -> texto
METERING_MODES: dict[int, str] = {
    0: "Desconocido",
    1: "Promedio",
    2: "Ponderada al centro",
    3: "Puntual",
    4: "Multipuntual",
    5: "Matricial",
    6: "Parcial",
    255: "Otro",
}

# Flash: 'photo_details.flash_fired' (bit 0 del código EXIF 'Flash') -> texto
FLASH_STATES: dict[int, str] = {0: "No disparado", 1: "Disparado"}

# Códecs de vídeo: identificador del contenedor -> nombre conocido
_CODECS: dict[str, str] = {
    "avc1": "H.264",
    "avc3": "H.264",
    "hvc1": "HEVC (H.265)",
    "hev1": "HEVC (H.265)",
    "av01": "AV1",
    "vp09": "VP9",
    "apcn": "ProRes 422",
    "apch": "ProRes 422 HQ",
    "ap4h": "ProRes 4444",
}

# Los ocho rumbos de la dirección de la foto (sectores de 45°, como Lightroom)
_DIRECTIONS = ("Norte", "Noreste", "Este", "Sureste", "Sur", "Suroeste", "Oeste", "Noroeste")

# Fracciones de paso de exposición que se reconocen (tercios y medios), como texto
_FRACTIONS = ((1 / 3, "1/3"), (1 / 2, "1/2"), (2 / 3, "2/3"))


def _decimal(value: float, decimals: int) -> str:
    """Número con coma decimal y punto de miles ('1.234,5')."""
    text = f"{value:,.{decimals}f}"  # formato inglés: '1,234.5'
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def format_size(size: int) -> str:
    """Tamaño legible: '512 B', '24,3 KB', '412 MB', '1,2 GB'.

    Un decimal por debajo de 100 en la unidad elegida y ninguno a partir de ahí
    (mismo criterio que los exploradores de archivos).
    """
    value = float(max(0, size))
    unit = 0
    while value >= 1024 and unit < len(_SIZE_UNITS) - 1:
        value /= 1024
        unit += 1
    if unit == 0:
        return f"{int(value)} B"
    return f"{_decimal(value, 1 if value < 100 else 0)} {_SIZE_UNITS[unit]}"


def format_bytes_exact(size: int) -> str:
    """Tamaño exacto con punto de miles: '25.481.234 bytes'."""
    return f"{_decimal(max(0, size), 0)} bytes"


def format_date(text: str | None, precision: str | None = "second") -> str:
    """Fecha de la base de datos ('YYYY-MM-DD HH:MM:SS') según su precisión.

    'year' -> '2024'; 'month' -> '06/2024'; 'day' -> '01/06/2024';
    'second' (o desconocida) -> '01/06/2024 12:00'. Sin fecha -> ''.
    """
    if not text or len(text) < 10:
        return ""
    year, month, day = text[0:4], text[5:7], text[8:10]
    match precision:
        case "year":
            return year
        case "month":
            return f"{month}/{year}"
        case "day":
            return f"{day}/{month}/{year}"
    time = text[11:16] if len(text) >= 16 else ""
    return f"{day}/{month}/{year} {time}".strip()


def format_date_range(date_min: str | None, date_max: str | None) -> str:
    """Rango de fechas de varios elementos.

    Mismo instante -> '01/06/2024 12:00'; mismo día -> '01/06/2024 10:00 – 12:30';
    días distintos -> '12/05/2023 – 01/06/2024'. Sin fechas -> ''.
    """
    if not date_min or not date_max:
        return format_date(date_min or date_max)
    if date_min[:16] == date_max[:16]:
        return format_date(date_min)
    if date_min[:10] == date_max[:10]:
        return f"{format_date(date_min)} – {date_max[11:16]}"
    return f"{format_date(date_min, 'day')} – {format_date(date_max, 'day')}"


def media_type_count(media_type: str, count: int) -> str:
    """'1 foto', '20 vídeos', '3 otros'."""
    singular, plural = _MEDIA_TYPE_NAMES.get(media_type, ("otro", "otros"))
    return f"{_decimal(count, 0)} {singular if count == 1 else plural}"


def format_media_types(media_types: Iterable[tuple[str, int]]) -> str:
    """'434 fotos · 20 vídeos · 6 tracks' (en el orden recibido)."""
    return " · ".join(media_type_count(media_type, count) for media_type, count in media_types)


def _trimmed(value: float, decimals: int) -> str:
    """Número con coma decimal y sin ceros sobrantes: 8.0 -> '8', 2.2 -> '2,2'."""
    text = _decimal(value, decimals)
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def format_datetime(text: str | None) -> str:
    """Fecha y hora con segundos: '2026-10-19 18:44:05' -> '19/10/2026 18:44:05'."""
    if not text or len(text) < 10:
        return ""
    date = f"{text[8:10]}/{text[5:7]}/{text[0:4]}"
    return f"{date} {text[11:19]}".strip() if len(text) >= 19 else date


def format_dimensions(width: int | None, height: int | None) -> str:
    """'5712 × 4284 (24 MP)'; con menos de 10 MP, un decimal ('2,1 MP')."""
    if not width or not height:
        return ""
    megapixels = width * height / 1_000_000
    mp = _trimmed(megapixels, 1) if megapixels < 10 else _decimal(round(megapixels), 0)
    return f"{width} × {height} ({mp} MP)"


# Velocidades de obturación "nominales" de las cámaras (pasos de 1/3 de punto), como
# denominadores de 1/N s. Lightroom muestra el tiempo REDONDEADO a la más cercana:
# un iPhone guarda 1/54 s y Lightroom enseña «1/50 seg.» (comprobado con IMG_6257.heic).
_NOMINAL_SPEEDS: tuple[int, ...] = (
    8000, 6400, 5000, 4000, 3200, 2500, 2000, 1600, 1250, 1000, 800, 640, 500, 400,
    320, 250, 200, 160, 125, 100, 80, 60, 50, 40, 30, 25, 20, 15, 13, 10, 8, 6, 5, 4, 3,
)

# Distancia máxima (en puntos de luz) para redondear a una velocidad nominal: medio
# tercio. Más lejos, el valor no corresponde a ningún paso y se escribe tal cual.
_NOMINAL_TOLERANCE_EV = 1 / 6


def _shutter_text(seconds: float, nominal: bool) -> str:
    """Tiempo de exposición en texto ('1/50 s', '0,4 s', '2 s').

    Args:
        seconds: Tiempo en segundos (> 0).
        nominal: True para redondear a la velocidad nominal más cercana (como Lightroom);
            False para el valor exacto del archivo.
    """
    if seconds >= 1:
        return f"{_trimmed(seconds, 1)} s"
    denominator = 1 / seconds
    if nominal:
        # Más rápido que la velocidad más alta de la tabla: esa (Lightroom muestra 1/8000
        # para el 1/17544 de un iPhone con el sol en el encuadre)
        if denominator > _NOMINAL_SPEEDS[0]:
            return f"1/{_NOMINAL_SPEEDS[0]} s"
        # La velocidad nominal más cercana en escala logarítmica (en puntos de luz)
        closest = min(_NOMINAL_SPEEDS, key=lambda speed: abs(math.log2(speed / denominator)))
        if abs(math.log2(closest / denominator)) <= _NOMINAL_TOLERANCE_EV:
            return f"1/{closest} s"
    if abs(denominator - round(denominator)) <= 0.05 * denominator:
        return f"1/{round(denominator)} s"
    return f"{_trimmed(seconds, 2)} s"


def format_exposure(seconds: float | None, f_number: float | None) -> str:
    """'1/1250 s a f/8,0'; con solo uno de los dos datos, ese ('1/1250 s', 'f/8,0').

    El tiempo se redondea a la velocidad nominal más cercana, como hace Lightroom (1/54 s
    -> '1/50 s'); el valor exacto está en 'format_exposure_exact'. Si no corresponde a
    ningún paso, o a partir de 1 s, se escribe con decimales ('0,4 s', '2 s', '1,3 s').
    """
    parts: list[str] = []
    if seconds and seconds > 0:
        parts.append(_shutter_text(seconds, nominal=True))
    if f_number and f_number > 0:
        parts.append(f"f/{_decimal(f_number, 1)}")
    return " a ".join(parts)


def format_exposure_exact(seconds: float | None, f_number: float | None = None) -> str:
    """Texto emergente de la exposición: el tiempo EXACTO del archivo, si se redondeó.

    'Tiempo exacto: 1/54 s' para 1/54 s (que se muestra como '1/50 s'); '' si el valor
    mostrado ya es el exacto. 'f_number' se acepta para usarla con las mismas columnas.
    """
    if not seconds or seconds <= 0:
        return ""
    exact = _shutter_text(seconds, nominal=False)
    return "" if exact == _shutter_text(seconds, nominal=True) else f"Tiempo exacto: {exact}"


def format_focal_length(millimeters: float | None) -> str:
    """'20 mm'; si no es entera, con hasta dos decimales, como Lightroom ('2,22 mm', '16,9 mm')."""
    if not millimeters or millimeters <= 0:
        return ""
    return f"{_trimmed(millimeters, 2)} mm"


def format_iso(iso: int | None) -> str:
    """'ISO 100' (punto de miles: 'ISO 12.800')."""
    return f"ISO {_decimal(iso, 0)}" if iso else ""


def format_exposure_bias(ev: float | None) -> str:
    """Compensación de exposición: '0 EV', '+1 EV', '−1/3 EV', '+1 2/3 EV' ('' si no hay).

    Se reconocen los pasos de tercio y de medio; un valor raro se escribe con decimales.
    """
    if ev is None:
        return ""
    if abs(ev) < 0.01:
        return "0 EV"
    sign = "+" if ev > 0 else "−"  # el signo menos tipográfico, como Lightroom
    whole = math.floor(abs(ev) + 0.01)
    rest = abs(ev) - whole
    if rest < 0.02:
        return f"{sign}{whole} EV"
    for value, text in _FRACTIONS:
        if abs(rest - value) < 0.02:
            return f"{sign}{whole} {text} EV" if whole else f"{sign}{text} EV"
    return f"{sign}{_trimmed(abs(ev), 2)} EV"


def format_camera(make: str | None, model: str | None) -> str:
    """Cámara sin la marca repetida: ('NIKON CORPORATION', 'NIKON Df') -> 'NIKON Df'.

    Si el modelo no empieza por la marca (o su primera palabra), se escriben las dos:
    ('Apple', 'iPhone 17 Pro') -> 'Apple iPhone 17 Pro'.
    """
    make, model = (make or "").strip(), (model or "").strip()
    if not model:
        return make
    if not make:
        return model
    first_word = make.split()[0].casefold()
    if model.casefold().startswith(first_word):
        return model
    return f"{make} {model}"


def _dms(value: float, positive: str, negative: str) -> str:
    """Una coordenada en grados, minutos y segundos (4 decimales, como Lightroom): '42°40'55,5204" N'."""
    hemisphere = positive if value >= 0 else negative
    value = abs(value)
    degrees = int(value)
    minutes_total = (value - degrees) * 60
    minutes = int(minutes_total)
    seconds = (minutes_total - minutes) * 60
    if round(seconds, 4) >= 60:  # 59,99999" redondea a 60": se pasa al minuto siguiente
        seconds, minutes = 0.0, minutes + 1
        if minutes == 60:
            minutes, degrees = 0, degrees + 1
    return f"{degrees}°{minutes}'{_decimal(seconds, 4)}\" {hemisphere}"


def format_gps(latitude: float | None, longitude: float | None) -> str:
    """'42°40'55,5204" N 0°4'11,9676" E' (sin coordenadas, '')."""
    if latitude is None or longitude is None:
        return ""
    return f"{_dms(latitude, 'N', 'S')} {_dms(longitude, 'E', 'O')}"


def format_altitude(meters: float | None) -> str:
    """'1.418,1 m' (bajo el nivel del mar, negativa: '−12,5 m')."""
    if meters is None:
        return ""
    sign = "−" if meters < 0 else ""
    return f"{sign}{_decimal(abs(meters), 1)} m"


def format_direction(degrees: float | None) -> str:
    """Rumbo de la foto en ocho sectores de 45°, como Lightroom: 2,3 -> 'Norte'."""
    if degrees is None:
        return ""
    sector = int(((degrees % 360) + 22.5) // 45) % 8
    return _DIRECTIONS[sector]


def format_duration(seconds: float | None) -> str:
    """'0:15', '12:05', '1:32:05' (como la insignia de la tarjeta)."""
    if seconds is None or seconds < 0:
        return ""
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_frame_rate(fps: float | None) -> str:
    """'29,97 fps', '30 fps'."""
    return f"{_trimmed(fps, 2)} fps" if fps else ""


def format_codec(codec: str | None) -> str:
    """Nombre conocido del códec ('hvc1' -> 'HEVC (H.265)'); si no se conoce, tal cual."""
    if not codec:
        return ""
    return _CODECS.get(codec.strip().lower(), codec.strip())


if __name__ == "__main__":
    # Autoprueba. Ejecutar desde la raíz del proyecto:
    #   python -m ui_helpers.inspector.formatting
    assert [format_size(n) for n in (0, 512, 1024, 25_481_234, 431_000_000, 1_300_000_000)] == [
        "0 B", "512 B", "1,0 KB", "24,3 MB", "411 MB", "1,2 GB"
    ], [format_size(n) for n in (0, 512, 1024, 25_481_234, 431_000_000, 1_300_000_000)]
    assert format_bytes_exact(25_481_234) == "25.481.234 bytes"
    assert format_date("2024-06-01 12:00:00") == "01/06/2024 12:00"
    assert format_date("2024-06-01 00:00:00", "day") == "01/06/2024"
    assert format_date("2024-06-01 00:00:00", "month") == "06/2024"
    assert format_date("2024-01-01 00:00:00", "year") == "2024"
    assert format_date(None) == "" and format_date("") == ""
    assert format_date_range("2024-06-01 12:00:00", "2024-06-01 12:00:30") == "01/06/2024 12:00"
    assert format_date_range("2024-06-01 10:00:00", "2024-06-01 12:30:00") == "01/06/2024 10:00 – 12:30"
    assert format_date_range("2023-05-12 08:00:00", "2024-06-02 09:30:00") == "12/05/2023 – 02/06/2024"
    assert format_date_range(None, None) == ""
    assert format_media_types([("photo", 434), ("video", 1), ("other", 2)]) == "434 fotos · 1 vídeo · 2 otros"
    assert media_type_count("photo", 1500) == "1.500 fotos"

    # Metadatos
    assert format_datetime("2026-10-19 18:44:05") == "19/10/2026 18:44:05"
    assert format_dimensions(5712, 4284) == "5712 × 4284 (24 MP)"
    assert format_dimensions(3000, 2000) == "3000 × 2000 (6 MP)"
    assert format_dimensions(1920, 1080) == "1920 × 1080 (2,1 MP)" and format_dimensions(None, 5) == ""
    assert format_exposure(1 / 1250, 8.0) == "1/1250 s a f/8,0"
    assert format_exposure(0.0008, 1.78) == "1/1250 s a f/1,8"
    assert format_exposure(1 / 3, None) == "1/3 s" and format_exposure(0.4, None) == "0,4 s"
    assert format_exposure(2.0, 11.0) == "2 s a f/11,0" and format_exposure(1.3, None) == "1,3 s"
    assert format_exposure(None, None) == "" and format_exposure(None, 2.8) == "f/2,8"
    # Redondeo a la velocidad nominal, como Lightroom (iPhone: 1/54 s -> «1/50 seg.»)
    assert format_exposure(0.01851851852, 2.2) == "1/50 s a f/2,2"
    assert format_exposure_exact(0.01851851852) == "Tiempo exacto: 1/54 s"
    assert format_exposure(1 / 121, None) == "1/125 s" and format_exposure(1 / 400, None) == "1/400 s"
    assert format_exposure_exact(1 / 400) == "" and format_exposure_exact(None) == ""
    assert format_exposure(1 / 7000, None) == "1/6400 s"  # a 1/8 de punto: se redondea
    assert format_exposure(1 / 8500, None) == "1/8000 s"
    # Más rápido que 1/8000: 1/8000, como Lightroom (iPhone con el sol: 1/17544)
    assert format_exposure(1 / 17544, 1.78) == "1/8000 s a f/1,8"
    assert format_exposure_exact(1 / 17544) == "Tiempo exacto: 1/17544 s"
    assert format_focal_length(20.0) == "20 mm" and format_focal_length(4.2) == "4,2 mm"
    assert format_focal_length(2.22) == "2,22 mm" and format_focal_length(16.9) == "16,9 mm"
    assert EXPOSURE_PROGRAMS[2] == "Normal"
    assert format_iso(100) == "ISO 100" and format_iso(12800) == "ISO 12.800" and format_iso(None) == ""
    assert [format_exposure_bias(v) for v in (0, 1, -1 / 3, 2 / 3, -1.6667, 0.5, 0.15, None)] == [
        "0 EV", "+1 EV", "−1/3 EV", "+2/3 EV", "−1 2/3 EV", "+1/2 EV", "+0,15 EV", ""
    ], [format_exposure_bias(v) for v in (0, 1, -1 / 3, 2 / 3, -1.6667, 0.5, 0.15, None)]
    assert EXPOSURE_PROGRAMS[3] == "Prioridad de apertura" and METERING_MODES[5] == "Matricial"
    assert format_camera("NIKON CORPORATION", "NIKON Df") == "NIKON Df"
    assert format_camera("Apple", "iPhone 17 Pro") == "Apple iPhone 17 Pro"
    assert format_camera("Canon", "Canon EOS R5") == "Canon EOS R5" and format_camera(None, None) == ""
    assert format_gps(42.682089, 0.069991) == "42°40'55,5204\" N 0°4'11,9676\" E", format_gps(42.682089, 0.069991)
    assert format_gps(-33.5, -70.25) == "33°30'0,0000\" S 70°15'0,0000\" O"
    assert format_gps(None, 1.0) == ""
    assert format_altitude(1418.1) == "1.418,1 m" and format_altitude(-12.5) == "−12,5 m"
    assert [format_direction(d) for d in (2.3, 44, 46, 180, 292.47, 359)] == [
        "Norte", "Noreste", "Noreste", "Sur", "Oeste", "Norte"
    ]
    assert format_duration(15.38) == "0:15" and format_duration(5182) == "1:26:22"
    assert format_frame_rate(29.9772) == "29,98 fps" and format_frame_rate(30.0) == "30 fps"
    assert format_codec("hvc1") == "HEVC (H.265)" and format_codec("xyz") == "xyz"
    print("Autoprueba finalizada correctamente.")
