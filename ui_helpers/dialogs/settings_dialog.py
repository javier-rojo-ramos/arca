"""Ventana de opciones: columna de secciones a la izquierda y opciones en el centro.

Estructura (pensada para crecer sin tocar la ventana):

    SettingsDialog
    ├── columna izquierda   QListWidget con una fila (icono + nombre) por sección
    ├── cuerpo central      QStackedWidget con una página por sección
    └── abajo               Aceptar / Cancelar

Cada sección es una clase que hereda de 'SettingsPage' y sabe:
    - 'load()': poner en sus controles lo que hay en settings.json.
    - 'save()': guardar en settings.json lo que el usuario cambió y devolver qué claves
      han cambiado (el controlador reacciona a eso: p. ej. lanzar la escritura de los
      datos del usuario si se acaba de activar).

Cómo añadir una sección:
    1. Crear una clase 'XxxPage(SettingsPage)' con 'title', 'icon' y sus controles.
    2. Añadirla a 'PAGES'.
Cómo añadir una opción a una sección existente: crear el control en su '__init__',
leerlo en 'load()' y guardarlo en 'save()' (y añadir la clave a
'ConfigManager.DEFAULTS' con su valor por defecto).

Los cambios se guardan solo al pulsar "Aceptar"; "Cancelar" no guarda nada.

1.4.1 La aceleración por GPU, sin elegir, según el sistema; «Aceptar» sin tocarla no la
      guarda ni avisa.
1.4.0 "General": opción «Usar aceleración por GPU si está disponible» (al volver a abrir
      la aplicación; SETTING_GPU_RENDERING).
1.3.0 Sección "Mapa": capas propias (añadir, cambiar, quitar) y caché de teselas (tamaño
      máximo, lo que ocupa y vaciarla). Docs/MAPA.md, paso 2.4.
1.2.0 "Metadatos": opción «Preguntar antes de cambiar varios archivos con valores
      distintos» (el aviso «Edición múltiple»; SETTING_CONFIRM_MULTI_EDIT); la ayuda de
      «Escribir los cambios en los archivos» cita también las palabras clave y los
      metadatos editados.
1.1.1 Texto de ayuda con el nombre nuevo del archivo de carpeta ('.arca.json').
1.1.0 Sección "Catálogo": mostrar o no los elementos de las subcarpetas.
"""

__version__ = "1.4.1"
__all__ = [
    "PAGES",
    "CatalogPage",
    "GeneralPage",
    "MapSettingsPage",
    "MetadataPage",
    "SettingsDialog",
    "SettingsPage",
]

# Librerías estándar
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, QSize, Qt, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from config import app_paths
from config.app_constants import (
    SETTING_CONFIRM_MULTI_EDIT,
    SETTING_GPU_RENDERING,
    SETTING_MAP_CACHE_MB,
    SETTING_MAP_USER_LAYERS,
    SETTING_SHOW_SUBFOLDER_ITEMS,
    SETTING_WRITE_USER_DATA_TO_FILES,
    AppIcons,
)
from core.maps.tile_layers import (
    TileLayer,
    is_valid_key,
    new_user_key,
    user_layers_from_settings,
    user_layers_to_settings,
)
from core.maps.tile_store import TileStorageError, TileStore
from ui_helpers.dialogs.map_layer_dialog import MapLayerDialog
from ui_helpers.helpers.gpu_composition import default_gpu_setting
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_message import MessageBoxHelper
from ui_helpers.inspector.formatting import format_size


class SettingsPage(QWidget):
    """Una sección de la ventana de opciones (clase base).

    Attributes:
        title: Nombre de la sección (columna izquierda y cabecera de la página).
        icon: Ruta del icono SVG (una constante de 'AppIcons').
    """

    title: ClassVar[str] = ""
    icon: ClassVar[str] = AppIcons.SETTINGS

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        """Crea la página con su cabecera; las subclases añaden sus controles a 'self.body'.

        Args:
            config: Gestor de settings.json ('ConfigManager').
            context: Datos de la aplicación que la página puede mostrar (p. ej. la
                carpeta del catálogo abierto).
            parent: Widget padre.
        """
        super().__init__(parent)
        self.config = config
        self.context = context

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QLabel(self.title)
        font = QFont(header.font())
        if font.pointSizeF() > 0:  # -1 si la fuente se definió en píxeles
            font.setPointSizeF(font.pointSizeF() * 1.3)
        font.setBold(True)
        header.setFont(font)
        layout.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # Las subclases añaden aquí sus controles
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        layout.addLayout(self.body)
        layout.addStretch(1)

    def load(self) -> None:
        """Pone en los controles los valores de settings.json (por defecto, nada)."""

    def save(self) -> set[str]:
        """Guarda en settings.json lo que cambió. Devuelve las claves cambiadas."""
        return set()

    @staticmethod
    def make_help_label(text: str) -> QLabel:
        """Texto explicativo de una opción: más pequeño, atenuado y con saltos de línea."""
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setContentsMargins(22, 0, 0, 4)  # alineado con el texto del QCheckBox
        label.setEnabled(False)  # gris de la paleta: se lee como ayuda, no como opción
        return label

    def _load_bool(self, key: str, checkbox: QCheckBox, default: bool) -> None:
        """Pone en un QCheckBox el valor de settings.json (el de por defecto si no es bool)."""
        value = self.config.get(key, default)
        checkbox.setChecked(value if isinstance(value, bool) else default)

    def _save_bool(self, key: str, checkbox: QCheckBox) -> set[str]:
        """Guarda un QCheckBox en settings.json si cambió. Devuelve {key} o vacío."""
        value = checkbox.isChecked()
        if self.config.get(key) == value:
            return set()
        self.config.set(key, value)
        return {key}


class GeneralPage(SettingsPage):
    """Sección "General": dónde guarda las cosas la aplicación y la aceleración por GPU."""

    title = "General"
    icon = AppIcons.SETTINGS_APP

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(config, context, parent)

        catalog_dir = context.get("catalog_dir")
        rows = (
            ("Catálogo abierto", str(catalog_dir) if catalog_dir else "(ninguno)"),
            ("Archivo de opciones", str(app_paths.CONFIG_FILE)),
            ("Versión", app_paths.APP_VERSION),
        )
        for caption, value in rows:
            label = QLabel(f"<b>{caption}</b><br>{_escape(value)}")
            label.setWordWrap(True)
            # Se puede seleccionar y copiar la ruta
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.body.addWidget(label)

        # Texto de la opción, del autor (13/11/2026)
        self.body.addSpacing(6)
        self.check_gpu = QCheckBox("Usar aceleración por GPU si está disponible")
        self.body.addWidget(self.check_gpu)
        self.body.addWidget(
            self.make_help_label(
                "La ventana se dibuja con la tarjeta gráfica: las fotos se mueven con suavidad "
                "(también a 1:1 en la vista individual) y la ventana no parpadea al abrir el "
                "mapa. Desactívala si la ventana se ve mal (puede pasar en máquinas virtuales "
                "o con escritorio remoto). Viene activada en Windows y macOS, y desactivada en "
                "Linux (aún sin probar allí).<br>"
                "Se aplica al volver a abrir la aplicación. Si con ella la ventana no llega a "
                "verse, se puede abrir sin ella añadiendo <i>--sin-gpu</i> al arrancar."
            )
        )

    def _gpu_setting(self) -> bool:
        """La opción tal como se aplica: la elegida o, si no, la del sistema."""
        value = self.config.get(SETTING_GPU_RENDERING)
        return value if isinstance(value, bool) else default_gpu_setting()

    def load(self) -> None:
        self.check_gpu.setChecked(self._gpu_setting())

    def save(self) -> set[str]:
        # Solo si cambia lo que se aplica: «Aceptar» sin tocarla no la guarda (sigue
        # dependiendo del sistema) ni avisa de volver a abrir la aplicación
        value = self.check_gpu.isChecked()
        if value == self._gpu_setting():
            return set()
        self.config.set(SETTING_GPU_RENDERING, value)
        return {SETTING_GPU_RENDERING}


class CatalogPage(SettingsPage):
    """Sección "Catálogo": cómo se muestran las carpetas de la barra lateral."""

    title = "Catálogo"
    icon = AppIcons.LIB_ALL

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(config, context, parent)

        self.check_show_subfolders = QCheckBox("Mostrar los elementos de las subcarpetas")
        self.body.addWidget(self.check_show_subfolders)
        self.body.addWidget(
            self.make_help_label(
                "Al elegir una carpeta en la sección <b>Carpetas</b>, la cuadrícula muestra "
                "también lo que hay en sus subcarpetas, y el número de cada carpeta las "
                "incluye (como <i>Mostrar fotos en subcarpetas</i> de Lightroom).<br>"
                "Si se desactiva, cada carpeta muestra y cuenta solo sus propios archivos."
            )
        )

    def load(self) -> None:
        self._load_bool(SETTING_SHOW_SUBFOLDER_ITEMS, self.check_show_subfolders, True)

    def save(self) -> set[str]:
        return self._save_bool(SETTING_SHOW_SUBFOLDER_ITEMS, self.check_show_subfolders)


class MetadataPage(SettingsPage):
    """Sección "Metadatos": guardar los cambios también en los archivos y preguntar antes de
    poner el mismo metadato a varios archivos que lo tienen distinto."""

    title = "Metadatos"
    icon = AppIcons.LIB_IMAGE

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(config, context, parent)

        self.check_write_files = QCheckBox("Escribir los cambios en los archivos")
        self.body.addWidget(self.check_write_files)
        self.body.addWidget(
            self.make_help_label(
                "La valoración, la marca, la etiqueta de color, las palabras clave y los "
                "metadatos editados en el inspector (título, pie, ubicación...) se guardan "
                "también fuera del catálogo, para no perderlos si hay que volver a crearlo:"
                "<ul>"
                "<li><b>JPEG, TIFF, PNG, WebP, DNG, HEIC</b>: dentro del propio archivo (XMP), "
                "como Lightroom.</li>"
                "<li><b>RAW</b> (CR2, CR3, NEF, ARW...): en un archivo <i>.xmp</i> junto "
                "al original.</li>"
                "<li><b>Vídeo, audio, libros...</b>: en un único archivo oculto por carpeta "
                "(<i>.arca.json</i>).</li>"
                "</ul>"
                "Solo se modifican esas etiquetas; la imagen y el resto de metadatos no se tocan. "
                "Si se desactiva, los cambios quedan en el catálogo y se escribirán al "
                "volver a activarla."
            )
        )

        self.check_confirm_multi_edit = QCheckBox(
            "Preguntar antes de cambiar varios archivos con valores distintos"
        )
        self.body.addWidget(self.check_confirm_multi_edit)
        self.body.addWidget(
            self.make_help_label(
                "Al editar en el inspector un metadato (título, pie, ubicación...) de varios "
                "archivos que lo tienen distinto (<i>Varios</i>), se pide confirmación antes "
                "de poner a todos el mismo valor. Es el aviso <b>Edición múltiple</b>: su "
                "casilla <i>No volver a mostrar</i> desactiva esta opción."
            )
        )

    def load(self) -> None:
        self._load_bool(SETTING_WRITE_USER_DATA_TO_FILES, self.check_write_files, True)
        self._load_bool(SETTING_CONFIRM_MULTI_EDIT, self.check_confirm_multi_edit, True)

    def save(self) -> set[str]:
        changed = self._save_bool(SETTING_WRITE_USER_DATA_TO_FILES, self.check_write_files)
        changed |= self._save_bool(SETTING_CONFIRM_MULTI_EDIT, self.check_confirm_multi_edit)
        return changed


class _Relay(QObject):
    """Lleva al hilo principal el resultado de una tarea en segundo plano."""

    done = Signal(object)


def _in_background(task: Callable[[], object], relay: _Relay) -> None:
    """Ejecuta 'task' en un hilo aparte y emite 'relay.done' con su resultado (o con la
    excepción, si falla). Si la ventana se ha cerrado mientras tanto, no pasa nada."""

    def run() -> None:
        try:
            result: object = task()
        except (OSError, TileStorageError) as error:
            result = error
        try:
            relay.done.emit(result)
        except RuntimeError:
            pass  # la ventana ya no existe

    threading.Thread(target=run, daemon=True).start()


# Límites del tamaño máximo de la caché de los mapas (MB)
_CACHE_MB_MIN = 256
_CACHE_MB_MAX = 51_200
_CACHE_MB_STEP = 256
_CACHE_MB_DEFAULT = 2048


class MapSettingsPage(SettingsPage):
    """Sección "Mapa": capas propias y caché de las teselas (docs/MAPA.md, paso 2.4).

    Las capas propias se guardan al pulsar «Aceptar» (como el resto de opciones); al
    quitar una, se vacía también su caché (así su clave podría volver a usarse sin mezclar
    teselas de dos servicios). «Vaciar la caché…» actúa en el momento, tras preguntar.
    """

    title = "Mapa"
    icon = AppIcons.VIEW_MAP

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(config, context, parent)
        self._layers: list[TileLayer] = []
        self._cache_dir: Path = context.get("tile_cache_dir") or app_paths.TILE_CACHE_DIR
        self._size_relay = _Relay(self)
        self._size_relay.done.connect(self._on_size)
        self._clear_relay = _Relay(self)
        self._clear_relay.done.connect(self._on_cleared)

        # --- Capas propias ---
        self.body.addWidget(QLabel("<b>Capas propias</b>"))
        self.list_layers = QListWidget()
        self.list_layers.setFixedHeight(110)
        self.list_layers.itemDoubleClicked.connect(lambda _item: self._edit_layer())
        self.list_layers.currentRowChanged.connect(lambda _row: self._update_buttons())
        self.button_add = QPushButton("Añadir…")
        self.button_edit = QPushButton("Cambiar…")
        self.button_remove = QPushButton("Quitar")
        self.button_add.clicked.connect(self._add_layer)
        self.button_edit.clicked.connect(self._edit_layer)
        self.button_remove.clicked.connect(self._remove_layer)
        buttons = QVBoxLayout()
        for button in (self.button_add, self.button_edit, self.button_remove):
            buttons.addWidget(button)
        buttons.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.list_layers, 1)
        row.addLayout(buttons)
        self.body.addLayout(row)
        self.body.addWidget(
            self._help(
                "Servicios de mapas que se añaden a los de la aplicación: salen al final del "
                "desplegable de la capa, en la barra inferior del mapa. Sirven también si "
                "uno de los de la aplicación cambia de dirección o deja de funcionar."
            )
        )

        # --- Caché ---
        self.body.addSpacing(6)
        self.body.addWidget(QLabel("<b>Caché de los mapas</b>"))
        self.spin_cache = QSpinBox()
        self.spin_cache.setRange(_CACHE_MB_MIN, _CACHE_MB_MAX)
        self.spin_cache.setSingleStep(_CACHE_MB_STEP)
        self.spin_cache.setSuffix(" MB")
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Tamaño máximo"))
        size_row.addWidget(self.spin_cache)
        size_row.addStretch(1)
        self.body.addLayout(size_row)
        self.label_cache_size = QLabel()
        self.button_clear = QPushButton("Vaciar la caché…")
        self.button_clear.clicked.connect(self._clear_cache)
        used_row = QHBoxLayout()
        used_row.addWidget(self.label_cache_size)
        used_row.addStretch(1)
        used_row.addWidget(self.button_clear)
        self.body.addLayout(used_row)
        self.body.addWidget(
            self._help(
                "Lo que se ve en el mapa se guarda en el equipo, para no descargarlo otra vez y "
                "para ver sin conexión lo ya visto. Al abrir el mapa, si la caché pasa del "
                "tamaño máximo, se borran las teselas descargadas hace más tiempo. Está en "
                f"<i>{_escape(str(self._cache_dir))}</i>."
            )
        )

    @classmethod
    def _help(cls, text: str) -> QLabel:
        label = cls.make_help_label(text)
        label.setContentsMargins(0, 0, 0, 4)  # aquí no hay casilla con la que alinearse
        return label

    # --- Cargar y guardar ---

    def load(self) -> None:
        self._layers = list(user_layers_from_settings(self.config.get(SETTING_MAP_USER_LAYERS)))
        self._fill_list()
        value = self.config.get(SETTING_MAP_CACHE_MB, _CACHE_MB_DEFAULT)
        valid = isinstance(value, int) and not isinstance(value, bool)
        self.spin_cache.setValue(value if valid else _CACHE_MB_DEFAULT)
        self._measure()

    def save(self) -> set[str]:
        changed: set[str] = set()
        saved = user_layers_from_settings(self.config.get(SETTING_MAP_USER_LAYERS))
        if user_layers_to_settings(self._layers) != user_layers_to_settings(saved):
            self.config.set(SETTING_MAP_USER_LAYERS, user_layers_to_settings(self._layers))
            changed.add(SETTING_MAP_USER_LAYERS)
            # Las teselas de las capas quitadas ya no sirven: fuera (en segundo plano)
            kept = {layer.key for layer in self._layers}
            for key in {layer.key for layer in saved} - kept:
                store = TileStore(self._cache_dir)
                threading.Thread(target=_clear_quietly, args=(store, key), daemon=True).start()
        if self.config.get(SETTING_MAP_CACHE_MB) != self.spin_cache.value():
            self.config.set(SETTING_MAP_CACHE_MB, self.spin_cache.value())
            changed.add(SETTING_MAP_CACHE_MB)
        return changed

    # --- Capas propias ---

    def _fill_list(self, current: int | None = None) -> None:
        self.list_layers.clear()
        for layer in self._layers:
            item = QListWidgetItem(layer.name)
            item.setToolTip(layer.url_template)
            self.list_layers.addItem(item)
        if self._layers:
            row = current if current is not None else 0
            self.list_layers.setCurrentRow(max(0, min(row, len(self._layers) - 1)))
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_current = 0 <= self.list_layers.currentRow() < len(self._layers)
        self.button_edit.setEnabled(has_current)
        self.button_remove.setEnabled(has_current)

    def _taken_keys(self) -> set[str]:
        """Claves que no se pueden dar a una capa nueva: las de la lista, las guardadas y
        las que aún tienen carpeta en la caché (con teselas de otro servicio)."""
        taken = {layer.key for layer in self._layers}
        taken |= {layer.key for layer in user_layers_from_settings(self.config.get(SETTING_MAP_USER_LAYERS))}
        try:
            taken |= {child.name for child in self._cache_dir.iterdir() if is_valid_key(child.name)}
        except OSError:
            pass  # aún no hay caché
        return taken

    def _add_layer(self) -> None:
        dialog = MapLayerDialog(new_user_key(self._taken_keys()), parent=self)
        if dialog.exec() and dialog.layer() is not None:
            self._layers.append(dialog.layer())
            self._fill_list(len(self._layers) - 1)
        dialog.deleteLater()

    def _edit_layer(self) -> None:
        row = self.list_layers.currentRow()
        if not 0 <= row < len(self._layers):
            return
        layer = self._layers[row]
        dialog = MapLayerDialog(layer.key, layer, parent=self)
        if dialog.exec() and dialog.layer() is not None:
            self._layers[row] = dialog.layer()
            self._fill_list(row)
        dialog.deleteLater()

    def _remove_layer(self) -> None:
        row = self.list_layers.currentRow()
        if 0 <= row < len(self._layers):
            del self._layers[row]
            self._fill_list(row)

    # --- Caché ---

    def _measure(self) -> None:
        """Calcula lo que ocupa la caché (recorre la carpeta: en segundo plano)."""
        self.label_cache_size.setText("Ocupa ahora: calculando…")
        store = TileStore(self._cache_dir)
        _in_background(store.size_bytes, self._size_relay)

    def _on_size(self, result: object) -> None:
        if isinstance(result, int):
            self.label_cache_size.setText(f"Ocupa ahora: {format_size(result)}")
        else:
            self.label_cache_size.setText("Ocupa ahora: no se ha podido calcular")

    def _clear_cache(self) -> None:
        answer = MessageBoxHelper(self).question(
            "Se borran las teselas de los mapas guardadas en el equipo; se volverán a "
            "descargar al verlas (sin conexión, no se verán).",
            "Vaciar la caché de los mapas",
            buttons=["Vaciar", "Cancelar"],
        )
        if answer != "Vaciar":
            return
        self.button_clear.setEnabled(False)
        self.label_cache_size.setText("Ocupa ahora: vaciando…")
        store = TileStore(self._cache_dir)
        _in_background(store.clear, self._clear_relay)

    def _on_cleared(self, result: object) -> None:
        self.button_clear.setEnabled(True)
        if isinstance(result, Exception):
            logger.warning(f"No se pudo vaciar la caché de los mapas: {result}")
        self._measure()


def _clear_quietly(store: TileStore, key: str) -> None:
    """Vacía la caché de una capa; si no se puede, solo se anota."""
    try:
        store.clear(key)
    except (TileStorageError, ValueError) as error:
        logger.warning(f"No se pudo vaciar la caché de la capa {key!r}: {error}")


# Secciones de la ventana, en el orden en que aparecen. Para añadir una, crear su
# clase (heredando de SettingsPage) y añadirla aquí.
PAGES: tuple[type[SettingsPage], ...] = (GeneralPage, CatalogPage, MetadataPage, MapSettingsPage)


class SettingsDialog(QDialog):
    """Ventana de opciones de la aplicación.

    Attributes:
        changed_keys: Claves de settings.json que cambiaron al pulsar "Aceptar" (vacío si
            se canceló o no cambió nada).
    """

    def __init__(
        self,
        config: Any,
        *,
        context: dict[str, Any] | None = None,
        start_page: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Crea la ventana.

        Args:
            config: Gestor de settings.json ('ConfigManager').
            context: Datos para las páginas (p. ej. {'catalog_dir': Path}).
            start_page: Título de la sección que se muestra al abrir (por defecto, la
                primera).
            parent: Ventana padre.
        """
        super().__init__(parent)
        self.setWindowTitle(f"Opciones - {app_paths.APP_NAME_COMERCIAL}")
        self.setModal(True)
        self.resize(720, 460)
        self.changed_keys: set[str] = set()

        # --- Columna de secciones ---
        self.list_sections = QListWidget()
        self.list_sections.setObjectName("list_settings_sections")  # para el tema (QSS)
        self.list_sections.setFixedWidth(180)
        self.list_sections.setIconSize(QSize(20, 20))
        self.list_sections.setFrameShape(QFrame.Shape.NoFrame)

        # --- Cuerpo central ---
        self.stack_pages = QStackedWidget()
        self._pages: list[SettingsPage] = []
        for page_class in PAGES:
            page = page_class(config, context or {}, self)
            page.load()
            self._pages.append(page)
            self.stack_pages.addWidget(page)
            item = QListWidgetItem(tinted_icon(page.icon), page.title)
            item.setSizeHint(QSize(0, 34))
            self.list_sections.addItem(item)
        self.list_sections.currentRowChanged.connect(self.stack_pages.setCurrentIndex)

        # Separador vertical entre la columna y el cuerpo
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self.list_sections)
        content.addWidget(separator)
        content.addWidget(self.stack_pages, 1)

        # --- Botones ---
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Aceptar")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.addLayout(content, 1)
        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(10, 0, 10, 0)
        buttons_row.addWidget(self.buttons)
        layout.addLayout(buttons_row)

        # Sección inicial
        titles = [page.title for page in self._pages]
        self.list_sections.setCurrentRow(titles.index(start_page) if start_page in titles else 0)

    def accept(self) -> None:
        """Guarda las opciones de todas las páginas y cierra."""
        changed: set[str] = set()
        for page in self._pages:
            try:
                changed |= page.save()
            except Exception:  # noqa: BLE001 - una página no debe impedir guardar las demás
                logger.exception(f"No se pudieron guardar las opciones de '{page.title}'")
        self.changed_keys = changed
        if changed:
            logger.info(f"Opciones cambiadas: {sorted(changed)}")
        super().accept()


def _escape(text: str) -> str:
    """Escapa un texto para mostrarlo en una etiqueta con formato (rutas con '<', '&'...)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


if __name__ == "__main__":
    # Prueba visual (abre la ventana sin el resto de la aplicación). No toca settings.json:
    # usa un gestor de opciones en memoria.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.dialogs.settings_dialog
    import sys

    from qtpy.QtWidgets import QApplication

    import resources.recursos_rc  # noqa: F401 - iconos ':/img/...'
    from ui_helpers.helpers.ui_theme import apply_theme

    class _MemoryConfig:
        """Sustituto de ConfigManager que guarda en un diccionario."""

        def __init__(self) -> None:
            self.data: dict[str, Any] = {
                SETTING_WRITE_USER_DATA_TO_FILES: True,
                SETTING_SHOW_SUBFOLDER_ITEMS: True,
                SETTING_CONFIRM_MULTI_EDIT: False,  # como tras «No volver a mostrar»
                SETTING_MAP_CACHE_MB: 2048,
                SETTING_MAP_USER_LAYERS: [],
                SETTING_GPU_RENDERING: None,  # sin elegir: según el sistema
            }

        def get(self, key: str, default: Any = None) -> Any:
            return self.data.get(key, default)

        def set(self, key: str, value: Any) -> None:
            self.data[key] = value

    app = QApplication(sys.argv)
    apply_theme()
    memory = _MemoryConfig()
    dialog = SettingsDialog(memory, context={"catalog_dir": Path.home() / "Catálogo"})
    result = dialog.exec()
    print("Aceptado" if result else "Cancelado", "| cambios:", dialog.changed_keys, memory.data)
