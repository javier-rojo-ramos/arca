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
    7. cerrar.

Falla si algo no llega a tiempo, si sale un aviso de error («critical») o si una excepción
llega a 'sys.excepthook' (en la aplicación, una excepción en un slot de Qt solo se apunta en
el registro). Los cuadros de mensaje no se abren: se apuntan y se responde lo primero.

Es la comprobación de fondo de las refactorizaciones del controlador (docs/PENDIENTE.md,
GEN 15): se lanza antes y después, además de 'run_selftests.py'. Usa partes internas de la
ventana ('folder_import.start', 'remove_actions.request_remove') y sustituye
'MessageBoxHelper' en el módulo del controlador y 'RemoveDialog' en el de
'remove_actions.py': si una refactorización los mueve a otro módulo, hay que
cambiar aquí dónde se sustituyen.

Nunca toca los datos del autor: antes de crear la ventana comprueba que 'settings.json' está
dentro de la carpeta temporal (si no, se detiene). La carpeta se borra al terminar.

Uso (desde la raíz del proyecto, con el Python de .venv; necesita ExifTool para el paso 3):
    python scripts/smoke_main_window.py              # unos 5 segundos
    python scripts/smoke_main_window.py --conservar  # no borra la carpeta temporal

Termina con código 0 si todo va bien y 1 si algo falla.

1.1.0 Paso nuevo: sincronizar con una foto borrada fuera (resumen y quitar la ausente).
1.0.2 Eliminar con 'remove_actions' y su ventana sustituida en ese módulo (GEN 15.3).
1.0.1 Añadir la carpeta con 'folder_import' (GEN 15.2: ya no está en la ventana).
1.0.0 Primera versión (18/11/2026), con GEN 15.1.
"""

__version__ = "1.1.0"
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
    from controllers import remove_actions
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

    class CatalogOnlyRemoveDialog:
        """La ventana «Eliminar», respondiendo siempre «Eliminar del catálogo»."""

        @staticmethod
        def ask(_parent: object, _plan: object) -> bool:
            return False

    mwc.MessageBoxHelper = QuietMessageBox  # la ventana crea el suyo con esta clase
    remove_actions.RemoveDialog = CatalogOnlyRemoveDialog  # (antes de crear la ventana)

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

    # 7. Cerrar
    window.close()
    app.processEvents()
    if jobs.is_attached:
        raise SmokeError("Al cerrar, el coordinador sigue con el catálogo")
    errors = [text for kind, text in shown if kind == "critical"]
    if errors or exceptions:
        raise SmokeError(f"Errores: {errors or exceptions}")
    print(f"7. Cerrar (mensajes apuntados, sin abrirse: {[kind for kind, _ in shown]})")
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
    finally:
        if args.conservar:
            print(f"Carpeta de la prueba: {work_dir}")
        else:
            shutil.rmtree(work_dir, ignore_errors=True)
    print("Comprobación finalizada correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
