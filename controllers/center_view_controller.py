"""Vistas del centro en pantalla: qué página se ve, los botones de vista y el deslizador.

Une tres piezas que no se conocen entre sí:
    - el 'ModuleHost', que sabe qué vistas ofrece el módulo activo y cuál tiene elegida
      ('active_views', 'active_view', señal 'view_changed', 'set_view');
    - los botones de vista de la barra inferior ('ViewButtons', 'widget_view_buttons');
    - la pila del centro ('stacked_widget_main': 'page_grid', 'page_single'...) y el
      deslizador del tamaño de las tarjetas, que solo se ve en la cuadrícula.

Flujo: pulsar un botón -> 'ModuleHost.set_view' (lo recuerda por módulo y por catálogo)
-> 'view_changed' -> aquí: página, botones y deslizador. Lo mismo al cambiar de módulo o
al abrir y cerrar un catálogo (el host emite 'view_changed').

Uso (en el controlador principal, que solo lo crea):
    CenterViewController(
        module_host, buttons=..., stack=..., pages={CenterView.GRID: page_grid, ...},
        size_slider=..., parent=window,
    )

1.0.0 Primera versión (paso A.1, subpaso 3): botones, páginas y deslizador. La vista
      individual todavía es una página vacía (subpaso 4).
"""

__version__ = "1.0.0"
__all__ = ["CenterViewController"]

# Librerías estándar
from collections.abc import Mapping

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject
from qtpy.QtWidgets import QStackedWidget, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from controllers.app_modules.center_views import CenterView
from controllers.app_modules.module_host import ModuleHost
from ui_helpers.widgets.view_buttons import ViewButtons


class CenterViewController(QObject):
    """Pone en pantalla la vista del centro del módulo activo (ver el docstring del archivo)."""

    def __init__(
        self,
        host: ModuleHost,
        *,
        buttons: ViewButtons,
        stack: QStackedWidget,
        pages: Mapping[CenterView, QWidget],
        size_slider: QWidget,
        parent: QObject | None = None,
    ) -> None:
        """Conecta las piezas y muestra ya la vista del módulo activo.

        Args:
            host: Coordinador de los módulos.
            buttons: Botones de vista de la barra inferior.
            stack: Pila del centro ('stacked_widget_main').
            pages: Página de cada vista (las que no estén usan la de la cuadrícula).
            size_slider: Deslizador del tamaño de las tarjetas (solo en la cuadrícula).
            parent: Objeto padre (la ventana principal).
        """
        super().__init__(parent)
        self._host = host
        self._buttons = buttons
        self._stack = stack
        self._pages = dict(pages)
        self._slider = size_slider

        buttons.view_requested.connect(self._on_view_requested)
        host.view_changed.connect(self._show)
        self._show()  # el módulo inicial ya se activó al crear el host

    @property
    def current_view(self) -> CenterView:
        """Vista que se está viendo (la del módulo activo)."""
        return self._host.active_view

    def _on_view_requested(self, key: str) -> None:
        """Un botón de vista: se pide al host (que la recuerda y avisa con 'view_changed')."""
        view = CenterView.from_key(key)
        if view is not None:
            self._host.set_view(view)

    def _show(self, _view: object = None) -> None:
        """Página, botones y deslizador según la vista del módulo activo."""
        view = self._host.active_view
        self._buttons.set_views(
            [(v.value, v.tooltip, getattr(AppIcons, v.icon_name, "") if v.icon_name else "")
             for v in self._host.active_views()],
            view.value,
        )  # fmt: skip
        page = self._pages.get(view)
        if page is None:
            logger.warning(f"La vista {view.value!r} todavía no tiene página: se ve la cuadrícula.")
            page = self._pages[CenterView.GRID]
        self._stack.setCurrentWidget(page)
        # El tamaño de las tarjetas solo tiene sentido en la cuadrícula. Se oculta solo el
        # deslizador (no su zona), para que la barra de clasificación siga centrada
        self._slider.setVisible(view == CenterView.GRID)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen'), con un host de mentira.
    # Ejecutar desde la raíz del proyecto:  python -m controllers.center_view_controller
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import Signal
    from qtpy.QtWidgets import QApplication, QSlider

    app = QApplication([])

    class _FakeHost(QObject):
        view_changed = Signal(object)

        def __init__(self) -> None:
            super().__init__()
            self.views = (CenterView.GRID, CenterView.SINGLE)
            self.view = CenterView.GRID

        @property
        def active_view(self) -> CenterView:
            return self.view

        def active_views(self) -> tuple[CenterView, ...]:
            return self.views

        def set_view(self, view: CenterView) -> None:
            if view in self.views and view != self.view:
                self.view = view
                self.view_changed.emit(view)

    window = QWidget()  # nunca se muestra
    stack = QStackedWidget(window)
    page_grid, page_single = QWidget(stack), QWidget(stack)
    stack.addWidget(page_grid)
    stack.addWidget(page_single)
    slider = QSlider(window)
    buttons = ViewButtons(window)
    host = _FakeHost()
    controller = CenterViewController(
        host, buttons=buttons, stack=stack,  # type: ignore[arg-type]
        pages={CenterView.GRID: page_grid, CenterView.SINGLE: page_single},
        size_slider=slider, parent=window,
    )  # fmt: skip

    # Al empezar: la cuadrícula, con su botón marcado y el deslizador visible
    assert stack.currentWidget() is page_grid and buttons.current == "grid"
    assert buttons.keys() == ["grid", "single"] and not slider.isHidden()

    # Botón de la vista individual: página vacía, botón marcado, deslizador oculto
    buttons._buttons["single"].click()
    assert host.view is CenterView.SINGLE and controller.current_view is CenterView.SINGLE
    assert stack.currentWidget() is page_single and buttons.current == "single"
    assert slider.isHidden()

    # Otro módulo (el host cambia de vistas y avisa): botones rehechos y su vista
    host.views, host.view = (CenterView.GRID,), CenterView.GRID
    host.view_changed.emit(CenterView.GRID)
    assert stack.currentWidget() is page_grid and not slider.isHidden()
    assert buttons.isHidden()  # una sola vista: sin botones

    # Una vista sin página todavía: se ve la cuadrícula (con un aviso en el registro)
    host.views, host.view = (CenterView.GRID, CenterView.MAP), CenterView.MAP
    host.view_changed.emit(CenterView.MAP)
    assert stack.currentWidget() is page_grid

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
