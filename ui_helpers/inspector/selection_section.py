"""Sección «Selección» del inspector: datos básicos de lo seleccionado.

Es la primera sección del panel derecho, común a todos los tipos de archivo. Con un
archivo, varios o ninguno seleccionado (en ese caso resume lo que se está viendo y el
título pasa a ser «SELECCIÓN (VISTA ACTUAL)»; si lo que se ve está vacío, «SELECCIÓN
(VACÍO)», con las filas en blanco: así nunca hay un texto de aviso debajo y la sección
mantiene su alto):

    ▼ SELECCIÓN
      IMG_6264                                   [MOV]   <- nombre (o «6 archivos») y extensión
         Carpeta   …\\Fotos & Videos\\2024        [📂]    <- abre la carpeta (o el archivo)
          Tamaño   24,3 MB
           Fecha   01/06/2024 12:00
       Contenido   434 fotos · 20 vídeos                 <- también con uno: «1 foto»
      Biblioteca   Imágenes             [🖼]   <- icono de su módulo
          Estado   Sin conexión                   [●]    <- solo si hay algún problema

Textos emergentes: la ruta completa (Carpeta), el tamaño exacto (Tamaño), el origen de la
fecha y su zona horaria (Fecha), y la lista completa si no cabe.

La extensión y los iconos van pegados al borde derecho, alineados entre sí.

Aquí NO se edita nada: la fecha y el resto de metadatos se editan en el módulo de cada tipo
(decisión del 30/10/2026: «el Catálogo ve y organiza; los módulos editan el contenido»).

1.3.1 Vista actual vacía: título «Selección (vacío)» y filas en blanco (antes, «Ningún
      archivo» y las filas ocultas: la sección cambiaba de alto).
1.3.0 Sin selección, el título dice «Selección (vista actual)» en lugar de la frase
      «Nada seleccionado: resumen de lo que se está viendo» (así la sección tiene siempre
      el mismo alto).
1.2.0 «Contenido» también con un solo archivo («1 foto», «1 track»): así la sección tiene
      siempre las mismas filas y su alto no cambia al pasar de uno a varios.
1.1.0 Extensión e iconos alineados a la derecha; iconos centrados con el texto
      ('IconCell'); nombres de las bibliotecas desde 'LIBRARY_NAMES'.
"""

__version__ = "1.3.1"
__all__ = ["SelectionSection"]

# Librerías estándar
from pathlib import Path

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QPainter, QPixmap
from qtpy.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

# Módulos del proyecto
from config.app_constants import AppIcons
from core.catalog.libraries import LIBRARY_NAMES, Library
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.helpers.ui_file_manager import FILE_MANAGER_NAME
from ui_helpers.helpers.ui_icons import tinted_icon
from ui_helpers.helpers.ui_theme import ACCENT_COLOR
from ui_helpers.inspector.base_section import (
    ICON_SIZE,
    IconCell,
    InfoGrid,
    InspectorSection,
    set_secondary_text,
)
from ui_helpers.inspector.formatting import (
    DATE_SOURCE_TEXTS,
    format_bytes_exact,
    format_date,
    format_date_range,
    format_media_types,
    format_size,
)
from ui_helpers.widgets.elided_label import ElidedLabel

# Colores del indicador de estado: los mismos que el aviso de la tarjeta
# (ThumbnailsDelegate.MISSING_COLOR y OFFLINE_COLOR)
MISSING_COLOR = "#e8833a"  # ausente: naranja (hay que hacer algo)
OFFLINE_COLOR = "#7d7d7d"  # sin conexión: gris (volverá al conectar el disco)

# Icono de cada biblioteca: el del botón de su módulo en la toolbar. Si el SVG aún no
# existe en 'AppIcons', se muestra la inicial, como hace la toolbar
_LIBRARY_ICONS: dict[str, tuple[str, str]] = {
    Library.IMAGE: ("LIB_IMAGE", "I"),
    Library.VIDEO: ("LIB_VIDEO", "V"),
    Library.AUDIO: ("LIB_AUDIO", "A"),
    Library.EBOOK: ("LIB_EBOOK", "L"),
    Library.TRACKS: ("LIB_TRACKS", "T"),
}
_DOT_SIZE = 10  # diámetro del círculo de estado


def _dot_pixmap(color: str, device_ratio: float) -> QPixmap:
    """Círculo de color para la fila «Estado» (nítido en pantallas de alta densidad)."""
    side = round(ICON_SIZE * device_ratio)
    pixmap = QPixmap(side, side)
    pixmap.fill(QColor(0, 0, 0, 0))
    pixmap.setDevicePixelRatio(device_ratio)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    offset = (ICON_SIZE - _DOT_SIZE) / 2
    painter.drawEllipse(round(offset), round(offset), _DOT_SIZE, _DOT_SIZE)
    painter.end()
    return pixmap


class SelectionSection(InspectorSection):
    """Sección «Selección» (ver el docstring del módulo)."""

    title = "Selección"
    key = "selection"
    # Título sin selección: el resumen es de lo que se está viendo (todo, una carpeta...)
    source_title = "Selección (vista actual)"
    # Título si no hay nada (lo que se ve está vacío): las filas quedan en blanco
    empty_title = "Selección (vacío)"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._reveal_target: Path | None = None  # lo que abre el botón de la carpeta

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._grid = InfoGrid(self)
        layout.addWidget(self._grid)

        # --- Cabecera: nombre (o «6 archivos») y extensión ---
        name_box = QWidget(self._grid)
        name_layout = QHBoxLayout(name_box)
        name_layout.setContentsMargins(0, 2, 0, 4)
        name_layout.setSpacing(6)
        self._name = ElidedLabel(name_box, mode=Qt.TextElideMode.ElideMiddle)
        self._name.setObjectName("lbl_inspector_name")
        name_layout.addWidget(self._name, 1)
        self._extension = QLabel(name_box)
        self._extension.setObjectName("lbl_inspector_extension")
        self._extension.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_layout.addWidget(self._extension)
        self._grid.add_widget_row(name_box)

        # --- Filas ---
        # Botón de la carpeta: icono que toma el color de acento con el ratón encima
        self._reveal_button = IconCell(clickable=True)
        self._reveal_button.set_icon(tinted_icon(AppIcons.FOLDER_OPEN, hover_color=ACCENT_COLOR))
        self._reveal_button.clicked.connect(self._on_reveal_clicked)
        self._folder = self._grid.add_row(
            "Carpeta", mode=Qt.TextElideMode.ElideLeft, accessory=self._reveal_button
        )
        self._size = self._grid.add_row("Tamaño")
        self._date = self._grid.add_row("Fecha")
        self._contents = self._grid.add_row("Contenido")

        self._library_icon = IconCell()
        self._library_icon.setObjectName("lbl_inspector_library_icon")
        self._library = self._grid.add_row("Biblioteca", accessory=self._library_icon)

        self._status_icon = IconCell()
        self._status = self._grid.add_row("Estado", accessory=self._status_icon)

    # -------------------------------------------------------------------------
    # InspectorSection
    # -------------------------------------------------------------------------

    def title_for(self, summary: SelectionSummary) -> str:
        """«Selección», «Selección (vista actual)» sin selección o «Selección (vacío)»."""
        if summary.is_empty:
            return self.empty_title
        return self.source_title if summary.scope == "source" else self.title

    def show_summary(self, summary: SelectionSummary) -> None:
        """Rellena todas las filas con el resumen."""
        self._show_header(summary)
        if summary.is_empty:
            self._show_empty()
            return
        for row in (self._folder, self._size, self._date, self._library):
            row.set_visible(True)
        self._show_folder(summary)
        self._show_size(summary)
        self._show_date(summary)
        self._show_contents(summary)
        self._show_library(summary)
        self._show_status(summary)

    # -------------------------------------------------------------------------
    # Filas
    # -------------------------------------------------------------------------

    def _show_header(self, summary: SelectionSummary) -> None:
        """Nombre (sin extensión) y extensión; o el número de archivos."""
        item = summary.item
        if item is not None:
            path = Path(item.file_name)
            self._name.set_full_text(path.stem or item.file_name, item.file_name)
            extension = path.suffix.lstrip(".").upper()
        else:
            count = summary.count
            # Sin nada que mostrar, el nombre queda en blanco (lo dice el título: «vacío»)
            self._name.set_full_text("" if count == 0 else f"{count:,} archivos".replace(",", "."))
            extension = (summary.extension or "").upper() if count else ""
            if count > 1 and not extension:
                extension = "VARIOS"
        self._extension.setText(extension)
        self._extension.setVisible(bool(extension))
        # (Sin selección, que es un resumen de la vista actual lo dice el título de la
        # sección: ver 'title_for')

    def _show_empty(self) -> None:
        """Nada que mostrar: las mismas filas, con el valor en blanco (la sección no encoge).

        El estado («Ausente», «Sin conexión») solo aparece cuando hay algún problema, así
        que aquí se oculta, como con cualquier selección sin problemas.
        """
        for row in (self._folder, self._size, self._date, self._contents, self._library):
            row.set_visible(True)
            row.value.set_full_text("")
            set_secondary_text(row.value, False)
        self._reveal_target = None
        self._reveal_button.setVisible(False)
        self._set_library_icon(None)
        self._status.set_visible(False)

    def _show_folder(self, summary: SelectionSummary) -> None:
        """Carpeta común (recortada por la izquierda) y botón para abrirla."""
        if summary.folder is None:
            self._folder.value.set_full_text("Varias ubicaciones")
            self._reveal_target = None
        else:
            folder = str(summary.folder)
            self._folder.value.set_full_text(folder, folder)
            # Un solo archivo: se abre su carpeta con él seleccionado
            self._reveal_target = summary.item.path if summary.item else summary.folder
        self._reveal_button.setVisible(self._reveal_target is not None)
        if self._reveal_target is not None:
            offline = summary.offline == summary.count
            self._reveal_button.setEnabled(not offline)
            self._reveal_button.setToolTip(
                "El disco de esta carpeta no está conectado."
                if offline
                else f"Mostrar en {FILE_MANAGER_NAME}"
            )

    def _show_size(self, summary: SelectionSummary) -> None:
        """Tamaño legible; el exacto en el texto emergente."""
        exact = format_bytes_exact(summary.total_size)
        if summary.count > 1:
            self._size.value.set_full_text(
                f"{format_size(summary.total_size)} en total", f"{exact} en total"
            )
        else:
            self._size.value.set_full_text(format_size(summary.total_size), exact)

    def _show_date(self, summary: SelectionSummary) -> None:
        """Fecha (o rango); origen y zona horaria en el texto emergente."""
        item = summary.item
        if item is not None:
            text = format_date(summary.date_min, item.date_precision)
            details = []
            if item.date_source:
                details.append(f"Origen: {DATE_SOURCE_TEXTS.get(item.date_source, item.date_source)}")
            if item.timezone_offset:
                details.append(f"Zona horaria: {item.timezone_offset}")
            tooltip = "\n".join(details)
            # Fecha del archivo (no de los metadatos): en gris, es menos fiable
            set_secondary_text(self._date.value, item.date_source == "file_mtime" or not text)
        else:
            text = format_date_range(summary.date_min, summary.date_max)
            tooltip = "Fechas de la más antigua a la más reciente" if text else ""
            set_secondary_text(self._date.value, not text)
        self._date.value.set_full_text(text or "Sin fecha", tooltip)

    def _show_contents(self, summary: SelectionSummary) -> None:
        """Reparto por tipos («434 fotos · 20 vídeos»; con uno, «1 foto»).

        Se muestra siempre que haya algo (también con un solo archivo): así la sección no
        cambia de alto al pasar de uno a varios y las secciones de debajo no saltan.
        """
        self._contents.set_visible(True)
        self._contents.value.set_full_text(format_media_types(summary.media_types))

    def _show_library(self, summary: SelectionSummary) -> None:
        """Nombre de la biblioteca (o «Varias») y el icono de su módulo."""
        libraries = summary.libraries
        names = [self._library_name(library) for library in libraries]
        if len(libraries) == 1:
            self._library.value.set_full_text(names[0])
            set_secondary_text(self._library.value, libraries[0] is None)
            self._set_library_icon(libraries[0])
        else:
            self._library.value.set_full_text("Varias", "\n".join(names))
            set_secondary_text(self._library.value, False)
            self._set_library_icon(None)

    def _show_status(self, summary: SelectionSummary) -> None:
        """Solo si hay algún problema: ausentes y/o sin conexión, con su círculo."""
        missing, offline = summary.missing, summary.offline
        self._status.set_visible(bool(missing or offline))
        if not (missing or offline):
            return
        if summary.count == 1:
            text = "Ausente" if missing else "Sin conexión"
            tooltip = (
                "El archivo no está en su carpeta (¿se movió, renombró o borró?)."
                if missing
                else "El disco o la carpeta de red de este archivo no está conectado."
            )
        else:
            parts = []
            if missing:
                parts.append(f"{missing} ausente{'s' if missing != 1 else ''}")
            if offline:
                parts.append(f"{offline} sin conexión")
            text = " · ".join(parts)
            tooltip = ""
        self._status.value.set_full_text(text, tooltip)
        # Naranja si hay algo ausente (requiere actuar); gris si solo está desconectado
        color = MISSING_COLOR if missing else OFFLINE_COLOR
        self._status_icon.set_pixmap(_dot_pixmap(color, self.devicePixelRatioF()))

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    @staticmethod
    def _library_name(library: str | None) -> str:
        """Nombre de una biblioteca para el usuario (None = sin clasificar)."""
        if library is None:
            return "Sin clasificar"
        return LIBRARY_NAMES.get(library, library)  # una nueva sin nombre: su clave

    def _set_library_icon(self, library: str | None) -> None:
        """Icono del módulo de la biblioteca (o su inicial); nada si son varias."""
        if library is None or library not in _LIBRARY_ICONS:
            self._library_icon.set_icon(None)
            self._library_icon.clear()
            return
        attribute, initial = _LIBRARY_ICONS[library]
        path = getattr(AppIcons, attribute, None)
        if path:
            # Color del texto: discreto, como los iconos de la barra izquierda
            self._library_icon.set_icon(tinted_icon(path))
        else:
            self._library_icon.set_letter(initial)

    def _on_reveal_clicked(self) -> None:
        if self._reveal_target is not None:
            self.reveal_requested.emit(self._reveal_target)
