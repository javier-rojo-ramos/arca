"""Mostrar una carpeta o un archivo en el explorador de archivos del sistema.

Cada sistema lo hace a su manera:
    - Windows: el Explorador se abre en la carpeta PADRE con el elemento seleccionado
      ('explorer /select,"ruta"'), como hace Lightroom.
    - macOS:   el Finder, también con el elemento seleccionado ('open -R ruta').
    - Linux:   no hay una forma estándar de seleccionar: se abre la carpeta (si es un
      archivo, la carpeta que lo contiene) con el gestor de archivos del escritorio.

Papelera ('move_to_trash'): envía un archivo a la papelera del sistema con
'QFile.moveToTrash' (Qt 5.15+; Papelera de reciclaje en Windows, Papelera en macOS y la
de freedesktop.org en Linux). Es la función 'trash' que recibe
'core/catalog/media_removal.remove_media_items' (core/ no usa Qt).

1.1.0 'move_to_trash': enviar un archivo a la papelera del sistema.

Uso:
    from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME, reveal_in_file_manager

    action = menu.addAction(f"Mostrar en {FILE_MANAGER_NAME}")
    if not reveal_in_file_manager(path):
        ...  # avisar al usuario
"""

__version__ = "1.1.0"
__all__ = ["FILE_MANAGER_NAME", "move_to_trash", "reveal_in_file_manager"]

# Librerías estándar
import os
import subprocess
import sys
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QFile, QUrl
from qtpy.QtGui import QDesktopServices

# Nombre del explorador de archivos, para los textos de los menús ("Mostrar en el Explorador")
match sys.platform:
    case "win32":
        FILE_MANAGER_NAME = "el Explorador"
    case "darwin":
        FILE_MANAGER_NAME = "el Finder"
    case _:
        FILE_MANAGER_NAME = "el gestor de archivos"


def reveal_in_file_manager(path: str | Path) -> bool:
    """Muestra una carpeta o un archivo en el explorador de archivos del sistema.

    No espera a que se cierre el explorador (se lanza aparte).

    Args:
        path: Ruta de la carpeta o del archivo. Debe existir.

    Returns:
        True si se pudo lanzar el explorador; False si la ruta no existe o falló.
    """
    target = Path(path)
    try:
        if not target.exists():
            return False
    except OSError:
        return False  # p. ej. una unidad de red que no responde

    try:
        if sys.platform == "win32":
            # Se pasa como TEXTO (no como lista): el Explorador solo entiende las comillas
            # si van justo después de la coma ('/select,"ruta con espacios"'); con una lista,
            # Python pondría las comillas alrededor de todo el argumento.
            native = os.path.normpath(str(target))  # barras invertidas
            subprocess.Popen(f'explorer /select,"{native}"')
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
            return True
    except OSError:
        logger.opt(exception=True).warning(f"No se pudo abrir el explorador para: {target}")
        # Se intenta la forma genérica de Qt (abre la carpeta, sin seleccionar)

    # Linux (o si lo anterior falló): se abre la carpeta con el programa del escritorio
    folder = target if target.is_dir() else target.parent
    opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
    if not opened:
        logger.warning(f"No se pudo abrir la carpeta en el gestor de archivos: {folder}")
    return bool(opened)


def move_to_trash(path: str | Path) -> None:
    """Envía un archivo a la papelera del sistema.

    Se puede llamar desde un hilo secundario: 'QFile.moveToTrash' es una función
    estática que no crea objetos de Qt ligados a un hilo.

    Ojo: en Windows, una carpeta de RED no tiene papelera y el archivo se borraría para
    siempre. Quien llama debe evitarlo antes ('media_removal.is_network_path').

    Args:
        path: Ruta del archivo.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        OSError: Si el sistema no pudo enviarlo a la papelera (abierto en otro programa,
            sin permisos, unidad sin papelera...). El archivo sigue donde estaba.
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"No existe: {target}")
    # Según la versión de PySide6, la función estática devuelve un bool o una tupla
    # (bool, ruta dentro de la papelera): se aceptan las dos formas
    outcome = QFile.moveToTrash(str(target))
    moved = outcome[0] if isinstance(outcome, tuple) else bool(outcome)
    if not moved:
        raise OSError(f"El sistema no pudo enviar el archivo a la papelera: {target}")
