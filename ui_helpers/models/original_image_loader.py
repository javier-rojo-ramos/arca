"""Carga en segundo plano del ORIGINAL de una foto, para verla a 1:1 en la vista individual.

La imagen sale de 'core/thumbnails/full_image.py' (el original a tamaño completo, con el
color de la caché). Decodificar una foto de 24 megapíxeles tarda unas décimas de segundo,
así que se hace SIEMPRE en un hilo (CLAUDE.md: nada largo en el hilo principal).

    loader.request(media_type, media_id, ruta)  # pide el original (olvida lo pedido antes)
    loader.loaded -> (media_id, QImage)         # cuando llega (nula si no se pudo leer)
    loader.cancel()                             # ya no hace falta (se ha salido del 1:1)

Detalles:
    - Un solo hilo propio: no le quita sitio a la cuadrícula ni a la vista individual.
    - Solo cuenta lo ÚLTIMO pedido: lo anterior que aún no ha empezado se descarta, y lo
      que se esté leyendo no se puede parar, pero su resultado se ignora (contador de
      generación).
    - No guarda nada: la imagen la guarda quien la pidió, y la suelta al salir del 1:1
      (una foto de 24 megapíxeles ocupa unos 100 MB).
    - Los orígenes de las miniaturas ('default_registry') se crean la primera vez que hacen
      falta, EN EL HILO: buscar ExifTool arranca un proceso.
    - La imagen llega en formato RGB32, el que Qt dibuja sin convertir.

1.0.0 Primera versión (vista individual a 1:1, paso 3).

Prueba rápida (desde la raíz del proyecto; crea archivos temporales y no abre ventanas):
    python -m ui_helpers.models.original_image_loader
"""

__version__ = "1.0.0"
__all__ = ["OriginalImageLoader"]

# Librerías estándar
import threading
from collections.abc import Callable
from pathlib import Path

# Librerías de terceros
from loguru import logger
from PIL import Image

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from qtpy.QtGui import QImage

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.thumbnails.full_image import load_full_image
from core.thumbnails.registry import SourceRegistry, default_registry
from core.thumbnails.sources.base import ThumbnailError, ThumbnailRequest


def to_qimage(image: Image.Image) -> QImage:
    """Una imagen RGB de Pillow como QImage RGB32 con sus propios datos (se puede usar en
    cualquier hilo y soltar la de Pillow)."""
    data = image.tobytes("raw", "RGB")
    wrapped = QImage(data, image.width, image.height, 3 * image.width, QImage.Format.Format_RGB888)
    # 'convertToFormat' hace una copia: 'data' ya no hace falta después
    return wrapped.convertToFormat(QImage.Format.Format_RGB32)


class _Signals(QObject):
    """Canal por el que el hilo devuelve la imagen: (generación, id, imagen)."""

    done = Signal(int, int, QImage)


class _Task(QRunnable):
    """Lee el original de un elemento (en el hilo del cargador)."""

    def __init__(
        self,
        registry: Callable[[], SourceRegistry],
        request: ThumbnailRequest,
        generation: int,
        signals: _Signals,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._request = request
        self._generation = generation
        self._signals = signals

    def run(self) -> None:
        image = QImage()
        name = self._request.path.name
        try:
            full = load_full_image(self._request, self._registry())
            try:
                image = to_qimage(full.image)
            finally:
                full.image.close()
        except FileNotFoundError:
            logger.warning(f"Vista 1:1: el original ya no existe: {self._request.path}")
        except ThumbnailError as error:
            logger.warning(f"Vista 1:1: no se pudo leer el original de {name}: {error}")
        # Un hilo nunca debe lanzar: cualquier otro fallo, al registro, y la imagen, nula
        except Exception as error:  # noqa: BLE001
            logger.exception(f"Vista 1:1: fallo inesperado al leer {name}: {error}")
        self._signals.done.emit(self._generation, self._request.media_id, image)


class OriginalImageLoader(QObject):
    """Originales leídos en segundo plano (ver el docstring del archivo).

    Signals:
        loaded(int, QImage): ha llegado el original de un 'id' (nulo si no se pudo leer).
    """

    loaded = Signal(int, QImage)

    def __init__(
        self,
        parent: QObject | None = None,
        registry_factory: Callable[[], SourceRegistry] = default_registry,
    ) -> None:
        """Prepara el cargador (los orígenes, aún no: ver el docstring del archivo).

        Args:
            parent: Objeto padre.
            registry_factory: Crea los orígenes (en las pruebas, unos de mentira).
        """
        super().__init__(parent)
        self._registry_factory = registry_factory
        self._registry: SourceRegistry | None = None
        self._registry_lock = threading.Lock()
        self._generation = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._signals = _Signals(self)
        self._signals.done.connect(self._on_done, Qt.ConnectionType.QueuedConnection)

    def request(self, media_type: str, media_id: int, path: Path) -> None:
        """Pide el original de un elemento; lo pedido antes deja de contar."""
        self.cancel()
        try:
            kind = MediaType(media_type)
        except ValueError:
            kind = MediaType.PHOTO  # el registro decide por la extensión
        request = ThumbnailRequest(media_id, kind, Path(path))
        self._pool.start(_Task(self._registry_for_thread, request, self._generation, self._signals))

    def cancel(self) -> None:
        """Lo pedido ya no hace falta: no se empieza y, si ya se está leyendo, se ignora."""
        self._generation += 1
        self._pool.clear()

    def shutdown(self) -> None:
        """Para lo pendiente y espera a la lectura en curso (al cerrar la aplicación)."""
        self.cancel()
        self._pool.waitForDone()

    def _registry_for_thread(self) -> SourceRegistry:
        """Los orígenes, creados la primera vez (lo llama el hilo del cargador)."""
        with self._registry_lock:
            if self._registry is None:
                self._registry = self._registry_factory()
            return self._registry

    def _on_done(self, generation: int, media_id: int, image: QImage) -> None:
        if generation == self._generation:
            self.loaded.emit(media_id, image)


if __name__ == "__main__":
    # Autoprueba SIN ventana: archivos de verdad en una carpeta temporal.
    # Ejecutar desde la raíz:  python -m ui_helpers.models.original_image_loader
    import os
    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtCore import QCoreApplication, QEventLoop, QTimer

    from core.thumbnails import _testing
    from core.thumbnails.sources.pillow_source import PillowSource

    app = QCoreApplication([])

    def pillow_only() -> SourceRegistry:
        registry = SourceRegistry()
        registry.register(PillowSource())
        return registry

    def wait(loader: OriginalImageLoader, milliseconds: int = 4000) -> list[tuple[int, QImage]]:
        """Recoge lo que llegue durante un rato (sin bloquear la cola de eventos)."""
        got: list[tuple[int, QImage]] = []
        loop = QEventLoop()
        loader.loaded.connect(lambda media_id, image: (got.append((media_id, image)), loop.quit()))
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()
        QTimer.singleShot(300, loop.quit)  # por si llegara algo más (no debe)
        loop.exec()
        return got

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "a.jpg").write_bytes(_testing.jpeg_bytes((3000, 2000), orientation=6, marker=True))
        (base / "b.jpg").write_bytes(_testing.jpeg_bytes((1200, 800)))

        # 1. El original, entero, derecho y en RGB32
        loader = OriginalImageLoader(registry_factory=pillow_only)
        loader.request("photo", 1, base / "a.jpg")
        got = wait(loader)
        assert [(media_id, image.width(), image.height()) for media_id, image in got] == [(1, 2000, 3000)]
        image = got[0][1]
        assert image.format() == QImage.Format.Format_RGB32
        red = image.pixelColor(1990, 10)  # la marca roja, arriba a la derecha tras girarla
        assert red.red() > 200 and red.green() < 60, red.name()

        # 2. Solo cuenta lo último pedido
        loader.request("photo", 1, base / "a.jpg")
        loader.request("photo", 2, base / "b.jpg")
        got = wait(loader)
        assert [media_id for media_id, _image in got] == [2], got

        # 3. Cancelado: no llega nada
        loader.request("photo", 1, base / "a.jpg")
        loader.cancel()
        assert wait(loader, 1500) == []

        # 4. Un archivo que no existe: imagen nula (y un aviso en el registro)
        loader.request("photo", 3, base / "no_existe.jpg")
        got = wait(loader)
        assert len(got) == 1 and got[0][0] == 3 and got[0][1].isNull()
        loader.shutdown()
    print("Autoprueba finalizada correctamente.")
