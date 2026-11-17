"""Icono de la aplicación (el de la ventana y la barra de tareas), según el sistema.

Los archivos están en 'resources/icons/' (su 'README.md' explica el diseño y qué hay en
cada carpeta). Cada sistema usa su juego:

    - Windows: 'windows/arca-media.ico', que ya lleva todos los tamaños (16, 24 y 32 en
      versión simplificada; 48, 64, 128 y 256).
    - macOS: los PNG de 'macos/png/' (16 a 1024, con la retícula y la sombra de Apple).
    - Linux y el resto: los PNG de 'windows/png/' (así los tamaños pequeños son también
      las versiones simplificadas) y 'linux/arca-media-512.png' para el más grande.

Con varios tamaños, Qt elige en cada sitio el que mejor encaja, en lugar de reducir uno
grande (a 16 px, el diseño completo no se distingue).

El icono del ejecutable (PyInstaller, '--icon') es otra cosa: ver [PENDIENTE.md] 'GEN 5'.

Uso:
    from ui_helpers.helpers.app_icon import build_app_icon

    window.setWindowIcon(build_app_icon())

1.0.0 Primera versión (17/11/2026), con el icono nuevo de Arca Media.
"""

__version__ = "1.0.0"
__all__ = ["app_icon_files", "build_app_icon"]

# Librerías estándar
import sys
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QSize
from qtpy.QtGui import QIcon

# Módulos del proyecto
from config import app_paths

# Carpeta de los iconos de la aplicación
ICONS_DIR = app_paths.RESOURCES_DIR / "icons"


def _png_size(png: Path) -> int | None:
    """Tamaño de un PNG, sacado de su nombre ('arca-media-256.png' -> 256); None si no lo hay."""
    tail = png.stem.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else None


def app_icon_files(
    platform: str | None = None, icons_dir: Path = ICONS_DIR
) -> list[tuple[Path, int | None]]:
    """Archivos del icono para un sistema, con su tamaño (None: el archivo trae varios).

    'platform' es como 'sys.platform' ("win32", "darwin", "linux"...); None = el actual.
    Solo devuelve los archivos que existen, ordenados de menor a mayor.
    """
    platform = platform or sys.platform
    if platform == "win32":
        ico = icons_dir / "windows" / "arca-media.ico"
        return [(ico, None)] if ico.is_file() else []

    if platform == "darwin":
        pngs = list((icons_dir / "macos" / "png").glob("arca-media-*.png"))
    else:
        pngs = [
            *(icons_dir / "windows" / "png").glob("arca-media-*.png"),
            *(icons_dir / "linux").glob("arca-media-512.png"),
        ]
    sized = [(png, _png_size(png)) for png in pngs]
    return sorted(
        ((png, size) for png, size in sized if size is not None), key=lambda item: item[1]
    )


def build_app_icon(platform: str | None = None, icons_dir: Path = ICONS_DIR) -> QIcon:
    """El icono de la aplicación para el sistema actual (o 'platform'), con todos sus tamaños.

    Si no se encuentra ningún archivo, devuelve un icono vacío (la ventana usa el del
    sistema) y lo avisa en el registro: no impide arrancar.
    """
    icon = QIcon()
    files = app_icon_files(platform, icons_dir)
    for path, size in files:
        if size is None:
            # Un .ico: Qt añade cada imagen que contiene, cada una con su tamaño
            icon.addFile(str(path))
        else:
            icon.addFile(str(path), QSize(size, size))
    if not files:
        logger.warning(f"No se ha encontrado el icono de la aplicación en '{icons_dir}'.")
    return icon


if __name__ == "__main__":
    # Librerías de terceros (Qt)
    from qtpy.QtGui import QGuiApplication

    # 1. Archivos de cada sistema, con los iconos reales del proyecto
    win = app_icon_files("win32")
    assert [path.name for path, _ in win] == ["arca-media.ico"], win
    mac = app_icon_files("darwin")
    assert [size for _, size in mac] == [16, 32, 64, 128, 256, 512, 1024], mac
    linux = app_icon_files("linux")
    assert [size for _, size in linux] == [16, 24, 32, 48, 64, 128, 256, 512], linux
    assert linux[0][0].parent.name == "png" and linux[-1][0].parent.name == "linux", linux
    print("1. Archivos de cada sistema: OK")

    # 2. Sin carpeta de iconos: lista vacía e icono vacío, sin error
    missing = Path(__file__).parent / "no_existe"
    assert app_icon_files("win32", missing) == []
    assert app_icon_files("linux", missing) == []

    # Para crear un QIcon hace falta una aplicación (sin ventana: 'offscreen' si no hay
    # pantalla; en Windows, la plataforma normal no abre nada)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    assert build_app_icon("win32", missing).isNull()
    print("2. Sin iconos: OK")

    # 3. El .ico de Windows trae todos sus tamaños, también los simplificados
    sizes = {size.width() for size in build_app_icon("win32").availableSizes()}
    assert {16, 24, 32, 48, 64, 128, 256} <= sizes, sizes
    sizes = {size.width() for size in build_app_icon("linux").availableSizes()}
    assert {16, 24, 32, 256, 512} <= sizes, sizes
    print("3. Tamaños del icono: OK")

    print("Autoprueba finalizada correctamente.")
