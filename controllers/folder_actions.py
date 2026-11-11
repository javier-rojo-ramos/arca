"""Operaciones sobre una carpeta entera pedidas desde la barra lateral (sección Carpetas).

Está aparte de 'main_window_controller.py' para no seguir engordándolo. De momento,
"Quitar del catálogo..." del menú contextual de una carpeta o de una ubicación (como en
Lightroom Classic):

    CatalogSidebar.remove_folder_requested(ubicación, carpeta, nombre)
        └─► FolderActions: ¿algo en marcha? → cuenta sus archivos (segundo plano)
                → pregunta → start_removal(remove_folder_from_catalog, ubicación, carpeta)

Lo que hace el trabajo está en 'core/catalog/folder_removal.py' (nunca toca el disco). El
trabajo lo lanza el controlador principal ('start_removal') con el mismo nombre que
"Eliminar": así se reutilizan su barra de progreso, la escritura previa de lo pendiente y
lo que se hace al terminar (recargar la cuadrícula y la barra lateral, relanzar lo que
esperaba). Si la carpeta quitada era la que se veía, la barra lateral elige su carpeta
padre (ver 'CatalogSidebar._closest_folder').

El controlador principal solo tiene que crearlo, pasándole tres funciones:
    - get_db(): el gestor de la base de datos del catálogo abierto (o None);
    - busy_reason(): por qué ahora no se puede quitar nada (o None);
    - start_removal(trabajo, *args): lanza el trabajo de quitar.

1.0.1 Autoprueba al día con el texto del aviso («con sus subcarpetas si existen»).
1.0.0 Primera versión: "Quitar del catálogo..." de una carpeta.
"""

__version__ = "1.0.1"
__all__ = ["FolderActions", "confirmation_text"]

# Librerías estándar
from collections.abc import Callable
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from core.catalog.folder_removal import count_folder_items, remove_folder_from_catalog
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.sidebars.catalog_sidebar import CatalogSidebar

REMOVE_BUTTON_TEXT = "Quitar del catálogo"
CANCEL_BUTTON_TEXT = "Cancelar"


def confirmation_text(name: str, count: int) -> str:
    """Texto del aviso antes de quitar una carpeta del catálogo (redactado por el autor)."""
    if count == 0:
        files = ""
    elif count == 1:
        files = " y su archivo"
    else:
        files = f" y sus {count} archivos"
    return (
        f"Se va a quitar del catálogo la carpeta «{name}»{files}, con sus subcarpetas si existen.\n\n"
        "Si continúa, los archivos se quitarán del catálogo (y de las colecciones) pero "
        "permanecerán en el disco."
    )


class FolderActions(QObject):
    """Atiende "Quitar del catálogo..." del menú de las carpetas de la barra lateral."""

    def __init__(
        self,
        window: QWidget,
        sidebar: CatalogSidebar,
        message_box: MessageBoxHelper,
        *,
        get_db: Callable[[], Any],
        busy_reason: Callable[[], str | None],
        start_removal: Callable[..., None],
    ) -> None:
        """Conecta la señal de la barra lateral.

        Args:
            window: Ventana principal (padre de este objeto).
            sidebar: Barra lateral del catálogo.
            message_box: Ayudante de mensajes de la ventana.
            get_db: Devuelve el gestor de la base de datos del catálogo abierto, o None.
            busy_reason: Devuelve por qué ahora no se puede quitar nada, o None.
            start_removal: Lanza el trabajo de quitar ('start_removal(trabajo, *args)').
        """
        super().__init__(window)
        self._message_box = message_box
        self._get_db = get_db
        self._busy_reason = busy_reason
        self._start_removal = start_removal
        sidebar.remove_folder_requested.connect(self._on_remove_folder_requested)

    def _on_remove_folder_requested(
        self, location_id: int, folder: str, name: str
    ) -> None:
        """Menú de una carpeta > "Quitar del catálogo...": comprueba, cuenta y pregunta."""
        db = self._get_db()
        if db is None:
            return
        busy = self._busy_reason()
        if busy:
            self._message_box.info(
                f"{busy}\n\nEspera a que termine para quitar carpetas del catálogo."
            )
            return
        db.execute_async(
            count_folder_items,
            location_id,
            folder,
            on_result=lambda count: self._confirm(location_id, folder, name, count),
            on_error=lambda error: self._message_box.critical(
                f"No se pudieron contar los archivos de la carpeta.\n\nDetalle: {error}"
            ),
        )

    def _confirm(self, location_id: int, folder: str, name: str, count: int) -> None:
        """Pregunta antes de quitar la carpeta y, si se acepta, lanza el trabajo."""
        if self._get_db() is None:
            return  # el catálogo se cerró mientras se contaba
        answer = self._message_box.question(
            confirmation_text(name, count),
            title=REMOVE_BUTTON_TEXT,
            buttons=[REMOVE_BUTTON_TEXT, CANCEL_BUTTON_TEXT],
        )
        if answer == REMOVE_BUTTON_TEXT and self._get_db() is not None:
            self._start_removal(remove_folder_from_catalog, location_id, folder)


if __name__ == "__main__":
    # Autoprueba sin ventanas: solo el texto del aviso.
    # Ejecutar desde la raíz del proyecto:  python -m controllers.folder_actions
    assert confirmation_text("Viaje", 12) == (
        "Se va a quitar del catálogo la carpeta «Viaje» y sus 12 archivos, con sus "
        "subcarpetas si existen.\n\nSi continúa, los archivos se quitarán del catálogo (y de "
        "las colecciones) pero permanecerán en el disco."
    ), confirmation_text("Viaje", 12)
    assert "«Viaje» y su archivo," in confirmation_text("Viaje", 1)
    assert "«Viaje», con sus" in confirmation_text("Viaje", 0)
    print("1. Texto del aviso (0, 1 y varios archivos)")
    print("Autoprueba finalizada correctamente.")
