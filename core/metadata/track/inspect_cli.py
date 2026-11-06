"""Herramienta de diagnóstico de tracks GPX: qué lee la aplicación y cómo cambia el desnivel.

Sirve para AJUSTAR el umbral del desnivel acumulado ('ELEVATION_THRESHOLD_M' en
'gpx_reader.py') comparando con lo que dicen Wikiloc, Garmin u otro programa para los
mismos tracks. La altitud del GPS oscila unos metros arriba y abajo: cuanto menor es el
umbral, más se suman esas oscilaciones y mayor sale el desnivel.

Uso (desde la raíz del proyecto):
    python -m core.metadata.track.inspect_cli ruta1.gpx ruta2.gpx ...
    python -m core.metadata.track.inspect_cli carpeta_de_tracks

Para cada archivo muestra su resumen y una tabla con el desnivel de subida y de bajada
para varios umbrales. Elige el umbral que más se acerque a la referencia en VARIOS
tracks (no en uno solo) y ponlo en 'ELEVATION_THRESHOLD_M'. Después sube
'TRACK_EXTRACTOR_VERSION' (en 'extractor.py') para que se vuelvan a leer los tracks
del catálogo con el umbral nuevo.
"""

__version__ = "1.0.0"
__all__ = ["main"]

# Librerías estándar
import sys
from pathlib import Path

# Módulos del proyecto
from core.metadata.track.gpx_reader import ELEVATION_THRESHOLD_M, GpxError, read_gpx

# Umbrales (metros) que se comparan en la tabla
THRESHOLDS_M: tuple[float, ...] = (0, 3, 5, 8, 10, 12, 15, 20, 25)


def _gpx_files(arguments: list[str]) -> list[Path]:
    """Archivos .gpx de los argumentos (los de una carpeta, incluidas sus subcarpetas)."""
    files: list[Path] = []
    for argument in arguments:
        path = Path(argument)
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.suffix.lower() == ".gpx")
        else:
            files.append(path)
    return files


def _inspect(path: Path) -> None:
    """Muestra el resumen de un track y su desnivel con varios umbrales."""
    print(f"\n=== {path.name} ===")
    try:
        summary = read_gpx(path)
    except (GpxError, OSError) as error:
        print(f"  No se pudo leer: {error}")
        return

    distance = f"{summary.distance_m / 1000:.2f} km" if summary.distance_m is not None else "-"
    print(f"  Nombre:     {summary.name or '-'}")
    print(f"  Distancia:  {distance}   Puntos: {summary.point_count}   "
          f"Segmentos: {summary.segment_count}")  # fmt: skip
    print(f"  Altitud:    mín. {summary.elevation_min_m} m   máx. {summary.elevation_max_m} m")
    print(f"  Inicio UTC: {summary.start_time}   Programa: {summary.creator_app or '-'}")
    if summary.elevation_min_m is None:
        print("  El track no tiene altitudes: no hay desnivel que calcular.")
        return

    print("  Umbral (m)   Subida (m)   Bajada (m)")
    for threshold in THRESHOLDS_M:
        data = read_gpx(path, threshold_m=threshold)
        mark = "  <- actual" if threshold == ELEVATION_THRESHOLD_M else ""
        print(f"  {threshold:>10g}   {data.elevation_gain_m:>10.0f}   "
              f"{data.elevation_loss_m:>10.0f}{mark}")  # fmt: skip


def main(arguments: list[str] | None = None) -> int:
    """Punto de entrada de la herramienta. Devuelve el código de salida."""
    arguments = sys.argv[1:] if arguments is None else arguments
    if not arguments:
        print(__doc__)
        return 1
    files = _gpx_files(arguments)
    if not files:
        print("No se ha encontrado ningún archivo .gpx.")
        return 1
    for path in files:
        _inspect(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
