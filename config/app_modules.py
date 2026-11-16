"""La ficha de cada módulo de la aplicación, en un solo sitio.

>>> AQUÍ SE DA DE ALTA UN MÓDULO NUEVO: una línea en 'MODULES'. <<<

Cada módulo (Catálogo, Imagen, Vídeo, Audio, Tracks) tiene una clave, un nombre, una
biblioteca, un icono y el título de su sección «Biblioteca - …». Antes cada dato estaba
repetido en la clase del módulo, en el registro de secciones y en el inspector
(docs/PENDIENTE.md, GEN 12): ahora todos lo leen de aquí.

Quién lo usa:
    - 'controllers/app_modules/*_module.py': su 'key', 'title', 'icon' y 'library'.
    - 'ui_helpers/layout/section_registry.py': los modos (en este orden), sus títulos, qué
      modos llevan las secciones de una biblioteca y el título de «Biblioteca - …».
    - 'ui_helpers/inspector/selection_section.py': el icono (o la inicial) de la biblioteca
      de lo seleccionado ('library_badge').

Está en 'config/' porque lo leen tanto 'controllers/' como 'ui_helpers/'. No depende de Qt
ni de 'core/' (las bibliotecas van por su valor, 'image', 'video'...; la autoprueba
comprueba que son las de 'core/catalog/libraries.Library').

Lo que NO está aquí, porque no se repetía: los textos de cada barra (en su módulo), el
botón del .ui (en 'controllers/app_modules/registry.py'), y lo que es de cada TIPO de
archivo y no de un módulo (los nombres «foto» / «track», la proporción de la tarjeta, los
grupos de las colecciones inteligentes).

Para un módulo nuevo: su línea aquí, su icono en 'AppIcons', su clase en
'controllers/app_modules/', su botón en 'ui/main_window.ui' y su línea en 'registry.py'.

Uso:
    module_spec("tracks").title            # «Tracks»
    module_spec("tracks").icon             # ruta del SVG, o None si aún no está en AppIcons
    library_modules()                      # los que tienen una biblioteca (todos menos el Catálogo)
    library_badge("audio")                 # (ruta del icono o None, «A»)

1.0.0 Primera versión (16/11/2026; docs/PENDIENTE.md, GEN 12).

Prueba rápida (desde la raíz del proyecto):
    python -m config.app_modules
"""

__version__ = "1.0.0"
__all__ = ["MODULES", "ModuleSpec", "library_badge", "library_modules", "module_spec"]

# Librerías estándar
from dataclasses import dataclass

# Módulos del proyecto
from config.app_constants import AppIcons


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    """La ficha de un módulo.

    Attributes:
        key: Clave estable (se guarda en settings.json; es también el modo de las
            secciones de las barras): 'catalog', 'image'...
        title: Nombre para el usuario (el texto de ayuda de su botón; la página «Paneles»).
        library: Biblioteca que gestiona (el valor de 'Library': 'image'...), o None si las
            abarca todas (el Catálogo).
        icon_name: Nombre de su icono en 'AppIcons' ('LIB_IMAGE'). Puede no existir aún:
            entonces se ve su inicial.
        initial: La letra que se ve si no hay icono.
        library_title: Título de la primera sección de su barra («Biblioteca - Imagen»);
            vacío en el Catálogo, que no la tiene.
    """

    key: str
    title: str
    library: str | None
    icon_name: str
    initial: str
    library_title: str = ""

    @property
    def icon(self) -> str | None:
        """Ruta de su icono SVG, o None si todavía no está en 'AppIcons'."""
        return getattr(AppIcons, self.icon_name, None)


# Los módulos, en el orden de la toolbar (el primero es el inicial)
MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec("catalog", "Catálogo", None, "LIB_ALL", "C"),
    ModuleSpec("image", "Imagen", "image", "LIB_IMAGE", "I", "Biblioteca - Imagen"),
    ModuleSpec("video", "Vídeo", "video", "LIB_VIDEO", "V", "Biblioteca - Vídeos"),
    ModuleSpec("audio", "Audio", "audio", "LIB_AUDIO", "A", "Biblioteca - Música"),
    ModuleSpec("tracks", "Tracks", "tracks", "LIB_TRACKS", "T", "Biblioteca - Tracks"),
)

_BY_KEY: dict[str, ModuleSpec] = {spec.key: spec for spec in MODULES}

# Bibliotecas que todavía no tienen módulo: su icono y su inicial, para el inspector. Al
# darles módulo (los libros: EBK 1), su línea pasa a 'MODULES' y sale de aquí
_LIBRARIES_WITHOUT_MODULE: dict[str, tuple[str, str]] = {
    "ebook": ("LIB_EBOOK", "L"),
}


def module_spec(key: str) -> ModuleSpec:
    """La ficha de un módulo por su clave.

    Raises:
        KeyError: Si no hay ningún módulo con esa clave.
    """
    return _BY_KEY[key]


def library_modules() -> tuple[ModuleSpec, ...]:
    """Los módulos de UNA biblioteca (todos menos el Catálogo), en el orden de la toolbar."""
    return tuple(spec for spec in MODULES if spec.library is not None)


def library_badge(library: str) -> tuple[str | None, str] | None:
    """El icono de una biblioteca: (ruta del SVG o None si aún no existe, su inicial).

    None si la biblioteca no se conoce.
    """
    for spec in library_modules():
        if spec.library == library:
            return spec.icon, spec.initial
    if library in _LIBRARIES_WITHOUT_MODULE:
        icon_name, initial = _LIBRARIES_WITHOUT_MODULE[library]
        return getattr(AppIcons, icon_name, None), initial
    return None


if __name__ == "__main__":
    # Autoprueba (sin Qt). Ejecutar desde la raíz del proyecto:
    #     python -m config.app_modules
    from core.catalog.libraries import Library

    # 1. Claves únicas y en el orden de la toolbar; el Catálogo, el primero y sin biblioteca
    keys = [spec.key for spec in MODULES]
    assert keys == ["catalog", "image", "video", "audio", "tracks"], keys
    assert len(set(keys)) == len(keys)
    assert MODULES[0].library is None and MODULES[0].library_title == ""
    assert module_spec("tracks").title == "Tracks"
    try:
        module_spec("no_existe")
    except KeyError:
        pass
    else:
        raise AssertionError("una clave que no existe debe dar KeyError")

    # 2. Las bibliotecas son las de 'core' y ninguna se repite; cada módulo de biblioteca
    #    tiene el título de su sección
    libraries = [spec.library for spec in library_modules()]
    assert len(set(libraries)) == len(libraries) == len(MODULES) - 1
    assert set(libraries) <= {library.value for library in Library}, libraries
    assert all(spec.library_title.startswith("Biblioteca - ") for spec in library_modules())

    # 3. Los iconos: los cinco de hoy existen en 'AppIcons'
    assert all(spec.icon and spec.icon.startswith(":/img/") for spec in MODULES)
    assert module_spec("audio").icon == AppIcons.LIB_AUDIO

    # 4. Toda biblioteca tiene icono o inicial para el inspector, tenga módulo o no
    for library in Library:
        badge = library_badge(library.value)
        assert badge is not None and len(badge[1]) == 1, library
    assert library_badge("audio") == (AppIcons.LIB_AUDIO, "A")
    assert library_badge("ebook") == (None, "L")  # sin icono todavía: su inicial
    assert library_badge("no_existe") is None
    # Una biblioteca no puede estar en los dos sitios
    assert not set(_LIBRARIES_WITHOUT_MODULE) & set(libraries)

    print("Autoprueba finalizada correctamente.")
