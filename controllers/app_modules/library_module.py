"""Base de los módulos de UNA biblioteca con la barra 'LibrarySidebar' (Imagen, Tracks, Vídeo
y Audio).

Lo común de esos módulos, que antes estaba en 'TracksModule' (15/11/2026): la barra
izquierda («Biblioteca - …» con sus dos filas fijas, «Carpetas» y «Fechas»), lo que se lee
para ella en segundo plano, lo guardado de la barra por catálogo y el menú de las
carpetas. Lo de cada módulo (su biblioteca y sus textos, las secciones de más de su barra,
sus vistas, su orden y sus filtros) lo pone su subclase.

Qué hace (la barra no sabe nada de la base de datos):
    - Pasa al 'ModuleHost' lo que se elige en la barra ('source_selected').
    - 'refresh' lee en segundo plano, en una sola visita a la base de datos, los contadores
      de la biblioteca, el árbol de carpetas con archivos suyos, los años, meses y días
      ('timeline.fetch_timeline') y lo de cada sección de más ('ExtraSection.fetch').
    - Si lo elegido (una carpeta, una fecha, una fila de una sección de más) ya no existe
      (se borró, o ya no tiene nada de la biblioteca), vuelve a la primera fila («Todos los
      …»); salvo que una sección esté ocultando filas (un filtro escrito: 'hides_rows').
    - Lo desplegado y la fila elegida, guardados por catálogo ('save_state' /
      'restore_state'; el 'ModuleHost' los escribe en settings.json).

Uso (una subclase por módulo):
    class TracksModule(LibraryModule):
        key, title, icon = MODE_TRACKS, "Tracks", AppIcons.LIB_TRACKS
        library = Library.TRACKS.value
        texts = LibraryTexts("Biblioteca - Tracks", "Todos los tracks", ...)
        extra_sections = (ExtraSection("keywords", "Lista de palabras clave", ...),)  # si las tiene
        def views(self): ...          # y el orden, los filtros, el mapa...

1.3.0 'with_dates': un módulo puede no llevar «Fechas» (Música; MUS 4.1): ni la sección
      ni su lectura.
1.2.0 'folder_renamed': la barra, al día tras renombrar una carpeta (CAT 4.3).
1.1.0 Secciones de más en la barra ('extra_sections'), leídas con lo demás; no se vuelve
      a «Todos» mientras una sección oculte filas. Con ello, Imagen pasa a ser un módulo
      más de esta base (docs/PENDIENTE.md, GEN 13). Tracks, Vídeo y Audio, igual.
1.0.0 Primera versión (15/11/2026): sale de 'TracksModule' (sin cambiar lo que hace),
      para servir también a Vídeo y Audio.

Prueba rápida (desde la raíz del proyecto; sin ventana, con un catálogo en memoria):
    python -m controllers.app_modules.library_module
"""

__version__ = "1.3.0"
__all__ = ["LibraryModule", "fetch_library_sidebar_data"]

# Librerías estándar
from collections.abc import Callable, Sequence
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
from ui_helpers.sidebars.library_sidebar import ExtraSection, LibrarySidebar, LibraryTexts


def fetch_library_sidebar_data(
    conn: Any, library: str, *, dates: bool = True
) -> tuple[int, int, tuple, tuple]:
    """Lo que necesita la barra de una biblioteca: cuántos archivos tiene y cuántos de su
    selección rápida, el árbol de carpetas (solo con archivos suyos) y los años con sus
    meses y días (con 'dates=False', la barra no tiene «Fechas»: nada).

    Una sola función (una sola visita al hilo de la base de datos) para que todo llegue a
    la vez (así se sabe si la carpeta o la fecha elegida sigue existiendo).
    """
    everything, quick = library_source(library), quick_source(library)
    counts = count_grid_items(conn, [everything, quick])
    return (
        counts.get(everything, 0),
        counts.get(quick, 0),
        fetch_folder_tree(conn, library),
        fetch_timeline(conn, library).values if dates else (),
    )


def _fetch_sidebar_data(
    conn: Any, library: str, fetchers: Sequence[Callable[[Any, str], Any]], dates: bool
) -> tuple[tuple[int, int, tuple, tuple], tuple[Any, ...]]:
    """Todo lo de la barra en una sola visita al hilo de la base de datos: lo común
    ('fetch_library_sidebar_data') y, en su orden, lo de cada sección de más."""
    return (
        fetch_library_sidebar_data(conn, library, dates=dates),
        tuple(fetch(conn, library) for fetch in fetchers),
    )


class LibraryModule(AppModule):
    """Módulo de una biblioteca con la barra 'LibrarySidebar' (ver el docstring del archivo).

    Cada subclase pone, además de 'key', 'title' e 'icon' (los de 'AppModule'), su
    biblioteca ('library'), los textos de su barra ('texts') y, si las tiene, las secciones
    de más de su barra ('extra_sections').
    """

    # Biblioteca del módulo ('Library.X.value') y textos de su barra: los pone la subclase
    library: ClassVar[str] = ""
    texts: ClassVar[LibraryTexts | None] = None
    # Secciones de la barra además de biblioteca, carpetas y fechas (en su orden de partida)
    extra_sections: ClassVar[tuple[ExtraSection, ...]] = ()
    # Si su barra lleva «Fechas» (Música no: en su lugar, «Artistas» y «Años»)
    with_dates: ClassVar[bool] = True

    def __init__(
        self, context: ModuleContext, *, button: QToolButton, parent: QObject | None = None
    ) -> None:
        """Crea su barra lateral (todavía sin catálogo: ver 'attach')."""
        if not self.library or self.texts is None:
            raise TypeError(f"{type(self).__name__}: faltan 'library' o 'texts'.")
        super().__init__(context, button=button, parent=parent)
        self.sidebar = LibrarySidebar(
            self.library,
            self.texts,
            extra_sections=self.extra_sections,
            dates=self.with_dates,
        )
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

    def folder_renamed(self, location_id: int, old: str, new: str) -> None:
        """Ver 'AppModule.folder_renamed'."""
        self.sidebar.folder_renamed(location_id, old, new)

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
            _fetch_sidebar_data,
            self.library,
            tuple(spec.fetch for spec in self.extra_sections),
            self.with_dates,
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

    def _on_sidebar_data(
        self, generation: int, data: tuple[tuple[int, int, tuple, tuple], tuple[Any, ...]]
    ) -> None:
        """Pone los contadores y los árboles (si siguen siendo del catálogo abierto).

        Si lo elegido (una carpeta, una fecha, una fila de una sección de más) ya no existe
        (se borró, o ya no tiene nada de la biblioteca), se vuelve a la primera fila («Todos
        los …»). No, si una sección oculta filas (un filtro escrito): entonces que la fila
        no esté no quiere decir que haya desaparecido.
        """
        if generation != self._generation or self._db is None:
            return
        (count, quick_count, folders, dates), extra = data
        self.sidebar.set_library_count(count, quick_count)
        self.sidebar.set_folder_tree(folders)
        self.sidebar.set_date_tree(dates)
        for spec, section_data in zip(self.extra_sections, extra, strict=True):
            self.sidebar.set_section_data(spec.key, section_data)
        current = self.sidebar.current_source()
        if (
            current != self.sidebar.all_source
            and not self.sidebar.hides_rows()
            and not self.sidebar.has_source(current)
        ):
            self.sidebar.select_source(self.sidebar.all_source)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'), con un catálogo en memoria: lo que
    # se lee para la barra es solo de la biblioteca del módulo, la barra vuelve a «Todos»
    # si lo elegido desaparece, y las secciones de más. Ejecutar desde la raíz del proyecto:
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
    assert fetch_library_sidebar_data(conn, "tracks", dates=False)[3] == ()  # sin «Fechas»

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

    # 3. Una sección de más (como la «Lista de palabras clave» de Imagen): se crea, recibe
    #    sus datos con lo demás, guarda lo suyo y, mientras oculta filas (su filtro), no se
    #    vuelve a «Todos»; sin filtro, si lo elegido ya no existe, sí
    from qtpy.QtWidgets import QLineEdit

    from core.catalog.grid_source import keyword_source
    from core.catalog.keywords import fetch_keyword_tree
    from ui_helpers.sidebars.sections.keyword_section import KeywordSection

    add("fotos/a.jpg", "photo", "image", "2024-01-01 10:00:00")
    word = conn.execute("INSERT INTO keywords(name, name_folded) VALUES ('Ana', 'ana')").lastrowid
    conn.execute(
        "INSERT INTO media_keywords(media_id, keyword_id) "
        "SELECT id, ? FROM media_items WHERE library = 'image'",
        (word,),
    )

    class _WithKeywords(LibraryModule):
        key, title, icon = "image", "Imagen", None
        library = "image"
        texts = LibraryTexts("Biblioteca - Imagen", "Todas las imágenes", "Todas", "Rápida")
        extra_sections = (
            ExtraSection(
                "keywords",
                "Lista de palabras clave",
                lambda library, parent: KeywordSection(library, None, parent),
                fetch_keyword_tree,
            ),
        )

    images = _WithKeywords(context, button=QToolButton(window))
    assert images.sidebar._stack.section_ids() == ("library", "folders", "dates", "keywords")
    assert module.sidebar._stack.section_ids() == ("library", "folders", "dates")  # sin las de más
    images.attach(_Db(), Path("/tmp"))
    images.refresh()
    chosen = keyword_source(word, "image")
    assert images.sidebar.has_source(chosen)
    images.sidebar.select_source(chosen, emit=False)
    assert "expanded_keywords" in images.save_state()
    keyword_filter = images.sidebar.findChild(QLineEdit, "edit_keyword_filter")
    keyword_filter.setText("zzz")
    images.refresh()  # la palabra no se ve (el filtro), pero existe: sigue elegida
    assert images.sidebar.hides_rows() and not images.sidebar.has_source(chosen)
    assert images.current_source() == chosen
    keyword_filter.setText("")
    conn.execute("DELETE FROM keywords")
    images.refresh()  # ya no existe: vuelve a la primera fila
    assert images.current_source() == library_source("image")
    images.detach()

    # 4. Sin 'library' o sin 'texts', la subclase está a medias: se avisa al crearla
    class _Incomplete(LibraryModule):
        key = "x"

    try:
        _Incomplete(context, button=QToolButton(window))
    except TypeError:
        pass
    else:
        raise AssertionError("faltaba 'library' y no ha avisado")

    # 5. Un módulo sin «Fechas» (como Música): ni la sección ni su lectura
    class _NoDates(_Module):
        with_dates = False

    no_dates = _NoDates(context, button=QToolButton(window))
    assert no_dates.sidebar._stack.section_ids() == ("library", "folders")
    no_dates.attach(_Db(), Path("/tmp"))
    no_dates.refresh()
    assert "expanded_dates" not in no_dates.save_state()
    no_dates.detach()

    module.detach()
    print("Autoprueba finalizada correctamente.")
