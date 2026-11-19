"""Prueba de humo de la ventana principal, de verdad pero fuera de pantalla y sin tocar nada.

Las autopruebas no cubren 'main_window_controller.py' (abre ventanas). Esta prueba crea la
ventana principal de verdad con la plataforma 'offscreen' de Qt (no se ve nada), con la
configuración (settings.json) desviada a una carpeta temporal y un catálogo de prueba con
unas fotos inventadas, y recorre lo que conecta el controlador:

    1. abrir el catálogo;
    2. añadir una carpeta: recorrido -> lectura de metadatos -> miniaturas (y la cuadrícula);
    3. valorar una foto: se guarda y, tras la espera, se escribe en su XMP (con ExifTool);
    4. regenerar miniaturas;
    5. eliminar una foto del catálogo (la ventana de eliminar responde «del catálogo»);
    6. borrar otra del disco y sincronizar la carpeta: el resumen ofrece quitarla y se quita
       (y la eliminada en el paso 5, que sigue en el disco, vuelve a entrar);
    7. quitar del catálogo una subcarpeta cuya foto se borró fuera (CAT 3.2): el aviso dice
       que la carpeta se eliminará del disco y se elimina (lo que sobra, a una papelera
       simulada, nunca a la del sistema);
    8. «Eliminar del disco» la única foto de otra subcarpeta (CAT 3.3): la foto, a la
       papelera simulada, y la carpeta, eliminada;
    9. «Cambiar nombre...» de una foto (CAT 4.2; la ventana responde sola): el archivo en
       el disco y su ruta y su título en el catálogo;
    10. «Cambiar nombre...» de una subcarpeta elegida en la barra (CAT 4.3): la carpeta en el
       disco, las rutas en el catálogo y la barra y la cuadrícula con el nombre nuevo;
    11. soltar esa foto sobre la raíz de la ubicación (CAT 4.4b; la confirmación responde
       «Mover»): la foto, movida, y sus carpetas, que se quedan vacías, eliminadas;
    12. «Nueva carpeta...» en la raíz con la foto elegida en la cuadrícula (CAT 4.4a; la
       ventana responde sola): la carpeta, creada, con la foto dentro;
    13. cerrar.

Falla si algo no llega a tiempo, si sale un aviso de error («critical») o si una excepción
llega a 'sys.excepthook' (en la aplicación, una excepción en un slot de Qt solo se apunta en
el registro). Los cuadros de mensaje no se abren: se apuntan y se responde lo primero.

Es la comprobación de fondo de las refactorizaciones del controlador (docs/PENDIENTE.md,
GEN 15): se lanza antes y después, además de 'run_selftests.py'. Usa partes internas de la
ventana ('folder_import.start', 'remove_actions.request_remove') y sustituye
'MessageBoxHelper' en el módulo del controlador, 'RemoveDialog' y 'move_to_trash' en el de
'remove_actions.py', 'move_to_trash' en el de 'folder_actions.py' y 'RenameDialog' y
'move_to_trash' y 'NewFolderDialog' en el de 'file_actions.py': si una refactorización los
mueve a otro módulo, hay que cambiar aquí dónde se sustituyen.

Nunca toca los datos del autor: antes de crear la ventana comprueba que 'settings.json' está
dentro de la carpeta temporal (si no, se detiene). La carpeta se borra al terminar.

Uso (desde la raíz del proyecto, con el Python de .venv; necesita ExifTool para el paso 3):
    python scripts/smoke_main_window.py              # unos 5 segundos
    python scripts/smoke_main_window.py --conservar  # no borra la carpeta temporal

Termina con código 0 si todo va bien y 1 si algo falla.

1.7.0 Paso nuevo: «Nueva carpeta...» con la foto elegida (CAT 4.4a), con su ventana
      sustituida.
1.6.0 Paso nuevo: soltar una foto sobre una carpeta del árbol para moverla (CAT 4.4b).
1.5.1 Un error que no es de la prueba (p. ej. al crear la ventana) se enseña entero: antes
      terminaba con el código 1 sin decir nada.
1.5.0 Paso nuevo: «Cambiar nombre...» de una carpeta elegida (CAT 4.3).
1.4.0 Paso nuevo: «Cambiar nombre...» de una foto (CAT 4.2), con su ventana sustituida.
1.3.0 Paso nuevo: «Eliminar del disco» la única foto de una carpeta (CAT 3.3), con la
      papelera de 'remove_actions' también simulada.
1.2.0 Paso nuevo: quitar del catálogo una carpeta vacía en el disco (CAT 3.2), con la
      papelera de 'folder_actions' sustituida por una simulada.
1.1.0 Paso nuevo: sincronizar con una foto borrada fuera (resumen y quitar la ausente).
1.0.2 Eliminar con 'remove_actions' y su ventana sustituida en ese módulo (GEN 15.3).
1.0.1 Añadir la carpeta con 'folder_import' (GEN 15.2: ya no está en la ventana).
1.0.0 Primera versión (18/11/2026), con GEN 15.1.
"""

__version__ = "1.7.0"
__all__ = ["main", "run"]

# Librerías estándar
import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Raíz del proyecto (este archivo está en 'scripts/')
ROOT = Path(__file__).resolve().parent.parent

# Fotos inventadas de la biblioteca de prueba
PHOTO_COUNT = 30

# Tiempos máximos (s) de cada espera
TIMEOUT_ADD_FOLDER = 60
TIMEOUT_JOBS = 120
TIMEOUT_SHORT = 30


class SmokeError(AssertionError):
    """Un paso de la prueba no ha salido como debía."""


def _redirect_user_dirs(base: Path) -> None:
    """Desvía las carpetas de configuración del usuario a 'base' (ANTES de importar 'config').

    Windows usa LOCALAPPDATA; Linux, XDG_CONFIG_HOME y XDG_STATE_HOME; macOS, la carpeta
    personal (HOME). Ver 'config/app_paths.py' y 'config/app_logging_manager.py'.
    """
    os.environ["LOCALAPPDATA"] = str(base / "local")
    os.environ["XDG_CONFIG_HOME"] = str(base / "config")
    os.environ["XDG_STATE_HOME"] = str(base / "state")
    if sys.platform == "darwin":
        os.environ["HOME"] = str(base / "home")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"  # nada se dibuja en pantalla


def run(work_dir: Path) -> None:
    """Hace la prueba en 'work_dir' (vacía). Lanza 'SmokeError' si algo falla."""
    _redirect_user_dirs(work_dir)
    sys.path.insert(0, str(ROOT))

    # Importaciones aquí, y no arriba: tienen que ir DESPUÉS de desviar las carpetas del
    # usuario ('config' calcula la ruta de settings.json al importarse)
    # Librerías de terceros
    from loguru import logger
    from PIL import Image

    # Librerías de terceros (Qt)
    from qtpy.QtWidgets import QApplication

    # Módulos del proyecto
    from ui_helpers.map.map_scheme import register_map_scheme

    logger.remove()  # solo los avisos y errores, para que se lea el resultado
    logger.add(sys.stderr, level="WARNING")

    register_map_scheme()  # como 'main.py': antes de crear QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    from config import app_paths
    from ui_helpers.helpers.ui_theme import apply_theme

    apply_theme()
    if work_dir not in Path(app_paths.CONFIG_FILE).parents:
        raise SmokeError(f"settings.json no quedó en la carpeta temporal: {app_paths.CONFIG_FILE}")

    import controllers.main_window_controller as mwc
    from controllers import file_actions, folder_actions, remove_actions
    from core.catalog.catalog_builder import CatalogBuilder
    from core.metadata.exiftool_runner import ExifToolRunner

    # --- Lo que no debe abrirse ni pasar en silencio ---------------------------------
    shown: list[tuple[str, str]] = []
    exceptions: list[str] = []
    sys.excepthook = lambda kind, value, tb: exceptions.append(
        "".join(traceback.format_exception(kind, value, tb))
    )

    class QuietMessageBox:
        """'MessageBoxHelper' que apunta los mensajes y responde el primer botón."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def info(self, text: str, **_kwargs: object) -> None:
            shown.append(("info", text))

        def warning(self, text: str, **_kwargs: object) -> None:
            shown.append(("warning", text))

        def critical(self, text: str, **_kwargs: object) -> None:
            shown.append(("critical", text))

        def question(self, text: str, buttons: list[str] | None = None, **_kwargs: object) -> Any:
            shown.append(("question", text))
            return buttons[0] if buttons else None

    remove_answer = {"to_trash": False}  # lo que responde la ventana «Eliminar»

    class CatalogOnlyRemoveDialog:
        """La ventana «Eliminar»: «Eliminar del catálogo», salvo que se pida el disco."""

        @staticmethod
        def ask(_parent: object, _plan: object) -> bool:
            return remove_answer["to_trash"]

    trash_dir = work_dir / "Papelera"
    trash_dir.mkdir()
    trashed: list[str] = []

    def fake_trash(path: Path) -> None:
        """Papelera simulada: la de verdad es la del usuario y no se toca."""
        path.replace(trash_dir / f"{len(trashed)}_{path.name}")
        trashed.append(path.name)

    mwc.MessageBoxHelper = QuietMessageBox  # la ventana crea el suyo con esta clase
    remove_actions.RemoveDialog = CatalogOnlyRemoveDialog  # (antes de crear la ventana)
    remove_actions.move_to_trash = fake_trash
    folder_actions.move_to_trash = fake_trash

    class AnsweringRenameDialog:
        """La ventana «Cambiar nombre»: «Renombrada» a un archivo y «Carpeta nueva» a una carpeta."""

        @staticmethod
        def ask(
            _parent: object, _file_name: str, _initial: str | None = None, **kwargs: object
        ) -> str:
            return "Carpeta nueva" if kwargs.get("folder_files") is not None else "Renombrada"

    file_actions.RenameDialog = AnsweringRenameDialog
    file_actions.move_to_trash = fake_trash

    class AnsweringNewFolderDialog:
        """La ventana «Nueva carpeta», que responde «Seleccion» (lo elegido va dentro)."""

        @staticmethod
        def ask(*_args: object, **_kwargs: object) -> str:
            return "Seleccion"

    file_actions.NewFolderDialog = AnsweringNewFolderDialog

    def run_until(condition: Callable[[], bool], seconds: float, label: str) -> None:
        """Deja correr el bucle de eventos hasta que se cumpla 'condition'."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if exceptions:
                raise SmokeError(f"Excepción en la aplicación ({label}):\n{exceptions[0]}")
            if condition():
                return
            time.sleep(0.02)
        raise SmokeError(f"Tiempo agotado: {label}")

    def query(sql: str) -> list[tuple]:
        """Una consulta al catálogo de prueba, en solo lectura."""
        uri = f"file:{window.catalog_dir / CatalogBuilder.DB_FILENAME}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    # --- Biblioteca y catálogo de prueba ---------------------------------------------
    library = work_dir / "Biblioteca"
    library.mkdir()
    for number in range(PHOTO_COUNT):
        Image.new("RGB", (64, 48), (number * 8 % 256, 90, 160)).save(
            library / f"foto_{number:02d}.jpg"
        )
    catalog_dir = work_dir / "Catalogo"
    CatalogBuilder(catalog_dir).build()

    window = mwc.MainWindowController()
    window.iniciar()
    # 'iniciar' deja para la primera vuelta del bucle «reabrir el último catálogo» (aquí no
    # hay ninguno): que pase antes de abrir el de prueba, o lo cerraría a mitad
    for _ in range(5):
        app.processEvents()
    jobs = window.job_coordinator

    def idle() -> bool:
        return not window.folder_import.is_running and jobs.busy_reason() is None

    # 1. Abrir el catálogo
    if not window._open_catalog(catalog_dir) or not jobs.is_attached:
        raise SmokeError("No se abrió el catálogo de prueba")
    print("1. Catálogo abierto")

    # 2. Añadir la carpeta: recorrido -> lectura -> miniaturas (-> escritura: nada pendiente)
    window.folder_import.start(str(library), sync=False, content="auto")
    run_until(
        lambda: not window.folder_import.is_running, TIMEOUT_ADD_FOLDER, "añadir la carpeta"
    )
    run_until(idle, TIMEOUT_JOBS, "lectura de metadatos y miniaturas")
    run_until(
        lambda: window.mosaico_model.rowCount() == PHOTO_COUNT, TIMEOUT_SHORT, "cuadrícula llena"
    )
    read, thumbnails = query(
        "SELECT SUM(last_scanned_at IS NOT NULL), SUM(thumbnail_status = 1) FROM media_items"
    )[0]
    if (read, thumbnails) != (PHOTO_COUNT, PHOTO_COUNT):
        raise SmokeError(f"Leídas {read} y con miniatura {thumbnails} de {PHOTO_COUNT}")
    print(f"2. Añadir carpeta: {read} leídas, {thumbnails} miniaturas, cuadrícula con {PHOTO_COUNT}")

    # 3. Valorar una foto: se guarda y, tras la espera, se escribe en su XMP
    window.mosaico_model.set_field("rating", 4, [0])
    first_id = window.mosaico_model.media_ids_in_rows(0, 0)[0]
    run_until(
        lambda: query(f"SELECT rating, user_data_pending FROM media_items WHERE id = {first_id}")
        == [(4, 0)],
        TIMEOUT_SHORT,
        "guardar y escribir la valoración",
    )
    run_until(idle, TIMEOUT_SHORT, "fin de la escritura")
    (name,) = query(f"SELECT relative_path FROM media_items WHERE id = {first_id}")[0]
    tags = ExifToolRunner().read([library / name], tags=("-XMP-xmp:Rating",))[library / name].tags
    if tags.get("XMP-xmp:Rating") != 4:
        raise SmokeError(f"La valoración no está en el archivo: {tags}")
    print(f"3. Valoración: guardada y escrita en {name}")

    # 4. Regenerar las miniaturas de dos fotos
    jobs.regenerate_thumbnails(window.mosaico_model.media_ids_in_rows(1, 2))
    run_until(lambda: jobs.busy_reason() is not None, TIMEOUT_SHORT, "lanzar la regeneración")
    run_until(idle, TIMEOUT_JOBS, "regenerar miniaturas")
    (ready,) = query("SELECT COUNT(*) FROM media_items WHERE thumbnail_status = 1")[0]
    if ready != PHOTO_COUNT:
        raise SmokeError(f"Tras regenerar, {ready} miniaturas de {PHOTO_COUNT}")
    print("4. Regenerar miniaturas")

    # 5. Eliminar una foto del catálogo
    victim = window.mosaico_model.media_ids_in_rows(5, 5)[0]
    window.remove_actions.request_remove([victim])
    run_until(
        lambda: not query(f"SELECT 1 FROM media_items WHERE id = {victim}"),
        TIMEOUT_SHORT,
        "eliminar del catálogo",
    )
    run_until(idle, TIMEOUT_SHORT, "fin de eliminar")
    run_until(
        lambda: window.mosaico_model.rowCount() == PHOTO_COUNT - 1,
        TIMEOUT_SHORT,
        "cuadrícula sin la eliminada",
    )
    print("5. Eliminar del catálogo")

    # 6. Sincronizar la carpeta tras borrar una foto fuera de la aplicación: el resumen
    #    ofrece quitar la ausente (se responde «Quitar del catálogo», el primer botón). La
    #    eliminada en el paso 5 sigue en el disco: al sincronizar, vuelve a entrar
    (gone,) = query(
        f"SELECT relative_path FROM media_items WHERE id != {first_id} ORDER BY id DESC LIMIT 1"
    )[0]
    (library / gone).unlink()
    questions_before = sum(kind == "question" for kind, _ in shown)
    window.folder_import.request_sync(str(library))
    run_until(
        lambda: not query(f"SELECT 1 FROM media_items WHERE relative_path = '{gone}'"),
        TIMEOUT_ADD_FOLDER,
        "sincronizar y quitar la ausente",
    )
    run_until(idle, TIMEOUT_JOBS, "fin de sincronizar")
    if sum(kind == "question" for kind, _ in shown) != questions_before + 1:
        raise SmokeError("Al sincronizar, el resumen no ofreció quitar la foto ausente")
    (total, missing) = query("SELECT COUNT(*), SUM(is_missing) FROM media_items")[0]
    if (total, missing) != (PHOTO_COUNT - 1, 0):  # la eliminada vuelve; la borrada, no
        raise SmokeError(f"Tras sincronizar: {total} elementos y {missing} ausentes")
    run_until(
        lambda: window.mosaico_model.rowCount() == PHOTO_COUNT - 1,
        TIMEOUT_SHORT,
        "cuadrícula tras sincronizar",
    )
    print(f"6. Sincronizar: {gone} (borrada fuera), quitada; la eliminada en 5 vuelve a entrar")

    # 7. Quitar del catálogo una subcarpeta cuya foto se borró fuera de la aplicación: se
    #    elimina también del disco (su 'Thumbs.db', a la papelera simulada)
    empty = library / "Vacia"
    empty.mkdir()
    Image.new("RGB", (64, 48), (200, 90, 40)).save(empty / "suelta.jpg")
    alone = library / "Sola"  # para el paso 8
    alone.mkdir()
    Image.new("RGB", (64, 48), (40, 200, 90)).save(alone / "unica.jpg")
    trip = library / "Viaje" / "Dia 1"  # para el paso 10
    trip.mkdir(parents=True)
    Image.new("RGB", (64, 48), (90, 40, 200)).save(trip / "playa.jpg")
    window.folder_import.request_sync(str(library))
    run_until(
        lambda: query("SELECT 1 FROM media_items WHERE relative_path = 'Vacia/suelta.jpg'"),
        TIMEOUT_ADD_FOLDER,
        "sincronizar con la subcarpeta nueva",
    )
    run_until(idle, TIMEOUT_JOBS, "fin de sincronizar la subcarpeta")
    (empty / "suelta.jpg").unlink()  # borrada fuera: la carpeta se queda vacía en el disco
    (empty / "Thumbs.db").write_bytes(b"x")
    ((location_id,),) = query("SELECT id FROM storage_locations")
    questions_before = sum(kind == "question" for kind, _ in shown)
    window.widget_catalog_sidebar.remove_folder_requested.emit(location_id, "Vacia", "Vacia")
    run_until(lambda: not empty.exists(), TIMEOUT_SHORT, "quitar la carpeta vacía")
    run_until(idle, TIMEOUT_SHORT, "fin de quitar la carpeta")
    asked = [text for kind, text in shown if kind == "question"][questions_before:]
    if len(asked) != 1 or "la carpeta también se eliminará del disco" not in asked[0]:
        raise SmokeError(f"El aviso no anunció que la carpeta se elimina del disco: {asked}")
    if query("SELECT 1 FROM media_items WHERE relative_path LIKE 'Vacia/%'"):
        raise SmokeError("La carpeta vacía sigue en el catálogo")
    if trashed != ["Thumbs.db"]:
        raise SmokeError(f"A la papelera simulada fue {trashed}, en lugar de 'Thumbs.db'")
    print("7. Quitar una carpeta vacía en el disco: del catálogo y del disco")

    # 8. «Eliminar del disco» la única foto de una subcarpeta: la foto va a la papelera
    #    simulada y la carpeta, que se queda vacía, se elimina
    ((alone_id,),) = query("SELECT id FROM media_items WHERE relative_path = 'Sola/unica.jpg'")
    remove_answer["to_trash"] = True
    window.remove_actions.request_remove([alone_id])
    run_until(lambda: not alone.exists(), TIMEOUT_SHORT, "eliminar del disco y la carpeta vacía")
    run_until(idle, TIMEOUT_SHORT, "fin de eliminar del disco")
    remove_answer["to_trash"] = False
    if query(f"SELECT 1 FROM media_items WHERE id = {alone_id}"):
        raise SmokeError("La foto eliminada del disco sigue en el catálogo")
    if trashed != ["Thumbs.db", "unica.jpg"]:
        raise SmokeError(f"A la papelera simulada fue {trashed}")
    print("8. Eliminar del disco la única foto de una carpeta: la foto y la carpeta")

    # 9. «Cambiar nombre...» de una foto: en el disco y en el catálogo (ruta y título)
    ((renamed_id, old_name),) = query(
        "SELECT id, relative_path FROM media_items WHERE relative_path = 'foto_01.jpg'"
    )
    window.file_actions.request_rename([renamed_id])
    run_until(
        lambda: (library / "Renombrada.jpg").exists(), TIMEOUT_SHORT, "cambiar el nombre en el disco"
    )
    run_until(idle, TIMEOUT_SHORT, "fin de cambiar el nombre")
    row = query(f"SELECT relative_path, title FROM media_items WHERE id = {renamed_id}")
    if row != [("Renombrada.jpg", "Renombrada")] or (library / old_name).exists():
        raise SmokeError(f"Tras cambiar el nombre: {row}")
    if query("SELECT COUNT(*) FROM file_operations") != [(0,)]:
        raise SmokeError("El registro de operaciones no quedó vacío")
    print(f"9. Cambiar nombre: {old_name} → Renombrada.jpg (disco y catálogo)")

    # 10. «Cambiar nombre...» de la carpeta «Viaje», con su subcarpeta elegida en la barra:
    #     la carpeta en el disco, las rutas en el catálogo y lo elegido, con el nombre nuevo
    sidebar = window.widget_catalog_sidebar
    # (partes internas de la barra: el origen tal como lo hace ella y sus filas de carpetas)
    chosen = sidebar._source_for(location_id, "Viaje/Dia 1")
    run_until(
        lambda: chosen in sidebar._folder_items, TIMEOUT_SHORT, "la subcarpeta en la barra"
    )
    sidebar.select_source(chosen)
    run_until(
        lambda: window.mosaico_model.rowCount() == 1, TIMEOUT_SHORT, "la subcarpeta elegida"
    )
    sidebar.rename_folder_requested.emit(location_id, "Viaje", "Viaje")
    run_until(lambda: (library / "Carpeta nueva").is_dir(), TIMEOUT_SHORT, "renombrar la carpeta")
    run_until(idle, TIMEOUT_SHORT, "fin de renombrar la carpeta")
    if query("SELECT relative_path FROM media_items WHERE relative_path LIKE 'Viaje/%'"):
        raise SmokeError("Quedan rutas con el nombre viejo de la carpeta")
    if query("SELECT 1 FROM media_items WHERE relative_path = 'Carpeta nueva/Dia 1/playa.jpg'") != [
        (1,)
    ]:
        raise SmokeError("La foto de la carpeta no tiene la ruta nueva")
    now = sidebar.current_source()
    if now.folder != "Carpeta nueva/Dia 1" or window.mosaico_model.source.folder != now.folder:
        raise SmokeError(f"Lo elegido no siguió a la carpeta: {now}, {window.mosaico_model.source}")
    run_until(
        lambda: window.mosaico_model.rowCount() == 1, TIMEOUT_SHORT, "la cuadrícula, con su foto"
    )
    print("10. Cambiar nombre de una carpeta: disco, catálogo y lo elegido en la barra")

    # 11. Soltar esa foto sobre la raíz de la ubicación: se mueve, y «Carpeta nueva» y su
    #     subcarpeta, que se quedan vacías, se eliminan (la confirmación responde «Mover»)
    from ui_helpers.models.media_mime import MediaDrag

    ((beach_id,),) = query(
        "SELECT id FROM media_items WHERE relative_path = 'Carpeta nueva/Dia 1/playa.jpg'"
    )
    questions_before = sum(kind == "question" for kind, _ in shown)
    drag = MediaDrag(str(window.catalog_dir), (beach_id,))
    sidebar.media_dropped_on_folder.emit(location_id, "", "Biblioteca", drag)
    run_until(lambda: (library / "playa.jpg").exists(), TIMEOUT_SHORT, "mover la foto")
    run_until(idle, TIMEOUT_SHORT, "fin de mover")
    asked = [text for kind, text in shown if kind == "question"][questions_before:]
    if len(asked) != 1 or "se quedará vacía y también se eliminará del disco" not in asked[0]:
        raise SmokeError(f"La confirmación no anunció la carpeta que se vacía: {asked}")
    if query(f"SELECT relative_path FROM media_items WHERE id = {beach_id}") != [("playa.jpg",)]:
        raise SmokeError("La foto movida no tiene la ruta nueva en el catálogo")
    if (library / "Carpeta nueva").exists():
        raise SmokeError("La carpeta que se quedó vacía sigue en el disco")
    print("11. Soltar una foto en una carpeta: movida; su carpeta, vacía, eliminada")

    # 12. «Nueva carpeta...» en la raíz de la ubicación, con la primera tarjeta elegida
    view = window.grid_actions._view  # (parte interna: la vista de la cuadrícula)
    run_until(lambda: window.mosaico_model.rowCount() > 0, TIMEOUT_SHORT, "la cuadrícula")
    view.setCurrentIndex(window.mosaico_model.index(0, 0))
    (picked,) = window.grid_actions.selected_ids()
    ((picked_name,),) = query(f"SELECT file_name FROM media_items WHERE id = {picked}")
    sidebar.new_folder_requested.emit(location_id, "", "Biblioteca")
    run_until(
        lambda: (library / "Seleccion" / picked_name).exists(), TIMEOUT_SHORT, "la carpeta nueva"
    )
    run_until(idle, TIMEOUT_SHORT, "fin de crear la carpeta")
    expected = [(f"Seleccion/{picked_name}",)]
    if query(f"SELECT relative_path FROM media_items WHERE id = {picked}") != expected:
        raise SmokeError("La foto de la carpeta nueva no tiene la ruta nueva en el catálogo")
    print(f"12. Nueva carpeta «Seleccion» con {picked_name} dentro")

    # 13. Cerrar
    window.close()
    app.processEvents()
    if jobs.is_attached:
        raise SmokeError("Al cerrar, el coordinador sigue con el catálogo")
    errors = [text for kind, text in shown if kind == "critical"]
    if errors or exceptions:
        raise SmokeError(f"Errores: {errors or exceptions}")
    print(f"13. Cerrar (mensajes apuntados, sin abrirse: {[kind for kind, _ in shown]})")
    window.deleteLater()
    app.processEvents()


def main(argv: list[str] | None = None) -> int:
    """Lanza la prueba en una carpeta temporal. Devuelve el código de salida."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--conservar", action="store_true", help="no borrar la carpeta temporal al terminar"
    )
    args = parser.parse_args(argv)

    work_dir = Path(tempfile.mkdtemp(prefix="arca_humo_")).resolve()
    try:
        run(work_dir)
    except SmokeError as error:
        print(f"FALLO: {error}")
        return 1
    except Exception:  # noqa: BLE001 - un error que no es de la prueba: se enseña entero
        # (la prueba sustituye 'sys.excepthook': sin esto, el error no se vería)
        print("FALLO: error inesperado")
        traceback.print_exc(file=sys.__stderr__)
        return 1
    finally:
        if args.conservar:
            print(f"Carpeta de la prueba: {work_dir}")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)
    print("Comprobación finalizada correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
