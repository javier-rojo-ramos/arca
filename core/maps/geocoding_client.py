"""Pide al servicio de búsqueda de lugares (Nominatim) lo que arma 'geocoding.py'.

Este módulo NO depende de Qt: usa 'urllib', de la librería estándar, y BLOQUEA mientras
espera la respuesta (hasta 'timeout' segundos, más la espera de su turno). Por eso se
llama siempre desde un hilo secundario: la caja de búsqueda del mapa (GEN 8.4) y, más
adelante, el trabajo de ubicar fotos a partir de su GPS (GEN 8.5, con 'JobManager').

Aquí se cumplen las condiciones de uso de Nominatim (ver 'geocoding.py'):
    - Un turno ('RequestGate'): UNA petición cada vez y, entre el final de una y el
      principio de la siguiente, al menos 'MIN_INTERVAL_S' (1 s). Hay UNO para toda la
      aplicación ('SHARED_GATE'): el límite cuenta lo que pide la aplicación entera, sea la
      caja del mapa o un trabajo.
    - Un 'User-Agent' propio (obligatorio: el que pone 'urllib' no vale).
    - Un tiempo máximo de espera y un tamaño máximo de la respuesta.

Errores (todos son 'GeocodingError', de 'geocoding.py'):
    GeocodingNetworkError   sin conexión, el servidor no se encuentra o no contesta a tiempo
    GeocodingServiceError   el servicio contesta con un error HTTP ('status': 429 si se le
                            pide demasiado, 503 si está saturado...)
    GeocodingResponseError  lo que contesta no se entiende
    GeocodingCancelled      se canceló mientras esperaba su turno

Uso (en un hilo secundario):
    client = GeocodingClient(tile_layers.user_agent(APP_VERSION), service_url=url)
    places = client.search("Torla", viewbox=(sur, oeste, norte, este))  # [] si no hay nada

1.0.0 Primera versión (GEN 8.4a).

Prueba rápida (desde la raíz del proyecto; sin red):
    python -m core.maps.geocoding_client
"""

__version__ = "1.0.0"
__all__ = [
    "DEFAULT_TIMEOUT_S",
    "MAX_RESPONSE_BYTES",
    "MIN_INTERVAL_S",
    "SHARED_GATE",
    "GeocodingCancelled",
    "GeocodingClient",
    "GeocodingNetworkError",
    "GeocodingServiceError",
    "RequestGate",
    "Transport",
]

# Librerías estándar
import http.client
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager

# Módulos del proyecto
from core.maps.geocoding import (
    DEFAULT_LANGUAGE,
    DEFAULT_SERVICE_URL,
    Bounds,
    GeocodingError,
    GeocodingResponseError,
    Place,
    normalize_query,
    parse_search,
    search_url,
)

# Lo más que se espera la respuesta del servicio
DEFAULT_TIMEOUT_S = 10.0
# Separación mínima entre dos peticiones (Nominatim: como mucho una por segundo)
MIN_INTERVAL_S = 1.0
# Un lugar ocupa alrededor de 1 KB: una respuesta de más de 1 MB es que algo va mal
MAX_RESPONSE_BYTES = 1024 * 1024
# Cada cuánto se mira si se ha cancelado mientras se espera el turno
_POLL_S = 0.05

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


# El turno de toda la aplicación (lo comparten la caja del mapa y los trabajos)
SHARED_GATE = RequestGate()


class GeocodingClient:
    """Busca lugares en el servicio (ver el docstring del archivo). Bloquea: siempre desde
    un hilo secundario."""

    def __init__(
        self,
        user_agent: str,
        *,
        service_url: str = DEFAULT_SERVICE_URL,
        timeout: float = DEFAULT_TIMEOUT_S,
        gate: RequestGate | None = None,
        transport: Transport | None = None,
    ) -> None:
        """
        Args:
            user_agent: La identificación de la aplicación ('tile_layers.user_agent').
            service_url: La dirección del servicio ('geocoding.service_url_from_settings').
            timeout: Lo más que se espera la respuesta, en segundos.
            gate: El turno (de partida, el de toda la aplicación: 'SHARED_GATE').
            transport: Quién hace la petición (de partida, 'urllib').

        Raises:
            ValueError: Sin 'User-Agent' propio (Nominatim no admite el de 'urllib').
        """
        agent = user_agent.strip()
        if not agent or agent.casefold().startswith("python-urllib"):
            raise ValueError("Hace falta un 'User-Agent' propio de la aplicación")
        self.user_agent = agent
        self.service_url = service_url.rstrip("/")
        self.timeout = timeout
        self._gate = gate if gate is not None else SHARED_GATE
        self._transport = transport if transport is not None else _urlopen

    def search(
        self,
        query: str,
        *,
        viewbox: Bounds | None = None,
        language: str = DEFAULT_LANGUAGE,
        limit: int = 1,
        cancel_event: threading.Event | None = None,
    ) -> list[Place]:
        """Los lugares que encuentra el servicio para ese texto, el mejor primero ([] si no
        encuentra nada o no hay nada que buscar: entonces no se pide nada).

        Args:
            query: Lo que se busca.
            viewbox: Lo que se ve en el mapa (sur, oeste, norte, este): lo de dentro, antes.
            language: Idioma de los nombres.
            limit: Cuántos lugares (la caja del mapa va al primero: uno).
            cancel_event: Si se activa mientras espera su turno, no se pide nada.

        Raises:
            GeocodingError: Si no se ha podido buscar (ver los tipos en el docstring del
                archivo).
        """
        if not normalize_query(query):
            return []
        url = search_url(self.service_url, query, viewbox=viewbox, language=language,
                         limit=limit)
        return parse_search(self._fetch(url, language, cancel_event))

    def _fetch(self, url: str, language: str, cancel_event: threading.Event | None) -> bytes:
        """Los bytes de la respuesta, en su turno."""
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": language,
        })
        with self._gate.turn(cancel_event):
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


def _urlopen(request: urllib.request.Request, timeout: float) -> bytes:
    """La petición de verdad. Lee como mucho un byte más del tope, para saber si lo pasa."""
    with urllib.request.urlopen(request, timeout=timeout) as response:
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

    print("Autoprueba finalizada correctamente.")
