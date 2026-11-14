"""Registro central de las secciones plegables de las barras laterales.

Este módulo NO depende de Qt: es Python puro.

Aquí se dice QUÉ secciones existen y dónde pueden aparecer; CÓMO las tiene colocadas el
usuario (orden, ocultas, plegadas) lo lleva 'section_layout.py', que parte de lo que se
declara aquí. Es el único sitio que hay que tocar para dar de alta:

    - Un MODO nuevo (la clave de su 'AppModule': 'catalog', 'image'...):
          registry.register_mode("tracks", "Tracks")
    - Una SECCIÓN nueva:
          registry.register(SectionSpec(
              id="elevation",                 # estable: se guarda en settings.json
              title="Perfil de elevación",
              sidebars=RIGHT,                 # barras en las que puede estar
              order=250,                      # posición de partida (entre la 200 y la 300)
              modes=frozenset({"tracks"}),    # None = en todos los modos
          ))

    Las dos cosas se hacen en '_build_default_registry' (al final de este archivo). Lo
    guardado por el usuario no se pierde: al cargarlo, la sección nueva entra en su
    posición de partida (ver 'SectionLayout.from_state').

Reglas:
    - El 'id' de una sección es único en todo el registro y NO se cambia nunca (es lo que
      se guarda). El título sí se puede cambiar.
    - Una misma sección puede estar en varios modos («Carpetas», en el Catálogo y en
      Imagen): su colocación es independiente en cada uno.
    - Una sección está en UNA sola barra de cada modo. 'sidebars' dice en cuáles puede
      estar; hoy todas declaran una sola (decidido por el autor el 14/11/2026: no se mueven
      entre barras; las de la izquierda navegan y las de la derecha muestran lo
      seleccionado). Si una declarase las dos, empezaría en la primera ('default_sidebar').
    - 'order' es la posición de partida dentro de su barra: de menor a mayor. Se dejan
      huecos (100, 200...) para poder intercalar. Con el mismo 'order', la registrada antes.

Uso:
    from ui_helpers.layout.section_registry import SECTION_REGISTRY, Sidebar

    SECTION_REGISTRY.modes()                          # los modos, en su orden
    SECTION_REGISTRY.defaults("image", Sidebar.LEFT)  # sus secciones, en el orden de partida
    SECTION_REGISTRY.get("folders").title_for("image")

1.1.0 Modo 'tracks' (módulo provisional: de momento, solo con las secciones del inspector).
1.0.0 Primera versión (14/11/2026), con las secciones que ya existían: las del Catálogo y
      las de Imagen en la barra izquierda, y las cuatro del inspector en la derecha.

Prueba rápida (desde la raíz del proyecto):
    python -m ui_helpers.layout.section_registry
"""

__version__ = "1.1.0"
__all__ = [
    "LEFT",
    "RIGHT",
    "SECTION_REGISTRY",
    "ModeSpec",
    "SectionRegistry",
    "SectionSpec",
    "Sidebar",
]

# Librerías estándar
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class Sidebar(StrEnum):
    """Las dos barras laterales (su valor es la clave con la que se guarda)."""

    LEFT = "left"    # izquierda: navegar (la barra de cada módulo)
    RIGHT = "right"  # derecha: el inspector


# Atajos para 'SectionSpec.sidebars'
LEFT: frozenset[Sidebar] = frozenset({Sidebar.LEFT})
RIGHT: frozenset[Sidebar] = frozenset({Sidebar.RIGHT})


@dataclass(frozen=True, slots=True)
class ModeSpec:
    """Un modo de la aplicación.

    Attributes:
        key: Clave estable (la 'key' de su 'AppModule'; se guarda en settings.json).
        title: Nombre para el usuario.
    """

    key: str
    title: str


@dataclass(frozen=True, slots=True)
class SectionSpec:
    """Lo que declara una sección plegable (ver el docstring del archivo).

    Attributes:
        id: Clave estable y única (se guarda en settings.json).
        title: Título para el usuario.
        sidebars: Barras en las que puede estar.
        order: Posición de partida dentro de su barra (de menor a mayor).
        modes: Modos en los que aparece; None = en todos.
        visible: Si empieza visible.
        expanded: Si empieza desplegada.
        mode_titles: Títulos distintos en algún modo ({modo: título}); p. ej. «Biblioteca -
            Imagen». En los demás, 'title'.
    """

    id: str
    title: str
    sidebars: frozenset[Sidebar]
    order: int
    modes: frozenset[str] | None = None
    visible: bool = True
    expanded: bool = True
    mode_titles: Mapping[str, str] = field(default_factory=dict)

    @property
    def default_sidebar(self) -> Sidebar:
        """Barra en la que empieza: la primera de las suyas (izquierda antes que derecha)."""
        return next(sidebar for sidebar in Sidebar if sidebar in self.sidebars)

    def in_mode(self, mode: str) -> bool:
        """True si la sección aparece en ese modo."""
        return self.modes is None or mode in self.modes

    def title_for(self, mode: str) -> str:
        """Título de la sección en ese modo."""
        return self.mode_titles.get(mode, self.title)


class SectionRegistry:
    """Los modos y las secciones dados de alta (ver el docstring del archivo)."""

    def __init__(self) -> None:
        # Los diccionarios conservan el orden de alta (el de los modos es el de la toolbar)
        self._modes: dict[str, ModeSpec] = {}
        self._sections: dict[str, SectionSpec] = {}

    # -------------------------------------------------------------------------
    # Altas
    # -------------------------------------------------------------------------

    def register_mode(self, key: str, title: str) -> None:
        """Da de alta un modo.

        Raises:
            ValueError: Si la clave está vacía o repetida.
        """
        if not key or key in self._modes:
            raise ValueError(f"Clave de modo vacía o repetida: {key!r}")
        self._modes[key] = ModeSpec(key, title)

    def register(self, spec: SectionSpec) -> None:
        """Da de alta una sección (sus modos tienen que estar ya dados de alta).

        Raises:
            ValueError: Si el 'id' está vacío o repetido, si no declara ninguna barra o si
                nombra un modo que no existe (así un error al escribirlo no pasa inadvertido).
        """
        if not spec.id or spec.id in self._sections:
            raise ValueError(f"Id de sección vacío o repetido: {spec.id!r}")
        if not spec.sidebars:
            raise ValueError(f"La sección {spec.id!r} no declara ninguna barra.")
        named = set(spec.modes or ()) | set(spec.mode_titles)
        unknown = named - set(self._modes)
        if unknown:
            raise ValueError(f"La sección {spec.id!r} nombra modos sin registrar: {sorted(unknown)}")
        self._sections[spec.id] = spec

    # -------------------------------------------------------------------------
    # Consultas
    # -------------------------------------------------------------------------

    def modes(self) -> tuple[ModeSpec, ...]:
        """Los modos, en el orden en el que se dieron de alta."""
        return tuple(self._modes.values())

    def mode_keys(self) -> tuple[str, ...]:
        """Las claves de los modos, en su orden."""
        return tuple(self._modes)

    def get(self, section_id: str) -> SectionSpec | None:
        """La sección con ese 'id' (None si no existe)."""
        return self._sections.get(section_id)

    def allowed(self, mode: str, sidebar: Sidebar, section_id: str) -> bool:
        """True si esa sección existe y puede estar en esa barra de ese modo."""
        spec = self._sections.get(section_id)
        return spec is not None and spec.in_mode(mode) and sidebar in spec.sidebars

    def defaults(self, mode: str, sidebar: Sidebar) -> tuple[SectionSpec, ...]:
        """Las secciones que EMPIEZAN en esa barra de ese modo, en su orden de partida."""
        specs = [
            spec
            for spec in self._sections.values()
            if spec.in_mode(mode) and spec.default_sidebar == sidebar
        ]
        # 'sorted' es estable: con el mismo 'order', la que se registró antes
        return tuple(sorted(specs, key=lambda spec: spec.order))


def _build_default_registry() -> SectionRegistry:
    """El registro de la aplicación: AQUÍ se añaden los modos y las secciones nuevos."""
    registry = SectionRegistry()

    # --- Modos, en el orden de la toolbar. Las claves son las de los módulos
    # ('AppModule.key', en 'controllers/app_modules/'); no se importan de allí porque
    # este módulo no depende de Qt
    registry.register_mode("catalog", "Catálogo")
    registry.register_mode("image", "Imagen")
    registry.register_mode("video", "Vídeo")
    registry.register_mode("audio", "Audio")
    registry.register_mode("tracks", "Tracks")

    # --- Barra izquierda (la de cada módulo). Los 'id' son las claves con las que ya se
    # guardaba lo plegado de cada barra
    catalog = frozenset({"catalog"})
    image = frozenset({"image"})
    registry.register(SectionSpec("catalog", "Catálogo", LEFT, 100, modes=catalog))
    registry.register(
        SectionSpec(
            "library", "Biblioteca", LEFT, 100, modes=image,
            mode_titles={"image": "Biblioteca - Imagen"},
        )
    )  # fmt: skip
    registry.register(SectionSpec("folders", "Carpetas", LEFT, 200, modes=catalog | image))
    registry.register(SectionSpec("collections", "Colecciones", LEFT, 300, modes=catalog))
    registry.register(SectionSpec("dates", "Fechas", LEFT, 300, modes=image))
    registry.register(SectionSpec("keywords", "Lista de palabras clave", LEFT, 400, modes=image))

    # --- Barra derecha (el inspector): las mismas en todos los modos. Los 'id' son las
    # 'key' de cada 'InspectorSection'. Que se vean depende además de lo seleccionado
    # ('InspectorSection.fits' y 'applies_to')
    registry.register(SectionSpec("selection", "Selección", RIGHT, 100))
    registry.register(SectionSpec("keyword_editor", "Palabras clave", RIGHT, 200))
    registry.register(SectionSpec("keyword_list", "Lista de palabras clave", RIGHT, 300))
    registry.register(SectionSpec("metadata", "Metadatos", RIGHT, 400))
    return registry


# El registro de la aplicación (único)
SECTION_REGISTRY = _build_default_registry()


if __name__ == "__main__":
    # Autoprueba (sin Qt). Desde la raíz del proyecto:
    #     python -m ui_helpers.layout.section_registry

    def _ids(registry: SectionRegistry, mode: str, sidebar: Sidebar) -> list[str]:
        return [spec.id for spec in registry.defaults(mode, sidebar)]

    # El registro de la aplicación: lo que hoy muestra cada barra, en su orden
    reg = SECTION_REGISTRY
    assert reg.mode_keys() == ("catalog", "image", "video", "audio", "tracks"), reg.mode_keys()
    assert _ids(reg, "catalog", Sidebar.LEFT) == ["catalog", "folders", "collections"]
    assert _ids(reg, "image", Sidebar.LEFT) == ["library", "folders", "dates", "keywords"]
    assert _ids(reg, "video", Sidebar.LEFT) == []  # módulo provisional: sin barra propia
    inspector = ["selection", "keyword_editor", "keyword_list", "metadata"]
    for mode_key in reg.mode_keys():
        assert _ids(reg, mode_key, Sidebar.RIGHT) == inspector, mode_key
    assert reg.get("library").title_for("image") == "Biblioteca - Imagen"
    assert reg.get("folders").title_for("image") == "Carpetas"
    assert reg.get("no_existe") is None
    assert reg.allowed("image", Sidebar.LEFT, "folders")
    assert not reg.allowed("image", Sidebar.RIGHT, "folders")      # no es de esa barra
    assert not reg.allowed("image", Sidebar.LEFT, "collections")   # no es de ese modo
    assert not reg.allowed("image", Sidebar.LEFT, "no_existe")

    # Altas: un modo y una sección nuevos; mismo 'order' = la registrada antes
    test = SectionRegistry()
    test.register_mode("a", "A")
    test.register_mode("b", "B")
    test.register(SectionSpec("one", "Uno", LEFT, 200))
    test.register(SectionSpec("two", "Dos", LEFT, 100, modes=frozenset({"a"})))
    test.register(SectionSpec("three", "Tres", LEFT, 200))
    test.register(SectionSpec("both", "Las dos", LEFT | RIGHT, 50))
    assert _ids(test, "a", Sidebar.LEFT) == ["both", "two", "one", "three"]
    assert _ids(test, "b", Sidebar.LEFT) == ["both", "one", "three"]
    # Una sección de las dos barras empieza en la izquierda, pero vale en las dos
    assert _ids(test, "a", Sidebar.RIGHT) == []
    assert test.get("both").default_sidebar is Sidebar.LEFT
    assert test.allowed("a", Sidebar.RIGHT, "both")

    # Lo que no vale se rechaza al registrarlo
    for bad_call in (
        lambda: test.register_mode("a", "Repetido"),
        lambda: test.register_mode("", "Vacío"),
        lambda: test.register(SectionSpec("one", "Repetida", LEFT, 1)),
        lambda: test.register(SectionSpec("", "Sin id", LEFT, 1)),
        lambda: test.register(SectionSpec("none", "Sin barra", frozenset(), 1)),
        lambda: test.register(SectionSpec("x", "Modo raro", LEFT, 1, modes=frozenset({"z"}))),
        lambda: test.register(SectionSpec("y", "Título raro", LEFT, 1, mode_titles={"z": "Z"})),
    ):
        try:
            bad_call()
            raise AssertionError("debía rechazarlo")
        except ValueError:
            pass

    print("Autoprueba finalizada correctamente.")
