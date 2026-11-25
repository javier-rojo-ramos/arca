"""Herramienta de diagnóstico de canciones: qué lee la aplicación, para compararlo con Mp3tag.

Para cada archivo enseña lo que entrega el lector ('core/audio/tag_reader.py'): el tipo de
etiqueta, los campos ya traducidos (en el orden de la sección «Audio» del inspector), los
datos técnicos y las imágenes. Con '--bruto', además, las etiquetas tal como las da
mutagen (sin los bytes de las imágenes): sirve para ver de dónde sale un valor raro.
Solo lee: nunca cambia los archivos.

Uso (desde la raíz del proyecto):
    python -m core.metadata.audio.inspect_cli cancion.mp3 otra.flac ...
    python -m core.metadata.audio.inspect_cli carpeta                 # y sus subcarpetas
    python -m core.metadata.audio.inspect_cli carpeta --resumen       # una línea por canción
    python -m core.metadata.audio.inspect_cli cancion.mp3 --bruto
    python -m core.metadata.audio.inspect_cli carpeta --json salida.json

1.0.0 Primera versión (25/11/2026; docs/MOD_MUSICA.md, paso MUS 1.1).
"""

__version__ = "1.0.0"
__all__ = ["main"]

# Librerías estándar
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Librerías de terceros
import mutagen

# Módulos del proyecto
from core.audio.picture_types import picture_type_label
from core.audio.tag_map import TAG_FIELDS
from core.audio.tag_reader import AudioInfo, AudioPicture, AudioReadError, read_audio

# Extensiones que se buscan dentro de una carpeta (las de audio que se catalogan y algunas
# más que mutagen abre)
AUDIO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav", ".aif", ".aiff",
    ".mka", ".wma", ".wv", ".ape",
})  # fmt: skip
# Ancho de la columna de las etiquetas en la salida
_LABEL_WIDTH = 20
# Largo máximo de un valor en bruto
_RAW_MAX = 90


def _audio_files(arguments: list[str]) -> list[Path]:
    """Los archivos de los argumentos (los de una carpeta, con sus subcarpetas)."""
    files: list[Path] = []
    for argument in arguments:
        path = Path(argument)
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.suffix.lower() in AUDIO_EXTENSIONS)
        else:
            files.append(path)
    return files


def _duration_text(seconds: float | None) -> str:
    """«4:12» (o «1:02:03»)."""
    if not seconds:
        return ""
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def _pair_text(number: int | None, total: int | None) -> str:
    """«3 / 12», «3» o vacío."""
    if number is None and total is None:
        return ""
    return f"{number or ''} / {total}" if total else str(number)


def _picture_text(picture: AudioPicture) -> str:
    """«Portada · image/jpeg · 600 × 600 · 88,7 KB»."""
    kind = picture_type_label(picture.type_key) or "(sin tipo)"
    size = f"{picture.width} × {picture.height}" if picture.width else "¿tamaño?"
    weight = f"{picture.size_bytes / 1024:.1f} KB".replace(".", ",")
    parts = [kind, picture.mime or "¿formato?", size, weight]
    if picture.description:
        parts.append(f"«{picture.description}»")
    return " · ".join(parts)


def _quality_text(info: AudioInfo) -> str:
    """«MP3 · CBR · 320 kbps · 44,1 kHz · 2 canales» (con los bits si es sin pérdida)."""
    tech = info.technical
    parts = [(tech.codec or "¿códec?").upper()]
    if tech.codec_detail:
        parts.append(tech.codec_detail)
    if tech.bitrate_mode:
        parts.append(tech.bitrate_mode.upper())
    if tech.bitrate:
        parts.append(f"{round(tech.bitrate / 1000)} kbps")
    if tech.sample_rate:
        parts.append(f"{tech.sample_rate / 1000:g} kHz".replace(".", ","))
    if tech.channels:
        parts.append(f"{tech.channels} canales")
    if tech.bit_depth:
        parts.append(f"{tech.bit_depth} bits")
    if tech.lossless:
        parts.append("sin pérdida")
    return " · ".join(parts)


def _field_values(info: AudioInfo) -> list[tuple[str, str]]:
    """Los campos, en el orden de la tabla, como (etiqueta, texto)."""
    tags = info.tags
    rows = []
    for field in TAG_FIELDS:
        if field.key in ("track", "disc"):
            value = _pair_text(getattr(tags, f"{field.key}_number"), getattr(tags, f"{field.key}_total"))
        else:
            value = getattr(tags, field.key) or ""
        rows.append((field.label, value))
    return rows


def _raw_tags(path: Path) -> list[str]:
    """Las etiquetas tal como las da mutagen, una por línea (sin los bytes de las imágenes)."""
    audio = mutagen.File(path)
    if audio is None or audio.tags is None:
        return ["(sin etiquetas)"]
    lines = []
    for key, value in audio.tags.items():
        name = type(value).__name__
        if name in ("APIC", "MP4Cover") or str(key).lower() in ("covr", "metadata_block_picture"):
            text = f"[imagen{'s' if isinstance(value, list) and len(value) > 1 else ''}]"
        else:
            text = repr(value) if not hasattr(value, "text") else repr(list(map(str, value.text)))
        lines.append(f"{key!s:<28} {text[:_RAW_MAX]}")
    return lines


def _print_detail(path: Path, info: AudioInfo, raw: bool) -> None:
    """Todo lo leído de un archivo."""
    print(f"=== {path}")
    print(f"{'Etiqueta':<{_LABEL_WIDTH}}{info.tag_type or '(ninguna)'}")
    for label, value in _field_values(info):
        print(f"  {label:<{_LABEL_WIDTH - 2}}{value}")
    print(f"{'Duración':<{_LABEL_WIDTH}}{_duration_text(info.technical.duration)}")
    print(f"{'Formato y calidad':<{_LABEL_WIDTH}}{_quality_text(info)}")
    if not info.pictures:
        print(f"{'Imágenes':<{_LABEL_WIDTH}}(ninguna)")
    for number, picture in enumerate(info.pictures, start=1):
        label = "Imágenes" if number == 1 else ""
        print(f"{label:<{_LABEL_WIDTH}}{_picture_text(picture)}")
    if raw:
        print("En bruto (mutagen):")
        for line in _raw_tags(path):
            print(f"  {line}")
    print()


def _summary_line(path: Path, info: AudioInfo) -> str:
    """Una línea por canción: lo justo para recorrer una carpeta."""
    tags = info.tags
    cover = info.cover
    cover_text = f"{cover.width}×{cover.height}" if cover and cover.width else ("sí" if cover else "-")
    columns = [
        path.suffix.lower(), info.tag_type or "-", _pair_text(tags.track_number, tags.track_total),
        tags.title or "-", tags.artist or "-", tags.album or "-", tags.date or "-",
        tags.genre or "-", _duration_text(info.technical.duration), _quality_text(info),
        f"carátula {cover_text}",
    ]  # fmt: skip
    return " | ".join(columns)


def _as_json(path: Path, info: AudioInfo | None, error: str | None) -> dict[str, Any]:
    """Lo leído de un archivo, para el JSON."""
    if info is None:
        return {"path": str(path), "error": error}
    data = asdict(info)
    data["path"] = str(path)
    return data


def main(argv: list[str] | None = None) -> int:
    """Lee los archivos pedidos y enseña lo que entiende la aplicación."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="canciones o carpetas")
    parser.add_argument("--resumen", action="store_true", help="una línea por canción")
    parser.add_argument("--bruto", action="store_true", help="también las etiquetas de mutagen")
    parser.add_argument("--json", type=Path, help="guarda todo lo leído en este archivo")
    args = parser.parse_args(argv)
    # En la consola de Windows, lo que no quepa en su juego de caracteres sale como «?»
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    files = _audio_files(args.paths)
    results: list[dict[str, Any]] = []
    errors = 0
    for path in files:
        try:
            info = read_audio(path)
        except AudioReadError as error:
            errors += 1
            print(f"=== {path}\n  ERROR: {error}\n" if not args.resumen else f"{path.name} | ERROR: {error}")
            results.append(_as_json(path, None, str(error)))
            continue
        if args.resumen:
            print(_summary_line(path, info))
        else:
            _print_detail(path, info, args.bruto)
        results.append(_as_json(path, info, None))

    print(f"\n{len(files)} archivos, {errors} con error.")
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Guardado: {args.json}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
