# Arca Media — Metadatos de imagen, vídeo y tracks

> Qué se lee de cada archivo, de qué etiqueta y con qué prioridad, y dónde se ve cada dato ([mapa de campos](#mapa-de-campos-qué-se-extrae-y-dónde-se-ve)); equivalencias con Lightroom. Las recetas para añadir campos están en [core/metadata/LEEME.md](../core/metadata/LEEME.md).
> Índice: [INDEX.md](INDEX.md).

**Prioridad entre fuentes** (la recomendación del Metadata Working Group, la que sigue Lightroom). Es el **orden de las etiquetas en cada línea** de `image/fields.py`:

| Tipo de dato | Orden |
|---|---|
| Descriptivos (título, pie de foto, autor, copyright, ubicación) | XMP → IPTC → EXIF |
| GPS: coordenadas, altitud y dirección (desde el 11/11/2026, `IMAGE_FIELDS_VERSION` 9) | XMP → EXIF |
| Técnicos de la toma (cámara, objetivo, exposición, ISO, flash...) | EXIF → XMP |
| Fecha de captura | EXIF `DateTimeOriginal` → EXIF `CreateDate` → XMP `DateCreated` → IPTC → EXIF `ModifyDate` → fecha del archivo (`content_date_source = 'file_mtime'`) |

- **Sidecars**: se buscan `IMG_0001.xmp` (convención de Adobe) y `IMG_0001.CR3.xmp`. Del sidecar solo se toman etiquetas XMP, y pisan a las del XMP incrustado.
- **ExifTool se invoca con** `-j -n -G1 -a -charset utf8 -charset filename=utf8`: JSON, valores numéricos sin traducir (programa de exposición, medición y flash se guardan como **códigos EXIF**; la interfaz los traduce), etiquetas con su grupo (`IFD0:Make`, `XMP-photoshop:City`) y los nombres de archivo en UTF-8 mediante archivo temporal (`-@`).
- **Dónde busca el ejecutable**: variable `EXIFTOOL_PATH` → carpeta `tools/exiftool` → `PATH`.
- **Tamaño**: se guarda "de pantalla" (ya girado si la orientación EXIF es 5 a 8). En los **DNG**, `DefaultCropSize` manda sobre `Composite:ImageSize` (el sensor completo, algo mayor): es lo que Lightroom muestra como "Dimensiones de archivo" (verificado: 3200 × 2128 frente a 3264 × 2140). Solo existe en los DNG, así que no afecta a otros formatos.
- **GPS**: primero el XMP y después el compuesto de ExifTool (los dos, ya con signo), como Lightroom; la pareja latitud/longitud, siempre de la misma fuente (el XMP solo si tiene las dos); la altitud del XMP, con `XMP-exif:GPSAltitudeRef` (1 = bajo el nivel del mar; sin ella, sobre él); se descartan los fuera de rango y `0, 0` (`rules.py`).

## Mapa de campos: qué se extrae y dónde se ve

> Referencia para añadir metadatos (actualizada el 02/11/2026; generada a partir de `IMAGE_FIELDS`, `VIDEO_FIELDS`, `metadata_fields.FIELDS` y `smart_fields`). **Al añadir un campo o mostrarlo en algún sitio, añadir o actualizar su fila.** «—» = no se usa. Las fuentes se prueban de izquierda a derecha («…» = hay más; el detalle completo de las imágenes, en la tabla siguiente). «Regla» = lo calcula `rules.py` a partir de varias etiquetas. Las columnas sin prefijo son de `media_items`.

| Columna | Imagen: de dónde sale | Vídeo: de dónde sale | Inspector «Metadatos» (vistas) | Colección inteligente | Otros usos |
|---|---|---|---|---|---|
| `title` | `XMP-dc:Title` → `IPTC:ObjectName` | `XMP-dc:Title` → `ItemList:Title` → `UserData:Title` … | «Título» (Por defecto, Ubicación; el propio: en blanco si es el nombre del archivo) | Título | — |
| `description` | `XMP-dc:Description` → `IPTC:Caption-Abstract` → `IFD0:ImageDescription` | `XMP-dc:Description` → `ItemList:Description` → `UserData:Description` … | «Pie» (Por defecto, Ubicación) | Descripción | — |
| `creator` | `XMP-dc:Creator` → `IPTC:By-line` → `IFD0:Artist` | `XMP-dc:Creator` → `ItemList:Artist` → `UserData:Artist` … | «Creador» (Por defecto, Ubicación) | Autor | — |
| `copyright` | `XMP-dc:Rights` → `IPTC:CopyrightNotice` → `IFD0:Copyright` | `XMP-dc:Rights` → `ItemList:Copyright` → `UserData:Copyright` | «Copyright» (Por defecto, Ubicación) | Copyright | — |
| `intellectual_genre` | `XMP-iptcCore:IntellectualGenre` → `IPTC:ObjectAttributeReference` | — | — | — | — |
| `scene` | `XMP-iptcCore:Scene` | — | — | — | — |
| `iptc_created_at` | `XMP-photoshop:DateCreated` → `Composite:DateTimeCreated` → `IPTC:DateCreated` | — | — | — | — |
| `sublocation` | `XMP-iptcCore:Location` → `IPTC:Sub-location` | — | «Lugar» (Por defecto, Ubicación) | Lugar | — |
| `city` | `XMP-photoshop:City` → `IPTC:City` | — | «Ciudad» (Por defecto, Ubicación) | Ciudad | — |
| `region` | `XMP-photoshop:State` → `IPTC:Province-State` | — | «Región» (Por defecto, Ubicación) | Región o provincia | — |
| `country` | `XMP-photoshop:Country` → `IPTC:Country-PrimaryLocationName` | — | «País» (Por defecto, Ubicación) | País | — |
| `country_code` | `XMP-iptcCore:CountryCode` → `IPTC:Country-PrimaryLocationCode` | — | «Código país» (Por defecto, Ubicación) | — | — |
| `latitude` | `XMP-exif:GPSLatitude` → `Composite:GPSLatitude` | `Composite:GPSLatitude` → `XMP-exif:GPSLatitude` → `GPSLatitude` | «GPS» (Por defecto, Ubicación) | Tiene coordenadas GPS | — |
| `longitude` | `XMP-exif:GPSLongitude` → `Composite:GPSLongitude` | `Composite:GPSLongitude` → `XMP-exif:GPSLongitude` → `GPSLongitude` | «GPS» (Por defecto, Ubicación) | Tiene coordenadas GPS | — |
| `altitude` | `XMP-exif:GPSAltitude` (con su referencia) → `Composite:GPSAltitude` → `GPS:GPSAltitude` | `Composite:GPSAltitude` → `XMP-exif:GPSAltitude` → `GPSAltitude` | «Altitud» (Por defecto, Ubicación) | — | — |
| `width` | `DefaultCropSize` → `Composite:ImageSize` → `File:ImageWidth` … | `Composite:ImageSize` → `ImageWidth` → `SourceImageWidth` | «Dimensiones» (todas) | Ancho | proporción de la miniatura |
| `height` | `DefaultCropSize` → `Composite:ImageSize` → `File:ImageHeight` … | `Composite:ImageSize` → `ImageHeight` → `SourceImageHeight` | «Dimensiones» (todas) | Alto | proporción de la miniatura |
| `duration` | — | `QuickTime:Duration` → `Composite:Duration` → `Duration` | «Duración» (EXIF) | — | marcador de duración en la tarjeta |
| `content_created_at` | regla (ver «Fecha de captura») | regla (`video/rules.py`) | «Captura» (todas) | Fecha de captura | Selección: «Fecha»; orden de la cuadrícula |
| `content_date_precision` | regla | regla | — | — | — |
| `content_date_source` | regla | regla | — | — | — |
| `timezone_offset` | regla | regla | — | — | — |
| `orientation` | regla (`IFD0:Orientation`) | siempre 1 | — | Orientación | giro de la miniatura |
| `has_xmp_sidecar` | extractor genérico | extractor genérico | — | — | — |
| `photo_details.camera_make` | `IFD0:Make` → `XMP-tiff:Make` | — | «Cámara» (Por defecto, EXIF) | Marca de la cámara | — |
| `photo_details.camera_model` | `IFD0:Model` → `XMP-tiff:Model` | — | «Cámara» (Por defecto, EXIF) | Modelo de la cámara | — |
| `photo_details.body_serial_number` | `ExifIFD:SerialNumber` → `XMP-exifEX:BodySerialNumber` → `XMP-aux:SerialNumber` | — | — | — | — |
| `photo_details.lens_model` | `ExifIFD:LensModel` → `XMP-exifEX:LensModel` → `XMP-aux:Lens` … | — | «Objetivo» (Por defecto, EXIF) | Objetivo | — |
| `photo_details.software` | `IFD0:Software` → `XMP-xmp:CreatorTool` | — | — | — | — |
| `photo_details.user_comment` | `ExifIFD:UserComment` | — | — | — | — |
| `photo_details.focal_length_mm` | `ExifIFD:FocalLength` → `XMP-exif:FocalLength` | — | «Focal» (Por defecto, EXIF) | Distancia focal | — |
| `photo_details.focal_length_35mm` | `ExifIFD:FocalLengthIn35mmFormat` → `XMP-exif:FocalLengthIn35mmFilm` | — | «Focal 35 mm» (Por defecto, EXIF) | — | — |
| `photo_details.f_number` | `ExifIFD:FNumber` → `XMP-exif:FNumber` | — | «Exposición» (Por defecto, EXIF) | Apertura (f/) | — |
| `photo_details.exposure_time_s` | `ExifIFD:ExposureTime` → `XMP-exif:ExposureTime` | — | «Exposición» (Por defecto, EXIF) | Tiempo de exposición | — |
| `photo_details.iso` | `ExifIFD:ISO` → `XMP-exif:ISO` | — | «Sensibilidad» (Por defecto, EXIF) | ISO | — |
| `photo_details.exposure_bias_ev` | `ExifIFD:ExposureCompensation` → `XMP-exif:ExposureBiasValue` | — | «Compensación» (Por defecto, EXIF) | — | — |
| `photo_details.brightness_value` | `ExifIFD:BrightnessValue` → `XMP-exif:BrightnessValue` | — | — | — | — |
| `photo_details.exposure_program` | `ExifIFD:ExposureProgram` → `XMP-exif:ExposureProgram` | — | «Programa» (Por defecto, EXIF) | — | — |
| `photo_details.metering_mode` | `ExifIFD:MeteringMode` → `XMP-exif:MeteringMode` | — | «Medición» (Por defecto, EXIF) | — | — |
| `photo_details.flash_code` | `ExifIFD:Flash` | — | — | — | — |
| `gps_direction` | `XMP-exif:GPSImgDirection` → `GPS:GPSImgDirection` | — | «Dirección» (Por defecto, Ubicación) | — | — |
| `photo_details.digitized_at` | `ExifIFD:CreateDate` → `XMP-xmp:CreateDate` | — | «Digitalización» (todas) | — | — |
| `photo_details.exif_modified_at` | `IFD0:ModifyDate` → `XMP-xmp:ModifyDate` | — | «Modificación» (todas) | — | — |
| `photo_details.flash_fired` | regla (bit 0 de `flash_code`) | — | «Flash» (Por defecto, EXIF) | Flash disparado | — |
| `photo_details.crop_width` | regla (`XMP-crs:Crop*`) | — | «Recorte» (todas) | — | — |
| `photo_details.crop_height` | regla (`XMP-crs:Crop*`) | — | «Recorte» (todas) | — | — |
| `video_details.camera_make` | — | `Keys:Make` → `UserData:Make` → `XML:DeviceManufacturer` … | «Cámara» (Por defecto, EXIF) | — | — |
| `video_details.camera_model` | — | `Keys:Model` → `UserData:Model` → `XML:DeviceModelName` … | «Cámara» (Por defecto, EXIF) | — | — |
| `video_details.software` | — | `Keys:Software` → `UserData:Software` → `Software` … | — | — | — |
| `video_details.video_codec` | — | `CompressorID` → `VideoCodec` → `CompressorName` | «Códec» (EXIF) | — | — |
| `video_details.frame_rate` | — | `VideoFrameRate` → `FrameRate` | «Fotogramas» (EXIF) | — | — |
| `video_details.lens_model` | — | `VideoKeys:LensModel` → `Keys:LensModel` → `LensModel` … | «Objetivo» (Por defecto, EXIF) | — | — |
| `video_details.focal_length_35mm` | — | `VideoKeys:FocalLengthIn35mmFormat` → `Keys:FocalLengthIn35mmFormat` → `FocalLengthIn35mmFormat` | «Focal 35 mm» (Por defecto, EXIF) | — | — |
| `video_details.f_number` | — | `VideoKeys:CameraLensIrisfnumber` → `Keys:CameraLensIrisfnumber` → `CameraLensIrisfnumber` … | — | — | — |

Huecos a la vista (extraídos pero sin mostrar en ningún sitio): `intellectual_genre`, `scene`, `iptc_created_at`, `body_serial_number`, `software` (foto y vídeo), `user_comment`, `brightness_value`, `flash_code` (el detalle del flash: modo, retorno), `timezone_offset` y `content_date_source` (sí aparecen en el texto emergente de «Fecha» de «Selección»), `has_xmp_sidecar` y, en los vídeos, `f_number` (la fila «Exposición» solo lee fotos). Candidatos naturales para las vistas IPTC y Personalizada.

**Datos del usuario** que se leen del archivo (`IMAGE_USER_FIELDS`, ver más abajo): `rating`, `flag` y `color_label` se ven en las **tarjetas** y en la **barra inferior**, y son filtrables en colecciones inteligentes (Valoración, Marca, Etiqueta de color).

**Tracks GPS** (`core/metadata/track/extractor.py`, lector propio de GPX, sin ExifTool): rellena en `media_items` `title` (`<name>`), `description`, `creator` (`<author>`), la fecha de captura (primer punto, en hora local), `latitude`/`longitude`/`altitude` (punto de salida) y `duration`; y en `track_details`: `distance_m`, `elevation_gain_m`, `elevation_loss_m`, `elevation_min_m`, `elevation_max_m`, `started_at`, `ended_at` (UTC), `point_count`, `segment_count`, `track_count`, `route_count`, `waypoint_count`, `is_planned_route`, el recuadro (`min/max_latitude`, `min/max_longitude`), la llegada (`end_latitude`, `end_longitude`), `activity_type` y `creator_app`. No tienen sección en el inspector (son de la biblioteca Tracks); filtrables en colecciones inteligentes: Distancia, Desnivel positivo y negativo, Altitud máxima, Actividad y Creado con. La duración se ve en la tarjeta.

**Campos de imagen** (generado de `IMAGE_FIELDS`; las fuentes se prueban de izquierda a derecha):

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
| `camera_make` | photo_details | `IFD0:Make` → `XMP-tiff:Make` | `text` |
| `camera_model` | photo_details | `IFD0:Model` → `XMP-tiff:Model` | `text` |
| `body_serial_number` | photo_details | `ExifIFD:SerialNumber` → `XMP-exifEX:BodySerialNumber` → `XMP-aux:SerialNumber` | `text` |
| `lens_model` | photo_details | `ExifIFD:LensModel` → `XMP-exifEX:LensModel` → `XMP-aux:Lens` → `Composite:LensID` | `text` |
| `software` | photo_details | `IFD0:Software` → `XMP-xmp:CreatorTool` | `text` |
| `user_comment` | photo_details | `ExifIFD:UserComment` | `text` |
| `focal_length_mm` | photo_details | `ExifIFD:FocalLength` → `XMP-exif:FocalLength` | `real` |
| `focal_length_35mm` | photo_details | `ExifIFD:FocalLengthIn35mmFormat` → `XMP-exif:FocalLengthIn35mmFilm` | `real` |
| `f_number` | photo_details | `ExifIFD:FNumber` → `XMP-exif:FNumber` | `real` |
| `exposure_time_s` | photo_details | `ExifIFD:ExposureTime` → `XMP-exif:ExposureTime` | `real` |
| `iso` | photo_details | `ExifIFD:ISO` → `XMP-exif:ISO` | `integer` |
| `exposure_bias_ev` | photo_details | `ExifIFD:ExposureCompensation` → `XMP-exif:ExposureBiasValue` | `real` |
| `brightness_value` | photo_details | `ExifIFD:BrightnessValue` → `XMP-exif:BrightnessValue` | `real` |
| `exposure_program` | photo_details | `ExifIFD:ExposureProgram` → `XMP-exif:ExposureProgram` | `integer` |
| `metering_mode` | photo_details | `ExifIFD:MeteringMode` → `XMP-exif:MeteringMode` | `integer` |
| `flash_code` | photo_details | `ExifIFD:Flash` | `integer` |
| `gps_direction` | media_items | `XMP-exif:GPSImgDirection` → `GPS:GPSImgDirection` | `real` |
| `digitized_at` | photo_details | `ExifIFD:CreateDate` → `XMP-xmp:CreateDate` | `datetime_text` |
| `exif_modified_at` | photo_details | `IFD0:ModifyDate` → `XMP-xmp:ModifyDate` | `datetime_text` |

Además, las reglas (`image/rules.py`) rellenan `orientation`, `content_created_at`, `content_date_precision`, `content_date_source`, `timezone_offset`, `flash_fired`, `crop_width` y `crop_height`; el extractor genérico rellena `has_xmp_sidecar`.

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

**Escritura de los metadatos descriptivos** (paso C.5; `xmp_writer.py` y `editable_fields.py`, ver [DECISIONES.md](DECISIONES.md)). Se editan en la sección «Metadatos» del inspector (fotos y vídeos de Imagen; vistas «Por defecto» y «Ubicación»). Se escribe en todas las etiquetas de las que se lee: el XMP siempre y las antiguas solo si el archivo ya las tiene. Para saber si ya está al día y para comprobar lo escrito, se lee como el extractor (la primera etiqueta no vacía). Un texto que ExifTool entrega como número («1.50» llega como 1,5) se compara como número. Probado el 10/11/2026, antes de programarlo, con ExifTool 13.59, el extractor de imagen y Lightroom Classic:

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

**Contrastado con Lightroom** (paneles EXIF y Ubicación) con un JPEG, dos HEIC (uno vertical) y un DNG: coinciden todos los campos. Diferencias que no son errores: la exposición se muestra redondeada (1/906 s → 1/900), la Dirección se traduce a 8 sectores de 45° (292,47° → "Oeste"), Lightroom abrevia la marca ("NIKON CORPORATION" → "Nikon"; aquí se guarda tal cual) y un campo borrado en Lightroom puede seguir en el archivo (la Dirección de un HEIC). Disponible pero sin columna: `OriginalRawFileName` ("Nombre de archivo original" de un DNG).

**GPS en Lightroom Classic 16** (comprobado el 11/11/2026 con cinco JPEG de prueba y el sidecar de un NEF; para la edición del GPS, [PENDIENTE.md](PENDIENTE.md) C.5): con el EXIF y el XMP distintos, **muestra el XMP** (coordenadas, altitud y dirección). Al editar el GPS de un **JPEG**, lo escribe **en el EXIF** (lo crea si no hay), con sus referencias N/S y E/O, **borra el GPS del XMP** si lo había, **borra `GPSAltitudeRef`** (la altitud queda sin referencia: sobre el nivel del mar) y **no cambia la dirección** que ya había en el EXIF (solo la escribe al crear el GPS): tras «Leer metadatos del archivo», la dirección editada vuelve a la antigua. En el **sidecar de un RAW** lo escribe en el XMP (`exif:GPSLatitude="41,23.244N"`, grados y minutos con decimales; altitud y dirección como fracciones, sin referencia). Lee bien una altitud del XMP con `GPSAltitudeRef` = 1 (−430,0 m).

**Escritura del GPS** (desde el 11/11/2026; `xmp_writer.py`, decisión en [DECISIONES.md](DECISIONES.md)): la latitud, la longitud, la altitud y la dirección editadas se escriben en los grupos de GPS que ya tenga el archivo (`XMP-exif:GPS*`, el EXIF `GPS:GPS*` o los dos) y, si no tiene ninguno, en el EXIF, como Lightroom (ExifTool añade `GPSVersionID`); en un sidecar o un GIF, solo en el XMP. Con su referencia: en el EXIF, `GPSLatitudeRef` N/S y `GPSLongitudeRef` E/W (el valor, sin signo); en el XMP, la latitud y la longitud llevan el signo en el valor (`33,27.414S`); la altitud, sin signo, con `GPSAltitudeRef` 0 (sobre el nivel del mar) o 1 (bajo él); la dirección con `GPSImgDirectionRef` T (norte verdadero). Todo con `#` (sin la conversión de texto de ExifTool). Vaciar un campo borra el valor y su referencia allí donde estén. Se comprueba leyendo como el extractor (`gps_from_tags` de `image/rules.py`) y con margen: 1e-6° en las coordenadas (unos 11 cm), 5 cm en la altitud, 0,01° en la dirección (el EXIF guarda fracciones: 42,682089 vuelve como 42,6820889999).
