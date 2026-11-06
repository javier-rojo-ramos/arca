"""Registro de carpetas en el catálogo como 'ubicaciones de almacenamiento'.

Este módulo NO depende de Qt: es Python puro. Sus funciones reciben una conexión
sqlite3 como primer parámetro, así que se pueden enviar tal cual al gestor
asíncrono (CatalogDatabaseManager.execute_async) y ejecutar en un hilo secundario:

    self.db.execute_async(
        register_folder, folder, on_result=self._on_folder_registered,
        on_error=self._on_register_error,
    )

Cuando el usuario añade una carpeta al catálogo, hay que decidir a qué fila de
'storage_locations' pertenecen sus archivos. Regla básica: las ubicaciones NUNCA
se solapan (ninguna está dentro de otra). Si se solaparan, un mismo archivo
podría catalogarse dos veces (una por cada ubicación) con valoraciones propias,
y el UNIQUE (storage_location_id, relative_path) no lo detectaría. Por eso todas
las altas deben pasar por 'register_folder', que aplica estas reglas:

    1. La carpeta ya está dentro de una ubicación existente (o es esa misma):
       se usa esa ubicación. No se crea nada.
    2. La carpeta no está dentro de ninguna ni contiene ninguna: se crea una
       ubicación nueva con esa carpeta.
    3. La carpeta contiene ubicaciones que ya existen: se rechaza con
       'OverlappingLocationError'. (Fusionarlas, moviendo sus elementos a la
       ubicación nueva, se implementará más adelante como un paso aparte.)

Los archivos guardan su 'relative_path' respecto a la ubicación, con '/' como
separador en todos los sistemas; 'make_relative_path' es el único sitio donde se
define ese formato.

Limitación conocida: la comparación de rutas distingue mayúsculas en macOS y
Linux (en Windows no). En macOS, escribir a mano la misma carpeta con otras
mayúsculas podría crear dos ubicaciones. Con el selector de carpetas del sistema
no ocurre, porque entrega siempre la ruta tal como está en disco.

1.2.0 'locate_folder': a qué ubicación pertenecería una carpeta, sin registrar nada.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.storage_locations
"""

__version__ = "1.2.0"
__all__ = [
    "FolderRegistration",
    "InvalidFolderError",
    "OverlappingLocationError",
    "StorageLocation",
    "StorageLocationError",
    "locate_folder",
    "make_relative_path",
    "refresh_location_status",
    "register_folder",
]

# Librerías estándar
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Librerías de terceros
from loguru import logger

# Módulos del proyecto
from core.catalog.media_types import CACHEABLE_MEDIA_TYPES, MediaType


@dataclass(frozen=True, slots=True)
class StorageLocation:
    """Una fila de 'storage_locations' como objeto simple (no depende de la conexión).

    Attributes:
        id: Identificador de la ubicación.
        name: Nombre para mostrar en la interfaz.
        absolute_path: Carpeta raíz de la ubicación.
        default_media_type: Valor de 'MediaType' por defecto, o None.
        is_online: False si la unidad está desconectada.
    """

    id: int
    name: str
    absolute_path: Path
    default_media_type: str | None
    is_online: bool


@dataclass(frozen=True, slots=True)
class FolderRegistration:
    """Resultado de registrar una carpeta.

    Attributes:
        location: Ubicación a la que pertenecen los archivos de la carpeta.
        relative_folder: Ruta de la carpeta respecto a la ubicación, con '/'
            ('' si la carpeta es la propia raíz de la ubicación).
        created: True si se ha creado una ubicación nueva; False si ya existía.
    """

    location: StorageLocation
    relative_folder: str
    created: bool


class StorageLocationError(Exception):
    """Error genérico al registrar una carpeta en el catálogo.

    Quien llame solo necesita capturar esta excepción y mostrar 'str(error)'.
    """


class InvalidFolderError(StorageLocationError):
    """La ruta elegida está vacía, no existe o no es una carpeta."""


class OverlappingLocationError(StorageLocationError):
    """La carpeta elegida contiene ubicaciones que ya están en el catálogo.

    Attributes:
        folder: La carpeta que se intentaba añadir.
        locations: Ubicaciones existentes que quedarían dentro de ella.
    """

    def __init__(self, folder: Path, locations: list[StorageLocation]) -> None:
        self.folder = folder
        self.locations = locations
        listado = "\n".join(f"  - {location.absolute_path}" for location in locations)
        super().__init__(
            f"La carpeta elegida contiene carpetas que ya están en el catálogo:\n"
            f"{listado}\n"
            "Por ahora no se pueden solapar. Elige una carpeta que no las contenga."
        )


# -----------------------------------------------------------------------------
# API pública
# -----------------------------------------------------------------------------


def register_folder(
    conn: sqlite3.Connection,
    folder: str | Path,
    *,
    name: str | None = None,
    default_media_type: MediaType | str | None = None,
) -> FolderRegistration:
    """Registra una carpeta en el catálogo aplicando las reglas anti-solapamiento.

    No hace 'commit': lo hace quien llame (el gestor asíncrono lo hace solo al
    terminar sin errores y hace rollback si esta función lanza una excepción).

    Args:
        conn: Conexión sqlite3 (con o sin 'row_factory').
        folder: Carpeta elegida por el usuario. Debe existir.
        name: Nombre de la ubicación si hay que crearla (por defecto, el nombre
            de la carpeta). Se ignora si la carpeta ya pertenece a una ubicación.
        default_media_type: Tipo de medio por defecto de la ubicación nueva. Se
            ignora si la ubicación ya existía.

    Returns:
        La ubicación a la que pertenece la carpeta y su ruta relativa en ella.

    Raises:
        InvalidFolderError: Si la ruta está vacía, no existe o no es una carpeta.
        ValueError: Si 'default_media_type' no es un tipo de medio del catálogo.
        OverlappingLocationError: Si la carpeta contiene ubicaciones existentes.
        sqlite3.Error: Si falla la base de datos.
    """
    # 1. Validaciones que no necesitan la base de datos
    folder_path = _normalize_folder(folder)
    default_value = _validate_media_type(default_media_type)

    # 2. Bloquea la escritura desde ya (BEGIN IMMEDIATE): así dos altas
    #    simultáneas no pueden comprobar "no hay solapamiento" a la vez y crear
    #    ubicaciones solapadas. Si ya hay una transacción abierta, se aprovecha.
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE;")

    locations = _load_locations(conn)

    # 3. REGLA 1: la carpeta ya está dentro de una ubicación (o es ella misma)
    existing = _containing_location(locations, folder_path)
    if existing is not None:
        return existing

    # 4. REGLA 3: la carpeta contiene ubicaciones existentes -> se rechaza
    contained = [
        location
        for location in locations
        if location.absolute_path.is_relative_to(folder_path)
    ]
    if contained:
        raise OverlappingLocationError(folder_path, contained)

    # 5. REGLA 2: no hay solapamiento -> se crea la ubicación nueva
    location_name = name or folder_path.name or str(folder_path)
    cursor = conn.execute(
        "INSERT INTO storage_locations(name, absolute_path, default_media_type) "
        "VALUES (?, ?, ?)",
        (location_name, str(folder_path), default_value),
    )
    new_location = StorageLocation(
        id=int(cursor.lastrowid),
        name=location_name,
        absolute_path=folder_path,
        default_media_type=default_value,
        is_online=True,
    )
    logger.info(f"Ubicación de almacenamiento creada: {folder_path}")
    return FolderRegistration(new_location, relative_folder="", created=True)


def locate_folder(conn: sqlite3.Connection, folder: str | Path) -> FolderRegistration | None:
    """A qué ubicación pertenecería una carpeta, SIN registrar nada (solo lee).

    Aplica la regla 1 de 'register_folder': si la carpeta está dentro de una ubicación
    (o es ella misma), devuelve esa ubicación y su ruta relativa ('created' = False). Si
    no, None (al añadirla se crearía una ubicación nueva, o se rechazaría por solaparse).

    Raises:
        InvalidFolderError: Si la ruta está vacía, no existe o no es una carpeta.
    """
    return _containing_location(_load_locations(conn), _normalize_folder(folder))


def make_relative_path(location_path: Path, file_path: Path) -> str:
    """Devuelve la ruta de un archivo relativa a su ubicación, con '/' como separador.

    Es el valor que se guarda en 'media_items.relative_path'. Usa siempre '/',
    también en Windows, para que el catálogo sea portable entre sistemas.

    Args:
        location_path: Carpeta raíz de la ubicación ('StorageLocation.absolute_path').
        file_path: Ruta completa del archivo.

    Raises:
        ValueError: Si el archivo no está dentro de la ubicación.
    """
    return file_path.relative_to(location_path).as_posix()


# -----------------------------------------------------------------------------
# Pasos internos
# -----------------------------------------------------------------------------


def refresh_location_status(conn: sqlite3.Connection) -> int:
    """Comprueba qué ubicaciones están conectadas y lo anota en 'is_online'.

    Una ubicación está conectada si su carpeta raíz existe (un disco externo
    desconectado o una unidad de red caída no la tienen). Es una consulta al disco por
    ubicación, no por archivo. No hace 'commit' (lo hace el gestor de la base de datos).

    Ojo: en Windows, comprobar una unidad de red caída puede tardar varios segundos; por
    eso se llama desde un hilo secundario ('execute_async').

    Args:
        conn: Conexión sqlite3.

    Returns:
        Cuántas ubicaciones han cambiado de estado (0 = todo sigue igual).
    """
    changed = 0
    for location in _load_locations(conn):
        try:
            online = location.absolute_path.is_dir()
        except OSError:
            online = False
        if online != location.is_online:
            conn.execute(
                "UPDATE storage_locations SET is_online = ? WHERE id = ?",
                (1 if online else 0, location.id),
            )
            changed += 1
    return changed


def _normalize_folder(folder: str | Path) -> Path:
    """Convierte la ruta en absoluta y comprueba que es una carpeta que existe.

    Se usa 'os.path.abspath' y no 'Path.resolve()' a propósito: 'resolve()' puede
    convertir una unidad de red mapeada de Windows (Z:\\) en su ruta UNC, y el
    usuario esperaría ver guardada la ruta que eligió.
    """
    # Una cadena vacía NO debe interpretarse como "la carpeta actual"
    if not str(folder).strip():
        raise InvalidFolderError("No se ha indicado ninguna carpeta.")

    try:
        folder_path = Path(os.path.abspath(folder))
        is_folder = folder_path.is_dir()
    except OSError as exc:
        raise InvalidFolderError(f"No se pudo acceder a la carpeta: {exc}") from exc

    if not is_folder:
        raise InvalidFolderError(
            f"La ruta no existe o no es una carpeta:\n{folder_path}"
        )
    return folder_path


def _containing_location(
    locations: list[StorageLocation], folder_path: Path
) -> FolderRegistration | None:
    """Ubicación que contiene la carpeta (o es ella misma), con su ruta relativa; o None.

    'is_relative_to' compara por componentes de ruta: '/Fotos2' NO está dentro de
    '/Fotos' (con 'startswith' sobre texto sí lo estaría).
    """
    for location in locations:
        if folder_path.is_relative_to(location.absolute_path):
            relative = folder_path.relative_to(location.absolute_path).as_posix()
            # La propia raíz da '.', que se guarda como cadena vacía
            relative_folder = "" if relative == "." else relative
            return FolderRegistration(location, relative_folder, created=False)
    return None


def _validate_media_type(media_type: MediaType | str | None) -> str | None:
    """Comprueba que es un tipo de medio del catálogo y devuelve su valor en texto."""
    if media_type is None:
        return None

    # Lanza ValueError si no es un valor válido de MediaType
    value = MediaType(media_type)
    if value not in CACHEABLE_MEDIA_TYPES:
        raise ValueError(f"'{value}' no es un tipo de medio que gestione el catálogo.")
    return value.value


def _load_locations(conn: sqlite3.Connection) -> list[StorageLocation]:
    """Lee todas las ubicaciones (son pocas: una por biblioteca o disco)."""
    rows = conn.execute(
        "SELECT id, name, absolute_path, default_media_type, is_online "
        "FROM storage_locations ORDER BY id"
    ).fetchall()
    # Se accede por posición (no por nombre) para funcionar con cualquier row_factory
    return [
        StorageLocation(
            id=row[0],
            name=row[1],
            absolute_path=Path(row[2]),
            default_media_type=row[3],
            is_online=bool(row[4]),
        )
        for row in rows
    ]


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria y carpetas temporales.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.storage_locations
    import tempfile

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    connection = sqlite3.connect(":memory:")
    configure_connection(connection)
    apply_migrations(connection)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        photos = base / "Fotos"
        photos_2024 = photos / "2024"
        photos_2 = base / "Fotos2"  # empieza igual que "Fotos", pero es otra carpeta
        for directory in (photos_2024, photos_2):
            directory.mkdir(parents=True)

        # REGLA 2: carpeta nueva -> se crea la ubicación
        first = register_folder(connection, photos, default_media_type=MediaType.PHOTO)
        print(f"Alta de Fotos: creada={first.created}, relativa='{first.relative_folder}'")
        assert first.created and first.relative_folder == ""
        assert first.location.default_media_type == "photo"

        # REGLA 1 (misma carpeta): no se crea nada
        again = register_folder(connection, photos)
        assert not again.created and again.location.id == first.location.id

        # REGLA 1 (subcarpeta): misma ubicación, con ruta relativa
        sub = register_folder(connection, photos_2024)
        print(f"Alta de Fotos/2024: creada={sub.created}, relativa='{sub.relative_folder}'")
        assert not sub.created and sub.location.id == first.location.id
        assert sub.relative_folder == "2024"

        # "Fotos2" NO está dentro de "Fotos": ubicación distinta
        other = register_folder(connection, photos_2, name="Otras fotos")
        assert other.created and other.location.id != first.location.id
        assert other.location.name == "Otras fotos"

        # REGLA 3: una carpeta que contiene ubicaciones existentes se rechaza
        try:
            register_folder(connection, base)
        except OverlappingLocationError as error:
            print(f"Solapamiento rechazado: {len(error.locations)} ubicaciones dentro")
            assert len(error.locations) == 2
        else:
            raise AssertionError("Debería haber lanzado OverlappingLocationError")

        # Rutas no válidas
        for invalid in ("", "   ", base / "no_existe"):
            try:
                register_folder(connection, invalid)
            except InvalidFolderError:
                print(f"Ruta no válida rechazada: {str(invalid)!r}")
            else:
                raise AssertionError(f"{invalid!r} debería ser inválida")

        file_path = base / "archivo.txt"
        file_path.write_bytes(b"x")
        try:
            register_folder(connection, file_path)  # un archivo no es una carpeta
        except InvalidFolderError:
            print("Un archivo no es una carpeta: rechazado")
        else:
            raise AssertionError("Un archivo no debería aceptarse")

        # Tipo de medio no válido ('other' existe en MediaType pero no se cataloga)
        for bad_type in ("other", "comic"):
            try:
                register_folder(connection, photos, default_media_type=bad_type)
            except ValueError:
                print(f"Tipo de medio rechazado: {bad_type!r}")
            else:
                raise AssertionError(f"{bad_type!r} debería rechazarse")

        # Ruta relativa de un archivo: siempre con '/'
        relative = make_relative_path(photos, photos_2024 / "viaje" / "foto.jpg")
        assert relative == "2024/viaje/foto.jpg"

        # Con 'sqlite3.Row' (como usa el gestor asíncrono) funciona igual
        connection.row_factory = sqlite3.Row
        assert register_folder(connection, photos_2024).location.id == first.location.id

        total = connection.execute("SELECT COUNT(*) FROM storage_locations").fetchone()[0]
        print(f"Ubicaciones en la base de datos: {total}")
        assert total == 2  # solo Fotos y Fotos2: nada de duplicados ni solapadas

    connection.close()

    # Estado de conexión de las ubicaciones: una carpeta que desaparece (disco
    # desconectado) queda "sin conexión" y vuelve a "conectada" al reaparecer
    from core.catalog.catalog_schema import apply_migrations, configure_connection

    with tempfile.TemporaryDirectory() as tmp:
        disk = Path(tmp) / "DiscoExterno"
        disk.mkdir()
        status = sqlite3.connect(":memory:")
        configure_connection(status)
        apply_migrations(status)
        status.execute(
            "INSERT INTO storage_locations(name, absolute_path) VALUES ('Disco', ?)", (str(disk),)
        )
        assert refresh_location_status(status) == 0  # conectada, como ya estaba
        disk.rename(Path(tmp) / "Desconectado")
        assert refresh_location_status(status) == 1
        assert status.execute("SELECT is_online FROM storage_locations").fetchone()[0] == 0
        (Path(tmp) / "Desconectado").rename(disk)
        assert refresh_location_status(status) == 1
        assert status.execute("SELECT is_online FROM storage_locations").fetchone()[0] == 1

        # 'locate_folder': solo lee (no abre transacción ni crea ubicaciones)
        status.commit()  # 'refresh_location_status' no confirma: lo hace quien llama
        (disk / "2024" / "Verano").mkdir(parents=True)
        found = locate_folder(status, disk / "2024" / "Verano")
        assert found is not None and found.relative_folder == "2024/Verano" and not found.created
        assert locate_folder(status, disk).relative_folder == ""
        assert locate_folder(status, Path(tmp)) is None  # fuera (la contiene): no se crea nada
        assert not status.in_transaction
        assert status.execute("SELECT COUNT(*) FROM storage_locations").fetchone()[0] == 1
        try:
            locate_folder(status, disk / "no_existe")
        except InvalidFolderError:
            pass
        else:
            raise AssertionError("debería rechazar una carpeta que no existe")
        status.close()
    print("Estado de conexión de las ubicaciones y 'locate_folder': correcto")
    print("Autoprueba finalizada correctamente.")
