"""Coordinador de los módulos: toolbar de modos, barras laterales y cuadrícula.

Lo crea el controlador principal con la lista de 'registry.create_modules' y se encarga de:

    - La toolbar de modos ('ModeToolbar'): un botón por módulo; al pulsarlo se muestra su
      barra izquierda y su panel derecho.
    - La cuadrícula: solo el módulo ACTIVO decide qué se muestra. Lo que se elige en la
      barra de otro módulo se aplica al volver a él ('current_source').
    - El ciclo de vida del catálogo: 'attach' / 'detach' / 'refresh' / 'apply_settings'
      se reparten a todos los módulos. 'refresh' solo consulta la base de datos para el
      módulo activo: los demás quedan marcados y se refrescan al activarlos.
    - El ORDEN de la cuadrícula de cada módulo: el módulo ofrece sus campos y su orden de
      partida ('sort_fields', 'default_order'); el que elige el usuario ('set_order') se
      guarda por módulo y por catálogo ('ModuleViewState', module_view_state.py). Al
      cambiar de módulo, la cuadrícula
      cambia a la vez de origen y de orden (una sola recarga). 'order_changed' avisa al
      control de la barra inferior.
    - El estado visual de cada módulo, guardado POR CATÁLOGO en settings.json (clave
      'sidebar_state'), con los órdenes elegidos en 'orders':

        {"<carpeta del catálogo>": {"modules": {"catalog": {...}, "image": {...}},
                                    "orders": {"image": {"field": ..., "descending": ...}}}}

      Formato anterior (hasta el 29/10/2026), que se sigue leyendo: el estado de la barra
      del catálogo directamente, {"<carpeta del catálogo>": {...}}. Se toma como el del
      módulo Catálogo y se reescribe con el formato nuevo al cerrar el catálogo.

    - El módulo activo, guardado en settings.json ('active_module', común a todos los
      catálogos): al arrancar se vuelve a él. Si ya no existe, el primero (el Catálogo).

1.5.0 Lo que se guarda por módulo (el orden) pasa a 'ModuleViewState'; sin cambios de
      comportamiento ni en settings.json.
1.4.0 Orden de la cuadrícula por módulo: 'set_order', 'active_order', 'active_sort_fields',
      señal 'order_changed'; se guarda por catálogo ('orders') y se aplica al cambiar de
      módulo y al abrir el catálogo, sin cargar la cuadrícula dos veces.
1.3.1 'show_source' recarga la cuadrícula si ya mostraba ese origen (pulsar otra vez la
      flecha «ver sus fotos» tras quitar la palabra a una foto no la quitaba de la vista).
1.3.0 'show_source': el módulo activo muestra un origen pedido desde fuera de su barra.
1.2.0 Reenvía los 'catalog_edit_requested' de todos los módulos (paso K4c-2).
1.1.0 Se recuerda el módulo activo entre sesiones; al abrir un catálogo, la cuadrícula
      muestra lo que tenga elegido el módulo activo (también si no es el Catálogo).
"""

__version__ = "1.5.0"
__all__ = ["ModuleHost"]

# Librerías estándar
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal
from qtpy.QtWidgets import QStackedWidget, QWidget

# Módulos del proyecto
from config.app_constants import SETTING_ACTIVE_MODULE, SETTING_SIDEBAR_STATE
from controllers.app_modules.base import AppModule
from controllers.app_modules.module_view_state import ModuleViewState
from core.catalog.grid_orders import GridOrder
from core.catalog.grid_source import GridSource
from ui_helpers.helpers.mode_toolbar import MODE_CATALOG, ModeToolbar
from ui_helpers.models.media_grid_model import MediaGridModel

# Clave del nuevo formato guardado (ver el docstring del archivo)
_MODULES_KEY = "modules"
# El formato anterior solo tenía el estado de la barra del catálogo
_LEGACY_MODULE_KEY = MODE_CATALOG


class ModuleHost(QObject):
    """Coordina los módulos de la aplicación (ver el docstring del archivo).

    Signals:
        module_changed(str): ha cambiado el módulo activo (lleva su clave).
        catalog_edit_requested(object, object): un módulo quiere cambiar el catálogo
            (función, argumentos); lo atiende el controlador principal.
        order_changed(object): ha cambiado el orden del módulo activo (un 'GridOrder', o
            None si el módulo no decide el orden). Se emite al cambiar de módulo, al
            elegir otro orden y al abrir o cerrar un catálogo.
    """

    module_changed = Signal(str)
    catalog_edit_requested = Signal(object, object)
    order_changed = Signal(object)

    def __init__(
        self,
        modules: Sequence[AppModule],
        *,
        config: Any,
        grid_model: MediaGridModel,
        sidebar_stack: QStackedWidget,
        info_stack: QStackedWidget,
        info_default_page: QWidget,
        parent: QObject | None = None,
    ) -> None:
        """Monta la toolbar y las barras laterales, y activa el primer módulo.

        Args:
            modules: Módulos en el orden de la toolbar (el primero es el inicial).
            config: Configuración de la aplicación (para guardar el estado por catálogo).
            grid_model: Modelo de la cuadrícula (compartido por todos los módulos).
            sidebar_stack: Donde van las barras laterales izquierdas
                ('stacked_widget_sidebar_catalog').
            info_stack: Donde van los paneles derechos ('stacked_widget_sidebar_metadata').
            info_default_page: Panel derecho de los módulos que no tienen uno propio
                ('page_metadata_default').
            parent: Objeto padre.

        Raises:
            ValueError: Si no hay módulos o hay dos con la misma clave.
        """
        super().__init__(parent)
        if not modules:
            raise ValueError("Hace falta al menos un módulo.")
        keys = [module.key for module in modules]
        if len(set(keys)) != len(keys) or not all(keys):
            raise ValueError(f"Claves de módulo vacías o repetidas: {keys}")

        self._modules: dict[str, AppModule] = {module.key: module for module in modules}
        self._config = config
        self._grid_model = grid_model
        self._sidebar_stack = sidebar_stack
        self._info_stack = info_stack
        self._info_default_page = info_default_page

        self._active: AppModule | None = None
        self._attached = False  # True mientras hay un catálogo abierto
        # Módulos cuya barra hay que releer al activarlos (no se refrescaron por no verse)
        self._dirty: set[str] = set()
        # Lo elegido en cada módulo (el orden) para el catálogo abierto
        self._view_state = ModuleViewState()

        # Barras izquierdas: las que no están ya en el stack (las creadas en código) se
        # añaden. Las de los módulos sin barra las pone 'ModeToolbar' (provisionales)
        pages: dict[str, QWidget] = {}
        for module in modules:
            page = module.sidebar_page()
            if page is None:
                continue
            if sidebar_stack.indexOf(page) < 0:
                sidebar_stack.addWidget(page)
            pages[module.key] = page

        # Paneles derechos propios (los demás usan el panel por defecto)
        for module in modules:
            panel = module.info_panel()
            if panel is not None and info_stack.indexOf(panel) < 0:
                info_stack.addWidget(panel)

        # Lo que se elige en la barra de cada módulo (se sabe cuál lo pide)
        for module in modules:
            module.source_selected.connect(
                lambda source, m=module: self._on_module_source_selected(m, source)
            )
            # Cambios del catálogo pedidos desde una barra (de cualquier módulo)
            module.catalog_edit_requested.connect(self.catalog_edit_requested)

        # Toolbar de modos: activa el primero nada más crearse (antes de conectar su
        # señal), así que el módulo inicial se activa a mano justo después
        self.toolbar = ModeToolbar(
            {module.key: (module.button, module.icon, module.title) for module in modules},
            stack=sidebar_stack,
            pages=pages,
            parent=self,
        )
        # El módulo en el que se cerró la aplicación: se lee ANTES de activar el primero
        # (al activarlo se guarda, y se perdería)
        saved = self._config.get(SETTING_ACTIVE_MODULE, MODE_CATALOG)
        self.toolbar.mode_changed.connect(self._on_mode_changed)
        self._on_mode_changed(self.toolbar.current_mode())
        # Si sigue existiendo, se vuelve a él
        if isinstance(saved, str) and saved in self._modules and saved != self.toolbar.current_mode():
            self.toolbar.set_mode(saved)  # -> '_on_mode_changed'

    # -------------------------------------------------------------------------
    # Consultas
    # -------------------------------------------------------------------------

    @property
    def active_module(self) -> AppModule | None:
        """Módulo activo."""
        return self._active

    def module(self, key: str) -> AppModule | None:
        """Módulo con esa clave (None si no existe)."""
        return self._modules.get(key)

    @property
    def active_order(self) -> GridOrder | None:
        """Orden del módulo activo (None si no decide el orden)."""
        return self._view_state.order_for(self._active) if self._active is not None else None

    def active_sort_fields(self) -> tuple[str, ...]:
        """Campos de orden que ofrece el módulo activo (vacío si no decide el orden)."""
        return self._active.sort_fields() if self._active is not None else ()

    def set_order(self, order: GridOrder) -> None:
        """El usuario ha elegido otro orden para el módulo activo: se recuerda y se aplica.

        Un campo que el módulo no ofrece se ignora (con un aviso en el registro).
        """
        module = self._active
        if module is None:
            return
        try:
            changed = self._view_state.set_order(module, order)
        except ValueError as error:
            logger.warning(str(error))
            return
        if not changed:
            return
        if self._attached:
            self._grid_model.set_order(order)
        self.order_changed.emit(order)

    def show_source(self, source: GridSource) -> None:
        """Muestra un origen pedido desde fuera de la barra (p. ej. la flecha «ver sus
        fotos» del inspector): lo hace el módulo activo, eligiéndolo en su barra.

        Si la cuadrícula ya muestra ese origen, se RECARGA: es una petición expresa de
        verlo, y lo mostrado puede haber cambiado (p. ej. se quitó la palabra a una foto,
        y la cuadrícula no se recarga sola tras los cambios del usuario). 'set_source' no
        recargaría lo mismo, así que se hace aquí.
        """
        if self._active is None or not self._attached:
            return
        already_shown = self._grid_model.source == source
        self._active.show_source(source)
        if already_shown:
            self._grid_model.reload()

    def set_active(self, key: str) -> None:
        """Activa un módulo (como si se pulsara su botón)."""
        self.toolbar.set_mode(key)

    # -------------------------------------------------------------------------
    # Ciclo de vida del catálogo
    # -------------------------------------------------------------------------

    def attach(self, db: Any, catalog_dir: Path) -> None:
        """Se ha abierto un catálogo: se avisa a todos los módulos.

        Llamar DESPUÉS de 'restore_state'. Todos quedan pendientes de refrescar: el activo
        lo hará en el próximo 'refresh' (al terminar de cargar la cuadrícula).
        """
        self._attached = True
        for module in self._modules.values():
            module.attach(db, catalog_dir)
        self._dirty = set(self._modules)
        # La cuadrícula, con lo que tenga elegido el módulo activo. El Catálogo ya lo ha
        # emitido al recuperar su estado, pero otro módulo (p. ej. Imagen con «Todas las
        # imágenes») puede no hacerlo. 'set_source' no recarga si ya es lo que se muestra
        # El orden ya lo fijó 'restore_state' (sin cargar); 'set_view' no recarga si ya
        # es lo que se muestra
        if self._active is not None:
            self._apply_view(self._active)

    def detach(self) -> None:
        """El catálogo se ha cerrado: cada módulo olvida lo suyo (llamar tras 'save_state')."""
        self._attached = False
        self._dirty.clear()
        self._view_state.clear()  # es de cada catálogo
        for module in self._modules.values():
            module.detach()
        self.order_changed.emit(self.active_order)

    def refresh(self) -> None:
        """Refresca la barra del módulo activo; las demás, al activarlas."""
        if not self._attached or self._active is None:
            return
        self._dirty = set(self._modules)
        self._dirty.discard(self._active.key)
        self._active.refresh()

    def apply_settings(self, changed: set[str]) -> None:
        """Pasa a todos los módulos las opciones que han cambiado."""
        for module in self._modules.values():
            module.apply_settings(changed)

    # -------------------------------------------------------------------------
    # Estado guardado por catálogo (settings.json)
    # -------------------------------------------------------------------------

    def save_state(self, catalog_dir: Path) -> None:
        """Guarda el estado de todos los módulos para ese catálogo (antes de 'detach')."""
        modules_state = {}
        for key, module in self._modules.items():
            state = module.save_state()
            if state:  # los módulos sin nada que guardar no ocupan sitio
                modules_state[key] = state

        saved = self._config.get(SETTING_SIDEBAR_STATE, {})
        # Copia nueva: 'ConfigManager.set' compara con el valor anterior para saber si
        # ha cambiado (si se modificara el diccionario que devuelve 'get', no lo notaría)
        states = dict(saved) if isinstance(saved, dict) else {}
        entry: dict[str, Any] = {_MODULES_KEY: modules_state}
        entry.update(self._view_state.to_state())  # los órdenes elegidos ('orders')
        states[str(catalog_dir)] = entry
        try:
            self._config.set(SETTING_SIDEBAR_STATE, states)
        except Exception:  # noqa: BLE001 - no poder guardarlo no debe impedir cerrar
            logger.exception("No se pudo guardar el estado de las barras laterales.")

    def restore_state(self, catalog_dir: Path) -> None:
        """Recupera el estado de cada módulo para ese catálogo (antes de 'attach').

        Un módulo puede emitir 'source_selected' al recuperar lo que tenía elegido: si es
        el activo, la cuadrícula lo muestra ya.
        """
        saved = self._config.get(SETTING_SIDEBAR_STATE, {})
        entry = saved.get(str(catalog_dir)) if isinstance(saved, dict) else None
        self._view_state.restore(entry, self._modules)
        # El orden del módulo activo, en la cuadrícula ANTES de restaurar las barras (sin
        # cargar): el origen que emitan al restaurarse ya se carga en su orden
        order = self.active_order
        if order is not None:
            self._grid_model.set_order(order, reload=False)
        for key, module in self._modules.items():
            module.restore_state(self._module_state(entry, key))
        self.order_changed.emit(order)

    @staticmethod
    def _module_state(entry: object, key: str) -> object:
        """Estado guardado de un módulo dentro de la entrada de un catálogo (o None).

        Entiende el formato nuevo ({"modules": {...}}) y el anterior (el estado de la
        barra del catálogo, sin más).
        """
        if not isinstance(entry, dict):
            return None
        modules_state = entry.get(_MODULES_KEY)
        if isinstance(modules_state, dict):
            return modules_state.get(key)
        # Formato anterior: solo existía la barra del catálogo
        return entry if key == _LEGACY_MODULE_KEY else None

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _on_mode_changed(self, key: str) -> None:
        """Cambia el módulo activo: panel derecho, refresco pendiente y cuadrícula."""
        module = self._modules.get(key)
        if module is None or module is self._active:
            return
        if self._active is not None:
            self._active.deactivated()
        self._active = module

        # Panel derecho: el del módulo o el de por defecto
        panel = module.info_panel()
        self._info_stack.setCurrentWidget(panel if panel is not None else self._info_default_page)

        module.activated()

        # Si su barra no se refrescó mientras no se veía, se refresca ahora
        if self._attached and key in self._dirty:
            self._dirty.discard(key)
            module.refresh()

        # La cuadrícula pasa a mostrar lo que tenga elegido el módulo, en su orden
        if self._attached:
            self._apply_view(module)
        self.order_changed.emit(self._view_state.order_for(module))

        # Se recuerda para el próximo arranque
        try:
            self._config.set(SETTING_ACTIVE_MODULE, key)
        except Exception:  # noqa: BLE001 - no poder guardarlo no debe impedir cambiar
            logger.exception("No se pudo guardar el módulo activo.")

        logger.debug(f"Módulo activo: {key}")
        self.module_changed.emit(key)

    def _apply_view(self, module: AppModule) -> None:
        """La cuadrícula, con el origen y el orden del módulo (una sola recarga).

        Lo que el módulo no decide (None) se queda como estaba. 'set_view' no recarga si
        no cambia nada.
        """
        source = module.current_source()
        order = self._view_state.order_for(module)
        if source is None and order is None:
            return
        self._grid_model.set_view(
            source if source is not None else self._grid_model.source,
            order if order is not None else self._grid_model.order,
        )

    def _on_module_source_selected(self, module: AppModule, source: GridSource) -> None:
        """Un módulo ha elegido otro origen: solo el activo cambia la cuadrícula."""
        if module is self._active:
            self._grid_model.set_source(source)
