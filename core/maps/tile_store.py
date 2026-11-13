"""Almacén de teselas: la caché en disco de los mapas.

Este módulo NO depende de Qt ni de la red: solo guarda y devuelve archivos. Quien
descarga las teselas (el componente de mapa, con Qt; más adelante, el modelo de
elevaciones) le pregunta primero ('read') y le entrega lo descargado ('write').
Diseño completo en docs/MAPA.md (§3.3).

Dónde se guarda: en UNA carpeta para toda la aplicación (no en cada catálogo: las teselas
no son datos del catálogo y se pueden volver a descargar). La ruta la decide quien crea
el almacén; dentro, una carpeta por capa:

    <raíz>/<clave de la capa>/<z>/<x>/<y>.<extensión>

Reglas:
    - La FECHA del archivo es la de la descarga. Pasados 'max_age_days' (30 por defecto;
      la política de OpenStreetMap pide al menos 7), la tesela está CADUCADA: se sigue
      devolviendo (sin conexión vale siempre), pero 'read' lo dice para que quien pueda
      la descargue otra vez.
    - Solo se guardan IMÁGENES ('looks_like_image'): una página de error de un servidor
      no debe quedarse en la caché haciéndose pasar por un trozo de mapa.
    - Escritura ATÓMICA (archivo temporal + sustitución, como la caché de miniaturas):
      nunca queda una tesela a medias.
    - TOPE de tamaño ('max_bytes'; 2 GB por defecto): 'prune' borra las descargadas hace
      más tiempo hasta dejar la caché por debajo. Recorre toda la carpeta, así que se
      llama en segundo plano (al arrancar, no en cada escritura) y obedece 'cancel_event'.

Uso:
    store = TileStore(carpeta)
    cached = store.read(layer, z, x, y)        # None si no está
    if cached is None or cached.stale: ...     # descargar y 'store.write(layer, z, x, y, datos)'

1.0.0 Primera versión (docs/MAPA.md, paso 1.1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.maps.tile_store
"""

__version__ = "1.0.0"
__all__ = [
    "DEFAULT_MAX_AGE_DAYS",
    "DEFAULT_MAX_BYTES",
    "CachedTile",
    "PruneResult",
    "TileStorageError",
    "TileStore",
    "looks_like_image",
]

# Librerías estándar
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

# Módulos del proyecto
from core.maps.tile_layers import TileLayer, is_valid_key, is_valid_tile

# Días que vale una tesela antes de pedirla otra vez
DEFAULT_MAX_AGE_DAYS = 30
# Tamaño máximo de la caché (decidido por el autor el 13/11/2026: 2 GB)
DEFAULT_MAX_BYTES = 2 * 1024**3
# 'prune' deja la caché algo por debajo del tope, para no tener que limpiar cada vez
_PRUNE_TARGET = 0.9

_SECONDS_PER_DAY = 86_400


class TileStorageError(OSError):
    """No se pudo escribir en la caché de mapas (disco lleno, sin permisos...).

    El mapa puede seguir funcionando sin caché: quien escribe debe avisar una vez y
    continuar, no fallar por cada tesela.
    """


@dataclass(frozen=True, slots=True)
class CachedTile:
    """Una tesela leída de la caché.

    Attributes:
        data: Los bytes de la imagen.
        stale: True si está caducada (conviene descargarla otra vez; mientras, vale).
    """

    data: bytes
    stale: bool


@dataclass(frozen=True, slots=True)
class PruneResult:
    """Lo que ha hecho una limpieza.

    Attributes:
        files_removed: Teselas borradas.
        bytes_removed: Bytes liberados.
        bytes_left: Tamaño de la caché al terminar.
        cancelled: True si se interrumpió antes de acabar.
    """

    files_removed: int
    bytes_removed: int
    bytes_left: int
    cancelled: bool = False


def looks_like_image(data: bytes) -> bool:
    """True si los bytes empiezan como un PNG, un JPEG o un WebP."""
    if data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        return True
    return data.startswith(b"RIFF") and data[8:12] == b"WEBP"


class TileStore:
    """La caché de teselas en disco (ver el docstring del archivo)."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_age_days: float = DEFAULT_MAX_AGE_DAYS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        """No crea nada en el disco hasta la primera escritura.

        Args:
            root: Carpeta de la caché.
            max_age_days: Días que vale una tesela antes de darla por caducada.
            max_bytes: Tope de tamaño que respeta 'prune'.
        """
        self.root = Path(root)
        self.max_age_days = max_age_days
        self.max_bytes = max_bytes

    # -------------------------------------------------------------------------
    # Leer y escribir una tesela
    # -------------------------------------------------------------------------

    def path_for(self, layer: TileLayer, z: int, x: int, y: int) -> Path:
        """Ruta de una tesela en la caché (exista o no).

        Raises:
            ValueError: Si la clave de la capa no vale como carpeta o la tesela no existe
                en esa capa (así nunca se compone una ruta con datos que vengan de fuera).
        """
        if not is_valid_key(layer.key):
            raise ValueError(f"Clave de capa no válida: {layer.key!r}")
        if not is_valid_tile(layer, z, x, y):
            raise ValueError(f"Tesela fuera de la capa {layer.key!r}: z={z!r}, x={x!r}, y={y!r}")
        return self.root / layer.key / str(z) / str(x) / f"{y}.{layer.extension}"

    def read(self, layer: TileLayer, z: int, x: int, y: int) -> CachedTile | None:
        """La tesela guardada, o None si no está (o no se puede leer)."""
        path = self.path_for(layer, z, x, y)
        try:
            data = path.read_bytes()
            age = time.time() - path.stat().st_mtime
        except OSError:
            return None
        if not data:
            return None
        return CachedTile(data, stale=age > self.max_age_days * _SECONDS_PER_DAY)

    def write(self, layer: TileLayer, z: int, x: int, y: int, data: bytes) -> None:
        """Guarda una tesela recién descargada (sustituye a la que hubiera).

        Raises:
            ValueError: Si los datos no son una imagen (p. ej. una página de error).
            TileStorageError: Si no se puede escribir en el disco.
        """
        if not looks_like_image(data):
            raise ValueError("Lo descargado no es una imagen: no se guarda en la caché")
        path = self.path_for(layer, z, x, y)
        # Nombre temporal único por proceso e hilo: dos descargas de la misma tesela a la
        # vez no se pisan el archivo a medias
        temporary = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(data)
            _replace(temporary, path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise TileStorageError(f"No se pudo guardar la tesela en {path}: {error}") from error

    # -------------------------------------------------------------------------
    # Tamaño y limpieza (recorren la carpeta: en segundo plano)
    # -------------------------------------------------------------------------

    def size_bytes(self) -> int:
        """Tamaño total de la caché, en bytes."""
        return sum(size for _path, size, _mtime in self._files())

    def prune(self, *, cancel_event: threading.Event | None = None) -> PruneResult:
        """Si la caché pasa del tope, borra las teselas descargadas hace más tiempo hasta
        dejarla algo por debajo. Los temporales abandonados se borran siempre.

        Args:
            cancel_event: Si se activa, la limpieza se interrumpe (lo borrado, borrado queda).
        """
        files = []
        for entry in self._files(include_temporary=True):
            if cancel_event is not None and cancel_event.is_set():
                return PruneResult(0, 0, sum(size for _p, size, _m in files), cancelled=True)
            path = entry[0]
            if path.suffix == ".tmp":
                # Resto de una escritura interrumpida (de hace más de una hora: no es de ahora)
                if time.time() - entry[2] > 3600:
                    _remove(path)
                continue
            files.append(entry)

        total = sum(size for _path, size, _mtime in files)
        if total <= self.max_bytes:
            return PruneResult(0, 0, total)

        target = int(self.max_bytes * _PRUNE_TARGET)
        files.sort(key=lambda entry: entry[2])  # las más antiguas, primero
        removed = freed = 0
        for path, size, _mtime in files:
            if total - freed <= target:
                break
            if cancel_event is not None and cancel_event.is_set():
                return PruneResult(removed, freed, total - freed, cancelled=True)
            if _remove(path):
                removed += 1
                freed += size
        return PruneResult(removed, freed, total - freed)

    def clear(self, layer_key: str | None = None) -> None:
        """Vacía la caché entera, o solo la de una capa.

        Raises:
            ValueError: Si la clave de la capa no es válida.
            TileStorageError: Si no se puede borrar.
        """
        if layer_key is not None and not is_valid_key(layer_key):
            raise ValueError(f"Clave de capa no válida: {layer_key!r}")
        target = self.root if layer_key is None else self.root / layer_key
        if not target.is_dir():
            return
        try:
            # De la raíz solo se borran las carpetas de capas: si alguien apuntara la caché
            # a una carpeta con otras cosas, no se las lleva
            folders = [target] if layer_key is not None else [
                child for child in target.iterdir() if child.is_dir() and is_valid_key(child.name)
            ]
            for folder in folders:
                shutil.rmtree(folder)
        except OSError as error:
            raise TileStorageError(f"No se pudo vaciar la caché de mapas: {error}") from error

    def _files(self, *, include_temporary: bool = False) -> list[tuple[Path, int, float]]:
        """(ruta, tamaño, fecha) de cada archivo de las carpetas de capas."""
        found: list[tuple[Path, int, float]] = []
        if not self.root.is_dir():
            return found
        for layer_folder in self.root.iterdir():
            if not layer_folder.is_dir() or not is_valid_key(layer_folder.name):
                continue
            for folder, _folders, names in os.walk(layer_folder):
                for name in names:
                    if name.endswith(".tmp") and not include_temporary:
                        continue
                    path = Path(folder, name)
                    try:
                        status = path.stat()
                    except OSError:
                        continue  # borrado mientras se recorría
                    found.append((path, status.st_size, status.st_mtime))
        return found


def _replace(temporary: Path, final: Path) -> None:
    """Sustituye el archivo final por el temporal. En Windows, si un antivirus tiene
    abierto el destino en ese instante, el cambio falla: se reintenta unos milisegundos
    (igual que la caché de miniaturas)."""
    for attempt in range(5):
        try:
            os.replace(temporary, final)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)


def _remove(path: Path) -> bool:
    """Borra un archivo; False si no se pudo (se deja para otra limpieza)."""
    try:
        path.unlink()
    except OSError:
        return False
    return True


if __name__ == "__main__":
    # Autoprueba en una carpeta temporal (sin Qt y sin red).
    # Ejecutar desde la raíz del proyecto:  python -m core.maps.tile_store
    import tempfile

    from core.maps.tile_layers import layer_for

    PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 992  # 1 000 bytes que empiezan como un PNG
    JPEG = b"\xff\xd8\xff\xe0" + b"y" * 496
    osm, mtn = layer_for("osm"), layer_for("ign_mtn")

    def set_age(path: Path, days: float) -> None:
        moment = time.time() - days * _SECONDS_PER_DAY
        os.utime(path, (moment, moment))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "tiles"
        store = TileStore(root)

        # 1. Sin escribir nada no se crea nada, y todo responde
        assert store.read(osm, 3, 1, 2) is None
        assert store.size_bytes() == 0 and store.prune() == PruneResult(0, 0, 0)
        store.clear()
        assert not root.exists()

        # 2. Rutas: carpeta de la capa, zoom, columna y fila con su extensión
        assert store.path_for(osm, 12, 2048, 1509) == root / "osm" / "12" / "2048" / "1509.png"
        assert store.path_for(mtn, 3, 1, 2).name == "2.jpg"
        for layer, z, x, y in ((osm, 3, 8, 0), (osm, 25, 0, 0), (mtn, 18, 0, 0), (osm, 3, "1", 0)):
            try:
                store.path_for(layer, z, x, y)
            except ValueError:
                pass
            else:
                raise AssertionError(f"debería rechazarse: {layer.key} {z} {x} {y}")
        # Una capa con una clave que se saldría de la carpeta
        try:
            store.path_for(TileLayer("../fuera", "x", "https://x/{z}/{x}/{y}", "x"), 0, 0, 0)
        except ValueError:
            pass
        else:
            raise AssertionError("una clave con '..' debe rechazarse")

        # 3. Escribir y leer; no queda ningún temporal
        store.write(osm, 3, 1, 2, PNG)
        store.write(mtn, 3, 1, 2, JPEG)
        assert store.read(osm, 3, 1, 2) == CachedTile(PNG, stale=False)
        assert store.read(mtn, 3, 1, 2).data == JPEG
        assert store.size_bytes() == len(PNG) + len(JPEG)
        assert not list(root.rglob("*.tmp"))
        # Sobrescribir cambia el contenido
        store.write(osm, 3, 1, 2, PNG + b"z")
        assert store.read(osm, 3, 1, 2).data == PNG + b"z"
        store.write(osm, 3, 1, 2, PNG)

        # 4. Solo imágenes: una página de error no entra (y no deja restos)
        assert looks_like_image(PNG) and looks_like_image(JPEG)
        assert looks_like_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        for bad in (b"", b"<html>Too many requests</html>", b"RIFF\x00\x00\x00\x00WAVE"):
            assert not looks_like_image(bad), bad
            try:
                store.write(osm, 3, 0, 0, bad)
            except ValueError:
                pass
            else:
                raise AssertionError("lo que no es una imagen no se guarda")
        assert store.read(osm, 3, 0, 0) is None and not list(root.rglob("*.tmp"))

        # 5. Caducidad: pasados los días se sigue leyendo, pero avisa
        path = store.path_for(osm, 3, 1, 2)
        set_age(path, DEFAULT_MAX_AGE_DAYS - 1)
        assert store.read(osm, 3, 1, 2).stale is False
        set_age(path, DEFAULT_MAX_AGE_DAYS + 1)
        assert store.read(osm, 3, 1, 2) == CachedTile(PNG, stale=True)
        store.write(osm, 3, 1, 2, PNG)  # descargada otra vez: deja de estar caducada
        assert store.read(osm, 3, 1, 2).stale is False

        # 6. Tope de tamaño: se borran las más antiguas hasta quedar por debajo
        small = TileStore(root, max_bytes=5_000)
        store.clear()
        for column in range(8):  # 8 teselas de 1 000 bytes; la columna 0, la más antigua
            small.write(osm, 4, column, 0, PNG)
            set_age(small.path_for(osm, 4, column, 0), 8 - column)
        assert small.size_bytes() == 8_000
        result = small.prune()
        # Objetivo: el 90 % de 5 000 = 4 500 -> quedan 4 (4 000 bytes), las más recientes
        assert result == PruneResult(files_removed=4, bytes_removed=4_000, bytes_left=4_000), result
        assert [small.read(osm, 4, c, 0) is not None for c in range(8)] == [False] * 4 + [True] * 4
        assert small.prune() == PruneResult(0, 0, 4_000)  # ya está por debajo: no toca nada

        # 7. La limpieza se puede interrumpir, y se lleva los temporales abandonados
        cancel = threading.Event()
        cancel.set()
        assert small.prune(cancel_event=cancel).cancelled
        assert small.size_bytes() == 4_000
        old_temp = root / "osm" / "4" / "7" / "0.png.1-1.tmp"
        new_temp = root / "osm" / "4" / "7" / "0.png.2-2.tmp"
        old_temp.write_bytes(b"resto")
        new_temp.write_bytes(b"resto")
        set_age(old_temp, 1)
        assert small.size_bytes() == 4_000  # los temporales no cuentan
        small.prune()
        assert not old_temp.exists() and new_temp.exists()  # el reciente puede ser de ahora

        # 8. Vaciar: una capa o todo; lo que no es una carpeta de capa no se toca
        store.write(mtn, 3, 1, 2, JPEG)
        (root / "nota.txt").write_text("no es de la caché", encoding="utf-8")
        (root / "Otra Carpeta").mkdir()
        store.clear("osm")
        assert not (root / "osm").exists() and store.read(mtn, 3, 1, 2) is not None
        store.clear()
        assert store.size_bytes() == 0
        assert (root / "nota.txt").exists() and (root / "Otra Carpeta").exists()
        try:
            store.clear("../fuera")
        except ValueError:
            pass
        else:
            raise AssertionError("una clave con '..' debe rechazarse")

        # 9. Si no se puede escribir, error propio y sin restos
        (root / "osm").write_bytes(b"un archivo en el sitio de la carpeta")
        try:
            store.write(osm, 3, 1, 2, PNG)
        except TileStorageError as error:
            print(f"Escritura imposible: {type(error).__name__}")
        else:
            raise AssertionError("debería lanzar TileStorageError")
        assert not list(root.rglob("*.tmp"))

    print("Autoprueba finalizada correctamente.")
