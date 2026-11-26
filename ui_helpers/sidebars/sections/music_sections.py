"""Secciones «Artistas» y «Años» de la barra de Música (en lugar de «Fechas»).

    ▼ ARTISTAS                                ▼ AÑOS
    ▾ 0 Varios                    4           ▾ 2003                       13
        1994 · BSO Pulp Fiction   2               Estopa - Estopa Gra...   13
        1999 · BSO The Matrix     2           ▸ 2001                       13
    ▾ Estopa                     26           ▸ Sin año                     1
        2001 · Destrangis        13
        1974 – 2011 · Grandes...  9
        Sin álbum                 1
      Sin artista                 2

Acordadas con el autor el 26/11/2026 (docs/MOD_MUSICA.md §7.2; el porqué, en
docs/DECISIONES.md): la barra tiene recorridos fijos y la combinación libre está en la
barra de filtros.
    - «Artistas»: el artista del álbum (o, sin él, el artista) ▸ sus álbumes, por año. Un
      álbum con canciones de varios años, con los dos extremos («1974 – 2011 · …»; pedido
      por el autor); sin año, solo el nombre.
    - «Años»: del más reciente al más antiguo ▸ sus álbumes con su artista delante,
      «Artista - Álbum», por artista y después por álbum (pedido por el autor); los que no
      tienen artista, solo con el nombre, al final.
    - «Sin artista», «Sin álbum» y «Sin año», al final de su nivel.
    - Sin iconos, como «Fechas»: los nombres, en la columna de las flechas
      ('TEXT_NAME_INDENT').
    - Lo desplegado se guarda por catálogo ('expanded_artists', 'expanded_years'). La
      primera vez, todo plegado.
    - En la barra, detrás de «Biblioteca» y «Carpetas» (las primeras en todos los módulos);
      «Años», plegada de partida ('section_registry.py').

Los árboles y el origen de cada fila, en 'core/catalog/music_browse.py' (cada fila cuenta
exactamente lo que muestra la cuadrícula al elegirla).

Uso (lo hace la barra, 'LibrarySidebar', con las secciones de más del módulo Audio):
    artists = ArtistSection("audio", parent)
    artists.set_tree(fetch_artist_tree(conn, "audio"))     # lo lee el módulo
    years = YearSection("audio", parent)
    years.set_tree(fetch_year_tree(conn, "audio"))

1.1.0 «Años»: «Artista - Álbum» ('year_album_label'), un álbum por artista; fuera el texto
      emergente con el artista y «Varios artistas» (pedido por el autor al verlo).
1.0.0 Primera versión (26/11/2026; docs/MOD_MUSICA.md, paso MUS 4.1).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m ui_helpers.sidebars.sections.music_sections
"""

__version__ = "1.1.0"
__all__ = ["ArtistSection", "YearSection", "album_label", "year_album_label"]

# Librerías estándar
from collections.abc import Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QModelIndex, Qt
from qtpy.QtGui import QStandardItem, QStandardItemModel
from qtpy.QtWidgets import QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.catalog_schema import fold_text
from core.catalog.grid_source import GridSource
from core.catalog.music_browse import (
    AlbumNode,
    ArtistNode,
    YearNode,
    artist_album_source,
    artist_source,
    is_artist_source,
    is_year_source,
    year_album_source,
    year_source,
)
from ui_helpers.helpers.signal_blocker import blocked_signals as _blocked
from ui_helpers.sidebars.sections.tree_section import TEXT_NAME_INDENT, TreeSection, make_item
from ui_helpers.widgets.sidebar_tree_view import ROLE_SOURCE, SidebarTreeView

# Textos de la interfaz
NO_ARTIST_TEXT = "Sin artista"
NO_ARTIST_TOOLTIP = "Canciones sin artista del álbum ni artista"
NO_ALBUM_TEXT = "Sin álbum"
NO_ALBUM_TOOLTIP = "Canciones sin álbum"
NO_YEAR_TEXT = "Sin año"
NO_YEAR_TOOLTIP = "Canciones sin año"
# Entre el artista y el álbum, en «Años» (como lo escribió el autor: «Artista - Álbum»)
ARTIST_ALBUM_SEPARATOR = " - "

# Rol propio: la clave de una fila que se despliega (artista o año), para recordarla
_ROLE_KEY = Qt.ItemDataRole.UserRole + 46


def album_label(album: AlbumNode, *, with_years: bool) -> str:
    """El texto de un álbum: su nombre o «Sin álbum»; con 'with_years' («Artistas»), su
    año delante («2001 · Destrangis») o los dos extremos si son varios («1974 – 2011 · …»)."""
    if album.name is None:
        return NO_ALBUM_TEXT
    if not with_years or album.year_min is None:
        return album.name
    years = str(album.year_min)
    if album.year_max is not None and album.year_max != album.year_min:
        years = f"{album.year_min} – {album.year_max}"
    return f"{years} · {album.name}"


def year_album_label(album: AlbumNode) -> str:
    """El texto de un álbum en «Años»: «Estopa - Destrangis», «Estopa - Sin álbum» o, sin
    artista, solo el álbum."""
    name = album_label(album, with_years=False)
    if album.artist is None:
        return name
    return f"{album.artist}{ARTIST_ALBUM_SEPARATOR}{name}"


class _MusicTreeSection(TreeSection):
    """Lo común de las dos secciones: un árbol de dos niveles (artista o año ▸ álbumes), lo
    desplegado y la fila elegida. Cada una pone sus filas ('_append_rows') y dice qué
    orígenes son suyos ('owns')."""

    # Clave de lo desplegado en el estado de la barra (una por sección)
    _state_key = ""

    def __init__(self, library: str, parent: QWidget | None = None) -> None:
        """Crea la sección vacía.

        Args:
            library: Biblioteca del módulo ('audio').
            parent: Widget padre.
        """
        super().__init__(parent)
        self._library = library
        self._tree: tuple[Any, ...] = ()
        self._expanded: set[str] = set()  # claves de las filas desplegadas

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._model = QStandardItemModel(self)
        self._view = SidebarTreeView(self, name_indent=TEXT_NAME_INDENT)
        self._view.setModel(self._model)
        self._view.expanded.connect(lambda index: self._on_expanded(index, True))
        self._view.collapsed.connect(lambda index: self._on_expanded(index, False))
        layout.addWidget(self._view)

    # --- 'TreeSection' -------------------------------------------------------

    def set_tree(self, data: Sequence[Any] | None) -> None:
        """Pone el árbol que ha leído el módulo; no hace nada si no ha cambiado."""
        tree = tuple(data or ())
        if tree == self._tree and self._model.rowCount() > 0:
            return
        self._tree = tree
        self._rebuild()

    def views(self) -> tuple[SidebarTreeView, ...]:
        return (self._view,)

    def find_item(self, source: GridSource) -> QStandardItem | None:
        """La fila de un origen de la sección (un artista, un año o uno de sus álbumes)."""
        if not self.owns(source):
            return None
        root = self._model.invisibleRootItem()
        for row in range(root.rowCount()):
            parent = root.child(row)
            if parent.data(ROLE_SOURCE) == source:
                return parent
            for child_row in range(parent.rowCount()):
                child = parent.child(child_row)
                if child.data(ROLE_SOURCE) == source:
                    return child
        return None

    def save_state(self) -> dict:
        return {self._state_key: sorted(self._expanded)}

    def restore_state(self, state: dict) -> None:
        expanded = state.get(self._state_key)
        if isinstance(expanded, list):
            self._expanded = {value for value in expanded if isinstance(value, str)}
            self._apply_expanded()

    def reset(self) -> None:
        self._tree = ()
        self._expanded.clear()
        self._rebuild()

    # --- Árbol ---------------------------------------------------------------

    def _append_rows(self, root: QStandardItem) -> None:
        """Añade las filas del árbol ('self._tree') bajo la raíz (cada sección las suyas)."""
        raise NotImplementedError

    @staticmethod
    def _parent_item(
        text: str, source: GridSource, count: int, key: str, tooltip: str = ""
    ) -> QStandardItem:
        """Una fila que se despliega (un artista o un año), con su clave para recordarla."""
        item = make_item(text, source, count)
        item.setData(key, _ROLE_KEY)
        if tooltip:
            item.setToolTip(tooltip)
        return item

    def _rebuild(self) -> None:
        """Rehace el árbol conservando lo desplegado; después, 'rebuilt' (la barra vuelve a
        marcar la fila elegida). Como en «Fechas», no se bloquean las señales del MODELO
        (ver TRAMPAS.md): solo las de la vista y su selección."""
        view, model = self._view, self._model
        with _blocked(view.selectionModel(), view):
            model.clear()
            self._append_rows(model.invisibleRootItem())
            self._apply_expanded()
        view.updateGeometry()
        self.rebuilt.emit()

    def _apply_expanded(self) -> None:
        """Despliega las filas de '_expanded' y pliega las demás."""
        root = self._model.invisibleRootItem()
        with _blocked(self._view):
            for row in range(root.rowCount()):
                item = root.child(row)
                if item.hasChildren():
                    self._view.setExpanded(item.index(), item.data(_ROLE_KEY) in self._expanded)
        self._view.updateGeometry()

    def _on_expanded(self, index: QModelIndex, expanded: bool) -> None:
        """Recuerda lo que despliega o pliega el usuario."""
        key = index.data(_ROLE_KEY)
        if isinstance(key, str):
            (self._expanded.add if expanded else self._expanded.discard)(key)


class ArtistSection(_MusicTreeSection):
    """«Artistas»: artista del álbum ▸ álbumes (ver el docstring del módulo). Espera
    'music_browse.fetch_artist_tree'."""

    _state_key = "expanded_artists"

    def owns(self, source: GridSource) -> bool:
        return is_artist_source(source, self._library)

    def _append_rows(self, root: QStandardItem) -> None:
        for artist in self._tree:
            if not isinstance(artist, ArtistNode):
                continue
            # La clave, sin mayúsculas ni acentos (la de la fila; «Sin artista», vacía)
            key = fold_text(artist.name) if artist.name is not None else ""
            item = self._parent_item(
                artist.name if artist.name is not None else NO_ARTIST_TEXT,
                artist_source(self._library, artist.name),
                artist.count,
                key,
                NO_ARTIST_TOOLTIP if artist.name is None else "",
            )
            for album in artist.albums:
                child = make_item(
                    album_label(album, with_years=True),
                    artist_album_source(self._library, artist.name, album.name),
                    album.count,
                )
                if album.name is None:
                    child.setToolTip(NO_ALBUM_TOOLTIP)
                item.appendRow(child)
            root.appendRow(item)


class YearSection(_MusicTreeSection):
    """«Años»: año ▸ álbumes (ver el docstring del módulo). Espera
    'music_browse.fetch_year_tree'."""

    _state_key = "expanded_years"

    def owns(self, source: GridSource) -> bool:
        return is_year_source(source, self._library)

    def _append_rows(self, root: QStandardItem) -> None:
        for year in self._tree:
            if not isinstance(year, YearNode):
                continue
            item = self._parent_item(
                year.year if year.year is not None else NO_YEAR_TEXT,
                year_source(self._library, year.year),
                year.count,
                year.year or "",
                NO_YEAR_TOOLTIP if year.year is None else "",
            )
            for album in year.albums:
                child = make_item(
                    year_album_label(album),
                    year_album_source(self._library, year.year, album.artist, album.name),
                    album.count,
                )
                if album.name is None:
                    child.setToolTip(NO_ALBUM_TOOLTIP)
                item.appendRow(child)
            root.appendRow(item)


if __name__ == "__main__":
    # Autoprueba (sin ventana). Ejecutar desde la raíz:
    #   python -m ui_helpers.sidebars.sections.music_sections
    import sys

    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Los textos de los álbumes
    single = AlbumNode("Destrangis", 13, 2001, 2001)
    assert album_label(single, with_years=True) == "2001 · Destrangis"
    assert album_label(single, with_years=False) == "Destrangis"
    span = AlbumNode("Grandes Éxitos", 9, 1974, 2011)
    assert album_label(span, with_years=True) == "1974 – 2011 · Grandes Éxitos"
    assert album_label(AlbumNode("Raro", 1), with_years=True) == "Raro"
    assert album_label(AlbumNode(None, 1, 2003, 2003), with_years=True) == "Sin álbum"
    assert year_album_label(AlbumNode("Destrangis", 13, 2001, 2001, "Estopa")) == "Estopa - Destrangis"
    assert year_album_label(AlbumNode(None, 1, 2003, 2003, "Estopa")) == "Estopa - Sin álbum"
    assert year_album_label(AlbumNode("Vacío", 1, 2010, 2010)) == "Vacío"  # sin artista

    # 2. «Artistas»: filas, números, orígenes y textos emergentes
    artists = (
        ArtistNode("Estopa", 23, (single, span, AlbumNode(None, 1, 2003, 2003))),
        ArtistNode(None, 2, (AlbumNode(None, 2),)),
    )
    section = ArtistSection("audio")
    rebuilt: list[bool] = []
    section.rebuilt.connect(lambda: rebuilt.append(True))
    section.set_tree(artists)
    model = section._model
    assert [model.item(r).text() for r in range(model.rowCount())] == ["Estopa", "Sin artista"]
    estopa = model.item(0)
    assert [estopa.child(r).text() for r in range(3)] == [
        "2001 · Destrangis", "1974 – 2011 · Grandes Éxitos", "Sin álbum",
    ]  # fmt: skip
    album_source = artist_album_source("audio", "Estopa", "Destrangis")
    assert section.find_item(album_source) is estopa.child(0) and section.owns(album_source)
    assert section.find_item(artist_source("audio", None)) is model.item(1)
    assert model.item(1).toolTip() == NO_ARTIST_TOOLTIP and estopa.child(2).toolTip() == NO_ALBUM_TOOLTIP
    assert section.find_item(year_source("audio", "2001")) is None  # de «Años»
    assert not section.owns(artist_source("video", "Estopa"))  # de otra biblioteca
    assert rebuilt == [True]
    section.set_tree(artists)  # lo mismo: no se rehace
    assert rebuilt == [True]

    # 3. Lo desplegado: al principio, nada; se guarda, se recupera y sobrevive al rehacer
    view = section._view
    assert not view.isExpanded(estopa.index())
    view.setExpanded(estopa.index(), True)  # como el usuario
    assert section.save_state() == {"expanded_artists": ["estopa"]}
    section.set_tree(artists[1:])
    section.set_tree(artists)
    assert view.isExpanded(model.item(0).index())
    section.restore_state({"expanded_artists": ["", 5]})  # lo que no es texto se ignora
    assert not view.isExpanded(model.item(0).index()) and view.isExpanded(model.item(1).index())
    section.reset()
    assert model.rowCount() == 0 and section.save_state() == {"expanded_artists": []}

    # 4. «Años»: «Artista - Álbum»; sin artista, solo el álbum; «Sin año»
    years = (
        YearNode("2010", 3, (
            AlbumNode("Mezclas", 2, 2010, 2010, artist="Ana"),
            AlbumNode("Solo", 1, 2010, 2010),
        )),
        YearNode(None, 1, (AlbumNode(None, 1),)),
    )  # fmt: skip
    year_section = YearSection("audio")
    year_section.set_tree(years)
    year_model = year_section._model
    assert [year_model.item(r).text() for r in range(2)] == ["2010", "Sin año"]
    first = year_model.item(0)
    assert [first.child(r).text() for r in range(2)] == ["Ana - Mezclas", "Solo"]
    assert first.child(0).toolTip() == "" and year_model.item(1).child(0).toolTip() == NO_ALBUM_TOOLTIP
    ana_source = year_album_source("audio", "2010", "Ana", "Mezclas")
    assert year_section.find_item(ana_source) is first.child(0)
    assert year_section.find_item(year_album_source("audio", "2010", None, "Solo")) is first.child(1)
    assert year_section.find_item(year_source("audio", None)) is year_model.item(1)
    assert year_section.find_item(album_source) is None  # de «Artistas»
    year_section._view.setExpanded(first.index(), True)
    assert year_section.save_state() == {"expanded_years": ["2010"]}
    print("Autoprueba finalizada correctamente.")
