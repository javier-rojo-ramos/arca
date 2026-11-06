"""Bibliotecas del catálogo y tipo de contenido de cada carpeta.

Este módulo NO depende de Qt. Las funciones que tocan la base de datos reciben la
conexión como primer parámetro (para 'CatalogDatabaseManager.execute_async') y NO hacen
'commit': lo hace quien las llama.

Dos conceptos distintos (no confundir con 'media_type', el tipo TÉCNICO del archivo):

    BIBLIOTECA ('media_items.library'): qué módulo gestiona el archivo.
        image   fotos y vídeos personales (de cámara o de móvil)     -> módulo Imagen
        video   películas y series                                   -> módulo Vídeo
        audio   música                                               -> módulo Audio
        ebook   libros electrónicos                                  -> módulo Ebooks
        tracks  tracks GPS (GPX)                                     -> módulo Tracks
        NULL    sin clasificar (p. ej. un vídeo en una carpeta automática: puede ser un
                clip del móvil o una película; se resolverá en los pasos 2b y 2c)

    TIPO DE CONTENIDO DE UNA CARPETA (tabla 'folder_libraries'): lo que el usuario dice
    que contiene una carpeta al añadirla ("¿Qué contiene esta carpeta?"). Vale para ella
    y para sus subcarpetas; una subcarpeta puede declarar el suyo (manda el más
    profundo). Sin declaración = "auto".
        auto    Detectar automáticamente: se cataloga todo lo soportado y la biblioteca
                sale del tipo de archivo (un vídeo queda sin clasificar).
        image / video / audio / ebook / tracks
                La carpeta es de esa biblioteca: SOLO se catalogan los tipos que admite
                (ver 'ALLOWED_MEDIA_TYPES') y todos van a esa biblioteca. El resto se
                ignora al escanear: las carátulas de una carpeta de música o los pósters
                de una de películas no se catalogan (decidido por el autor: las carátulas
                viven en las etiquetas del audio y los pósters, en el catálogo).

VÍDEOS EN CARPETAS "auto" (paso 2b): se intenta deducir por el NOMBRE del archivo, que
es lo único que se conoce al escanear ('guess_video_library'):
    - Nombres de cámara o de móvil (IMG_, VID_, PXL_, DJI_, GOPR, GX, MVI_, C0001,
      20240101_120000...) y los .MTS / .M2TS de las videocámaras        -> 'image'
    - Episodios (S01E02, 1x02) o películas (año entre paréntesis o etiquetas de
      ripeo como 1080p, x264, BluRay, WEB-DL)                            -> 'video'
    - Lo demás queda sin clasificar hasta que se leen sus metadatos (paso 2c):
      con datos de cámara (marca o modelo) o GPS -> 'image'; más de 40 minutos sin
      datos de cámara -> 'video'; si no, sigue sin clasificar ('classify_video').

CORRECCIÓN MANUAL (menú contextual "Biblioteca", 'set_library'): se guarda con
'library_manual = 1', y entonces ni el escáner ni la detección automática la cambian.
"Detectar automáticamente" la quita y vuelve a calcularla.

Dónde se usa: 'folder_importer.add_folder' (filtra y asigna la biblioteca al escanear), el
diálogo "¿Qué contiene esta carpeta?" ('folder_content_for' le dice qué preseleccionar),
el menú de la cuadrícula ('set_library'), la apertura del catálogo y el final de la
lectura de metadatos ('classify_pending_videos': aplica la detección, por el nombre y por
los metadatos, a los vídeos que siguen sin clasificar).

1.3.1 Nombres más cortos, como las bibliotecas de Windows: «Imágenes», «Vídeos», «Música».
1.3.0 'LIBRARY_NAMES': el nombre de cada biblioteca para el usuario, en un solo sitio
      (diálogo de la carpeta, submenú «Biblioteca», colecciones inteligentes, inspector).
1.2.0 Clasificación de vídeos también por sus metadatos (cámara, GPS, duración).
1.1.0 Detección de vídeos por el nombre, corrección manual y vídeos sin clasificar.

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.libraries
"""

__version__ = "1.3.1"
__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "AUTO_LIBRARY_BY_MEDIA_TYPE",
    "CLASSIFIABLE_MEDIA_TYPES",
    "FOLDER_AUTO",
    "FOLDER_CONTENTS",
    "LIBRARY_NAMES",
    "MOVIE_MIN_DURATION_S",
    "FolderContentResolver",
    "Library",
    "classify_pending_videos",
    "classify_video",
    "count_unclassified",
    "folder_content_for",
    "guess_video_library",
    "is_allowed",
    "library_for",
    "parent_folder",
    "set_folder_content",
    "set_library",
    "validate_folder_content",
]

# Librerías estándar
import re
import sqlite3
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

# Módulos del proyecto
from core.catalog.media_types import MediaType
from core.catalog.storage_locations import locate_folder


class Library(StrEnum):
    """Biblioteca de un elemento (el valor se guarda en 'media_items.library').

    Los valores NO deben cambiarse una vez creados catálogos reales.
    """

    IMAGE = "image"  # fotos y vídeos personales
    VIDEO = "video"  # películas y series
    AUDIO = "audio"  # música
    EBOOK = "ebook"  # libros electrónicos
    TRACKS = "tracks"  # tracks GPS (GPX)


# Nombre de cada biblioteca para el usuario (el MISMO en toda la interfaz). Ojo: en los
# textos de menús y botones de Qt, '&' marca la tecla de acceso; quien los use ahí debe
# escribirlo doble ('&&'), ver 'ui_helpers/dialogs/folder_content_dialog.py'
LIBRARY_NAMES: dict[str, str] = {
    Library.IMAGE: "Imágenes",
    Library.VIDEO: "Vídeos",
    Library.AUDIO: "Música",
    Library.EBOOK: "Libros",
    Library.TRACKS: "Tracks GPS",
}


# Tipo de contenido "Detectar automáticamente" (lo que vale una carpeta sin declaración)
FOLDER_AUTO = "auto"

# Todos los tipos de contenido que se pueden declarar en una carpeta, en el orden del diálogo
FOLDER_CONTENTS: tuple[str, ...] = (FOLDER_AUTO, *(library.value for library in Library))

# Qué tipos de archivo se catalogan en una carpeta declarada de cada biblioteca.
# En una carpeta "auto" se cataloga todo lo soportado.
ALLOWED_MEDIA_TYPES: dict[str, frozenset[str]] = {
    Library.IMAGE: frozenset({MediaType.PHOTO, MediaType.VIDEO}),
    Library.VIDEO: frozenset({MediaType.VIDEO}),
    Library.AUDIO: frozenset({MediaType.AUDIO}),
    Library.EBOOK: frozenset({MediaType.EBOOK}),
    Library.TRACKS: frozenset({MediaType.TRACK}),
}

# Biblioteca según el tipo de archivo en una carpeta "auto". El vídeo no está: puede ser
# un clip del móvil (Imagen) o una película (Vídeo), así que queda sin clasificar (None)
AUTO_LIBRARY_BY_MEDIA_TYPE: dict[str, str] = {
    MediaType.PHOTO: Library.IMAGE,
    MediaType.AUDIO: Library.AUDIO,
    MediaType.EBOOK: Library.EBOOK,
    MediaType.TRACK: Library.TRACKS,
}

assert set(ALLOWED_MEDIA_TYPES) == set(Library)  # no puede faltar ninguna biblioteca

# Tipos de archivo que pueden estar en MÁS DE UNA biblioteca (hoy, solo el vídeo: clip
# personal o película). Son los únicos que tiene sentido clasificar a mano
CLASSIFIABLE_MEDIA_TYPES: frozenset[str] = frozenset(
    media_type
    for media_type in {t for types in ALLOWED_MEDIA_TYPES.values() for t in types}
    if sum(media_type in types for types in ALLOWED_MEDIA_TYPES.values()) > 1
)

# SQLite limita las variables de una sentencia (999 en versiones antiguas)
_CHUNK = 500

# --- Detección de vídeos por el nombre (carpetas "auto") ---
# Películas y series: se miran ANTES que los de cámara (son indicios más fuertes).
# Se buscan en cualquier parte del nombre, sin distinguir mayúsculas.
_MOVIE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![a-z0-9])s\d{1,2}[ ._-]?e\d{1,3}(?![0-9])", re.IGNORECASE),  # S01E02, s1.e2
    re.compile(r"(?<![a-z0-9])\d{1,2}x\d{2}(?![0-9])", re.IGNORECASE),  # 1x02
    re.compile(r"[(\[]\s*(19|20)\d{2}\s*[)\]]"),  # (2010) o [2010]
    re.compile(
        r"(?<![a-z0-9])(480p|576p|720p|1080p|2160p|4k|x264|x265|h\.?264|h\.?265|hevc|"
        r"xvid|divx|bluray|blu-ray|bdrip|brrip|dvdrip|webrip|web-dl|hdtv|remux)(?![a-z0-9])",
        re.IGNORECASE,
    ),
)
# Cámaras y móviles: el nombre EMPIEZA así (sin extensión)
_CAMERA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(img|vid|pxl|dji|mvi|mov|dsc|dscn|dscf|gopr|trim|screenrecording)[_-]", re.IGNORECASE
    ),
    re.compile(r"^(gopr|gp|gx|gh)\d{4,}", re.IGNORECASE),  # GoPro: GOPR0001, GX010001
    re.compile(r"^c\d{4}$", re.IGNORECASE),  # Sony: C0001
    re.compile(r"^(vid|img)-\d{8}-wa\d+", re.IGNORECASE),  # WhatsApp: VID-20240101-WA0001
    re.compile(r"^(vid_|pxl_|img_)?\d{8}_\d{6}"),  # Android/Samsung: 20240101_120000
)
# Extensiones de videocámara (AVCHD): siempre personales
_CAMERA_EXTENSIONS = frozenset({"mts", "m2ts"})

# Un vídeo de al menos esta duración (segundos) y sin datos de cámara se toma por película
# o episodio. 40 minutos: más que casi cualquier clip personal y menos que una película
MOVIE_MIN_DURATION_S = 40 * 60


def guess_video_library(file_name: str) -> str | None:
    """Biblioteca de un vídeo deducida por su nombre, o None si el nombre no lo dice.

    Ejemplos: 'IMG_1234.MOV' -> 'image'; 'Serie S01E02 1080p.mkv' -> 'video';
    'Boda.mp4' -> None (sin clasificar).
    """
    stem, _dot, extension = file_name.rpartition(".")
    if not stem:  # sin extensión
        stem, extension = file_name, ""
    if any(pattern.search(stem) for pattern in _MOVIE_PATTERNS):
        return Library.VIDEO.value
    if extension.lower() in _CAMERA_EXTENSIONS:
        return Library.IMAGE.value
    if any(pattern.search(stem) for pattern in _CAMERA_PATTERNS):
        return Library.IMAGE.value
    return None


# -----------------------------------------------------------------------------
# Reglas (sin base de datos)
# -----------------------------------------------------------------------------


def validate_folder_content(content: object) -> str:
    """Devuelve el tipo de contenido en texto, o lanza ValueError si no es válido."""
    value = str(content) if isinstance(content, str) else None
    if value not in FOLDER_CONTENTS:
        raise ValueError(f"Tipo de contenido de carpeta no válido: {content!r}")
    return value


def is_allowed(media_type: str, content: str) -> bool:
    """True si un archivo de ese tipo se cataloga en una carpeta con ese contenido."""
    if content == FOLDER_AUTO:
        return True
    return media_type in ALLOWED_MEDIA_TYPES[content]


def classify_video(
    file_name: str,
    *,
    duration: float | None = None,
    has_camera: bool = False,
    has_gps: bool = False,
) -> str | None:
    """Biblioteca de un vídeo de una carpeta "auto", con todo lo que se sepa de él.

    Por orden: su nombre ('guess_video_library'); si no dice nada, sus metadatos: datos
    de cámara (marca o modelo) o GPS -> 'image' (lo grabó un móvil o una cámara); al
    menos 'MOVIE_MIN_DURATION_S' sin ellos -> 'video'. Si nada lo decide, None.

    Args:
        file_name: Nombre del archivo.
        duration: Duración en segundos (None = no se sabe todavía).
        has_camera: Si sus metadatos traen marca o modelo de cámara.
        has_gps: Si trae coordenadas.
    """
    by_name = guess_video_library(file_name)
    if by_name is not None:
        return by_name
    if has_camera or has_gps:
        return Library.IMAGE.value
    if duration is not None and duration >= MOVIE_MIN_DURATION_S:
        return Library.VIDEO.value
    return None


def library_for(media_type: str, content: str, file_name: str = "") -> str | None:
    """Biblioteca de un archivo de ese tipo en una carpeta con ese contenido.

    En una carpeta declarada, la de la carpeta (llamar solo con tipos admitidos: ver
    'is_allowed'). En una "auto", la del tipo de archivo; un vídeo, la que diga su
    nombre ('guess_video_library'), o None (sin clasificar).
    """
    if content == FOLDER_AUTO:
        if media_type == MediaType.VIDEO:
            return guess_video_library(file_name)
        library = AUTO_LIBRARY_BY_MEDIA_TYPE.get(media_type)
        return str(library) if library is not None else None
    return str(content)


def parent_folder(relative_path: str) -> str:
    """Carpeta (relativa a la ubicación) de un archivo: 'a/b/c.jpg' -> 'a/b'; 'c.jpg' -> ''."""
    return relative_path.rpartition("/")[0]


def _ancestors(folder: str) -> list[str]:
    """La carpeta y sus padres, de la más profunda a la raíz: 'a/b' -> ['a/b', 'a', '']."""
    chain = []
    while folder:
        chain.append(folder)
        folder = parent_folder(folder)
    chain.append("")
    return chain


# -----------------------------------------------------------------------------
# Declaraciones por carpeta (base de datos)
# -----------------------------------------------------------------------------


class FolderContentResolver:
    """Tipo de contenido efectivo de las carpetas de UNA ubicación (con herencia).

    Lee de una vez las declaraciones de la ubicación (son pocas) y recuerda lo ya
    resuelto: el escáner pregunta por cada archivo y la mayoría comparten carpeta.
    """

    def __init__(self, declarations: dict[str, str]) -> None:
        """Args: declarations: carpeta relativa ('' = raíz) -> tipo de contenido."""
        self._declarations = dict(declarations)
        self._cache: dict[str, str] = {}

    @classmethod
    def load(cls, conn: sqlite3.Connection, location_id: int) -> "FolderContentResolver":
        """Lee las declaraciones de una ubicación."""
        rows = conn.execute(
            "SELECT folder, content FROM folder_libraries WHERE storage_location_id = ?",
            (location_id,),
        ).fetchall()
        return cls({row[0]: row[1] for row in rows})

    def content_of(self, folder: str) -> str:
        """Tipo de contenido de una carpeta: el suyo o el del padre declarado más cercano."""
        cached = self._cache.get(folder)
        if cached is not None:
            return cached
        content = next(
            (self._declarations[f] for f in _ancestors(folder) if f in self._declarations),
            FOLDER_AUTO,
        )
        self._cache[folder] = content
        return content

    def inherited_content(self, folder: str) -> str:
        """Tipo de contenido que tendría la carpeta sin su propia declaración (el del padre)."""
        if not folder:
            return FOLDER_AUTO
        return self.content_of(parent_folder(folder))


def set_folder_content(
    conn: sqlite3.Connection, location_id: int, folder: str, content: str
) -> bool:
    """Declara qué contiene una carpeta (y sus subcarpetas sin declaración propia).

    Si lo declarado es lo mismo que heredaría de su carpeta padre, no se guarda nada (y
    se borra su declaración anterior, si la tenía): así la tabla solo tiene lo necesario.
    No hace 'commit'.

    Args:
        conn: Conexión sqlite3.
        location_id: Ubicación de la carpeta.
        folder: Carpeta relativa a la ubicación ('' = su raíz).
        content: 'auto' o una biblioteca.

    Returns:
        True si ha cambiado el tipo de contenido efectivo de la carpeta.

    Raises:
        ValueError: Si 'content' no es un tipo de contenido válido.
    """
    content = validate_folder_content(content)
    resolver = FolderContentResolver.load(conn, location_id)
    before = resolver.content_of(folder)
    if content == resolver.inherited_content(folder):
        conn.execute(
            "DELETE FROM folder_libraries WHERE storage_location_id = ? AND folder = ?",
            (location_id, folder),
        )
    else:
        conn.execute(
            """INSERT INTO folder_libraries(storage_location_id, folder, content)
               VALUES (?, ?, ?)
               ON CONFLICT(storage_location_id, folder)
               DO UPDATE SET content = excluded.content, updated_at = CURRENT_TIMESTAMP""",
            (location_id, folder, content),
        )
    return content != before


def folder_content_for(conn: sqlite3.Connection, folder: str | Path) -> str:
    """Tipo de contenido efectivo de una carpeta del disco (para preseleccionarlo en el diálogo).

    Solo lee. Si la carpeta no está en ninguna ubicación del catálogo (o no se puede
    leer), devuelve 'auto'.
    """
    try:
        registration = locate_folder(conn, folder)
    except Exception:  # noqa: BLE001 - solo es una preselección: ante la duda, "auto"
        return FOLDER_AUTO
    if registration is None:
        return FOLDER_AUTO
    resolver = FolderContentResolver.load(conn, registration.location.id)
    return resolver.content_of(registration.relative_folder)


def set_library(
    conn: sqlite3.Connection, media_ids: Sequence[int], library: str | None
) -> dict[int, tuple[str | None, int]]:
    """Corrección manual de la biblioteca (menú "Biblioteca" de la cuadrícula).

    No hace 'commit'. Solo cambia los elementos de un tipo que puede estar en varias
    bibliotecas ('CLASSIFIABLE_MEDIA_TYPES': hoy, los vídeos) y que admite la elegida:
    una foto siempre es de Imagen, así que no se toca.

    Args:
        conn: Conexión sqlite3.
        media_ids: Elementos elegidos.
        library: Biblioteca nueva (queda fijada: 'library_manual = 1'), o None =
            "Detectar automáticamente": se quita la marca manual y se vuelve a calcular
            como al escanear (tipo de contenido de su carpeta y nombre del archivo).

    Returns:
        Lo que ha cambiado: 'id' -> (biblioteca nueva o None, 1 si es manual). Sirve
        para actualizar las tarjetas cargadas sin recargar la cuadrícula.

    Raises:
        ValueError: Si 'library' no es una biblioteca.
    """
    ids = [int(media_id) for media_id in media_ids]
    changed: dict[int, tuple[str | None, int]] = {}
    if library is not None:
        library = Library(library).value  # ValueError si no existe
        allowed = sorted(ALLOWED_MEDIA_TYPES[library] & CLASSIFIABLE_MEDIA_TYPES)
        if not allowed:
            return changed  # ningún tipo clasificable puede ir a esa biblioteca
        type_marks = ",".join("?" * len(allowed))
        for start in range(0, len(ids), _CHUNK):
            chunk = ids[start : start + _CHUNK]
            marks = ",".join("?" * len(chunk))
            # RETURNING (SQLite 3.35+) dice qué filas han cambiado, sin otra consulta
            cursor = conn.execute(
                f"""UPDATE media_items SET library = ?, library_manual = 1
                     WHERE id IN ({marks}) AND media_type IN ({type_marks})
                       AND (library IS NOT ? OR library_manual = 0)
                 RETURNING id""",
                (library, *chunk, *allowed, library),
            )
            changed.update({row[0]: (library, 1) for row in cursor.fetchall()})
        return changed

    # "Detectar automáticamente": se recalcula cada uno con las reglas del escáner
    resolvers: dict[int, FolderContentResolver] = {}
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        marks = ",".join("?" * len(chunk))
        type_marks = ",".join("?" * len(CLASSIFIABLE_MEDIA_TYPES))
        rows = conn.execute(
            "SELECT id, storage_location_id, relative_path, file_name, media_type, library, "
            f"library_manual FROM media_items WHERE id IN ({marks}) "
            f"AND media_type IN ({type_marks})",
            (*chunk, *sorted(CLASSIFIABLE_MEDIA_TYPES)),
        ).fetchall()
        for media_id, location_id, relative_path, file_name, media_type, current, manual in rows:
            resolver = resolvers.get(location_id)
            if resolver is None:
                resolver = resolvers[location_id] = FolderContentResolver.load(conn, location_id)
            content = resolver.content_of(parent_folder(relative_path))
            # Un archivo que ya no encaja con su carpeta (p. ej. catalogado antes de
            # declararla) recibe la biblioteca de su tipo, como en una carpeta "auto"
            if not is_allowed(media_type, content):
                content = FOLDER_AUTO
            new_library = library_for(media_type, content, file_name)
            if new_library != current or manual:
                conn.execute(
                    "UPDATE media_items SET library = ?, library_manual = 0 WHERE id = ?",
                    (new_library, media_id),
                )
                changed[media_id] = (new_library, 0)
    return changed


def classify_pending_videos(conn: sqlite3.Connection) -> int:
    """Clasifica los vídeos que siguen sin biblioteca, por su nombre y sus metadatos.

    Se llama al abrir el catálogo y al terminar de leer metadatos: así se clasifican los
    vídeos catalogados antes de que existiera la detección (o de mejorarla) y los que se
    acaban de leer, sin sincronizar las carpetas. Solo toca los que no tienen biblioteca
    ni corrección manual (ver 'classify_video'). No hace 'commit'.

    Returns:
        Número de vídeos clasificados.
    """
    rows = conn.execute(
        """SELECT m.id, m.file_name, m.duration, m.latitude,
                  d.camera_make, d.camera_model
             FROM media_items AS m
             LEFT JOIN video_details AS d ON d.media_id = m.id
            WHERE m.media_type = ? AND m.library IS NULL AND m.library_manual = 0""",
        (MediaType.VIDEO.value,),
    ).fetchall()
    updates = [
        (library, media_id)
        for media_id, file_name, duration, latitude, make, model in rows
        if (
            library := classify_video(
                file_name,
                duration=duration,
                has_camera=bool(make or model),
                has_gps=latitude is not None,
            )
        )
        is not None
    ]
    conn.executemany("UPDATE media_items SET library = ? WHERE id = ?", updates)
    return len(updates)


def count_unclassified(conn: sqlite3.Connection, location_id: int, folder: str) -> int:
    """Elementos sin biblioteca dentro de una carpeta (y sus subcarpetas).

    Args:
        conn: Conexión sqlite3.
        location_id: Ubicación.
        folder: Carpeta relativa a la ubicación ('' = toda la ubicación).
    """
    if not folder:
        row = conn.execute(
            "SELECT COUNT(*) FROM media_items WHERE storage_location_id = ? AND library IS NULL",
            (location_id,),
        ).fetchone()
        return int(row[0])
    # Rango en lugar de LIKE (ver 'catalog_writer._under_prefix'): '0' sigue a '/'
    row = conn.execute(
        """SELECT COUNT(*) FROM media_items
            WHERE storage_location_id = ? AND library IS NULL
              AND (relative_path >= ? AND relative_path < ?)""",
        (location_id, folder + "/", folder + "0"),
    ).fetchone()
    return int(row[0])


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria y carpetas temporales.
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.libraries
    import tempfile

    from core.catalog.catalog_schema import apply_migrations, configure_connection

    # 1. Reglas
    assert FOLDER_CONTENTS == ("auto", "image", "video", "audio", "ebook", "tracks")
    assert is_allowed("photo", "auto") and is_allowed("video", "auto")
    assert is_allowed("video", "image") and is_allowed("photo", "image")
    assert not is_allowed("photo", "audio") and not is_allowed("photo", "video")
    assert not is_allowed("audio", "image") and is_allowed("track", "tracks")
    assert library_for("photo", "auto") == "image"
    assert library_for("video", "auto") is None  # sin clasificar
    assert library_for("track", "auto") == "tracks"
    assert library_for("video", "image") == "image" and library_for("video", "video") == "video"
    for bad in ("Música", None, 3, "photo"):
        try:
            validate_folder_content(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} debería rechazarse")
    assert parent_folder("a/b/c.jpg") == "a/b" and parent_folder("c.jpg") == ""
    assert _ancestors("a/b") == ["a/b", "a", ""] and _ancestors("") == [""]
    print("1. Reglas de catalogación y biblioteca")

    # 2. Herencia (sin base de datos)
    resolver = FolderContentResolver({"Musica": "audio", "Musica/Bandas sonoras/Clips": "image"})
    assert resolver.content_of("") == "auto"
    assert resolver.content_of("Fotos/2024") == "auto"
    assert resolver.content_of("Musica") == "audio"
    assert resolver.content_of("Musica/Rock/AC DC") == "audio"
    assert resolver.content_of("Musica/Bandas sonoras/Clips/x") == "image"
    assert resolver.content_of("Musicas") == "auto"  # 'Musicas' no está dentro de 'Musica'
    assert resolver.inherited_content("Musica") == "auto"
    assert resolver.inherited_content("Musica/Rock") == "audio"
    print("2. Herencia: manda la declaración más profunda")

    # 3. Declaraciones en la base de datos
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "Biblioteca"
        (root / "Musica" / "Rock").mkdir(parents=True)
        (root / "Fotos").mkdir()
        db = sqlite3.connect(":memory:")
        configure_connection(db)
        apply_migrations(db)
        db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('B', ?)", (str(root),))

        assert folder_content_for(db, root / "Musica") == "auto"
        assert set_folder_content(db, 1, "Musica", "audio") is True
        assert set_folder_content(db, 1, "Musica", "audio") is False  # sin cambios
        assert folder_content_for(db, root / "Musica" / "Rock") == "audio"
        assert folder_content_for(db, root / "Fotos") == "auto"
        # Declarar lo mismo que se hereda no guarda nada
        assert set_folder_content(db, 1, "Musica/Rock", "audio") is False
        assert db.execute("SELECT COUNT(*) FROM folder_libraries").fetchone()[0] == 1
        # Una subcarpeta puede volver a "auto" dentro de una carpeta declarada
        assert set_folder_content(db, 1, "Musica/Rock", "auto") is True
        assert folder_content_for(db, root / "Musica" / "Rock") == "auto"
        # ...y al volver a heredar, su fila desaparece
        set_folder_content(db, 1, "Musica/Rock", "audio")
        assert db.execute("SELECT folder FROM folder_libraries").fetchall() == [("Musica",)]
        # Carpeta fuera del catálogo o inexistente: "auto"
        assert folder_content_for(db, Path(tmp)) == "auto"
        assert folder_content_for(db, root / "no_existe") == "auto"
        try:
            set_folder_content(db, 1, "Fotos", "fotos")
        except ValueError:
            pass
        else:
            raise AssertionError("debería rechazar un tipo desconocido")
        # Al borrar la ubicación se borran sus declaraciones
        db.execute("DELETE FROM storage_locations")
        assert db.execute("SELECT COUNT(*) FROM folder_libraries").fetchone()[0] == 0
        db.close()
    print("3. Declaraciones en la base de datos")

    # 4. Detección de vídeos por el nombre
    cases = {
        "IMG_1234.MOV": "image", "VID_20240101_120000.mp4": "image", "PXL_20231231.mp4": "image",
        "DJI_0001.MP4": "image", "GX010123.MP4": "image", "GOPR0042.MP4": "image",
        "MVI_0001.MOV": "image", "C0001.MP4": "image", "20240101_120000.mp4": "image",
        "VID-20240101-WA0001.mp4": "image", "00001.MTS": "image", "clip.m2ts": "image",
        "Breaking Bad S01E02 720p.mkv": "video", "serie.1x02.avi": "video",
        "Origen (2010).mkv": "video", "Pelicula.1080p.BluRay.x264.mkv": "video",
        "Pelicula [2019].mp4": "video", "Boda.mp4": None, "vacaciones playa.mov": None,
        "IMG_2010.MOV": "image",  # un número no es un año entre paréntesis
        "sin_extension": None, "mixes1e2.mp4": None,  # 's1e2' dentro de una palabra no cuenta
    }  # fmt: skip
    for name, expected in cases.items():
        assert guess_video_library(name) == expected, (name, guess_video_library(name))
    assert library_for("video", "auto", "IMG_1.MOV") == "image"
    assert library_for("video", "image", "Serie S01E01.mkv") == "image"  # manda la carpeta
    assert CLASSIFIABLE_MEDIA_TYPES == {"video"}
    # Con metadatos: el nombre manda; luego cámara o GPS; luego la duración
    assert classify_video("Pelicula S01E01.mp4", has_camera=True) == "video"
    assert classify_video("boda.mp4", has_camera=True) == "image"
    assert classify_video("boda.mp4", has_gps=True, duration=9000) == "image"
    assert classify_video("documental.mkv", duration=MOVIE_MIN_DURATION_S) == "video"
    assert classify_video("documental.mkv", duration=MOVIE_MIN_DURATION_S - 1) is None
    assert classify_video("sin datos.mp4") is None
    print("4. Detección de vídeos por el nombre y por los metadatos")

    # 5. Corrección manual, "Detectar automáticamente" y vídeos sin clasificar
    with tempfile.TemporaryDirectory() as tmp:
        db = sqlite3.connect(":memory:")
        configure_connection(db)
        apply_migrations(db)
        db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('B', ?)", (tmp,))
        items = (("Viajes/boda.mp4", "video", None), ("Viajes/IMG_1.MOV", "video", None),
                 ("Viajes/a.jpg", "photo", "image"), ("Pelis/x.mkv", "video", "video"))  # fmt: skip
        for path, media_type, library in items:
            db.execute(
                """INSERT INTO media_items(storage_location_id, relative_path, file_name,
                       media_type, mime_type, file_size, file_mtime_ns, title, library)
                   VALUES (1, ?, ?, ?, 'x', 1, 0, 't', ?)""",
                (path, path.rpartition("/")[2], media_type, library),
            )
        set_folder_content(db, 1, "Pelis", "video")
        ids = dict(db.execute("SELECT relative_path, id FROM media_items"))

        def library_of(path: str) -> tuple:
            return db.execute(
                "SELECT library, library_manual FROM media_items WHERE relative_path = ?", (path,)
            ).fetchone()

        assert count_unclassified(db, 1, "") == 2 and count_unclassified(db, 1, "Viajes") == 2
        assert count_unclassified(db, 1, "Pelis") == 0
        # Al abrir: se clasifica el que lo dice su nombre; el otro sigue sin clasificar
        assert classify_pending_videos(db) == 1
        assert library_of("Viajes/IMG_1.MOV") == ("image", 0)
        assert library_of("Viajes/boda.mp4") == (None, 0)
        # Tras leer sus metadatos (cámara del móvil), también se clasifica
        db.execute("INSERT INTO video_details(media_id, camera_make) VALUES (?, 'Apple')",
                   (ids["Viajes/boda.mp4"],))
        assert classify_pending_videos(db) == 1
        assert library_of("Viajes/boda.mp4") == ("image", 0)
        db.execute("UPDATE media_items SET library = NULL WHERE relative_path = 'Viajes/boda.mp4'")
        db.execute("DELETE FROM video_details")
        # Corrección manual: la boda es de Imagen; la foto no puede ir a Vídeo
        boda, foto, peli = ids["Viajes/boda.mp4"], ids["Viajes/a.jpg"], ids["Pelis/x.mkv"]
        assert set_library(db, [boda, foto], "image") == {boda: ("image", 1)}
        assert library_of("Viajes/boda.mp4") == ("image", 1)
        assert set_library(db, [foto], "video") == {}
        assert set_library(db, [boda], "image") == {}  # ya estaba así
        # Una película de la carpeta de películas, a mano a Imagen; después, a automática
        assert set_library(db, [peli], "image") == {peli: ("image", 1)}
        assert set_library(db, [peli, boda], None) == {peli: ("video", 0), boda: (None, 0)}
        assert library_of("Pelis/x.mkv") == ("video", 0)  # vuelve a mandar la carpeta
        assert library_of("Viajes/boda.mp4") == (None, 0)  # su nombre no dice nada
        try:
            set_library(db, [1], "fotos")
        except ValueError:
            pass
        else:
            raise AssertionError("debería rechazar una biblioteca desconocida")
        db.close()
    print("5. Corrección manual y vídeos sin clasificar")
    print("Autoprueba finalizada correctamente.")
