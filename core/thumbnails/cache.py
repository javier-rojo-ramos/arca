"""Caché de miniaturas en disco: dónde se guardan, cómo se escriben y cómo se buscan.

Este módulo NO depende de Qt ni de la base de datos. Es el ÚNICO sitio que conoce el
formato de los archivos de la caché (JPEG) y su distribución en carpetas, así que si
algún día se cambia (p. ej. a WebP), solo se toca aquí.

Distribución, dentro de la carpeta 'cache/' del catálogo:

    cache/<tipo de medio>/<lado largo>/<id // 1000>/<id>.jpg

    cache/photo/160/12/12345.jpg      miniatura de 160 px del elemento 12345
    cache/photo/480/12/12345.jpg      la de 480 px
    cache/photo/1200/12/12345.jpg
    cache/photo/2560/12/12345.jpg

La ruta NO se guarda en la base de datos: se calcula a partir del id (ver el esquema,
BLOQUE D). Las carpetas intermedias ('id // 1000') evitan tener decenas de miles de
archivos en una sola carpeta, algo que ralentiza el explorador de archivos y algunos
sistemas de archivos.

Las escrituras son ATÓMICAS: la miniatura se escribe en un archivo temporal y después
se renombra, de modo que quien la lea (la cuadrícula, desde otro hilo) nunca ve un
JPEG a medias.

Prueba rápida (desde la raíz del proyecto):
    python -m core.thumbnails.cache
"""

__version__ = "1.1.0"
# ruff: noqa: RUF022
__all__ = [
    "CACHE_DIRECTORY_NAME",
    "StoredThumbnail",
    "ThumbnailCache",
    "ThumbnailStorageError",
]

# Librerías estándar
import os
import sys
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Librerías de terceros
from PIL import Image

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.thumbnails.sizes import ALL_SIZES, ThumbnailSize

# Nombre de la carpeta de la caché dentro del catálogo (la crea 'CatalogBuilder')
CACHE_DIRECTORY_NAME = "cache"


class ThumbnailStorageError(OSError):
    """No se pudo escribir en la caché de miniaturas (disco lleno, sin permisos, unidad desconectada...).

    Es un fallo GENERAL de la caché, no del archivo que se estaba procesando: quien genere
    miniaturas en lote debe detenerse en lugar de marcar miles de archivos como fallidos.
    Hereda de 'OSError' para que quien ya capture 'OSError' siga funcionando.
    """


@dataclass(frozen=True, slots=True)
class StoredThumbnail:
    """Una miniatura ya escrita en disco.

    Attributes:
        size: Tamaño de la escalera al que corresponde.
        path: Ruta del archivo.
        width: Ancho real en píxeles.
        height: Alto real en píxeles.
        file_bytes: Tamaño del archivo, en bytes.
    """

    size: ThumbnailSize
    path: Path
    width: int
    height: int
    file_bytes: int


class ThumbnailCache:
    """Caché de miniaturas de UN catálogo.

    Es barata de crear (no toca el disco al construirla) y segura para usar desde
    varios hilos a la vez: cada miniatura se escribe en un temporal propio de ese hilo.
    """

    # Formato de los archivos de la caché. JPEG: lo decodifica Qt sin plugins y a
    # gran velocidad, y es el que menos problemas da al empaquetar la aplicación.
    FILE_EXTENSION = "jpg"

    # Elementos por carpeta
    BUCKET_SIZE = 1000

    def __init__(self, catalog_directory: str | Path) -> None:
        """Prepara la caché de un catálogo.

        Args:
            catalog_directory: Carpeta del catálogo (la que contiene 'catalogo.db').
        """
        self.root: Path = Path(catalog_directory) / CACHE_DIRECTORY_NAME

    # -------------------------------------------------------------------------
    # Rutas y consulta
    # -------------------------------------------------------------------------

    def path_for(
        self, media_type: MediaType | str, media_id: int, size: ThumbnailSize
    ) -> Path:
        """Devuelve la ruta (exista o no) de la miniatura de un elemento y tamaño."""
        return (
            self.root
            / MediaType(media_type).value
            / str(size.max_side)
            / str(media_id // self.BUCKET_SIZE)
            / f"{media_id}.{self.FILE_EXTENSION}"
        )

    def existing(
        self, media_type: MediaType | str, media_id: int
    ) -> dict[ThumbnailSize, Path]:
        """Devuelve las miniaturas que existen de un elemento (de menor a mayor)."""
        found: dict[ThumbnailSize, Path] = {}
        for size in ALL_SIZES:
            path = self.path_for(media_type, media_id, size)
            if path.is_file():
                found[size] = path
        return found

    def resolve(
        self, media_type: MediaType | str, media_id: int, wanted: ThumbnailSize
    ) -> Path | None:
        """Busca la mejor miniatura disponible para un tamaño que se quiere mostrar.

        Una miniatura bien generada tiene siempre todos los tamaños, pero puede que el
        elemento aún no esté procesado (o que un fallo la dejara a medias, o que se
        pida un tamaño que ya no existe). Se devuelve el MAYOR tamaño que exista sin
        pasar de 'wanted'; si no hay ninguno tan pequeño, el más pequeño de los mayores
        (Qt lo reducirá al pintarlo).

        Returns:
            La ruta, o None si el elemento no tiene ninguna miniatura.
        """
        available = self.existing(media_type, media_id)
        if not available:
            return None
        not_larger = [size for size in available if size.max_side <= wanted.max_side]
        if not_larger:
            return available[not_larger[-1]]  # 'available' va de menor a mayor
        return next(iter(available.values()))

    # -------------------------------------------------------------------------
    # Escritura y borrado
    # -------------------------------------------------------------------------

    def store(
        self,
        media_type: MediaType | str,
        media_id: int,
        size: ThumbnailSize,
        image: Image.Image,
    ) -> StoredThumbnail:
        """Guarda una miniatura (JPEG) de forma atómica, sustituyendo la anterior.

        Args:
            media_type: Tipo de medio del elemento.
            media_id: Identificador del elemento ('media_items.id').
            size: Tamaño de la escalera al que corresponde la imagen.
            image: Imagen ya reducida y en RGB.

        Raises:
            ThumbnailStorageError: Si no se puede escribir (disco lleno, sin permisos...).
            OSError: Si Pillow no puede codificar la imagen (error de programación, p. ej.
                un modo de color no guardable como JPEG).
        """
        final_path = self.path_for(media_type, media_id, size)

        # El nombre del temporal incluye el proceso y el hilo: dos hilos nunca pisan
        # el temporal del otro, aunque regeneren el mismo elemento a la vez.
        temp_path = final_path.with_name(
            f"{final_path.name}.{os.getpid()}-{threading.get_ident()}.tmp"
        )
        try:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            # Sin EXIF ni perfil: la imagen ya está derecha y en sRGB (que es lo que
            # asume cualquier lector para un JPEG sin perfil)
            image.save(
                temp_path,
                format="JPEG",
                quality=size.quality,
                optimize=True,
            )
            self._replace(temp_path, final_path)
        except OSError as exc:
            self._remove_quietly(temp_path)
            # Los errores del disco traen código de error del sistema; los de codificación
            # de Pillow ("cannot write mode RGBA as JPEG") no: esos son errores de programación
            if exc.errno is None:
                raise
            raise ThumbnailStorageError(
                exc.errno, f"No se pudo escribir en la caché de miniaturas: {exc.strerror or exc}"
            ) from exc
        except BaseException:
            self._remove_quietly(temp_path)
            raise

        return StoredThumbnail(
            size=size,
            path=final_path,
            width=image.width,
            height=image.height,
            file_bytes=final_path.stat().st_size,
        )

    def delete(
        self,
        media_type: MediaType | str,
        media_id: int,
        sizes: Iterable[ThumbnailSize] = ALL_SIZES,
    ) -> list[ThumbnailSize]:
        """Borra las miniaturas de un elemento (por defecto, todas).

        Un archivo que no se pueda borrar (p. ej. abierto por otro programa en
        Windows) se ignora: no es grave, se sobrescribirá en la próxima generación.

        Returns:
            Los tamaños cuyo archivo existía y se ha borrado.
        """
        deleted: list[ThumbnailSize] = []
        for size in sizes:
            path = self.path_for(media_type, media_id, size)
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                continue
            deleted.append(size)
        return deleted

    # -------------------------------------------------------------------------
    # Pasos internos
    # -------------------------------------------------------------------------

    @staticmethod
    def _remove_quietly(path: Path) -> None:
        """Borra un archivo temporal sin lanzar errores (no debe ocultar el error original)."""
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _replace(temp_path: Path, final_path: Path) -> None:
        """Renombra el temporal sobre el definitivo (atómico en todos los sistemas)."""
        if sys.platform != "win32":
            os.replace(temp_path, final_path)
            return

        # Windows: si un antivirus o el propio visor tiene abierto el archivo de destino
        # en ese instante, el renombrado falla. Se reintenta unos milisegundos.
        for attempt in range(5):
            try:
                os.replace(temp_path, final_path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)


if __name__ == "__main__":
    # Autoprueba en una carpeta temporal.
    # Ejecutar desde la raíz del proyecto:  python -m core.thumbnails.cache
    import tempfile
    from concurrent.futures import ThreadPoolExecutor

    THUMB, MEDIUM, PREVIEW, FULL = ALL_SIZES

    with tempfile.TemporaryDirectory() as tmp:
        cache = ThumbnailCache(tmp)

        # 1. Rutas: llevan el tipo, el lado largo y la carpeta 'id // 1000'
        path = cache.path_for(MediaType.PHOTO, 12345, MEDIUM)
        assert path == Path(tmp) / "cache" / "photo" / "480" / "12" / "12345.jpg"
        assert cache.path_for("photo", 7, THUMB).parts[-3:] == ("160", "0", "7.jpg")
        assert cache.path_for("photo", 999, THUMB).parent.name == "0"
        assert cache.path_for("photo", 1000, THUMB).parent.name == "1"
        assert cache.path_for("video", 5, FULL).parts[-4:-2] == ("video", "2560")
        assert cache.resolve("photo", 1, MEDIUM) is None and cache.existing("photo", 1) == {}

        # 2. Escritura: JPEG válido, con la medida indicada, sin dejar temporales
        image = Image.new("RGB", (480, 320), (200, 30, 30))
        stored = cache.store("photo", 1, MEDIUM, image)
        assert stored.path.is_file() and stored.file_bytes > 0
        assert (stored.width, stored.height) == (480, 320)
        with Image.open(stored.path) as reopened:
            assert reopened.format == "JPEG" and reopened.size == (480, 320)
            assert "exif" not in reopened.info  # no se copia ningún metadato
        assert not list(Path(tmp).rglob("*.tmp"))
        print(f"Miniatura escrita: {stored.path.relative_to(tmp).as_posix()} ({stored.file_bytes} bytes)")

        # 3. Sobrescribir cambia el contenido (regenerar a demanda)
        cache.store("photo", 1, MEDIUM, Image.new("RGB", (480, 320), (30, 30, 200)))
        with Image.open(stored.path) as reopened:
            red, _green, blue = reopened.convert("RGB").getpixel((10, 10))
            assert blue > red

        # 4. 'resolve': el mayor tamaño que exista sin pasar del pedido
        cache.store("photo", 1, THUMB, Image.new("RGB", (160, 107)))
        cache.store("photo", 1, FULL, Image.new("RGB", (2560, 1707)))
        assert list(cache.existing("photo", 1)) == [THUMB, MEDIUM, FULL]
        assert cache.resolve("photo", 1, THUMB) == cache.path_for("photo", 1, THUMB)
        assert cache.resolve("photo", 1, MEDIUM) == cache.path_for("photo", 1, MEDIUM)
        assert cache.resolve("photo", 1, PREVIEW) == cache.path_for("photo", 1, MEDIUM)  # no hay 1200
        assert cache.resolve("photo", 1, FULL) == cache.path_for("photo", 1, FULL)
        cache.store("photo", 2, MEDIUM, Image.new("RGB", (300, 200)))  # solo hay uno, y es mayor
        assert cache.resolve("photo", 2, THUMB) == cache.path_for("photo", 2, MEDIUM)
        print("resolve: mayor disponible sin pasar del pedido, y si no hay, el menor de los mayores")

        # 5. Borrado selectivo y total
        assert cache.delete("photo", 1, [FULL, PREVIEW]) == [FULL]  # el 1200 no existía
        assert list(cache.existing("photo", 1)) == [THUMB, MEDIUM]
        assert cache.delete("photo", 1) == [THUMB, MEDIUM]
        assert cache.existing("photo", 1) == {} and cache.delete("photo", 1) == []

        # 6. Escritura desde varios hilos sobre el MISMO elemento: nunca queda un JPEG roto
        def hammer(worker: int) -> None:
            for _ in range(20):
                color = (worker * 20 % 256, 100, 100)
                cache.store("photo", 99, THUMB, Image.new("RGB", (160, 100), color))
                with Image.open(cache.path_for("photo", 99, THUMB)) as reread:
                    reread.load()  # si el archivo estuviera a medias, fallaría aquí

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(hammer, range(6)))
        assert not list(Path(tmp).rglob("*.tmp"))
        print("Escrituras simultáneas sobre el mismo archivo: sin archivos rotos ni temporales")

        # 7. Si la escritura falla no queda ningún temporal. Dos tipos de fallo:
        #    a) un modo no guardable en JPEG es un error de programación (OSError a secas)
        try:
            cache.store("photo", 5, THUMB, Image.new("RGBA", (10, 10)))
        except OSError as error:
            assert not isinstance(error, ThumbnailStorageError)
        else:
            raise AssertionError("Un RGBA no se puede guardar como JPEG")
        assert not list(Path(tmp).rglob("*.tmp")) and not cache.path_for("photo", 5, THUMB).exists()

        #    b) un fallo del disco (aquí: un ARCHIVO donde debería haber una carpeta) es un
        #       fallo general de la caché: 'ThumbnailStorageError', que sigue siendo un OSError
        blocker = cache.root / "photo" / "160" / "7"
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_bytes(b"estorbo")
        try:
            cache.store("photo", 7123, THUMB, Image.new("RGB", (10, 10)))
        except ThumbnailStorageError as error:
            assert isinstance(error, OSError) and "caché" in str(error)
            print("Fallo del disco:", error)
        else:
            raise AssertionError("Debería fallar el almacenamiento")
        blocker.unlink()
        assert not list(Path(tmp).rglob("*.tmp"))

        # Tipo de medio no válido
        try:
            cache.path_for("comic", 1, THUMB)
        except ValueError:
            pass
        else:
            raise AssertionError("Un tipo de medio inexistente debería rechazarse")

    print("Autoprueba finalizada correctamente.")
