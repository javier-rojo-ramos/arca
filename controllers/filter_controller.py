"""Controlador de la barra de filtros: une la barra ('FilterBar') con el 'ModuleHost'.

La barra solo muestra y avisa; el 'ModuleHost' guarda el filtro de cada módulo y lo pasa a
la cuadrícula (ver 'module_host.py'). Aquí se traduce lo uno en lo otro:

    - Pestaña pulsada -> 'GridFilter.with_panel' -> 'ModuleHost.set_filter' -> la barra.
    - «Ninguno»       -> 'GridFilter.cleared' (sin borrar lo escrito).
    - Candado         -> el mismo filtro con 'locked' cambiado (no recarga la cuadrícula).
    - Ctrl+L          -> 'GridFilter.toggled': de encendido a «Ninguno» y vuelta a lo
                         último encendido. Funciona también con la barra oculta.
    - 'ModuleHost.filter_changed' (otro módulo, abrir o cerrar el catálogo, la vuelta a
      «Ninguno» al cambiar de origen) -> la barra.
    - 'ModuleHost.view_changed' -> la franja de la barra se oculta en la vista individual
      (el filtro sigue mandando: las flechas solo pasan por lo filtrado).

La barra está desactivada sin catálogo y en los módulos que no deciden la cuadrícula (los
provisionales: no ofrecen campos de orden).

Paneles de las pestañas: los de las pestañas que ya tienen uno se pasan al crearlo
('panels'); solo esas se pueden pulsar.

Uso (en el controlador principal, solo la conexión):
    self.filters = FilterController(module_host, bar=widget_filter_bar,
                                    frame=frame_main_top, window=self, parent=self)

1.0.0 Primera versión (paso A.3, subpaso 3).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m controllers.filter_controller
"""

__version__ = "1.0.0"
__all__ = ["TOGGLE_SHORTCUT", "FilterController"]

# Librerías estándar
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Qt
from qtpy.QtGui import QKeySequence, QShortcut
from qtpy.QtWidgets import QWidget

# Módulos del proyecto
from controllers.app_modules.center_views import CenterView
from ui_helpers.widgets.filter_bar import FilterBar

# Atajo para activar o desactivar el filtro (como en Lightroom)
TOGGLE_SHORTCUT = "Ctrl+L"


class FilterController(QObject):
    """Une la barra de filtros con el filtro del módulo activo (ver el docstring del archivo)."""

    def __init__(
        self,
        host: Any,
        *,
        bar: FilterBar,
        frame: QWidget,
        window: QWidget,
        panels: Mapping[str, QWidget] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Conecta la barra y el host.

        Args:
            host: El 'ModuleHost' (o algo con 'active_filter', 'set_filter',
                'active_sort_fields', 'attached', 'active_view' y las señales
                'filter_changed' y 'view_changed').
            bar: La barra de filtros ('widget_filter_bar').
            frame: Franja que la contiene ('frame_main_top'): se oculta en la vista
                individual.
            window: Ventana donde vale Ctrl+L.
            panels: Panel de cada pestaña que ya lo tiene (clave -> widget).
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._host = host
        self._bar = bar
        self._frame = frame
        for key, panel in (panels or {}).items():
            bar.add_panel(key, panel)
        bar.set_available((panels or {}).keys())

        bar.panel_toggled.connect(self._on_panel_toggled)
        bar.none_requested.connect(self._on_none_requested)
        bar.lock_toggled.connect(self._on_lock_toggled)
        host.filter_changed.connect(self._show)
        host.view_changed.connect(self._on_view_changed)

        self._shortcut = QShortcut(QKeySequence(TOGGLE_SHORTCUT), window)
        self._shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcut.activated.connect(self.toggle)

        self._show()
        self._on_view_changed()

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def toggle(self) -> None:
        """Ctrl+L: activa o desactiva el filtro sin perder lo escrito."""
        if self._enabled():
            self._apply(self._host.active_filter.toggled())

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _enabled(self) -> bool:
        """Hay catálogo y el módulo activo decide la cuadrícula (no es provisional)."""
        return bool(self._host.attached and self._host.active_sort_fields())

    def _apply(self, grid_filter: Any) -> None:
        """Pide el filtro al host (lo recuerda y recarga si hace falta) y lo muestra."""
        self._host.set_filter(grid_filter)
        self._show()

    def _show(self, _filter: object = None) -> None:
        """La barra, con el filtro del módulo activo."""
        grid_filter = self._host.active_filter
        self._bar.setEnabled(self._enabled())
        self._bar.set_state(grid_filter.active, locked=grid_filter.locked)

    def _on_panel_toggled(self, key: str, on: bool) -> None:
        if self._enabled():
            self._apply(self._host.active_filter.with_panel(key, on))

    def _on_none_requested(self) -> None:
        if self._enabled():
            self._apply(self._host.active_filter.cleared())

    def _on_lock_toggled(self, locked: bool) -> None:
        if self._enabled():
            self._apply(replace(self._host.active_filter, locked=locked))

    def _on_view_changed(self, _view: object = None) -> None:
        """En la vista individual, la franja se oculta (deja más sitio a la foto)."""
        self._frame.setVisible(self._host.active_view != CenterView.SINGLE)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen') con un host de mentira.
    # Ejecutar desde la raíz del proyecto:  python -m controllers.filter_controller
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import Signal
    from qtpy.QtWidgets import QApplication

    from core.catalog.grid_filter import FILTER_ATTRIBUTES, FILTER_TEXT, NO_FILTER

    app = QApplication([])

    class _Host(QObject):
        filter_changed = Signal(object)
        view_changed = Signal(object)

        def __init__(self) -> None:
            super().__init__()
            self.active_filter = NO_FILTER
            self.attached = True
            self.fields: tuple[str, ...] = ("file_name",)
            self.active_view = CenterView.GRID
            self.requests: list = []

        def active_sort_fields(self) -> tuple[str, ...]:
            return self.fields

        def set_filter(self, grid_filter) -> None:
            self.requests.append(grid_filter)
            self.active_filter = grid_filter

    window = QWidget()  # nunca se muestra: no se crea ninguna ventana
    frame = QWidget(window)
    bar = FilterBar(frame)
    host = _Host()
    text_panel = QWidget(window)
    controller = FilterController(host, bar=bar, frame=frame, window=window,
                                  panels={FILTER_TEXT: text_panel}, parent=window)  # fmt: skip

    # Solo «Texto» se puede pulsar; al pulsarla se enciende, y su panel se ve
    assert bar._tabs[FILTER_TEXT].isEnabled() and not bar._tabs[FILTER_ATTRIBUTES].isEnabled()
    bar._tabs[FILTER_TEXT].click()
    assert host.active_filter.active == {FILTER_TEXT} and bar.active == {FILTER_TEXT}
    assert not text_panel.isHidden()
    # Candado: se cierra sin tocar las pestañas
    bar._lock.click()
    assert host.active_filter.locked and bar.locked and bar.active == {FILTER_TEXT}
    # «Ninguno» y Ctrl+L (vuelta a lo último encendido)
    bar._none.click()
    assert host.active_filter.is_none and bar._none.isChecked() and text_panel.isHidden()
    controller.toggle()
    assert host.active_filter.active == {FILTER_TEXT} and bar.active == {FILTER_TEXT}
    controller.toggle()
    assert host.active_filter.is_none

    # El host cambia el filtro (otro módulo, cambio de origen): la barra lo muestra
    host.active_filter = NO_FILTER.with_panel(FILTER_TEXT, True)
    host.filter_changed.emit(host.active_filter)
    assert bar.active == {FILTER_TEXT} and not bar.locked

    # Sin catálogo o en un módulo provisional: desactivada; Ctrl+L no hace nada
    host.fields = ()
    host.filter_changed.emit(host.active_filter)
    count = len(host.requests)
    controller.toggle()
    assert not bar.isEnabled() and len(host.requests) == count
    host.fields, host.attached = ("file_name",), False
    host.filter_changed.emit(host.active_filter)
    assert not bar.isEnabled()
    host.attached = True
    host.filter_changed.emit(host.active_filter)
    assert bar.isEnabled()

    # Vista individual: la franja se oculta; al volver a la cuadrícula, se ve
    host.active_view = CenterView.SINGLE
    host.view_changed.emit(host.active_view)
    assert frame.isHidden()
    host.active_view = CenterView.GRID
    host.view_changed.emit(host.active_view)
    assert not frame.isHidden()

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
