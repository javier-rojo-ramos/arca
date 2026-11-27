# Arca Media — Módulo Música: arquitectura y plan

> Documento del módulo Música (en el código y en la interfaz, el módulo **Audio**: `AudioModule`, biblioteca `audio`). Tiene dos partes: **I, arquitectura** (cómo está hecho y cómo encaja con el resto) y **II, planificación** (fases y pasos, con los códigos `MUS` de [PENDIENTE.md](PENDIENTE.md)).
> **Estado (16/11/2026): diseño acordado con el autor; sin implementar.** El 25/11/2026, acordada la sección «Audio» del inspector (§7.1) y hechos `MUS 1.1` (la base de audio, `core/audio/`), `MUS 1.2` (la tabla `audio_details`) y `MUS 1.3` (el extractor: las canciones se leen solas). El 26/11/2026, acordada la barra izquierda (§7.2) y el orden de los pasos siguientes: `MUS 2.1`, `MUS 4.1`, y después `MUS 2.2` y `2.3`; hechos `MUS 2.1` (la sección «Audio» del inspector, de solo lectura) y `MUS 4.1` («Artistas» y «Años» en la barra, en lugar de «Fechas»), `MUS 2.2` (el orden: «Artista», «Álbum», «Año» y «Título»), `MUS 2.3` (los campos de audio en las colecciones inteligentes y en la barra de filtros) `MUS 3.1` (la carátula como miniatura), `MUS 5.3` (la vista de álbumes) y, adelantado, `MUS 9.1` (la sección «Carátula» del inspector). El 27/11/2026, acordadas las reglas de escritura (§5: en qué etiquetas, la etiqueta preferida, el ID3v1, `MUS 8.4`) y `MUS 6.1` partido en cuatro pasos; hechos `MUS 6.1a` (el tipo de etiqueta como dato) y `MUS 6.1b` (el ID3v1). Todo lo de la parte I que no esté en «Punto de partida» es lo PREVISTO: cuando un paso se entregue, su parte se corrige aquí y pasa a [FLUJOS.md](FLUJOS.md), [ARQUITECTURA.md](ARQUITECTURA.md), [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md) y [METADATOS.md](METADATOS.md). Si el código y este documento no coinciden, manda el código.
> Índice: [INDEX.md](INDEX.md). Decisiones: [DECISIONES.md](DECISIONES.md) (16/11/2026).

## Resumen

**Objetivo**: una funcionalidad básica parecida a la de Mp3tag (ver y editar las etiquetas y las carátulas de las canciones, de una en una y por lotes), con lo que ya da el catalogador (bibliotecas, valoración, marca, color, palabras clave, filtros, colecciones inteligentes), de lo básico a lo avanzado. Cada paso deja la aplicación funcionando, como en Tracks.

**Lo decidido** (el autor, 16/11/2026; el porqué, en [DECISIONES.md](DECISIONES.md)):

| | |
|---|---|
| Biblioteca | **mutagen**, para leer y para escribir (Python puro; ID3 v2.3 y v2.4, FLAC, Ogg/Opus, M4A, carátulas). Licencia GPL: sin problema en uso interno |
| Formatos | **Leer**: MP3, FLAC, M4A y Ogg/Opus. **Escribir**: primero MP3; cada formato más, cuando haya archivos reales con los que compararlo |
| Etiquetas al escribir | Editar escribe en las que el archivo ya tiene (con su versión de ID3v2; el ID3v1, si lo tiene, al día) y no añade ni quita ninguna; si falta el ID3v2, la etiqueta preferida de las Opciones (ID3v2.3 de partida). Cambiar el tipo, solo con «Reescribir etiquetas…» (`MUS 8.4`). Acordado el 27/11/2026: §5 |
| Campos | Título, artista, álbum, artista del álbum, pista / total, disco / total, año, género, compositor y comentario. Letras y BPM, después |
| Listas (varios géneros o artistas) | Primero como texto; las tablas propias, si los archivos reales las piden (se cuenta en `MUS 1`) |
| Marca de cambio pendiente | Sigue siendo un bit por campo (`metadata_edit_pending`); se revisa con Vídeo |
| Valoración, marca, color y palabras clave | En el `.arca.json` de la carpeta, como hasta ahora (POPM, por decidir más adelante) |
| Dónde se guarda lo editado | **En el propio archivo de audio, sin generar copias** (como Mp3tag): regla nueva de los archivos del usuario, [CLAUDE.md](../CLAUDE.md) |
| Renombrar archivos (etiqueta → nombre) | Aparte y más adelante (`MUS 8.3`), con el motor de renombrar y mover de `CAT 4` (acordado el 19/11/2026) |

---

# Parte I — Arquitectura

## 1. Punto de partida (lo que ya existe)

- **Catalogación**: las canciones se catalogan como `MediaType.AUDIO` y van a la biblioteca Música (`library = 'audio'`). El detector (`core/catalog/media_detector.py`) reconoce MP3, M4A, FLAC, Ogg y Opus. En el catálogo del autor hay 20 canciones, todas MP3 (16/11/2026).
- **Módulo**: `controllers/app_modules/audio_module.py` (`AudioModule`, sobre `LibraryModule`), con la barra común (`ui_helpers/sidebars/library_sidebar.py`: biblioteca, carpetas y fechas). La cuadrícula y la vista individual (desde el 19/11/2026, pedida por el autor para entrar y salir como en los demás módulos; desde `MUS 3.1`, la carátula en grande; sin ella, la corchea y el nombre). Orden: `AUDIO_SORT_FIELDS` (`core/catalog/grid_orders.py`; desde `MUS 2.2`, antes los de Vídeo). Filtros: su tipo y, en «Metadatos», desde `MUS 2.3`, «Género», «Artista del álbum» y «Álbum» (antes, fecha y palabras clave; §7.4).
- **Etiquetas**: desde `MUS 1.3` (25/11/2026), el extractor de audio (`core/metadata/audio/extractor.py`, con `core/audio/`) lee las etiquetas, los datos técnicos y la carátula de cada canción al abrir el catálogo. Antes no había extractor y de cada canción solo se sabía lo del archivo.
- **Miniatura**: desde `MUS 3.1`, la carátula incrustada (`core/thumbnails/sources/audio_cover_source.py`), con los cuatro tamaños de siempre; sin carátula, el marcador (§6).
- **Datos del usuario**: valoración, marca, color y palabras clave, en el `.arca.json` de la carpeta (destino `FOLDER_FILE` de `core/userdata/policy.py`).
- **Edición**: el mecanismo «un campo, varios escritores» (14/11/2026; [core/userdata/LEEME.md](../core/userdata/LEEME.md)) ya admite campos sin XMP, de tablas de detalles y solo de algunos tipos de archivo. El grupo «Audio» de las colecciones inteligentes (`core/catalog/smart_fields.py`), con sus 15 campos desde `MUS 2.3` (§7.4).
- **Las imágenes de una carpeta de música** (`cover.jpg`, `folder.jpg`) no entran en el catálogo: la carpeta es de Música y solo cataloga audio.

## 2. Dónde vive cada cosa

Como en Tracks: lo que no necesita ni Qt ni la base de datos, en un paquete de `core/` propio; el extractor, con los demás; el escritor, con los demás escritores.

| Qué | Dónde | Notas |
|---|---|---|
| Tabla campo ↔ etiqueta de cada formato; leer y escribir etiquetas y carátulas con mutagen | `core/audio/` (sin Qt ni BD): `tag_map.py` (la tabla), `tag_reader.py` (`read_audio`), `picture_types.py` (los tipos de imagen); desde `MUS 1.1`. `tag_set.py` (el tipo de etiqueta y en qué etiquetas se escribe; desde `MUS 6.1a`) e `id3v1.py` (el ID3v1, desde `MUS 6.1b`). Previsto: `tag_writer.py` (el motor, `MUS 6.1c`) | **Una sola tabla** para el extractor y para el escritor: los dos entienden lo mismo |
| Extractor | `core/metadata/audio/`: `extractor.py` (con `AUDIO_FIELDS_VERSION`; no hace falta un `fields.py`: la tabla es `core/audio/tag_map.py`) e `inspect_cli.py` | `MetadataExtractor` con `details_table = "audio_details"`, como `TrackExtractor`; registrado en `core/metadata/registry.py` (si mutagen está instalado) |
| Tabla de detalles | `core/catalog/catalog_schema.py`, la siguiente migración libre (la 5 fue el registro de operaciones de `CAT 4` y la 6, las carpetas de `CAT 5`) | `audio_details` (§3) |
| Consultas | `core/catalog/` | Datos de las secciones del inspector (`audio_stats.py`, desde `MUS 2.1`; `cover_stats.py`, desde `MUS 9.1`), valores de las secciones de la barra, filas de la vista de lista |
| Origen de la miniatura | `core/thumbnails/sources/audio_cover_source.py` (desde `MUS 3.1`) | Se registra en `core/thumbnails/registry.py` |
| Campos editables | `core/userdata/editable_fields.py` | Una línea por campo, con `table="audio_details"` y `media_types` de audio |
| Escritor | `core/userdata/audio_writer.py` (nuevo) | Declara qué campos sabe guardar en cada formato; el trabajo que escribe sigue siendo el de `sync.py` |
| Módulo y barra | `controllers/app_modules/audio_module.py`, `ui_helpers/sidebars/sections/` | Secciones nuevas dadas de alta en `section_registry.py`; desde `MUS 4.1`, «Artistas» y «Años» (`music_sections.py`, con los árboles de `core/catalog/music_browse.py`) |
| Inspector | `ui_helpers/inspector/audio_section.py` (desde `MUS 2.1`) y `cover_section.py` (desde `MUS 9.1`, con el recuadro `ui_helpers/widgets/cover_image.py`) | Como `track_section.py`; de la biblioteca `audio` (salen también en el Catálogo con canciones seleccionadas); los textos, en `formatting.py`; la imagen de la carátula, de la caché de miniaturas (`FullImageLoader`) |
| Vista de lista | `ui_helpers/widgets/` y `ui_helpers/models/` (nuevos) | Una vista más del centro (`CenterView`); sirve a otros módulos |

`core/audio/` y `core/metadata/audio/` no usan Qt. La interfaz no toca mutagen: lee del catálogo y pide los cambios por la cola de edición.

## 3. Datos

### 3.1 Columnas comunes (`media_items`)

Lo que ya tiene columna común se guarda ahí, para que el filtro de texto, el orden y las colecciones inteligentes funcionen sin nada nuevo:

| Etiqueta | Columna | Notas |
|---|---|---|
| Título | `title` | Si la canción no lo tiene, se queda el nombre del archivo (como en las fotos) |
| Artista | `creator` | |
| Año (o fecha) | `content_created_at` | Con `content_date_precision` según lo que traiga la etiqueta (`year` casi siempre); sin año, sin fecha (§4). Ordena bien y «Selección» la muestra como el año. La sección «Fechas» la pone en el 1 de enero: en Música la sustituye «Años» (`MUS 4.1`, §7.2) |
| Comentario | `description` | |
| Duración | `duration` | Segundos |

### 3.2 `audio_details` (migración 7)

Una fila por canción (`media_id`, clave primaria y ajena con borrado en cascada, como `track_details`). Creada en `MUS 1.2` (25/11/2026; `core/catalog/catalog_schema.py`, migración 7), con los `CHECK` de los números; sin índices propios por ahora:

| Columna | Tipo | Qué es |
|---|---|---|
| `album` | TEXT | Álbum |
| `album_artist` | TEXT | Artista del álbum |
| `track_number`, `track_total` | INTEGER | Pista / total |
| `disc_number`, `disc_total` | INTEGER | Disco / total |
| `genre` | TEXT | Género (si el archivo trae varios, unidos en un texto: §3.4) |
| `composer` | TEXT | Compositor |
| `codec` | TEXT | Formato del audio (`mp3`, `flac`, `aac`, `alac`, `vorbis`, `opus`) |
| `codec_detail` | TEXT | La descripción del formato que da mutagen, si la da («AAC LC»), para la fila «Formato» |
| `bitrate` | INTEGER | Bits por segundo |
| `bitrate_mode` | TEXT | `cbr`, `vbr` o `abr` (solo MP3, si se sabe), para la fila «Calidad» («VBR · 277 kbps») |
| `sample_rate` | INTEGER | Hz |
| `channels` | INTEGER | |
| `bit_depth` | INTEGER | Solo en los formatos sin pérdida |
| `lossless` | INTEGER (0/1) | |
| `picture_count` | INTEGER | Cuántas imágenes trae el archivo (0 = sin carátula; sustituye a `has_cover`) |
| `cover_type` | TEXT | Tipo de la carátula (clave de `core/audio/picture_types.py`; en M4A, que no tiene tipos, la portada, como Mp3tag) |
| `cover_mime` | TEXT | Formato de la carátula (`image/jpeg`, `image/png`) |
| `cover_width`, `cover_height` | INTEGER | Tamaño de la carátula en píxeles (leído de su cabecera, con Pillow) |
| `cover_bytes` | INTEGER | Peso de la carátula |
| `cover_hash` | TEXT | Huella de la carátula (un resumen de sus bytes): dos canciones con la misma huella tienen la misma carátula |
| `tag_type` | TEXT | Tipo de etiqueta, como la columna «Tag» de Mp3tag (`ID3v2.3`, `ID3v2.4 + ID3v1`, `Vorbis`, `MP4`) |

Los ocho primeros son del bloque editable (los escribe el extractor y, cuando se editan, la aplicación: no se pisan al releer si están pendientes); los técnicos, solo del extractor.

**La carátula en el catálogo** (acordado con el autor el 25/11/2026): de las imágenes de un archivo, el catálogo guarda solo **cuántas hay** y los datos de **la carátula**: la primera de tipo «Portada» o, si no hay ninguna, la primera imagen (`AudioInfo.cover`). Con eso, las tarjetas, el inspector con varias canciones y la fila «Imagen» (§6) se rellenan sin abrir ningún archivo, y se puede filtrar («Sin carátula», «Carátula de menos de 500 px»). Las demás imágenes no se guardan: solo hacen falta con una canción seleccionada (la sección de la carátula enseñaría «1 de 3») y entonces se lee ese archivo, en segundo plano. Si un día hiciera falta filtrar por ellas («con contraportada»), una tabla con una fila por imagen. Las columnas de la carátula y las técnicas son del extractor; al cambiar una imagen desde la aplicación (`MUS 9`), la canción se relee.

### 3.3 Tabla campo ↔ etiqueta (`core/audio/`)

Hecha en `MUS 1.1` (`core/audio/tag_map.py`, con las claves que solo se leen: «ALBUM ARTIST», «TOTALTRACKS», «DESCRIPTION»...; los detalles de cada campo, en su cabecera). Leídas con ella las 75 canciones del autor (MP3, M4A, FLAC y Ogg Vorbis) sin errores y comparadas con Mp3tag el 25/11/2026 (todo igual; en MP4, Mp3tag enseña el total de la pista en otro campo, `TOTALTRACKS`, y no en «Pista»):

| Campo | ID3 (MP3) | Vorbis (FLAC, Ogg, Opus) | MP4 (M4A) |
|---|---|---|---|
| Título | `TIT2` | `TITLE` | `©nam` |
| Artista | `TPE1` | `ARTIST` | `©ART` |
| Álbum | `TALB` | `ALBUM` | `©alb` |
| Artista del álbum | `TPE2` | `ALBUMARTIST` | `aART` |
| Pista / total | `TRCK` («3/12») | `TRACKNUMBER` y `TRACKTOTAL` | `trkn` |
| Disco / total | `TPOS` | `DISCNUMBER` y `DISCTOTAL` | `disk` |
| Año | `TDRC` (v2.4) o `TYER` (v2.3) | `DATE` | `©day` |
| Género | `TCON` | `GENRE` | `©gen` |
| Compositor | `TCOM` | `COMPOSER` | `©wrt` |
| Comentario | `COMM` | `COMMENT` | `©cmt` |
| Carátula | `APIC` (portada frontal) | Bloque de imagen | `covr` |

### 3.4 Listas

Un archivo puede traer varios géneros o varios artistas. En la primera versión se guardan **como un texto**, unidos con un separador fijo (`«; »`: decidido con el autor el 25/11/2026; ver abajo); al escribir un campo editado, se separa de nuevo en los formatos que admiten varios valores. `MUS 1.4` cuenta cuántas canciones reales traen varios valores: si la navegación por géneros o artistas los necesita por separado, se pasan a tablas propias, como las palabras clave (decisión del 14/11/2026). **Hecho en `MUS 1.4`**: en las 4 876 canciones del autor (26/11/2026; 4 558 MP3, 291 M4A, 14 FLAC y 13 Ogg), ningún género ni artista trae varios valores (ni «; », «/», «feat.» ni comas; 26 géneros distintos) y solo cinco artistas llevan «&», que son nombres de grupo; ninguna tiene artista del álbum, compositor ni comentario. Etiquetas: ID3v2.3 (4 558), MP4 (291) y Vorbis (27). Se quedan **como texto** (M1, cerrada el 26/11/2026); si un día llegan colecciones con varios valores, se vuelve a contar.

**El separador, «; » y no la coma de las palabras clave**: en una palabra clave la coma está prohibida, pero en un artista no («Earth, Wind & Fire», «Crosby, Stills, Nash & Young»); si el escritor (`MUS 6`) separase por comas, un artista así acabaría como varios. El punto y coma casi no aparece en un nombre. Las palabras clave siguen con la coma (como Lightroom). En las 75 canciones del autor (25/11/2026) ninguna trae varios valores ni comas en esos campos.

### 3.5 Versiones

`AUDIO_FIELDS_VERSION` (nueva; se guarda en `media_items.scan_version`): al subirla, las canciones se releen solas al abrir el catálogo, como los GPX. Va a la tabla de versiones de [INDEX.md](INDEX.md) y a la lista de [CLAUDE.md](../CLAUDE.md). Las carátulas como miniatura no subieron `THUMBNAIL_VERSION` (`MUS 3.1`): las canciones nunca habían tenido miniatura y ya estaban pendientes; al registrar su origen, se generan solas.

## 4. Lectura

- `AudioExtractor.extract(path)` abre el archivo con mutagen (`read_audio`), traduce las etiquetas con la tabla de §3.3 y entrega las columnas comunes y las de `audio_details`. No usa ExifTool (como el de tracks).
- **La fecha** (decidido con el autor el 25/11/2026): «2001» se guarda como el 1 de enero de 2001 con precisión `year`; «2001-05», `month`; «2001-05-04», con o sin hora, `day` (la hora de una etiqueta no es la de la grabación: iTunes pone la medianoche en UTC). Su origen, la familia de la etiqueta (`id3`, `vorbis` o `mp4`). **Sin año, sin fecha**: no se usa la del archivo, como en las fotos, porque es cuándo se copió o se convirtió la canción, no el año del disco.
- Un archivo sin etiquetas no es un error: se guardan los datos técnicos y el título queda como el nombre del archivo. Un archivo dañado o que mutagen no entiende, a `scan_errors`, como los demás.
- **Un extractor nunca escribe datos del usuario**: valoración, marca, color y palabras clave siguen saliendo del `.arca.json`.
- **Datos técnicos** (duración, formato, kbps, kHz, canales, bits): de mutagen, que ya se necesita para las etiquetas; basta para las filas de §7.1. **MediaInfo** (propuesta del autor el 25/11/2026) no se usa por ahora: añadiría una biblioteca nativa que empaquetar en tres sistemas (`GEN 5`) sin nada nuevo que mostrar. Si se elige para Vídeo (`VID 1.1`), podría servir aquí de respaldo (MKA, que mutagen no lee; WMA) o para unos «datos técnicos ampliados» (codificador, VBR o CBR...). Por eso, en `AudioInfo` los datos técnicos van aparte: otra fuente los podría rellenar sin tocar el resto.
- Diagnóstico: `python -m core.metadata.audio.inspect_cli archivo` enseña las etiquetas tal cual las da mutagen y los campos ya traducidos, para comparar con Mp3tag.

## 5. Escritura

**Regla** (el autor, 16/11/2026): las etiquetas y las carátulas se guardan **en el propio archivo, sin generar copias**, como hace Mp3tag y como ya se hace con el XMP de un JPEG o un HEIC.

- **Por la cola de siempre**: editar cambia el catálogo y marca el campo como pendiente; el trabajo de `sync.py` lo escribe en segundo plano, lo comprueba releyendo y quita la marca. La opción «Escribir los cambios en los archivos» y la pregunta de las tandas grandes valen igual.
- **Un campo, varios escritores**: el escritor de audio declara qué campos sabe guardar en cada formato. Lo que no sabe (o un formato que aún no escribe) va al `.arca.json`, como hoy.
- **Solo lo editado**: se cambian los campos pendientes y se conservan las etiquetas que la aplicación no conoce. Con mutagen, eso obliga a abrir el ID3 sin convertirlo y guardarlo en la misma versión: guardando como dice su documentación se perderían marcos ([TRAMPAS.md](TRAMPAS.md), 27/11/2026).
- **En qué etiquetas** (acordado con el autor el 27/11/2026, a la vista de su configuración de Mp3tag; [DECISIONES.md](DECISIONES.md); la regla, en `core/audio/tag_set.py`, `tags_for_edit`):
  1. Editar escribe en las etiquetas que el archivo **ya tiene**, y en cada una solo los campos editados. Nunca añade ni quita una etiqueta ni cambia la versión del ID3v2.
  2. Solo si le **falta la principal** (un MP3 sin ID3v2, o solo con ID3v1) se añade la **etiqueta preferida**, completa (con todo lo que se lee del archivo). Lo que tenía se queda: el ID3v1, al día; el APEv2 (que no se lee), sin tocar. Un ID3v2.2 cuenta como si faltara (mutagen no lo escribe).
  3. **Cambiar el tipo** (convertir de versión, quitar el ID3v1 o el APEv2, limpiar) es solo cosa de «Reescribir etiquetas…» (`MUS 8.4`), a petición y con vista previa.

  | El archivo tiene | Después de editar |
  |---|---|
  | ID3v2.3 / ID3v2.4 | Lo mismo |
  | ID3v2.3 + ID3v1 | Lo mismo, las dos al día |
  | Solo ID3v1 | ID3v2.3 (nueva, completa) + ID3v1 al día |
  | Nada | La preferida: ID3v2.3 (más ID3v1, si se marca) |
  | ID3v2.3 + APEv2 | Lo mismo; el APEv2, sin tocar |
  | Vorbis (FLAC, Ogg), MP4 (M4A) | La suya (`MUS 6.3`, `6.4`) |
- **La etiqueta preferida**, en Opciones > Música (`MUS 6.1d`): «ID3v2.3 UTF-16» (de partida) o «ID3v2.4 UTF-8», y la casilla «Incluir ID3v1» (desmarcada), como el Mp3tag del autor; la «ID3v2.3 ISO-8859-1» de Mp3tag no se ofrece. Se usa al crear una etiqueta donde falta y como destino de `MUS 8.4`. Lo que se escribe va en la codificación de su versión: UTF-16 en v2.3, UTF-8 en v2.4.
- **El ID3v1**, adaptado a sus límites y cambiando solo lo editado (`core/audio/id3v1.py`, hecho en `MUS 6.1b`): 30 caracteres en título, artista y álbum, 28 en el comentario (los otros dos bytes son la pista); el año en 4 cifras; la pista hasta 255, sin total; el género, de su lista (192, la de Winamp; con varios, el primero; si no está, sin género: de los 26 del autor, «Pop Folk», «BSO» y «Opera Pop»); disco, artista del álbum y compositor no existen; en Latin-1 (caben los acentos, la ñ, «» y ¿¡), con los caracteres que tienen un equivalente claro cambiados (’ → ', — → -, … → ...; una letra con un acento que Latin-1 no tiene, sin él: ř → r) y «?» en el resto. Lo no editado queda como estaba (también un texto en otra codificación o un género fuera de la lista); la única excepción la pone el formato: al añadir una pista a un ID3v1.0, su comentario pasa a 28 caracteres. Se comprueba contra el valor ya adaptado. Comprobado con el lector: lo que compone, mutagen lo lee igual (salvo el comentario: [TRAMPAS.md](TRAMPAS.md)).
- **El audio no se toca**: tras escribir se comprueba, además de las etiquetas, que los bytes del audio son los mismos que antes.
- **Sin riesgo de perder o corromper un archivo** (decidido por el autor el 16/11/2026): mutagen escribe sobre el propio archivo, así que la aplicación escribe en un **archivo temporal de la misma carpeta, lo comprueba y sustituye el original** (lo que hace ExifTool con las fotos). Si algo falla, el original sigue intacto y el temporal se borra. «Sin generar copias» quiere decir que no quedan archivos duplicados, no que no haya temporal.
- **Fecha de modificación**: cambia, como en las fotos; el catálogo anota el tamaño y la fecha nuevos sin releer ni regenerar la miniatura.
- **Archivo cambiado fuera** (Mp3tag, otro programa): la regla de las fotos: se escribe lo pendiente y el archivo queda para releer.

## 6. Carátulas

- **Como miniatura** (hecho en `MUS 3.1`, 26/11/2026): la carátula incrustada es el origen (`AudioCoverSource`, con mutagen: la misma imagen cuyos datos guarda el catálogo, por `tag_reader.cover_index`), con su proporción (casi siempre cuadrada) en el hueco cuadrado del marcador, la escalera de tamaños de siempre y sin ampliar por encima del original. Sin carátula, el marcador: **no es un error** (no sale en la lista de errores; se vuelve a mirar si el archivo cambia, p. ej. al añadirle una en `MUS 9`). La vista individual, sin 1:1 (el zoom sigue siendo de las fotos). De reserva, si se decide (M2), `folder.jpg` / `cover.jpg` de la carpeta.
  - **En la caché, como las fotos** (acordado con el autor el 25/11/2026): el motor de miniaturas extrae la carátula de cada canción y guarda sus tamaños en `cache/audio/...`, por el `id` de la canción, igual que `cache/photo/...`. La cuadrícula, la vista individual y el inspector la leen de la caché, nunca del archivo, sin nada nuevo en ellos; al cambiar la carátula, su miniatura se regenera como la de una foto editada. La vista individual, del tamaño mayor (a 1:1, el original, del archivo); el inspector, del de 1200 (al hacer `MUS 9.1`, en lugar del de 480 previsto: nítida también con la pantalla escalada o el panel ancho).
  - **La carátula del álbum**: no hay caché propia. La tarjeta de un álbum (la vista de álbumes, `MUS 5.3`) usa la miniatura de su primera canción que la tiene. La huella (`cover_hash`) servirá para encontrar álbumes con carátulas distintas.
  - **Lo que cuesta** (medido en `MUS 3.1`): con la música del autor (4 876 canciones con 287 carátulas distintas), unos 220–270 KB por canción con los cuatro tamaños: entre 1,1 y 1,3 GB en total; sin el de 2560, unos 730 MB; con una sola copia por carátula, unos 76 MB. El autor eligió los cuatro tamaños, como las fotos, por si más adelante se amplía la carátula a 1:1 (26/11/2026). Si el espacio llega a importar, una sola copia por huella (otra organización de la caché, el trabajo de miniaturas, la cuadrícula y el borrado): `MUS 3.3`, opcional.
- **En el inspector** (`MUS 9`; la sección «Carátula», de solo lectura, hecha en `MUS 9.1` el 26/11/2026): la carátula en grande; cambiarla arrastrando una imagen, con «Elegir…», pegándola o desde `folder.jpg`, para una canción, para la selección o para el álbum; extraerla a un archivo; quitarla.
  - **Cómo se ve** (acordado con el autor el 25/11/2026, tras ver una muestra): la imagen a todo el ancho, con el mismo margen a la izquierda y a la derecha que el resto de filas (8 px), y debajo **dos filas**: «Tipo» (un desplegable) e «Imagen» (formato, tamaño y peso: «JPEG · 600 × 600 · 25 KB», con un botón a la derecha para hacerla cuadrada: M9). Si «Imagen» resulta larga, se divide en dos filas.
  - **Cómo quedó en `MUS 9.1`** (26/11/2026, con el autor): el recuadro, siempre cuadrado (la sección no cambia de alto al pasar de una canción a otra), con las no cuadradas centradas y las pequeñas ampliadas hasta llenarlo (a prueba: `ENLARGE_SMALL`); una raya fina alrededor (`BORDER`; el autor la dejó al verificarla); «Tipo», como texto (el desplegable, cuando se pueda cambiar); «Imagen» en una fila (a 354 px cabe; más estrecho, se recorta, como «Calidad»). Con varias canciones, cada fila con su regla, como «Audio» (`core/catalog/cover_stats.py`): «Tipo», el común o «Varios»; «Imagen», la común o «Varios», con el porqué al pasar el ratón («2 carátulas distintas», «1 canción sin carátula»); la imagen, solo si es la misma en todas (si no, el marcador). Sin carátula, el marcador y «Sin carátula». Si el archivo trae varias imágenes, «Tipo» lo dice al pasar el ratón. Mientras se genera la miniatura, el marcador; la carátula llega sola.
  - **Tipos** (los de ID3 y FLAC, en el orden de Mp3tag; textos propuestos, M7): Portada, Contraportada, Otra, Icono, Folleto, Soporte (CD, vinilo), Solista, Artista, Director, Grupo, Compositor, Letrista, Lugar de la grabación, Durante la grabación, Durante la actuación, Captura de vídeo, Ilustración, Logotipo del grupo y Logotipo de la discográfica. M4A no tiene tipos: sus imágenes se leen como «Portada», como Mp3tag (decidido por el autor el 25/11/2026), y el desplegable sale desactivado.
  - **Dónde va** (M8, decidida el 26/11/2026): en su propia sección «Carátula», detrás de «Audio» (se pliega, se oculta y se mueve como las demás); sus acciones (añadir, quitar, cambiar el tipo, extraer...), en un botón de su cabecera, con `MUS 9.2`–`9.4`.
- **Al guardarla**: se prepara como JPEG con un tamaño máximo (por decidir: 1000–1400 px) y sustituye a la portada frontal que hubiera. Se escribe por la misma cola que las etiquetas y se rehacen sus miniaturas.

## 7. Interfaz

- **Barra izquierda** (`MUS 4`): «Biblioteca», «Artistas», «Carpetas», «Años» y «Géneros»; sin «Fechas». Cómo es, en §7.2.
- **Centro**: la cuadrícula (con la carátula) y la **vista de lista** (`GEN 18`, común a todos los módulos; lo de Música, en `MUS 5`), estilo Mp3tag: columnas a elegir, orden por columna y selección múltiple, compartida con la cuadrícula. La **vista de álbumes** (desde `MUS 5.3`): §7.5.
- **Inspector**: sección «Audio» (`MUS 2`), primero de solo lectura; con `MUS 7`, editable, también con varias canciones («Varios» y el aviso «Edición múltiple», como en «Metadatos»). Palabras clave y clasificación, como en todos los módulos. Cómo es, en §7.1.
- **Ventanas, solo para lo pesado o por lotes** (plan de interfaz): las herramientas de `MUS 8`.

### 7.1 La sección «Audio» del inspector

Acordada con el autor el 25/11/2026, tras ver una muestra hecha con las piezas reales del inspector (tres variantes, a su ancho de 354 px). Las filas de siempre: la etiqueta a la izquierda y el valor a la derecha, en cajas que parecen texto hasta pasar el ratón o entrar en ellas, como en «Metadatos». **Una fila por campo** (la variante A), en este orden:

```
▼ AUDIO
   Título              04 De Mayor - Alicia
   Artista             Enrique Bunbury
   Álbum               Singles
   Año                 2001
   Pista               22 / 25
   Disco               1 / 2
   Género              Rock
   Artista del álbum
   Compositor
   Comentario          (caja de varias líneas, como «Pie»)
   ────────────────────────────────────────
   Duración            4:12
   Formato             MP3
   Calidad             320 kbps · 44,1 kHz · Estéreo
   Etiqueta            ID3v2.3 + ID3v1
```

- Los diez de arriba son los campos de la canción: de solo lectura en `MUS 2.1` y editables desde `MUS 7`. Los cuatro de debajo de la raya son datos técnicos, siempre de solo lectura (los da el extractor).
- La pista y el disco, cada uno con su total en la misma caja («22 / 25»), como en la muestra.
- Descartadas: el año, la pista y el género en una sola fila, como en Mp3tag (al género le quedaban unos 45 px), y el año, la pista y el disco en una fila con el género aparte.
- **Hecha en `MUS 2.1`** (26/11/2026; `audio_section.py`, de solo lectura; los datos, de `core/catalog/audio_stats.py`). Decidido por el autor al hacerla: «Artista del álbum», la etiqueta más larga del inspector, ensancha la columna de etiquetas de todas las secciones de 87 a 97 px (los valores de «Metadatos» y «Track», 10 px a la derecha); «Calidad» con el modo de la tasa de bits, también «CBR» («CBR · 128 kbps · 44,1 kHz · Estéreo»); el comentario, en una línea hasta `MUS 7` (entero en el texto emergente); el título de la sección, «Audio» con una canción y con varias.
- **Con varias canciones**: cada campo, el valor común, «Varios» en gris (distintos, o unas con valor y otras sin él) o nada, con las reglas de «Metadatos»; la duración, sumada («Suma de las 13 canciones», en el emergente); en «Calidad», la tasa como intervalo («114 – 136 kbps · 44,1 kHz · Estéreo») y, de lo demás, solo lo que tienen igual todas. Al ancho de 354 px, dos textos de «Calidad» no caben y se recortan con «…» (enteros en el emergente): el de un álbum VBR («VBR · 239 – 277 kbps · 44,1 kHz · Estéreo», 227 px para 209) y, previsiblemente, el de un FLAC de más de 1.000 kbps.
- La carátula, en su propia sección «Carátula», detrás de «Audio» (§6; `MUS 9.1`).
- En el registro de secciones, detrás de las comunes (`order` de 400 en adelante: [DECISIONES.md](DECISIONES.md), 25/11/2026).

### 7.2 La barra izquierda

Acordada con el autor el 26/11/2026 (el porqué, en [DECISIONES.md](DECISIONES.md)): **la barra tiene recorridos fijos y la combinación libre está en la barra de filtros**. La barra sirve para ir a un sitio (eliges un álbum y ves sus canciones); quien quiera, p. ej., Género → Año → Artista → Álbum lo tiene en las columnas de «Metadatos» de la barra de filtros, con los campos de audio desde `MUS 2.3`, y lo puede guardar como ajuste personalizado. No se hace un árbol personalizable en la barra.

| Sección | Qué | De partida | Paso |
|---|---|---|---|
| «Biblioteca - Audio» | Como hoy | Visible | — |
| «Carpetas» | Como hoy | Visible | — |
| «Artistas» | Artista del álbum ▸ álbum | Visible, debajo de «Carpetas» | `MUS 4.1` |
| «Años» | Año ▸ «Artista - Álbum» | Plegada | `MUS 4.1` |
| «Géneros» | Una lista simple | Por decidir en su paso | `MUS 4.2` |

- **«Fechas» sale de Música**: su año ▸ mes ▸ día no sirve con canciones que casi siempre solo tienen el año. Sigue en Tracks y en Vídeo, donde el día sí importa.
- **Los álbumes de un artista, por año** (la discografía en orden): «2001 · Destrangis», «2003 · Estopa Grandes Éxitos». Un álbum con canciones de varios años, con los dos extremos: «1974 – 2011 · Grandes Éxitos» (pedido por el autor al aprobar el plan); para ordenar, el más antiguo. Sin año, solo el nombre, al final.
- **En «Años»**, del más reciente al más antiguo; sus álbumes, con su artista delante, «Estopa - Destrangis», ordenados por artista y después por álbum; los que no tienen artista, solo con el nombre, al final del año. Cada fila es un artista y su álbum, como en «Artistas»: un recopilatorio con artista del álbum queda en una fila («0 Varios - BSO The Matrix») y uno sin él se reparte entre sus artistas (cambiado por el autor al verlo, el 26/11/2026; antes, solo el nombre del álbum, con el artista al pasar el ratón).
- **El orden de las secciones**: en todos los módulos, primero «Biblioteca» y «Carpetas» y después las de cada uno (pedido por el autor al verlo, el 26/11/2026; antes, «Artistas» iba delante de «Carpetas»).
- **Los recopilatorios**: se agrupan por el «Artista del álbum» y, si no lo tienen, por el artista. Las bandas sonoras del autor quedan bajo «0 Varios»; un recopilatorio sin artista del álbum se reparte entre sus artistas.
- **Lo que falta**: «Sin álbum» al final de cada artista y de cada año; «Sin artista» (sin artista del álbum ni artista) y «Sin año», al final de su sección.
- **Los textos** se comparan sin mayúsculas ni acentos, como las reglas: «Estopa» y «ESTOPA» son la misma fila.
- **Cada fila es una colección fija**, como las de «Fechas»: la biblioteca y las reglas de «Artista del álbum» y «Álbum» (o la fecha y el álbum), con los dos campos del grupo «Audio» de las colecciones inteligentes, adelantados de `MUS 2.3`. Así cuenta exactamente lo que muestra la cuadrícula. «Artista del álbum» cuenta el artista si la canción no lo tiene, también en las colecciones (como foobar2000; decidido por el autor el 26/11/2026).
- **Las canciones de un álbum**, al elegirlo: por disco y pista con el orden de partida de Música, «Artista» (desde `MUS 2.2`), sin cambiar el orden al elegir una fila (el de cada módulo se recuerda; decidido por el autor el 26/11/2026).
- **Hecho en `MUS 4.1`** (26/11/2026): `core/catalog/music_browse.py`, `ui_helpers/sidebars/sections/music_sections.py`, `audio_module.py` (`with_dates = False`) y el registro de secciones.
- Las secciones se pliegan, se ocultan y se reordenan por módulo como las demás (`section_registry.py`): otra colocación no necesita código.

### 7.3 El orden de la cuadrícula

Hecho en `MUS 2.2` (26/11/2026; acordado con el autor). Campos del desplegable de Música, en este orden (`AUDIO_SORT_FIELDS`, `core/catalog/grid_orders.py`):

| Campo | Ordena por |
|---|---|
| «Artista» (el de partida) | Artista del álbum (o, sin él, el artista; la misma expresión que la sección «Artistas»), año, álbum, disco y pista |
| «Álbum» | Álbum, artista del álbum, disco y pista |
| «Año» | Año, artista del álbum, álbum, disco y pista |
| «Título» | El título |
| «Tasa de bits» (desde `MUS 2.3`, pedido por el autor) | La tasa (en los VBR, la media): hacia arriba, la peor calidad primero |
| «Duración», «Nombre», «Extensión», «Tamaño», «Fecha de modificación», «Fecha de importación» | Los de siempre |

- **La flecha invierte solo el primer criterio**: el resto (y el desempate por nombre) va siempre hacia arriba. «Año ↓»: los discos más recientes primero, cada uno con sus pistas en orden. En los demás módulos, la flecha invierte la lista entera.
- **Los textos, sin mayúsculas ni acentos** (`arca_fold`), como las secciones de la barra: «Álvaro», entre «Alberto» y «Ana».
- **Lo que no tiene el dato, al final**, en las dos direcciones.
- **Sin «Hora de captura»** (en una canción es el año: «Año») **ni «Pista» suelta** (con varios álbumes juntaría todas las pistas 1; dentro de un álbum ya la ordena «Álbum»).
- **Sin cambios automáticos** al elegir una fila de la barra: con «Artista» o «Álbum», un álbum sale por disco y pista.

### 7.5 La vista de álbumes

Hecha en `MUS 5.3` (26/11/2026; idea del autor, acordada con él; el porqué, en [DECISIONES.md](DECISIONES.md)). Es la primera tarjeta agrupada (`GEN 17`).

```
┌────────────────┐
│    carátula    │
│   13 canciones │  ← en lugar de la duración
└────────────────┘
  Destrangis        ← el álbum, sin extensión
```

- **Una vista más**: el botón «Álbumes» (un disco), entre «Cuadrícula» y «Vista individual»; Música empieza en la cuadrícula. Es la misma cuadrícula, con su deslizador y las carátulas de la caché: una tarjeta por álbum (`core/catalog/album_rows.py`).
- **Qué álbumes**: los de lo elegido en la barra, con el filtro; cada uno cuenta solo sus canciones que lo cumplen. Agrupados como «Artistas» (artista del álbum o, sin él, el artista, y álbum; sin mayúsculas ni acentos); las canciones sin álbum, un «Sin álbum» por artista. En el orden del desplegable (cada álbum, donde va su primera canción).
- **La tarjeta**: la carátula de su primera canción que la tiene; el nombre del álbum; «13 canciones» en la insignia; al pasar el ratón, «Estopa · 2001 · 13 canciones · 52:10» (`ui_helpers/models/album_cards.py`). Las estrellas, la marca, el color y el círculo, el valor común de sus canciones (o nada, si difieren).
- **Un álbum son sus canciones**: seleccionarlo es seleccionarlas (el inspector, como con las canciones seleccionadas); lo que se haga, a todas: clasificar, palabras clave, arrastrar a una colección, eliminar.
- **Entrar y volver**: doble clic, Intro o «adelante», sus canciones en la cuadrícula (por disco y pista, con su fila elegida en «Artistas»); Esc, «atrás» o el botón «Álbumes», de vuelta, con ese álbum seleccionado. El filtro se queda en los dos sentidos. G, desde los álbumes, la cuadrícula con todas las canciones; la vista individual, la primera canción del álbum (Esc vuelve a los álbumes).
- **Entrar** muestra el álbum entero de su fila de «Artistas»: si se veía una carpeta, puede tener más canciones de las que contaba la tarjeta (las de otras carpetas).

### 7.4 Filtros y colecciones inteligentes

Hecho en `MUS 2.3` (26/11/2026; acordado con el autor; el porqué, en [DECISIONES.md](DECISIONES.md)). El grupo «Audio» de las colecciones inteligentes (`core/catalog/smart_fields.py`); los marcados con *, también columnas de «Metadatos» de la barra de filtros:

| Sección | Campos |
|---|---|
| Etiquetas | Artista*, Álbum*, Año*, Pista, Disco, Género*, Artista del álbum*, Compositor* |
| Formato | Formato*, Tasa de bits, Frecuencia de muestreo*, Canales*, Tipo de etiqueta* |
| Carátula | Tiene carátula*, Lado menor de la carátula |

- **«Título» y «Comentario» no se repiten**: son «Título» y «Descripción» de Estándar. «Artista» sí: es el «Autor» de Estándar, solo en las canciones.
- **«Año» es un número**: «Año está entre 1980 y 1989»; en la columna, del más reciente al más antiguo (no año ▸ enero ▸ 1, como saldría con la fecha).
- **«Artista del álbum»**, con el artista si falta, como la sección «Artistas».
- **Columnas de partida** de Música: «Género», «Artista del álbum» y «Álbum». Lo que falta: «Sin artista», «Sin álbum», «Sin año» y «Sin género».
- **«Texto» ▸ «Todos los campos disponibles»** busca también en el artista, el álbum, el artista del álbum, el género y el compositor de las canciones (`grid_filter.TEXT_FIELDS`; la regla general, los campos propios de cada módulo).
- **La tasa de bits no es columna** (con los VBR, casi un valor por canción): el orden «Tasa de bits» (§7.3).

## 8. Riesgos y trampas previstas

1. **Escribir en los archivos del usuario**: es el riesgo principal. Por eso el escritor va antes que la edición, sin interfaz, y se prueba con copias y comparando con Mp3tag, foobar2000, el Explorador de Windows y el móvil.
2. **ID3 es irregular**: varias versiones en un mismo archivo, codificaciones de texto, `TYER` / `TDRC`, etiquetas APE mezcladas. Se anota en [TRAMPAS.md](TRAMPAS.md) lo que aparezca con archivos reales.
3. **Varios valores** (§3.4): al unirlos en un texto no se debe perder nada al volver a escribir.
4. **mutagen es una dependencia nueva**: instalarla y añadirla a `requirements.txt` lo hace el autor; al empaquetar (`GEN 5`) no necesita nada especial (Python puro).
5. **Discos de red o lentos**: el archivo temporal duplica lo que se escribe; con FLAC, decenas de MB por canción.

---

# Parte II — Planificación

Códigos de [PENDIENTE.md](PENDIENTE.md). El orden es el de las fases; dentro de cada una, el de los pasos. **El escritor (`MUS 6`) va antes que la edición (`MUS 7`)**: si se editara antes de tenerlo, lo editado iría al `.arca.json` y habría que migrarlo después.

### Fase MUS 1 — Leer las etiquetas

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| ~~**MUS 1.1** Base de audio~~ (hecho el 25/11/2026) | mutagen instalada (el autor); la tabla campo ↔ etiqueta y `read_audio(path)` (campos, datos técnicos, tipo de etiqueta e imágenes), sin BD; los tipos de imagen | `core/audio/` (`tag_map.py`, `tag_reader.py`, `picture_types.py`); `core/metadata/audio/inspect_cli.py` | Autoprueba con un MP3 y un FLAC mínimos; `inspect_cli` con las 75 canciones del autor, comparado con Mp3tag |
| ~~**MUS 1.2** Tabla de detalles~~ (hecho el 25/11/2026) | `audio_details` (la siguiente migración libre) | `catalog_schema.py`; [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md), [INDEX.md](INDEX.md) | Un catálogo existente pasa solo al esquema siguiente (hoy, v7) |
| ~~**MUS 1.3** Extractor~~ (hecho el 25/11/2026) | `AudioExtractor` con `AUDIO_FIELDS_VERSION`, registrado | Nuevo: `core/metadata/audio/`; `registry.py` | Al abrir el catálogo, las canciones se leen solas; título, artista y duración, en el catálogo |
| ~~**MUS 1.4** Recuento~~ (hecho el 26/11/2026) | Cuántas canciones traen varios géneros o artistas, y qué tipos de etiqueta hay | Un guion de solo lectura | Decide §3.4 |

### Fase MUS 2 — Verlas

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| ~~**MUS 2.1** Sección «Audio» del inspector~~ (hecho el 26/11/2026) | De solo lectura: los campos y los datos técnicos, con la forma de §7.1; con varias canciones, lo común y «Varios», y la duración sumada | Nuevos: `ui_helpers/inspector/audio_section.py`, la consulta en `core/catalog/`; `section_registry.py` | Los valores, los de Mp3tag |
| ~~**MUS 2.2** Orden~~ (hecho el 26/11/2026) | Artista, álbum, año y título (sin «Pista» suelta ni «Hora de captura»; ver §7.3) | `grid_orders.py`, `audio_module.py` | Un álbum sale en su orden |
| ~~**MUS 2.3** Filtros y colecciones inteligentes~~ (hecho el 26/11/2026) | Campos del grupo «Audio» (`smart_fields.py`); columnas de «Metadatos» | `smart_fields.py` y lo que use la barra de filtros | «Género es…», «Álbum contiene…» |

### Fase MUS 3 — Carátulas como miniatura

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| ~~**MUS 3.1** Carátula incrustada~~ (hecho el 26/11/2026) | `AudioCoverSource`; tarjeta cuadrada en la biblioteca de música | Nuevo: `core/thumbnails/sources/audio_cover_source.py`; `registry.py`; el delegado, si hace falta para la proporción | Las canciones con carátula la muestran; las demás, el marcador |
| **MUS 3.2** `folder.jpg` de reserva (si se decide) | La imagen de la carpeta cuando la canción no trae carátula | El mismo origen | — |
| **MUS 3.3** (opcional) Una copia por carátula | En la caché, una sola copia de cada carátula, por su huella (§6) | `core/thumbnails/` (caché y trabajo), el modelo de la cuadrícula, el borrado | El mismo resultado, con mucho menos espacio |

### Fase MUS 4 — Navegar

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| ~~**MUS 4.1** «Artistas» y «Años»~~ (hecho el 26/11/2026) | Artista del álbum ▸ álbum y año ▸ álbum, con recuentos (§7.2); «Fechas» sale de Música | Nuevas secciones en `ui_helpers/sidebars/sections/`; consultas en `core/catalog/`; `section_registry.py`; `audio_module.py` | Elegir un álbum muestra sus canciones |
| **MUS 4.2** «Géneros» | Una lista simple, con recuentos | Lo mismo | Elegir un género muestra sus canciones |
| **MUS 4.3** Listas que se recorren con las flechas | Ver la nota de abajo | `SidebarTreeView`, `CenterViewController` | Recorrer los álbumes con el teclado |

**Nota de `MUS 4.3`** (pregunta del autor el 12/11/2026): hoy los árboles de las barras no cogen el teclado (`SidebarTreeView`, `NoFocus`) y los atajos solo actúan con la cuadrícula o la vista individual enfocadas. Si la lista está en el centro (vista de lista o de carátulas), ya tiene el teclado; los atajos se le enganchan con `GridActions.watch`. Si está en la barra izquierda: ese árbol, y solo ese, aceptaría el teclado (una opción de `SidebarTreeView`); `CenterViewController._on_source_chosen` no debe llevarse el teclado al centro cuando se elige desde él (cada flecha sacaría de la lista); decidir qué hace un atajo («3») con la lista activa y, si se quiere, la búsqueda al teclear (las letras dejarían de ser atajos mientras la lista tenga el teclado). Vale también para las películas (`VID 5.4`).

### Fase MUS 5 — Vista de lista

> **Cambiado el 16/11/2026**: la vista de lista pasa a ser una fase general (`GEN 18`: la lista y sus columnas a elegir, 5.1 y 5.2 de abajo); de Música quedan sus columnas y la vista de álbumes (5.3).

Estilo Mp3tag. Es una vista más del centro, pensada para servir a otros módulos.

| Paso | Objetivo | Aceptación |
|---|---|---|
| **MUS 5.1** La lista | Una fila por canción con columnas fijas; selección compartida con la cuadrícula; atajos de clasificación | Se pasa de la cuadrícula a la lista con lo mismo seleccionado |
| **MUS 5.2** Columnas | Elegirlas, moverlas y cambiar su ancho; ordenar por columna; recordado por módulo | — |
| ~~**MUS 5.3** Vista de álbumes~~ (hecho el 26/11/2026) | Los álbumes con su carátula: una tarjeta por álbum; con doble clic, sus canciones (idea del autor; §7.5) | — |

### Fase MUS 6 — Escribir en los archivos

Sin interfaz: se prueba con copias antes de que nada lo use. El escritor es una clase de `core/userdata/writers.py` (`GEN 14`, hecho el 16/11/2026): se registra sin tocar `sync.py`, y lo que no sabe guardar va solo al `.arca.json`.

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| ~~**MUS 6.1a** El tipo de etiqueta~~ (hecho el 27/11/2026) | `TagSet` (el tipo como dato, con el texto de siempre y su vuelta) y `tags_for_edit` (en qué etiquetas se escribe, §5); el lector calcula el tipo con él | Nuevo: `core/audio/tag_set.py`; `tag_reader.py` | Autoprueba con la tabla de §5; las 4 876 canciones del autor, con el mismo tipo que el guardado en el catálogo |
| ~~**MUS 6.1b** El ID3v1~~ (hecho el 27/11/2026) | Leerlo y componerlo con sus límites (§5), cambiando solo lo editado | Nuevo: `core/audio/id3v1.py` | Autoprueba sin archivos; lo que compone, leído por el lector |
| **MUS 6.1c** El motor de MP3 | `write_tags(path, changes, preferred)` con las reglas de §5: temporal, ID3v2 sin convertir y en su versión, ID3v1, comprobación (lo editado, el resto de marcos, el audio, la versión) y sustitución conservando la fecha de creación | Nuevo: `core/audio/tag_writer.py` | Autoprueba con MP3 mínimos; copias de canciones reales, leídas después por Mp3tag, foobar2000, el Explorador y el móvil |
| **MUS 6.1d** Opciones > Música | La etiqueta preferida: «ID3v2.3 UTF-16» o «ID3v2.4 UTF-8» y «Incluir ID3v1» | Nuevo: `ui_helpers/dialogs/music_settings_page.py`; `settings_dialog.py`, `app_constants.py`, `app_config_manager.py` | La página, guardada al pulsar «Aceptar» (sin efecto hasta `MUS 6.2`) |
| **MUS 6.2** En la cola | `core/userdata/audio_writer.py` (el escritor de la cola, con `fields_for`) con la preferida de las Opciones; campos de audio en `editable_fields.py`; `sync.py` usa el escritor; lo que no sabe guardar, al `.arca.json`; si cambia el tipo de etiqueta, se relee; los errores, a la lista de errores (`GEN 6.1`) | `audio_writer.py`, `writers.py`, `editable_fields.py`, `policy.py`, `sync.py` | Autoprueba de `sync` con audio: catálogo → archivos → catálogo nuevo; las fotos, igual que antes |
| **MUS 6.3** FLAC | Comentarios Vorbis | Lo mismo | Cuando haya archivos reales |
| **MUS 6.4** M4A y Ogg/Opus | Átomos MP4; Vorbis en Ogg | Lo mismo | Cuando haya archivos reales |

### Fase MUS 7 — Editar

| Paso | Objetivo | Aceptación |
|---|---|---|
| **MUS 7.1** Edición en el inspector | Los campos de la sección «Audio», editables, de una canción | Lo editado está en el archivo; Mp3tag lo lee |
| **MUS 7.2** Varias canciones | «Varios» y el aviso «Edición múltiple» | Poner el álbum a doce canciones a la vez |
| **MUS 7.3** Edición en la lista (opcional) | Editar una celda de la vista de lista | — |

### Fase MUS 8 — Herramientas por lotes

En una ventana, sobre la selección, con vista previa de lo que va a cambiar; cada una se aplica y se deshace de una vez.

- **MUS 8.1** Numerar pistas; mayúsculas y minúsculas; buscar y reemplazar.
- **MUS 8.2** Nombre de archivo → etiqueta, con un patrón (`%artista% - %título%`).
- **MUS 8.3** Etiqueta → nombre de archivo: **renombra originales**; paso aparte, con su decisión (la ruta del catálogo y la entrada del `.arca.json` cambian con el archivo).
- **MUS 8.4** «Reescribir etiquetas…» (acordado con el autor el 27/11/2026, §5): la única forma de cambiar el tipo de etiqueta. Sobre la selección, con el destino (de partida, la etiqueta preferida de las Opciones) y una casilla «Conservar lo que la aplicación no muestra (letras, valoraciones de otros programas, marcos de iTunes…)»: marcada, **convierte**; desmarcada, **limpia** (solo los campos del inspector y la carátula). Vista previa por tipo («ID3v2.4 → ID3v2.3: 12 canciones»), aviso y trabajo largo que se puede cancelar; con el mismo motor (`tag_writer.py`) y su regla en `tag_set.py`. «Limpiar y escribir desde el nombre del archivo» es esta herramienta y después `MUS 8.2`.

### Fase MUS 9 — Carátulas: cambiarlas y guardarlas

- ~~**MUS 9.1** La carátula en grande en el inspector~~ (hecho el 26/11/2026, adelantado: la sección «Carátula», de solo lectura; §6).
- **MUS 9.2** Escribir la carátula (`APIC`; después, FLAC y M4A) por la cola, con el tamaño máximo decidido; se rehacen las miniaturas.
- **MUS 9.3** Cambiarla: arrastrar, «Elegir…», pegar o `folder.jpg`; para una canción, la selección o el álbum.
- **MUS 9.4** Extraerla a un archivo; quitarla. Opcional: guardar también `folder.jpg`.

### Fase MUS 10 — Internet

Descargar etiquetas y carátulas (MusicBrainz y Cover Art Archive, sin clave). Lo descargado entra como una edición más: misma cola, misma marca de pendiente, mismo escritor.

### Por decidir

| | Para | Qué |
|---|---|---|
| ~~**M1**~~ | `MUS 1.4` | Decidida el 26/11/2026: como texto (ningún valor múltiple en las 4 876 canciones del autor; §3.4) |
| **M2** | `MUS 3.2` | `folder.jpg` / `cover.jpg` como carátula de reserva |
| ~~**M3**~~ | `MUS 6.1` | Decidida el 16/11/2026: archivo temporal, comprobación y sustitución (§5) |
| **M4** | `MUS 9.2` | Tamaño máximo de la carátula (1000–1400 px) |
| **M5** | Después de `MUS 6` | La valoración, también en POPM (hoy, solo en el `.arca.json`: un solo destino por dato) |
| **M6** | `MUS 8.3` | Renombrar archivos desde las etiquetas |
| **M7** | Cada paso | Los textos del módulo y, si se quiere, llamarlo «Música» también en la interfaz |
| ~~**M8**~~ | `MUS 9.1` | Decidida el 26/11/2026: en su propia sección «Carátula», detrás de «Audio», con sus acciones en un botón de la cabecera (§6) |
| **M9** | `MUS 9` | El botón de hacer cuadrada la carátula: si se hace, recortando o rellenando (cambia la imagen guardada en el archivo) |
