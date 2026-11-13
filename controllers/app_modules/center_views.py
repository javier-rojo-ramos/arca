"""Vistas del centro de la ventana: cuadrícula, lista, individual y mapa.

Este módulo NO depende de Qt: solo define las vistas posibles. Cada módulo dice cuáles
ofrece y cuál es la inicial ('AppModule.views' y 'AppModule.default_view'); la elegida se
recuerda por módulo y por catálogo ('ModuleViewState'); la pone en pantalla el
'CenterViewController' (página de 'stacked_widget_main', botones de vista y deslizador).

    GRID    cuadrícula de tarjetas            (todos los módulos, de momento)
    SINGLE  vista individual: un archivo      (todos los módulos, de momento)
    LIST    lista con columnas                (llegará con el módulo Audio)
    MAP     mapa                              (el Catálogo, desde el 13/11/2026; docs/MAPA.md)

Decidido por el autor el 08/11/2026 (ver docs/DECISIONES.md, «Vistas del centro»).

1.2.0 'MapOptions': qué permite el mapa de cada módulo (de momento, ubicar fotos).
1.1.0 El mapa: icono y atajo «Mapa (M)» (decidido por el autor el 13/11/2026).
1.0.0 Primera versión (paso A.1, subpaso 3).

Prueba rápida (desde la raíz del proyecto):
    python -m controllers.app_modules.center_views
"""

__version__ = "1.2.0"
__all__ = ["CenterView", "MapOptions"]

# Librerías estándar
from dataclasses import dataclass
from enum import Enum


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

    @property
    def tooltip(self) -> str:
        return _TOOLTIPS[self]

    @property
    def icon_name(self) -> str:
        return _ICON_NAMES[self]

    @classmethod
    def from_key(cls, key: object) -> "CenterView | None":
        """La vista de una clave guardada, o None si no se entiende (otra versión...)."""
        try:
            return cls(key)
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class MapOptions:
    """Qué permite el mapa de un módulo ('AppModule.map_options'; docs/MAPA.md, §2.6).

    Attributes:
        allow_geotag: Ubicar fotos soltándolas en el mapa y mover las ya ubicadas (Imagen,
            sí; el Catálogo, que mezcla tipos de archivo, solo mira).
    """

    allow_geotag: bool = False


# Textos de la interfaz (decididos por el autor el 08/11/2026: «Cuadrícula (G)» y
# «Vista individual (Intro)»)
_TOOLTIPS: dict[CenterView, str] = {
    CenterView.GRID: "Cuadrícula (G)",
    CenterView.SINGLE: "Vista individual (Intro)",
    CenterView.LIST: "Lista",
    CenterView.MAP: "Mapa (M)",
}

# Iconos (constantes de AppIcons); la lista aún no tiene
_ICON_NAMES: dict[CenterView, str] = {
    CenterView.GRID: "VIEW_GRID",
    CenterView.SINGLE: "VIEW_FULL",
    CenterView.LIST: "",
    CenterView.MAP: "VIEW_MAP",
}


if __name__ == "__main__":
    # Autoprueba (sin Qt).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.app_modules.center_views
    assert {view.value for view in CenterView} == {"grid", "single", "list", "map"}
    assert all(view.tooltip for view in CenterView)
    assert CenterView.GRID.tooltip == "Cuadrícula (G)"
    assert CenterView.from_key("single") is CenterView.SINGLE
    for bad in ("otra", None, 3, ["grid"]):
        assert CenterView.from_key(bad) is None, bad

    # El mapa, por defecto, solo para mirar
    assert MapOptions() == MapOptions(allow_geotag=False) and MapOptions(True).allow_geotag

    # Los iconos que se nombran existen en AppIcons
    from config.app_constants import AppIcons

    for view in CenterView:
        if view.icon_name:
            assert getattr(AppIcons, view.icon_name, ""), view
    print("Autoprueba finalizada correctamente.")
