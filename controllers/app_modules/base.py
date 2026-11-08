"""Base de los módulos de la aplicación (Catálogo, Imagen, Vídeo, Audio...).

Un MÓDULO es cada una de las secciones a las que se entra con los botones de la toolbar de
la izquierda. Todos comparten el mismo esqueleto de la ventana, y cada uno decide el
CONTENIDO de cada zona:

    ┌────┬──────────────┬──────────────────────────┬─────────────────┐
    │ M  │ IZQUIERDA    │ CENTRO                   │ DERECHA         │
    │ o  │ ¿qué veo?    │ ¿cómo lo veo?            │ ¿qué es esto?   │
    │ d  │ navegar y    │ cuadrícula (compartida   │ ficha y         │
    │ o  │ elegir       │ por todos los módulos)   │ metadatos       │
    │ s  │ (GridSource) │                          │ (opcional)      │
    └────┴──────────────┴──────────────────────────┴─────────────────┘

Qué aporta cada módulo (sobrescribiendo los métodos de 'AppModule'):
    - 'sidebar_page()':   su barra lateral izquierda (None = página provisional).
    - 'info_panel()':     su panel derecho (None = el panel por defecto).
    - 'current_source()': qué muestra la cuadrícula cuando el módulo está activo (None =
                          el módulo no decide: la cuadrícula se queda como estaba).
    - 'sort_fields()' y 'default_order()': por qué campos se puede ordenar su cuadrícula
                          y su orden de partida ('core/catalog/grid_orders.py'). El orden
                          que elige el usuario lo guarda el 'ModuleHost', por módulo y por
                          catálogo. Sin campos, el módulo no decide el orden.
    - 'views()' y 'default_view()': qué vistas del centro ofrece (cuadrícula, individual...;
                          'center_views.py') y con cuál empieza. La elegida también se
                          recuerda por módulo y por catálogo.
    - 'filter_media_types()': qué tipos ofrece la fila «Atributos» de la barra de filtros
                          (vacío = ninguno).
    - Señal 'source_selected': el usuario ha elegido otra cosa en su barra.
    - Señal 'catalog_edit_requested(función, argumentos)': el usuario quiere cambiar el
      catálogo desde la barra (p. ej. renombrar una palabra clave). La función recibe la
      conexión y los argumentos; la ejecuta la cola de cambios del inspector, que avisa
      de los errores y refresca después (ver 'InspectorController.request_edit').
    - Ciclo de vida del catálogo: 'attach', 'detach', 'refresh', 'save_state',
      'restore_state' y 'apply_settings' (ver cada método).

Quién los coordina: 'module_host.ModuleHost' (toolbar, barras laterales, cuadrícula y
estado guardado). Dónde se da de alta un módulo nuevo: 'registry.py'.

1.5.0 'filter_media_types': los tipos de la fila «Atributos» (paso A.3).
1.4.0 'views' y 'default_view': las vistas del centro de cada módulo (paso A.1).
1.3.0 'sort_fields' y 'default_order': el orden de la cuadrícula de cada módulo.
1.2.0 'show_source': mostrar un origen elegido fuera de la barra (p. ej. desde el inspector).
1.1.0 Señal 'catalog_edit_requested' (paso K4c-2).

Los módulos son la capa que une la interfaz de su barra lateral con 'core/' (como
'controllers/collection_actions.py'). Las operaciones con el catálogo entero (añadir o
sincronizar una carpeta, trabajos en segundo plano...) siguen en el controlador principal.
"""

__version__ = "1.5.0"
__all__ = ["AppModule", "ModuleContext"]

# Librerías estándar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, Signal
from qtpy.QtWidgets import QListView, QToolButton, QWidget

# Módulos del proyecto
from controllers.app_modules.center_views import CenterView
from core.catalog.grid_orders import GridOrder
from core.catalog.grid_source import GridSource
from ui_helpers.helpers.grid_actions import GridActions
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.models.media_grid_model import MediaGridModel


@dataclass(frozen=True, slots=True)
class ModuleContext:
    """Lo que la ventana principal comparte con todos los módulos.

    Attributes:
        window: Ventana principal (padre de los diálogos y dueña de la barra de estado).
        config: Configuración de la aplicación ('config.app_config.config').
        message_box: Ayudante de mensajes de la ventana.
        grid_view: Vista de la cuadrícula (compartida por todos los módulos).
        grid_model: Modelo de la cuadrícula (compartido).
        grid_actions: Atajos de teclado y menú contextual de la cuadrícula.
    """

    window: QWidget
    config: Any
    message_box: MessageBoxHelper
    grid_view: QListView
    grid_model: MediaGridModel
    grid_actions: GridActions


class AppModule(QObject):
    """Un módulo de la aplicación (ver el docstring del archivo).

    Las subclases definen 'key', 'title' e 'icon' (o los reciben en el constructor, como
    'PlaceholderModule') y sobrescriben los métodos que necesiten: todos tienen una
    versión por defecto que no hace nada.

    Signals:
        source_selected(object): el usuario ha elegido en la barra del módulo otro origen
            (un 'GridSource'). El 'ModuleHost' lo pasa a la cuadrícula si el módulo es el
            activo; si no, lo aplicará al activarlo (con 'current_source').
    """

    source_selected = Signal(object)
    # El usuario quiere cambiar el catálogo desde la barra: (función, argumentos)
    catalog_edit_requested = Signal(object, object)

    # Clave estable del módulo (se guarda en settings.json): 'catalog', 'image'...
    key: str = ""
    # Nombre para el usuario (tooltip del botón)
    title: str = ""
    # Ruta del icono SVG del botón (p. ej. 'AppIcons.LIB_ALL'), o None (se ve su inicial)
    icon: str | None = None

    def __init__(
        self, context: ModuleContext, *, button: QToolButton, parent: QObject | None = None
    ) -> None:
        """Prepara el módulo (todavía sin catálogo: ver 'attach').

        Args:
            context: Lo que comparte la ventana principal.
            button: Botón de la toolbar que activa el módulo.
            parent: Objeto padre (por defecto, la ventana principal).
        """
        super().__init__(parent if parent is not None else context.window)
        self.context = context
        self.button = button

    # -------------------------------------------------------------------------
    # Interfaz: qué pone el módulo en cada zona de la ventana
    # -------------------------------------------------------------------------

    def sidebar_page(self) -> QWidget | None:
        """Barra lateral izquierda del módulo (None = página provisional "próximamente")."""
        return None

    def info_panel(self) -> QWidget | None:
        """Panel lateral derecho del módulo (None = el panel por defecto de la ventana)."""
        return None

    def current_source(self) -> GridSource | None:
        """Qué debe mostrar la cuadrícula con este módulo activo.

        None = el módulo no decide (p. ej. un módulo provisional, o uno que aún espera
        datos de la base de datos): la cuadrícula se queda como estaba.
        """
        return None

    def sort_fields(self) -> tuple[str, ...]:
        """Campos por los que se puede ordenar su cuadrícula (claves de 'SORT_FIELDS', en
        el orden del desplegable). Vacío = el módulo no decide el orden (p. ej. uno
        provisional, o una vista sin cuadrícula): se queda el que hubiera."""
        return ()

    def default_order(self) -> GridOrder | None:
        """Orden de partida (hasta que el usuario elige otro). Su campo debe estar en
        'sort_fields'. None = el módulo no decide el orden."""
        return None

    def views(self) -> tuple[CenterView, ...]:
        """Vistas del centro que ofrece, en el orden de sus botones en la barra inferior.

        De momento, todos los módulos ofrecen la cuadrícula y la vista individual (la lista
        y el mapa llegarán con los módulos Audio y Tracks).
        """
        return (CenterView.GRID, CenterView.SINGLE)

    def default_view(self) -> CenterView:
        """Vista con la que empieza (hasta que el usuario elige otra). Debe estar en
        'views'."""
        return CenterView.GRID

    def filter_media_types(self) -> tuple[str, ...]:
        """Tipos que ofrece la fila «Atributos» de la barra de filtros (valores de
        'MediaType', en su orden). Por defecto, ninguno."""
        return ()

    def show_source(self, source: GridSource) -> None:
        """Mostrar un origen pedido desde fuera de la barra (p. ej. la flecha «ver sus
        fotos» del inspector). Lo normal es elegirlo en la barra, que emite
        'source_selected'. Por defecto, nada."""

    # -------------------------------------------------------------------------
    # Ciclo de vida del catálogo (el 'ModuleHost' llama a todos los módulos)
    # -------------------------------------------------------------------------

    def attach(self, db: Any, catalog_dir: Path) -> None:
        """Se ha abierto un catálogo (se llama DESPUÉS de 'restore_state').

        Args:
            db: Gestor de la base de datos ('CatalogDatabaseManager').
            catalog_dir: Carpeta del catálogo.
        """

    def detach(self) -> None:
        """El catálogo se ha cerrado: el módulo olvida todo lo suyo y vacía su barra.

        Se llama DESPUÉS de 'save_state'.
        """

    def refresh(self) -> None:
        """Relee en segundo plano lo que muestra su barra (contadores, árboles...).

        El 'ModuleHost' solo lo llama en el módulo ACTIVO; los demás se refrescan al
        activarlos (así no se hacen consultas para barras que no se ven).
        """

    def save_state(self) -> dict:
        """Estado visual del módulo para el catálogo abierto (lo desplegado, lo elegido...).

        Debe poder guardarse en JSON. Vacío = nada que guardar.
        """
        return {}

    def restore_state(self, state: object) -> None:
        """Recupera lo guardado con 'save_state' (llamar al abrir el catálogo).

        Debe tolerar datos incompletos, de otra versión o None (lo que no entienda, se
        ignora).
        """

    def apply_settings(self, changed: set[str]) -> None:
        """Se han cambiado opciones en la ventana de opciones.

        Args:
            changed: Claves de settings.json que han cambiado.
        """

    def activated(self) -> None:
        """El módulo pasa a ser el activo (su barra ya se ve)."""

    def deactivated(self) -> None:
        """El módulo deja de ser el activo."""
