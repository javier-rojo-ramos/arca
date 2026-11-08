"""Vistas del centro de la ventana: cuadrícula, lista, individual y mapa.

Este módulo NO depende de Qt: solo define las vistas posibles. Cada módulo dice cuáles
ofrece y cuál es la inicial ('AppModule.views' y 'AppModule.default_view'); la elegida se
recuerda por módulo y por catálogo ('ModuleViewState'); la pone en pantalla el
'CenterViewController' (página de 'stacked_widget_main', botones de vista y deslizador).

    GRID    cuadrícula de tarjetas            (todos los módulos, de momento)
    SINGLE  vista individual: un archivo      (todos los módulos, de momento)
    LIST    lista con columnas                (llegará con el módulo Audio)
    MAP     mapa                              (llegará con el módulo Tracks)

Decidido por el autor el 08/11/2026 (ver docs/DECISIONES.md, «Vistas del centro»).

1.0.0 Primera versión (paso A.1, subpaso 3).

Prueba rápida (desde la raíz del proyecto):
    python -m controllers.app_modules.center_views
"""

__version__ = "1.0.0"
__all__ = ["CenterView"]

# Librerías estándar
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


# Textos de la interfaz (decididos por el autor el 08/11/2026: «Cuadrícula (G)» y
# «Vista individual (Intro)»)
_TOOLTIPS: dict[CenterView, str] = {
    CenterView.GRID: "Cuadrícula (G)",
    CenterView.SINGLE: "Vista individual (Intro)",
    CenterView.LIST: "Lista",
    CenterView.MAP: "Mapa",
}

# Iconos (constantes de AppIcons); la lista y el mapa aún no tienen
_ICON_NAMES: dict[CenterView, str] = {
    CenterView.GRID: "VIEW_GRID",
    CenterView.SINGLE: "VIEW_FULL",
    CenterView.LIST: "",
    CenterView.MAP: "",
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

    # Los iconos que se nombran existen en AppIcons
    from config.app_constants import AppIcons

    for view in CenterView:
        if view.icon_name:
            assert getattr(AppIcons, view.icon_name, ""), view
    print("Autoprueba finalizada correctamente.")
