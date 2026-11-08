"""Cómo se ve cada módulo: lo que el usuario elige por módulo y se recuerda por catálogo.

Este módulo NO depende de Qt: es Python puro.

Guarda, para cada módulo, el ORDEN de la cuadrícula y la VISTA del centro que elige el
usuario (los módulos sin nada elegido usan su 'default_order' y su 'default_view'). Lo
usa el 'ModuleHost', que decide cuándo se aplica y lo escribe en settings.json junto al
estado de las barras laterales:

    {"<carpeta del catálogo>": {"modules": {...},
                                "orders": {"image": {"field": ..., "descending": ...}},
                                "views": {"image": "single"}}}

Uso:
    state = ModuleViewState()
    state.order_for(module)                 # el elegido o el de partida del módulo
    state.set_order(module, order)          # True si cambia; ValueError si no lo ofrece
    state.view_for(module)                  # la vista elegida o la inicial del módulo
    state.set_view(module, view)            # igual que 'set_order'
    entry.update(state.to_state())          # al cerrar el catálogo
    state.restore(entry, modules_by_key)    # al abrirlo

Un módulo es cualquier objeto con 'key', 'sort_fields()', 'default_order()', 'views()' y
'default_view()' (como 'AppModule'): así este módulo no depende de la interfaz.

1.1.0 La vista del centro de cada módulo ('view_for', 'set_view'; clave 'views').

1.0.0 Sacado de 'module_host.py' (1.4.0) sin cambios de comportamiento, antes de guardar
      también la vista de cada módulo (paso A.1).

Prueba rápida (desde la raíz del proyecto):
    python -m controllers.app_modules.module_view_state
"""

__version__ = "1.1.0"
__all__ = ["ModuleViewState", "ViewStateModule"]

# Librerías estándar
from collections.abc import Mapping
from typing import Any, Protocol

# Módulos del proyecto
from controllers.app_modules.center_views import CenterView
from core.catalog.grid_orders import GridOrder

# Clave, dentro de la entrada de un catálogo, con los órdenes elegidos por módulo
_ORDERS_KEY = "orders"
# Clave con las vistas del centro elegidas por módulo
_VIEWS_KEY = "views"


class ViewStateModule(Protocol):
    """Lo que necesita saber de un módulo ('AppModule' lo cumple)."""

    key: str

    def sort_fields(self) -> tuple[str, ...]: ...

    def default_order(self) -> GridOrder | None: ...

    def views(self) -> tuple[CenterView, ...]: ...

    def default_view(self) -> CenterView: ...


class ModuleViewState:
    """Lo elegido en cada módulo para el catálogo abierto (ver el docstring del archivo)."""

    def __init__(self) -> None:
        # Orden elegido por el usuario en cada módulo (los que no están aquí usan su
        # 'default_order')
        self._orders: dict[str, GridOrder] = {}
        # Vista del centro elegida en cada módulo (los que no están aquí, su 'default_view')
        self._views: dict[str, CenterView] = {}

    # -------------------------------------------------------------------------
    # Orden de la cuadrícula
    # -------------------------------------------------------------------------

    def order_for(self, module: ViewStateModule) -> GridOrder | None:
        """Orden de un módulo: el elegido por el usuario o, si no, el de partida.

        Un orden elegido cuyo campo el módulo ya no ofrece se ignora. None = el módulo no
        decide el orden.
        """
        chosen = self._orders.get(module.key)
        if chosen is not None and chosen.field in module.sort_fields():
            return chosen
        return module.default_order()

    def set_order(self, module: ViewStateModule, order: GridOrder) -> bool:
        """Recuerda el orden elegido en un módulo.

        Returns:
            True si cambia lo que el módulo muestra; False si ya era ese.

        Raises:
            ValueError: Si el módulo no ofrece ese campo.
        """
        if order.field not in module.sort_fields():
            raise ValueError(f"El módulo {module.key!r} no ordena por {order.field!r}.")
        if order == self.order_for(module):
            return False
        self._orders[module.key] = order
        return True

    # -------------------------------------------------------------------------
    # Vista del centro
    # -------------------------------------------------------------------------

    def view_for(self, module: ViewStateModule) -> CenterView:
        """Vista de un módulo: la elegida por el usuario o, si no (o si el módulo ya no la
        ofrece), la inicial."""
        chosen = self._views.get(module.key)
        if chosen is not None and chosen in module.views():
            return chosen
        return module.default_view()

    def set_view(self, module: ViewStateModule, view: CenterView) -> bool:
        """Recuerda la vista elegida en un módulo.

        Returns:
            True si cambia la vista del módulo; False si ya era esa.

        Raises:
            ValueError: Si el módulo no ofrece esa vista.
        """
        if view not in module.views():
            raise ValueError(f"El módulo {module.key!r} no tiene la vista {view.value!r}.")
        if view == self.view_for(module):
            return False
        self._views[module.key] = view
        return True

    # -------------------------------------------------------------------------
    # Estado guardado por catálogo
    # -------------------------------------------------------------------------

    def clear(self) -> None:
        """Olvida todo lo elegido (al cerrar el catálogo: es de cada catálogo)."""
        self._orders.clear()
        self._views.clear()

    def to_state(self) -> dict[str, Any]:
        """Lo que se añade a la entrada del catálogo en settings.json (vacío si nada)."""
        state: dict[str, Any] = {}
        if self._orders:
            state[_ORDERS_KEY] = {key: order.to_state() for key, order in self._orders.items()}
        if self._views:
            state[_VIEWS_KEY] = {key: view.value for key, view in self._views.items()}
        return state

    def restore(self, entry: object, modules: Mapping[str, ViewStateModule]) -> None:
        """Recupera lo guardado con 'to_state' en la entrada de un catálogo.

        Descarta lo que ya no vale: un módulo que no existe o que no decide el orden, un
        campo desconocido o que el módulo ya no ofrece, una vista que no se entiende o que
        el módulo no tiene.
        """
        self._orders.clear()
        self._views.clear()
        self._restore_views(entry, modules)
        saved = entry.get(_ORDERS_KEY) if isinstance(entry, dict) else None
        if not isinstance(saved, dict):
            return
        for key, state in saved.items():
            module = modules.get(key)
            default = module.default_order() if module is not None else None
            if module is None or default is None:
                continue  # módulo que ya no existe o que no decide el orden
            order = GridOrder.from_state(state, default)
            if order.field in module.sort_fields():
                self._orders[key] = order

    def _restore_views(self, entry: object, modules: Mapping[str, ViewStateModule]) -> None:
        """Recupera las vistas elegidas (las que ya no valen se descartan)."""
        saved = entry.get(_VIEWS_KEY) if isinstance(entry, dict) else None
        if not isinstance(saved, dict):
            return
        for key, value in saved.items():
            module = modules.get(key)
            view = CenterView.from_key(value)
            if module is not None and view is not None and view in module.views():
                self._views[key] = view


if __name__ == "__main__":
    # Autoprueba con módulos de mentira (sin Qt).
    # Ejecutar desde la raíz del proyecto:  python -m controllers.app_modules.module_view_state
    from dataclasses import dataclass

    from core.catalog.grid_orders import CAPTURE_TIME_ORDER, NAME_ORDER, SORT_FIELDS

    @dataclass
    class _Module:
        key: str
        fields: tuple[str, ...]
        default: GridOrder | None
        offered: tuple[CenterView, ...] = (CenterView.GRID, CenterView.SINGLE)

        def sort_fields(self) -> tuple[str, ...]:
            return self.fields

        def default_order(self) -> GridOrder | None:
            return self.default

        def views(self) -> tuple[CenterView, ...]:
            return self.offered

        def default_view(self) -> CenterView:
            return CenterView.GRID

    catalog = _Module("catalog", tuple(SORT_FIELDS), NAME_ORDER)
    image = _Module("image", tuple(SORT_FIELDS), CAPTURE_TIME_ORDER)
    video = _Module("video", (), None)  # provisional: no decide el orden
    modules = {m.key: m for m in (catalog, image, video)}

    state = ModuleViewState()
    # Sin nada elegido: el orden de partida de cada módulo
    assert state.order_for(catalog) == NAME_ORDER and state.order_for(image) == CAPTURE_TIME_ORDER
    assert state.order_for(video) is None and state.to_state() == {}

    # Elegir: cambia solo ese módulo; repetirlo no cambia nada
    by_size = GridOrder("file_size", descending=True)
    assert state.set_order(image, by_size) is True
    assert state.set_order(image, by_size) is False
    assert state.set_order(catalog, NAME_ORDER) is False  # ya era el de partida: no se guarda
    assert state.order_for(image) == by_size and state.order_for(catalog) == NAME_ORDER
    try:
        state.set_order(video, NAME_ORDER)
        raise AssertionError("debía rechazar un campo que el módulo no ofrece")
    except ValueError:
        pass

    # Guardar y recuperar: el mismo formato que antes en settings.json
    saved = state.to_state()
    assert saved == {"orders": {"image": {"field": "file_size", "descending": True}}}, saved
    restored = ModuleViewState()
    restored.restore({"modules": {}, **saved}, modules)
    assert restored.order_for(image) == by_size and restored.order_for(catalog) == NAME_ORDER

    # Lo que ya no vale se descarta
    restored.restore(
        {"orders": {"image": {"field": "ya_no_existe"}, "video": {"field": "file_name"},
                    "borrado": {"field": "file_name"}, "catalog": 3}},
        modules,
    )  # fmt: skip
    # (un estado ilegible se lee como el orden de partida: el Catálogo sigue por nombre)
    assert restored.order_for(catalog) == NAME_ORDER
    assert restored.order_for(image) == CAPTURE_TIME_ORDER and restored.order_for(video) is None
    for bad in (None, [], {"orders": []}):
        restored.restore(bad, modules)
        assert restored.to_state() == {}

    # Un módulo que deja de ofrecer el campo elegido vuelve a su orden de partida
    state.set_order(catalog, GridOrder("file_size"))
    catalog.fields = ("file_name",)
    assert state.order_for(catalog) == NAME_ORDER

    # Vistas: la inicial, elegir otra, repetir, una que el módulo no ofrece
    views = ModuleViewState()
    assert views.view_for(image) is CenterView.GRID
    assert views.set_view(image, CenterView.SINGLE) is True
    assert views.set_view(image, CenterView.SINGLE) is False
    assert views.set_view(catalog, CenterView.GRID) is False  # ya era la inicial
    assert views.view_for(image) is CenterView.SINGLE and views.view_for(catalog) is CenterView.GRID
    try:
        views.set_view(image, CenterView.MAP)
        raise AssertionError("debía rechazar una vista que el módulo no ofrece")
    except ValueError:
        pass
    views.set_order(image, by_size)
    saved = views.to_state()
    assert saved == {"orders": {"image": {"field": "file_size", "descending": True}},
                     "views": {"image": "single"}}, saved  # fmt: skip
    again = ModuleViewState()
    again.restore(saved, modules)
    assert again.view_for(image) is CenterView.SINGLE and again.order_for(image) == by_size
    # Lo que ya no vale se descarta; un módulo que deja de ofrecer la vista vuelve a la inicial
    again.restore({"views": {"image": "otra", "borrado": "single", "catalog": "map"}}, modules)
    assert again.to_state() == {}
    again.restore(saved, modules)
    image.offered = (CenterView.GRID,)
    assert again.view_for(image) is CenterView.GRID
    image.offered = (CenterView.GRID, CenterView.SINGLE)

    # Al cerrar el catálogo se olvida todo
    state.clear()
    assert state.to_state() == {} and state.order_for(image) == CAPTURE_TIME_ORDER
    views.clear()
    assert views.to_state() == {} and views.view_for(image) is CenterView.GRID
    print("Autoprueba finalizada correctamente.")
