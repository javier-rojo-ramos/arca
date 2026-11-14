"""Inspector: el panel lateral DERECHO, con la información de lo seleccionado.

Mismo aspecto que la barra izquierda (Catálogo, Carpetas, Colecciones): secciones
plegables una debajo de otra dentro de un área con desplazamiento. Cada sección es un
'InspectorSection' (ver 'base_section.py'):

    ▼ SELECCIÓN     nombre, carpeta, tamaño, fecha, biblioteca y estado (selection_section.py)
    ▼ TRACK         distancia, desnivel, altitud, duración... de los tracks seleccionados
                    (track_section.py; solo si todo es de la biblioteca Tracks)
    ▼ PALABRAS CLAVE  la caja para verlas y escribirlas, con cualquier selección
                    (keyword_editor_section.py)
    ▼ LISTA DE PALABRAS CLAVE  el árbol con casillas, siempre (keyword_list_section.py)
    ▼ METADATOS     cámara, exposición, ubicación... de la biblioteca Imagen, con un
                    desplegable de vistas en la cabecera (metadata_section.py)

El ORDEN de las secciones, si el usuario las tiene a la vista y si están plegadas lo
lleva el modelo de colocación ('ui_helpers/layout/'), POR MODO: el panel se une a él con
'bind_layout' y se recoloca al cambiar de módulo ('set_layout_mode'). Una sección se ve si
el usuario la tiene a la vista Y tiene algo que mostrar para lo seleccionado.

Más adelante (decidido el 30/10/2026): «Organización» (valoración, marca, color,
colecciones), «Descripción», y las propias de cada tipo («Cámara», «Ubicación», «Etiquetas
de audio», «Ficha»...). El inspector es EL MISMO en todos los módulos (decidido por el
autor el 08/11/2026): cada sección aparece según la biblioteca de lo resumido
('InspectorSection.fits': las de una biblioteca, solo si todo es de ella) y lo que tenga
que mostrar ('applies_to'), nunca según el módulo activo (lo que sí es de cada módulo es
cómo las tiene colocadas el usuario).

Cómo se usa:
    panel = InspectorPanel(parent)                       # con las secciones por defecto
    panel.bind_layout(model, "catalog")   # la colocación del usuario ('SectionLayoutModel')
    panel.set_layout_mode("image")        # al cambiar de módulo
    panel.show_summary(summary)    # 'SelectionSummary' (lo calcula el controlador)
    panel.show_no_catalog()        # sin catálogo abierto
    panel.reveal_requested.connect(...)  # «Mostrar en el Explorador» de alguna sección
    panel.edit_requested.connect(...)    # una sección quiere cambiar el catálogo

El panel NO lee la base de datos: el resumen se lo da 'controllers/inspector_controller.py'.
Las secciones que no tienen nada que mostrar para lo seleccionado se ocultan enteras.

El título de cada sección puede cambiar con lo que se ve ('InspectorSection.title_for'):
p. ej. «SELECCIÓN» con algo seleccionado y «SELECCIÓN (VISTA ACTUAL)» sin selección.

1.8.0 Sección «Track» (debajo de «Selección»).
1.7.1 El menú de las secciones, también con el clic derecho en el hueco vacío del panel.
1.7.0 Las secciones, en una 'SectionStack' colocada por el modelo de colocación, por modo
      ('bind_layout', 'set_layout_mode'); lo plegado ya no se guarda aquí (antes, en
      'inspector_sections'). Al volver a verse una sección oculta, pide sus datos.
1.6.1 El área con desplazamiento no coge el teclado: un clic en el inspector (fuera de
      una caja) no se lo quita a las fotos; las cajas, sí lo cogen (12/11/2026).
1.6.0 Las secciones, según la biblioteca de lo resumido ('fits'), no según el módulo
      (fuera 'set_module'); las palabras clave se editan en todos los módulos y la sección
      de solo lectura ('KeywordsSection') deja de usarse (paso A.2).
1.5.3 Reenvía 'navigate_requested'.
1.5.2 Reenvía 'drop_edit_requested' (tarjetas soltadas en una sección).
1.5.1 En Imagen, la caja y el árbol con casillas en dos secciones (se pliegan por separado).
1.5.0 Secciones según el módulo activo ('set_module'): en Imagen, el editor de palabras
      clave en lugar de la lista; señal 'edit_requested' (paso K4b).
1.4.0 Sección «Palabras clave» (entre «Selección» y «Metadatos»).
1.3.0 Lo plegado y desplegado de cada sección se guarda en settings.json
      ('inspector_sections', por la clave de la sección) y se recupera al abrir.
1.2.0 Sección «Metadatos»; secciones con datos propios ('data_requests' / 'deliver_data'),
      widget en la cabecera de cada sección y la columna de etiquetas con el mismo ancho
      en todas las secciones.
1.1.0 El título de cada sección se actualiza con cada resumen ('title_for').

El aspecto se define en la hoja de estilos global (ui_helpers/helpers/ui_theme.py) con los
nombres de objeto 'scroll_inspector', 'widget_inspector_content' y los 'lbl_inspector_*'.
"""

__version__ = "1.8.0"
__all__ = ["DEFAULT_SECTIONS", "InspectorPanel"]

# Librerías estándar
from collections.abc import Callable, Sequence
from typing import Any

# Librerías de terceros (Qt)
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

# Módulos del proyecto
from core.catalog.selection_summary import SelectionSummary
from ui_helpers.inspector.base_section import InspectorSection, set_secondary_text
from ui_helpers.inspector.keyword_editor_section import KeywordEditorSection
from ui_helpers.inspector.keyword_list_section import KeywordListSection
from ui_helpers.inspector.metadata_section import MetadataSection
from ui_helpers.inspector.selection_section import SelectionSection
from ui_helpers.inspector.track_section import TrackSection
from ui_helpers.layout.section_layout_model import SectionLayoutModel
from ui_helpers.layout.section_registry import Sidebar
from ui_helpers.widgets.collapsible_section import CollapsibleSection
from ui_helpers.widgets.section_stack import SectionStack

# Secciones del inspector, en su orden de partida (una función que crea cada una).
# Para añadir una sección: escribir su clase (heredando de 'InspectorSection'), ponerla aquí
# y registrar su 'key' en 'ui_helpers/layout/section_registry.py' (barra derecha)
DEFAULT_SECTIONS: tuple[Callable[[QWidget], InspectorSection], ...] = (
    SelectionSection,
    TrackSection,           # solo si todo es de la biblioteca Tracks
    KeywordEditorSection,   # la caja de texto (con cualquier selección)
    KeywordListSection,     # el árbol con casillas (siempre)
    MetadataSection,        # solo si todo es de la biblioteca Imagen
)


class InspectorPanel(QWidget):
    """Panel derecho con las secciones del inspector (ver el docstring del módulo).

    Signals:
        reveal_requested(object): mostrar una ruta ('Path') en el explorador de archivos.
    """

    reveal_requested = Signal(object)
    # Alguna sección necesita sus datos otra vez (p. ej. ha cambiado de vista)
    refresh_requested = Signal()
    # Alguna sección quiere cambiar el catálogo: (función, argumentos)
    edit_requested = Signal(object, object)
    # Lo mismo con tarjetas soltadas: (función, argumentos, MediaDrag)
    drop_edit_requested = Signal(object, object, object)
    # Alguna sección quiere que la cuadrícula muestre otro origen ('GridSource')
    navigate_requested = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        sections: Sequence[Callable[[QWidget], InspectorSection]] = DEFAULT_SECTIONS,
    ) -> None:
        """Crea el panel con sus secciones (vacías hasta 'show_summary').

        Args:
            parent: Widget padre.
            sections: Qué secciones lleva y en qué orden (por defecto, 'DEFAULT_SECTIONS').
        """
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Todo el panel se desplaza a la vez (como la barra izquierda)
        scroll = QScrollArea(self)
        scroll.setObjectName("scroll_inspector")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Sin teclado: un clic en la barra (fuera de una caja de texto) no se lo quita a las
        # fotos; si no, Qt se lo daría a esta área (la primera de más arriba que lo acepta)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget(scroll)
        content.setObjectName("widget_inspector_content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        scroll.setWidget(content)

        # Aviso cuando no hay catálogo abierto (en lugar de secciones vacías)
        self._empty_label = QLabel("Abre o crea un catálogo para ver aquí la información.", content)
        self._empty_label.setObjectName("lbl_inspector_hint")
        self._empty_label.setWordWrap(True)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setContentsMargins(12, 24, 12, 0)
        set_secondary_text(self._empty_label)
        layout.addWidget(self._empty_label)

        # Secciones: cada una en su sección plegable, dentro de una pila que las coloca
        # como diga el modelo de colocación ('bind_layout')
        self._stack = SectionStack(content)
        # Una sección que el usuario vuelve a mostrar (o que se ve en el modo al que se
        # cambia) necesita sus datos
        self._stack.shown_sections_changed.connect(self.refresh_requested)
        self._sections: list[tuple[InspectorSection, CollapsibleSection]] = []
        for factory in sections:
            section = factory(content)
            frame = CollapsibleSection(section.title, content)
            frame.set_content(section)
            header_widget = section.header_widget()
            if header_widget is not None:
                frame.add_header_widget(header_widget)  # p. ej. el desplegable de vistas
            self._stack.add_section(section.key, frame)
            section.reveal_requested.connect(self.reveal_requested)
            section.refresh_requested.connect(self.refresh_requested)
            section.edit_requested.connect(self.edit_requested)
            section.drop_edit_requested.connect(self.drop_edit_requested)
            section.navigate_requested.connect(self.navigate_requested)
            self._sections.append((section, frame))

        layout.addWidget(self._stack)
        layout.addStretch(1)  # las secciones arriba, el hueco abajo
        # El menú de las secciones (mostrar, ocultar, restaurar), también en ese hueco
        self._stack.watch_empty_area(content)
        self.show_no_catalog()

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def bind_layout(self, model: SectionLayoutModel, mode: str) -> None:
        """Une las secciones al modelo de colocación (orden, visibles y plegadas), para el
        modo indicado. Sin llamarlo, quedan en el orden de partida, desplegadas."""
        self._stack.bind(model, mode, Sidebar.RIGHT)

    def set_layout_mode(self, mode: str) -> None:
        """Ha cambiado el módulo activo: las secciones, como las tenga el usuario en él."""
        self._stack.set_mode(mode)

    def show_summary(self, summary: SelectionSummary) -> None:
        """Muestra el resumen en todas las secciones (oculta las que no aplican)."""
        self._empty_label.setVisible(False)
        for section, frame in self._sections:
            applies = section.fits(summary) and section.applies_to(summary)
            # Se ve si aplica Y el usuario la tiene a la vista (lo segundo, la pila)
            self._stack.set_available(section.key, applies)
            if applies:
                frame.set_title(section.title_for(summary))
                section.show_summary(summary)
        self._align_key_columns()

    def data_requests(
        self, summary: SelectionSummary, ids: Sequence[int]
    ) -> list[tuple[InspectorSection, Callable[..., Any], tuple[Any, ...]]]:
        """Datos propios que piden las secciones visibles: (sección, función, argumentos).

        Lo llama el controlador después de 'show_summary' y lanza cada función en segundo
        plano; el resultado vuelve con 'deliver_data'.
        """
        requests = []
        for section, frame in self._sections:
            if not frame.isVisibleTo(self):
                continue
            request = section.data_request(summary, ids)
            if request is not None:
                function, arguments = request
                requests.append((section, function, arguments))
        return requests

    def deliver_data(self, section: InspectorSection, result: Any) -> None:
        """Entrega a una sección el resultado de su 'data_request'."""
        section.show_data(result)
        self._align_key_columns()

    def _align_key_columns(self) -> None:
        """La columna de etiquetas, con el mismo ancho FIJO en todas las secciones y vistas.

        El ancho es el de la etiqueta más larga de TODAS las que pueden aparecer (no solo
        las de ahora): así los valores empiezan siempre en el mismo sitio, sea cual sea la
        sección o la vista elegida en «Metadatos». Las etiquetas usan la fuente del panel.
        """
        grids = [grid for section, _frame in self._sections for grid in section.info_grids()]
        if not grids:
            return
        labels = [text for section, _frame in self._sections for text in section.possible_key_labels()]
        metrics = grids[0].fontMetrics()
        width = max((metrics.horizontalAdvance(text) for text in labels), default=0) + 2
        for grid in grids:
            grid.set_key_column_width(width)

    def show_no_catalog(self) -> None:
        """Sin catálogo abierto: solo el aviso, sin secciones."""
        self._empty_label.setVisible(True)
        for section, _frame in self._sections:
            self._stack.set_available(section.key, False)

    def sections(self) -> list[InspectorSection]:
        """Las secciones del panel, en orden (para las pruebas y para guardar su estado)."""
        return [section for section, _frame in self._sections]
