"""Utilidades para la interacción con el sistema de archivos mediante diálogos gráficos.

Este módulo proporciona funciones desacopladas para la selección de archivos y
carpetas utilizando los cuadros de diálogo nativos de Qt ('QFileDialog'). Se encarga
de resolver de forma segura las rutas predeterminadas, validar la existencia de los
elementos en el disco y normalizar las salidas en formato de ruta POSIX.

1.02 Se añade 'select_files' para selección múltiple y se completan
    los docstrings técnicos y notas de mantenibilidad.
1.01 Se reemplazan las importaciones heredadas aprovechando Python 3.14 (la unión
    de tipos nativa (|) y las colecciones estándar minúsculas (tuple)).
"""

__version__ = "1.02"
# ruff: noqa: RUF022
__all__ = [
    "select_file",
    "select_files",
    "select_folder",
    "save_file",
]

# Librerías estándar
import logging
from pathlib import Path

# Librerías de terceros (Qt)
from qtpy.QtWidgets import QFileDialog, QWidget

logger = logging.getLogger(__name__)


def select_file(
    parent: QWidget | None,
    title: str = "Seleccionar archivo",
    file_filter: str = "Todos los archivos (*)",
    initial_path: str | None = None,
    force_dialog: bool = False,
) -> str | None:
    """Muestra diálogo gráfico para seleccionar un único archivo.

    Si se proporciona un 'initial_path' que ya existe en el disco y 'force_dialog' es False,
    la función devuelve directamente dicha ruta sin abrir la interfaz gráfica.

    Args:
        parent: Widget padre de Qt para centrar y gestionar la ventana de diálogo.
        title: Texto de la barra de título de la ventana.
        file_filter: Filtro de extensiones, separar grupos con ';;'.
            Ejemplo: "Imágenes (*.png *.jpg);;Todos (*)"
        initial_path: Ruta de partida para abrir el explorador.
        force_dialog: Si es True, fuerza la apertura de la ventana gráfica
            incluso si 'initial_path' existe (usar True en acciones explícitas de menú).

    Returns:
        Ruta absoluta normalizada en formato POSIX (barras '/'), o None si cancela.
    """
    path_obj, initial_dir = _resolve_paths(initial_path)

    # Si 'force_dialog' es False y la ruta existe, se omite el cuadro de diálogo.
    # Esto se usa para validar rutas guardadas en configuración sin molestar al usuario.
    if force_dialog or not path_obj or not path_obj.exists():
        file_path, _ = QFileDialog.getOpenFileName(
            parent, title, initial_dir, file_filter
        )
        if file_path:
            # .as_posix() fuerza barras '/' incluso en Windows.
            # Esto evita errores de escape '\\' al guardar rutas en SQLite o JSON.
            final_path = Path(file_path).as_posix()
            logger.info(f"El usuario seleccionó un archivo vía diálogo: {final_path}")
            return final_path
        return None

    return path_obj.as_posix()


def select_files(
    parent: QWidget | None,
    title: str = "Seleccionar archivos",
    file_filter: str = "Todos los archivos (*)",
    initial_path: str | None = None,
) -> list[str]:
    """Muestra diálogo gráfico para seleccionar múltiples archivos simultáneamente.

    Args:
        parent: Widget padre de Qt para centrar y gestionar la ventana de diálogo.
        title: Texto de la barra de título de la ventana.
        file_filter: Filtro de extensiones, separar grupos con ';;'.
            Ejemplo: "Imágenes (*.png *.jpg);;Todos (*)"
        initial_path: Ruta de partida para abrir el explorador.

    Returns:
        Lista de rutas absolutas normalizadas en formato POSIX (barras '/').
        Devuelve una lista vacía si el usuario cancela la selección.
    """
    _, initial_dir = _resolve_paths(initial_path)

    # getOpenFileNames (en plural) devuelve una tupla: (lista_rutas, filtro_usado)
    files, _ = QFileDialog.getOpenFileNames(parent, title, initial_dir, file_filter)

    if files:
        final_paths = [Path(f).as_posix() for f in files]
        logger.info(f"El usuario seleccionó {len(final_paths)} archivos vía diálogo.")
        return final_paths

    return []


def select_folder(
    parent: QWidget | None,
    title: str = "Seleccionar carpeta",
    initial_path: str | None = None,
    force_dialog: bool = False,
) -> str | None:
    """Muestra diálogo gráfico para seleccionar un directorio/carpeta.

    Args:
        parent: Widget padre de Qt para centrar y gestionar la ventana de diálogo.
        title: Texto de la barra de título de la ventana.
        initial_path: Ruta de partida para abrir el explorador.
        force_dialog: Si es True, fuerza la apertura de la ventana gráfica
            incluso si 'initial_path' ya es una carpeta válida existente.

    Returns:
        Ruta absoluta del directorio en formato POSIX (barras '/'), o None si cancela.
    """
    path_obj, initial_dir = _resolve_paths(initial_path)

    if force_dialog or not path_obj or not path_obj.exists():
        folder_path = QFileDialog.getExistingDirectory(parent, title, initial_dir)
        if folder_path:
            final_path = Path(folder_path).as_posix()
            logger.info(f"El usuario seleccionó una carpeta vía diálogo: {final_path}")
            return final_path
        return None

    return path_obj.as_posix()


def save_file(
    parent: QWidget | None,
    title: str = "Guardar archivo",
    file_filter: str = "Todos los archivos (*)",
    initial_path: str | None = None,
) -> str | None:
    """Muestra diálogo gráfico para seleccionar la ubicación de guardado de un archivo.

    Args:
        parent: Widget padre de Qt para centrar y gestionar la ventana de diálogo.
        title: Texto de la barra de título de la ventana.
        file_filter: Filtro de extensiones, separar grupos con ';;'.
            Ejemplo: "Imágenes (*.png *.jpg);;Todos (*)"
        initial_path: Ruta de partida para abrir el explorador.

    Returns:
        Ruta de destino seleccionada en formato POSIX (barras '/'), o None si cancela.
    """
    _, initial_dir = _resolve_paths(initial_path)

    # getSaveFileName incluye confirmación nativa al intentar sobrescribir.
    file_path, _ = QFileDialog.getSaveFileName(parent, title, initial_dir, file_filter)
    if file_path:
        final_path = Path(file_path).as_posix()
        logger.info(f"El usuario seleccionó guardar en: {final_path}")
        return final_path
    return None


def _resolve_paths(initial_path: str | None) -> tuple[Path | None, str]:
    """Resuelve la ruta a evaluar y determina la carpeta inicial segura para el diálogo.

    Garantiza que siempre se devuelva un directorio válido para abrir los diálogos,
    retrocediendo al Home del sistema ('Path.home()') si la ruta previa no existe.

    Args:
        initial_path: String o None con la ruta sugerida.

    Returns:
        Tupla con (Path o None de la ruta evaluada, String con la carpeta contenedora válida).
    """
    path_obj = Path(initial_path) if initial_path else None

    if path_obj and path_obj.exists():
        if path_obj.is_dir():
            initial_dir = str(path_obj)
        else:
            initial_dir = str(path_obj.parent)
    else:
        initial_dir = str(Path.home())

    return path_obj, initial_dir
