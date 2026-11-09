"""Controlador de la barra de filtros: une la barra ('FilterBar') con el 'ModuleHost'.

La barra solo muestra y avisa; el 'ModuleHost' guarda el filtro de cada módulo y lo pasa a
la cuadrícula (ver 'module_host.py'). Aquí se traduce lo uno en lo otro:

    - Pestaña pulsada -> 'GridFilter.with_panel' -> 'ModuleHost.set_filter' -> la barra.
    - «Ninguno»       -> 'GridFilter.cleared' (sin borrar lo escrito).
    - Candado         -> el mismo filtro con 'locked' cambiado (no recarga la cuadrícula).
    - Ctrl+L          -> 'GridFilter.toggled': de encendido a «Ninguno» y vuelta a lo
                         último encendido. Funciona también con la barra oculta.
    - Fila de «Texto» ('TextFilterRow', su panel) -> el filtro con 'text' cambiado (la
      fila ya espera la pausa al escribir). Al cambiar de módulo, la fila muestra lo
      escrito en ese módulo.
    - Ctrl+F          -> enciende «Texto» (si no lo estaba) y pone el cursor en su caja.
                         En la vista individual (la barra está oculta) no hace nada.
    - Fila de «Atributos» ('AttributeFilterRow', su panel) -> el filtro con 'attributes'
      cambiado (en el acto). Al cambiar de módulo, la fila muestra lo elegido en ese
      módulo y sus tipos ('ModuleHost.active_filter_media_types').
    - Panel de «Metadatos» (lo lleva su propio controlador, 'MetadataFilterController':
      los recuentos en segundo plano) -> el filtro con 'metadata' cambiado. Cada vez que
      la barra muestra un filtro, se lo pasa ('show_filter'): así cuenta lo que cambie
      también al escribir en «Texto» o pulsar en «Atributos».
    - Desplegable de los ajustes personalizados (lo lleva 'FilterPresetController': la
      lista y las preguntas) -> el filtro que pide (un ajuste elegido, «Restaurar...»).
      Cada vez que la barra muestra un filtro, se lo pasa ('show_filter'): así el botón
      enseña el nombre del ajuste que coincide.
    - 'ModuleHost.filter_changed' (otro módulo, abrir o cerrar el catálogo, la vuelta a
      «Ninguno» al cambiar de origen) -> la barra.
    - 'ModuleHost.view_changed' -> la franja de la barra se oculta en la vista individual
      (el filtro sigue mandando: las flechas solo pasan por lo filtrado).

La barra está desactivada sin catálogo y en los módulos que no deciden la cuadrícula (los
provisionales: no ofrecen campos de orden).

Paneles de las pestañas: las filas de «Texto» ('text_row') y de «Atributos»
('attribute_row'), el controlador de «Metadatos» ('metadata', con su panel) y los de las
demás que ya tengan uno ('panels') se pasan al crearlo; solo esas pestañas se pueden pulsar.
El controlador de los ajustes personalizados ('presets'), también.

Uso (en el controlador principal, solo la conexión):
    self.filters = FilterController(module_host, bar=widget_filter_bar,
                                    frame=frame_main_top, window=self,
                                    text_row=TextFilterRow(widget_filter_bar),
                                    attribute_row=AttributeFilterRow(widget_filter_bar),
                                    metadata=MetadataFilterController(...),
                                    presets=FilterPresetController(...),
                                    parent=self)

1.4.0 Ajustes personalizados ('presets': su controlador, con el desplegable de la
      barra); paso A.3, filtros personalizados.
1.3.0 Panel de «Metadatos» ('metadata': su controlador, con los recuentos); la pestaña
      «Metadatos» ya se puede pulsar (paso A.3).
1.2.0 Fila de «Atributos» ('attribute_row'), con los tipos del módulo activo (paso A.3).
1.1.0 Fila de «Texto» ('text_row') y Ctrl+F (paso A.3, subpaso 4).
1.0.0 Primera versión (paso A.3, subpaso 3).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m controllers.filter_controller
"""

__version__ = "1.4.0"
__all__ = ["TEXT_SHORTCUT", "TOGGLE_SHORTCUT", "FilterController"]

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
from controllers.filter_preset_controller import FilterPresetController
from controllers.metadata_filter_controller import MetadataFilterController
from core.catalog.grid_filter import (
    FILTER_ATTRIBUTES,
    FILTER_METADATA,
    FILTER_TEXT,
    AttributeFilter,
    GridFilter,
    MetadataFilter,
    TextFilter,
)
from ui_helpers.widgets.attribute_filter_row import AttributeFilterRow
from ui_helpers.widgets.filter_bar import FilterBar
from ui_helpers.widgets.text_filter_row import TextFilterRow

# Atajo para activar o desactivar el filtro (como en Lightroom)
TOGGLE_SHORTCUT = "Ctrl+L"
# Atajo para buscar: enciende «Texto» y pone el cursor en su caja
TEXT_SHORTCUT = "Ctrl+F"


class FilterController(QObject):
    """Une la barra de filtros con el filtro del módulo activo (ver el docstring del archivo)."""

    def __init__(
        self,
        host: Any,
        *,
        bar: FilterBar,
        frame: QWidget,
        window: QWidget,
        text_row: TextFilterRow | None = None,
        attribute_row: AttributeFilterRow | None = None,
        metadata: MetadataFilterController | None = None,
        presets: FilterPresetController | None = None,
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
            window: Ventana donde valen Ctrl+L y Ctrl+F.
            text_row: Fila de «Texto» (el panel de esa pestaña; None = sin él).
            attribute_row: Fila de «Atributos» (igual).
            metadata: Controlador del panel «Metadatos» (su panel es el de la pestaña).
            presets: Controlador de los ajustes personalizados (el desplegable de la barra).
            panels: Panel de las demás pestañas que ya lo tienen (clave -> widget).
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._host = host
        self._bar = bar
        self._frame = frame
        self._text_row = text_row
        self._attribute_row = attribute_row
        self._metadata = metadata
        self._presets = presets
        if presets is not None:
            presets.filter_requested.connect(self._on_preset_requested)
        all_panels: dict[str, QWidget] = dict(panels or {})
        if text_row is not None:
            all_panels[FILTER_TEXT] = text_row
            text_row.text_filter_changed.connect(self._on_text_changed)
        if attribute_row is not None:
            all_panels[FILTER_ATTRIBUTES] = attribute_row
            attribute_row.attribute_filter_changed.connect(self._on_attributes_changed)
        if metadata is not None:
            all_panels[FILTER_METADATA] = metadata.panel
            metadata.metadata_filter_changed.connect(self._on_metadata_changed)
        for key, panel in all_panels.items():
            bar.add_panel(key, panel)
        bar.set_available(all_panels.keys())

        bar.panel_toggled.connect(self._on_panel_toggled)
        bar.none_requested.connect(self._on_none_requested)
        bar.lock_toggled.connect(self._on_lock_toggled)
        host.filter_changed.connect(self._show)
        host.view_changed.connect(self._on_view_changed)

        self._shortcut = QShortcut(QKeySequence(TOGGLE_SHORTCUT), window)
        self._shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._shortcut.activated.connect(self.toggle)
        self._text_shortcut = QShortcut(QKeySequence(TEXT_SHORTCUT), window)
        self._text_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._text_shortcut.activated.connect(self.focus_text)

        self._show()
        self._on_view_changed()

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def toggle(self) -> None:
        """Ctrl+L: activa o desactiva el filtro sin perder lo escrito."""
        if self._enabled():
            self._apply(self._host.active_filter.toggled())

    def focus_text(self) -> None:
        """Ctrl+F: enciende «Texto» (si no lo estaba) y pone el cursor en su caja."""
        if (
            not self._enabled()
            or self._text_row is None
            or self._host.active_view == CenterView.SINGLE  # la barra no se ve
        ):
            return
        grid_filter = self._host.active_filter
        if FILTER_TEXT not in grid_filter.active:
            self._apply(grid_filter.with_panel(FILTER_TEXT, True))
        self._text_row.focus_text()

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
        if self._text_row is not None:
            self._text_row.set_filter(grid_filter.text)  # no hace nada si ya es lo que se ve
        if self._attribute_row is not None:
            self._attribute_row.set_media_types(self._host.active_filter_media_types())
            self._attribute_row.set_filter(grid_filter.attributes)
        if self._metadata is not None:
            # Sus columnas y, si se ve, los recuentos que hayan cambiado
            self._metadata.show_filter(grid_filter, enabled=self._enabled())
        if self._presets is not None:
            # El nombre del ajuste que coincide y qué se puede pulsar en su menú
            self._presets.show_filter(grid_filter, enabled=self._enabled())

    def _on_preset_requested(self, grid_filter: GridFilter) -> None:
        """Un ajuste elegido o «Restaurar...» en el desplegable de ajustes."""
        if self._enabled():
            self._apply(grid_filter)

    def _on_metadata_changed(self, metadata: MetadataFilter) -> None:
        """Lo cambiado en el panel «Metadatos» (valores, campos, columnas)."""
        if self._enabled():
            self._apply(replace(self._host.active_filter, metadata=metadata))

    def _on_attributes_changed(self, attributes: AttributeFilter) -> None:
        """Lo pulsado en la fila de «Atributos»."""
        if self._enabled():
            self._apply(replace(self._host.active_filter, attributes=attributes))

    def _on_text_changed(self, text_filter: TextFilter) -> None:
        """Lo escrito (o el campo o el operador) en la fila de «Texto»."""
        if self._enabled():
            self._apply(replace(self._host.active_filter, text=text_filter))

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

    from core.catalog.grid_filter import FILTER_METADATA, NO_FILTER

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

        def active_filter_media_types(self) -> tuple[str, ...]:
            return ("photo", "video")

        def set_filter(self, grid_filter) -> None:
            self.requests.append(grid_filter)
            self.active_filter = grid_filter

    window = QWidget()  # nunca se muestra: no se crea ninguna ventana
    frame = QWidget(window)
    bar = FilterBar(frame)
    host = _Host()
    text_panel = TextFilterRow(window)
    attribute_panel = AttributeFilterRow(window)
    controller = FilterController(host, bar=bar, frame=frame, window=window, text_row=text_panel,
                                  attribute_row=attribute_panel, parent=window)  # fmt: skip

    # «Texto» y «Atributos» se pueden pulsar; «Metadatos», no
    assert bar._tabs[FILTER_TEXT].isEnabled() and bar._tabs[FILTER_ATTRIBUTES].isEnabled()
    assert not bar._tabs[FILTER_METADATA].isEnabled()
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

    # Fila de «Texto»: lo escrito pasa al filtro; al cambiar el host, la fila lo muestra
    host.active_filter = NO_FILTER.with_panel(FILTER_TEXT, True)
    host.filter_changed.emit(host.active_filter)
    text_panel.text_filter_changed.emit(TextFilter(text="boda"))
    assert host.active_filter.text.text == "boda" and host.active_filter.active == {FILTER_TEXT}
    host.active_filter = NO_FILTER  # otro módulo, sin nada escrito
    host.filter_changed.emit(host.active_filter)
    assert text_panel.current() == TextFilter()

    # Ctrl+F: enciende «Texto»; en la vista individual, nada
    controller.focus_text()
    assert host.active_filter.active == {FILTER_TEXT} and bar.active == {FILTER_TEXT}
    host.active_filter = NO_FILTER
    host.active_view = CenterView.SINGLE
    controller.focus_text()
    assert host.active_filter == NO_FILTER
    host.active_view = CenterView.GRID

    # Fila de «Atributos»: los tipos del módulo; lo pulsado pasa al filtro; y al revés
    assert [k for k in attribute_panel._rest._zones if k.startswith("type:")] == ["type:photo", "type:video"]
    attribute_panel.attribute_filter_changed.emit(AttributeFilter(rating=4))
    assert host.active_filter.attributes.rating == 4
    host.active_filter = NO_FILTER
    host.filter_changed.emit(host.active_filter)
    assert attribute_panel.current() == AttributeFilter()

    # «Metadatos»: con su controlador, se puede pulsar; recibe cada filtro que se muestra
    # (para contar) y lo que cambia en el panel pasa al filtro
    class _Metadata(QObject):
        metadata_filter_changed = Signal(object)

        def __init__(self, parent: QWidget) -> None:
            super().__init__(parent)
            self.panel = QWidget(parent)
            self.shown: list = []

        def show_filter(self, grid_filter: object, *, enabled: bool) -> None:
            self.shown.append((grid_filter, enabled))

    host.active_filter = NO_FILTER
    metadata_bar = FilterBar(frame)
    metadata = _Metadata(window)
    FilterController(host, bar=metadata_bar, frame=frame, window=window, metadata=metadata,
                     parent=window)  # fmt: skip
    assert metadata_bar._tabs[FILTER_METADATA].isEnabled() and metadata.shown[-1] == (NO_FILTER, True)
    metadata_bar._tabs[FILTER_METADATA].click()
    assert host.active_filter.active == {FILTER_METADATA} and not metadata.panel.isHidden()
    assert metadata.shown[-1] == (host.active_filter, True)
    columns = MetadataFilter.from_fields(("city",)).with_values(0, ["Huesca"])
    metadata.metadata_filter_changed.emit(columns)
    assert host.active_filter.metadata == columns and metadata.shown[-1][0].metadata == columns

    # Ajustes personalizados: reciben cada filtro que se muestra; el que piden, se aplica
    class _Presets(QObject):
        filter_requested = Signal(object)

        def __init__(self, parent: QWidget) -> None:
            super().__init__(parent)
            self.shown: list = []

        def show_filter(self, grid_filter: object, *, enabled: bool) -> None:
            self.shown.append((grid_filter, enabled))

    host.active_filter = NO_FILTER
    presets = _Presets(window)
    FilterController(host, bar=FilterBar(frame), frame=frame, window=window, presets=presets,
                     parent=window)  # fmt: skip
    assert presets.shown[-1] == (NO_FILTER, True)
    wanted = NO_FILTER.with_panel(FILTER_ATTRIBUTES, True)
    presets.filter_requested.emit(wanted)
    assert host.active_filter == wanted and presets.shown[-1] == (wanted, True)
    host.attached = False  # sin catálogo: no se aplica
    presets.filter_requested.emit(NO_FILTER)
    assert host.active_filter == wanted
    host.attached = True

    window.deleteLater()
    print("Autoprueba finalizada correctamente.")
