"""Vistas del centro de la ventana: cuadrícula, lista, individual y mapa.

Este módulo NO depende de Qt: solo define las vistas posibles. Cada módulo dice cuáles
ofrece y cuál es la inicial ('AppModule.views' y 'AppModule.default_view'); la elegida se
recuerda por módulo y por catálogo ('ModuleViewState'); la pone en pantalla el
'CenterViewController' (página de 'stacked_widget_main', botones de vista y deslizador).

    GRID    cuadrícula de tarjetas            (todos los módulos, de momento)
    SINGLE  vista individual: un archivo      (todos los módulos, de momento)
    LIST    lista con columnas                (llegará con el módulo Audio)
    MAP     mapa                              (el Catálogo, desde el 13/11/2026; docs/MOD_TRACKS.md)
    ALBUMS  álbumes: la cuadrícula, una       (Música, desde MUS 5.3; docs/MOD_MUSICA.md §7.5)
            tarjeta por álbum

Cada vista dice cómo se agrupan las filas de la cuadrícula ('grouping'): la de álbumes, una
por álbum ('core/catalog/album_rows.py'); las demás, una por archivo (None).

Decidido por el autor el 08/11/2026 (ver docs/DECISIONES.md, «Vistas del centro»).

1.4.0 'ALBUMS', la vista de álbumes de Música, y 'CenterView.grouping' (MUS 5.3; acordado
      con el autor el 26/11/2026: «Álbumes», con un disco por icono y sin atajo).
1.3.0 'MapOptions.show_profile' (la banda del perfil, en Tracks) y
      'MapOptions.filmstrip_starts_visible' (la tira, recordada por módulo; en Tracks empieza
      oculta). Docs/MOD_TRACKS.md, paso 5.3a.
1.2.0 'MapOptions': qué permite el mapa de cada módulo (de momento, ubicar fotos).
1.1.0 El mapa: icono y atajo «Mapa (M)» (decidido por el autor el 13/11/2026).
1.0.0 Primera versión (paso A.1, subpaso 3).

Prueba rápida (desde la raíz del proyecto):
    python -m controllers.app_modules.center_views
"""

__version__ = "1.4.0"
__all__ = ["CenterView", "MapOptions"]

# Librerías estándar
from dataclasses import dataclass
from enum import Enum

# Módulos del proyecto
from core.catalog.album_rows import ALBUM_GROUPING


class CenterView(Enum):
    """Una vista del centro. El valor es la clave que se guarda en settings.json.

    Attributes:
        tooltip: Texto emergente de su botón en la barra inferior (con su atajo).
        icon_name: Nombre de su icono en 'config.app_constants.AppIcons' ("" = sin icono:
            el botón muestra la inicial del texto emergente).
    """

    GRID = "grid"
    SINGLE = "single"
    LIST = "list"
    MAP = "map"
    ALBUMS = "albums"

    @property
    def tooltip(self) -> str:
        return _TOOLTIPS[self]

    @property
    def icon_name(self) -> str:
        return _ICON_NAMES[self]

    @property
    def grouping(self) -> str | None:
        """Cómo agrupa las filas de la cuadrícula (None: una por archivo)."""
        return _GROUPINGS.get(self)

    @classmethod
    def from_key(cls, key: object) -> "CenterView | None":
        """La vista de una clave guardada, o None si no se entiende (otra versión...)."""
        try:
            return cls(key)
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class MapOptions:
    """Qué permite el mapa de un módulo ('AppModule.map_options'; docs/MOD_TRACKS.md, §2.6).

    Attributes:
        allow_geotag: Ubicar fotos soltándolas en el mapa y mover las ya ubicadas (Imagen,
            sí; el Catálogo, que mezcla tipos de archivo, solo mira).
        show_profile: La banda del perfil de elevación del track activo bajo el mapa
            (Tracks).
        filmstrip_starts_visible: Si la tira de fotos se ve mientras el usuario no la
            muestre u oculte en este módulo (después, cada módulo recuerda la suya). En
            Tracks empieza oculta: el perfil es lo que interesa ahí.
    """

    allow_geotag: bool = False
    show_profile: bool = False
    filmstrip_starts_visible: bool = True


# Textos de la interfaz (decididos por el autor el 08/11/2026: «Cuadrícula (G)» y
# «Vista individual (Intro)»)
_TOOLTIPS: dict[CenterView, str] = {
    CenterView.GRID: "Cuadrícula (G)",
    CenterView.SINGLE: "Vista individual (Intro)",
    CenterView.LIST: "Lista",
    CenterView.MAP: "Mapa (M)",
    CenterView.ALBUMS: "Álbumes",
}

# Iconos (constantes de AppIcons); la lista aún no tiene
_ICON_NAMES: dict[CenterView, str] = {
    CenterView.GRID: "VIEW_GRID",
    CenterView.SINGLE: "VIEW_FULL",
    CenterView.LIST: "",
    CenterView.MAP: "VIEW_MAP",
    CenterView.ALBUMS: "VIEW_ALBUMS",
}

# Las vistas que agrupan las filas de la cuadrícula (las demás, una por archivo)
_GROUPINGS: dict[CenterView, str] = {CenterView.ALBUMS: ALBUM_GROUPING}


if __name__ == "__main__":
    # Autoprueba (sin Qt).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.app_modules.center_views
    assert {view.value for view in CenterView} == {"grid", "single", "list", "map", "albums"}
    assert CenterView.ALBUMS.grouping == ALBUM_GROUPING and CenterView.GRID.grouping is None
    assert all(view.tooltip for view in CenterView)
    assert CenterView.GRID.tooltip == "Cuadrícula (G)"
    assert CenterView.from_key("single") is CenterView.SINGLE
    for bad in ("otra", None, 3, ["grid"]):
        assert CenterView.from_key(bad) is None, bad

    # El mapa, por defecto, solo para mirar, sin perfil y con la tira a la vista
    assert MapOptions() == MapOptions(allow_geotag=False) and MapOptions(True).allow_geotag
    assert not MapOptions().show_profile and MapOptions().filmstrip_starts_visible

    # Los iconos que se nombran existen en AppIcons
    from config.app_constants import AppIcons

    for view in CenterView:
        if view.icon_name:
            assert getattr(AppIcons, view.icon_name, ""), view
    print("Autoprueba finalizada correctamente.")
