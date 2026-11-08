"""Controlador del inspector (panel derecho): qué resumen mostrar y cuándo.

Une tres cosas que no se conocen entre sí:
    - La cuadrícula (vista y modelo): qué hay seleccionado y qué origen se está viendo.
    - 'core/catalog/selection_summary.py': calcula el resumen en la base de datos.
    - 'ui_helpers/inspector/inspector_panel.py': lo muestra.

Cuándo se recalcula (siempre en segundo plano, con 'execute_async'):
    - Al cambiar la selección de la cuadrícula.
    - Al recargarse la cuadrícula (otra carpeta o colección, metadatos leídos...).
    - Al cambiar la disponibilidad de alguna tarjeta (disco desconectado, archivo ausente).
    - Cuando lo pide el controlador principal ('refresh'), p. ej. tras cambiar la biblioteca.

Los avisos seguidos se juntan en uno (temporizador de 'DEBOUNCE_MS'): seleccionar con el
ratón arrastrando o con Mayús + flechas no lanza una consulta por cada paso. Las respuestas
que llegan tarde (se pidió otra después) se descartan con un contador de generación.

Sin selección, el resumen es el del origen que se está viendo ('fetch_source_summary').

Datos propios de las secciones (p. ej. «Metadatos»): después de mostrar el resumen, se
preguntan al panel ('data_requests') y cada función se ejecuta también en segundo plano;
su resultado se entrega a su sección ('deliver_data'), con el mismo contador de generación
(si entretanto cambió la selección, se descarta). Si una sección pide sus datos otra vez
(p. ej. al cambiar de vista), el panel avisa ('refresh_requested') y se recalcula todo.

Módulo activo ('set_module'): el panel muestra las secciones de ese módulo (p. ej. en
Imagen, el editor de palabras clave); al cambiar, se recalcula.

Estado guardado por catálogo ('save_state' / 'restore_state'): lo desplegado del árbol
de palabras clave del inspector (estado 'INSPECTOR' de 'keyword_expansion'), para que se
abra como se dejó. El controlador principal lo pasa al 'ModuleHost', que lo escribe en
settings.json junto al estado de las barras (clave 'inspector').

Cambios pedidos por las secciones ('edit_requested', p. ej. asignar una palabra clave):
se ejecutan en segundo plano DE UNO EN UNO y en orden (marcar y desmarcar deprisa no se
adelantan entre sí). Si cambian algo, se avisa con 'user_data_changed' (el controlador
principal programa la escritura en los archivos y refresca la barra lateral) y el
inspector se recalcula.

1.6.0 Guarda y recupera lo desplegado del árbol de palabras clave ('save_state',
      'restore_state'; antes lo hacía el módulo Imagen) y lo olvida al cerrar el catálogo.
1.5.0 Reenvía 'navigate_requested' de las secciones.
1.4.0 Tarjetas soltadas en una sección ('drop_edit_requested'), con la comprobación de
      que son del catálogo abierto.
1.3.0 'request_edit': la cola de cambios también la usan las barras de los módulos (p. ej.
      el menú del árbol de palabras clave); señal 'edit_finished' tras cada cambio (para
      refrescar la barra aunque no cambie ningún archivo: crear o purgar palabras); los
      errores previstos ('KeywordError') se muestran tal cual (paso K4c-2).
1.2.0 Módulo activo ('set_module') y cambios de las secciones ('edit_requested',
      señal 'user_data_changed'); paso K4b, palabras clave.
1.1.0 Datos propios de las secciones (sección «Metadatos»).

Acciones del panel: «Mostrar en el Explorador» (botón de la carpeta) se atiende aquí.
"""

__version__ = "1.6.0"
__all__ = ["STATE_KEY", "InspectorController"]

# Librerías estándar
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Librerías de terceros
from loguru import logger
from qtpy.QtCore import QObject, QTimer, Signal
from qtpy.QtWidgets import QListView

# Módulos del proyecto
from core.catalog.keywords import KeywordError
from core.catalog.selection_summary import (
    SelectionSummary,
    fetch_selection_summary,
    fetch_source_summary,
)
from ui_helpers.helpers.keyword_expansion import INSPECTOR, keyword_expansion
from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME, reveal_in_file_manager
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.inspector.inspector_panel import InspectorPanel
from ui_helpers.models.media_grid_model import MediaGridModel
from ui_helpers.models.media_roles import ROLE_AVAILABILITY

# Clave del inspector dentro de la entrada de cada catálogo en settings.json ('sidebar_state')
STATE_KEY = "inspector"
# Lo desplegado del árbol de palabras clave del inspector (lista de 'keywords.id')
_EXPANDED_KEY = "expanded_keywords"
# Dónde lo guardaba el módulo Imagen hasta el 08/11/2026 (estado del módulo 'image')
_LEGACY_EXPANDED_KEY = "inspector_expanded_keywords"

# Espera (ms) desde el último aviso hasta pedir el resumen
DEBOUNCE_MS = 120


class InspectorController(QObject):
    """Mantiene el inspector al día con la selección de la cuadrícula (ver el módulo).

    Signals:
        user_data_changed(int): un cambio ha dejado archivos pendientes (cuántos).
        edit_finished(): ha terminado un cambio (haya cambiado algún archivo o no).
        navigate_requested(object): una sección quiere que la cuadrícula muestre otro
            origen ('GridSource'); lo atiende el controlador principal (módulo activo).
    """

    user_data_changed = Signal(int)
    edit_finished = Signal()
    navigate_requested = Signal(object)

    def __init__(
        self,
        panel: InspectorPanel,
        view: QListView,
        model: MediaGridModel,
        message_box: MessageBoxHelper,
        parent: QObject | None = None,
    ) -> None:
        """Conecta el panel con la cuadrícula (todavía sin catálogo: ver 'attach').

        Args:
            panel: El inspector que se actualiza.
            view: Vista de la cuadrícula (su selección). Ya debe tener el modelo puesto.
            model: Modelo de la cuadrícula (los 'id' de las filas y el origen que se ve).
            message_box: Para avisar si no se puede abrir una carpeta.
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._panel = panel
        self._view = view
        self._model = model
        self._message_box = message_box
        self._db: Any = None
        self._generation = 0  # sube con cada petición: las respuestas antiguas se ignoran
        # Cambios pedidos por las secciones, en orden; solo uno en marcha a la vez
        self._edits: deque[tuple[Callable[..., Any], tuple[Any, ...]]] = deque()
        self._edit_running = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._request_summary)

        # Avisos de la cuadrícula
        selection = view.selectionModel()
        if selection is not None:
            selection.selectionChanged.connect(self._schedule)
        model.modelReset.connect(self._schedule)  # recarga (la selección se pierde)
        model.dataChanged.connect(self._on_data_changed)

        panel.reveal_requested.connect(self._on_reveal_requested)
        panel.refresh_requested.connect(self._schedule)  # p. ej. otra vista en «Metadatos»
        panel.edit_requested.connect(self._on_edit_requested)
        panel.drop_edit_requested.connect(self._on_drop_edit_requested)
        panel.navigate_requested.connect(self.navigate_requested)

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def attach(self, db: Any) -> None:
        """Catálogo abierto: a partir de ahora se calculan los resúmenes."""
        self._db = db
        self._schedule()

    def detach(self) -> None:
        """Catálogo cerrado: se descartan las respuestas pendientes y se vacía el panel."""
        self._db = None
        self._generation += 1
        self._timer.stop()
        self._edits.clear()
        self._edit_running = False
        self._panel.show_no_catalog()
        keyword_expansion(INSPECTOR).replace(())  # los id son de cada catálogo

    # -------------------------------------------------------------------------
    # Estado guardado por catálogo
    # -------------------------------------------------------------------------

    def save_state(self) -> dict[str, Any]:
        """Lo que se guarda en la entrada del catálogo (settings.json): lo desplegado del
        árbol de palabras clave del inspector."""
        return {STATE_KEY: {_EXPANDED_KEY: sorted(keyword_expansion(INSPECTOR).ids())}}

    def restore_state(self, entry: object) -> None:
        """Recupera lo guardado con 'save_state' en la entrada de un catálogo (llamar al
        abrirlo). Entiende también el formato anterior al 08/11/2026, cuando lo guardaba el
        módulo Imagen. Lo que no se entienda, se ignora."""
        expanded: object = None
        if isinstance(entry, dict):
            own = entry.get(STATE_KEY)
            if isinstance(own, dict):
                expanded = own.get(_EXPANDED_KEY)
            else:
                modules = entry.get("modules")
                image = modules.get("image") if isinstance(modules, dict) else None
                expanded = image.get(_LEGACY_EXPANDED_KEY) if isinstance(image, dict) else None
        ids = [value for value in expanded if isinstance(value, int)] if isinstance(expanded, list) else []
        keyword_expansion(INSPECTOR).replace(ids)

    def refresh(self) -> None:
        """Vuelve a calcular el resumen (p. ej. tras cambiar la biblioteca de lo seleccionado)."""
        self._schedule()

    def set_module(self, module: str) -> None:
        """Ha cambiado el módulo activo: otras secciones (p. ej. el editor en Imagen)."""
        self._panel.set_module(module)
        self._schedule()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _schedule(self, *_args: object) -> None:
        """Pide el resumen dentro de un momento (junta los avisos seguidos)."""
        if self._db is not None:
            self._timer.start()

    def _on_data_changed(self, _first: object, _last: object, roles: list[int] = ()) -> None:
        """Solo interesa la disponibilidad (las miniaturas también avisan, y muy a menudo)."""
        if ROLE_AVAILABILITY in (roles or ()):
            self._schedule()

    def _selected_ids(self) -> list[int]:
        """'id' de las tarjetas seleccionadas, en el orden de la cuadrícula."""
        selection = self._view.selectionModel()
        if selection is None:
            return []
        rows = sorted({index.row() for index in selection.selectedIndexes()})
        return self._model.media_ids(rows)

    def _request_summary(self) -> None:
        """Lanza la consulta del resumen (selección u origen) en segundo plano."""
        if self._db is None:
            return
        self._generation += 1
        generation = self._generation
        ids = self._selected_ids()
        if ids:
            function, argument = fetch_selection_summary, ids
        else:
            function, argument = fetch_source_summary, self._model.source
        self._db.execute_async(
            function,
            argument,
            on_result=lambda summary: self._on_summary(generation, summary, ids),
            on_error=lambda error: self._on_error(generation, error),
        )

    def _on_summary(self, generation: int, summary: SelectionSummary, ids: list[int]) -> None:
        """Muestra el resumen y pide los datos propios de las secciones visibles."""
        if generation != self._generation or self._db is None:
            return
        self._panel.show_summary(summary)
        for section, function, arguments in self._panel.data_requests(summary, ids):
            self._db.execute_async(
                function,
                *arguments,
                on_result=lambda result, section=section: self._on_section_data(
                    generation, section, result
                ),
                on_error=lambda error: self._on_error(generation, error),
            )

    def _on_section_data(self, generation: int, section: Any, result: Any) -> None:
        """Llegan los datos de una sección: se entregan si siguen siendo los de ahora."""
        if generation == self._generation and self._db is not None:
            self._panel.deliver_data(section, result)

    def _on_error(self, generation: int, error: Exception) -> None:
        if generation == self._generation:
            logger.error(f"No se pudo calcular el resumen del inspector: {error}")

    def request_edit(self, function: Callable[..., Any], arguments: tuple[Any, ...]) -> None:
        """Cambia el catálogo con la cola del inspector (en orden, uno a uno; avisa de los
        errores y refresca al terminar). La usan las secciones y las barras de los módulos."""
        self._on_edit_requested(function, arguments)

    def _on_edit_requested(self, function: Callable[..., Any], arguments: tuple[Any, ...]) -> None:
        """Una sección quiere cambiar el catálogo: a la cola (se ejecutan en orden)."""
        if self._db is None:
            return
        self._edits.append((function, tuple(arguments)))
        self._run_next_edit()

    def _on_drop_edit_requested(
        self, function: Callable[..., Any], arguments: tuple[Any, ...], drag: Any
    ) -> None:
        """Tarjetas soltadas en una sección: si son de este catálogo, a la cola."""
        if self._db is None:
            return
        if getattr(drag, "catalog", None) != self._model.catalog_key():
            # P. ej. tarjetas arrastradas desde otra ventana con otro catálogo
            self._message_box.warning("Esos elementos son de otro catálogo: no se les puede asignar.")
            return
        self._on_edit_requested(function, arguments)

    def _run_next_edit(self) -> None:
        """Lanza el siguiente cambio de la cola, si no hay otro en marcha."""
        if self._edit_running or not self._edits or self._db is None:
            return
        function, arguments = self._edits.popleft()
        self._edit_running = True
        self._db.execute_async(
            function, *arguments, on_result=self._on_edit_done, on_error=self._on_edit_error
        )

    def _on_edit_done(self, changed: Any) -> None:
        """Cambio guardado: aviso (escritura en archivos, barra lateral) y recálculo."""
        self._edit_running = False
        count = changed if isinstance(changed, int) else 0
        if count:
            self.user_data_changed.emit(count)
        self.edit_finished.emit()
        self._schedule()  # también sin cambios: la sección vuelve a mostrar lo que hay
        self._run_next_edit()

    def _on_edit_error(self, error: Exception) -> None:
        """No se pudo guardar: se avisa y el inspector vuelve a mostrar lo guardado."""
        self._edit_running = False
        if isinstance(error, KeywordError):
            # Error previsto (nombre repetido, mover dentro de sí misma...): su mensaje ya
            # es para el usuario
            logger.info(f"Cambio de palabras clave no válido: {error}")
            self._message_box.warning(str(error))
        else:
            logger.error(f"No se pudo guardar el cambio del inspector: {error}")
            self._message_box.warning(f"No se pudo guardar el cambio en el catálogo:\n{error}")
        self.edit_finished.emit()
        self._schedule()
        self._run_next_edit()

    def _on_reveal_requested(self, target: Path) -> None:
        """Botón de la carpeta: abre el explorador con el archivo (o la carpeta) seleccionado."""
        try:
            exists = Path(target).exists()
        except OSError:
            exists = False  # p. ej. una unidad de red que no responde
        if not exists:
            self._message_box.warning(
                f"No se encuentra en el disco (¿se ha movido, renombrado o borrado?):\n{target}"
            )
            return
        if not reveal_in_file_manager(target):
            self._message_box.warning(f"No se pudo abrir {FILE_MANAGER_NAME}:\n{target}")
