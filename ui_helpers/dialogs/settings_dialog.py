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

1.1.1 Texto de ayuda con el nombre nuevo del archivo de carpeta ('.arca.json').
1.1.0 Sección "Catálogo": mostrar o no los elementos de las subcarpetas.
"""

__version__ = "1.1.1"
__all__ = ["PAGES", "CatalogPage", "GeneralPage", "MetadataPage", "SettingsDialog", "SettingsPage"]

# Librerías estándar
from pathlib import Path
from typing import Any, ClassVar

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QSize, Qt
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Módulos del proyecto
from config import app_paths
from config.app_constants import (
    SETTING_SHOW_SUBFOLDER_ITEMS,
    SETTING_WRITE_USER_DATA_TO_FILES,
    AppIcons,
)
from ui_helpers.helpers.ui_icons import tinted_icon


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
    """Sección "General": información de dónde guarda las cosas la aplicación."""

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
    """Sección "Metadatos": dónde se guardan la valoración, la marca y el color."""

    title = "Metadatos"
    icon = AppIcons.LIB_IMAGE

    def __init__(self, config: Any, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(config, context, parent)

        self.check_write_files = QCheckBox("Escribir los cambios en los archivos")
        self.body.addWidget(self.check_write_files)
        self.body.addWidget(
            self.make_help_label(
                "La valoración, la marca y la etiqueta de color se guardan también fuera "
                "del catálogo, para no perderlas si hay que volver a crearlo:"
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

    def load(self) -> None:
        self._load_bool(SETTING_WRITE_USER_DATA_TO_FILES, self.check_write_files, True)

    def save(self) -> set[str]:
        return self._save_bool(SETTING_WRITE_USER_DATA_TO_FILES, self.check_write_files)


# Secciones de la ventana, en el orden en que aparecen. Para añadir una, crear su
# clase (heredando de SettingsPage) y añadirla aquí.
PAGES: tuple[type[SettingsPage], ...] = (GeneralPage, CatalogPage, MetadataPage)


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
