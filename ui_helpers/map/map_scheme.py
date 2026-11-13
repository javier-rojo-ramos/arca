"""Esquema 'arca-map://': de dónde saca la página del mapa todo lo que pide.

La página del mapa (resources/map/) NO habla con Internet ni lee el disco: todo lo pide a
este esquema propio, que atiende Python. Diseño en docs/MAPA.md (§3.2).

    arca-map://app/<archivo>               recursos de la página (resources/map/) y
                                           'qwebchannel.js', que viene dentro de Qt
    arca-map://tiles/<capa>/<z>/<x>/<y>    una tesela: de la caché ('TileStore') si está;
                                           si no, se descarga, se guarda y se devuelve
    arca-map://thumb/<media_id>            la miniatura de un marcador (la da una función:
                                           'set_thumbnail_provider')

Ventajas de pasar por aquí: la caché y el uso sin conexión los controla la aplicación;
un solo sitio se identifica ante los servidores ('User-Agent') y, si un día hay claves,
no llegan a la página; y todo tiene el mismo origen (sin problemas de permisos web).

DOS OBLIGACIONES DE Qt (ver docs/TRAMPAS.md):
    - 'register_map_scheme()' se llama ANTES de crear QApplication (lo hace main.py).
      Después ya no se puede registrar un esquema, y el mapa no cargaría.
    - Este módulo importa QtWebEngineCore, que también debe importarse antes de crear
      QApplication: por eso main.py lo importa aunque el mapa no se abra.

Teselas caducadas (docs/MAPA.md, §3.3): se devuelven en el acto y se renuevan por detrás.
Lo que se ejecuta aquí lo hace en el hilo principal (Qt llama ahí a 'requestStarted'):
leer un archivo pequeño de la caché es inmediato y las descargas son asíncronas.

Uso:
    register_map_scheme()                   # main.py, antes de QApplication
    handler = shared_handler()              # el único de la aplicación (lo crea 'WebMapBackend')
    handler.set_thumbnail_provider(funcion) # al abrir un catálogo

1.1.0 El tipo de cada tesela se mira en sus bytes (las capas propias no dicen si sirven
      PNG o JPEG).
1.0.0 Primera versión (docs/MAPA.md, paso 1.3).
"""

__version__ = "1.1.0"
__all__ = ["SCHEME", "START_URL", "MapSchemeHandler", "register_map_scheme", "shared_handler"]

# Librerías estándar
from collections.abc import Callable, Sequence
from functools import cache, partial
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Librerías de terceros (Qt)
from qtpy.QtCore import QBuffer, QByteArray, QCoreApplication, QFile, QIODevice, QObject, Qt, QUrl
from qtpy.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qtpy.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

# Módulos del proyecto
from config import app_paths
from core.maps.tile_layers import TILE_LAYERS, TileLayer, is_valid_tile, tile_url, user_agent
from core.maps.tile_store import TileStorageError, TileStore, image_mime

SCHEME = "arca-map"
START_URL = f"{SCHEME}://app/index.html"

_SCHEME_BYTES = SCHEME.encode("ascii")

# Tipo MIME de los recursos de la página, por su extensión
_ASSET_MIME_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}
# Tipo MIME de una miniatura, por su extensión (la caché las guarda en JPEG)
_THUMBNAIL_MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

_Job = QWebEngineUrlRequestJob
ThumbnailProvider = Callable[[int], Path | None]


def register_map_scheme() -> bool:
    """Da de alta el esquema 'arca-map'. Hay que llamarla ANTES de crear QApplication.

    También pide a Qt que comparta los contextos gráficos, que QtWebEngine necesita y que
    solo se puede pedir antes de crear la aplicación.

    Returns:
        True si el esquema queda registrado (o ya lo estaba); False si se llamó tarde.
    """
    if QWebEngineUrlScheme.schemeByName(_SCHEME_BYTES).name():
        return True  # ya registrado
    if QCoreApplication.instance() is not None:
        logger.error(
            "El esquema del mapa se ha intentado registrar después de crear QApplication: "
            "el mapa no podrá cargar su página."
        )
        return False
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    scheme = QWebEngineUrlScheme(_SCHEME_BYTES)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
    )
    QWebEngineUrlScheme.registerScheme(scheme)
    return True


class MapSchemeHandler(QWebEngineUrlSchemeHandler):
    """Atiende las peticiones de la página del mapa (ver el docstring del archivo)."""

    def __init__(
        self,
        store: TileStore,
        *,
        assets_dir: Path,
        agent: str,
        parent: QObject | None = None,
    ) -> None:
        """
        Args:
            store: Caché de teselas.
            assets_dir: Carpeta de los recursos de la página (resources/map).
            agent: Identificación ante los servidores de teselas ('User-Agent').
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._store = store
        self._assets_dir = assets_dir.resolve()
        self._agent = agent.encode("ascii", "replace")
        self._network = QNetworkAccessManager(self)
        self._layers: dict[str, TileLayer] = {layer.key: layer for layer in TILE_LAYERS}
        self._thumbnail_provider: ThumbnailProvider | None = None
        # Descargas en curso: tesela -> peticiones de la página que la esperan (vacío si
        # solo se está renovando una caducada). Así una tesela no se baja dos veces a la vez
        self._downloads: dict[tuple[str, int, int, int], list[_Job]] = {}
        self._storage_warned = False
        self._failures_logged = 0

    # -------------------------------------------------------------------------
    # Configuración
    # -------------------------------------------------------------------------

    def set_layers(self, layers: Sequence[TileLayer]) -> None:
        """Capas de las que se sirven teselas (las de fábrica y, más adelante, las del usuario)."""
        self._layers = {layer.key: layer for layer in layers}

    def set_thumbnail_provider(self, provider: ThumbnailProvider | None) -> None:
        """Función que da la ruta de la miniatura de un 'media_items.id' (None si no tiene).
        None = sin miniaturas (catálogo cerrado)."""
        self._thumbnail_provider = provider

    # -------------------------------------------------------------------------
    # Peticiones
    # -------------------------------------------------------------------------

    def requestStarted(self, job: _Job) -> None:  # nombre de Qt
        url = job.requestUrl()
        host, parts = url.host(), [part for part in url.path().split("/") if part]
        try:
            if host == "app":
                self._serve_asset(job, parts)
            elif host == "tiles" and len(parts) == 4:
                self._serve_tile(job, parts[0], int(parts[1]), int(parts[2]), int(parts[3]))
            elif host == "thumb" and len(parts) == 1:
                self._serve_thumbnail(job, int(parts[0]))
            else:
                job.fail(_Job.Error.UrlNotFound)
        except ValueError:  # un número que no lo es
            job.fail(_Job.Error.UrlInvalid)

    @staticmethod
    def _reply(job: _Job, mime: str, data: bytes) -> None:
        """Responde con unos bytes. El búfer es hijo de la petición: se borra con ella."""
        try:
            buffer = QBuffer(job)
            buffer.setData(QByteArray(data))
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            job.reply(QByteArray(mime.encode("ascii")), buffer)
        except RuntimeError:
            pass  # la página ya no espera esa petición (se canceló al mover el mapa)

    @staticmethod
    def _fail(job: _Job, error: _Job.Error = _Job.Error.RequestFailed) -> None:
        try:
            job.fail(error)
        except RuntimeError:
            pass  # petición ya cancelada

    # --- Recursos de la página ---

    def _serve_asset(self, job: _Job, parts: list[str]) -> None:
        if parts == ["qwebchannel.js"]:
            resource = QFile(":/qtwebchannel/qwebchannel.js")  # recurso del módulo QtWebChannel
            if resource.open(QIODevice.OpenModeFlag.ReadOnly):
                self._reply(job, "text/javascript", bytes(resource.readAll()))
            else:
                logger.error("No se encuentra qwebchannel.js en los recursos de Qt.")
                self._fail(job, _Job.Error.UrlNotFound)
            return
        path = self._assets_dir.joinpath(*parts).resolve()
        # Nada de fuera de la carpeta de recursos ('..')
        if self._assets_dir not in path.parents or not path.is_file():
            self._fail(job, _Job.Error.UrlNotFound)
            return
        mime = _ASSET_MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
        try:
            self._reply(job, mime, path.read_bytes())
        except OSError as error:
            logger.error(f"No se pudo leer un recurso del mapa ({path.name}): {error}")
            self._fail(job)

    # --- Teselas ---

    def _serve_tile(self, job: _Job, layer_key: str, z: int, x: int, y: int) -> None:
        layer = self._layers.get(layer_key)
        if layer is None or not is_valid_tile(layer, z, x, y):
            self._fail(job, _Job.Error.UrlNotFound)
            return
        cached = self._store.read(layer, z, x, y)
        if cached is not None:
            self._reply(job, image_mime(cached.data) or layer.mime_type, cached.data)
            if cached.stale:
                self._download(layer, z, x, y, None)  # se renueva por detrás
            return
        self._download(layer, z, x, y, job)

    def _download(self, layer: TileLayer, z: int, x: int, y: int, job: _Job | None) -> None:
        """Descarga una tesela (o se apunta a la descarga que ya hay en curso)."""
        key = (layer.key, z, x, y)
        waiting = self._downloads.get(key)
        if waiting is not None:
            if job is not None:
                waiting.append(job)
            return
        self._downloads[key] = [job] if job is not None else []
        request = QNetworkRequest(QUrl(tile_url(layer, z, x, y)))
        # Con 'setRawHeader': 'setHeader' no acepta bytes desde Python (avisa y no la pone)
        request.setRawHeader(b"User-Agent", self._agent)
        reply = self._network.get(request)
        reply.finished.connect(partial(self._on_downloaded, reply, layer, key))

    def _on_downloaded(
        self, reply: QNetworkReply, layer: TileLayer, key: tuple[str, int, int, int]
    ) -> None:
        reply.deleteLater()
        jobs = self._downloads.pop(key, [])
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        data = bytes(reply.readAll())
        if reply.error() != QNetworkReply.NetworkError.NoError or status != 200 or not data:
            # Sin conexión es lo normal aquí: se anota poco, para no llenar el registro
            if self._failures_logged < 3:
                self._failures_logged += 1
                logger.warning(
                    f"No se pudo descargar una tesela de {layer.key!r} "
                    f"(estado {status}): {reply.errorString()}"
                )
            for job in jobs:
                self._fail(job)
            return
        self._failures_logged = 0
        try:
            self._store.write(layer, key[1], key[2], key[3], data)
        except ValueError:
            # El servidor ha contestado algo que no es una imagen (una página de aviso)
            logger.warning(f"El servidor de {layer.key!r} no ha devuelto una imagen.")
            for job in jobs:
                self._fail(job)
            return
        except TileStorageError as error:
            # El mapa sigue funcionando sin caché: se avisa una sola vez
            if not self._storage_warned:
                self._storage_warned = True
                logger.warning(f"La caché de mapas no se puede escribir: {error}")
        for job in jobs:
            self._reply(job, image_mime(data) or layer.mime_type, data)

    # --- Miniaturas ---

    def _serve_thumbnail(self, job: _Job, media_id: int) -> None:
        path = self._thumbnail_provider(media_id) if self._thumbnail_provider else None
        if path is None:
            self._fail(job, _Job.Error.UrlNotFound)  # la página pinta el recuadro vacío
            return
        try:
            data = path.read_bytes()
        except OSError:
            self._fail(job, _Job.Error.UrlNotFound)
            return
        self._reply(job, _THUMBNAIL_MIME_TYPES.get(path.suffix.lower(), "image/jpeg"), data)


@cache
def shared_handler() -> MapSchemeHandler:
    """El manejador de la aplicación (uno solo, compartido por todos los mapas).

    Se crea la primera vez que se pide, ya con QApplication, y se instala en el perfil por
    defecto de QtWebEngine, que es el que usan las páginas del mapa.
    """
    profile = QWebEngineProfile.defaultProfile()
    handler = MapSchemeHandler(
        TileStore(app_paths.TILE_CACHE_DIR),
        assets_dir=app_paths.RESOURCES_DIR / "map",
        agent=user_agent(app_paths.APP_VERSION),
        parent=profile,
    )
    profile.installUrlSchemeHandler(_SCHEME_BYTES, handler)
    return handler
