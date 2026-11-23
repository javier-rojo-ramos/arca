"""Buscar lugares para el mapa (geocodificación): la petición, la respuesta y el historial.

Este módulo NO depende de Qt ni de la red: arma la dirección de la petición, lee lo que
responde el servicio y lleva la lista de las búsquedas recientes. Quien pide de verdad es
'geocoding_client.py' (con 'urllib', en un hilo secundario). Lo usa la caja de búsqueda del
mapa (GEN 8.4) y lo usará la ubicación de las fotos a partir de su GPS (geocodificación
inversa, GEN 8.5).

El servicio es Nominatim, de OpenStreetMap (decidido por el autor el 23/11/2026). Sus
condiciones de uso, leídas el 23/11/2026 en
https://operations.osmfoundation.org/policies/nominatim/:
    - Como mucho UNA petición por segundo, sumando todo lo que pide la aplicación (lo
      cumple 'geocoding_client.RequestGate', una para toda la aplicación).
    - Identificarse con un 'User-Agent' propio (el de las teselas: 'tile_layers.user_agent').
    - PROHIBIDO buscar mientras se escribe (autocompletar): solo al pulsar Intro.
    - Guardar los resultados: aquí, el historial (una búsqueda repetida no se vuelve a pedir).
    - Citar a OpenStreetMap (los datos son ODbL).
    - Poder cambiar de servicio sin actualizar el programa: su dirección se lee de
      settings.json ('service_url_from_settings').
    - Pedir muchos puntos (p. ej. la geocodificación inversa de un catálogo) es «uso masivo»:
      solo trabajos puntuales, de uno en uno y con caché; nunca consultas sistemáticas
      (docs/TRAMPAS.md).

Lo que devuelve es un 'Place': nombre corto, nombre completo, coordenadas, rectángulo y la
dirección ya repartida en los campos de ubicación de la aplicación ('PlaceAddress').

Reparto de la dirección ('address_from_nominatim'), PROVISIONAL hasta GEN 8.5, que lo
comprobará con respuestas reales. Sigue lo que ya hay en las fotos del autor (escrito por
Lightroom o a mano, visto el 23/11/2026): la región es la provincia (Segovia, Guadalajara...),
la ciudad es la población y la sububicación, el sitio concreto (un parque, un museo, una calle);
el país, en español:
    sublocation   el nombre del propio lugar, si es más pequeño que una población (un barrio,
                  una calle, un parque...; lo dice su tipo, 'addresstype')
    city          city, town, village, municipality o hamlet (la primera que haya)
    region        province, state, region o state_district (la primera que haya)
    country       country (en el idioma pedido: «España»)
    country_code  country_code, en mayúsculas («ES»)

Uso:
    url = search_url(service_url_from_settings(valor), "Torla", viewbox=(s, w, n, e))
    places = parse_search(bytes_de_la_respuesta)       # [] si no se encuentra nada
    history = remember_search(history, "Torla", places[0])
    place = recall_search(history, "torla")            # el de antes, sin pedirlo otra vez

1.0.0 Primera versión (GEN 8.4a).

Prueba rápida (desde la raíz del proyecto; sin red):
    python -m core.maps.geocoding
"""

__version__ = "1.0.0"
__all__ = [
    "DEFAULT_LANGUAGE",
    "DEFAULT_SERVICE_URL",
    "HISTORY_LIMIT",
    "MAX_QUERY_LENGTH",
    "Bounds",
    "GeocodingError",
    "GeocodingResponseError",
    "HistoryEntry",
    "Place",
    "PlaceAddress",
    "address_from_nominatim",
    "history_from_settings",
    "history_to_settings",
    "normalize_query",
    "parse_search",
    "recall_search",
    "remember_search",
    "search_url",
    "service_url_from_settings",
]

# Librerías estándar
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit

# El servicio de partida (se puede cambiar en settings.json sin tocar el código)
DEFAULT_SERVICE_URL = "https://nominatim.openstreetmap.org"
# Idioma de los nombres que se piden (el de la interfaz)
DEFAULT_LANGUAGE = "es"
# Búsquedas recientes que se recuerdan (decidido por el autor el 23/11/2026)
HISTORY_LIMIT = 10
# Más largo no es un lugar ni una dirección: se recorta
MAX_QUERY_LENGTH = 200
# Nominatim no da más de 40 resultados por petición
_MAX_RESULTS = 40

# Rectángulo en grados: (sur, oeste, norte, este)
Bounds = tuple[float, float, float, float]

# Claves de la dirección de Nominatim de las que sale cada campo, por orden de preferencia
_CITY_KEYS = ("city", "town", "village", "municipality", "hamlet")
_REGION_KEYS = ("province", "state", "region", "state_district")
# Tipos de lugar ('addresstype') que son una población o algo mayor: su nombre no es una
# sububicación (sí lo son un barrio, una calle, un parque, un museo...)
_AREA_KINDS = frozenset({
    "continent", "country", "state", "province", "region", "state_district", "county",
    "municipality", "city", "town", "village", "hamlet", "postcode", "island", "archipelago",
})


class GeocodingError(Exception):
    """No se ha podido buscar. Es la clase común de todos los errores de la búsqueda
    (también de los de 'geocoding_client.py'): quien busca solo necesita esta."""


class GeocodingResponseError(GeocodingError):
    """El servicio ha respondido algo que no se entiende, o un mensaje de error."""


@dataclass(frozen=True, slots=True)
class PlaceAddress:
    """La dirección de un lugar, repartida en los campos de ubicación de la aplicación
    (los de 'core/userdata/editable_fields.py'). Lo que no se sabe, vacío."""

    sublocation: str = ""
    city: str = ""
    region: str = ""
    country: str = ""
    country_code: str = ""

    def is_empty(self) -> bool:
        """True si no se sabe nada de la dirección."""
        return not (self.sublocation or self.city or self.region or self.country
                    or self.country_code)


@dataclass(frozen=True, slots=True)
class Place:
    """Un lugar encontrado.

    Attributes:
        name: Nombre corto («Torla-Ordesa», «Museo Nacional del Prado»).
        label: Nombre completo, con dónde está («Torla-Ordesa, Sobrarbe, Huesca, Aragón,
            España»).
        latitude, longitude: El punto del lugar, en grados.
        bounds: Lo que ocupa (sur, oeste, norte, este), o None si el servicio no lo dice.
            Para encuadrarlo; en una dirección es un rectángulo diminuto.
        address: La dirección repartida en los campos de ubicación.
    """

    name: str
    label: str
    latitude: float
    longitude: float
    bounds: Bounds | None = None
    address: PlaceAddress = field(default_factory=PlaceAddress)


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """Una búsqueda reciente: lo que se escribió y el lugar al que llevó."""

    query: str
    place: Place


# -----------------------------------------------------------------------------
# La petición
# -----------------------------------------------------------------------------


def normalize_query(text: str) -> str:
    """El texto tal como se busca: sin espacios de más y como mucho MAX_QUERY_LENGTH
    caracteres."""
    return " ".join(str(text).split())[:MAX_QUERY_LENGTH].strip()


def service_url_from_settings(value: object) -> str:
    """La dirección del servicio guardada en settings.json, o la de partida si no hay
    ninguna o no vale (solo http o https, sin parámetros; sin la barra del final)."""
    if isinstance(value, str):
        text = value.strip().rstrip("/")
        try:
            parts = urlsplit(text)
        except ValueError:
            return DEFAULT_SERVICE_URL
        if (parts.scheme in ("http", "https") and parts.netloc
                and not parts.query and not parts.fragment):
            return text
    return DEFAULT_SERVICE_URL


def search_url(
    service_url: str,
    query: str,
    *,
    viewbox: Bounds | None = None,
    language: str = DEFAULT_LANGUAGE,
    limit: int = 1,
) -> str:
    """La dirección de la petición de búsqueda.

    Args:
        service_url: La del servicio ('service_url_from_settings').
        query: Lo que se busca (se normaliza).
        viewbox: Lo que se ve en el mapa (sur, oeste, norte, este): los lugares de dentro
            salen antes, pero no se descartan los de fuera.
        language: Idioma de los nombres.
        limit: Cuántos lugares (1 a 40). La caja del mapa va al primero: pide uno.

    Raises:
        ValueError: Si no hay nada que buscar.
    """
    text = normalize_query(query)
    if not text:
        raise ValueError("No hay nada que buscar")
    params = {
        "q": text,
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": str(max(1, min(int(limit), _MAX_RESULTS))),
        "accept-language": language,
    }
    box = _viewbox(viewbox)
    if box is not None:
        params["viewbox"] = box  # sin 'bounded': da preferencia, no filtra
    return f"{service_url.rstrip('/')}/search?{urlencode(params)}"


def _viewbox(bounds: Bounds | None) -> str | None:
    """El parámetro 'viewbox' («oeste,sur,este,norte»), o None si no vale. El mapa puede dar
    longitudes de más allá de ±180 (al dar la vuelta al mundo): se recortan."""
    if bounds is None:
        return None
    try:
        south, west, north, east = (float(value) for value in bounds)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (south, west, north, east)):
        return None
    south, north = max(south, -90.0), min(north, 90.0)
    west, east = max(west, -180.0), min(east, 180.0)
    if south >= north or west >= east:
        return None
    return ",".join(f"{value:.6f}" for value in (west, south, east, north))


# -----------------------------------------------------------------------------
# La respuesta
# -----------------------------------------------------------------------------


def parse_search(data: bytes | str) -> list[Place]:
    """Los lugares de una respuesta de búsqueda ('format=jsonv2'), en su orden (el primero
    es el que el servicio cree mejor). Lista vacía si no ha encontrado nada. Los lugares
    sin coordenadas válidas se saltan.

    Raises:
        GeocodingResponseError: Si la respuesta no es JSON, no es una lista o es un error.
    """
    try:
        payload = json.loads(data)
    except (TypeError, ValueError) as error:  # también UnicodeDecodeError (ValueError)
        raise GeocodingResponseError("La respuesta del servicio no es JSON") from error
    if isinstance(payload, Mapping) and "error" in payload:
        raise GeocodingResponseError(f"El servicio responde con un error: {payload['error']}")
    if not isinstance(payload, list):
        raise GeocodingResponseError("La respuesta del servicio no es una lista de lugares")
    return [place for item in payload if (place := _place_from_item(item)) is not None]


def address_from_nominatim(
    address: Mapping[str, object], *, name: str = "", kind: str = ""
) -> PlaceAddress:
    """La dirección de Nominatim ('address') repartida en los campos de la aplicación
    (reglas en el docstring del archivo; PROVISIONALES hasta GEN 8.5).

    Args:
        address: El objeto 'address' de la respuesta.
        name: El nombre del propio lugar (para la sububicación).
        kind: Su tipo ('addresstype': «village», «road», «tourism»...). Si es una población
            o algo mayor, o no se sabe, su nombre no es una sububicación.
    """
    city = _first(address, _CITY_KEYS)
    region = _first(address, _REGION_KEYS)
    country = _text(address.get("country"))
    code = _text(address.get("country_code")).upper()
    if not (code.isascii() and code.isalpha() and len(code) in (2, 3)):
        code = ""
    sublocation = ""
    # Sin el tipo no se sabe si el nombre es el de un sitio concreto o el de la población
    if name and kind and kind not in _AREA_KINDS and name not in (city, region, country):
        sublocation = name
    return PlaceAddress(sublocation, city, region, country, code)


def _place_from_item(item: object) -> Place | None:
    """Un lugar de la respuesta, o None si no tiene coordenadas válidas."""
    if not isinstance(item, Mapping):
        return None
    latitude, longitude = _number(item.get("lat")), _number(item.get("lon"))
    if latitude is None or longitude is None or not _valid_position(latitude, longitude):
        return None
    raw_address = item.get("address")
    address = raw_address if isinstance(raw_address, Mapping) else {}
    label = _text(item.get("display_name"))
    name = _text(item.get("name")) or _fallback_name(address, label)
    if not name:
        name = f"{latitude:.5f}, {longitude:.5f}"
    return Place(
        name=name,
        label=label or name,
        latitude=latitude,
        longitude=longitude,
        bounds=_bounds(item.get("boundingbox")),
        address=address_from_nominatim(address, name=name, kind=_text(item.get("addresstype"))),
    )


def _fallback_name(address: Mapping[str, object], label: str) -> str:
    """Nombre de un lugar que no tiene: la calle y el número («Calle de Alcalá, 42») o, si
    no, lo primero del nombre completo."""
    road = _text(address.get("road"))
    if road:
        number = _text(address.get("house_number"))
        return f"{road}, {number}" if number else road
    return label.split(",")[0].strip()


def _bounds(value: object) -> Bounds | None:
    """El rectángulo de Nominatim (['sur', 'norte', 'oeste', 'este'], como textos) en el
    orden de la aplicación (sur, oeste, norte, este); None si no vale."""
    if not isinstance(value, Sequence) or isinstance(value, str) or len(value) != 4:
        return None
    numbers = [_number(part) for part in value]
    if any(number is None for number in numbers):
        return None
    south, north, west, east = numbers
    if not (_valid_position(south, west) and _valid_position(north, east)):
        return None
    if south > north or west > east:  # p. ej. un rectángulo que cruza el meridiano 180
        return None
    return (south, west, north, east)


# -----------------------------------------------------------------------------
# Las búsquedas recientes (se guardan en settings.json)
# -----------------------------------------------------------------------------


def remember_search(
    history: Iterable[HistoryEntry], query: str, place: Place, *, limit: int = HISTORY_LIMIT
) -> tuple[HistoryEntry, ...]:
    """El historial con esta búsqueda arriba del todo. Si ya estaba (sin distinguir
    mayúsculas), se quita de donde estaba; las que pasan de 'limit', fuera."""
    entries = tuple(history)
    text = normalize_query(query)
    if not text:
        return entries[:limit]
    key = text.casefold()
    kept = [entry for entry in entries if entry.query.casefold() != key]
    return (HistoryEntry(text, place), *kept)[:limit]


def recall_search(history: Iterable[HistoryEntry], query: str) -> Place | None:
    """El lugar de una búsqueda reciente con ese texto (sin distinguir mayúsculas), o None."""
    key = normalize_query(query).casefold()
    if not key:
        return None
    for entry in history:
        if entry.query.casefold() == key:
            return entry.place
    return None


def history_to_settings(history: Iterable[HistoryEntry]) -> list[dict[str, object]]:
    """El historial como se guarda en settings.json. De cada lugar, lo que hace falta para
    volver a él (la dirección repartida no se guarda: la caja no la usa)."""
    result: list[dict[str, object]] = []
    for entry in history:
        place = entry.place
        result.append({
            "query": entry.query,
            "name": place.name,
            "label": place.label,
            "latitude": place.latitude,
            "longitude": place.longitude,
            "bounds": list(place.bounds) if place.bounds is not None else None,
        })
    return result


def history_from_settings(
    value: object, *, limit: int = HISTORY_LIMIT
) -> tuple[HistoryEntry, ...]:
    """El historial leído de settings.json. Lo que no vale (editado a mano, de otra versión)
    se salta sin fallar; sin repetidos y como mucho 'limit'."""
    if not isinstance(value, list):
        return ()
    entries: list[HistoryEntry] = []
    seen: set[str] = set()
    for raw in value:
        entry = _entry_from_settings(raw)
        if entry is None or entry.query.casefold() in seen:
            continue
        seen.add(entry.query.casefold())
        entries.append(entry)
        if len(entries) >= limit:
            break
    return tuple(entries)


def _entry_from_settings(raw: object) -> HistoryEntry | None:
    if not isinstance(raw, Mapping):
        return None
    query = normalize_query(_text(raw.get("query")))
    name = _text(raw.get("name"))
    latitude, longitude = _number(raw.get("latitude")), _number(raw.get("longitude"))
    if not query or not name or latitude is None or longitude is None:
        return None
    if not _valid_position(latitude, longitude):
        return None
    bounds = None
    raw_bounds = raw.get("bounds")
    if isinstance(raw_bounds, list) and len(raw_bounds) == 4:
        # Guardado (sur, oeste, norte, este): se reordena como lo da Nominatim para validarlo
        south, west, north, east = raw_bounds
        bounds = _bounds([south, north, west, east])
    label = _text(raw.get("label")) or name
    return HistoryEntry(query, Place(name, label, latitude, longitude, bounds))


# -----------------------------------------------------------------------------
# Utilidades
# -----------------------------------------------------------------------------


def _text(value: object) -> str:
    """Un texto de la respuesta, sin espacios a los lados ('' si no es un texto)."""
    return value.strip() if isinstance(value, str) else ""


def _number(value: object) -> float | None:
    """Un número de la respuesta (Nominatim da las coordenadas como textos)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)):
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _valid_position(latitude: float, longitude: float) -> bool:
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


def _first(address: Mapping[str, object], keys: Sequence[str]) -> str:
    """El primer valor con texto de esas claves de la dirección."""
    for key in keys:
        text = _text(address.get(key))
        if text:
            return text
    return ""


if __name__ == "__main__":
    # Autoprueba (sin Qt y sin red), con respuestas como las de Nominatim.
    # Ejecutar desde la raíz del proyecto:  python -m core.maps.geocoding
    from urllib.parse import parse_qs

    # 1. El texto que se busca
    assert normalize_query("  Torla   Ordesa \n") == "Torla Ordesa"
    assert normalize_query("") == "" and normalize_query("   ") == ""
    assert len(normalize_query("x" * 500)) == MAX_QUERY_LENGTH

    # 2. La dirección del servicio: la guardada si vale; si no, la de partida
    assert service_url_from_settings(None) == DEFAULT_SERVICE_URL
    assert service_url_from_settings("http://localhost:8080/") == "http://localhost:8080"
    assert service_url_from_settings(" https://geo.example.com/nominatim ") == (
        "https://geo.example.com/nominatim")
    for bad in ("", "ftp://x.org", "nominatim.org", "https://x.org/?a=1", "https://[::1",
                42, ["https://x.org"]):
        assert service_url_from_settings(bad) == DEFAULT_SERVICE_URL, bad

    # 3. La petición: parámetros, acentos y espacios bien codificados, 'viewbox' en su orden
    url = search_url(DEFAULT_SERVICE_URL + "/", "  Calle de Alcalá  42 ",
                     viewbox=(40.0, -4.0, 41.0, -3.0))
    assert url.startswith("https://nominatim.openstreetmap.org/search?"), url
    params = {key: values[0] for key, values in parse_qs(url.split("?", 1)[1]).items()}
    assert params == {
        "q": "Calle de Alcalá 42", "format": "jsonv2", "addressdetails": "1", "limit": "1",
        "accept-language": "es", "viewbox": "-4.000000,40.000000,-3.000000,41.000000",
    }, params
    assert "bounded" not in params  # da preferencia a lo que se ve, no filtra
    # El límite, entre 1 y 40; un 'viewbox' que da la vuelta al mundo se recorta; uno vacío,
    # fuera
    assert "limit=40" in search_url(DEFAULT_SERVICE_URL, "x", limit=99)
    assert "limit=1" in search_url(DEFAULT_SERVICE_URL, "x", limit=0)
    assert _viewbox((-95.0, -200.0, 95.0, 250.0)) == (
        "-180.000000,-90.000000,180.000000,90.000000")
    for bad in ((41.0, -3.0, 40.0, -4.0), (40.0, -3.0, 40.0, -3.0), (math.nan, 0, 1, 1),
                ("a", 0, 1, 1)):
        assert _viewbox(bad) is None, bad
    try:
        search_url(DEFAULT_SERVICE_URL, "   ")
    except ValueError:
        pass
    else:
        raise AssertionError("una búsqueda vacía debe rechazarse")

    # 4. La respuesta: un pueblo, un museo, una ciudad extranjera y una dirección sin nombre
    licence = "Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright"
    response = json.dumps([
        {
            "place_id": 1, "licence": licence, "osm_type": "relation", "osm_id": 347898,
            "lat": "42.6266", "lon": "-0.1116", "category": "boundary",
            "type": "administrative", "place_rank": 16, "addresstype": "village",
            "name": "Torla-Ordesa",
            "display_name": "Torla-Ordesa, Sobrarbe, Huesca, Aragón, España",
            "address": {
                "village": "Torla-Ordesa", "county": "Sobrarbe", "province": "Huesca",
                "ISO3166-2-lvl6": "ES-HU", "state": "Aragón", "ISO3166-2-lvl4": "ES-AR",
                "country": "España", "country_code": "es",
            },
            "boundingbox": ["42.5487", "42.7344", "-0.1987", "0.0386"],
        },
        {
            "lat": "40.4137818", "lon": "-3.6921271", "category": "tourism", "type": "museum",
            "addresstype": "tourism", "name": "Museo Nacional del Prado",
            "display_name": "Museo Nacional del Prado, Paseo del Prado, Jerónimos, Retiro, "
                            "Madrid, Comunidad de Madrid, 28014, España",
            "address": {
                "tourism": "Museo Nacional del Prado", "road": "Paseo del Prado",
                "neighbourhood": "Jerónimos", "suburb": "Retiro", "city": "Madrid",
                "state": "Comunidad de Madrid", "postcode": "28014", "country": "España",
                "country_code": "es",
            },
            "boundingbox": ["40.4128", "40.4148", "-3.6936", "-3.6904"],
        },
        {
            "lat": "51.5074456", "lon": "-0.1277653", "addresstype": "city", "name": "Londres",
            "display_name": "Londres, Greater London, Inglaterra, Reino Unido",
            "address": {
                "city": "Londres", "state_district": "Greater London", "state": "Inglaterra",
                "country": "Reino Unido", "country_code": "gb",
            },
            "boundingbox": ["51.2867601", "51.6918741", "-0.5103751", "0.3340155"],
        },
        {
            "lat": "40.4380", "lon": "-3.6780", "addresstype": "building", "name": "",
            "display_name": "42, Calle de General Pardiñas, Salamanca, Madrid, España",
            "address": {"house_number": "42", "road": "Calle de General Pardiñas",
                        "suburb": "Salamanca", "city": "Madrid", "country": "España",
                        "country_code": "es"},
        },
        {"lat": "91", "lon": "0", "name": "Fuera del mundo"},  # coordenadas imposibles
        {"lat": "x", "lon": "0", "name": "Sin número"},
        "no es un lugar",
    ]).encode("utf-8")
    places = parse_search(response)
    assert [place.name for place in places] == [
        "Torla-Ordesa", "Museo Nacional del Prado", "Londres", "Calle de General Pardiñas, 42"]
    torla, prado, london, street = places
    assert (torla.latitude, torla.longitude) == (42.6266, -0.1116)
    assert torla.label == "Torla-Ordesa, Sobrarbe, Huesca, Aragón, España"
    # El rectángulo, en el orden de la aplicación (sur, oeste, norte, este)
    assert torla.bounds == (42.5487, -0.1987, 42.7344, 0.0386), torla.bounds
    assert street.bounds is None and street.label.startswith("42, Calle")
    # La dirección repartida: la provincia como región; el sitio concreto como sububicación
    assert torla.address == PlaceAddress("", "Torla-Ordesa", "Huesca", "España", "ES")
    assert prado.address == PlaceAddress(
        "Museo Nacional del Prado", "Madrid", "Comunidad de Madrid", "España", "ES")
    assert london.address == PlaceAddress("", "Londres", "Inglaterra", "Reino Unido", "GB")
    assert street.address.sublocation == "Calle de General Pardiñas, 42"
    assert not torla.address.is_empty() and PlaceAddress().is_empty()
    # Sin dirección: un lugar con nombre y coordenadas, nada más
    bare = parse_search('[{"lat": 1.5, "lon": 2.5, "display_name": "Algo, Lejos"}]')[0]
    assert (bare.name, bare.label, bare.address) == ("Algo", "Algo, Lejos", PlaceAddress())
    nameless = parse_search('[{"lat": "1.5", "lon": "2.5"}]')[0]
    assert nameless.name == nameless.label == "1.50000, 2.50000"

    # 5. Reglas del reparto (lo provisional, escrito una vez)
    assert address_from_nominatim({"town": "Rascafría", "municipality": "Otro"}).city == (
        "Rascafría")
    assert address_from_nominatim({"hamlet": "Aldea", "municipality": "Municipio"}).city == (
        "Municipio")
    assert address_from_nominatim({"state": "Escocia", "state_district": "X"}).region == "Escocia"
    assert address_from_nominatim({"country_code": "e1"}).country_code == ""
    # El nombre del lugar no es sububicación si es la propia población o algo mayor
    assert address_from_nominatim({"city": "Madrid"}, name="Madrid", kind="").sublocation == ""
    assert address_from_nominatim({}, name="Retiro", kind="suburb").sublocation == "Retiro"
    assert address_from_nominatim({}, name="Huesca", kind="province").sublocation == ""
    # Valores que no son textos, fuera
    assert address_from_nominatim({"city": 3, "country": None}) == PlaceAddress()

    # 6. Respuestas que no valen
    assert parse_search(b"[]") == []
    for bad in (b"<html>Too Many Requests</html>", b'{"error": "Unable to geocode"}',
                b'{"lat": 1}', b"\xff\xfe", b""):
        try:
            parse_search(bad)
        except GeocodingResponseError as error:
            assert isinstance(error, GeocodingError)
        else:
            raise AssertionError(f"debería rechazarse: {bad!r}")
    # Rectángulos que no valen
    assert _bounds(["1", "2", "3"]) is None and _bounds("1234") is None
    assert _bounds(["2", "1", "0", "1"]) is None  # el sur, al norte del norte
    assert _bounds(["-91", "1", "0", "1"]) is None
    assert _bounds(["0", "1", "179", "-179"]) is None  # cruza el meridiano 180

    # 7. El historial: la última arriba, sin repetidas (ni por las mayúsculas), con tope
    history: tuple[HistoryEntry, ...] = ()
    history = remember_search(history, "Torla", torla)
    history = remember_search(history, "museo del prado", prado)
    history = remember_search(history, "  TORLA ", torla)
    assert [entry.query for entry in history] == ["TORLA", "museo del prado"]
    assert remember_search(history, "   ", london) == history  # nada que recordar
    assert recall_search(history, "torla") is torla
    assert recall_search(history, "Museo   del Prado") is prado
    assert recall_search(history, "Londres") is None and recall_search(history, "") is None
    for number in range(15):
        history = remember_search(history, f"Lugar {number}", london)
    assert len(history) == HISTORY_LIMIT and history[0].query == "Lugar 14"
    assert remember_search(history, "otra", london, limit=3)[2].query == "Lugar 13"

    # 8. El historial en settings.json: ida y vuelta (sin la dirección repartida)
    history = (HistoryEntry("Torla", torla), HistoryEntry("calle", street))
    stored = history_to_settings(history)
    assert stored[0] == {
        "query": "Torla", "name": "Torla-Ordesa", "label": torla.label,
        "latitude": 42.6266, "longitude": -0.1116,
        "bounds": [42.5487, -0.1987, 42.7344, 0.0386],
    }, stored[0]
    assert stored[1]["bounds"] is None
    stored = json.loads(json.dumps(stored))  # como sale de settings.json
    restored = history_from_settings(stored)
    assert [entry.query for entry in restored] == ["Torla", "calle"]
    assert restored[0].place == Place(torla.name, torla.label, torla.latitude,
                                      torla.longitude, torla.bounds)
    assert restored[1].place.bounds is None
    # Lo que no vale se salta; los repetidos, también; con tope
    messy = [
        "texto", {"query": "", "name": "x", "latitude": 1, "longitude": 1},
        {"query": "sin nombre", "latitude": 1, "longitude": 1},
        {"query": "fuera", "name": "x", "latitude": 100, "longitude": 1},
        {"query": "torla", "name": "Repetida", "latitude": 1, "longitude": 1},
        {"query": "malo", "name": "Rectángulo malo", "latitude": 1, "longitude": 1,
         "bounds": [3, 0, 1, 1]},
        *stored,
    ]
    restored = history_from_settings(messy)
    assert [entry.query for entry in restored] == ["torla", "malo", "calle"], restored
    assert restored[1].place.bounds is None and restored[0].place.label == "Repetida"
    assert history_from_settings(None) == () and history_from_settings({"a": 1}) == ()
    assert len(history_from_settings(stored, limit=1)) == 1

    print("Autoprueba finalizada correctamente.")
