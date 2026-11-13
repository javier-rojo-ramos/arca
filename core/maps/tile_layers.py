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

Quién lo usa: 'tile_store.py' (la carpeta y la extensión de cada capa) y, cuando exista,
el componente de mapa (ui_helpers/map/), que pide las teselas con 'tile_url' y se
identifica con 'user_agent'.

1.0.1 Orden de las capas decidido por el autor.
1.0.0 Primera versión (docs/MAPA.md, paso 1.1): cinco capas y 'user_agent'.

Prueba rápida (desde la raíz del proyecto):
    python -m core.maps.tile_layers
"""

__version__ = "1.0.1"
__all__ = [
    "DEFAULT_LAYER_KEY",
    "TILE_LAYERS",
    "TileLayer",
    "is_valid_key",
    "is_valid_tile",
    "layer_for",
    "tile_url",
    "user_agent",
]

# Librerías estándar
import re
from dataclasses import dataclass

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

    # 5. Identificación: nombre y versión, nada más
    assert user_agent("26.11.001") == "ArcaMedia/26.11.001"

    print("Autoprueba finalizada correctamente.")
