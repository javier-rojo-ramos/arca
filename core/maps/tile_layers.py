"""Capas del mapa: la LISTA de servicios de teselas que ofrece la aplicación.

Este módulo NO depende de Qt ni de la red: es una lista declarativa y unas pocas cuentas.
Diseño completo en docs/MAPA.md (§3).

Una TESELA es un cuadrado (256 px) del mapa, identificado por su nivel de zoom 'z' y su
columna 'x' y su fila 'y' (el esquema de casi todos los mapas web: en el zoom z hay
2^z × 2^z teselas; la 0, 0 es la de arriba a la izquierda). Cada capa dice de qué
dirección sale cada tesela ('url_template', con '{z}', '{x}', '{y}' y, si reparte la
carga entre varios servidores, '{s}').

AQUÍ SE AÑADE UNA CAPA: una línea 'TileLayer(...)' en 'TILE_LAYERS'. Antes hay que leer
las condiciones de uso del servicio (cambian) y anotar su atribución, que el mapa enseña
siempre. La clave ('key') no se cambia después: es el nombre de su carpeta en la caché y
lo que se guarda en settings.json.

Condiciones de las capas de partida (leídas el 13/11/2026; direcciones comprobadas ese día):
    IGN España (topográfico, base y ortofoto)   gratuito, CC BY 4.0, sin clave.
    OpenStreetMap (callejero mundial)           política de uso estricta: identificarse
        ('User-Agent' propio), guardar en caché y NO descargar zonas por adelantado.
    OpenTopoMap (topográfico mundial)           gratuito con uso moderado; CC BY-SA.

CAPAS DEL USUARIO (por durabilidad: si un servicio cambia de dirección o cierra, se corrige
sin tocar el código; docs/MAPA.md, §1.5): las añade el usuario en Opciones > Mapa y se
guardan en settings.json ('map_user_layers'). Llevan una clave 'user_N' y van detrás de las
de fábrica ('all_layers'). Su dirección se comprueba con 'check_url_template'. Sus
teselas se guardan en la caché como '.png' aunque sean JPEG: al servirlas, el tipo se
mira en los propios bytes ('tile_store.image_mime').

Quién lo usa: 'tile_store.py' (la carpeta y la extensión de cada capa) y, cuando exista,
el componente de mapa (ui_helpers/map/), que pide las teselas con 'tile_url' y se
identifica con 'user_agent'.

1.1.0 Capas del usuario: 'user_layer', 'check_url_template', 'all_layers', 'new_user_key',
      'user_layers_from_settings' y 'user_layers_to_settings'.
1.0.1 Orden de las capas decidido por el autor.
1.0.0 Primera versión (docs/MAPA.md, paso 1.1): cinco capas y 'user_agent'.

Prueba rápida (desde la raíz del proyecto):
    python -m core.maps.tile_layers
"""

__version__ = "1.1.0"
__all__ = [
    "DEFAULT_LAYER_KEY",
    "MAX_ZOOM_LIMIT",
    "TILE_LAYERS",
    "USER_LAYER_PREFIX",
    "TileLayer",
    "all_layers",
    "check_url_template",
    "is_valid_key",
    "is_valid_tile",
    "layer_for",
    "new_user_key",
    "tile_url",
    "user_agent",
    "user_layer",
    "user_layers_from_settings",
    "user_layers_to_settings",
]

# Librerías estándar
import re
from collections.abc import Iterable
from dataclasses import dataclass
from string import Formatter

# Una clave vale como nombre de carpeta en cualquier sistema (y nunca sale de la caché)
_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,31}")

# Extensión del archivo en la caché -> tipo MIME con el que se sirve
_MIME_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


@dataclass(frozen=True, slots=True)
class TileLayer:
    """Una capa del mapa (un servicio de teselas).

    Attributes:
        key: Clave estable (minúsculas, cifras y '_'): carpeta de la caché y settings.json.
        name: Nombre para el usuario.
        url_template: Dirección de una tesela, con '{z}', '{x}', '{y}' y, opcional, '{s}'.
        attribution: Texto de atribución que exige el servicio (se ve siempre en el mapa).
        extension: Formato de sus teselas: 'png', 'jpg' o 'webp'.
        min_zoom: Menor zoom que sirve.
        max_zoom: Mayor zoom que sirve (más cerca, el mapa amplía sus teselas).
        subdomains: Valores de '{s}' (servidores equivalentes); vacío si no tiene.
        allow_prefetch: True si sus condiciones permiten descargar zonas por adelantado
            (para usarlas sin conexión). Por defecto, no.
    """

    key: str
    name: str
    url_template: str
    attribution: str
    extension: str = "png"
    min_zoom: int = 0
    max_zoom: int = 19
    subdomains: tuple[str, ...] = ()
    allow_prefetch: bool = False

    @property
    def mime_type(self) -> str:
        """Tipo MIME de sus teselas ('image/png'...)."""
        return _MIME_TYPES[self.extension]


def _ign(service: str, layer: str) -> str:
    """Dirección de una capa WMTS del IGN de España, con la rejilla de los mapas web."""
    return (
        f"https://www.ign.es/wmts/{service}?layer={layer}&style=default"
        "&tilematrixset=GoogleMapsCompatible&Service=WMTS&Request=GetTile&Version=1.0.0"
        "&Format=image/jpeg&TileMatrix={z}&TileCol={x}&TileRow={y}"
    )


_IGN_ATTRIBUTION = "© Instituto Geográfico Nacional de España"

# Las capas, en el orden en que se ofrecen (nombres y orden, del autor, 13/11/2026).
TILE_LAYERS: tuple[TileLayer, ...] = (
    # Mapa «normal» de todo el mundo, para ubicar fotos de viajes y de ciudades
    TileLayer(
        "osm",
        "Callejero (OpenStreetMap)",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "© OpenStreetMap contributors",
    ),
    # Topográfico de todo el mundo (curvas de nivel y sombreado)
    TileLayer(
        "opentopo",
        "OpenTopoMap",
        "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "© OpenStreetMap contributors, SRTM · © OpenTopoMap (CC BY-SA)",
        max_zoom=17,
        subdomains=("a", "b", "c"),
    ),
    TileLayer(
        "ign_base",
        "Mapa base (IGN)",
        _ign("ign-base", "IGNBaseTodo"),
        _IGN_ATTRIBUTION,
        extension="jpg",
        max_zoom=17,
        allow_prefetch=True,
    ),
    # El de los mapas 1:25 000 y 1:50 000: el topográfico de referencia en España
    TileLayer(
        "ign_mtn",
        "Topográfico (IGN)",
        _ign("mapa-raster", "MTN"),
        _IGN_ATTRIBUTION,
        extension="jpg",
        max_zoom=17,
        allow_prefetch=True,
    ),
    TileLayer(
        "ign_pnoa",
        "Ortofoto (PNOA)",
        _ign("pnoa-ma", "OI.OrthoimageCoverage"),
        "PNOA cedido por © Instituto Geográfico Nacional de España",
        extension="jpg",
        allow_prefetch=True,
    ),
)

# Capa con la que empieza el mapa mientras el usuario no elija otra: la única de partida
# que cubre todo el mundo con detalle de calle
DEFAULT_LAYER_KEY = "osm"

_BY_KEY = {layer.key: layer for layer in TILE_LAYERS}


def is_valid_key(key: object) -> bool:
    """True si el texto vale como clave de una capa (también de una del usuario)."""
    return isinstance(key, str) and _KEY_PATTERN.fullmatch(key) is not None


def layer_for(key: object) -> TileLayer | None:
    """La capa de fábrica con esa clave, o None si no existe."""
    return _BY_KEY.get(key) if isinstance(key, str) else None


def is_valid_tile(layer: TileLayer, z: int, x: int, y: int) -> bool:
    """True si la tesela existe en esa capa (zoom dentro de sus límites, columna y fila
    dentro de la rejilla de ese zoom)."""
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (z, x, y)):
        return False
    if not layer.min_zoom <= z <= layer.max_zoom:
        return False
    side = 1 << z
    return 0 <= x < side and 0 <= y < side


def tile_url(layer: TileLayer, z: int, x: int, y: int) -> str:
    """Dirección de una tesela.

    Con varios servidores ('subdomains'), la misma tesela va siempre al mismo (así las
    cachés intermedias sirven) y las vecinas se reparten entre todos.

    Raises:
        ValueError: Si la tesela no existe en esa capa.
    """
    if not is_valid_tile(layer, z, x, y):
        raise ValueError(f"Tesela fuera de la capa {layer.key!r}: z={z!r}, x={x!r}, y={y!r}")
    server = layer.subdomains[(x + y) % len(layer.subdomains)] if layer.subdomains else ""
    return layer.url_template.format(z=z, x=x, y=y, s=server)


# -----------------------------------------------------------------------------
# Capas del usuario
# -----------------------------------------------------------------------------

# Clave de las capas del usuario: 'user_1', 'user_2'...
USER_LAYER_PREFIX = "user_"
# Mayor zoom que se puede pedir a una capa (ningún servicio pasa de 22)
MAX_ZOOM_LIMIT = 22
# Huecos que puede llevar la dirección de una capa del usuario
_URL_FIELDS = frozenset({"z", "x", "y", "s"})
# Servidores que se usan si la dirección lleva '{s}' (los habituales: a, b y c)
_USER_SUBDOMAINS = ("a", "b", "c")
# Límites de los textos (lo que se guarda en settings.json)
_MAX_NAME = 60
_MAX_URL = 1000
_MAX_ATTRIBUTION = 300


def check_url_template(text: str) -> str | None:
    """Comprueba la dirección de las teselas de una capa del usuario.

    Returns:
        None si vale; si no, por qué (un texto para el usuario).
    """
    url = text.strip()
    if not url.lower().startswith(("https://", "http://")):
        return "La dirección tiene que empezar por https:// (o http://)."
    if len(url) > _MAX_URL:
        return "La dirección es demasiado larga."
    try:
        fields = {name for _text, name, _spec, _conversion in Formatter().parse(url) if name is not None}
    except ValueError:
        return "La dirección tiene una llave sin cerrar ({ o })."
    if not fields <= _URL_FIELDS:
        return "La dirección solo puede llevar entre llaves {z}, {x}, {y} y, si acaso, {s}."
    if not {"z", "x", "y"} <= fields:
        return "La dirección tiene que llevar {z}, {x} e {y} (el zoom, la columna y la fila)."
    return None


def user_layer(key: str, name: str, url_template: str, attribution: str, max_zoom: int) -> TileLayer:
    """Una capa del usuario, comprobada.

    Raises:
        ValueError: Si algo no vale (el mensaje es para el usuario).
    """
    name, url_template, attribution = name.strip(), url_template.strip(), attribution.strip()
    if not (is_valid_key(key) and key.startswith(USER_LAYER_PREFIX)):
        raise ValueError(f"Clave no válida para una capa del usuario: {key!r}")
    if not name:
        raise ValueError("Falta el nombre.")
    if len(name) > _MAX_NAME:
        raise ValueError(f"El nombre es demasiado largo (como mucho, {_MAX_NAME} letras).")
    problem = check_url_template(url_template)
    if problem:
        raise ValueError(problem)
    if len(attribution) > _MAX_ATTRIBUTION:
        raise ValueError("La atribución es demasiado larga.")
    if isinstance(max_zoom, bool) or not isinstance(max_zoom, int) or not 1 <= max_zoom <= MAX_ZOOM_LIMIT:
        raise ValueError(f"El zoom máximo va de 1 a {MAX_ZOOM_LIMIT}.")
    return TileLayer(
        key,
        name,
        url_template,
        attribution,
        max_zoom=max_zoom,
        subdomains=_USER_SUBDOMAINS if "{s}" in url_template else (),
    )


def new_user_key(existing: Iterable[str]) -> str:
    """Una clave libre para una capa del usuario ('user_1', 'user_2'...). Nunca reutiliza
    una que esté en uso (su carpeta de la caché tiene sus teselas)."""
    taken = set(existing)
    number = 1
    while f"{USER_LAYER_PREFIX}{number}" in taken:
        number += 1
    return f"{USER_LAYER_PREFIX}{number}"


def user_layers_from_settings(data: object) -> tuple[TileLayer, ...]:
    """Las capas del usuario guardadas en settings.json. Lo que no se entienda (editado a
    mano, de otra versión) se ignora, sin error; una clave repetida, también."""
    if not isinstance(data, list):
        return ()
    layers: list[TileLayer] = []
    keys: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            layer = user_layer(
                entry.get("key", ""),
                entry.get("name", ""),
                entry.get("url", ""),
                entry.get("attribution", ""),
                entry.get("max_zoom", 19),
            )
        except (ValueError, TypeError, AttributeError):
            continue
        if layer.key not in keys:
            keys.add(layer.key)
            layers.append(layer)
    return tuple(layers)


def user_layers_to_settings(layers: Iterable[TileLayer]) -> list[dict]:
    """Las capas del usuario como se guardan en settings.json."""
    return [
        {
            "key": layer.key,
            "name": layer.name,
            "url": layer.url_template,
            "attribution": layer.attribution,
            "max_zoom": layer.max_zoom,
        }
        for layer in layers
    ]


def all_layers(user_layers: Iterable[TileLayer] = ()) -> tuple[TileLayer, ...]:
    """Las capas que se ofrecen: las de fábrica y, detrás, las del usuario (sin las que
    repitan la clave de otra)."""
    result = list(TILE_LAYERS)
    keys = {layer.key for layer in result}
    for layer in user_layers:
        if layer.key not in keys:
            keys.add(layer.key)
            result.append(layer)
    return tuple(result)


def user_agent(app_version: str) -> str:
    """Identificación de la aplicación ante los servidores de teselas (cabecera 'User-Agent').

    Solo el nombre y la versión, sin datos personales (decidido por el autor el
    13/11/2026). OpenStreetMap exige que cada aplicación se identifique con una propia.
    """
    return f"ArcaMedia/{app_version}"


if __name__ == "__main__":
    # Autoprueba (sin Qt y sin red).
    # Ejecutar desde la raíz del proyecto:  python -m core.maps.tile_layers

    # 1. La lista: claves válidas y sin repetir, textos y formato de cada capa
    keys = [layer.key for layer in TILE_LAYERS]
    assert len(keys) == len(set(keys)), keys
    for layer in TILE_LAYERS:
        assert is_valid_key(layer.key), layer.key
        assert layer.name and layer.attribution, layer.key
        assert layer.extension in _MIME_TYPES, layer.key
        assert 0 <= layer.min_zoom <= layer.max_zoom <= 22, layer.key
        assert layer.url_template.startswith("https://"), layer.key
        for mark in ("{z}", "{x}", "{y}"):
            assert mark in layer.url_template, (layer.key, mark)
        # '{s}' y 'subdomains' van juntos
        assert ("{s}" in layer.url_template) == bool(layer.subdomains), layer.key
        assert layer_for(layer.key) is layer
    assert layer_for(DEFAULT_LAYER_KEY) is not None
    assert layer_for("no_existe") is None and layer_for(None) is None

    # 2. Claves: nada que pueda salirse de la carpeta de la caché
    for bad in ("", "Osm", "a/b", "..", "a.b", "1abc", "con espacio", None, 3, "x" * 33):
        assert not is_valid_key(bad), bad
    assert is_valid_key("mi_capa_2")

    # 3. Direcciones
    osm, mtn, topo = layer_for("osm"), layer_for("ign_mtn"), layer_for("opentopo")
    assert tile_url(osm, 12, 2048, 1509) == "https://tile.openstreetmap.org/12/2048/1509.png"
    url = tile_url(mtn, 12, 2048, 1509)
    assert url.startswith("https://www.ign.es/wmts/mapa-raster?layer=MTN&"), url
    assert url.endswith("&TileMatrix=12&TileCol=2048&TileRow=1509"), url
    assert "{" not in url
    assert (osm.mime_type, mtn.mime_type) == ("image/png", "image/jpeg")
    # Varios servidores: siempre el mismo para una tesela, y repartidos entre las vecinas
    assert tile_url(topo, 10, 3, 3) == tile_url(topo, 10, 3, 3)
    servers = {tile_url(topo, 10, x, 5).split(".")[0] for x in range(6)}
    assert servers == {"https://a", "https://b", "https://c"}, servers

    # 4. Teselas que no existen: fuera del zoom de la capa o de la rejilla
    assert is_valid_tile(osm, 0, 0, 0) and is_valid_tile(osm, 19, (1 << 19) - 1, 0)
    for z, x, y in ((20, 0, 0), (-1, 0, 0), (3, 8, 0), (3, 0, 8), (3, -1, 0), (3, 1.0, 0), (3, True, 0)):
        assert not is_valid_tile(osm, z, x, y), (z, x, y)
    assert not is_valid_tile(mtn, 18, 0, 0)  # el topográfico llega al 17
    try:
        tile_url(osm, 3, 8, 0)
    except ValueError:
        pass
    else:
        raise AssertionError("una tesela fuera de la rejilla debe rechazarse")

    # 6. Capas del usuario: direcciones que valen y que no
    for good in ("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                 "http://{s}.servidor.es/mapa?z={z}&x={x}&y={y}&formato=png",
                 "  https://x.es/{z}/{y}/{x}.jpg  "):  # fmt: skip
        assert check_url_template(good) is None, good
    for bad in ("tile.openstreetmap.org/{z}/{x}/{y}.png", "ftp://x/{z}/{x}/{y}", "https://x/{z}/{x}.png",
                "https://x/{z}/{x}/{y}/{w}", "https://x/{z}/{x}/{y", "https://x/{z}/{x}/{y}/{0}",
                "https://x/" + "a" * 1000 + "/{z}/{x}/{y}"):  # fmt: skip
        assert check_url_template(bad), bad
    mine = user_layer("user_1", " Mi mapa ", "https://{s}.x.es/{z}/{x}/{y}.png", "© X", 18)
    assert (mine.name, mine.subdomains, mine.max_zoom, mine.extension) == ("Mi mapa", ("a", "b", "c"), 18, "png")
    assert tile_url(mine, 3, 1, 2).startswith("https://") and "{" not in tile_url(mine, 3, 1, 2)
    for args in (("osm", "x", "https://x/{z}/{x}/{y}", "", 19), ("user_1", "", "https://x/{z}/{x}/{y}", "", 19),
                 ("user_1", "x", "https://x/{z}/{x}", "", 19), ("user_1", "x", "https://x/{z}/{x}/{y}", "", 0),
                 ("user_1", "x", "https://x/{z}/{x}/{y}", "", 23), ("user_1", "x", "https://x/{z}/{x}/{y}", "", True),
                 ("user_1", "x" * 61, "https://x/{z}/{x}/{y}", "", 19)):  # fmt: skip
        try:
            user_layer(*args)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debería rechazarse: {args}")
    # Claves libres: nunca una que esté en uso
    assert new_user_key([]) == "user_1" and new_user_key(["user_1", "user_3"]) == "user_2"
    # settings.json: ida y vuelta; lo que no se entiende, fuera (sin error)
    other = user_layer("user_2", "Otro", "https://y.es/{z}/{x}/{y}.jpg", "", 17)
    saved = user_layers_to_settings([mine, other])
    assert user_layers_from_settings(saved) == (mine, other)
    messy = [*saved, {"key": "user_2", "name": "repetida", "url": "https://z/{z}/{x}/{y}"}, "x", 3,
             {"key": "user_9", "name": "sin dirección"}, {"key": "osm", "name": "x", "url": "https://z/{z}/{x}/{y}"}]  # fmt: skip
    assert user_layers_from_settings(messy) == (mine, other)
    for nothing in (None, {}, "x", []):
        assert user_layers_from_settings(nothing) == ()
    # Todas las capas: las de fábrica primero; las del usuario detrás, sin claves repetidas
    every = all_layers([mine, other, mine])
    assert every[: len(TILE_LAYERS)] == TILE_LAYERS and [layer.key for layer in every[len(TILE_LAYERS):]] == ["user_1", "user_2"]
    assert all_layers() == TILE_LAYERS

    # 5. Identificación: nombre y versión, nada más
    assert user_agent("26.11.001") == "ArcaMedia/26.11.001"

    print("Autoprueba finalizada correctamente.")
