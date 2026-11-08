"""Carga en segundo plano de la miniatura grande (2560 px) para la vista individual.

La vista individual muestra un archivo a toda la pantalla. Su imagen sale de la caché de
miniaturas: la FULLSCREEN (2560 px) o, si no existe, la mayor que haya
('ThumbnailCache.resolve'). Leer y decodificar un JPEG de ese tamaño tarda, así que se
hace SIEMPRE en un hilo del pool (CLAUDE.md: nada largo en el hilo principal).

    loader.image(media_type, media_id)    # la imagen si ya está en memoria; si no, la pide
    loader.loaded -> (media_id, QImage)   # cuando llega (QImage nula = no tiene miniatura)
    loader.prefetch([(tipo, id), ...])    # el anterior y el siguiente: las flechas, al momento
    loader.forget(ids)                    # sus miniaturas se han regenerado: releerlas
    loader.forget_missing()               # volver a buscar las que no tenían miniatura

Detalles:
    - Un solo hilo propio: no le quita sitio a la cuadrícula (que tiene el suyo).
    - Guarda en memoria las últimas MAX_IMAGES imágenes (la actual y las vecinas).
    - Las respuestas de otro catálogo se descartan (contador de generación): los 'id' de
      dos catálogos pueden coincidir.
    - Los archivos sin miniatura se recuerdan para no buscarlos en cada repintado.

1.0.0 Primera versión (paso A.1, subpaso 4).

Prueba rápida (desde la raíz del proyecto; crea una caché temporal y no abre ventanas):
    python -m ui_helpers.models.full_image_loader
"""

__version__ = "1.0.0"
__all__ = ["FullImageLoader"]

# Librerías estándar
from collections import OrderedDict
from collections.abc import Callable, Iterable

# Librerías de terceros (Qt)
from qtpy.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from qtpy.QtGui import QImage, QImageReader

# Módulos del proyecto
from core.thumbnails.cache import ThumbnailCache
from core.thumbnails.sizes import ThumbnailSize

# Qué se pide a la caché: la mayor (si no existe, 'resolve' da la mayor que haya)
_WANTED = ThumbnailSize.FULLSCREEN


class _Signals(QObject):
    """Canal por el que el hilo devuelve la imagen: (generación, id, imagen)."""

    done = Signal(int, int, QImage)


class _Task(QRunnable):
    """Lee de la caché la miniatura grande de un elemento (en un hilo del pool)."""

    def __init__(
        self, cache: ThumbnailCache, media_type: str, media_id: int, generation: int, signals: _Signals
    ) -> None:
        super().__init__()
        self._cache = cache
        self._media_type = media_type
        self._media_id = media_id
        self._generation = generation
        self._signals = signals

    def run(self) -> None:
        image = QImage()
        try:
            path = self._cache.resolve(self._media_type, self._media_id, _WANTED)
            if path is not None:
                # Las miniaturas de la caché ya están derechas: no hay que rotarlas
                image = QImageReader(str(path)).read()
        except (OSError, ValueError):
            image = QImage()  # «sin miniatura»: un hilo nunca debe lanzar
        self._signals.done.emit(self._generation, self._media_id, image)


class FullImageLoader(QObject):
    """Imágenes grandes de la caché, leídas en segundo plano (ver el docstring del archivo).

    Signals:
        loaded(int, QImage): ha llegado la imagen de un 'id' (nula si no tiene miniatura).
    """

    loaded = Signal(int, QImage)

    # Imágenes que se guardan en memoria (una de 2560 px ocupa unos 17 MB)
    MAX_IMAGES = 5

    def __init__(
        self,
        cache_provider: Callable[[], tuple[str, ThumbnailCache | None]],
        parent: QObject | None = None,
    ) -> None:
        """Prepara el cargador.

        Args:
            cache_provider: Devuelve (clave del catálogo abierto, su caché o None). Se
                consulta en cada petición: si cambia la clave, se olvida todo lo anterior.
            parent: Objeto padre.
        """
        super().__init__(parent)
        self._cache_provider = cache_provider
        self._catalog_key = ""
        self._generation = 0
        self._images: OrderedDict[int, QImage] = OrderedDict()
        self._pending: set[int] = set()
        self._missing: set[int] = set()  # sin miniatura (no se vuelven a buscar)

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._signals = _Signals(self)
        self._signals.done.connect(self._on_done, Qt.ConnectionType.QueuedConnection)

    # -------------------------------------------------------------------------
    # Interfaz pública
    # -------------------------------------------------------------------------

    def image(self, media_type: str, media_id: int) -> QImage | None:
        """La imagen si ya está en memoria; si no, la pide (llegará por 'loaded').

        Returns:
            La imagen; una QImage NULA si se sabe que no tiene miniatura; None si se está
            leyendo (o no hay catálogo).
        """
        cache = self._current_cache()
        if media_id in self._images:
            self._images.move_to_end(media_id)
            return self._images[media_id]
        if media_id in self._missing:
            return QImage()
        if cache is not None and media_id not in self._pending:
            self._start(cache, media_type, media_id, priority=1)
        return None

    def prefetch(self, items: Iterable[tuple[str, int]]) -> None:
        """Pide de antemano estas imágenes (las vecinas), con menos prioridad."""
        cache = self._current_cache()
        if cache is None:
            return
        for media_type, media_id in items:
            if media_id not in self._images and media_id not in self._missing and media_id not in self._pending:
                self._start(cache, media_type, media_id, priority=0)

    def forget(self, media_ids: Iterable[int] | None = None) -> None:
        """Olvida estas imágenes (o todas, con None): sus miniaturas se han regenerado."""
        if media_ids is None:
            self._images.clear()
            self._missing.clear()
            return
        for media_id in media_ids:
            self._images.pop(media_id, None)
            self._missing.discard(media_id)

    def forget_missing(self) -> None:
        """Vuelve a buscar las que no tenían miniatura (mientras se generan)."""
        self._missing.clear()

    def shutdown(self) -> None:
        """Para las lecturas y espera a la que está en curso (al cerrar la aplicación)."""
        self._generation += 1
        self._pool.clear()
        self._pool.waitForDone()

    # -------------------------------------------------------------------------
    # Interno
    # -------------------------------------------------------------------------

    def _current_cache(self) -> ThumbnailCache | None:
        """La caché del catálogo abierto; si es otro catálogo, olvida todo lo de antes."""
        key, cache = self._cache_provider()
        if key != self._catalog_key:
            self._catalog_key = key
            self._generation += 1  # lo que esté en camino es del catálogo anterior
            self._pool.clear()
            self._images.clear()
            self._pending.clear()
            self._missing.clear()
        return cache

    def _start(self, cache: ThumbnailCache, media_type: str, media_id: int, priority: int) -> None:
        self._pending.add(media_id)
        self._pool.start(_Task(cache, media_type, media_id, self._generation, self._signals), priority)

    def _on_done(self, generation: int, media_id: int, image: QImage) -> None:
        if generation != self._generation:
            return  # de otro catálogo (o tras cerrarlo)
        self._pending.discard(media_id)
        if image.isNull():
            self._missing.add(media_id)
        else:
            self._images[media_id] = image
            self._images.move_to_end(media_id)
            while len(self._images) > self.MAX_IMAGES:
                self._images.popitem(last=False)
        self.loaded.emit(media_id, image)


if __name__ == "__main__":
    # Autoprueba SIN ventana: una caché temporal con dos miniaturas de prueba.
    # Ejecutar desde la raíz del proyecto:  python -m ui_helpers.models.full_image_loader
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image
    from qtpy.QtCore import QCoreApplication, QEventLoop, QTimer

    app = QCoreApplication([])

    def wait_for(loader: FullImageLoader, count: int) -> list[tuple[int, QImage]]:
        """Espera (sin bloquear la cola de eventos) a que lleguen 'count' imágenes."""
        got: list[tuple[int, QImage]] = []
        loop = QEventLoop()
        loader.loaded.connect(lambda media_id, image: (got.append((media_id, image)),
                                                       loop.quit() if len(got) >= count else None))  # fmt: skip
        QTimer.singleShot(5000, loop.quit)  # por si algo fallara: no se queda colgado
        loop.exec()
        return got

    with tempfile.TemporaryDirectory() as folder:
        cache = ThumbnailCache(Path(folder))
        # Elemento 1: la de 2560 y la de 480; el 2 y del 4 al 9: solo la de 480; el 3, ninguna
        items = [(1, (ThumbnailSize.FULLSCREEN, ThumbnailSize.MEDIUM))]
        items += [(media_id, (ThumbnailSize.MEDIUM,)) for media_id in (2, 4, 5, 6, 7, 8, 9)]
        for media_id, sizes in items:
            for size in sizes:
                path = cache.path_for("photo", media_id, size)
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (size.max_side, size.max_side * 2 // 3), "gray").save(path, "JPEG")

        state = {"key": "A", "cache": cache}
        loader = FullImageLoader(lambda: (state["key"], state["cache"]))

        # Primera petición: aún no está (None) y llega por 'loaded'; la mayor que hay
        assert loader.image("photo", 1) is None
        (media_id, image), = wait_for(loader, 1)
        assert media_id == 1 and image.width() == 2560
        assert loader.image("photo", 1).width() == 2560  # ya en memoria: al momento
        # Sin la de 2560: la mayor que haya (480)
        loader.prefetch([("photo", 2)])
        (media_id, image), = wait_for(loader, 1)
        assert media_id == 2 and image.width() == 480
        # Sin ninguna miniatura: QImage nula, y se recuerda
        assert loader.image("photo", 3) is None
        (media_id, image), = wait_for(loader, 1)
        assert media_id == 3 and image.isNull() and loader.image("photo", 3).isNull()
        loader.forget_missing()  # se vuelve a buscar (sigue sin haberla)
        assert loader.image("photo", 3) is None
        wait_for(loader, 1)
        # Olvidar: se vuelve a leer
        loader.forget([1])
        assert loader.image("photo", 1) is None
        wait_for(loader, 1)

        # Otro catálogo: se olvida todo (los 'id' pueden coincidir)
        state["key"] = "B"
        assert loader.image("photo", 1) is None
        wait_for(loader, 1)
        # Sin catálogo: no se pide nada
        state["key"], state["cache"] = "", None
        assert loader.image("photo", 1) is None and not loader._pending

        # Memoria acotada
        state["key"], state["cache"] = "C", cache
        for media_id in range(1, 10):
            loader.image("photo", media_id)
        wait_for(loader, 9)  # 8 con miniatura y el 3 sin ella
        assert len(loader._images) == FullImageLoader.MAX_IMAGES, len(loader._images)
        loader.shutdown()
    print("Autoprueba finalizada correctamente.")
