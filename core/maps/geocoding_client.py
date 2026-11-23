"""Pide a los servicios de búsqueda de lugares (Nominatim y CartoCiudad) lo que arma
'geocoding.py', y decide a cuál y en qué orden ('find').

Este módulo NO depende de Qt: usa 'urllib', de la librería estándar, y BLOQUEA mientras
espera la respuesta (hasta 'timeout' segundos, más la espera de su turno). Por eso se
llama siempre desde un hilo secundario: la caja de búsqueda del mapa (GEN 8.4) y, más
adelante, el trabajo de ubicar fotos a partir de su GPS (GEN 8.5, con 'JobManager').

Aquí se cumplen las condiciones de uso de Nominatim (ver 'geocoding.py'):
    - Un turno ('RequestGate'): UNA petición cada vez y, entre el final de una y el
      principio de la siguiente, al menos 'MIN_INTERVAL_S' (1 s). Hay UNO para toda la
      aplicación ('SHARED_GATE'): el límite cuenta lo que pide la aplicación entera, sea la
      caja del mapa o un trabajo. CartoCiudad tiene el suyo ('CARTOCIUDAD_GATE'), con la
      misma separación por cortesía (no publica límites).
    - Un 'User-Agent' propio (obligatorio: el que pone 'urllib' no vale).
    - Un tiempo máximo de espera y un tamaño máximo de la respuesta.

Qué se pregunta y en qué orden ('find'; decidido por el autor el 23/11/2026, GEN 8.4d):
    Con número de portal («López de Hoyos, 345»), solo vale lo que ES LO ESCRITO
    ('geocoding.match_score'): su calle (CartoCiudad y Nominatim dan también calles que se le
    parecen: «Castelar, 7, Madrid» daba «Calle Mastelero, 7») y, si se escribe, el pueblo o
    la ciudad (que decide: «Calle Mayor 5, Torla» da la de Torla, mire donde mire el mapa);
    una errata en una palabra larga se perdona, y lo exacto va antes. Y sin pueblo escrito,
    manda la ZONA del mapa ('geocoding.zone': unos 30 km alrededor de su centro, la ciudad
    que se mira), no solo lo que hay en pantalla:
        1. Un portal de CartoCiudad (los oficiales de España) en la zona.
        2. Si no, Nominatim SOLO en la zona ('bounded'), con el número escrito.
        3. Si no, Nominatim en la zona, la calle aunque no tenga ese número (en un pueblo, a
           OpenStreetMap le faltan números): lo de la zona va antes que un portal lejano.
        4. Si no, un portal de CartoCiudad, esté donde esté (el pueblo escrito dice dónde:
           «López de Hoyos, 345, Madrid» con el mapa en otra parte).
        5. Si no, como un nombre (abajo), sin volver a preguntar a CartoCiudad; de lo que dé
           Nominatim, antes lo que es lo escrito.
    Historia (23/11/2026, el autor): primero se miraba solo lo que había en pantalla y sin
    comprobar nada; con el mapa sobre México, «Calle Luis de Salazar, 3» daba «Avenida Vicente
    C. Salazar, 3», y moviendo un poco el mapa, «Castelar, 7» acababa en Pego.
    Sin número (un nombre de lugar: «Torla», «Londres», «Santiago de Chile»):
        1. Nominatim en todo el mundo, por importancia (lo que se ve, solo como preferencia):
           limitarlo, o preguntar antes a CartoCiudad, daría la calle de Londres de Madrid.
           Se piden 5 y vale el primero que llegue al 75 % de la importancia del mayor
           ('RELEVANCE_SHARE'): la preferencia por lo que se ve sube cosas pequeñas («Santiago
           de Chile», con el mapa en España, daba un local de Barcelona; «Toledo», viendo
           Madrid, la Puerta de Toledo), pero «Santiago» sigue dando el de Galicia.
        2. Si no encuentra nada, CartoCiudad (sus topónimos: parajes, arroyos, picos...), lo
           que sea lo escrito, antes lo que caiga en lo que se ve.
    Si CartoCiudad falla (sin conexión, un certificado...), se sigue sin él, como si no
    hubiera encontrado nada (se apunta en el registro). Si falla Nominatim y CartoCiudad
    tiene algo, vale eso; si no, el error de Nominatim.

Certificados: con 'truststore' (si está instalada; requirements.txt), Python comprueba los
certificados con el sistema, como un navegador. Sin ella, en Windows solo valen las raíces
que el sistema ya tiene: la de CartoCiudad (HARICA, 2021) Windows la instala la primera vez
que la necesita un navegador, y hasta entonces CartoCiudad falla (y se sigue sin él). En
macOS, el Python de python.org (y el empaquetado) no usa los certificados del sistema: sin
'truststore', ninguna búsqueda funcionaría (docs/TRAMPAS.md).

Errores (todos son 'GeocodingError', de 'geocoding.py'):
    GeocodingNetworkError   sin conexión, el servidor no se encuentra o no contesta a tiempo
    GeocodingServiceError   el servicio contesta con un error HTTP ('status': 429 si se le
                            pide demasiado, 503 si está saturado...)
    GeocodingResponseError  lo que contesta no se entiende
    GeocodingCancelled      se canceló mientras esperaba su turno

Uso (en un hilo secundario):
    client = GeocodingClient(tile_layers.user_agent(APP_VERSION), service_url=url)
    places = client.find("Torla", viewbox=(sur, oeste, norte, este))  # [] si no hay nada
    places = client.search("Torla")         # solo Nominatim
    places = client.cartociudad("Torla")    # solo CartoCiudad

1.1.0 CartoCiudad ('cartociudad', con su turno 'CARTOCIUDAD_GATE'); 'find', la búsqueda
      con los dos servicios (solo lo que es lo escrito; sin pueblo escrito, la zona del
      mapa); 'search(..., bounded=)'; los certificados, con 'truststore' si está instalada
      (GEN 8.4d).
1.0.0 Primera versión (GEN 8.4a).

Prueba rápida (desde la raíz del proyecto; sin red):
    python -m core.maps.geocoding_client
"""

__version__ = "1.1.0"
__all__ = [
    "CARTOCIUDAD_GATE",
    "DEFAULT_TIMEOUT_S",
    "MAX_RESPONSE_BYTES",
    "MIN_INTERVAL_S",
    "NAME_RESULTS",
    "RELEVANCE_SHARE",
    "SHARED_GATE",
    "GeocodingCancelled",
    "GeocodingClient",
    "GeocodingNetworkError",
    "GeocodingServiceError",
    "RequestGate",
    "Transport",
    "uses_system_certificates",
]

# Librerías estándar
import http.client
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from functools import cache

# Librerías de terceros
from loguru import logger

try:  # opcional: sin ella, los certificados que ya tenga el sistema (ver el docstring)
    import truststore
except ImportError:
    truststore = None

# Módulos del proyecto
from core.maps.geocoding import (
    CARTOCIUDAD_URL,
    DEFAULT_LANGUAGE,
    DEFAULT_SERVICE_URL,
    KIND_PORTAL,
    Bounds,
    GeocodingError,
    GeocodingResponseError,
    Place,
    cartociudad_url,
    has_house_number,
    inside,
    match_score,
    normalize_query,
    parse_cartociudad,
    parse_search,
    search_url,
    written_number,
    zone,
)

# Lo más que se espera la respuesta del servicio
DEFAULT_TIMEOUT_S = 10.0
# Separación mínima entre dos peticiones (Nominatim: como mucho una por segundo)
MIN_INTERVAL_S = 1.0
# Un lugar ocupa alrededor de 1 KB: una respuesta de más de 1 MB es que algo va mal
MAX_RESPONSE_BYTES = 1024 * 1024
# Cada cuánto se mira si se ha cancelado mientras se espera el turno
_POLL_S = 0.05
# Un nombre de lugar: cuántos resultados se piden a Nominatim, y cuánto tiene que importar
# el elegido respecto al que más (ver el docstring del archivo)
NAME_RESULTS = 5
RELEVANCE_SHARE = 0.75

# Lo que hace la petición: recibe la petición y el tiempo máximo, devuelve los bytes. El de
# verdad es '_urlopen'; las autopruebas ponen uno de mentira
Transport = Callable[[urllib.request.Request, float], bytes]


class GeocodingNetworkError(GeocodingError):
    """Sin conexión, el servidor no se encuentra o no contesta a tiempo."""


class GeocodingServiceError(GeocodingError):
    """El servicio contesta con un error HTTP.

    Attributes:
        status: El código HTTP (429: demasiadas peticiones; 503: saturado...).
    """

    def __init__(self, status: int, reason: str = "") -> None:
        super().__init__(f"El servicio de búsqueda responde {status} {reason}".strip())
        self.status = status


class GeocodingCancelled(GeocodingError):
    """Se canceló mientras esperaba su turno (no se llegó a pedir nada)."""


class RequestGate:
    """El turno de las peticiones: una cada vez y, entre el final de una y el principio de
    la siguiente, al menos 'interval' segundos. Se puede usar desde varios hilos.

    Uso:
        with gate.turn(cancel_event):
            ...   # la petición
    """

    def __init__(
        self,
        interval: float = MIN_INTERVAL_S,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """
        Args:
            interval: Segundos entre dos peticiones.
            clock, sleep: El reloj y la espera (las autopruebas ponen unos de mentira).
        """
        self.interval = interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_end: float | None = None  # cuándo terminó la última petición

    @contextmanager
    def turn(self, cancel_event: threading.Event | None = None) -> Iterator[None]:
        """Espera su turno y lo ocupa mientras dura el bloque 'with'.

        Raises:
            GeocodingCancelled: Si 'cancel_event' se activa mientras espera (no se entra
                en el bloque).
        """
        self._acquire(cancel_event)
        try:
            if self._last_end is not None:
                remaining = self._last_end + self.interval - self._clock()
                if remaining > 0:
                    self._wait(remaining, cancel_event)
            try:
                yield
            finally:
                # Cuenta desde el final: una respuesta lenta no acerca la siguiente petición
                self._last_end = self._clock()
        finally:
            self._lock.release()

    def _acquire(self, cancel_event: threading.Event | None) -> None:
        if cancel_event is None:
            self._lock.acquire()
            return
        while not self._lock.acquire(timeout=_POLL_S):
            if cancel_event.is_set():
                raise GeocodingCancelled("Búsqueda cancelada")
        if cancel_event.is_set():
            self._lock.release()
            raise GeocodingCancelled("Búsqueda cancelada")

    def _wait(self, seconds: float, cancel_event: threading.Event | None) -> None:
        if cancel_event is None:
            self._sleep(seconds)
        elif cancel_event.wait(seconds):
            raise GeocodingCancelled("Búsqueda cancelada")


# El turno de Nominatim para toda la aplicación (lo comparten la caja del mapa y los
# trabajos), y el de CartoCiudad
SHARED_GATE = RequestGate()
CARTOCIUDAD_GATE = RequestGate()


class GeocodingClient:
    """Busca lugares en los servicios (ver el docstring del archivo). Bloquea: siempre desde
    un hilo secundario."""

    def __init__(
        self,
        user_agent: str,
        *,
        service_url: str = DEFAULT_SERVICE_URL,
        cartociudad_service_url: str = CARTOCIUDAD_URL,
        timeout: float = DEFAULT_TIMEOUT_S,
        gate: RequestGate | None = None,
        cartociudad_gate: RequestGate | None = None,
        transport: Transport | None = None,
    ) -> None:
        """
        Args:
            user_agent: La identificación de la aplicación ('tile_layers.user_agent').
            service_url: La dirección de Nominatim ('geocoding.service_url_from_settings').
            cartociudad_service_url: La de CartoCiudad.
            timeout: Lo más que se espera la respuesta, en segundos.
            gate: El turno de Nominatim (de partida, el de toda la aplicación: 'SHARED_GATE').
            cartociudad_gate: El de CartoCiudad (de partida, 'CARTOCIUDAD_GATE').
            transport: Quién hace la petición (de partida, 'urllib').

        Raises:
            ValueError: Sin 'User-Agent' propio (Nominatim no admite el de 'urllib').
        """
        agent = user_agent.strip()
        if not agent or agent.casefold().startswith("python-urllib"):
            raise ValueError("Hace falta un 'User-Agent' propio de la aplicación")
        self.user_agent = agent
        self.service_url = service_url.rstrip("/")
        self.cartociudad_service_url = cartociudad_service_url.rstrip("/")
        self.timeout = timeout
        self._gate = gate if gate is not None else SHARED_GATE
        self._cartociudad_gate = (
            cartociudad_gate if cartociudad_gate is not None else CARTOCIUDAD_GATE
        )
        self._transport = transport if transport is not None else _urlopen

    def find(
        self,
        query: str,
        *,
        viewbox: Bounds | None = None,
        language: str = DEFAULT_LANGUAGE,
        cancel_event: threading.Event | None = None,
    ) -> list[Place]:
        """El lugar que mejor responde a lo escrito, preguntando a CartoCiudad y a Nominatim
        en el orden del docstring del archivo: [lugar], o [] si ninguno encuentra nada (o
        no hay nada que buscar: entonces no se pide nada).

        Args:
            query: Lo que se busca.
            viewbox: Lo que se ve en el mapa (sur, oeste, norte, este).
            language: Idioma de los nombres (Nominatim).
            cancel_event: Si se activa mientras espera su turno, no se pide nada más.

        Raises:
            GeocodingError: Si Nominatim no ha podido buscar y CartoCiudad no tiene nada
                (ver los tipos en el docstring del archivo).
        """
        text = normalize_query(query)
        if not text:
            return []
        spain: list[Place] | None = None  # lo que ha dicho CartoCiudad (None = sin preguntar)
        numbered = has_house_number(text)
        if numbered:
            spain = self._cartociudad_quietly(text, cancel_event)
            # Solo los portales que son lo escrito, lo exacto antes
            portals = _written(text, [place for place in spain if place.kind == KIND_PORTAL])
            area = zone(viewbox)
            nearby = [place for place in portals if inside(place, area)]
            if nearby:
                return nearby[:1]
            local: list[Place] = []
            if area is not None:
                try:
                    local = _written(text, self.search(
                        text, viewbox=area, bounded=True, language=language,
                        limit=NAME_RESULTS, cancel_event=cancel_event))
                except GeocodingCancelled:
                    raise
                except GeocodingError:
                    if portals:
                        return portals[:1]
                    raise
                number = written_number(text)
                with_number = [place for place in local
                               if place.house_number.casefold() == number]
                if with_number:
                    return with_number[:1]
                if local:  # la calle escrita, en la zona, aunque sin ese número
                    return local[:1]
            if portals:
                return portals[:1]
        try:
            places = self.search(text, viewbox=viewbox, language=language,
                                 limit=NAME_RESULTS, cancel_event=cancel_event)
        except GeocodingCancelled:
            raise
        except GeocodingError:
            # Nominatim no responde: si CartoCiudad tiene algo que es lo escrito, vale eso
            if spain is None:
                spain = self._cartociudad_quietly(text, cancel_event)
            if found := _nearest_first(_written(text, spain), viewbox):
                return found[:1]
            raise
        if places:
            if numbered and (written := _written(text, places)):
                return written[:1]
            return [_most_relevant(places)]
        if spain is None:
            spain = self._cartociudad_quietly(text, cancel_event)
        return _nearest_first(_written(text, spain), viewbox)[:1]

    def search(
        self,
        query: str,
        *,
        viewbox: Bounds | None = None,
        bounded: bool = False,
        language: str = DEFAULT_LANGUAGE,
        limit: int = 1,
        cancel_event: threading.Event | None = None,
    ) -> list[Place]:
        """Los lugares que encuentra Nominatim para ese texto, el mejor primero ([] si no
        encuentra nada o no hay nada que buscar: entonces no se pide nada).

        Args:
            query: Lo que se busca.
            viewbox: Lo que se ve en el mapa (sur, oeste, norte, este): lo de dentro, antes.
            bounded: Solo lo de dentro de 'viewbox'.
            language: Idioma de los nombres.
            limit: Cuántos lugares (la caja del mapa va al primero: uno).
            cancel_event: Si se activa mientras espera su turno, no se pide nada.

        Raises:
            GeocodingError: Si no se ha podido buscar (ver los tipos en el docstring del
                archivo).
        """
        if not normalize_query(query):
            return []
        url = search_url(self.service_url, query, viewbox=viewbox, bounded=bounded,
                         language=language, limit=limit)
        return parse_search(self._fetch(url, self._gate, cancel_event, language))

    def cartociudad(
        self, query: str, *, cancel_event: threading.Event | None = None
    ) -> list[Place]:
        """Los candidatos de CartoCiudad con coordenadas, en su orden ([] si nada).

        Raises:
            GeocodingError: Si no se ha podido buscar.
        """
        if not normalize_query(query):
            return []
        url = cartociudad_url(self.cartociudad_service_url, query)
        data = self._fetch(url, self._cartociudad_gate, cancel_event)
        return parse_cartociudad(data, query)

    def _cartociudad_quietly(
        self, query: str, cancel_event: threading.Event | None
    ) -> list[Place]:
        """CartoCiudad, sin que su fallo pare la búsqueda: si falla, como si no hubiera
        encontrado nada (se apunta en el registro). Cancelar sí la para."""
        try:
            return self.cartociudad(query, cancel_event=cancel_event)
        except GeocodingCancelled:
            raise
        except GeocodingError as error:
            logger.warning(f"Búsqueda: CartoCiudad no ha respondido; se sigue sin él: {error}")
            return []

    def _fetch(
        self,
        url: str,
        gate: RequestGate,
        cancel_event: threading.Event | None,
        language: str = DEFAULT_LANGUAGE,
    ) -> bytes:
        """Los bytes de la respuesta, en su turno."""
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": language,
        })
        with gate.turn(cancel_event):
            try:
                data = self._transport(request, self.timeout)
            except urllib.error.HTTPError as error:  # antes que URLError: es una de ellas
                error.close()
                raise GeocodingServiceError(error.code, str(error.reason or "")) from error
            except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
                # URLError: sin conexión, nombre desconocido, certificado...; OSError:
                # tiempo agotado, conexión cortada; HTTPException: respuesta a medias
                raise GeocodingNetworkError(
                    f"No se ha podido conectar con el servicio de búsqueda: {error}"
                ) from error
        if len(data) > MAX_RESPONSE_BYTES:
            raise GeocodingResponseError("La respuesta del servicio es demasiado grande")
        return data


def _written(query: str, places: Sequence[Place]) -> list[Place]:
    """Los lugares que son lo escrito ('match_score'), lo exacto antes que lo que tiene una
    errata; entre iguales, en su orden."""
    scored = [(score, position, place) for position, place in enumerate(places)
              if (score := match_score(query, place)) is not None]
    return [place for _score, _position, place in sorted(scored, key=lambda item: item[:2])]


def _most_relevant(places: Sequence[Place]) -> Place:
    """De los resultados de Nominatim (en su orden), el primero que llega a
    'RELEVANCE_SHARE' de la importancia del que más importa (sin importancias, el primero)."""
    top = max(place.importance for place in places)
    if top <= 0:
        return places[0]
    return next(place for place in places if place.importance >= top * RELEVANCE_SHARE)


def _nearest_first(places: Sequence[Place], viewbox: Bounds | None) -> list[Place]:
    """Los lugares con los que caen en lo que se ve delante (el resto, en su orden)."""
    return sorted(places, key=lambda place: not inside(place, viewbox))


def uses_system_certificates() -> bool:
    """True si los certificados se comprueban con el sistema ('truststore' instalada)."""
    return truststore is not None


@cache
def _ssl_context() -> ssl.SSLContext | None:
    """El contexto TLS de las peticiones: el del sistema con 'truststore' o, sin ella, None
    (el de Python: en Windows, solo las raíces que el sistema ya tenga instaladas)."""
    if truststore is None:
        return None
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def _urlopen(request: urllib.request.Request, timeout: float) -> bytes:
    """La petición de verdad. Lee como mucho un byte más del tope, para saber si lo pasa."""
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        return response.read(MAX_RESPONSE_BYTES + 1)


if __name__ == "__main__":
    # Autoprueba SIN red: la petición la hace un 'transport' de mentira.
    # Ejecutar desde la raíz del proyecto:  python -m core.maps.geocoding_client
    import io
    import json
    from itertools import pairwise
    from urllib.parse import parse_qs, urlsplit

    ANSWER = json.dumps([{
        "lat": "42.6266", "lon": "-0.1116", "addresstype": "village", "name": "Torla-Ordesa",
        "display_name": "Torla-Ordesa, Sobrarbe, Huesca, Aragón, España",
        "address": {"village": "Torla-Ordesa", "province": "Huesca", "country": "España",
                    "country_code": "es"},
        "boundingbox": ["42.5487", "42.7344", "-0.1987", "0.0386"],
    }]).encode("utf-8")

    class FakeTransport:
        """Apunta las peticiones y responde lo que se le diga (o lanza el error)."""

        def __init__(self, answer: bytes | Exception = ANSWER) -> None:
            self.answer = answer
            self.requests: list[urllib.request.Request] = []

        def __call__(self, request: urllib.request.Request, timeout: float) -> bytes:
            self.requests.append(request)
            assert timeout == DEFAULT_TIMEOUT_S
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer

    fast_gate = RequestGate(0.0)

    # 1. Una búsqueda: la dirección, las cabeceras y el lugar
    transport = FakeTransport()
    client = GeocodingClient(" ArcaMedia/26.11.001 ", service_url="https://geo.example.com/",
                             gate=fast_gate, transport=transport)
    places = client.search("Torla", viewbox=(42.0, -1.0, 43.0, 0.5))
    assert [place.name for place in places] == ["Torla-Ordesa"]
    assert places[0].address.region == "Huesca"
    request = transport.requests[0]
    parts = urlsplit(request.full_url)
    assert (parts.scheme, parts.netloc, parts.path) == ("https", "geo.example.com", "/search")
    query = parse_qs(parts.query)
    assert query["q"] == ["Torla"] and query["format"] == ["jsonv2"]
    assert query["viewbox"] == ["-1.000000,42.000000,0.500000,43.000000"]
    # urllib guarda las cabeceras con la primera letra en mayúscula
    assert request.get_header("User-agent") == "ArcaMedia/26.11.001"
    assert request.get_header("Accept-language") == "es"
    # Nada que buscar: no se pide nada
    assert client.search("   ") == [] and len(transport.requests) == 1

    # 2. Sin 'User-Agent' propio no se crea
    for bad in ("", "   ", "Python-urllib/3.14"):
        try:
            GeocodingClient(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"debería rechazarse el User-Agent {bad!r}")

    # 3. Los errores, cada uno con su tipo (y todos son GeocodingError)
    http_error = urllib.error.HTTPError(
        "https://geo.example.com/search", 429, "Too Many Requests", None, io.BytesIO(b""))
    cases = [
        (http_error, GeocodingServiceError),
        (urllib.error.URLError("getaddrinfo failed"), GeocodingNetworkError),
        (TimeoutError("timed out"), GeocodingNetworkError),
        (ConnectionResetError("reset"), GeocodingNetworkError),
        (http.client.IncompleteRead(b"[{"), GeocodingNetworkError),
        (b"<html>no es JSON</html>", GeocodingResponseError),
        (b"[" + b" " * MAX_RESPONSE_BYTES + b"]", GeocodingResponseError),
    ]
    for answer, expected in cases:
        client = GeocodingClient("ArcaMedia/test", gate=fast_gate,
                                 transport=FakeTransport(answer))
        try:
            client.search("Torla")
        except expected as error:
            assert isinstance(error, GeocodingError)
            if expected is GeocodingServiceError:
                assert error.status == 429 and "429" in str(error)
        else:
            raise AssertionError(f"debería lanzar {expected.__name__}")

    # 4. El turno con un reloj de mentira: la segunda espera lo que falta del segundo
    now = [100.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    gate = RequestGate(1.0, clock=lambda: now[0], sleep=fake_sleep)
    with gate.turn():
        now[0] += 0.3  # la petición tarda 0,3 s
    assert sleeps == []  # la primera, sin esperar
    now[0] += 0.4  # 0,4 s después de terminar
    with gate.turn():
        pass
    assert len(sleeps) == 1 and abs(sleeps[0] - 0.6) < 1e-9, sleeps
    now[0] += 5.0  # mucho después: sin esperar
    with gate.turn():
        pass
    assert len(sleeps) == 1
    # Un error dentro del bloque también cuenta como petición hecha
    now[0] += 5.0
    try:
        with gate.turn():
            raise GeocodingNetworkError("sin conexión")
    except GeocodingNetworkError:
        pass
    with gate.turn():
        pass
    assert len(sleeps) == 2 and abs(sleeps[1] - 1.0) < 1e-9

    # 5. Desde varios hilos: nunca dos a la vez, y separadas al menos el intervalo
    interval = 0.12
    gate = RequestGate(interval)
    spans: list[tuple[float, float]] = []
    spans_lock = threading.Lock()

    def slow_transport(request: urllib.request.Request, timeout: float) -> bytes:
        start = time.monotonic()
        time.sleep(0.02)
        with spans_lock:
            spans.append((start, time.monotonic()))
        return b"[]"

    client = GeocodingClient("ArcaMedia/test", gate=gate, transport=slow_transport)
    threads = [threading.Thread(target=client.search, args=(f"lugar {n}",)) for n in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    spans.sort()
    assert len(spans) == 3, spans
    for (_start, end), (next_start, _end) in pairwise(spans):
        assert next_start - end >= interval - 0.01, spans

    # 6. Cancelar mientras se espera el turno: no se pide nada
    release = threading.Event()
    entered = threading.Event()

    def blocking_transport(request: urllib.request.Request, timeout: float) -> bytes:
        entered.set()
        release.wait(5)
        return b"[]"

    gate = RequestGate(0.0)
    busy = GeocodingClient("ArcaMedia/test", gate=gate, transport=blocking_transport)
    waiting_transport = FakeTransport()
    waiting = GeocodingClient("ArcaMedia/test", gate=gate, transport=waiting_transport)
    holder = threading.Thread(target=busy.search, args=("ocupa el turno",))
    holder.start()
    assert entered.wait(5)
    cancel = threading.Event()
    threading.Timer(0.1, cancel.set).start()
    try:
        waiting.search("espera", cancel_event=cancel)
    except GeocodingCancelled as error:
        assert isinstance(error, GeocodingError)
    else:
        raise AssertionError("debería cancelarse")
    assert waiting_transport.requests == []
    release.set()
    holder.join(timeout=5)
    # Cancelado antes de empezar, con el turno libre: tampoco se pide nada
    try:
        waiting.search("espera", cancel_event=cancel)
    except GeocodingCancelled:
        pass
    else:
        raise AssertionError("debería cancelarse")
    assert waiting_transport.requests == []
    # Y cancelado mientras espera la separación entre dos peticiones
    gate = RequestGate(5.0)
    spaced = GeocodingClient("ArcaMedia/test", gate=gate, transport=FakeTransport())
    spaced.search("primera")
    cancel = threading.Event()
    threading.Timer(0.1, cancel.set).start()
    started = time.monotonic()
    try:
        spaced.search("segunda", cancel_event=cancel)
    except GeocodingCancelled:
        assert time.monotonic() - started < 2.0  # no espera los 5 s
    else:
        raise AssertionError("debería cancelarse")

    # 7. 'find': qué se pregunta y en qué orden, con los dos servicios de mentira
    MADRID = (40.30, -3.85, 40.56, -3.52)
    MALAGA = (36.60, -4.65, 36.80, -4.35)
    BARCELONA = (41.30, 2.05, 41.50, 2.25)
    TORLA = (42.55, -0.25, 42.70, 0.05)

    def candidate(kind: str, address: str, lat: float, lng: float, portal: int | None = None,
                  muni: str = "Madrid", province: str = "Madrid") -> dict:
        return {"type": kind, "address": address, "portalNumber": portal, "muni": muni,
                "province": province, "lat": lat, "lng": lng}

    def osm(name: str, lat: float, lon: float, kind: str = "road", importance: float = 0,
            road: str | None = None, number: str = "", full_name: str = "") -> dict:
        """Un lugar de Nominatim; su calle, la que se diga o, si es una calle, su nombre."""
        street = road if road is not None else (name if kind == "road" else "")
        address = {"road": street} if street else {}
        if number:
            address["house_number"] = number
        return {"lat": str(lat), "lon": str(lon), "name": name,
                "display_name": full_name or name, "addresstype": kind,
                "importance": importance, "address": address}

    in_spain: dict[str, object] = {
        "luis de salazar, 3": [
            candidate("portal", "CALLE LUIS DE SALAZAR 3, Madrid", 40.4478, -3.6670, 3),
            candidate("portal", "CALLE LUIS SALAZAR 3, Campanillas (Málaga)", 36.7271, -4.5451,
                      3, "Málaga", "Málaga"),
        ],
        "calle mayor 5": [candidate("portal", "KALEA CALLE MAYOR 5 (Harana)", 42.7446, -2.3618,
                                    5, "Harana", "Araba/Álava")],
        "chorrera de mojonavalle": [candidate(
            "ngbe", "Arroyo de la Chorrera de Mojonavalle (Canencia)", 40.8623, -3.7875,
            muni="Canencia")],
        "rue de rivoli 10, paris": [], "torla": [],
    }
    in_spain["calle luis de salazar, 3"] = in_spain["luis de salazar, 3"]
    # Los casos del autor del 23/11/2026 (lo que daba CartoCiudad)
    in_spain["castelar, 7, madrid"] = [
        candidate("portal", "CALLE CASTELLO 7, Madrid", 40.4230, -3.6800, 7),
        candidate("portal", "CALLE MASTELERO 7, Madrid", 40.4700, -3.6400, 7),
        candidate("portal", "CALLE CASTELAR 7, Madrid", 40.4330, -3.6680, 7),
    ]
    in_spain["castelar, 7"] = [
        candidate("portal", "CALLE CASTELL DE CASTELLS 7, Pego", 38.8430, -0.1170, 7,
                  "Pego", "Alacant/Alicante"),
        candidate("portal", "CALLE CASTELAR 7, Albondón", 36.8270, -3.2100, 7,
                  "Albondón", "Granada"),
    ]
    in_spain["calle mayor 5, torla"] = [
        candidate("portal", "KALEA CALLE MAYOR 5 (Harana)", 42.7446, -2.3618, 5, "Harana",
                  "Araba/Álava"),
        candidate("portal", "CALLE MAYOR 5, Torla-Ordesa", 42.6270, -0.1110, 5,
                  "Torla-Ordesa", "Huesca"),
    ]
    in_spain["calle luis de slaazar, 3"] = [
        candidate("portal", "CALLE LUIS DE SALAZAR 3, Madrid", 40.4478, -3.6670, 3)]
    in_spain["calle lópez de hoyos, 345"] = [
        candidate("portal", "CALLE LOPEZ DE HOYOS 345, Madrid", 40.4686, -3.6529, 345)]
    in_osm: dict[tuple[str, bool], object] = {
        ("luis de salazar, 3", True): [],
        ("luis de salazar, 3", False): [osm("Avenida Vicente C. Salazar", 21.99, -99.02)],
        ("calle mayor 5", True): [osm("Calle Mayor", 42.6280, -0.1120)],
        # Con el mapa sobre México (lo que daba Nominatim el 23/11/2026): una calle parecida
        ("calle luis de salazar, 3", True): [
            osm("Multiservicios Loranet", 21.9940, -99.0221, "craft",
                road="Avenida Vicente C. Salazar")],
        ("rue de rivoli 10, paris", True): [],
        ("rue de rivoli 10, paris", False): [osm("Rue de Rivoli", 48.8606, 2.3376)],
        ("torla", False): [osm("Torla-Ordesa", 42.6277, -0.1121, "village")],
        ("chorrera de mojonavalle", False): [],
        ("castelar, 7", True): [osm("7", 40.4331, -3.6679, "place", road="Calle de Castelar",
                                    number="7", full_name="7, Calle de Castelar, Guindalera, "
                                    "Salamanca, Madrid, Comunidad de Madrid, 28028, España")],
        ("calle mayor 5, torla", True): [osm("Calle Mayor", 40.4155, -3.7090, number="5",
                                             full_name="Calle Mayor, Sol, Madrid, España")],
        # Nombres: lo que daba Nominatim el 23/11/2026, con la vista como preferencia
        ("santiago de chile", False): [
            osm("Santiago de Chile", 41.3852, 2.1429, "amenity", 0.0001),  # un local
            osm("Santiago de Chile", 42.8800, -8.5400, "highway", 0.0001),
            osm("Santiago", -33.4378, -70.6505, "city", 0.7289),
        ],
        ("toledo", False): [
            osm("Puerta de Toledo", 40.4068, -3.7114, "railway", 0.4086),
            osm("Puerta de Toledo", 40.4063, -3.7116, "building", 0.3702),
            osm("Toledo", 39.8567, -4.0244, "city", 0.6642),
            osm("Toledo", 41.6528, -83.5379, "city", 0.6293),
        ],
        ("santiago", False): [
            osm("Santiago", 42.8782, -8.5448, "county", 0.4571),
            osm("Santiago", 38.7139, -9.1334, "historic", 0.4045),
        ],
    }
    calls: list[tuple[str, str]] = []
    urls: list[str] = []

    def two_services(request: urllib.request.Request, timeout: float) -> bytes:
        urls.append(request.full_url)
        parts = urlsplit(request.full_url)
        query = parse_qs(parts.query)
        text = query["q"][0].casefold()
        if "cartociudad" in parts.netloc:
            calls.append(("cartociudad", text))
            answer = in_spain[text]
        else:
            bounded = "bounded" in query
            calls.append(("nominatim, en lo que se ve" if bounded else "nominatim", text))
            answer = in_osm[(text, bounded)]
            if bounded and isinstance(answer, list):
                # Como el servicio: limitado, solo lo de dentro del 'viewbox' pedido
                west, south, east, north = (float(v) for v in query["viewbox"][0].split(","))
                answer = [item for item in answer
                          if south <= float(item["lat"]) <= north
                          and west <= float(item["lon"]) <= east]
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer).encode("utf-8")

    both = GeocodingClient("ArcaMedia/test", gate=RequestGate(0.0),
                           cartociudad_gate=RequestGate(0.0), transport=two_services)

    def find(text: str, view: object) -> tuple[str | None, list[str]]:
        calls.clear()
        places = both.find(text, viewbox=view)  # type: ignore[arg-type]
        return (places[0].name if places else None), [service for service, _ in calls]

    # Una dirección en lo que se ve: CartoCiudad y nada más; el portal que cae en la vista
    assert find("Luis de Salazar, 3", MADRID) == ("Calle Luis de Salazar, 3", ["cartociudad"])
    assert find("Luis de Salazar, 3", MALAGA) == ("Calle Luis Salazar, 3", ["cartociudad"])
    # Con la vista en otra parte: Nominatim en lo que se ve y, si nada, el primer portal
    assert find("Luis de Salazar, 3", BARCELONA) == (
        "Calle Luis de Salazar, 3", ["cartociudad", "nominatim, en lo que se ve"])
    # Sin vista: el primer portal, sin preguntar a Nominatim
    assert find("Luis de Salazar, 3", None) == ("Calle Luis de Salazar, 3", ["cartociudad"])
    # Una calle de cientos de pueblos: lo de la vista (Nominatim) antes que un portal lejano
    assert find("Calle Mayor 5", TORLA) == (
        "Calle Mayor", ["cartociudad", "nominatim, en lo que se ve"])
    # Con el mapa en otro país, lo de la vista solo vale si es la calle escrita: «Avenida
    # Vicente C. Salazar» no es «Calle Luis de Salazar» -> el portal de Madrid
    MEXICO = (21.5, -99.5, 22.5, -98.5)
    assert find("Calle Luis de Salazar, 3", MEXICO) == (
        "Calle Luis de Salazar, 3", ["cartociudad", "nominatim, en lo que se ve"])
    # Lo que es lo escrito, no lo que se le parece; y sin pueblo escrito, la zona del mapa
    MASTELERO = (40.465, -3.645, 40.475, -3.635)  # en pantalla, Mastelero; Castelar, no
    assert find("Castelar, 7, Madrid", MASTELERO) == ("Calle Castelar, 7", ["cartociudad"])
    MADRID_MOVED = (40.445, -3.665, 40.455, -3.655)  # Madrid, pero sin Castelar en pantalla
    assert find("Castelar, 7", MADRID_MOVED) == (
        "7", ["cartociudad", "nominatim, en lo que se ve"])  # el de Madrid, por la zona
    VALENCIA = (39.44, -0.40, 39.50, -0.34)
    assert both.find("Castelar, 7", viewbox=VALENCIA)[0].label.startswith(
        "Calle Castelar, 7, Albondón")  # sin pueblo y lejos: el exacto, no Castell de Castells
    # El pueblo escrito decide, mire donde mire el mapa
    assert both.find("Calle Mayor 5, Torla", viewbox=MADRID)[0].address.city == "Torla-Ordesa"
    # Una errata en una palabra larga: vale
    assert find("Calle Luis de Slaazar, 3", MADRID) == (
        "Calle Luis de Salazar, 3", ["cartociudad"])
    # El portal, aunque no esté en pantalla, si está en la zona
    CHAMARTIN = (40.445, -3.685, 40.455, -3.675)
    assert find("Calle López de Hoyos, 345", CHAMARTIN) == (
        "Calle López de Hoyos, 345", ["cartociudad"])
    # Una dirección extranjera: CartoCiudad no la tiene; en lo que se ve, tampoco; en el mundo
    assert find("Rue de Rivoli 10, Paris", MADRID) == (
        "Rue de Rivoli", ["cartociudad", "nominatim, en lo que se ve", "nominatim"])
    # Un nombre: solo Nominatim, en todo el mundo
    assert find("Torla", MADRID) == ("Torla-Ordesa", ["nominatim"])
    # Por importancia: lo pequeño que sube la vista no gana a lo que se busca; lo comparable
    # en importancia, sí (lo de la vista, antes)
    SPAIN = (36.0, -9.5, 43.8, 3.3)
    calls.clear()
    chile = both.find("Santiago de Chile", viewbox=SPAIN)[0]
    assert (chile.kind, chile.latitude) == ("city", -33.4378), chile
    assert both.find("Toledo", viewbox=MADRID)[0].latitude == 39.8567  # la ciudad
    assert both.find("Santiago", viewbox=SPAIN)[0].kind == "county"  # el de Galicia
    # Para un nombre se piden varios a Nominatim (para poder elegir); en lo que se ve,
    # también (para quedarse con el de la calle escrita)
    assert parse_qs(urlsplit(urls[-1]).query)["limit"] == [str(NAME_RESULTS)]
    find("Calle Mayor 5", TORLA)
    assert parse_qs(urlsplit(urls[-1]).query)["limit"] == [str(NAME_RESULTS)]
    # Un nombre que Nominatim no tiene: los topónimos de CartoCiudad
    assert find("Chorrera de Mojonavalle", MADRID) == (
        "Arroyo de la Chorrera de Mojonavalle", ["nominatim", "cartociudad"])
    # Nada que buscar: no se pregunta nada
    assert find("   ", MADRID) == (None, [])

    # CartoCiudad no responde: se sigue sin él (aquí, Nominatim lo encuentra en México)
    in_spain["luis de salazar, 3"] = urllib.error.URLError("CERTIFICATE_VERIFY_FAILED")
    assert find("Luis de Salazar, 3", MADRID) == (
        "Avenida Vicente C. Salazar", ["cartociudad", "nominatim, en lo que se ve", "nominatim"])
    # Nominatim no responde: vale lo de CartoCiudad; si no tiene nada, el error
    in_osm[("chorrera de mojonavalle", False)] = TimeoutError("timed out")
    assert find("Chorrera de Mojonavalle", MADRID)[0] == "Arroyo de la Chorrera de Mojonavalle"
    in_osm[("torla", False)] = TimeoutError("timed out")
    try:
        find("Torla", MADRID)
    except GeocodingNetworkError:
        pass
    else:
        raise AssertionError("sin Nominatim ni CartoCiudad, el error de Nominatim")
    # Cancelar para la búsqueda (no cuenta como un fallo de CartoCiudad)
    cancel = threading.Event()
    cancel.set()
    try:
        both.find("Calle Mayor 5", viewbox=TORLA, cancel_event=cancel)
    except GeocodingCancelled:
        pass
    else:
        raise AssertionError("debería cancelarse")

    # 8. Los certificados: los del sistema con 'truststore', si está instalada
    if uses_system_certificates():
        assert isinstance(_ssl_context(), ssl.SSLContext)
        print("Certificados: los del sistema (truststore)")
    else:
        assert _ssl_context() is None
        print("Certificados: los de Python (sin truststore)")

    print("Autoprueba finalizada correctamente.")
