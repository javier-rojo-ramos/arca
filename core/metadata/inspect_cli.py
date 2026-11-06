"""Herramienta de diagnóstico: muestra lo que ExifTool lee de unos archivos reales.

Sirve para ver, antes de escribir el extractor, qué etiquetas trae cada formato
(JPEG, HEIC, DNG, NEF, CR3...) y en qué grupo está cada una (EXIF, XMP, IPTC...).
Así se decide con datos de verdad de dónde se toma cada campo de la base de datos.

Uso (desde la raíz del proyecto):

    python -m core.metadata.inspect_cli foto.jpg foto.heic foto.dng
    python -m core.metadata.inspect_cli foto.nef --json salida.json
    python -m core.metadata.inspect_cli foto.cr3 --todo
    python -m core.metadata.inspect_cli foto.heic --campos
    python -m core.metadata.inspect_cli video.mov --campos

Para cada archivo muestra:
    - Si tiene archivos sidecar .xmp (y los lee también).
    - Las etiquetas "clave" que usará la aplicación, con TODAS las fuentes donde
      aparecen (p. ej. 'City' en XMP y en IPTC) para ver si coinciden.
    - Con '--todo', todas las etiquetas agrupadas por grupo.
    - Con '--json', guarda la salida completa en un archivo (para compartirla).
    - Con '--campos', muestra lo que la aplicación guardaría en la base de datos
      (columna por columna), para compararlo con lo que muestra Lightroom. Usa el
      extractor de cada tipo: imagen (fotos y RAW) o vídeo, según el tipo del archivo.

No modifica ningún archivo: solo lee.

1.3.0 '--campos' muestra también los datos del usuario y las palabras clave que se leen.
1.2.0 '--campos' también para vídeos (extractor según el tipo del archivo).
"""

__version__ = "1.3.0"
__all__ = ["KEY_TAGS", "build_report", "main"]

# Librerías estándar
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Módulos del proyecto
from core.metadata.exiftool_runner import (
    ExifToolError,
    ExifToolNotFoundError,
    ExifToolRunner,
    FileMetadata,
    find_sidecars,
)

# Etiquetas que interesan al catalogador, por bloques (nombre sin grupo)
KEY_TAGS: dict[str, tuple[str, ...]] = {
    "Cámara y toma": (
        "Make",
        "Model",
        "LensModel",
        "LensID",
        "SerialNumber",
        "BodySerialNumber",
        "FocalLength",
        "FocalLengthIn35mmFormat",
        "FNumber",
        "ExposureTime",
        "ISO",
        "ExposureCompensation",
        "BrightnessValue",
        "ExposureProgram",
        "MeteringMode",
        "Flash",
        "WhiteBalance",
        "Software",
    ),
    "Fechas, tamaño y orientación": (
        "DateTimeOriginal",
        "SubSecDateTimeOriginal",
        "OffsetTimeOriginal",
        "CreateDate",
        "ModifyDate",
        "Orientation",
        "ImageWidth",
        "ImageHeight",
        "ExifImageWidth",
        "ExifImageHeight",
        "ImageSize",
    ),
    "GPS": (
        "GPSLatitude",
        "GPSLongitude",
        "GPSAltitude",
        "GPSAltitudeRef",
        "GPSImgDirection",
    ),
    "Descripción y autoría": (
        "Title",
        "ObjectName",
        "Description",
        "ImageDescription",
        "Caption-Abstract",
        "UserComment",
        "Artist",
        "Creator",
        "Copyright",
        "Rights",
        "Subject",
        "Keywords",
        "Rating",
        "Label",
    ),
    "Ubicación": (
        "Location",
        "Sub-location",
        "City",
        "State",
        "Province-State",
        "Country",
        "Country-PrimaryLocationName",
        "CountryCode",
        "Country-PrimaryLocationCode",
    ),
}

# Valores más largos que esto se recortan en el informe
MAX_VALUE_LENGTH = 90


def _short(value: Any) -> str:
    """Valor en una línea, recortado si es muy largo."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace("\n", " ⏎ ")
    return text if len(text) <= MAX_VALUE_LENGTH else text[: MAX_VALUE_LENGTH - 1] + "…"


def _occurrences(sources: list[tuple[str, FileMetadata]], name: str) -> list[tuple[str, str, Any]]:
    """Todas las apariciones de una etiqueta: (fuente, grupo, valor), sin importar el grupo."""
    found: list[tuple[str, str, Any]] = []
    for source_label, metadata in sources:
        for key, value in metadata.tags.items():
            group, separator, tag = key.rpartition(":")
            if (tag == name or key == name) and value not in (None, ""):
                found.append((source_label, group if separator else "(sin grupo)", value))
    return found


def build_report(
    path: Path, metadata: FileMetadata, sidecars: list[FileMetadata], *, show_all: bool = False
) -> str:
    """Construye el informe de texto de un archivo (y de sus sidecars).

    Args:
        path: Archivo analizado.
        metadata: Lo que ExifTool leyó del archivo.
        sidecars: Lo que leyó de cada sidecar .xmp que lo acompaña.
        show_all: Si es True, añade todas las etiquetas agrupadas.
    """
    lines = [f"=== {path.name} ===", f"Ruta: {path}"]
    lines.append(
        "Sidecars: " + (", ".join(sidecar.path.name for sidecar in sidecars) or "(ninguno)")
    )
    if metadata.error:
        lines.append(f"ERROR de ExifTool: {metadata.error}")
    for sidecar in sidecars:
        if sidecar.error:
            lines.append(f"ERROR leyendo {sidecar.path.name}: {sidecar.error}")
    lines.append(f"Etiquetas leídas del archivo: {len(metadata.tags)}")

    sources = [("archivo", metadata)] + [(f"sidecar {s.path.name}", s) for s in sidecars]

    for block, names in KEY_TAGS.items():
        block_lines: list[str] = []
        for name in names:
            occurrences = _occurrences(sources, name)
            if not occurrences:
                continue
            parts = [f"{_short(value)} [{group}{'' if source == 'archivo' else ', ' + source}]"
                     for source, group, value in occurrences]
            marker = "   <-- varias fuentes" if len(occurrences) > 1 else ""
            block_lines.append(f"  {name:<27} {'  |  '.join(parts)}{marker}")
        if block_lines:
            lines += ["", f"-- {block} --", *block_lines]

    if show_all:
        by_group: dict[str, list[str]] = defaultdict(list)
        for source_label, source_metadata in sources:
            for key, value in sorted(source_metadata.tags.items()):
                group, _separator, tag = key.rpartition(":")
                suffix = "" if source_label == "archivo" else f"   ({source_label})"
                by_group[group or "(sin grupo)"].append(f"    {tag} = {_short(value)}{suffix}")
        lines += ["", "-- Todas las etiquetas, por grupo --"]
        for group in sorted(by_group):
            lines += [f"  [{group}]", *by_group[group]]

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada. Devuelve el código de salida (0 = bien)."""
    # Las consolas de Windows suelen usar una codificación que no admite todos los caracteres
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Muestra lo que ExifTool lee de unos archivos (solo lectura)."
    )
    parser.add_argument("files", nargs="*", type=Path, help="archivos a analizar")
    parser.add_argument("--todo", action="store_true", help="muestra todas las etiquetas")
    parser.add_argument("--campos", action="store_true", help="muestra lo que se guardaría en la base de datos")
    parser.add_argument("--json", type=Path, help="guarda la salida completa en este archivo")
    parser.add_argument("--exiftool", help="ruta del ejecutable de ExifTool")
    parser.add_argument("--autoprueba", action="store_true", help="prueba el informe con datos falsos")
    args = parser.parse_args(argv)

    if args.autoprueba:
        return _self_test()
    if not args.files:
        parser.error("indica al menos un archivo")

    try:
        runner = ExifToolRunner(command=[args.exiftool] if args.exiftool else None)
        print(f"ExifTool {runner.version()}  ({' '.join(runner.command)})\n")
    except ExifToolNotFoundError as error:
        print(error)
        return 2
    except ExifToolError as error:
        print(f"ExifTool no se pudo ejecutar: {error}")
        return 2

    # Se leen a la vez los archivos y sus sidecars (una sola llamada a ExifTool)
    sidecars_of = {path: find_sidecars(path) for path in args.files}
    to_read = [*args.files, *(sidecar for found in sidecars_of.values() for sidecar in found)]
    try:
        results = runner.read(to_read)
    except ExifToolError as error:
        print(f"ExifTool falló: {error}")
        return 1

    dump: dict[str, Any] = {"exiftool": runner.version(), "files": {}}
    for path in args.files:
        metadata = results.get(path, FileMetadata(path, error="sin datos"))
        sidecar_metadata = [results[s] for s in sidecars_of[path] if s in results]
        print(build_report(path, metadata, sidecar_metadata, show_all=args.todo), "\n")
        dump["files"][str(path)] = {
            "error": metadata.error,
            "tags": metadata.tags,
            "sidecars": {str(s.path): {"error": s.error, "tags": s.tags} for s in sidecar_metadata},
        }

    if args.campos:
        _print_fields(runner, args.files)

    if args.json:
        args.json.write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Salida completa guardada en: {args.json}")
    return 0


def _print_fields(runner: ExifToolRunner, files: list[Path]) -> None:
    """Muestra, columna por columna, lo que la aplicación guardaría de cada archivo.

    Elige el extractor por el tipo del archivo: vídeo para los vídeos e imagen para lo demás
    (como antes, que solo había imágenes).
    """
    from core.catalog.media_detector import MediaTypeDetector
    from core.catalog.media_types import MediaType
    from core.metadata.base import ExtractionResult
    from core.metadata.image.extractor import ImageExtractor
    from core.metadata.video.extractor import VideoExtractor

    # El mismo detector que el escáner (extensión, tipo MIME y contenido)
    detector = MediaTypeDetector()
    extractors = {MediaType.VIDEO: VideoExtractor(runner)}
    default_extractor = ImageExtractor(runner)
    for path in files:
        media_type = detector.detect(path)
        extractor = extractors.get(media_type, default_extractor)
        result = extractor.extract_batch([path])[0]
        print(f"=== {path.name}: lo que se guardaría en la base de datos ===")
        if not isinstance(result, ExtractionResult):
            print(f"  No se puede extraer: {result}\n")
            continue
        for title, values in (
            ("media_items", result.common),
            (extractor.details_table or "detalles", result.details),
        ):
            print(f"-- {title} --")
            for column, value in values.items():
                shown = "—" if value is None else _short(value)
                print(f"  {column:<24} {shown}")
        # Datos del usuario (valoración, marca, color) y palabras clave
        user_data = dict(result.user_data)
        keywords = user_data.pop("keywords", None)
        if user_data:
            print("-- datos del usuario --")
            for column, value in user_data.items():
                shown = "— (el archivo no dice nada)" if value is None else _short(value)
                print(f"  {column:<24} {shown}")
        if keywords is not None:
            print(f"-- palabras clave ({len(keywords.paths) + len(keywords.flat)}) --")
            for path in keywords.paths:
                print(f"  {' > '.join(path)}")
            for name in keywords.flat:
                print(f"  {name}   (suelta, sin jerarquía)")
        print()


def _self_test() -> int:
    """Autoprueba del informe con datos inventados (no necesita ExifTool)."""
    photo = FileMetadata(
        Path("/fotos/IMG_6078.jpg"),
        {
            "IFD0:Make": "Apple",
            "ExifIFD:FNumber": 1.8,
            "ExifIFD:ExposureTime": 0.0285714,
            "XMP-photoshop:City": "Madrid",
            "IPTC:City": "Alcobendas",
            "GPS:GPSLatitude": 40.4282,
            "XMP-dc:Description": "x" * 200,
            "XMP-photoshop:Country": "",
        },
    )
    sidecar = FileMetadata(Path("/fotos/IMG_6078.xmp"), {"XMP-photoshop:City": "Getafe"})
    report = build_report(photo.path, photo, [sidecar], show_all=True)
    print(report)

    assert "Sidecars: IMG_6078.xmp" in report
    assert "Apple [IFD0]" in report and "1.8 [ExifIFD]" in report
    # Una etiqueta en varias fuentes se muestra completa y se marca
    city_line = next(line for line in report.splitlines() if line.strip().startswith("City"))
    assert "Madrid [XMP-photoshop]" in city_line and "Alcobendas [IPTC]" in city_line
    assert "Getafe [XMP-photoshop, sidecar IMG_6078.xmp]" in city_line and "varias fuentes" in city_line
    assert "Country" not in "".join(
        line for line in report.splitlines() if line.startswith("  Country")
    )  # vacío = no se muestra
    assert "…" in report  # los valores largos se recortan
    assert "-- Todas las etiquetas, por grupo --" in report and "[IPTC]" in report

    missing = build_report(Path("/x/a.jpg"), FileMetadata(Path("/x/a.jpg"), error="File not found"), [])
    assert "ERROR de ExifTool: File not found" in missing
    print("\nAutoprueba finalizada correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
