"""Apertura de un catálogo existente: comprobaciones y migración del esquema.

Este módulo NO depende de Qt: es Python puro, así que se puede probar desde la
consola. Es el paso que hay que dar ANTES de crear el 'CatalogDatabaseManager':

    db_path = open_catalog(catalog_directory)   # síncrono: tarda milisegundos
    manager = CatalogDatabaseManager(db_path)   # ya se puede consultar en hilos

Por qué es un paso aparte y síncrono: las migraciones del esquema deben aplicarse
UNA sola vez y sin otras conexiones escribiendo. El gestor asíncrono abre varias
conexiones en hilos distintos, así que migrar con él en marcha no sería seguro.

Qué comprueba, en este orden:
    1. Que la carpeta contiene el archivo 'catalogo.db'.
    2. Que ese archivo es realmente una base de datos SQLite.
    3. Que es un catálogo nuestro y no un archivo ajeno que casualmente se llama
       igual: una base de datos con tablas pero sin versión de esquema se rechaza,
       en lugar de añadirle nuestras tablas. Un catálogo con versión tiene que llevar
       la marca 'APPLICATION_ID'; sin ella, es de la fase de pruebas anterior a
       consolidar el esquema (05/11/2026, aún como EMC Manager) y se rechaza con un
       mensaje propio: no se puede migrar.
    4. Que no es de una versión más NUEVA de la aplicación (se rechaza sin tocarlo).
    5. Si es de una versión más antigua, aplica las migraciones pendientes.

Todos los fallos se lanzan como 'CatalogOpenError' (un 'CatalogError'), con un
mensaje en español pensado para mostrarlo tal cual al usuario.

1.1.0 Rechaza los catálogos sin la marca 'APPLICATION_ID' (los de antes de consolidar el
      esquema en la v1).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.catalog_opener
"""

__version__ = "1.1.0"
__all__ = ["CatalogOpenError", "open_catalog"]

# Librerías estándar
import sqlite3
from contextlib import closing
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.catalog_builder import CatalogBuilder, CatalogError
from core.catalog.catalog_schema import (
    APPLICATION_ID,
    BUSY_TIMEOUT_SECONDS,
    SchemaVersionError,
    apply_migrations,
    configure_connection,
)


class CatalogOpenError(CatalogError):
    """No se pudo abrir el catálogo (mensaje listo para mostrar al usuario)."""


def open_catalog(catalog_directory: str | Path) -> Path:
    """Comprueba un catálogo existente, lo migra si hace falta y devuelve su .db.

    Args:
        catalog_directory: Carpeta del catálogo (la que contiene 'catalogo.db').

    Returns:
        Ruta absoluta al archivo 'catalogo.db', lista para 'CatalogDatabaseManager'.

    Raises:
        CatalogOpenError: Si no existe, no es un catálogo válido, es de una versión
            más nueva de la aplicación o falla alguna migración.
    """
    catalog_path = Path(catalog_directory).resolve()
    db_path = catalog_path / CatalogBuilder.DB_FILENAME

    # 1. ¿Existe el archivo? (si no, SQLite crearía uno vacío al conectar)
    if not db_path.is_file():
        raise CatalogOpenError(f"No hay ningún catálogo en esta carpeta:\n{catalog_path}")

    try:
        with closing(sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_SECONDS)) as conn:
            configure_connection(conn)

            # 2 y 3. ¿Es SQLite y es de los nuestros?
            _check_is_our_catalog(conn, catalog_path)

            # 4 y 5. Versión del esquema: se rechaza la más nueva y se migra la antigua
            apply_migrations(conn)

    except SchemaVersionError as exc:
        # El texto de la excepción ya está redactado para el usuario
        raise CatalogOpenError(f"{exc}\n\nCatálogo: {catalog_path}") from exc
    except sqlite3.Error as exc:
        # Incluye "file is not a database" (archivo corrupto o que no es SQLite)
        logger.opt(exception=True).error(f"No se pudo abrir el catálogo: {db_path}")
        raise CatalogOpenError(
            f"No se pudo abrir la base de datos del catálogo:\n{catalog_path}\n\n({exc})"
        ) from exc

    logger.info(f"Catálogo listo: {db_path}")
    return db_path


def _check_is_our_catalog(conn: sqlite3.Connection, catalog_path: Path) -> None:
    """Rechaza una base de datos que no es un catálogo de esta aplicación.

    Un catálogo nuestro siempre tiene 'user_version' >= 1 y la marca 'APPLICATION_ID'.
    Si 'user_version' vale 0, solo es aceptable que la base de datos esté completamente
    vacía; si ya tiene tablas, es un archivo ajeno y migrarlo le añadiría nuestras tablas.
    """
    user_version: int = conn.execute("PRAGMA user_version;").fetchone()[0]
    if user_version != 0:
        application_id: int = conn.execute("PRAGMA application_id;").fetchone()[0]
        if application_id == APPLICATION_ID:
            return
        if application_id == 0:
            # Con versión pero sin marca: un catálogo de la fase de pruebas, creado antes
            # de consolidar las migraciones. Su esquema no se puede migrar al actual.
            raise CatalogOpenError(
                "Este catálogo es de una versión de pruebas anterior de la aplicación "
                "y ya no se puede abrir:\n"
                f"{catalog_path}\n\n"
                "Crea un catálogo nuevo y vuelve a añadir las carpetas: la valoración, "
                "la marca, el color y las palabras clave de las fotos se recuperan de "
                "sus archivos."
            )
        raise CatalogOpenError(
            "El archivo 'catalogo.db' de esta carpeta no parece un catálogo de "
            f"esta aplicación:\n{catalog_path}"
        )

    # La consulta también falla con sqlite3.DatabaseError si el archivo no es SQLite
    has_tables = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' LIMIT 1"
    ).fetchone()
    if has_tables is not None:
        raise CatalogOpenError(
            "El archivo 'catalogo.db' de esta carpeta no parece un catálogo de "
            f"esta aplicación:\n{catalog_path}"
        )


if __name__ == "__main__":
    # Autoprueba con catálogos reales en una carpeta temporal.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.catalog_opener
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # 1. Un catálogo recién creado se abre y devuelve la ruta del .db
        db_path = CatalogBuilder(base / "Bueno").build()
        assert open_catalog(base / "Bueno") == db_path
        print("Catálogo válido: abierto")

        # 2. Se puede abrir varias veces (las migraciones no se repiten)
        assert open_catalog(base / "Bueno") == db_path

        # 3. Carpeta sin catálogo (y NO se crea un .db vacío por el camino)
        (base / "Vacia").mkdir()
        try:
            open_catalog(base / "Vacia")
        except CatalogOpenError as error:
            print("Sin catálogo:", str(error).splitlines()[0])
        else:
            raise AssertionError("Debería rechazar una carpeta sin catálogo")
        assert not (base / "Vacia" / CatalogBuilder.DB_FILENAME).exists()

        # 4. Archivo que no es SQLite
        (base / "Corrupto").mkdir()
        (base / "Corrupto" / CatalogBuilder.DB_FILENAME).write_bytes(b"esto no es sqlite" * 100)
        try:
            open_catalog(base / "Corrupto")
        except CatalogOpenError as error:
            print("Archivo corrupto:", str(error).splitlines()[0])
        else:
            raise AssertionError("Debería rechazar un archivo que no es SQLite")

        # 5. Base de datos ajena (tiene tablas, pero ninguna versión de esquema)
        (base / "Ajeno").mkdir()
        foreign = base / "Ajeno" / CatalogBuilder.DB_FILENAME
        with closing(sqlite3.connect(foreign)) as conn:
            conn.execute("CREATE TABLE otra_app(x)")
            conn.commit()
        try:
            open_catalog(base / "Ajeno")
        except CatalogOpenError as error:
            print("Base de datos ajena:", str(error).splitlines()[0])
        else:
            raise AssertionError("Debería rechazar una base de datos ajena")
        with closing(sqlite3.connect(foreign)) as conn:
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert tables == ["otra_app"]  # no se le ha añadido nada

        # 6. Catálogo de una versión más nueva de la aplicación: se rechaza sin tocarlo
        newer = CatalogBuilder(base / "Nuevo").build()
        with closing(sqlite3.connect(newer)) as conn:
            conn.execute("PRAGMA user_version = 99;")
            conn.commit()
        try:
            open_catalog(base / "Nuevo")
        except CatalogOpenError as error:
            print("Versión más nueva:", str(error).splitlines()[0])
        else:
            raise AssertionError("Debería rechazar un catálogo de una versión más nueva")
        with closing(sqlite3.connect(newer)) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 99

        # 6b. Catálogo de la fase de pruebas (versión, pero sin la marca) y base de datos
        #     de otra aplicación con su propia marca: se rechazan sin tocarlos
        for name, app_id, expected in (("Antiguo", 0, "versión de pruebas"),
                                       ("OtraApp", 1234, "no parece un catálogo")):
            path = CatalogBuilder(base / name).build()
            with closing(sqlite3.connect(path)) as conn:
                conn.execute(f"PRAGMA application_id = {app_id};")
                conn.execute("PRAGMA user_version = 17;")
                conn.commit()
            try:
                open_catalog(base / name)
            except CatalogOpenError as error:
                assert expected in str(error), error
                print(f"{name}:", str(error).splitlines()[0])
            else:
                raise AssertionError(f"debería rechazar el catálogo {name}")
            with closing(sqlite3.connect(path)) as conn:
                assert conn.execute("PRAGMA user_version").fetchone()[0] == 17

        # 7. Un catálogo con la versión anterior se migra al abrirlo (simulado: se
        #    añade una migración falsa a la lista, así el catálogo queda "antiguo")
        from core.catalog import catalog_schema

        original_migrations = catalog_schema.MIGRATIONS
        try:
            catalog_schema.MIGRATIONS = (
                *original_migrations,
                "ALTER TABLE media_items ADD COLUMN bit_depth INTEGER;",
            )
            catalog_schema.SCHEMA_VERSION = len(catalog_schema.MIGRATIONS)
            open_catalog(base / "Bueno")
            with closing(sqlite3.connect(db_path)) as conn:
                columns = [row[1] for row in conn.execute("PRAGMA table_info(media_items)")]
                assert "bit_depth" in columns
                expected_version = len(original_migrations) + 1
                assert conn.execute("PRAGMA user_version").fetchone()[0] == expected_version
            print(f"Migración al abrir: v{len(original_migrations)} -> v{expected_version} aplicada")
        finally:
            catalog_schema.MIGRATIONS = original_migrations
            catalog_schema.SCHEMA_VERSION = len(original_migrations)

    print("Autoprueba finalizada correctamente.")
