"""Controlador del panel «Metadatos» de la barra de filtros: recuentos en segundo plano.

El panel ('MetadataFilterPanel') solo muestra y avisa. Aquí:
    - Se le pasa lo que tiene que mostrar ('show_filter', lo llama el 'FilterController'
      cada vez que muestra un filtro): las columnas del filtro del módulo activo o, si aún
      no tiene, las de partida del módulo ('AppModule.filter_metadata_fields'), y los
      tipos del módulo (qué campos ofrece cada columna).
    - Se piden en segundo plano ('execute_async' con 'metadata_values.fetch_metadata_values')
      los valores de las columnas que lo necesitan. Cada columna cuenta sobre el origen
      que muestra la cuadrícula, «Texto», «Atributos» y las columnas de su izquierda (la
      cascada, 'GridFilter.metadata_column_filters'). Se recuerda con qué se contó cada
      columna, así que solo se vuelve a pedir la que cambia: elegir en una columna recuenta
      las de su derecha; escribir en «Texto», todas; cambiar el orden, ninguna. Las
      respuestas que llegan tarde se descartan.
    - Se vuelve a contar todo cuando cambian los datos, aunque no cambie el filtro: al
      recargarse la cuadrícula con el mismo origen y el mismo filtro (tras añadir o
      sincronizar una carpeta) y tras los cambios del usuario ('refresh_counts', lo llama
      el controlador principal con el temporizador de los contadores de la barra izquierda).
    - Solo se cuenta con la pestaña «Metadatos» encendida y la barra activa (con catálogo
      y en un módulo que decide la cuadrícula).
    - Lo que cambia el usuario en el panel se reenvía ('metadata_filter_changed'): el
      'FilterController' lo guarda en el filtro del módulo. Las columnas de partida no se
      guardan hasta que el usuario cambia algo.
    - El alto del panel se guarda en settings.json (uno para todos: 'filter_metadata_height').

Uso (en el controlador principal, solo la conexión):
    self.metadata_filters = MetadataFilterController(
        module_host, panel=MetadataFilterPanel(bar), model=grid_model, config=config,
        parent=self)
    FilterController(..., metadata=self.metadata_filters)
    self.metadata_filters.attach(db)     # al abrir el catálogo;  detach() al cerrarlo
    self.metadata_filters.refresh_counts()  # tras los cambios del usuario

1.0.0 Primera versión (paso A.3, «Metadatos», subpaso 4).

Prueba rápida (desde la raíz del proyecto; no abre ninguna ventana):
    python -m controllers.metadata_filter_controller
"""

__version__ = "1.0.0"
__all__ = ["MetadataFilterController"]

# Librerías estándar
from dataclasses import replace
from functools import partial
from itertools import count
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal

# Módulos del proyecto
from config.app_constants import SETTING_FILTER_METADATA_HEIGHT
from core.catalog.grid_filter import (
    FILTER_METADATA,
    NO_FILTER,
    GridFilter,
    MetadataFilter,
)
from core.catalog.metadata_values import MetadataValues, fetch_metadata_values
from ui_helpers.widgets.metadata_filter_panel import MetadataFilterPanel


class MetadataFilterController(QObject):
    """Recuentos del panel «Metadatos» (ver el docstring del archivo).

    Signals:
        metadata_filter_changed(object): el usuario ha cambiado el panel (un
            'MetadataFilter'); lo guarda el 'FilterController'.
    """

    metadata_filter_changed = Signal(object)

    def __init__(
        self,
        host: Any,
        *,
        panel: MetadataFilterPanel,
        model: Any,
        config: Any,
        parent: QObject | None = None,
    ) -> None:
        """Conecta el panel.

        Args:
            host: El 'ModuleHost' (o algo con 'active_filter_media_types' y
                'active_filter_metadata_fields').
            panel: El panel «Metadatos».
            model: El modelo de la cuadrícula (su 'source', 'filter_rules', 'order' y la
                señal 'modelReset').
            config: Configuración de la aplicación (el alto del panel).
            parent: Objeto padre.
        """
        super().__init__(parent)
        self.panel = panel
        self._host = host
        self._model = model
        self._config = config
        self._db: Any = None
        self._filter: GridFilter = NO_FILTER
        self._shown = MetadataFilter()  # las columnas que se ven (las de partida, si no hay)
        self._enabled = False
        # Con qué se contó cada columna: (origen, filtros de su izquierda, campo)
        self._keys: list[tuple[Any, ...]] = []
        # Última petición de cada columna: solo vale su respuesta
        self._tokens: dict[int, int] = {}
        self._token_counter = count(1)
        # Origen, filtro y orden de la última recarga de la cuadrícula (si se recarga con lo
        # mismo, han cambiado los datos)
        self._grid_state: tuple[Any, ...] | None = None

        panel.metadata_filter_changed.connect(self.metadata_filter_changed)
        panel.height_changed.connect(self._on_height_changed)
        model.modelReset.connect(self._on_grid_reloaded)
        self._restore_height()

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def attach(self, db: Any) -> None:
        """Se ha abierto un catálogo."""
        self._db = db
        self._keys = []
        self._grid_state = None
        self._refresh()

    def detach(self) -> None:
        """Se ha cerrado el catálogo: se descartan las respuestas pendientes."""
        self._db = None
        self._keys = []
        self._tokens.clear()
        self._grid_state = None

    def show_filter(self, grid_filter: GridFilter, *, enabled: bool) -> None:
        """Muestra el filtro del módulo activo y pide lo que haga falta contar.

        Args:
            grid_filter: El filtro del módulo activo.
            enabled: Si la barra está activa (hay catálogo y el módulo decide la cuadrícula).
        """
        self._filter = grid_filter
        self._enabled = enabled
        columns = grid_filter.metadata
        if not columns.columns:  # aún sin elegir: las de partida del módulo
            columns = MetadataFilter.from_fields(self._host.active_filter_metadata_fields())
        self._shown = columns
        self.panel.set_media_types(self._host.active_filter_media_types())
        self.panel.set_filter(columns)
        self._refresh()

    def refresh_counts(self) -> None:
        """Vuelve a contar todas las columnas (tras los cambios del usuario: estrellas,
        palabras clave...). Si el panel no se ve, no hace nada."""
        self._refresh(force=True)

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _refresh(self, *, force: bool = False) -> None:
        """Pide los valores de las columnas que han cambiado (o de todas, con 'force')."""
        if self._db is None or not self._enabled or FILTER_METADATA not in self._filter.active:
            self._keys = []  # al volver a verse, se cuenta todo
            return
        grid_filter = replace(self._filter, metadata=self._shown)
        source = self._model.source
        keys: list[tuple[Any, ...]] = []
        for index, column in enumerate(self._shown.columns):
            filters = grid_filter.metadata_column_filters(index)
            key = (source, filters, column.field)
            keys.append(key)
            if force or index >= len(self._keys) or self._keys[index] != key:
                self._query(index, key, column.values)
        self._keys = keys

    def _query(self, index: int, key: tuple[Any, ...], chosen: frozenset[Any]) -> None:
        """Pide en segundo plano los valores de una columna."""
        source, filters, field_key = key
        token = next(self._token_counter)
        self._tokens[index] = token
        self._db.execute_async(
            fetch_metadata_values,
            source,
            field_key,
            filters,
            chosen,
            on_result=partial(self._on_values, index, token),
            on_error=partial(self._on_error, index, token),
        )

    def _on_values(self, index: int, token: int, values: MetadataValues) -> None:
        if self._db is None or self._tokens.get(index) != token:
            return  # llegó tarde: se pidió otra vez o se cerró el catálogo
        self.panel.set_column_values(index, values)

    def _on_error(self, index: int, token: int, error: Exception) -> None:
        if self._db is not None and self._tokens.get(index) == token:
            logger.warning(f"No se pudieron contar los valores de la columna {index + 1}: {error}")

    def _on_grid_reloaded(self) -> None:
        """La cuadrícula se ha recargado. Con otro origen, filtro u orden, se cuenta lo que
        haya cambiado; con lo mismo, han cambiado los datos: se cuenta todo."""
        state = (self._model.source, self._model.filter_rules, self._model.order)
        same = state == self._grid_state
        self._grid_state = state
        self._refresh(force=same)

    def _restore_height(self) -> None:
        """El alto guardado (si no hay o no vale, el de partida)."""
        height = self._config.get(SETTING_FILTER_METADATA_HEIGHT)
        if isinstance(height, int) and not isinstance(height, bool):
            self.panel.set_panel_height(height)

    def _on_height_changed(self, height: int) -> None:
        self._config.set(SETTING_FILTER_METADATA_HEIGHT, height)


if __name__ == "__main__":
    # Autoprueba SIN ventana (plataforma 'offscreen') con un host, un modelo y una base de
    # datos de mentira. Ejecutar desde la raíz:  python -m controllers.metadata_filter_controller
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    from core.catalog.grid_filter import FILTER_TEXT, TextFilter
    from core.catalog.grid_source import ALL_ITEMS, folder_source
    from core.catalog.metadata_values import MetadataValue
    from ui_helpers.widgets.metadata_filter_panel import DEFAULT_HEIGHT

    app = QApplication([])

    class _Host:
        def __init__(self) -> None:
            self.fields: tuple[str, ...] = ("captured_at", "camera_model", "lens_model")

        def active_filter_media_types(self) -> tuple[str, ...]:
            return ("photo", "video")

        def active_filter_metadata_fields(self) -> tuple[str, ...]:
            return self.fields

    class _Model(QObject):
        modelReset = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.source = ALL_ITEMS
            self.filter_rules: tuple = ()
            self.order = None

    class _Db:
        """Guarda las peticiones; 'answer' responde una como lo haría el gestor."""

        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def execute_async(self, func: object, *args: object, on_result: Any = None,
                          on_error: Any = None) -> None:
            assert func is fetch_metadata_values
            self.calls.append((args, on_result, on_error))

        def fields(self) -> list[str]:
            return [args[1] for args, _ok, _error in self.calls]

        def answer(self, call: tuple, values: MetadataValues) -> None:
            call[1](values)

    class _Config:
        def __init__(self, height: object = None) -> None:
            self.data = {SETTING_FILTER_METADATA_HEIGHT: height}

        def get(self, key: str, default: object = None) -> object:
            return self.data.get(key, default)

        def set(self, key: str, value: object) -> None:
            self.data[key] = value

    host, model, db, config = _Host(), _Model(), _Db(), _Config(260)
    panel = MetadataFilterPanel()
    controller = MetadataFilterController(host, panel=panel, model=model, config=config)
    forwarded: list[MetadataFilter] = []
    controller.metadata_filter_changed.connect(forwarded.append)

    # 1. El alto guardado; uno que no vale se ignora
    assert panel.panel_height == 260
    MetadataFilterController(host, panel=MetadataFilterPanel(), model=model, config=_Config("x"))
    assert MetadataFilterPanel().panel_height == DEFAULT_HEIGHT

    # 2. Sin catálogo, apagada o con la barra desactivada: no se pide nada
    on = NO_FILTER.with_panel(FILTER_METADATA, True)
    controller.show_filter(on, enabled=True)
    assert [c.field for c in panel.metadata_filter.columns] == list(host.fields)  # las de partida
    controller.attach(db)
    assert db.fields() == ["captured_at", "camera_model", "lens_model"]
    db.calls.clear()
    controller.show_filter(NO_FILTER, enabled=True)  # «Metadatos» apagada
    controller.show_filter(on, enabled=False)  # barra desactivada
    assert not db.calls
    controller.show_filter(on, enabled=True)  # al volver a verse, se cuenta todo
    assert len(db.calls) == 3
    first_calls = list(db.calls)
    db.calls.clear()

    # 3. Respuestas: solo la última de cada columna; las que llegan tarde, no
    models = MetadataValues("camera_model", 9, (MetadataValue("EOS R5", 6),))
    controller.show_filter(on, enabled=True)  # lo mismo: no se pide nada
    assert not db.calls
    controller.refresh_counts()  # tras un cambio del usuario: todo otra vez
    assert len(db.calls) == 3
    db.answer(first_calls[1], models)  # la antigua: se descarta
    assert panel._values[1] is None
    db.answer(db.calls[1], models)
    assert panel._values[1] == models
    db.calls.clear()

    # 4. Elegir en una columna: se cuentan las de su derecha (la cascada), no ella
    panel._columns[1].values_changed.emit(frozenset({"EOS R5"}))
    chosen = forwarded[-1]
    assert chosen.columns[1].values == {"EOS R5"} and not db.calls  # lo guarda el FilterController
    controller.show_filter(replace(on, metadata=chosen), enabled=True)
    assert db.fields() == ["lens_model"]
    filters = db.calls[0][0][2]
    assert len(filters) == 1 and filters[0].rules[0].field == "camera_model"
    db.calls.clear()
    # «Texto» encendida con algo escrito: todas, con el texto delante
    texted = replace(on, metadata=chosen, text=TextFilter(text="boda")).with_panel(FILTER_TEXT, True)
    controller.show_filter(texted, enabled=True)
    assert len(db.calls) == 3 and len(db.calls[0][0][2]) == 1
    db.calls.clear()

    # 5. La cuadrícula se recarga: con otro origen, lo que cambia; con lo mismo, todo
    model.source = folder_source(1, "a")
    model.modelReset.emit()
    assert len(db.calls) == 3  # otro origen: todas
    db.calls.clear()
    model.modelReset.emit()  # lo mismo: han cambiado los datos
    assert len(db.calls) == 3
    db.calls.clear()
    model.order = "otro"
    model.modelReset.emit()  # solo el orden: nada que contar
    assert not db.calls

    # 6. El alto, al soltar el borde, se guarda
    panel.height_changed.emit(300)
    assert config.data[SETTING_FILTER_METADATA_HEIGHT] == 300

    # 7. Al cerrar el catálogo, las respuestas pendientes se descartan
    controller.refresh_counts()
    pending = list(db.calls)
    controller.detach()
    db.answer(pending[0], MetadataValues("captured_at", 0, ()))
    assert panel._values[0] is None
    controller.show_filter(on, enabled=True)
    assert len(db.calls) == len(pending)  # sin catálogo, nada
    print("Autoprueba finalizada correctamente.")
