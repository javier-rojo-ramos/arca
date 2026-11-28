# Arca Media — Metadatos

> Qué datos tiene cada módulo y dónde se guarda cada uno ([mapa de campos por módulo](#mapa-de-campos-por-módulo)); de qué etiqueta se lee cada uno y con qué prioridad; equivalencias con Lightroom. Las recetas para añadir campos están en [core/metadata/LEEME.md](../core/metadata/LEEME.md); las tablas y sus columnas, en [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md).
> Índice: [INDEX.md](INDEX.md).

## Dónde se guarda cada dato

- **`media_items`, la ficha de cada archivo**: lo que tiene sentido en cualquier tipo de archivo (nombre, carpeta, tamaño, fecha, título, autor, descripción, ubicación, duración...) y los datos del usuario (valoración, marca, color, selección rápida). Así el filtro de texto, el orden, la barra de filtros, las colecciones inteligentes y la sección «Fechas» funcionan igual en todos los módulos. Por eso un mismo dato puede llamarse distinto en cada módulo: `creator` es el «Creador» de una foto, el autor de un GPX y el «Artista» de una canción.
- **Una tabla de detalles por tipo de archivo** (`photo_details`, `video_details`, `track_details` y `audio_details`, una fila por archivo): lo que solo tiene sentido en ese tipo (el objetivo de una foto, el desnivel de un track, el álbum de una canción).
- **Las palabras clave**, en sus propias tablas (`keywords` y `media_keywords`).
- **Fuera del catálogo**: lo que el usuario cambia se guarda también en el propio archivo (el XMP de una foto; desde `MUS 6`, las etiquetas de una canción) o en el `.arca.json` de su carpeta (vídeos, tracks y formatos sin XMP). Qué va dónde en cada formato: [FORMATOS.md](FORMATOS.md).

## Mapa de campos por módulo

> **Al añadir un dato, mostrarlo en otro sitio o cambiar dónde se guarda, actualizar su fila.** Revisado con el código el 25/11/2026 (`image/fields.py`, `video/fields.py`, `track/extractor.py`, `core/audio/tag_map.py`, `metadata_fields.py`, `smart_fields.py`, `editable_fields.py` y `grid_orders.py`). Las columnas sin tabla delante son de `media_items`. Las fuentes se prueban de izquierda a derecha («…» = hay más; las de las imágenes, enteras, en [Campos de imagen](#campos-de-imagen)); «Regla» = lo calcula el extractor con varias etiquetas. En «Dónde se ve»: «Insp.» es el inspector; «Colección», un campo de las colecciones inteligentes; «Filtro», una columna de «Metadatos» de la barra de filtros; «Orden», un campo del orden de la cuadrícula. El **Catálogo** muestra los de todos los módulos: en su inspector, la sección de una biblioteca sale cuando todo lo seleccionado es de ella.

### Comunes a todos los módulos

| Dato | Dónde se guarda | De dónde sale | Dónde se ve | ¿Se cambia? |
|---|---|---|---|---|
| Nombre y extensión | `file_name`, `file_extension` | El disco | Tarjeta; Insp. «Selección»; filtro de texto; Colección «Nombre de archivo» y «Extensión»; Filtro «Extensión»; Orden «Nombre» y «Extensión» | «Cambiar nombre…» (`CAT 4.2`): el archivo |
| Carpeta | `storage_location_id` y `relative_path` | El disco | Insp. «Selección» («Carpeta»); barra «Carpetas»; Colección «Carpeta (ruta)» | Mover (`CAT 4.4`): el archivo |
| Tamaño | `file_size` | El disco | Insp. «Selección»; Colección «Tamaño»; Orden «Tamaño» | — |
| Fecha de modificación | `file_mtime_ns` | El disco | Orden «Fecha de modificación» | — |
| Fecha de importación | `added_at` | Al añadirlo al catálogo | Colección y Filtro «Fecha de importación»; Orden | — |
| Fecha | `content_created_at`, con `content_date_precision`, `content_date_source` y `timezone_offset` | La de cada módulo (abajo); sin fecha, la del archivo la primera vez que se lee | Insp. «Selección» («Fecha»; su origen y su zona, en el texto emergente); barra «Fechas»; Colección y Filtro «Fecha de captura»; Orden «Hora de captura» | — (`GEN 2.1`) |
| Tipo de archivo | `media_type` | La extensión y el contenido (`media_detector.py`) | «Atributos»; Colección y Filtro «Tipo de archivo» | — |
| Biblioteca | `library` (`library_manual`: elegida a mano) | Las reglas de `libraries.py` | Insp. «Selección»; Colección y Filtro «Biblioteca» | Menú «Biblioteca»: solo el catálogo |
| Valoración, marca y color | `rating`, `flag`, `color_label` | Las imágenes, su XMP; lo demás, el `.arca.json` | Tarjeta; barra inferior; «Atributos»; Colección y Filtro | Sí: en el XMP o en el `.arca.json` |
| Selección rápida | `in_quick_selection` | — | Tarjeta; «Atributos»; Colección y Filtro | Sí: solo el catálogo |
| Palabras clave | `keywords` y `media_keywords` | Las imágenes, su XMP (`lr:HierarchicalSubject`, `dc:subject`); lo demás, el `.arca.json` | Insp. «Palabras clave» y «Lista de palabras clave»; barra «Lista de palabras clave» (Imagen); Colección y Filtro «Palabra clave» | Sí: en el XMP o en el `.arca.json` |
| Ausente | `is_missing` | La comprobación del disco | Aviso naranja de la tarjeta; Insp. «Selección» («Estado»); Colección y Filtro «Archivo ausente» | — |

### Imagen (fotos y vídeos personales)

En el orden de la sección «Metadatos» del inspector. Los vídeos de Imagen son los clips de cámara o de móvil; las películas van al módulo Vídeo (abajo).

| Dato | Dónde se guarda | Foto: de dónde sale | Vídeo: de dónde sale | Dónde se ve | ¿Se cambia? |
|---|---|---|---|---|---|
| Dimensiones | `width`, `height` (ya girados) | `DefaultCropSize` → `Composite:ImageSize` → `File:ImageWidth` …; HEIC con su `irot`; el área útil de algunos RAW ([cómo se lee](#imagen-cómo-se-lee)) | `Composite:ImageSize` → `ImageWidth` → `SourceImageWidth` | Insp. «Dimensiones» (todas las vistas); Colección «Ancho» y «Alto»; Colección y Filtro «Orientación» (horizontal, vertical o cuadrada, de las dos); proporción de la tarjeta | — |
| Orientación EXIF | `orientation` | Regla (`IFD0:Orientation`; el `irot` de un HEIC) | Siempre 1 | Giro de la miniatura | — |
| Recorte | `photo_details.crop_width`, `crop_height` | Regla (`XMP-crs:Crop*`) | — | Insp. «Recorte» (todas) | — |
| Fecha de captura | `content_created_at` (y su precisión, su origen y su zona) | Regla: EXIF `DateTimeOriginal` → … ([cómo se lee](#imagen-cómo-se-lee)) | Regla (`video/rules.py`): la hora local de Keys, XML, H264 o XMP, o la de QuickTime (UTC) pasada a local | Insp. «Captura» (todas); lo común, arriba | — |
| Digitalización | `photo_details.digitized_at` | `ExifIFD:CreateDate` → `XMP-xmp:CreateDate` | — | Insp. «Digitalización» (todas) | — |
| Modificación (EXIF) | `photo_details.exif_modified_at` | `IFD0:ModifyDate` → `XMP-xmp:ModifyDate` | — | Insp. «Modificación» (todas) | — |
| Cámara: marca | `photo_details.camera_make`, `video_details.camera_make` | `IFD0:Make` → `XMP-tiff:Make` → `CanonRaw:Make`, con el nombre corto («Nikon»: `camera_makers.py`) | `Keys:Make` → `UserData:Make` → `XML:DeviceManufacturer` …, con el nombre corto | Insp. «Cámara» (Por defecto, EXIF); Colección y Filtro «Marca de la cámara» y filtro de texto (solo fotos) | — |
| Cámara: modelo | `photo_details.camera_model`, `video_details.camera_model` | `IFD0:Model` → `XMP-tiff:Model` → `CanonRaw:Model` | `Keys:Model` → `UserData:Model` → `XML:DeviceModelName` … | Insp. «Cámara»; Colección y Filtro «Modelo de la cámara» y filtro de texto (solo fotos) | — |
| Objetivo | `photo_details.lens_model`, `video_details.lens_model` | `ExifIFD:LensModel` → `XMP-exifEX:LensModel` → `XMP-aux:Lens` … → `Nikon:Lens` (regla) | `VideoKeys:LensModel` → `Keys:LensModel` → `LensModel` → `Composite:LensID` → `Nikon:Lens` (regla) | Insp. «Objetivo» (Por defecto, EXIF); Colección y Filtro «Objetivo» y filtro de texto (solo fotos) | — |
| Focal | `photo_details.focal_length_mm` | `ExifIFD:FocalLength` → `XMP-exif:FocalLength` | — | Insp. «Focal»; Colección y Filtro «Distancia focal» | — |
| Focal 35 mm | `photo_details.focal_length_35mm`, `video_details.focal_length_35mm` | `ExifIFD:FocalLengthIn35mmFormat` → `XMP-exif:FocalLengthIn35mmFilm` | `VideoKeys:FocalLengthIn35mmFormat` → `Keys:FocalLengthIn35mmFormat` → `FocalLengthIn35mmFormat` | Insp. «Focal 35 mm» (Por defecto, EXIF) | — |
| Exposición: tiempo | `photo_details.exposure_time_s` (el exacto) | `ExifIFD:ExposureTime` → `XMP-exif:ExposureTime` → `Canon:ExposureTime` (CRW) | — | Insp. «Exposición» (redondeada, como Lightroom; el exacto, en el texto emergente); Colección y Filtro «Tiempo de exposición» | — |
| Exposición: apertura | `photo_details.f_number`, `video_details.f_number` | `ExifIFD:FNumber` → `XMP-exif:FNumber` | `VideoKeys:CameraLensIrisfnumber` → `Keys:CameraLensIrisfnumber` → `CameraLensIrisfnumber` → `FNumber` | Insp. «Exposición» (solo fotos); Colección y Filtro «Apertura (f/)» (solo fotos) | — |
| Sensibilidad | `photo_details.iso` | `ExifIFD:ISO` → `XMP-exif:ISO` → `Composite:ISO` (CRW) | — | Insp. «Sensibilidad»; Colección y Filtro «ISO» | — |
| Compensación | `photo_details.exposure_bias_ev` | `ExifIFD:ExposureCompensation` → `XMP-exif:ExposureBiasValue` → `Canon:ExposureCompensation` (CRW) | — | Insp. «Compensación» | — |
| Flash | `photo_details.flash_fired` (regla: el bit 0 de `flash_code`) y `flash_code` | `ExifIFD:Flash` | — | Insp. «Flash» («Disparado» / «No disparado»); Colección y Filtro «Flash disparado» | — |
| Programa | `photo_details.exposure_program` (código EXIF) | `ExifIFD:ExposureProgram` → `XMP-exif:ExposureProgram` | — | Insp. «Programa» | — |
| Medición | `photo_details.metering_mode` (código EXIF) | `ExifIFD:MeteringMode` → `XMP-exif:MeteringMode` | — | Insp. «Medición» | — |
| Duración | `duration` | — | `QuickTime:Duration` → `Composite:Duration` → `Duration` | Insp. «Duración» (EXIF); la tarjeta | — |
| Fotogramas | `video_details.frame_rate` | — | `VideoFrameRate` → `FrameRate` | Insp. «Fotogramas» (EXIF) | — |
| Códec | `video_details.video_codec` | — | `CompressorID` → `VideoCodec` → `CompressorName` | Insp. «Códec» (EXIF) | — |
| Título | `title` (sin título, el nombre del archivo) | `XMP-dc:Title` → `IPTC:ObjectName` | `XMP-dc:Title` → `ItemList:Title` → `UserData:Title` → `QuickTime:Title` | Insp. «Título» (Por defecto, Ubicación; en blanco si es el nombre del archivo); filtro de texto; Colección «Título» | Sí ¹ |
| Pie | `description` | `XMP-dc:Description` → `IPTC:Caption-Abstract` → `IFD0:ImageDescription` | `XMP-dc:Description` → `ItemList:Description` → `UserData:Description` → `QuickTime:Description` | Insp. «Pie»; Colección «Descripción»; filtro de texto | Sí ¹ |
| Creador | `creator` | `XMP-dc:Creator` → `IPTC:By-line` → `IFD0:Artist` | `XMP-dc:Creator` → `ItemList:Artist` → `UserData:Artist` → `QuickTime:Author` | Insp. «Creador»; Colección y Filtro «Autor»; filtro de texto | Sí ¹ |
| Copyright | `copyright` | `XMP-dc:Rights` → `IPTC:CopyrightNotice` → `IFD0:Copyright` | `XMP-dc:Rights` → `ItemList:Copyright` → `UserData:Copyright` | Insp. «Copyright»; Colección y Filtro «Copyright»; filtro de texto | Sí ¹ |
| Lugar | `sublocation` | `XMP-iptcCore:Location` → `IPTC:Sub-location` | — | Insp. «Lugar»; Colección y Filtro «Lugar»; filtro de texto | Sí ¹ |
| Ciudad | `city` | `XMP-photoshop:City` → `IPTC:City` | — | Insp. «Ciudad»; Colección y Filtro «Ciudad»; filtro de texto | Sí ¹ |
| Región | `region` | `XMP-photoshop:State` → `IPTC:Province-State` | — | Insp. «Región»; Colección y Filtro «Región o provincia»; filtro de texto | Sí ¹ |
| País | `country` | `XMP-photoshop:Country` → `IPTC:Country-PrimaryLocationName` | — | Insp. «País»; Colección y Filtro «País»; filtro de texto | Sí ¹ |
| Código del país | `country_code` | `XMP-iptcCore:CountryCode` → `IPTC:Country-PrimaryLocationCode` | — | Insp. «Código país» | Sí ¹ |
| GPS | `latitude`, `longitude` (la pareja, de la misma fuente) | `XMP-exif:GPSLatitude` → `Composite:GPSLatitude` | `Composite:GPSLatitude` → `XMP-exif:GPSLatitude` → `GPSLatitude` | Insp. «GPS»; el mapa; la chincheta de la tarjeta; Colección y Filtro «Tiene coordenadas GPS» | Sí ¹ (también en el mapa: ubicar, mover y quitar) |
| Altitud | `altitude` | `XMP-exif:GPSAltitude` (con su referencia) → `Composite:GPSAltitude` → `GPS:GPSAltitude` | `Composite:GPSAltitude` → `XMP-exif:GPSAltitude` → `GPSAltitude` | Insp. «Altitud» | Sí ¹ |
| Dirección | `gps_direction` | `XMP-exif:GPSImgDirection` → `GPS:GPSImgDirection` | — | Insp. «Dirección» | Sí ¹ |

¹ En la sección «Metadatos» del inspector (vistas «Por defecto» y «Ubicación»). Se guarda en el catálogo y se escribe en el archivo: en una foto, en su XMP (incrustado o en el sidecar `.xmp` de un RAW) y en las etiquetas antiguas que ya tenga ([escritura](#escritura-de-los-metadatos-descriptivos)); en un vídeo o en un formato sin XMP, en el `.arca.json` de su carpeta. Lo pendiente de escribir no se pisa al releer.

**Se leen pero no se ven en ningún sitio**: `intellectual_genre`, `scene`, `iptc_created_at`, `photo_details.body_serial_number`, `software` (foto y vídeo), `photo_details.user_comment`, `brightness_value`, `flash_code` (el detalle del flash: modo, retorno), `has_xmp_sidecar` y, en los vídeos, `f_number` (la fila «Exposición» solo lee fotos). Candidatos para las vistas IPTC y «Personalizada» del inspector (mejoras menores de [PENDIENTE.md](PENDIENTE.md)).

### Tracks

Del lector de GPX (`core/metadata/track/`, sin ExifTool), en el orden de la sección «Track» del inspector. Los puntos y los waypoints no se guardan: el GPX es la fuente y se lee cuando hace falta (el mapa y el perfil).

| Dato | Dónde se guarda | De dónde sale (GPX) | Dónde se ve | ¿Se cambia? |
|---|---|---|---|---|
| Distancia | `track_details.distance_m` | La suma de los tramos de cada segmento, en 2D (como Wikiloc) | Insp. «Distancia»; Colección «Distancia»; Orden «Distancia» | — |
| Desnivel | `track_details.elevation_gain_m`, `elevation_loss_m` | La altitud de los puntos, con un umbral de 8 m contra el ruido del GPS | Insp. «Desnivel» (↑ y ↓); Colección «Desnivel positivo» y «negativo»; Orden «Desnivel positivo»; el perfil | — |
| Altitud | `track_details.elevation_min_m`, `elevation_max_m` | La de los puntos | Insp. «Altitud» (mínima y máxima); Colección «Altitud máxima» | — |
| Duración | `duration` | Del primer punto con hora al último | Insp. «Duración»; la tarjeta; Orden «Duración» | — |
| Velocidad | No se guarda: la distancia entre la duración (`track_stats.py`) | — | Insp. «Velocidad» | — |
| Puntos | `track_details.point_count`, `segment_count`, `waypoint_count`, `is_planned_route` (y `track_count`, `route_count`) | `<trkpt>`, `<trkseg>`, `<wpt>`; una ruta planificada (`<rte>`) solo si no hay recorrido grabado | Insp. «Puntos» | — |
| Actividad | `track_details.activity_type` (la clave de `core/tracks/activities.py`) | `<trk><type>` («Hike» → `hiking`; lo que no se reconoce, `generic`) | Insp. «Actividad» (desplegable); Colección y Filtro «Actividad» | Sí: en el `.arca.json` (en el `<type>` del GPX, con `TRK 6.1`) |
| Creado con | `track_details.creator_app` | El atributo `creator` de `<gpx>` | Insp. «Creado con»; Colección y Filtro «Creado con»; filtro de texto | — |
| Nombre | `title` (sin nombre, el del archivo) | `<trk><name>` o el de `<metadata>` | Filtro de texto; Colección «Título» | — |
| Descripción | `description` | `<desc>` del track o del archivo | Colección «Descripción»; filtro de texto | — |
| Autor | `creator` | `<metadata><author><name>` (GPX 1.0: `<author>`) | Colección y Filtro «Autor» | — |
| Fecha de salida | `content_created_at` (hora LOCAL, con la zona del equipo); `track_details.started_at` y `ended_at` (UTC) | El primer y el último punto con hora | Lo común (arriba) | — |
| Salida y llegada | `latitude`, `longitude`, `altitude` (salida); `track_details.end_latitude`, `end_longitude` | El primer y el último punto | El mapa | — |
| Recuadro | `track_details.min_latitude`, `max_latitude`, `min_longitude`, `max_longitude` | Todos los puntos | El mapa (qué tracks caen en lo que se ve) | — |
| Contorno | `track_details.overview` (como mucho 1 000 puntos, en polilínea codificada) | El recorrido, simplificado (`core/tracks/simplify.py`) | El mapa (todos los tracks a la vez); la forma del recorrido en la tarjeta | — |

### Música

**Estado (26/11/2026)**: las canciones se leen solas desde `MUS 1.3` (`core/metadata/audio/extractor.py`). Los datos que están en `media_items` (título, artista, año, comentario y duración) se ven en «Selección», la tarjeta, el filtro de texto, las colecciones, la barra de filtros y el orden; desde `MUS 2.1`, todos los de las dos tablas siguientes (las filas «Insp.»), en la sección «Audio» del inspector, de solo lectura (`ui_helpers/inspector/audio_section.py`, con `core/catalog/audio_stats.py`); desde `MUS 2.2`, el orden («Artista», «Álbum», «Año» y «Título»); desde `MUS 2.3`, los filtros, las colecciones y la búsqueda de «Texto» (el grupo «Audio»: [MOD_MUSICA.md](MOD_MUSICA.md) §7.4); desde `MUS 4.1`, las secciones «Artistas» y «Años» de la barra; «Géneros», en `MUS 4.2`; desde `MUS 3.1`, la carátula como miniatura. Las filas del inspector, en el orden acordado ([MOD_MUSICA.md](MOD_MUSICA.md) §7.1). La tabla campo ↔ etiqueta es `core/audio/tag_map.py`.

| Dato | Dónde se guarda | ID3 (MP3, WAV, AIFF) | Vorbis (FLAC, Ogg, Opus) | MP4 (M4A) | Dónde se verá | ¿Se cambiará? |
|---|---|---|---|---|---|---|
| Título | `title` (sin título, el nombre del archivo) | `TIT2` | `TITLE` | `©nam` | Insp. «Título»; filtro de texto; Colección «Título» | ² |
| Artista | `creator` | `TPE1` | `ARTIST` | `©ART` | Insp. «Artista»; Colección y Filtro «Artista» (Audio) y «Autor» (Estándar); «Texto»; barra «Artistas» (si no hay artista del álbum) | ² |
| Álbum | `audio_details.album` | `TALB` | `ALBUM` | `©alb` | Insp. «Álbum»; barras «Artistas» y «Años» ▸ álbum; Colección y Filtro «Álbum»; «Texto»; Orden (`MUS 2.2`) | ² |
| Año | `content_created_at` (con precisión de año si solo trae el año; sin año, sin fecha; el origen, `id3`, `vorbis` o `mp4`) | `TDRC` (en v2.3, `TYER`) | `DATE` (o `YEAR`) | `©day` | Insp. «Año»; barra «Años» y el año de los álbumes en «Artistas» («2001 · Destrangis», «1974 – 2011 · …»); Colección y Filtro «Año» (un número) y «Fecha de captura»; Orden | ² |
| Pista | `audio_details.track_number`, `track_total` | `TRCK` («3/12») | `TRACKNUMBER` y `TRACKTOTAL` (o `TOTALTRACKS`) | `trkn` | Insp. «Pista» («22 / 25»); Colección «Pista»; Orden del álbum | ² |
| Disco | `audio_details.disc_number`, `disc_total` | `TPOS` | `DISCNUMBER` y `DISCTOTAL` (o `TOTALDISCS`) | `disk` | Insp. «Disco»; Colección «Disco»; Orden del álbum | ² |
| Género | `audio_details.genre` (varios, unidos con «; ») | `TCON` (también «(17)», el número de ID3v1) | `GENRE` | `©gen` (o `gnre`, el número) | Insp. «Género»; Colección y Filtro «Género»; «Texto»; barra «Géneros» (`MUS 4.2`) | ² |
| Artista del álbum | `audio_details.album_artist` | `TPE2` | `ALBUMARTIST` (o `ALBUM ARTIST`) | `aART` | Insp. «Artista del álbum»; barra «Artistas»; Colección y Filtro «Artista del álbum» (sin él, cuenta el artista, como foobar2000); «Texto» | ² |
| Compositor | `audio_details.composer` | `TCOM` | `COMPOSER` | `©wrt` | Insp. «Compositor»; Colección y Filtro «Compositor»; «Texto» | ² |
| Comentario | `description` | `COMM` sin descripción | `COMMENT` (o `DESCRIPTION`) | `©cmt` | Insp. «Comentario»; Colección «Descripción» | ² |

² Desde `MUS 7`, en el inspector. Desde `MUS 6.2b` (28/11/2026), lo editado de un MP3 se escribe en su etiqueta, sin copias (`core/userdata/audio_writer.py`, con la tabla de `core/userdata/audio_fields.py`), y la valoración, la marca, el color, las palabras clave y lo demás siguen en su `.arca.json`; en FLAC, M4A y Ogg, todo en el `.arca.json` hasta `MUS 6.3` y `6.4`. El año, con `MUS 7.1`, como un año.

Los datos técnicos y la carátula los da mutagen en todos los formatos (`core/audio/tag_reader.py`):

| Dato | Dónde se guarda | De dónde sale | Dónde se verá | ¿Se cambiará? |
|---|---|---|---|---|
| Duración | `duration` | La cabecera del audio | Insp. «Duración»; la tarjeta; Orden «Duración» (ya hoy) | — |
| Formato | `audio_details.codec`, `codec_detail` | El tipo de archivo y su códec («AAC LC») | Insp. «Formato»; Colección y Filtro «Formato» | — |
| Calidad | `audio_details.bitrate` (la media), `bitrate_mode`, `sample_rate`, `channels`, `bit_depth` (solo sin pérdida), `lossless` | La cabecera del audio; en Ogg Vorbis, la tasa se calcula ([TRAMPAS.md](TRAMPAS.md)) | Insp. «Calidad» («VBR · 277 kbps · 44,1 kHz · Estéreo»; también «CBR» y «ABR»; con varias canciones, la tasa como intervalo); Colección «Tasa de bits» y Orden «Tasa de bits»; Colección y Filtro «Frecuencia de muestreo» y «Canales» | — |
| Etiqueta | `audio_details.tag_type` | Las etiquetas del archivo («ID3v2.3 + ID3v1», «Vorbis», «MP4») | Insp. «Etiqueta»; Colección y Filtro «Tipo de etiqueta» | — |
| Carátula | `audio_details.picture_count` y, de la primera portada (o la primera imagen), `cover_type`, `cover_mime`, `cover_width`, `cover_height`, `cover_bytes` y `cover_hash` (la huella) | `APIC` (ID3); bloque PICTURE (FLAC) o `METADATA_BLOCK_PICTURE` (Ogg); `covr` (MP4, siempre «Portada») | La miniatura (desde `MUS 3.1`); Insp. «Carátula»: la imagen (de la caché), «Tipo» e «Imagen» (`MUS 9.1`); la carátula del álbum, por la huella; Colección y Filtro «Tiene carátula»; Colección «Lado menor de la carátula» | `MUS 9`: en el archivo |

### Vídeo (películas) y Ebooks

Sin datos propios todavía. Hoy una película tiene los comunes y los de vídeo de Imagen (el extractor es el mismo); su tabla llegará con `VID 1` y `VID 2` ([MOD_VIDEO.md](MOD_VIDEO.md)). La de los libros, con `EBK 2` ([MOD_EBOOKS.md](MOD_EBOOKS.md)).

## Imagen: cómo se lee

**Prioridad entre fuentes** (la recomendación del Metadata Working Group, la que sigue Lightroom). Es el **orden de las etiquetas en cada línea** de `image/fields.py`:

| Tipo de dato | Orden |
|---|---|
| Descriptivos (título, pie de foto, autor, copyright, ubicación) | XMP → IPTC → EXIF |
| GPS: coordenadas, altitud y dirección (desde el 11/11/2026, `IMAGE_FIELDS_VERSION` 9) | XMP → EXIF |
| Técnicos de la toma (cámara, objetivo, exposición, ISO, flash...) | EXIF → XMP |
| Fecha de captura | EXIF `DateTimeOriginal` → EXIF `CreateDate` → CRW `CanonRaw:DateTimeOriginal` (origen `crw`; los CRW no tienen EXIF) → XMP `DateCreated` → IPTC → EXIF `ModifyDate` → fecha del archivo (`content_date_source = 'file_mtime'`): la de la primera lectura; al releer se conserva, porque escribir en el archivo le cambia la fecha (`processor.py`, desde la versión 12) |

- **Sidecars**: se buscan `IMG_0001.xmp` (convención de Adobe) y `IMG_0001.CR3.xmp`. Del sidecar solo se toman etiquetas XMP, y pisan a las del XMP incrustado.
- **ExifTool se invoca con** `-j -n -G1 -a -charset utf8 -charset filename=utf8`: JSON, valores numéricos sin traducir (programa de exposición, medición y flash se guardan como **códigos EXIF**; la interfaz los traduce), etiquetas con su grupo (`IFD0:Make`, `XMP-photoshop:City`) y los nombres de archivo en UTF-8 mediante archivo temporal (`-@`).
- **Dónde busca el ejecutable**: variable `EXIFTOOL_PATH` → carpeta `tools/exiftool` → `PATH`.
- **Tamaño**: se guarda "de pantalla" (ya girado si la orientación EXIF es 5 a 8). En los **HEIC, HEIF y AVIF**, si traen su caja `irot` (ExifTool: `QuickTime:Rotation`, cuartos de vuelta de 0 a 3), manda ella, porque es el giro que aplican las librerías y el de la miniatura; si no hay orientación EXIF, la columna `orientation` toma la equivalente (desde el 21/11/2026, `IMAGE_FIELDS_VERSION` 10; antes, un AVIF con el giro solo en el `irot` salía apaisado). En los **RAW de Nikon, Olympus y Pentax**, el área útil de su nota del fabricante (`Nikon:CropArea`, `Nikon:AFImageWidth/Height`, `Olympus:CropWidth/Height`, `Pentax:RawImageSize`, si mide entre el 90 % y el 100 % del sensor), que es la de Lightroom: Nikon Df 4928 × 3280 frente a 4992 × 3292 del sensor (desde el 21/11/2026, `IMAGE_FIELDS_VERSION` 11; las Pentax, desde la 13; comparados con Lightroom 18 RAW de 11 marcas: solo la Coolpix NRW y los Sony SRF y SR2 antiguos siguen con el sensor, entre un 0,5 % y un 3 % mayor). En los **DNG**, `DefaultCropSize` manda sobre `Composite:ImageSize` (el sensor completo, algo mayor): es lo que Lightroom muestra como "Dimensiones de archivo" (verificado: 3200 × 2128 frente a 3264 × 2140). Solo existe en los DNG, así que no afecta a otros formatos.
- **GPS**: primero el XMP y después el compuesto de ExifTool (los dos, ya con signo), como Lightroom; la pareja latitud/longitud, siempre de la misma fuente (el XMP solo si tiene las dos); la altitud del XMP, con `XMP-exif:GPSAltitudeRef` (1 = bajo el nivel del mar; sin ella, sobre él); se descartan los fuera de rango y `0, 0` (`rules.py`).

### Campos de imagen

Generado de `IMAGE_FIELDS`; las fuentes se prueban de izquierda a derecha:

| Columna | Tabla | Fuentes (ExifTool) | Conversor |
|---|---|---|---|
| `title` | media_items | `XMP-dc:Title` → `IPTC:ObjectName` | `text` |
| `description` | media_items | `XMP-dc:Description` → `IPTC:Caption-Abstract` → `IFD0:ImageDescription` | `text` |
| `creator` | media_items | `XMP-dc:Creator` → `IPTC:By-line` → `IFD0:Artist` | `text` |
| `copyright` | media_items | `XMP-dc:Rights` → `IPTC:CopyrightNotice` → `IFD0:Copyright` | `text` |
| `intellectual_genre` | media_items | `XMP-iptcCore:IntellectualGenre` → `IPTC:ObjectAttributeReference` | `text` |
| `scene` | media_items | `XMP-iptcCore:Scene` | `text` |
| `iptc_created_at` | media_items | `XMP-photoshop:DateCreated` → `Composite:DateTimeCreated` → `IPTC:DateCreated` | `datetime_text` |
| `sublocation` | media_items | `XMP-iptcCore:Location` → `IPTC:Sub-location` | `text` |
| `city` | media_items | `XMP-photoshop:City` → `IPTC:City` | `text` |
| `region` | media_items | `XMP-photoshop:State` → `IPTC:Province-State` | `text` |
| `country` | media_items | `XMP-photoshop:Country` → `IPTC:Country-PrimaryLocationName` | `text` |
| `country_code` | media_items | `XMP-iptcCore:CountryCode` → `IPTC:Country-PrimaryLocationCode` | `text` |
| `latitude` | media_items | `XMP-exif:GPSLatitude` → `Composite:GPSLatitude` | `real` |
| `longitude` | media_items | `XMP-exif:GPSLongitude` → `Composite:GPSLongitude` | `real` |
| `altitude` | media_items | `XMP-exif:GPSAltitude` → `Composite:GPSAltitude` → `GPS:GPSAltitude` | `real` |
| `width` | media_items | `DefaultCropSize` → `Composite:ImageSize` → `File:ImageWidth` → `ExifIFD:ExifImageWidth` | `image_width` |
| `height` | media_items | `DefaultCropSize` → `Composite:ImageSize` → `File:ImageHeight` → `ExifIFD:ExifImageHeight` | `image_height` |
| `camera_make` | photo_details | `IFD0:Make` → `XMP-tiff:Make` → `CanonRaw:Make` | `maker_name` (`camera_makers.py`: el nombre corto, como Lightroom, por la primera palabra: «NIKON CORPORATION» → «Nikon», «RICOH IMAGING COMPANY, LTD.» → «Ricoh»; lo que no está en la lista, tal cual; «--», vacío; desde la versión 14) |
| `camera_model` | photo_details | `IFD0:Model` → `XMP-tiff:Model` → `CanonRaw:Model` | `model_name` (tal cual; «--», vacío) |
| `body_serial_number` | photo_details | `ExifIFD:SerialNumber` → `XMP-exifEX:BodySerialNumber` → `XMP-aux:SerialNumber` | `text`; sin ninguna, `CanonRaw:SerialNumber` con sus 10 cifras («0910501743», como Lightroom; regla en `rules.py`) |
| `lens_model` | photo_details | `ExifIFD:LensModel` → `XMP-exifEX:LensModel` → `XMP-aux:Lens` → `Canon:LensModel` → `Panasonic:LensType` → `Composite:LensID` | `lens_name` (sin los códigos numéricos: con `-n`, `Composite:LensID` es el código del fabricante); sin ningún nombre, `Nikon:Lens` («20 20 1.8 1.8») con el texto de Lightroom, «20.0 mm f/1.8» (`lens_from_spec`, regla en `rules.py`) |
| `software` | photo_details | `IFD0:Software` → `XMP-xmp:CreatorTool` | `text` |
| `user_comment` | photo_details | `ExifIFD:UserComment` | `text` |
| `focal_length_mm` | photo_details | `ExifIFD:FocalLength` → `XMP-exif:FocalLength` | `real` |
| `focal_length_35mm` | photo_details | `ExifIFD:FocalLengthIn35mmFormat` → `XMP-exif:FocalLengthIn35mmFilm` | `real` |
| `f_number` | photo_details | `ExifIFD:FNumber` → `XMP-exif:FNumber` | `real` |
| `exposure_time_s` | photo_details | `ExifIFD:ExposureTime` → `XMP-exif:ExposureTime` → `Canon:ExposureTime` (CRW) | `real` |
| `iso` | photo_details | `ExifIFD:ISO` → `XMP-exif:ISO` → `Composite:ISO` (CRW) | `integer` |
| `exposure_bias_ev` | photo_details | `ExifIFD:ExposureCompensation` → `XMP-exif:ExposureBiasValue` → `Canon:ExposureCompensation` (CRW) | `real` |
| `brightness_value` | photo_details | `ExifIFD:BrightnessValue` → `XMP-exif:BrightnessValue` | `real` |
| `exposure_program` | photo_details | `ExifIFD:ExposureProgram` → `XMP-exif:ExposureProgram` | `integer` |
| `metering_mode` | photo_details | `ExifIFD:MeteringMode` → `XMP-exif:MeteringMode` | `integer` |
| `flash_code` | photo_details | `ExifIFD:Flash` | `integer` |
| `gps_direction` | media_items | `XMP-exif:GPSImgDirection` → `GPS:GPSImgDirection` | `real` |
| `digitized_at` | photo_details | `ExifIFD:CreateDate` → `XMP-xmp:CreateDate` | `datetime_text` |
| `exif_modified_at` | photo_details | `IFD0:ModifyDate` → `XMP-xmp:ModifyDate` | `datetime_text` |

Además, las reglas (`image/rules.py`) rellenan `orientation`, `content_created_at`, `content_date_precision`, `content_date_source`, `timezone_offset`, `flash_fired`, `crop_width` y `crop_height`, y completan `lens_model` y `body_serial_number` con la nota del fabricante; el extractor genérico rellena `has_xmp_sidecar`.

**Lightroom ↔ aplicación** (paneles EXIF y Ubicación):

| Lightroom | Columna |
|---|---|
| Fecha y hora originales | `content_created_at` (+ `timezone_offset`) |
| Fecha y hora digitalizadas | `photo_details.digitized_at` |
| Fecha y hora | `photo_details.exif_modified_at` |
| Fecha de creación (IPTC) | `iptc_created_at` |
| Exposición, apertura, focal (real y 35 mm), ISO, compensación, valor de brillo | `exposure_time_s`, `f_number`, `focal_length_mm`, `focal_length_35mm`, `iso`, `exposure_bias_ev`, `brightness_value`. Se guarda el tiempo EXACTO (`ExposureTime`); Lightroom lo MUESTRA redondeado a la velocidad nominal más cercana (iPhone: 1/54 s → «1/50 seg.»; `ShutterSpeedValue` también da 1/54; y lo más rápido que 1/8000, como 1/8000: 1/17544 s → «1/8000 seg.»), y el inspector hace lo mismo (`formatting.format_exposure`), con el exacto en el texto emergente |
| Flash, programa de exposición, modo de medición | `flash_fired` + `flash_code`, `exposure_program`, `metering_mode` (códigos). El inspector muestra «Flash» con `flash_fired`: «Disparado» / «No disparado» |
| Marca, modelo, lente, nº de serie, software | `camera_make`, `camera_model`, `lens_model`, `body_serial_number`, `software` |
| Artista, comentario del usuario | `creator`, `photo_details.user_comment` |
| GPS, altitud, dirección | `latitude`/`longitude`, `altitude`, `gps_direction` (grados) |
| Ubicación secundaria, ciudad, estado o región, país, código ISO | `sublocation`, `city`, `region`, `country`, `country_code` |
| Título, pie de ilustración | `title`, `description` |
| Género intelectual, escena | `intellectual_genre`, `scene` |
| Archivos sidecar | `has_xmp_sidecar` |
| Dimensiones de archivo | `width`, `height` (DNG: `DefaultCropSize`) |
| Dimensiones actuales (recorte) | `photo_details.crop_width`, `crop_height`, calculadas en `image/rules.py` (`crop_size`) con `XMP-crs:HasCrop`, `CropLeft/Top/Right/Bottom` y `CropAngle` (del archivo o del sidecar). Left/Top y Right/Bottom son esquinas OPUESTAS del recorte en fracciones de la imagen sin girar; con enderezado, la diagonal (dx, dy) en píxeles se gira el ángulo: ancho = dx·cos a + dy·sen a, alto = −dx·sen a + dy·cos a. Verificado con un DNG (sin ángulo) y un JPG (−4,2°). NULL sin recorte o con `AlreadyApplied`. Se giran con la orientación, como `width`/`height` |
| Estado de metadatos | no se guarda: lo cubre la detección de cambios (`file_size` + `file_mtime_ns`, `scan_version`) |

**Datos del usuario que se leen del archivo** (`IMAGE_USER_FIELDS` en `image/fields.py`; bloque C, no van en `IMAGE_FIELDS`; verificados con HEIC de Lightroom Classic 15.6: rating 3 y 5, color rojo y azul, rechazada y marcada):

| Columna | Fuentes (ExifTool) | Conversor | Valores |
|---|---|---|---|
| `rating` | `XMP-xmp:Rating` | `rating_value` | 1 a 5 (0 = sin valoración = no se lee; -1 no se interpreta aquí) |
| `flag` | `XMP-xmpDM:Pick` | `pick_flag` | 1 marcada, -1 rechazada (`xmpDM:Good` es redundante) |
| `color_label` | `XMP-photoshop:LabelColor` → `XMP-xmp:Label` | `normalize_color_label` | `red`, `yellow`, `green`, `blue`, `purple` (`LabelColor` viene en inglés; `Label` traducido: "Roja", "Azul") |

Lightroom escribió el XMP **incrustado en el propio HEIC** (sin sidecar). El extractor devuelve estos valores en `ExtractionResult.user_data` (un 0 escrito es un dato; una etiqueta ausente, `None` = "no dice nada") y el procesador los aplica con la regla "manda el archivo, salvo en los campos pendientes" ([DECISIONES.md](DECISIONES.md)). Se leen del sidecar en los RAW (si existe) y del propio archivo en los demás. `xmp:Rating = -1` (rechazo de Bridge) **no** se trata todavía como rechazo.

**Escritura** (`core/userdata/xmp_writer.py`): las mismas etiquetas; el 0 se escribe explícito (`xmp:Rating = 0`, `xmpDM:Pick = 0`) y `xmpDM:Good` acompaña a la marca (`true`/`false`); el color escribe `photoshop:LabelColor` (inglés) y `xmp:Label` con el texto del juego de etiquetas de Lightroom en español (`XMP_LABEL_TEXTS` en `color_labels.py`: "Roja" y "Azul" comprobados; el resto, pendiente de comprobar). Si el archivo ya tiene un texto del mismo color, se conserva; un texto personalizado ("Revisar") no se borra al quitar el color.

**Palabras clave** (desde el 03/11/2026, `IMAGE_FIELDS_VERSION` 8; solo imágenes): se leen como **datos del usuario**, de las mismas etiquetas que la valoración (el sidecar en los RAW, el propio archivo en los demás), y van a las tablas `keywords` y `media_keywords` (ver [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md)). Comprobado con un HEIC y un NEF de Lightroom Classic 15.6:

| Etiqueta | Qué trae | Uso |
|---|---|---|
| `XMP-lr:HierarchicalSubject` | Las palabras **asignadas** con su ruta: `["Coche", "Coche\|Toyota Corolla"]`. Los padres de una ruta no están asignados por estar en ella (si aparecen solos, también se asignaron). Lightroom escribe la ruta completa aunque el padre sea una categoría («[Familia]») | Crea el árbol y asigna |
| `XMP-dc:Subject` → `IPTC:Keywords` | La lista plana (`["Coche", "Toyota Corolla"]`) | Solo lo que no esté ya en las rutas: palabras sueltas de otros programas |
| `XMP-lr:WeightedFlatSubject` | Copia interna de Lightroom | No se usa |

Una palabra suelta va a la única del árbol con ese nombre; si hay varias, al primer nivel marcada para revisar; si no hay ninguna, se crea en el primer nivel (`core/catalog/keywords.py`). **Manda el archivo**: quedan exactamente las suyas (una etiqueta ausente = ninguna, porque Lightroom borra la lista al quitar la última). Los **vídeos** no las traen: Lightroom no sabe escribir en MP4 (las guarda solo en su catálogo) y las tendrán en el catálogo y el `.arca.json` (paso K5). `python -m core.metadata.inspect_cli foto.heic --campos` muestra las que se leen. Se ven en la sección «Palabras clave» del inspector y se filtran con el campo «Palabra clave» de las colecciones inteligentes (Estándar ▸ Palabras clave): «es (con sus hijas)», «es (sin sus hijas)», «no es (ni sus hijas)», «contiene», «no contiene», «empieza por» (estos tres también miran las hijas), «tiene valor» y «está vacío».

**Escritura** (desde el 03/11/2026, paso K4a; `xmp_writer.py`): como Lightroom, comprobado con un NEF con solo «Opel Astra» (`lr:HierarchicalSubject` = `Coche|Opel Astra`, `dc:Subject` = `Coche`, `Opel Astra`) y un HEIC con «Familia > Isa» y «Familia > Javi» (`dc:Subject` = `Familia`, `Isa`, `Javi`, aunque «[Familia]» es una categoría): la jerárquica lleva las rutas **asignadas** y la plana cada palabra **y sus padres**. A un archivo solo se le asigna la palabra; sus padres se deducen del árbol (no hay «padres automáticos»). `IPTC:Keywords` se actualiza solo si el archivo ya lo tenía (y desde el 10/11/2026, con el resumen IPTC al día: ver más abajo). En los formatos sin XMP, en el `.arca.json` de la carpeta (clave `keywords`, lista de rutas), que también se lee al sincronizar. Para decidir si un archivo ya está al día, las rutas se comparan **letra a letra** (desde el 04/11/2026: renombrar «Familia» a «Família» en la aplicación tiene que llegar al archivo); al leer, en cambio, una palabra se reconoce sin mayúsculas ni acentos. Renombrar, mover o borrar una palabra del árbol deja pendientes todos los archivos que la tienen o tienen alguna de sus hijas.

### Escritura de los metadatos descriptivos

Paso C.5 (`xmp_writer.py` y `editable_fields.py`; ver [DECISIONES.md](DECISIONES.md)). Se editan en la sección «Metadatos» del inspector (fotos y vídeos de Imagen; vistas «Por defecto» y «Ubicación»). Se escribe en todas las etiquetas de las que se lee: el XMP siempre y las antiguas solo si el archivo ya las tiene. Para saber si ya está al día y para comprobar lo escrito, se lee como el extractor (la primera etiqueta no vacía). Un texto que ExifTool entrega como número («1.50» llega como 1,5) se compara como número. Probado el 10/11/2026, antes de programarlo, con ExifTool 13.59, el extractor de imagen y Lightroom Classic:

| Columna | XMP (siempre) | Antiguas (solo si ya existen) | Lightroom, vista IPTC |
|---|---|---|---|
| `title` | `XMP-dc:Title` | `IPTC:ObjectName` | Título (Estado) |
| `description` | `XMP-dc:Description` | `IPTC:Caption-Abstract`, `IFD0:ImageDescription` | Descripción (Contenido); en otras vistas, «Pie de ilustración» |
| `creator` | `XMP-dc:Creator` | `IPTC:By-line`, `IFD0:Artist` | Creador (Contacto) |
| `copyright` | `XMP-dc:Rights` | `IPTC:CopyrightNotice`, `IFD0:Copyright` | Copyright |
| `sublocation` | `XMP-iptcCore:Location` | `IPTC:Sub-location` | Ubicación secundaria (Imagen) |
| `city` | `XMP-photoshop:City` | `IPTC:City` | Ciudad |
| `region` | `XMP-photoshop:State` | `IPTC:Province-State` | Estado o región |
| `country` | `XMP-photoshop:Country` | `IPTC:Country-PrimaryLocationName` | País/Región |
| `country_code` | `XMP-iptcCore:CountryCode` | `IPTC:Country-PrimaryLocationCode` | Código de país ISO |

- **JPEG** (con IPTC en Latin y en UTF-8) y **HEIC** (solo EXIF): el extractor relee lo escrito y Lightroom lo muestra; al vaciar queda todo vacío. Las demás etiquetas IPTC (`IPTC:Keywords`) no se tocan. Si solo se vacía el XMP, al releer vuelve el IPTC antiguo.
- **Límites del IPTC** (`City` 32 bytes, `ObjectName` 64, `Caption-Abstract` 2000...): ExifTool recorta lo que sobra con un aviso `[Minor] ... exceeds length limit (truncated)`; en UTF-8, sin partir una letra. El XMP guarda el valor entero.
- **IPTC en Latin** (sin `CodedCharacterSet`): los acentos, la ñ, © y las comillas tipográficas, bien; lo que no existe en Latin («→»), «?». Lightroom lee bien los acentos de un IPTC antiguo en Latin.
- **Resumen IPTC** (`Photoshop:IPTCDigest`): ExifTool no lo recalcula solo; con `-Photoshop:IPTCDigest=new` queda igual a `CurrentIPTCDigest`. Con el resumen desajustado, Lightroom muestra el IPTC (la ciudad cortada, «Villanueva de la Cañada del Río», y «?» en el pie); con el resumen al día, el XMP entero.
- **Saltos de línea** en el pie: bien en `IPTC:Caption-Abstract`, `IFD0:ImageDescription` y el XMP, escritos con `#[CSTR]` ([TRAMPAS.md](TRAMPAS.md)).
- **`dc:creator` es una lista**: dos creadores se leen «Ana, Luis»; «Rojo, Javier» escrito es un solo creador (ExifTool no lo parte).
- **RAW** (simulado: un TIFF con `Artist` y `Copyright` de cámara, más su sidecar): lo escrito en el sidecar manda; al vaciarlo (borrando la etiqueta o con un vacío explícito, `-TAG^=`, que la lectura salta) vuelve lo de la cámara. Falta probarlo con un DNG y un RAW real (NEF o CR3).
- **Textos de cámara**: Lightroom también muestra «OLYMPUS DIGITAL CAMERA» (de `IFD0:ImageDescription`) como pie; aquí se lee igual.

Aún **no** se extraen los ajustes de revelado (`XMP-crs`), salvo el recorte. Tampoco las **regiones de caras** de Lightroom (`XMP-mwg-rs:RegionName` = «Isa», «Javi», `RegionType` = `Face`, con su posición): idea para más adelante (personas).

**Contrastado con Lightroom** (paneles EXIF y Ubicación) con un JPEG, dos HEIC (uno vertical) y un DNG: coinciden todos los campos. Diferencias que no son errores: la exposición se muestra redondeada (1/906 s → 1/900), la Dirección se traduce a 8 sectores de 45° (292,47° → "Oeste"), Lightroom abrevia la marca ("NIKON CORPORATION" → "Nikon"; aquí también, desde `IMAGE_FIELDS_VERSION` 14: `camera_makers.py`) y un campo borrado en Lightroom puede seguir en el archivo (la Dirección de un HEIC). Disponible pero sin columna: `OriginalRawFileName` ("Nombre de archivo original" de un DNG).

**GPS en Lightroom Classic 16** (comprobado el 11/11/2026 con cinco JPEG de prueba y el sidecar de un NEF; para la edición del GPS, hecha ese día): con el EXIF y el XMP distintos, **muestra el XMP** (coordenadas, altitud y dirección). Al editar el GPS de un **JPEG**, lo escribe **en el EXIF** (lo crea si no hay), con sus referencias N/S y E/O, **borra el GPS del XMP** si lo había, **borra `GPSAltitudeRef`** (la altitud queda sin referencia: sobre el nivel del mar) y **no cambia la dirección** que ya había en el EXIF (solo la escribe al crear el GPS): tras «Leer metadatos del archivo», la dirección editada vuelve a la antigua. En el **sidecar de un RAW** lo escribe en el XMP (`exif:GPSLatitude="41,23.244N"`, grados y minutos con decimales; altitud y dirección como fracciones, sin referencia). Lee bien una altitud del XMP con `GPSAltitudeRef` = 1 (−430,0 m).

**Escritura del GPS** (desde el 11/11/2026; `xmp_writer.py`, decisión en [DECISIONES.md](DECISIONES.md)): la latitud, la longitud, la altitud y la dirección editadas se escriben en los grupos de GPS que ya tenga el archivo (`XMP-exif:GPS*`, el EXIF `GPS:GPS*` o los dos) y, si no tiene ninguno, en el EXIF, como Lightroom (ExifTool añade `GPSVersionID`); en un sidecar o un GIF, solo en el XMP. Con su referencia: en el EXIF, `GPSLatitudeRef` N/S y `GPSLongitudeRef` E/W (el valor, sin signo); en el XMP, la latitud y la longitud llevan el signo en el valor (`33,27.414S`); la altitud, sin signo, con `GPSAltitudeRef` 0 (sobre el nivel del mar) o 1 (bajo él); la dirección con `GPSImgDirectionRef` T (norte verdadero). Todo con `#` (sin la conversión de texto de ExifTool). Vaciar un campo borra el valor y su referencia allí donde estén. Se comprueba leyendo como el extractor (`gps_from_tags` de `image/rules.py`) y con margen: 1e-6° en las coordenadas (unos 11 cm), 5 cm en la altitud, 0,01° en la dirección (el EXIF guarda fracciones: 42,682089 vuelve como 42,6820889999).
