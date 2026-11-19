"""Operaciones sobre una carpeta entera pedidas desde la barra lateral (sección Carpetas).

Está aparte de 'main_window_controller.py' para no seguir engordándolo. Del menú contextual
de una carpeta o de una ubicación, "Quitar del catálogo..." (como en Lightroom Classic) y
"Mostrar en el Explorador" (el Finder en macOS). «Sincronizar carpeta» y «Quitar archivos
ausentes» los atiende 'controllers/folder_import.py', con «Añadir carpeta».

    CatalogSidebar.remove_folder_requested(ubicación, carpeta, nombre)
        └─► FolderActions: ¿algo en marcha? → cuenta sus archivos y mira qué carpetas se
                han quedado vacías en el disco (segundo plano: 'plan_folder_removal')
                → pregunta → start_removal(remove_folder_from_catalog, ubicación, carpeta,
                               empty_folders=..., trash=move_to_trash)
    CatalogSidebar.reveal_folder_requested(carpeta)
        └─► FolderActions: si existe, la abre en el explorador de archivos del sistema

Lo que hace el trabajo está en 'core/catalog/folder_removal.py': los archivos del disco no
se tocan; las carpetas que se han quedado vacías (sus archivos ya no están), sí, como en
Lightroom Classic, y el aviso lo dice (CAT 3.2; reglas en 'core/catalog/empty_folders.py').
El trabajo lo lanza el controlador principal ('start_removal') con el mismo nombre que
"Eliminar": así se reutilizan su barra de progreso, la escritura previa de lo pendiente y
lo que se hace al terminar (recargar la cuadrícula y la barra lateral, relanzar lo que
esperaba). Si la carpeta quitada era la que se veía, la barra lateral elige su carpeta
padre (ver 'CatalogSidebar._closest_folder').

El controlador principal solo tiene que crearlo, pasándole tres funciones:
    - get_db(): el gestor de la base de datos del catálogo abierto (o None);
    - busy_reason(): por qué ahora no se puede quitar nada (o None);
    - start_removal(trabajo, *args): lanza el trabajo de quitar.

1.2.0 Carpetas vacías (CAT 3.2): el aviso dice qué carpetas se eliminarán también del
      disco (y si su '.arca.json' guarda datos) y el trabajo las borra al terminar.
1.1.0 "Mostrar en el Explorador", movido tal cual desde 'main_window_controller.py'
      (docs/PENDIENTE.md, GEN 15.2).
1.0.1 Autoprueba al día con el texto del aviso («con sus subcarpetas si existen»).
1.0.0 Primera versión: "Quitar del catálogo..." de una carpeta.
"""

__version__ = "1.2.0"
__all__ = ["FolderActions", "confirmation_text"]

# Librerías estándar
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from core.catalog.folder_removal import (
    FolderRemovalPlan,
    plan_folder_removal,
    remove_folder_from_catalog,
)
from ui_helpers.helpers.ui_file_manager import (
    FILE_MANAGER_NAME,
    move_to_trash,
    reveal_in_file_manager,
)
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.sidebars.catalog_sidebar import CatalogSidebar

REMOVE_BUTTON_TEXT = "Quitar del catálogo"
CANCEL_BUTTON_TEXT = "Cancelar"


def confirmation_text(name: str, count: int, plan: FolderRemovalPlan | None = None) -> str:
    """Texto del aviso antes de quitar una carpeta del catálogo.

    Los dos primeros párrafos los redactó el autor. Si hay carpetas que se han quedado
    vacías en el disco ('plan'), se dice que también se eliminarán del disco y si su
    '.arca.json' guarda datos de archivos que ya no están (CAT 3.2).
    """
    if count == 0:
        files = ""
    elif count == 1:
        files = " y su archivo"
    else:
        files = f" y sus {count} archivos"
    paragraphs = [
        f"Se va a quitar del catálogo la carpeta «{name}»{files}, con sus subcarpetas si existen."
    ]
    if plan is not None and plan.deletes_folder:
        paragraphs.append(
            "Los archivos ya no están en el disco: se quitarán del catálogo (y de las "
            "colecciones) y la carpeta también se eliminará del disco."
        )
    else:
        paragraphs.append(
            "Si continúa, los archivos se quitarán del catálogo (y de las colecciones) pero "
            "permanecerán en el disco."
        )
        subfolders = plan.deleted_subfolders if plan is not None else 0
        if subfolders == 1:
            paragraphs.append(
                "1 subcarpeta ya no tiene archivos en el disco: también se eliminará del disco."
            )
        elif subfolders > 1:
            paragraphs.append(
                f"{subfolders} subcarpetas ya no tienen archivos en el disco: también se "
                "eliminarán del disco."
            )
    data = _folder_file_text(plan)
    if data:
        paragraphs.append(data)
    return "\n\n".join(paragraphs)


def _folder_file_text(plan: FolderRemovalPlan | None) -> str:
    """Párrafo sobre los '.arca.json' con datos que irán a la Papelera ('' si no hay)."""
    if plan is None or plan.empty_folders is None or not plan.folder_file_items:
        return ""
    items = plan.folder_file_items
    folder_files = sum(1 for folder in plan.empty_folders.folders if folder.folder_file_items)
    if folder_files == 1:
        what = "Irá a la Papelera el archivo .arca.json, que guarda"
    else:
        what = f"Irán a la Papelera {folder_files} archivos .arca.json, que guardan"
    if items == 1:
        files = "1 archivo que ya no está en el disco. Si ese archivo se movió"
    else:
        files = f"{items} archivos que ya no están en el disco. Si esos archivos se movieron"
    return (
        f"{what} los datos (valoración, palabras clave...) de {files} a otra carpeta, "
        "sus datos se pueden recuperar de la Papelera."
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
        sidebar.reveal_folder_requested.connect(self._on_reveal_folder)

    def _on_reveal_folder(self, folder: str) -> None:
        """Menú de una carpeta > "Mostrar en el Explorador" (el Finder en macOS)."""
        if not Path(folder).is_dir():
            self._message_box.warning(
                f"La carpeta no existe (¿se ha movido, renombrado o borrado?):\n{folder}\n\n"
                "Si se ha borrado fuera de la aplicación, «Sincronizar carpeta» en su carpeta "
                "padre marcará sus archivos como ausentes."
            )
            return
        if not reveal_in_file_manager(folder):
            self._message_box.warning(f"No se pudo abrir {FILE_MANAGER_NAME}:\n{folder}")

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
            plan_folder_removal,
            location_id,
            folder,
            on_result=lambda plan: self._confirm(location_id, folder, name, plan),
            on_error=lambda error: self._message_box.critical(
                f"No se pudieron contar los archivos de la carpeta.\n\nDetalle: {error}"
            ),
        )

    def _confirm(
        self, location_id: int, folder: str, name: str, plan: FolderRemovalPlan
    ) -> None:
        """Pregunta antes de quitar la carpeta y, si se acepta, lanza el trabajo."""
        if self._get_db() is None:
            return  # el catálogo se cerró mientras se contaba
        answer = self._message_box.question(
            confirmation_text(name, plan.count, plan),
            title=REMOVE_BUTTON_TEXT,
            buttons=[REMOVE_BUTTON_TEXT, CANCEL_BUTTON_TEXT],
        )
        if answer != REMOVE_BUTTON_TEXT or self._get_db() is None:
            return
        # Solo las carpetas vacías anunciadas en el aviso (el trabajo las vuelve a mirar)
        disk: dict[str, Any] = {}
        if plan.empty_folders is not None and plan.empty_folders.folders:
            disk = {"empty_folders": plan.empty_folders, "trash": move_to_trash}
        self._start_removal(remove_folder_from_catalog, location_id, folder, **disk)


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

    # 2. Carpetas vacías en el disco (CAT 3.2)
    from core.catalog.empty_folders import EmptyFolder, EmptyFolderPlan

    def plan_for(folder: str, *folders: EmptyFolder) -> FolderRemovalPlan:
        return FolderRemovalPlan(folder, 12, EmptyFolderPlan(Path("."), folders))

    nothing = confirmation_text("Viaje", 12, plan_for("Viaje"))
    assert nothing == confirmation_text("Viaje", 12), nothing  # sin carpetas vacías, igual
    whole = confirmation_text(
        "Viaje", 12, plan_for("Viaje", EmptyFolder("Viaje/sub"), EmptyFolder("Viaje"))
    )
    assert "Los archivos ya no están en el disco" in whole and "permanecerán" not in whole
    assert "la carpeta también se eliminará del disco." in whole and ".arca.json" not in whole
    some = confirmation_text(
        "Viaje", 12, plan_for("Viaje", EmptyFolder("Viaje/a"), EmptyFolder("Viaje/b", (), 1))
    )
    assert "permanecerán en el disco" in some
    assert "2 subcarpetas ya no tienen archivos en el disco" in some, some
    assert "el archivo .arca.json, que guarda los datos" in some
    assert "de 1 archivo que ya no está en el disco. Si ese archivo se movió" in some, some
    data = confirmation_text(
        "Viaje", 12, plan_for("Viaje", EmptyFolder("Viaje/a", (), 2), EmptyFolder("Viaje", (), 1))
    )
    assert "Irán a la Papelera 2 archivos .arca.json, que guardan" in data, data
    assert "de 3 archivos que ya no están en el disco. Si esos archivos se movieron" in data
    print("2. Aviso con carpetas vacías: la carpeta entera, subcarpetas y el .arca.json")
    print(f"\n--- Ejemplo ---\n{some}\n---")
    print("Autoprueba finalizada correctamente.")
