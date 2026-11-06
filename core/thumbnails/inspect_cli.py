"""Herramienta de diagnóstico: genera las miniaturas de unos archivos reales y las cuenta.

Sirve para comprobar, ANTES de conectar nada a la base de datos, que cada formato
(JPG, PNG, HEIC, DNG, NEF, CR2, CR3, ARW...) se lee bien, se gira como toca, conserva
los colores y da los tamaños esperados. Se ejecuta con archivos de verdad, igual que
'core.metadata.inspect_cli'.

Uso (desde la raíz del proyecto):

    python -m core.thumbnails.inspect_cli foto.jpg foto.heic foto.dng
    python -m core.thumbnails.inspect_cli foto.nef --salida C:\\Temp\\prueba_miniaturas
    python -m core.thumbnails.inspect_cli foto.cr3 --tamanos 160,480
    python -m core.thumbnails.inspect_cli foto.dng --detalle

Para cada archivo muestra qué origen entregó la imagen (pillow, heif, raw_preview:...),
su tamaño, la orientación aplicada y cada miniatura escrita, y deja en la carpeta de
salida una caché igual que la de un catálogo ('cache/photo/160/0/1.jpg'...) más un
'indice.txt' que dice qué número corresponde a cada archivo. Abre las imágenes de esa
carpeta para revisarlas a ojo (sobre todo: ¿está girada bien una foto vertical?).

No modifica ningún archivo original: solo lee.
"""

__version__ = "1.0.1"
__all__ = ["main"]

# Librerías estándar
import argparse
import sys
import tempfile
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.metadata.exiftool_runner import ExifToolError, ExifToolRunner
from core.thumbnails.cache import ThumbnailCache
from core.thumbnails.generator import generate_thumbnails
from core.thumbnails.registry import default_registry
from core.thumbnails.sizes import ALL_SIZES, ThumbnailSize
from core.thumbnails.sources.base import ThumbnailError, ThumbnailRequest


def _parse_sizes(text: str) -> list[ThumbnailSize]:
    """Convierte '160,480' en la lista de tamaños correspondiente."""
    by_side = {size.max_side: size for size in ALL_SIZES}
    chosen: list[ThumbnailSize] = []
    for part in text.split(","):
        side = int(part.strip())
        if side not in by_side:
            valid = ", ".join(str(size.max_side) for size in ALL_SIZES)
            raise ValueError(f"El tamaño {side} no existe. Tamaños válidos: {valid}")
        chosen.append(by_side[side])
    return chosen


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada. Devuelve el código de salida (0 = todo bien)."""
    # Las consolas de Windows suelen usar una codificación que no admite todos los caracteres
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Genera las miniaturas de unos archivos reales y muestra el resultado."
    )
    parser.add_argument("files", nargs="+", type=Path, help="archivos de imagen a procesar")
    parser.add_argument("--salida", type=Path, help="carpeta donde dejar la caché de prueba")
    parser.add_argument("--tamanos", default="", help="lados largos separados por comas (por defecto, todos)")
    parser.add_argument("--exiftool", help="ruta del ejecutable de ExifTool")
    parser.add_argument(
        "--detalle",
        action="store_true",
        help="muestra los mensajes de depuración (p. ej. qué vistas previas trae un RAW y cuál se usa)",
    )
    args = parser.parse_args(argv)

    try:
        sizes = _parse_sizes(args.tamanos) if args.tamanos else list(ALL_SIZES)
    except ValueError as error:
        parser.error(str(error))

    # Por defecto solo avisos y errores del registro de la aplicación; con --detalle, también la depuración
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.detalle else "WARNING")

    runner = None
    if args.exiftool:
        try:
            runner = ExifToolRunner(command=[args.exiftool])
        except ExifToolError as error:
            print(f"ExifTool no se pudo usar: {error}")
            return 2
    registry = default_registry(runner)

    output = args.salida or Path(tempfile.gettempdir()) / "arca_miniaturas_prueba"
    cache = ThumbnailCache(output)
    print(f"Carpeta de salida: {output}\n")

    index_lines: list[str] = []
    failures = 0
    for number, path in enumerate(args.files, start=1):
        index_lines.append(f"{number}\t{path}")
        print(f"=== {number}. {path.name} ===")
        request = ThumbnailRequest(number, MediaType.PHOTO, path)
        try:
            result = generate_thumbnails(request, cache, registry, sizes)
        except FileNotFoundError:
            print("  ERROR: el archivo no existe\n")
            failures += 1
            continue
        except ThumbnailError as error:
            print(f"  ERROR: {error}\n")
            failures += 1
            continue

        original = "?" if result.original_size is None else f"{result.original_size[0]}x{result.original_size[1]}"
        print(f"  Origen:            {result.source_name}")
        print(f"  Original (girado): {original}")
        print(f"  Imagen de partida: {result.source_size[0]}x{result.source_size[1]}")
        for thumbnail in result.thumbnails:
            print(
                f"  {thumbnail.size.max_side:>5} px  ->  {thumbnail.width}x{thumbnail.height}"
                f"  ({thumbnail.file_bytes / 1024:.1f} KB)  {thumbnail.path.relative_to(output).as_posix()}"
            )
        print(f"  Tiempo: {result.seconds * 1000:.0f} ms\n")

    output.mkdir(parents=True, exist_ok=True)
    (output / "indice.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"Listo: {len(args.files) - failures} correctos, {failures} con error.")
    print("Abre las imágenes de la carpeta de salida para revisarlas (el número del nombre es el del índice).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
