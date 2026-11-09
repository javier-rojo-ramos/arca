"""Controlador de los ajustes personalizados de la barra de filtros.

Une el desplegable ('FilterPresetButton', 'FilterBar.preset_button') con la lista de
ajustes (settings.json, 'filter_presets') y el filtro del módulo activo. La lógica (qué
guarda un ajuste, cuál coincide, cómo se elige o se restaura) está en
'core/catalog/filter_presets.py'; aquí solo se conecta y se preguntan las cosas:

    - 'show_filter(filtro, enabled=...)': lo llama 'FilterController' cada vez que la barra
      muestra un filtro. El botón enseña los ajustes que valen para el módulo
      ('fits_module'), el nombre del que coincide (si no, «Personalizado», o «Sin filtro»
      con «Ninguno») y qué acciones se pueden
      pulsar: «Guardar…» con alguna pestaña encendida, «Restaurar…» si hay algo que
      restaurar.
    - «Guardar…» -> pide el nombre (ventana «Nuevo ajuste personalizado»); si ya hay uno
      que se llama así (sin distinguir mayúsculas), pregunta si se reemplaza. Se guarda
      la lista entera en settings.json y el botón muestra el nombre nuevo (el filtro no
      cambia).
    - «Restaurar…»  -> 'filter_requested(reset_filter(filtro))'.
    - Un ajuste     -> 'filter_requested(applied_preset(ajuste, filtro))'.
    - «Gestionar…»  -> la ventana «Gestionar ajustes personalizados» con TODOS los ajustes
                       ('FilterPresetsDialog'). Al aceptar, se guarda la lista nueva y, si
                       se ha renombrado el último elegido en un módulo, se sigue su nombre.

Qué ajuste coincide: en «Metadatos» basta con las mismas columnas, aunque lo elegido en
ellas sea otro ('matching_preset'). Si varios tienen las mismas columnas, el último que se
eligió (o guardó) en ese módulo: se recuerda mientras la aplicación está abierta.

'filter_requested' lo recoge 'FilterController', que lo aplica como cualquier otro cambio
del filtro (lo guarda el 'ModuleHost', recarga la cuadrícula y lo muestra la barra).

La lista es una para toda la aplicación (todos los módulos y catálogos); se lee al crear
el controlador.

Uso (en el controlador principal, solo la conexión):
    presets = FilterPresetController(module_host, button=bar.preset_button,
                                     config=self.config, window=self, parent=self)
    FilterController(..., presets=presets, ...)

1.3.0 «Gestionar…»: abre la ventana de gestión y guarda lo que devuelve (paso A.3,
      filtros personalizados, subpaso 3).
1.2.0 Pasa al botón si hay algo encendido ('filtering'): sin ajuste que coincida, dice
      «Personalizado» o, con «Ninguno», «Sin filtro» (el autor, 09/11/2026).
1.1.0 Recuerda el último ajuste elegido en cada módulo ('preferred' de
      'matching_preset'): al elegir otro valor en «Metadatos», el botón sigue con su
      nombre. Lo pidió el autor el 09/11/2026.
1.0.0 Primera versión (paso A.3, filtros personalizados, subpaso 2).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m controllers.filter_preset_controller
"""

__version__ = "1.3.0"
__all__ = [
    "REPLACE_BUTTONS",
    "SAVE_LABEL",
    "SAVE_TITLE",
    "FilterPresetController",
    "ask_preset_name",
    "confirm_replace",
    "replace_question",
]

# Librerías estándar
from collections.abc import Callable
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal
from qtpy.QtWidgets import QDialog, QInputDialog, QLineEdit, QWidget

# Módulos del proyecto
from config.app_constants import SETTING_FILTER_PRESETS
from core.catalog.filter_presets import (
    MAX_PRESET_NAME,
    FilterPreset,
    applied_preset,
    find_preset,
    fits_module,
    is_reset,
    matching_preset,
    preset_from_filter,
    presets_from_config,
    presets_to_config,
    reset_filter,
    with_preset_saved,
)
from core.catalog.grid_filter import GridFilter
from ui_helpers.dialogs.filter_presets_dialog import FilterPresetsDialog
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.widgets.filter_preset_button import FilterPresetButton

# Textos de la interfaz (aprobados por el autor el 09/11/2026)
SAVE_TITLE = "Nuevo ajuste personalizado"
SAVE_LABEL = "Nombre del ajuste:"
REPLACE_BUTTONS = ("Reemplazar", "Cancelar")


def replace_question(name: str) -> str:
    """La pregunta al guardar con un nombre que ya existe."""
    return f"Ya hay un ajuste llamado «{name}». ¿Quieres reemplazarlo por el filtro activo?"


def ask_preset_name(window: QWidget) -> str | None:
    """Pide el nombre del ajuste nuevo (caja vacía, como mucho 'MAX_PRESET_NAME'
    caracteres). None si se cancela o se deja vacío."""
    dialog = QInputDialog(window)
    dialog.setWindowTitle(SAVE_TITLE)
    dialog.setLabelText(SAVE_LABEL)
    dialog.setInputMode(QInputDialog.InputMode.TextInput)
    line = dialog.findChild(QLineEdit)
    if line is not None:
        line.setMaxLength(MAX_PRESET_NAME)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    name = " ".join(dialog.textValue().split())
    dialog.deleteLater()
    return name if accepted and name else None


def confirm_replace(window: QWidget, name: str) -> bool:
    """Pregunta si se reemplaza el ajuste que ya se llama así."""
    answer = MessageBoxHelper(window).question(
        replace_question(name), title=SAVE_TITLE, buttons=list(REPLACE_BUTTONS)
    )
    return answer == REPLACE_BUTTONS[0]


class FilterPresetController(QObject):
    """Une el desplegable de ajustes con la lista y el filtro (ver el docstring del archivo).

    Signals:
        filter_requested(object): el filtro ('GridFilter') que debe tener el módulo activo
            (tras elegir un ajuste o restaurar).
    """

    filter_requested = Signal(object)

    def __init__(
        self,
        host: Any,
        *,
        button: FilterPresetButton,
        config: Any,
        window: QWidget,
        parent: QObject | None = None,
    ) -> None:
        """Lee la lista de ajustes y conecta el botón.

        Args:
            host: El 'ModuleHost' (o algo con 'active_filter',
                'active_filter_media_types', 'active_filter_metadata_fields' y, si lo
                tiene, 'active_module').
            button: El desplegable ('FilterBar.preset_button').
            config: Configuración de la aplicación ('get' y 'set').
            window: Ventana de la que cuelgan las preguntas.
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._host = host
        self._button = button
        self._config = config
        self._window = window
        self._presets: list[FilterPreset] = presets_from_config(config.get(SETTING_FILTER_PRESETS))
        self._shown: list[FilterPreset] = []  # los del módulo activo, en el orden del menú
        self._enabled = False
        # El último ajuste elegido (o guardado) en cada módulo (clave -> nombre)
        self._last_chosen: dict[str | None, str] = {}
        # Las preguntas (se cambian en las pruebas: así no se abre ninguna ventana)
        self.ask_name: Callable[[QWidget], str | None] = ask_preset_name
        self.confirm_replace: Callable[[QWidget, str], bool] = confirm_replace
        # La ventana de gestión: (ventana, ajustes) -> (lista nueva, renombrados) o None
        self.manage: Callable[
            [QWidget, list[FilterPreset]], tuple[list[FilterPreset], dict[str, str]] | None
        ] = FilterPresetsDialog.ask

        button.save_requested.connect(self._on_save)
        button.reset_requested.connect(self._on_reset)
        button.preset_chosen.connect(self._on_chosen)
        button.manage_requested.connect(self._on_manage)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    @property
    def presets(self) -> list[FilterPreset]:
        """Todos los ajustes, en su orden (una copia)."""
        return list(self._presets)

    def show_filter(self, grid_filter: GridFilter, *, enabled: bool) -> None:
        """El botón, con los ajustes del módulo activo y el que coincide con el filtro.

        Args:
            grid_filter: El filtro del módulo activo.
            enabled: Si la barra se puede usar (hay catálogo y el módulo decide la
                cuadrícula); si no, ninguna acción se puede pulsar.
        """
        self._enabled = bool(enabled)
        media_types = self._host.active_filter_media_types()
        fields = self._host.active_filter_metadata_fields()
        self._shown = [p for p in self._presets if fits_module(p, media_types)]
        preferred = self._last_chosen.get(self._module_key())
        current = matching_preset(grid_filter, self._shown, media_types, fields, preferred)
        index = next((i for i, p in enumerate(self._shown) if p is current), None)
        self._button.set_state(
            [p.name for p in self._shown],
            index,
            filtering=not grid_filter.is_none,
            can_save=self._enabled and not grid_filter.is_none,
            can_reset=self._enabled and not is_reset(grid_filter, fields),
            can_manage=self._enabled,  # también sin ajustes: para restaurar los de fábrica
        )

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _module_key(self) -> str | None:
        """La clave del módulo activo (None si no hay o el host no lo dice)."""
        return getattr(getattr(self._host, "active_module", None), "key", None)

    def _set_presets(self, presets: list[FilterPreset]) -> None:
        """Cambia la lista y la guarda entera en settings.json."""
        self._presets = list(presets)
        self._config.set(SETTING_FILTER_PRESETS, presets_to_config(self._presets))

    def _on_save(self) -> None:
        """«Guardar filtro activo como nuevo ajuste personalizado…»."""
        grid_filter = self._host.active_filter
        if not self._enabled or grid_filter.is_none:
            return
        name = self.ask_name(self._window)
        if name is None:
            return
        try:
            preset = preset_from_filter(
                name, grid_filter, self._host.active_filter_metadata_fields()
            )
        except ValueError:
            return  # nombre vacío (no debería llegar: la pregunta ya lo descarta)
        index = find_preset(self._presets, preset.name)
        if index is not None and not self.confirm_replace(
            self._window, self._presets[index].name
        ):
            return
        self._set_presets(with_preset_saved(self._presets, preset))
        self._last_chosen[self._module_key()] = preset.name
        # El filtro no cambia, pero ahora coincide con el ajuste nuevo: su nombre al botón
        self.show_filter(self._host.active_filter, enabled=self._enabled)

    def _on_reset(self) -> None:
        """«Restaurar filtro activo a sus valores por defecto»."""
        if self._enabled:
            self.filter_requested.emit(reset_filter(self._host.active_filter))

    def _on_manage(self) -> None:
        """«Gestionar ajustes personalizados…»: la ventana con todos los ajustes."""
        if not self._enabled:
            return
        result = self.manage(self._window, list(self._presets))
        if result is None:
            return  # «Cancelar»
        presets, renamed = result
        # El último elegido en cada módulo sigue siéndolo aunque cambie de nombre
        for key, name in self._last_chosen.items():
            self._last_chosen[key] = renamed.get(name, name)
        if presets != self._presets:
            self._set_presets(presets)
        self.show_filter(self._host.active_filter, enabled=self._enabled)

    def _on_chosen(self, index: int) -> None:
        """Un ajuste de la lista (su posición entre los del módulo)."""
        if self._enabled and 0 <= index < len(self._shown):
            preset = self._shown[index]
            self._last_chosen[self._module_key()] = preset.name
            self.filter_requested.emit(applied_preset(preset, self._host.active_filter))


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen') con un host y una configuración de
    # mentira. Ejecutar desde la raíz del proyecto:  python -m controllers.filter_preset_controller
    import os
    from dataclasses import replace

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    from core.catalog.grid_filter import (
        FILTER_ATTRIBUTES,
        FILTER_METADATA,
        FILTER_TEXT,
        NO_FILTER,
        AttributeFilter,
        TextFilter,
    )

    app = QApplication([])

    class _Host:
        def __init__(self) -> None:
            self.active_filter = NO_FILTER
            self.types: tuple[str, ...] = ("photo", "video")
            self.fields: tuple[str, ...] = ("captured_at", "camera_model", "lens_model")

        def active_filter_media_types(self) -> tuple[str, ...]:
            return self.types

        def active_filter_metadata_fields(self) -> tuple[str, ...]:
            return self.fields

    class _Config:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {SETTING_FILTER_PRESETS: None}
            self.writes = 0

        def get(self, key: str, default: Any = None) -> Any:
            return self.data.get(key, default)

        def set(self, key: str, value: Any) -> None:
            self.data[key] = value
            self.writes += 1

    holder = QWidget()  # padre que nunca se muestra: no se crea ninguna ventana
    host, config = _Host(), _Config()
    button = FilterPresetButton(holder)
    controller = FilterPresetController(
        host, button=button, config=config, window=holder, parent=holder
    )
    requested: list[GridFilter] = []
    controller.filter_requested.connect(requested.append)
    answers: dict[str, Any] = {"name": None, "replace": False, "asked": []}
    controller.ask_name = lambda _w: answers["name"]

    def _confirm(_window: QWidget, name: str) -> bool:
        answers["asked"].append(name)
        return answers["replace"]

    controller.confirm_replace = _confirm

    COMMANDS = ("Guardar", "Gestionar", "Restaurar")

    def actions() -> dict[str, bool]:
        """Las entradas del menú (texto -> activa)."""
        return {a.text(): a.isEnabled() for a in button.menu().actions() if not a.isSeparator()}

    def preset_names() -> list[str]:
        """Los ajustes del menú (sin las acciones)."""
        return [name for name in actions() if not name.startswith(COMMANDS)]

    def apply(grid_filter: GridFilter) -> None:
        """Lo que hace 'FilterController' con un filtro: lo guarda el host y se muestra."""
        host.active_filter = grid_filter
        controller.show_filter(grid_filter, enabled=True)

    # 1. «Ninguno» en Imagen: los cinco de fábrica, «Sin filtro», sin guardar ni restaurar
    # (gestionar, sí)
    apply(NO_FILTER)
    assert button.text() == "Sin filtro ▾"
    assert preset_names() == [
        "Columnas de partida", "Ubicación", "Datos de exposición", "Valoradas", "Marcadas",
    ]
    enabled = [k for k, v in actions().items() if v and k.startswith(COMMANDS)]
    assert enabled == ["Gestionar ajustes personalizados…"], enabled

    # 2. Encender «Metadatos» sin tocar nada: coincide con «Columnas de partida»
    apply(NO_FILTER.with_panel(FILTER_METADATA, True))
    assert button.text() == "Columnas de partida ▾", button.text()
    assert actions()["Guardar filtro activo como nuevo ajuste personalizado…"]
    assert not actions()["Restaurar filtro activo a sus valores por defecto"]

    # 3. Elegir «Ubicación»: se pide su filtro; el candado y lo de las demás, igual
    host.active_filter = replace(host.active_filter, locked=True, text=TextFilter(text="boda"))
    button.preset_chosen.emit(1)
    (chosen,) = requested
    assert chosen.active == {FILTER_METADATA} and chosen.locked and chosen.text.text == "boda"
    location = ["country", "region", "city", "sublocation"]
    assert [c.field for c in chosen.metadata.columns] == location
    apply(chosen)
    assert button.text() == "Ubicación ▾"
    # Hay algo que restaurar: «boda» y otras columnas que las de partida
    assert actions()["Restaurar filtro activo a sus valores por defecto"]
    # Elegir un valor en una columna: sigue «Ubicación»; cambiar el campo de una, ya no
    apply(replace(chosen, metadata=chosen.metadata.with_values(0, ["España"])))
    assert button.text() == "Ubicación ▾"
    apply(replace(chosen, metadata=chosen.metadata.with_field(0, "keyword")))
    assert button.text() == "Personalizado ▾"
    apply(chosen)

    # 4. Restaurar: todo vacío, mismas pestañas y candado
    button.reset_requested.emit()
    restored = requested[-1]
    assert restored.active == chosen.active and restored.locked
    assert restored.text == TextFilter() and restored.metadata.columns == ()
    apply(restored)
    assert button.text() == "Columnas de partida ▾"

    # 5. Guardar: se pide el nombre; cancelar no guarda nada
    stars = replace(restored, active=frozenset({FILTER_ATTRIBUTES, FILTER_TEXT}),
                    attributes=AttributeFilter(rating=4), text=TextFilter(text="playa"))
    apply(stars)
    assert button.text() == "Personalizado ▾"
    button.save_requested.emit()
    assert config.writes == 0
    answers["name"] = "  Playa   buena "
    button.save_requested.emit()
    assert config.writes == 1 and button.text() == "Playa buena ▾"
    saved = config.data[SETTING_FILTER_PRESETS]
    assert [p["name"] for p in saved][-1] == "Playa buena" and len(saved) == 6
    assert saved[-1]["filter"]["active"] == ["text", "attributes"]

    # 6. El mismo nombre (otras mayúsculas): se pregunta; «Cancelar» no cambia nada
    apply(replace(stars, attributes=AttributeFilter(rating=5)))
    answers["name"] = "PLAYA BUENA"
    button.save_requested.emit()
    assert answers["asked"] == ["Playa buena"] and config.writes == 1
    assert button.text() == "Personalizado ▾"
    # «Reemplazar»: en su lugar, con el nombre como se ha escrito ahora
    answers["replace"] = True
    button.save_requested.emit()
    assert config.writes == 2 and len(controller.presets) == 6
    assert controller.presets[-1].name == "PLAYA BUENA" and button.text() == "PLAYA BUENA ▾"

    # 6b. Dos con las mismas columnas («Ubicación» y «Mi país», con España): con otro valor,
    # el último elegido
    spain = replace(chosen, metadata=chosen.metadata.with_values(0, ["España"]))
    apply(spain)
    answers["name"] = "Mi país"
    button.save_requested.emit()
    assert button.text() == "Mi país ▾"  # el que coincide del todo
    france = replace(chosen, metadata=chosen.metadata.with_values(0, ["Francia"]))
    apply(france)
    assert button.text() == "Mi país ▾"  # el último guardado
    button.preset_chosen.emit(1)  # «Ubicación»
    apply(requested[-1])
    apply(france)
    assert button.text() == "Ubicación ▾"
    button.preset_chosen.emit(preset_names().index("Mi país"))
    apply(requested[-1])
    assert button.text() == "Mi país ▾"
    apply(france)
    assert button.text() == "Mi país ▾"

    # 7. Un módulo sin fotos: «Datos de exposición» no sale; las posiciones son las de su lista
    host.types, host.fields = ("audio",), ("media_type",)
    apply(NO_FILTER)
    names = preset_names()
    assert "Datos de exposición" not in names and names[2] == "Valoradas", names
    requested.clear()
    button.preset_chosen.emit(2)
    assert requested[0].attributes == AttributeFilter(rating=1)

    # 7b. «Gestionar…»: la ventana recibe TODOS (también los que aquí no valen);
    # «Cancelar» no cambia nada
    assert actions()["Gestionar ajustes personalizados…"]
    seen: list[list[FilterPreset]] = []
    controller.manage = lambda _w, presets: seen.append(presets) or None
    button.manage_requested.emit()
    assert len(seen[0]) == 7 and "Datos de exposición" in [p.name for p in seen[0]]
    assert config.writes == 3
    # «Aceptar»: se guarda la lista nueva; el último elegido renombrado sigue siéndolo
    button.preset_chosen.emit(preset_names().index("Mi país"))
    apply(requested[-1])

    def _manage(_window: QWidget, presets: list[FilterPreset]) -> tuple[list, dict]:
        kept = [p for p in presets if p.name != "Columnas de partida"]
        kept = [replace(p, name="Mi tierra") if p.name == "Mi país" else p for p in kept]
        return kept, {"Mi país": "Mi tierra"}

    controller.manage = _manage
    button.manage_requested.emit()
    stored = [p["name"] for p in config.data[SETTING_FILTER_PRESETS]]
    assert config.writes == 4 and "Columnas de partida" not in stored and "Mi tierra" in stored
    assert button.text() == "Mi tierra ▾" and "Columnas de partida" not in preset_names()
    apply(france)  # otro valor: «Mi tierra» (el último elegido), no «Ubicación»
    assert button.text() == "Mi tierra ▾", button.text()

    # 8. Barra desactivada (sin catálogo): nada se puede pulsar ni pedir (el nombre, sí)
    controller.show_filter(chosen, enabled=False)
    assert not any(v for k, v in actions().items() if k.startswith(COMMANDS))
    requested.clear()
    button.preset_chosen.emit(0)
    button.reset_requested.emit()
    button.save_requested.emit()
    button.manage_requested.emit()
    assert requested == [] and config.writes == 4  # los guardados de antes

    # 9. Al volver a crear el controlador, la lista guardada
    again = FilterPresetController(host, button=FilterPresetButton(holder), config=config,
                                   window=holder, parent=holder)
    assert again.presets == controller.presets

    # Los textos de las preguntas
    assert replace_question("X") == (
        "Ya hay un ajuste llamado «X». ¿Quieres reemplazarlo por el filtro activo?"
    )
    holder.deleteLater()
    print("Autoprueba finalizada correctamente.")
