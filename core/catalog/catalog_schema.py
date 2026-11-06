"""Esquema SQL del catálogo, migraciones y configuración común de las conexiones SQLite.

Contiene:
    - MIGRATIONS: scripts SQL ordenados; cada uno lleva el catálogo de la versión
      N-1 a la N (el primero crea el esquema inicial completo).
    - SCHEMA_VERSION: versión actual del esquema (= número de migraciones). Se
      guarda dentro de cada catálogo en 'PRAGMA user_version'.
    - APPLICATION_ID: marca de los catálogos de esta aplicación ('PRAGMA application_id').
    - apply_migrations(): aplica a un catálogo las migraciones que le falten.
    - configure_connection(): PRAGMAs que hay que aplicar en cada conexión nueva.

Cómo añadir un campo (o una tabla) que se nos haya olvidado:
    1. Añadir UNA migración nueva AL FINAL de MIGRATIONS. Nunca editar las
       anteriores: los catálogos ya creados las aplicaron tal cual.
    2. SCHEMA_VERSION sube sola; no hay que tocarla.
    3. Si el campo se extrae del propio archivo, subir la versión del extractor
       del escáner: el reescaneo solo procesará las filas con 'scan_version'
       menor, rellenando únicamente lo nuevo.
    Limitaciones de 'ALTER TABLE ... ADD COLUMN' en SQLite: una columna NOT NULL
    necesita un DEFAULT constante, y no admite DEFAULT CURRENT_TIMESTAMP (para
    columnas de fecha nuevas: dejarlas NULL y rellenarlas con el reescaneo).

Los datos específicos de cada tipo (EXIF de una foto, códec de un vídeo, álbum
de una canción...) van en tablas 1:1 con 'media_items' (photo_details,
video_details, audio_details...), no en la tabla general. Las que falten se
añadirán como migraciones nuevas, una por una.

2.0.0 Esquema consolidado: las 17 migraciones de la fase de pruebas pasan a ser una sola
      (v1), con cada columna en su sitio lógico. 'APPLICATION_ID' marca los catálogos de
      la aplicación; los anteriores no se migran (los rechaza 'open_catalog').
1.17.1 La función SQL de texto sin mayúsculas ni acentos pasa a llamarse 'arca_fold'
       (antes 'emc_fold'). Se registra en cada conexión: no está guardada en el catálogo.
1.17.0 Migración 17: 'keywords.last_used_at' (palabras recientes del inspector).
1.13.0 Migración 13: objetivo en 'video_details' ('lens_model', 'focal_length_35mm', 'f_number').
1.12.0 Migración 12: tabla 'video_details' (cámara, software, códec, fotogramas por segundo).
1.11.0 Migración 11: 'media_items.library_manual' (biblioteca corregida a mano).
1.10.0 Migración 10: bibliotecas ('media_items.library') y tipo de contenido de las
       carpetas ('folder_libraries').
1.9.0 Migración 9: columna 'media_items.in_quick_selection' (selección rápida).
1.8.0 'configure_connection' registra la función SQL 'emc_fold' (texto sin mayúsculas ni
      acentos, para las reglas de las colecciones inteligentes) y se añade 'fold_text'.
1.7.0 Migración 8: colecciones del usuario ('collections' y 'collection_items').
1.6.0 Migración 7: tabla 'track_details' (tracks GPS: distancia, desnivel, fechas...).

Prueba rápida (desde la raíz del proyecto):
    python -m core.catalog.catalog_schema
"""

__version__ = "2.0.0"
__all__ = [
    "APPLICATION_ID",
    "BUSY_TIMEOUT_SECONDS",
    "FOLD_SQL_FUNCTION",
    "MIGRATIONS",
    "SCHEMA_VERSION",
    "SchemaVersionError",
    "apply_migrations",
    "configure_connection",
    "fold_text",
]

# Librerías estándar
import sqlite3
import unicodedata

# Segundos que una conexión espera si otra tiene la base de datos bloqueada
# (en modo WAL solo puede escribir una conexión a la vez; las demás esperan).
BUSY_TIMEOUT_SECONDS: float = 20.0


class SchemaVersionError(RuntimeError):
    """El catálogo fue creado por una versión MÁS NUEVA de la aplicación.

    Esta versión del programa no conoce su esquema, así que no debe abrirlo ni
    modificarlo (podría corromper datos). Hay que actualizar la aplicación.
    """


# =============================================================================
# Migración 1: esquema inicial
# =============================================================================
# Consolidado el 05/11/2026: reúne las 17 migraciones de la fase de pruebas (cada
# columna, en su sitio lógico). Los catálogos anteriores no se migran: se rechazan al
# abrirlos (no llevan 'APPLICATION_ID'; ver 'catalog_opener.py') y se crean de nuevo.
#
# Convenciones del esquema:
#   - Fechas de registro: texto UTC 'YYYY-MM-DD HH:MM:SS' (formato de CURRENT_TIMESTAMP).
#     Excepciones: 'file_mtime_ns' (entero, nanosegundos, igual que os.stat) y
#     'content_created_at' (hora LOCAL del contenido, sin zona horaria: el EXIF
#     tampoco la trae; el desfase, si se conoce, va en 'timezone_offset').
#   - Booleanos: INTEGER 0/1.
#   - 'relative_path' siempre con '/' como separador (también en Windows), para
#     que el catálogo sea portable entre sistemas.
#   - Valores como media_type, library o color_label NO llevan CHECK en SQL: se validan
#     en Python, así añadir un tipo o un color nuevo no obliga a reconstruir la tabla.
#   - Los datos propios de cada tipo (EXIF de una foto, códec de un vídeo...) van en
#     tablas 1:1 con 'media_items' (photo_details, video_details, track_details...),
#     con la misma clave ('media_id') y ON DELETE CASCADE.
#
# Propietario de cada columna de 'media_items' (clave para los reescaneos; tabla
# completa en docs/MODELO_DE_DATOS.md):
#   - BLOQUE A (archivo en disco) y BLOQUE B (metadatos extraídos): los escribe
#     el escáner y un reescaneo puede sobrescribirlos.
#   - BLOQUE C (datos del usuario): el escáner NUNCA los toca. El INSERT ... ON
#     CONFLICT DO UPDATE del escáner debe nombrar solo columnas de los bloques A y B.
#   - BLOQUE D (caché y control interno): los gestionan el generador de miniaturas,
#     el escáner y el trabajo de escritura de los datos del usuario.
#   - BLOQUE E (marcas de trabajo): solo viven en el catálogo.
_MIGRATION_001_INITIAL_SCHEMA = """
-- =============================================================================
-- 1. Ubicaciones, elementos y errores
-- =============================================================================

-- Carpetas raíz / bibliotecas. Si cambia la letra de unidad o el punto de montaje,
-- solo hay que actualizar 'absolute_path' aquí: los elementos guardan rutas relativas
-- a esta carpeta.
CREATE TABLE storage_locations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    absolute_path       TEXT NOT NULL UNIQUE,
    default_media_type  TEXT,                 -- valor de MediaType
    is_online           INTEGER NOT NULL DEFAULT 1 CHECK(is_online IN (0, 1)),
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Tabla general: solo datos comunes a cualquier tipo de archivo.
CREATE TABLE media_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_location_id     INTEGER NOT NULL,

    -- ===== BLOQUE A · Archivo en disco (el escáner lo actualiza siempre) =====
    relative_path           TEXT NOT NULL,    -- relativa a storage_locations.absolute_path
    file_name               TEXT NOT NULL,    -- con extensión (p. ej. DSC01234.JPG)
    file_extension          TEXT,             -- normalizada: minúsculas y sin punto (jpg, mp4, epub...)
    media_type              TEXT NOT NULL,    -- valor de MediaType (validado en Python)
    mime_type               TEXT NOT NULL,
    file_size               INTEGER NOT NULL, -- bytes
    file_mtime_ns           INTEGER NOT NULL, -- st_mtime_ns; junto con file_size detecta que el archivo cambió
    file_created_at         TEXT,             -- creación según el sistema (último recurso para ordenar)
    hash_partial            TEXT,             -- hash rápido (primeros y últimos KB); NULL hasta calcularlo
    hash_full               TEXT,             -- hash completo; NULL hasta calcularlo (es lento)
    hash_verified_at        TEXT,             -- cuándo se calculó/verificó hash_full (control de bit rot)
    is_missing              INTEGER NOT NULL DEFAULT 0 CHECK(is_missing IN (0, 1)),  -- 1 si el archivo ya no existe
    -- Fecha de modificación del sidecar .xmp cuando se leyó (la más reciente si hay dos;
    -- NULL = sin sidecar). Si otro programa (Lightroom) cambia el sidecar de un RAW, el
    -- RAW no cambia: así el escáner se entera y vuelve a leer los metadatos.
    sidecar_mtime_ns        INTEGER,

    -- ===== BLOQUE B · Metadatos extraídos del archivo (un reescaneo puede sobrescribirlos) =====
    title                   TEXT NOT NULL,    -- por defecto, el nombre sin extensión
    creator                 TEXT,             -- autor, artista, fotógrafo, director...
    description             TEXT,             -- sinopsis, pie de foto... (las notas propias van en user_notes)
    language                TEXT,             -- código BCP 47 (es, en-US...)
    copyright               TEXT,
    intellectual_genre      TEXT,             -- género intelectual (IPTC)
    scene                   TEXT,             -- escena (códigos IPTC)
    has_xmp_sidecar         INTEGER NOT NULL DEFAULT 0
        CHECK(has_xmp_sidecar IN (0, 1)),     -- 1 si hay un archivo .xmp junto al original

    -- Línea de tiempo
    content_created_at      TEXT,             -- 'YYYY-MM-DD HH:MM:SS' hora local; si solo se conoce el año o el mes se completa con 01/00
    content_date_precision  TEXT CHECK(content_date_precision IN ('year', 'month', 'day', 'second')),
    content_date_source     TEXT,             -- de dónde salió la fecha: 'exif', 'id3', 'epub', 'filename', 'file_mtime'...
    timezone_offset         TEXT,             -- ISO 8601, p. ej. '+02:00'
    iptc_created_at         TEXT,             -- "Fecha de creación" de IPTC/XMP

    -- Métricas (se guardan aquí para no hacer JOIN al pintar el grid)
    width                   INTEGER,          -- píxeles, YA rotados según 'orientation' (proporción real de la miniatura)
    height                  INTEGER,
    orientation             INTEGER NOT NULL DEFAULT 1 CHECK(orientation BETWEEN 1 AND 8),  -- código EXIF: 1 normal, 3 = 180°, 6 = 90° horario, 8 = 270° horario
    duration                REAL,             -- segundos (vídeo/audio/audiolibros)
    page_count              INTEGER,          -- ebooks y PDFs

    -- Geolocalización (los nombres, como los escriben Lightroom y otros programas en XMP/IPTC)
    latitude                REAL CHECK(latitude  BETWEEN  -90 AND  90),
    longitude               REAL CHECK(longitude BETWEEN -180 AND 180),
    altitude                REAL,             -- metros sobre el nivel del mar
    country_code            TEXT,             -- ISO 3166-1 alfa-2 (ES, FR...) para filtrar por lugar
    country                 TEXT,             -- nombre del país
    region                  TEXT,
    city                    TEXT,
    sublocation             TEXT,             -- ubicación secundaria (calle, paraje...)
    location_name           TEXT,             -- texto legible para mostrar

    -- ===== Biblioteca: qué módulo gestiona el elemento =====
    -- 'image', 'video', 'audio', 'ebook', 'tracks'; NULL = sin clasificar. Es distinta de
    -- 'media_type' (tipo técnico): un vídeo del móvil es de 'image'; una película, de
    -- 'video'. La escribe el escáner ('add_folder') según el tipo de contenido de la
    -- carpeta (ver core/catalog/libraries.py), salvo que el usuario la haya elegido a mano.
    library                 TEXT,
    -- 1 = biblioteca elegida a mano (menú "Biblioteca" de la cuadrícula): ni el escáner
    -- ('save_candidates') ni la detección automática la cambian; "Detectar
    -- automáticamente" la vuelve a 0. Vive SOLO en el catálogo (decisión del 29/10/2026:
    -- si hiciera falta que sobreviva a recrearlo, iría en el '.arca.json').
    library_manual          INTEGER NOT NULL DEFAULT 0 CHECK(library_manual IN (0, 1)),

    -- ===== BLOQUE C · Datos del usuario (el escáner NUNCA los toca) =====
    rating                  INTEGER NOT NULL DEFAULT 0 CHECK(rating BETWEEN 0 AND 5),
    flag                    INTEGER NOT NULL DEFAULT 0 CHECK(flag IN (-1, 0, 1)),  -- -1 rechazado, 0 sin marca, 1 aceptado
    color_label             TEXT,             -- etiqueta de color (NULL = sin etiqueta; validado en Python)
    is_favorite             INTEGER NOT NULL DEFAULT 0 CHECK(is_favorite IN (0, 1)),
    is_archived             INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0, 1)),
    user_notes              TEXT,             -- notas propias del usuario (distintas de 'description')
    play_count              INTEGER NOT NULL DEFAULT 0,
    last_played_at          TEXT,

    -- ===== BLOQUE D · Caché y control interno =====
    -- Miniaturas. La ruta NO se guarda: se calcula a partir del id (carpeta
    -- cache/<media_type>/...). Un archivo está "pendiente" si thumbnail_status = 0, si
    -- su thumbnail_version es menor que la actual o si thumbnail_mtime_ns no coincide
    -- con file_mtime_ns (ver core/thumbnails/job.py).
    thumbnail_status        INTEGER NOT NULL DEFAULT 0 CHECK(thumbnail_status IN (0, 1, 2)),  -- 0 pendiente, 1 lista, 2 error
    thumbnail_mtime_ns      INTEGER,          -- file_mtime_ns del archivo cuando se generó (si cambia, hay que regenerarla)
    -- Versión del motor que generó los archivos (THUMBNAIL_VERSION de
    -- core/thumbnails/generator.py; 0 = nunca): al subir la constante, se regeneran
    thumbnail_version       INTEGER NOT NULL DEFAULT 0,
    -- Origen que entregó la imagen de partida ('pillow', 'heif', 'raw_preview:PreviewImage'...):
    -- para diagnosticar y, más adelante, regenerar solo lo que salió de un origen mejorable
    thumbnail_source        TEXT,
    scan_version            INTEGER NOT NULL DEFAULT 0,  -- versión del extractor que rellenó esta fila (0 = nunca)
    last_scanned_at         TEXT,
    -- Datos del usuario aún no escritos en su destino (XMP, sidecar o '.arca.json'; ver
    -- core/userdata/), UN BIT POR CAMPO: 1 = rating, 2 = flag, 4 = color_label (0 = nada
    -- pendiente). Lo pone 'update_user_field' (solo el bit del campo que cambia) y lo
    -- quita el trabajo de escritura (core/userdata/sync.py) cuando el destino ya tiene ese
    -- valor. Mientras un bit está puesto, lo que se lea de los archivos NO pisa ESE campo
    -- (el cambio del usuario es más nuevo), pero sí los demás; y al escribir solo se tocan
    -- los campos pendientes (no se borra, p. ej., una valoración puesta en Lightroom
    -- porque en la aplicación se haya cambiado el color).
    user_data_pending       INTEGER NOT NULL DEFAULT 0 CHECK(user_data_pending BETWEEN 0 AND 7),
    -- 1 = las palabras clave del catálogo aún no están en el archivo (XMP o '.arca.json'):
    -- hasta escribirlas, lo que se lea del archivo no las pisa (core/userdata/sync.py).
    -- Va aparte de 'user_data_pending' porque las palabras se escriben siempre todas juntas.
    keywords_pending        INTEGER NOT NULL DEFAULT 0 CHECK(keywords_pending IN (0, 1)),
    added_at                TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- ===== BLOQUE E · Marcas de trabajo (solo en el catálogo) =====
    -- 1 = en la "Selección rápida" (la "Colección rápida" de Lightroom): el círculo de la
    -- esquina de la tarjeta. No se escribe en los archivos (no tiene bit en
    -- 'user_data_pending'). Es una columna, y no una colección más, porque la cuadrícula
    -- la necesita en cada tarjeta: así viene en la misma consulta, sin JOIN.
    in_quick_selection      INTEGER NOT NULL DEFAULT 0 CHECK(in_quick_selection IN (0, 1)),

    FOREIGN KEY (storage_location_id) REFERENCES storage_locations(id) ON DELETE CASCADE,
    -- Este UNIQUE ya crea un índice por (storage_location_id, relative_path),
    -- por eso no hace falta otro índice solo por storage_location_id.
    UNIQUE (storage_location_id, relative_path)
);

-- Índices para filtrar y ordenar rápido en la interfaz. Más índices = ingesta más
-- lenta: se añadirán (con una migración) cuando se midan consultas lentas.
--    Filtrar por tipo y ordenar por título (la consulta más habitual del grid)
CREATE INDEX idx_media_type_title ON media_items(media_type, title COLLATE NOCASE);
--    Filtrar por tipo y ordenar por fecha del contenido
CREATE INDEX idx_media_type_content_date ON media_items(media_type, content_created_at);
--    Filtrar por biblioteca y ordenar por fecha de captura (la línea de tiempo de los módulos)
CREATE INDEX idx_media_library_date ON media_items(library, content_created_at);
--    Detectar duplicados: primero candidatos por hash rápido + tamaño, luego hash completo
CREATE INDEX idx_media_partial_hash ON media_items(hash_partial, file_size) WHERE hash_partial IS NOT NULL;
CREATE INDEX idx_media_full_hash ON media_items(hash_full) WHERE hash_full IS NOT NULL;
--    Índices PARCIALES: solo contienen las pocas filas marcadas, así que ocupan muy poco
--    y contar o listar esas filas no recorre todo el catálogo
CREATE INDEX idx_media_favorite ON media_items(is_favorite) WHERE is_favorite = 1;
CREATE INDEX idx_media_user_data_pending ON media_items(id) WHERE user_data_pending <> 0;
CREATE INDEX idx_media_keywords_pending ON media_items(id) WHERE keywords_pending <> 0;
CREATE INDEX idx_media_items_quick_selection ON media_items(id) WHERE in_quick_selection = 1;

-- Actualiza 'updated_at' automáticamente en cada modificación.
-- (SQLite no ejecuta triggers de forma recursiva por defecto, así que este UPDATE
-- interno no vuelve a disparar el trigger.)
CREATE TRIGGER trg_media_items_updated_at
AFTER UPDATE ON media_items
FOR EACH ROW
BEGIN
    UPDATE media_items SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

-- Archivos que no se pudieron leer (no llegan a 'media_items'). Una fila por archivo y
-- fase: si se vuelve a escanear y falla otra vez se actualiza la fila existente; si por
-- fin funciona, el escáner la borra.
CREATE TABLE scan_errors (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_location_id  INTEGER NOT NULL,
    relative_path        TEXT NOT NULL,
    stage                TEXT NOT NULL,       -- fase que falló: 'metadata', 'thumbnail'...
    message              TEXT NOT NULL,
    occurred_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (storage_location_id) REFERENCES storage_locations(id) ON DELETE CASCADE,
    UNIQUE (storage_location_id, relative_path, stage)
);

-- Qué contiene cada carpeta según el usuario ("¿Qué contiene esta carpeta?" al
-- añadirla): 'auto' o una biblioteca. Vale para la carpeta y sus subcarpetas (manda la
-- declaración más profunda); sin fila = 'auto'. Se borra con su ubicación.
CREATE TABLE folder_libraries (
    storage_location_id  INTEGER NOT NULL,
    folder               TEXT NOT NULL,       -- relativa a la ubicación, con '/' ('' = su raíz)
    content              TEXT NOT NULL,       -- 'auto' o una biblioteca (validado en Python)
    updated_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (storage_location_id, folder),
    FOREIGN KEY (storage_location_id) REFERENCES storage_locations(id) ON DELETE CASCADE
) WITHOUT ROWID;

-- =============================================================================
-- 2. Detalles por tipo (1:1 con 'media_items')
-- =============================================================================

-- Fotos (EXIF y campos de los paneles "EXIF" y "Ubicación" de Lightroom). Las rellena
-- la lista de campos de imagen (core/metadata/image/fields.py).
CREATE TABLE photo_details (
    media_id            INTEGER PRIMARY KEY,
    camera_make         TEXT,               -- fabricante ('Canon')
    camera_model        TEXT,               -- modelo ('Canon EOS R5')
    body_serial_number  TEXT,
    lens_model          TEXT,
    focal_length_mm     REAL,
    focal_length_35mm   REAL,               -- equivalente en formato de 35 mm
    f_number            REAL,               -- apertura (2.8)
    exposure_time_s     REAL,               -- segundos (1/250 = 0.004)
    iso                 INTEGER,
    exposure_bias_ev    REAL,               -- compensación de exposición
    brightness_value    REAL,               -- valor de brillo (APEX)
    exposure_program    INTEGER,            -- código EXIF: 2 = normal...
    metering_mode       INTEGER,            -- código EXIF: 5 = matricial...
    flash_fired         INTEGER CHECK(flash_fired IN (0, 1)),  -- NULL = no consta
    flash_code          INTEGER,            -- código EXIF completo del flash
    software            TEXT,
    user_comment        TEXT,
    gps_direction       REAL,               -- grados 0-360 (hacia dónde apunta)
    digitized_at        TEXT,               -- EXIF "fecha y hora digitalizadas"
    exif_modified_at    TEXT,               -- EXIF "fecha y hora" (modificación)
    -- «Dimensiones actuales» de Lightroom: se calculan al leer la foto a partir de los
    -- ajustes de revelado del XMP ('crs:Crop*', ver core/metadata/image/rules.py). Ya
    -- giradas, como 'width' y 'height' de 'media_items'. NULL = sin recorte (o recorte ya
    -- aplicado a los píxeles).
    crop_width          INTEGER,            -- ancho del recorte (px)
    crop_height         INTEGER,            -- alto del recorte (px)

    FOREIGN KEY (media_id) REFERENCES media_items(id) ON DELETE CASCADE
);
-- Para filtrar por cámara en la interfaz
CREATE INDEX idx_photo_camera ON photo_details(camera_make, camera_model);

-- Vídeos. La rellena el extractor de vídeo (core/metadata/video/). Lo común va en
-- 'media_items': fecha de captura, duración, tamaño (ya girado), GPS. La cámara sirve
-- también para clasificar los vídeos de las carpetas automáticas (con datos de cámara o
-- GPS -> Imagen; ver core/catalog/libraries.py). El objetivo (los iPhone lo guardan en
-- 'Keys'/'VideoKeys') usa los mismos nombres y unidades que en 'photo_details'.
CREATE TABLE video_details (
    media_id           INTEGER PRIMARY KEY,
    camera_make        TEXT,                -- fabricante ('Apple', 'Sony', 'GoPro'...)
    camera_model       TEXT,                -- modelo ('iPhone 15 Pro')
    lens_model         TEXT,                -- objetivo ('iPhone 17 Pro back triple camera 6.765mm f/1.78')
    focal_length_35mm  REAL,                -- focal equivalente en 35 mm (mm)
    f_number           REAL,                -- apertura (1.78 = f/1.78)
    software           TEXT,                -- versión del sistema o programa que lo grabó
    video_codec        TEXT,                -- códec del vídeo ('avc1' = H.264, 'hvc1' = H.265...)
    frame_rate         REAL,                -- fotogramas por segundo

    FOREIGN KEY (media_id) REFERENCES media_items(id) ON DELETE CASCADE
);

-- Tracks GPS (GPX). La rellena el extractor de tracks (core/metadata/track/extractor.py).
-- Lo común va en 'media_items': nombre del track en 'title', hora local de salida en
-- 'content_created_at', punto de salida en 'latitude'/'longitude'/'altitude' y duración
-- en 'duration'. Distancias y altitudes en METROS; fechas de inicio y fin en UTC (como
-- las de registro). La caja geográfica (min/max de latitud y longitud) servirá para el
-- futuro mapa: saber qué tracks se ven en la zona visible, o qué fotos caen dentro.
CREATE TABLE track_details (
    media_id            INTEGER PRIMARY KEY,
    distance_m          REAL,             -- distancia en 2D (suma de los tramos de cada segmento)
    elevation_gain_m    REAL,             -- desnivel acumulado de subida (con umbral anti-ruido)
    elevation_loss_m    REAL,             -- desnivel acumulado de bajada (positivo)
    elevation_min_m     REAL,
    elevation_max_m     REAL,
    started_at          TEXT,             -- hora UTC del primer punto
    ended_at            TEXT,             -- hora UTC del último punto
    point_count         INTEGER,          -- puntos del recorrido
    segment_count       INTEGER,          -- segmentos (pausas del GPS)
    track_count         INTEGER,          -- elementos <trk> del archivo
    route_count         INTEGER,          -- elementos <rte> (rutas planificadas)
    waypoint_count      INTEGER,          -- puntos de interés (<wpt>)
    is_planned_route    INTEGER CHECK(is_planned_route IN (0, 1)),  -- 1 = sin track grabado: se usó la ruta planificada
    min_latitude        REAL CHECK(min_latitude  BETWEEN  -90 AND  90),
    max_latitude        REAL CHECK(max_latitude  BETWEEN  -90 AND  90),
    min_longitude       REAL CHECK(min_longitude BETWEEN -180 AND 180),
    max_longitude       REAL CHECK(max_longitude BETWEEN -180 AND 180),
    end_latitude        REAL CHECK(end_latitude  BETWEEN  -90 AND  90),   -- punto de llegada
    end_longitude       REAL CHECK(end_longitude BETWEEN -180 AND 180),
    activity_type       TEXT,             -- tipo de actividad del GPX ('hiking', 'cycling'...), tal cual
    creator_app         TEXT,             -- programa o dispositivo que creó el archivo

    FOREIGN KEY (media_id) REFERENCES media_items(id) ON DELETE CASCADE
);

-- =============================================================================
-- 3. Palabras clave (árbol jerárquico, como el de Lightroom)
-- =============================================================================
-- 'keywords' es el árbol: cada palabra con su padre (NULL = primer nivel). El nombre
-- normalizado (sin mayúsculas ni acentos, 'fold_text') evita duplicar «Árbol» y «arbol»
-- bajo el mismo padre; la misma palabra puede existir bajo padres distintos («Ana» en
-- Familia y en Amigos). Las palabras se conservan aunque ya no las use ningún archivo
-- (como en Lightroom). 'media_keywords' dice qué palabras tiene asignadas cada archivo:
-- solo la asignada, no sus padres (los padres se deducen del árbol).
-- Son datos del USUARIO (como la valoración): ver core/catalog/keywords.py.
CREATE TABLE keywords (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id          INTEGER,                -- NULL = primer nivel
    name               TEXT NOT NULL,          -- tal como se escribió («Toyota Corolla»)
    name_folded        TEXT NOT NULL,          -- sin mayúsculas ni acentos (para comparar)
    include_on_export  INTEGER NOT NULL DEFAULT 1 CHECK(include_on_export IN (0, 1)),
                                               -- 0 = categoría de Lightroom («[Familia]»)
    synonyms           TEXT,                   -- lista JSON de sinónimos (NULL = ninguno)
    needs_review       INTEGER NOT NULL DEFAULT 0 CHECK(needs_review IN (0, 1)),
                                               -- 1 = palabra suelta con el nombre de otras
                                               --     del árbol: revisar dónde va
    -- Última vez que se asignó DESDE LA INTERFAZ ('keywords.assign_keyword'; no al leerla
    -- de los archivos), para «Últimas palabras clave» del inspector. NULL = nunca
    last_used_at       TEXT,
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (parent_id) REFERENCES keywords(id) ON DELETE CASCADE
);
-- Un mismo nombre solo una vez bajo cada padre (IFNULL: el primer nivel cuenta como
-- padre 0, porque en SQLite dos NULL no se consideran iguales en un índice único)
CREATE UNIQUE INDEX idx_keywords_parent_name ON keywords(IFNULL(parent_id, 0), name_folded);
-- Buscar por nombre en todo el árbol (palabras sueltas, autocompletado)
CREATE INDEX idx_keywords_name ON keywords(name_folded);
-- Palabras recientes (parcial: solo las asignadas alguna vez desde la interfaz)
CREATE INDEX idx_keywords_last_used ON keywords(last_used_at) WHERE last_used_at IS NOT NULL;

CREATE TABLE media_keywords (
    media_id    INTEGER NOT NULL,
    keyword_id  INTEGER NOT NULL,

    PRIMARY KEY (media_id, keyword_id),
    FOREIGN KEY (media_id)   REFERENCES media_items(id) ON DELETE CASCADE,
    FOREIGN KEY (keyword_id) REFERENCES keywords(id)    ON DELETE CASCADE
) WITHOUT ROWID;
-- Archivos de una palabra (árbol con recuentos, colecciones inteligentes)
CREATE INDEX idx_media_keywords_keyword ON media_keywords(keyword_id, media_id);

-- =============================================================================
-- 4. Colecciones del usuario
-- =============================================================================
-- Una sola tabla para los tres tipos (como en Lightroom), en forma de árbol ('parent_id'):
--   - 'set':    conjunto de colecciones (solo agrupa; no contiene archivos).
--   - 'static': colección estática: los archivos que el usuario añade a mano.
--   - 'smart':  colección inteligente: sus reglas, en 'rules_json'.
-- Un conjunto puede contener colecciones y otros conjuntos; una colección solo puede
-- estar dentro de un conjunto (lo comprueba core/catalog/user_collections.py). Al
-- borrar un conjunto se borra todo lo que contiene (ON DELETE CASCADE sobre 'parent_id').
-- Las colecciones viven SOLO en la base de datos (decisión tomada): exportarlas o
-- guardarlas fuera del catálogo queda para más adelante.
CREATE TABLE collections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id   INTEGER,                  -- conjunto que la contiene (NULL = primer nivel)
    kind        TEXT NOT NULL CHECK(kind IN ('set', 'static', 'smart')),
    name        TEXT NOT NULL,
    rules_json  TEXT,                     -- reglas de una colección inteligente
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (parent_id) REFERENCES collections(id) ON DELETE CASCADE
);
CREATE INDEX idx_collections_parent ON collections(parent_id);

-- Qué archivos tiene cada colección estática. Un archivo puede estar en varias; si se
-- quita del catálogo, sale de todas solo (ON DELETE CASCADE). 'position' guarda el orden
-- en que se añadieron (servirá para un orden personalizado).
CREATE TABLE collection_items (
    collection_id  INTEGER NOT NULL,
    media_id       INTEGER NOT NULL,
    position       INTEGER NOT NULL DEFAULT 0,   -- orden en que se añadió
    added_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (collection_id, media_id),       -- un archivo, una vez por colección
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (media_id) REFERENCES media_items(id) ON DELETE CASCADE
) WITHOUT ROWID;
-- Para saber en qué colecciones está un archivo (y para el borrado en cascada)
CREATE INDEX idx_collection_items_media ON collection_items(media_id);
"""

# Lista ORDENADA de migraciones: la posición (empezando en 1) es la versión a la
# que lleva cada una. Para evolucionar el esquema, añadir elementos AL FINAL.
MIGRATIONS: tuple[str, ...] = (_MIGRATION_001_INITIAL_SCHEMA,)

# Versión actual del esquema: se deduce sola del número de migraciones, así no
# hay que acordarse de subirla a mano.
SCHEMA_VERSION: int = len(MIGRATIONS)

# Marca de los catálogos de esta aplicación en la cabecera del archivo SQLite ('PRAGMA
# application_id', un entero de 32 bits que SQLite guarda y nunca cambia): son los
# códigos ASCII de "ARCA". La pone 'apply_migrations' al crear el esquema; un catálogo
# con versión pero sin esta marca es de antes de consolidar las migraciones (05/11/2026)
# o de otra aplicación, y 'open_catalog' lo rechaza.
APPLICATION_ID: int = 0x41524341


# Nombre de la función SQL que pasa un texto a minúsculas y sin acentos (ver 'fold_text')
FOLD_SQL_FUNCTION = "arca_fold"


def fold_text(text: object) -> str | None:
    """Texto sin mayúsculas ni acentos, para comparar ('Cañón' -> 'canon').

    Es la función que SQLite ejecuta como 'arca_fold(columna)'. 'LIKE' y 'NOCASE' solo
    ignoran las mayúsculas de las letras inglesas: con esto, 'ordesa' encuentra 'ORDESA'
    y 'anisclo' encuentra 'Añisclo'.

    Args:
        text: Valor de la columna (None se queda en None; un número se pasa a texto).
    """
    if text is None:
        return None
    decomposed = unicodedata.normalize("NFD", str(text))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def configure_connection(conn: sqlite3.Connection) -> None:
    """Aplica a una conexión los PRAGMAs que SQLite NO recuerda entre conexiones.

    Debe llamarse justo después de cada 'sqlite3.connect()'.

    Nota: 'journal_mode = WAL' no se pone aquí porque sí se guarda dentro del
    archivo .db: basta con activarlo una vez al crear el catálogo.

    Args:
        conn: Conexión recién abierta.
    """
    # Hace que SQLite respete las claves foráneas (por defecto las ignora)
    conn.execute("PRAGMA foreign_keys = ON;")
    # NORMAL es el equilibrio recomendado con WAL: rápido y seguro ante cierres
    # de la aplicación (solo se podría perder la última transacción si se va la luz)
    conn.execute("PRAGMA synchronous = NORMAL;")
    # Funciones propias (tampoco se guardan en el archivo): texto sin mayúsculas ni acentos
    conn.create_function(FOLD_SQL_FUNCTION, 1, fold_text, deterministic=True)


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Lleva el catálogo a la versión actual aplicando las migraciones pendientes.

    - Catálogo vacío (user_version = 0): aplica todas, creando el esquema completo, y
      pone la marca 'APPLICATION_ID' en la misma transacción que la primera.
    - Catálogo al día: no hace nada.
    - Catálogo más antiguo: aplica solo las que le faltan.

    Cada migración es ATÓMICA: el script y el cambio de 'user_version' van dentro
    de la misma transacción, así que si algo falla no queda nada a medias.

    Debe llamarse una sola vez al abrir el catálogo, ANTES de que el gestor
    asíncrono empiece a lanzar consultas (hay que evitar migrar con varios hilos).

    Args:
        conn: Conexión ya configurada con 'configure_connection()'.

    Returns:
        La versión del esquema con la que queda el catálogo.

    Raises:
        SchemaVersionError: Si el catálogo es de una versión más nueva que la de
            esta aplicación.
        sqlite3.Error: Si falla alguna migración (se deshace y se vuelve a lanzar).
    """
    current_version: int = conn.execute("PRAGMA user_version;").fetchone()[0]

    if current_version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"El catálogo usa el esquema v{current_version}, pero esta versión de "
            f"la aplicación solo conoce hasta la v{SCHEMA_VERSION}. "
            "Actualiza la aplicación para poder abrirlo."
        )

    for version in range(current_version + 1, SCHEMA_VERSION + 1):
        script = MIGRATIONS[version - 1]
        # Al crear el esquema se marca el archivo como catálogo de esta aplicación
        mark = f"PRAGMA application_id = {APPLICATION_ID};\n" if version == 1 else ""
        try:
            # 'executescript' no admite parámetros, y PRAGMA tampoco: por eso 'version'
            # se inserta con f-string (es un entero generado por nosotros: seguro).
            conn.executescript(
                f"BEGIN;\n{script}\n{mark}PRAGMA user_version = {version};\nCOMMIT;"
            )
        except sqlite3.Error:
            conn.rollback()  # Deshace la migración a medias (y la versión)
            raise

    return SCHEMA_VERSION


if __name__ == "__main__":
    # Autoprueba con una base de datos en memoria (no toca el disco).
    # Ejecutar desde la raíz del proyecto:  python -m core.catalog.catalog_schema

    def tables_of(conn: sqlite3.Connection) -> set[str]:
        """Nombres de las tablas propias (sin las internas de SQLite)."""
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in rows}

    def columns_of(conn: sqlite3.Connection, table: str) -> set[str]:
        """Nombres de las columnas de una tabla."""
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def rejected(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> bool:
        """True si la sentencia choca con una restricción (CHECK, UNIQUE, NOT NULL...)."""
        try:
            conn.execute(sql, params)
        except sqlite3.IntegrityError:
            return True
        return False

    db = sqlite3.connect(":memory:")
    configure_connection(db)

    # 1. Un catálogo vacío pasa de la versión 0 a la actual, con la marca de la aplicación
    assert db.execute("PRAGMA user_version").fetchone()[0] == 0
    assert apply_migrations(db) == SCHEMA_VERSION == 1
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert db.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
    print(f"Esquema creado: v{SCHEMA_VERSION}, application_id = {APPLICATION_ID:#x}")

    # 2. Aplicar las migraciones otra vez no hace nada ni da error
    apply_migrations(db)

    # 3. Un catálogo de una versión más nueva se rechaza sin tocarlo
    newer = sqlite3.connect(":memory:")
    newer.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    try:
        apply_migrations(newer)
    except SchemaVersionError as error:
        print("Versión más nueva rechazada:", str(error).split(".")[0])
    else:
        raise AssertionError("debería rechazar un catálogo más nuevo")
    assert tables_of(newer) == set()
    newer.close()

    # 4. Están todas las tablas
    expected_tables = {
        "storage_locations", "media_items", "scan_errors", "folder_libraries",
        "photo_details", "video_details", "track_details", "keywords",
        "media_keywords", "collections", "collection_items",
    }  # fmt: skip
    assert tables_of(db) == expected_tables, tables_of(db) ^ expected_tables
    print("Tablas:", ", ".join(sorted(expected_tables)))

    # 5. 'media_items': los valores por defecto de una fila con lo mínimo obligatorio
    db.execute("INSERT INTO storage_locations(name, absolute_path) VALUES ('Prueba', '/p')")
    db.execute(
        """INSERT INTO media_items(storage_location_id, relative_path, file_name,
               media_type, mime_type, file_size, file_mtime_ns, title)
           VALUES (1, 'a/foto.jpg', 'foto.jpg', 'photo', 'image/jpeg', 1234, 0, 'foto')"""
    )
    defaults = db.execute(
        """SELECT rating, flag, orientation, is_missing, has_xmp_sidecar, library,
                  library_manual, thumbnail_status, thumbnail_version, thumbnail_source,
                  scan_version, user_data_pending, keywords_pending, in_quick_selection
             FROM media_items"""
    ).fetchone()
    assert defaults == (0, 0, 1, 0, 0, None, 0, 0, 0, None, 0, 0, 0, 0), defaults
    print("Valores por defecto de media_items: correctos")

    # 6. Los CHECK rechazan valores imposibles
    for column, value in (
        ("rating", 9), ("flag", 2), ("orientation", 0), ("latitude", 123.0),
        ("longitude", -181.0), ("user_data_pending", 8), ("keywords_pending", 2),
        ("in_quick_selection", 2), ("library_manual", 2), ("has_xmp_sidecar", 2),
        ("content_date_precision", "hour"), ("thumbnail_status", 3),
    ):  # fmt: skip
        assert rejected(db, f"UPDATE media_items SET {column} = ?", (value,)), column
    assert rejected(db, "INSERT INTO collections(kind, name) VALUES ('carpeta', 'x')")
    print("CHECK: valores imposibles rechazados")

    # 7. 'updated_at' se actualiza solo (trigger)
    db.execute("UPDATE media_items SET updated_at = '2000-01-01 00:00:00'")
    db.execute("UPDATE media_items SET rating = 3")
    assert db.execute("SELECT updated_at FROM media_items").fetchone()[0] != "2000-01-01 00:00:00"
    print("Trigger de updated_at: correcto")

    # 8. Los índices parciales se usan (contar lo marcado no recorre todo el catálogo)
    for index, where in (
        ("idx_media_items_quick_selection", "in_quick_selection = 1"),
        ("idx_media_user_data_pending", "user_data_pending <> 0"),
        ("idx_media_keywords_pending", "keywords_pending <> 0"),
    ):
        plan = " ".join(
            str(row[-1])
            for row in db.execute(f"EXPLAIN QUERY PLAN SELECT id FROM media_items WHERE {where}")
        )
        assert index in plan, (index, plan)
    print("Índices parciales: usados")

    # 9. Tablas de detalles: se borran con su elemento (ON DELETE CASCADE) y tienen las
    #    columnas que llegaron con migraciones posteriores en la fase de pruebas
    assert {"crop_width", "crop_height", "digitized_at"} <= columns_of(db, "photo_details")
    assert {"lens_model", "focal_length_35mm", "f_number"} <= columns_of(db, "video_details")
    db.execute("INSERT INTO photo_details(media_id, camera_make) VALUES (1, 'Nikon')")
    db.execute("INSERT INTO video_details(media_id, camera_make) VALUES (1, 'Apple')")
    db.execute("INSERT INTO track_details(media_id, distance_m) VALUES (1, 12345.6)")
    assert rejected(db, "UPDATE track_details SET min_latitude = 95")
    db.execute("INSERT INTO folder_libraries(storage_location_id, folder, content) "
               "VALUES (1, 'Musica', 'audio')")  # fmt: skip
    assert rejected(db, "INSERT INTO folder_libraries(storage_location_id, folder, content) "
                        "VALUES (1, 'Musica', 'video')")  # fmt: skip

    # 10. Palabras clave: un nombre una vez por padre (sin mayúsculas ni acentos) y el
    #     mismo nombre bajo otro padre sí; borrar una palabra borra sus hijas
    root = db.execute("INSERT INTO keywords(name, name_folded) VALUES ('Coche', 'coche')").lastrowid
    assert rejected(db, "INSERT INTO keywords(name, name_folded) VALUES ('COCHE', 'coche')")
    child = db.execute(
        "INSERT INTO keywords(parent_id, name, name_folded) VALUES (?, 'Coche', 'coche')", (root,)
    ).lastrowid
    db.execute("INSERT INTO media_keywords(media_id, keyword_id) VALUES (1, ?)", (child,))
    assert "last_used_at" in columns_of(db, "keywords")
    db.execute("DELETE FROM keywords WHERE id = ?", (root,))
    assert db.execute("SELECT COUNT(*) FROM keywords").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM media_keywords").fetchone()[0] == 0
    print("Palabras clave: unicidad por padre y borrado de las hijas")

    # 11. Colecciones: borrar un conjunto borra lo que contiene, y borrar un elemento del
    #     catálogo lo saca de sus colecciones
    db.execute("INSERT INTO collections(id, kind, name) VALUES (1, 'set', 'Álbumes')")
    db.execute("INSERT INTO collections(id, parent_id, kind, name) VALUES (2, 1, 'static', 'R')")
    db.execute("INSERT INTO collection_items(collection_id, media_id) VALUES (2, 1)")
    db.execute("INSERT INTO keywords(name, name_folded) VALUES ('Playa', 'playa')")
    db.execute("INSERT INTO media_keywords(media_id, keyword_id) VALUES (1, last_insert_rowid())")
    db.execute("DELETE FROM media_items WHERE id = 1")
    for table in ("photo_details", "video_details", "track_details", "collection_items",
                  "media_keywords"):  # fmt: skip
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    db.execute("DELETE FROM collections WHERE id = 1")
    assert db.execute("SELECT COUNT(*) FROM collections").fetchone()[0] == 0
    print("Borrado en cascada: detalles, colecciones y palabras clave")

    # 12. Borrar una ubicación se lleva sus carpetas declaradas
    db.execute("DELETE FROM storage_locations")
    assert db.execute("SELECT COUNT(*) FROM folder_libraries").fetchone()[0] == 0

    # 13. La función SQL de texto sin mayúsculas ni acentos está registrada
    assert db.execute(f"SELECT {FOLD_SQL_FUNCTION}('Añisclo')").fetchone()[0] == "anisclo"

    db.close()
    print("Autoprueba finalizada correctamente.")
