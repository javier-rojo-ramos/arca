"""Base de los módulos de UNA biblioteca con la barra 'LibrarySidebar' (Tracks; Vídeo y Audio).

Lo común de esos módulos, que antes estaba en 'TracksModule' (15/11/2026): la barra
izquierda («Biblioteca - …» con sus dos filas fijas, «Carpetas» y «Fechas»), lo que se lee
para ella en segundo plano, lo guardado de la barra por catálogo y el menú de las
carpetas. Lo de cada módulo (su biblioteca y sus textos, sus vistas, su orden y sus
filtros) lo pone su subclase.

Qué hace (la barra no sabe nada de la base de datos), como 'ImageModule':
    - Pasa al 'ModuleHost' lo que se elige en la barra ('source_selected').
    - 'refresh' lee en segundo plano los contadores de la biblioteca, el árbol de carpetas
      con archivos suyos y los años, meses y días ('timeline.fetch_timeline').
    - Si la carpeta o la fecha elegida ya no existe (se borró, o ya no tiene nada de la
      biblioteca), vuelve a la primera fila («Todos los …»).
    - Lo desplegado y la fila elegida, guardados por catálogo ('save_state' /
      'restore_state'; el 'ModuleHost' los escribe en settings.json).

Uso (una subclase por módulo):
    class TracksModule(LibraryModule):
        key, title, icon = MODE_TRACKS, "Tracks", AppIcons.LIB_TRACKS
        library = Library.TRACKS.value
        texts = LibraryTexts("Biblioteca - Tracks", "Todos los tracks", ...)
        def views(self): ...          # y el orden, los filtros, el mapa...

1.0.0 Primera versión (15/11/2026): sale de 'TracksModule' (sin cambiar lo que hace),
      para servir también a Vídeo y Audio.

Prueba rápida (desde la raíz del proyecto; sin ventana, con un catálogo en memoria):
    python -m controllers.app_modules.library_module
"""

__version__ = "1.0.0"
__all__ = ["LibraryModule", "fetch_library_sidebar_data"]

# Librerías estándar
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QToolButton, QWidget

# Módulos del proyecto
from config.app_constants import SETTING_SHOW_SUBFOLDER_ITEMS
from controllers.app_modules.base import AppModule, ModuleContext
from core.catalog.folder_tree import fetch_folder_tree
from core.catalog.grid_source import GridSource, library_source, quick_source
from core.catalog.media_queries import count_grid_items
from core.catalog.timeline import fetch_timeline
from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME, reveal_in_file_manager
from ui_helpers.sidebars.library_sidebar import LibrarySidebar, LibraryTexts


def fetch_library_sidebar_data(conn: Any, library: str) -> tuple[int, int, tuple, tuple]:
    """Lo que necesita la barra de una biblioteca: cuántos archivos tiene y cuántos de su
    selección rápida, el árbol de carpetas (solo con archivos suyos) y los años con sus
    meses y días.

    Una sola función (una sola visita al hilo de la base de datos) para que todo llegue a
    la vez (así se sabe si la carpeta o la fecha elegida sigue existiendo).
    """
    everything, quick = library_source(library), quick_source(library)
    counts = count_grid_items(conn, [everything, quick])
    return (
        counts.get(everything, 0),
        counts.get(quick, 0),
        fetch_folder_tree(conn, library),
        fetch_timeline(conn, library).values,
    )


class LibraryModule(AppModule):
    """Módulo de una biblioteca con la barra 'LibrarySidebar' (ver el docstring del archivo).

    Cada subclase pone, además de 'key', 'title' e 'icon' (los de 'AppModule'), su
    biblioteca ('library') y los textos de su barra ('texts').
    """

    # Biblioteca del módulo ('Library.X.value') y textos de su barra: los pone la subclase
    library: ClassVar[str] = ""
    texts: ClassVar[LibraryTexts | None] = None

    def __init__(
        self, context: ModuleContext, *, button: QToolButton, parent: QObject | None = None
    ) -> None:
        """Crea su barra lateral (todavía sin catálogo: ver 'attach')."""
        if not self.library or self.texts is None:
            raise TypeError(f"{type(self).__name__}: faltan 'library' o 'texts'.")
        super().__init__(context, button=button, parent=parent)
        self.sidebar = LibrarySidebar(self.library, self.texts)
        # El orden de sus secciones, si se ven y si están plegadas: como las tenga el
        # usuario en este modo
        if context.section_layout is not None:
            self.sidebar.bind_layout(context.section_layout, self.key)
        self.sidebar.source_selected.connect(self.source_selected)
        self.sidebar.reveal_folder_requested.connect(self._on_reveal_folder)
        # Carpetas con o sin sus subcarpetas: la misma opción que el Catálogo
        self.sidebar.set_include_subfolders(self._show_subfolder_items())
        # Gestor de la base de datos (None sin catálogo) y generación (descarta
        # respuestas de un catálogo ya cerrado), como en los demás módulos
        self._db: Any = None
        self._generation = 0

    # -------------------------------------------------------------------------
    # Interfaz
    # -------------------------------------------------------------------------

    def sidebar_page(self) -> QWidget:
        """Su barra lateral."""
        return self.sidebar

    def current_source(self) -> GridSource | None:
        """Lo elegido en la barra («Todos los …», una carpeta, una fecha...)."""
        return self.sidebar.current_source()

    def show_source(self, source: GridSource) -> None:
        """Lo pide otro (p. ej. el inspector): se elige en la barra, si tiene fila."""
        self.sidebar.show_source(source)

    # -------------------------------------------------------------------------
    # Ciclo de vida del catálogo
    # -------------------------------------------------------------------------

    def attach(self, db: Any, catalog_dir: Path) -> None:
        """Empieza a trabajar con un catálogo recién abierto."""
        self._db = db
        self._generation += 1

    def detach(self) -> None:
        """Olvida el catálogo y deja la barra vacía."""
        self._db = None
        self._generation += 1
        self.sidebar.reset()

    def refresh(self) -> None:
        """Relee en segundo plano los contadores, las carpetas y las fechas."""
        if self._db is None:
            return
        self._db.execute_async(
            fetch_library_sidebar_data,
            self.library,
            on_result=partial(self._on_sidebar_data, self._generation),
            on_error=lambda error: logger.warning(
                f"No se pudo leer la barra del módulo {self.title}: {error}"
            ),
        )

    def save_state(self) -> dict:
        """Lo desplegado y la fila elegida de la barra (ver 'LibrarySidebar.save_state')."""
        return self.sidebar.save_state()

    def restore_state(self, state: object) -> None:
        """Recupera lo desplegado de la barra y la fila elegida."""
        self.sidebar.restore_state(state)

    def apply_settings(self, changed: set[str]) -> None:
        """Si ha cambiado la opción de las subcarpetas, las «Carpetas» se rehacen (y, si hay
        una elegida, la cuadrícula se recarga)."""
        if SETTING_SHOW_SUBFOLDER_ITEMS in changed:
            self.sidebar.set_include_subfolders(self._show_subfolder_items())

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _show_subfolder_items(self) -> bool:
        """Opción «Mostrar los elementos de las subcarpetas» (por defecto, activada)."""
        value = self.context.config.get(SETTING_SHOW_SUBFOLDER_ITEMS, True)
        return value if isinstance(value, bool) else True

    def _on_reveal_folder(self, folder: str) -> None:
        """Menú de una carpeta > «Mostrar en el Explorador» (el Finder en macOS)."""
        if not Path(folder).is_dir():
            self.context.message_box.warning(
                f"La carpeta no existe (¿se ha movido, renombrado o borrado?):\n{folder}"
            )
            return
        if not reveal_in_file_manager(folder):
            self.context.message_box.warning(f"No se pudo abrir {FILE_MANAGER_NAME}:\n{folder}")

    def _on_sidebar_data(self, generation: int, data: tuple[int, int, tuple, tuple]) -> None:
        """Pone los contadores y los árboles (si siguen siendo del catálogo abierto).

        Si la carpeta o la fecha elegida ya no existe (se borró, o ya no tiene nada de la
        biblioteca), se vuelve a la primera fila («Todos los …»).
        """
        if generation != self._generation or self._db is None:
            return
        count, quick_count, folders, dates = data
        self.sidebar.set_library_count(count, quick_count)
        self.sidebar.set_folder_tree(folders)
        self.sidebar.set_date_tree(dates)
        current = self.sidebar.current_source()
        if current != self.sidebar.all_source and not self.sidebar.has_source(current):
            self.sidebar.select_source(self.sidebar.all_source)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'), con un catálogo en memoria: lo que
    # se lee para la barra es solo de la biblioteca del módulo, y la barra vuelve a
    # «Todos» si lo elegido desaparece. Ejecutar desde la raíz del proyecto:
    #     python -m controllers.app_modules.library_module
    import os
    import sqlite3

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from qtpy.QtWidgets import QApplication

    from core.catalog.catalog_schema import apply_migrations, configure_connection
    from core.catalog.grid_source import folder_source

    app = QApplication.instance() or QApplication([])

    conn = sqlite3.connect(":memory:")
    configure_connection(conn)
    apply_migrations(conn)
    conn.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('P', '/tmp/p')")

    def add(name: str, media_type: str, library: str, content: str | None) -> None:
        columns = {
            "storage_location_id": 1, "relative_path": name, "file_name": name.split("/")[-1],
            "media_type": media_type, "mime_type": "x/y", "file_size": 1, "file_mtime_ns": 0,
            "title": name, "library": library, "content_created_at": content,
        }  # fmt: skip
        conn.execute(
            f"INSERT INTO media_items({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
            tuple(columns.values()),
        )

    add("rutas/ordesa.gpx", "track", "tracks", "2024-07-01 08:00:00")
    add("rutas/pineta.gpx", "track", "tracks", "2023-08-02 09:00:00")
    add("musica/cancion.mp3", "audio", "audio", None)
    conn.execute("UPDATE media_items SET in_quick_selection = 1 WHERE file_name = 'pineta.gpx'")

    # 1. Lo de la barra, solo de la biblioteca pedida
    count, quick, folders, dates = fetch_library_sidebar_data(conn, "tracks")
    assert (count, quick) == (2, 1), (count, quick)
    assert folders and dates, (folders, dates)
    assert fetch_library_sidebar_data(conn, "audio")[:2] == (1, 0)
    assert fetch_library_sidebar_data(conn, "video")[:2] == (0, 0)

    # 2. Un módulo de prueba: la barra con sus textos; lo que lee, al llegar, en la barra
    class _Config(dict):
        pass

    class _Db:
        def execute_async(self, function: Any, *args: Any, on_result: Any, on_error: Any) -> None:
            on_result(function(conn, *args))  # en el momento: la prueba no tiene hilos

    class _Module(LibraryModule):
        key, title, icon = "tracks", "Tracks", None
        library = "tracks"
        texts = LibraryTexts("Biblioteca - Tracks", "Todos los tracks", "Todos", "Rápida")

    window = QWidget()
    context = ModuleContext(
        window=window, config=_Config(), message_box=None,  # type: ignore[arg-type]
        grid_view=None, grid_model=None, grid_actions=None,  # type: ignore[arg-type]
    )  # fmt: skip
    module = _Module(context, button=QToolButton(window))
    assert module.sidebar_page() is module.sidebar
    assert module.current_source() == library_source("tracks")
    module.refresh()  # sin catálogo: nada
    module.attach(_Db(), Path("/tmp"))
    module.refresh()
    # Una carpeta elegida que se queda sin tracks: al leer la barra, vuelve a «Todos»
    folder = folder_source(1, "rutas")
    assert module.sidebar.has_source(folder)
    module.sidebar.select_source(folder, emit=False)
    assert module.current_source() == folder
    conn.execute("DELETE FROM media_items WHERE library = 'tracks'")
    module.refresh()
    assert module.current_source() == library_source("tracks")

    # 3. Sin 'library' o sin 'texts', la subclase está a medias: se avisa al crearla
    class _Incomplete(LibraryModule):
        key = "x"

    try:
        _Incomplete(context, button=QToolButton(window))
    except TypeError:
        pass
    else:
        raise AssertionError("faltaba 'library' y no ha avisado")

    module.detach()
    print("Autoprueba finalizada correctamente.")
