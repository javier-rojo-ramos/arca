"""Creación de la estructura de un catálogo nuevo (carpetas + base de datos SQLite).

Este módulo no depende de Qt: es Python puro, así que se puede probar desde la
consola sin abrir la aplicación. Se ejecuta de forma síncrona porque crear unas
pocas carpetas y una base de datos vacía tarda milisegundos.

Estructura que se genera dentro de la carpeta del catálogo:

    <carpeta_del_catalogo>/
    ├── catalogo.db          # Base de datos SQLite (modo WAL)
    ├── cache/
    │   ├── photo/           # una por cada MediaType "cacheable"
    │   ├── video/
    │   ├── audio/
    │   ├── ebook/
    ├── media_assets/
    │   ├── backdrops/
    │   ├── covers/
    │   ├── posters/
    └── export/

Si queremos que se cree alguna carpeta más en 'cache', tenemos que añadirla a
media_types.py -> CACHEABLE_MEDIA_TYPES (y en la class MediaType)

Los archivos 'catalogo.db-wal' y 'catalogo.db-shm' los crea SQLite solos mientras
hay conexiones abiertas; al cerrar la última conexión, desaparecen.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.catalog_builder
"""

__version__ = "1.02"
# ruff: noqa: RUF022
__all__ = ["CatalogBuilder", "CatalogAlreadyExistsError", "CatalogError"]

# Librerías estándar
import sqlite3
from contextlib import closing
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.catalog_schema import (
    BUSY_TIMEOUT_SECONDS,
    apply_migrations,
    configure_connection,
)
from core.catalog.media_types import CACHEABLE_MEDIA_TYPES


class CatalogError(Exception):
    """Error genérico al crear un catálogo.

    Envuelve los errores de disco (OSError) y de SQLite (sqlite3.Error) para que
    quien llame (el controlador) solo tenga que capturar esta excepción y mostrar
    'str(error)' al usuario.
    """


class CatalogAlreadyExistsError(CatalogError):
    """La carpeta elegida ya contiene un catálogo (existe 'catalogo.db')."""


class CatalogBuilder:
    """Crea la estructura de carpetas y la base de datos de un catálogo nuevo."""

    # Nombre del archivo de base de datos dentro de la carpeta del catálogo
    DB_FILENAME: str = "catalogo.db"

    # Subcarpetas de 'media_assets' (imágenes descargadas/extraídas por elemento)
    ASSETS_SUBDIRECTORIES: tuple[str, ...] = ("backdrops", "covers", "posters")

    # Carpeta de exportaciones
    EXPORT_SUBDIRECTORY: str = "export"

    def __init__(self, catalog_directory: str | Path) -> None:
        """Prepara el constructor (todavía no toca el disco).

        Args:
            catalog_directory: Carpeta donde vivirá el catálogo. Si no existe,
                se crea; si existe, se usa tal cual (no se borra nada).
        """
        self.catalog_path: Path = Path(catalog_directory).resolve()
        self.db_path: Path = self.catalog_path / self.DB_FILENAME

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def already_exists(self) -> bool:
        """Indica si la carpeta ya contiene un catálogo (existe 'catalogo.db')."""
        return self.db_path.exists()

    def build(self) -> Path:
        """Crea las carpetas y la base de datos SQLite con el esquema inicial.

        Nunca sobrescribe un catálogo existente.

        Returns:
            Ruta absoluta al archivo .db generado.

        Raises:
            CatalogAlreadyExistsError: Si ya existe 'catalogo.db' en la carpeta.
            CatalogError: Si falla la creación de carpetas o de la base de datos.
        """
        logger.info(f"Creando catálogo en: {self.catalog_path}")

        # Protección: jamás pisar un catálogo existente
        if self.already_exists():
            raise CatalogAlreadyExistsError(
                f"Ya existe un catálogo en esta carpeta:\n{self.catalog_path}"
            )

        # 1. Carpetas (si falla, aún no hay base de datos que limpiar)
        try:
            self._create_folder_structure()
        except OSError as exc:
            logger.exception("No se pudo crear la estructura de carpetas.")
            raise CatalogError(f"No se pudieron crear las carpetas: {exc}") from exc

        # 2. Base de datos
        try:
            self._initialize_database()
        except (sqlite3.Error, OSError) as exc:
            logger.exception("No se pudo inicializar la base de datos.")
            # Se borra el .db a medias para que se pueda reintentar limpiamente.
            # Es seguro: arriba comprobamos que 'catalogo.db' NO existía antes.
            self._remove_partial_database()
            raise CatalogError(f"No se pudo crear la base de datos: {exc}") from exc

        logger.info(f"Catálogo creado correctamente: {self.db_path}")
        return self.db_path

    # -------------------------------------------------------------------------
    # Funciones internas
    # -------------------------------------------------------------------------

    def _required_subdirectories(self) -> list[Path]:
        """Devuelve las subcarpetas que debe tener el catálogo (rutas relativas).

        La caché se deriva de CACHEABLE_MEDIA_TYPES: al añadir un tipo nuevo en
        'media_types.py' (p. ej. "comic"), su carpeta 'cache/comic' aparece sola.
        """
        carpetas: list[Path] = [
            Path("cache") / tipo.value for tipo in CACHEABLE_MEDIA_TYPES
        ]
        carpetas += [
            Path("media_assets") / nombre for nombre in self.ASSETS_SUBDIRECTORIES
        ]
        carpetas.append(Path(self.EXPORT_SUBDIRECTORY))
        return carpetas

    def _create_folder_structure(self) -> None:
        """Crea la carpeta raíz y las subcarpetas requeridas si no existen."""
        self.catalog_path.mkdir(parents=True, exist_ok=True)

        for relativa in self._required_subdirectories():
            destino = self.catalog_path / relativa
            destino.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Carpeta verificada/creada: {destino}")

    def _initialize_database(self) -> None:
        """Crea el archivo SQLite, activa el modo WAL y aplica las migraciones."""
        # 'closing' garantiza que la conexión se cierra al salir del bloque.
        # (Ojo: 'with sqlite3.connect(...)' a secas NO cierra la conexión, solo
        # confirma/revierte la transacción; en Windows dejaría el archivo bloqueado.)
        with closing(
            sqlite3.connect(self.db_path, timeout=BUSY_TIMEOUT_SECONDS)
        ) as conn:
            # El modo WAL se guarda dentro del archivo: basta con activarlo aquí.
            # PRAGMA journal_mode devuelve el modo que realmente quedó activo.
            modo = conn.execute("PRAGMA journal_mode = WAL;").fetchone()[0]
            if str(modo).lower() != "wal":
                # Pasa, por ejemplo, en carpetas de red: WAL no funciona bien allí
                logger.warning(
                    f"SQLite no pudo activar el modo WAL (modo actual: {modo}). "
                    "Evita crear catálogos en unidades de red o carpetas sincronizadas."
                )

            # PRAGMAs que hay que repetir en cada conexión (foreign_keys, etc.)
            configure_connection(conn)

            # Tablas, índices y triggers: en un catálogo nuevo (user_version = 0) se
            # aplican todas las migraciones. Cada una es atómica y deja anotada la
            # versión del esquema en 'PRAGMA user_version' (no hace falta commit); la
            # primera marca además el archivo con 'APPLICATION_ID'.
            apply_migrations(conn)

        logger.info(f"Base de datos creada en: {self.db_path}")

    def _remove_partial_database(self) -> None:
        """Elimina el .db (y sus archivos auxiliares WAL/SHM) tras un fallo."""
        for sufijo in ("", "-wal", "-shm"):
            archivo = self.db_path.with_name(self.db_path.name + sufijo)
            try:
                archivo.unlink(missing_ok=True)
            except OSError:
                # Si no se puede borrar, solo avisamos: no ocultamos el error original
                logger.warning(f"No se pudo eliminar el archivo parcial: {archivo}")


if __name__ == "__main__":
    # Autoprueba: crea un catálogo en una carpeta temporal y comprueba el resultado.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.catalog_builder
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp) / "MiCatálogo"
        ruta_db = CatalogBuilder(carpeta).build()

        # Comprobamos que la base de datos tiene lo esperado
        with closing(sqlite3.connect(ruta_db)) as con:
            tablas = [
                f[0]
                for f in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            print("Tablas:", tablas)
            print("user_version:", con.execute("PRAGMA user_version").fetchone()[0])
            print("application_id:", hex(con.execute("PRAGMA application_id").fetchone()[0]))
            print("journal_mode:", con.execute("PRAGMA journal_mode").fetchone()[0])

        print("Subcarpetas:")
        for p in sorted(carpeta.rglob("*")):
            print("  ", p.relative_to(carpeta).as_posix())

        # Un segundo intento sobre la misma carpeta debe ser rechazado
        try:
            CatalogBuilder(carpeta).build()
        except CatalogAlreadyExistsError as err:
            print("Segundo intento rechazado correctamente:", str(err).splitlines()[0])
