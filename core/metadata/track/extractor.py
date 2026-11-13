"""Extractor de metadatos de TRACKS GPS (GPX).

Une el lector de GPX ('gpx_reader.py') con el catálogo: decide en qué columna va cada
dato. Se registra en 'core/metadata/registry.py'. No usa ExifTool: el GPX es XML y se
lee directamente (más rápido y sin depender de un programa externo).

Qué guarda:

    media_items (columnas comunes a todos los tipos)
        title                 nombre del track (si no tiene, se conserva el del archivo)
        description           descripción del track
        creator               autor que figura en el GPX
        content_created_at    hora del primer punto, en hora LOCAL (ver más abajo)
        content_date_precision 'second'
        content_date_source   'gpx'
        timezone_offset       desfase de esa hora local ('+02:00')
        latitude, longitude   punto de SALIDA (para el futuro mapa)
        altitude              altitud del punto de salida
        duration              segundos entre el primer y el último punto

    track_details (tabla propia de los tracks)
        distancia, desnivel acumulado, altitudes mínima y máxima, horas UTC de inicio y
        fin, recuentos (puntos, segmentos, tracks, rutas, puntos de interés), caja
        geográfica, punto de llegada, tipo de actividad y programa que lo creó.
        overview: el CONTORNO, el recorrido simplificado (como mucho 1 000 puntos),
        para pintar muchos tracks a la vez en el mapa sin abrir sus GPX
        (core/tracks/simplify.py; docs/MAPA.md, §5.3). Los puntos completos no se
        guardan: el GPX es la fuente.

Hora local: el GPX guarda las horas en UTC, pero 'content_created_at' es la hora LOCAL
(la que muestra el reloj de la cámara en las fotos), para que un track se ordene junto a
las fotos de ese día. Se convierte con la zona horaria del EQUIPO (que tiene en cuenta el
horario de verano de esa fecha). Para una ruta hecha en otro huso horario la hora saldría
con el de casa; si hiciera falta, se podría deducir la zona a partir de las coordenadas
(librería 'timezonefinder'), subiendo 'TRACK_EXTRACTOR_VERSION'.

1.2.0 El contorno del track ('track_details.overview'; TRACK_EXTRACTOR_VERSION 3).

Prueba rápida (desde la raíz del proyecto):
    python -m core.metadata.track.extractor
"""

__version__ = "1.2.0"
__all__ = ["SUPPORTED_EXTENSIONS", "TRACK_EXTRACTOR_VERSION", "TrackExtractor"]

# Librerías estándar
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.metadata.base import (
    ExtractionResult,
    MetadataError,
    MetadataExtractor,
    UnsupportedFormatError,
)
from core.metadata.track.gpx_reader import GpxError, GpxSummary, read_gpx
from core.tracks.simplify import encode_overview, simplify_track

# Versión del extractor de tracks. Se guarda en 'media_items.scan_version'. Súbela cada vez
# que el extractor lea campos nuevos o cambie un cálculo: los tracks se volverán a leer.
TRACK_EXTRACTOR_VERSION = 3
# Historial:
#   1  primera versión
#   2  umbral del desnivel de 5 a 8 m (gpx_reader.ELEVATION_THRESHOLD_M)
#   3  contorno del recorrido ('track_details.overview', migración 4)

# Formato de fecha de la base de datos ('YYYY-MM-DD HH:MM:SS')
_DB_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Extensiones que sabe leer (en minúsculas y sin punto)
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({"gpx"})


class TrackExtractor(MetadataExtractor):
    """Lee los tracks GPX: nombre, fechas, punto de salida, distancia, desnivel..."""

    media_type: ClassVar[MediaType] = MediaType.TRACK
    version: ClassVar[int] = TRACK_EXTRACTOR_VERSION
    details_table: ClassVar[str | None] = "track_details"

    def extract(self, path: Path) -> ExtractionResult:
        """Lee un track. Ver 'MetadataExtractor.extract'.

        Raises:
            FileNotFoundError: Si el archivo ya no existe.
            UnsupportedFormatError: Si no es un formato de track que se sepa leer.
            MetadataError: Si el GPX está dañado.
        """
        extension = path.suffix.lower().lstrip(".")
        if extension not in SUPPORTED_EXTENSIONS:
            # P. ej. un .tcx o .fit en el futuro: no es un fallo del archivo
            raise UnsupportedFormatError(f"Formato de track sin soporte todavía: .{extension}")

        try:
            summary = read_gpx(path, collect_points=True)
        except GpxError as error:
            raise MetadataError(str(error)) from error
        except FileNotFoundError:
            raise
        except OSError as error:
            raise MetadataError(f"No se pudo leer el archivo ({error}).") from error

        return ExtractionResult(
            common=_common_values(summary),
            details=_detail_values(summary),
        )


# -----------------------------------------------------------------------------
# Conversión del resumen a columnas
# -----------------------------------------------------------------------------


def _common_values(summary: GpxSummary) -> dict[str, Any]:
    """Columnas de 'media_items' (comunes a todos los tipos de medio)."""
    # Fecha del contenido: la del primer punto; si no hay horas, la del archivo GPX
    when = summary.start_time or summary.metadata_time
    local_text, offset_text = _local_time(when)

    start = summary.start_point
    return {
        # None en 'title' conserva el actual (el nombre del archivo): el procesador nunca lo vacía
        "title": summary.name,
        "description": summary.description,
        "creator": summary.author,
        "content_created_at": local_text,
        "content_date_precision": "second" if local_text else None,
        "content_date_source": "gpx" if local_text else None,
        "timezone_offset": offset_text,
        "latitude": start[0] if start else None,
        "longitude": start[1] if start else None,
        "altitude": start[2] if start else None,
        "duration": summary.duration_s,
    }


def _detail_values(summary: GpxSummary) -> dict[str, Any]:
    """Columnas de 'track_details' (propias de los tracks)."""
    end = summary.end_point
    bounds = summary.bounds
    return {
        "distance_m": _round(summary.distance_m, 1),
        "elevation_gain_m": _round(summary.elevation_gain_m, 1),
        "elevation_loss_m": _round(summary.elevation_loss_m, 1),
        "elevation_min_m": _round(summary.elevation_min_m, 1),
        "elevation_max_m": _round(summary.elevation_max_m, 1),
        "started_at": _utc_text(summary.start_time),
        "ended_at": _utc_text(summary.end_time),
        "point_count": summary.point_count,
        "segment_count": summary.segment_count,
        "track_count": summary.track_count,
        "route_count": summary.route_count,
        "waypoint_count": summary.waypoint_count,
        "min_latitude": bounds[0] if bounds else None,
        "max_latitude": bounds[1] if bounds else None,
        "min_longitude": bounds[2] if bounds else None,
        "max_longitude": bounds[3] if bounds else None,
        "end_latitude": end[0] if end else None,
        "end_longitude": end[1] if end else None,
        "activity_type": summary.activity_type,
        "creator_app": summary.creator_app,
        "is_planned_route": 1 if summary.uses_route else 0,
        "overview": encode_overview(simplify_track(summary.path_points)),
    }


def _local_time(moment: datetime | None) -> tuple[str | None, str | None]:
    """Hora local del EQUIPO (texto de la base de datos) y su desfase ('+02:00').

    'astimezone()' sin argumentos usa la zona del sistema y aplica el horario de verano
    que correspondía en ESA fecha (no el de hoy).
    """
    if moment is None:
        return None, None
    local = moment.astimezone()
    offset = local.utcoffset()
    if offset is None:
        return local.strftime(_DB_DATE_FORMAT), None
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return local.strftime(_DB_DATE_FORMAT), f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def _utc_text(moment: datetime | None) -> str | None:
    """Fecha UTC en el formato de la base de datos, o None."""
    return moment.strftime(_DB_DATE_FORMAT) if moment is not None else None


def _round(value: float | None, digits: int) -> float | None:
    """Redondea (para no guardar 12 decimales de metros), conservando None."""
    return round(value, digits) if value is not None else None


if __name__ == "__main__":
    # Autoprueba. Ejecutar desde la raíz del proyecto:  python -m core.metadata.track.extractor
    import os
    import tempfile
    import time

    GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Wikiloc" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><author><name>Javier</name></author></metadata>
  <trk>
    <name>Ruta X</name>
    <desc>Subida al pico</desc>
    <type>hiking</type>
    <trkseg>
      <trkpt lat="43.1" lon="-4.8"><ele>500</ele><time>2024-07-15T06:30:00Z</time></trkpt>
      <trkpt lat="43.2" lon="-4.8"><ele>900</ele><time>2024-07-15T10:30:00Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>"""

    # Zona horaria fija para que la prueba dé lo mismo en cualquier equipo (solo POSIX:
    # en Windows 'tzset' no existe y se comprueba solo el formato)
    if hasattr(time, "tzset"):
        os.environ["TZ"] = "Europe/Madrid"
        time.tzset()

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "ruta.gpx").write_text(GPX, encoding="utf-8")
        (base / "roto.gpx").write_text("<gpx><trk>", encoding="utf-8")
        (base / "ruta.tcx").write_text("<x/>", encoding="utf-8")

        extractor = TrackExtractor()
        result = extractor.extract(base / "ruta.gpx")
        common, details = result.common, result.details
        print(common)
        print(details)

        assert common["title"] == "Ruta X" and common["description"] == "Subida al pico"
        assert common["creator"] == "Javier" and common["content_date_source"] == "gpx"
        assert (common["latitude"], common["longitude"], common["altitude"]) == (43.1, -4.8, 500.0)
        assert common["duration"] == 4 * 3600
        if hasattr(time, "tzset"):
            # 06:30 UTC en julio = 08:30 en Madrid (horario de verano, +02:00)
            assert common["content_created_at"] == "2024-07-15 08:30:00", common
            assert common["timezone_offset"] == "+02:00"
        else:
            assert len(common["content_created_at"]) == 19
        assert details["started_at"] == "2024-07-15 06:30:00"  # UTC
        assert details["elevation_gain_m"] == 400 and details["elevation_loss_m"] == 0
        assert 11_100 < details["distance_m"] < 11_130  # 0,1° de latitud ≈ 11,1 km
        assert details["activity_type"] == "hiking" and details["creator_app"] == "Wikiloc"
        assert details["is_planned_route"] == 0 and details["point_count"] == 2
        assert result.user_data == {}  # los datos del usuario de un GPX van en .arca.json
        # El contorno: dos puntos, que vuelven tal cual
        from core.tracks.simplify import decode_overview

        assert decode_overview(details["overview"]) == (((43.1, -4.8), (43.2, -4.8)),)
        # Un GPX sin puntos no tiene contorno
        (base / "vacio.gpx").write_text('<gpx version="1.1" creator="x"></gpx>', encoding="utf-8")
        assert extractor.extract(base / "vacio.gpx").details["overview"] is None

        # Columnas que el extractor NUNCA puede escribir
        from core.metadata.base import PROTECTED_COLUMNS

        assert not set(common) & PROTECTED_COLUMNS

        # Errores: GPX dañado (MetadataError), formato sin soporte y archivo inexistente
        try:
            extractor.extract(base / "roto.gpx")
        except UnsupportedFormatError:
            raise AssertionError("un GPX dañado es un fallo, no un formato sin soporte") from None
        except MetadataError as error:
            print("roto.gpx:", error)
        try:
            extractor.extract(base / "ruta.tcx")
        except UnsupportedFormatError as error:
            print("ruta.tcx:", error)
        try:
            extractor.extract(base / "no_existe.gpx")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("debería lanzar FileNotFoundError")

        # Por lotes (lo que usa el procesador): un archivo malo no para a los demás
        batch = extractor.extract_batch([base / "ruta.gpx", base / "roto.gpx"])
        assert isinstance(batch[0], ExtractionResult) and isinstance(batch[1], MetadataError)

    print("Autoprueba finalizada correctamente.")
