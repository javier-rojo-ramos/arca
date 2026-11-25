# Arca Media — Módulo Música: arquitectura y plan

> Documento del módulo Música (en el código y en la interfaz, el módulo **Audio**: `AudioModule`, biblioteca `audio`). Tiene dos partes: **I, arquitectura** (cómo está hecho y cómo encaja con el resto) y **II, planificación** (fases y pasos, con los códigos `MUS` de [PENDIENTE.md](PENDIENTE.md)).
> **Estado (16/11/2026): diseño acordado con el autor; sin implementar.** El 25/11/2026, acordada la sección «Audio» del inspector (§7.1) y hecho `MUS 1.1` (la base de audio, `core/audio/`, sin conectar a la aplicación). Todo lo de la parte I que no esté en «Punto de partida» es lo PREVISTO: cuando un paso se entregue, su parte se corrige aquí y pasa a [FLUJOS.md](FLUJOS.md), [ARQUITECTURA.md](ARQUITECTURA.md), [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md) y [METADATOS.md](METADATOS.md). Si el código y este documento no coinciden, manda el código.
> Índice: [INDEX.md](INDEX.md). Decisiones: [DECISIONES.md](DECISIONES.md) (16/11/2026).

## Resumen

**Objetivo**: una funcionalidad básica parecida a la de Mp3tag (ver y editar las etiquetas y las carátulas de las canciones, de una en una y por lotes), con lo que ya da el catalogador (bibliotecas, valoración, marca, color, palabras clave, filtros, colecciones inteligentes), de lo básico a lo avanzado. Cada paso deja la aplicación funcionando, como en Tracks.

**Lo decidido** (el autor, 16/11/2026; el porqué, en [DECISIONES.md](DECISIONES.md)):

| | |
|---|---|
| Biblioteca | **mutagen**, para leer y para escribir (Python puro; ID3 v2.3 y v2.4, FLAC, Ogg/Opus, M4A, carátulas). Licencia GPL: sin problema en uso interno |
| Formatos | **Leer**: MP3, FLAC, M4A y Ogg/Opus. **Escribir**: primero MP3; cada formato más, cuando haya archivos reales con los que compararlo |
| ID3 al escribir | Se conserva la versión que tenga el archivo; sin etiqueta, v2.3. El ID3v1 se actualiza si existe; ni se crea ni se quita |
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
- **Módulo**: `controllers/app_modules/audio_module.py` (`AudioModule`, sobre `LibraryModule`), con la barra común (`ui_helpers/sidebars/library_sidebar.py`: biblioteca, carpetas y fechas). La cuadrícula y la vista individual (desde el 19/11/2026, pedida por el autor para entrar y salir como en los demás módulos; hoy, la corchea y el nombre; la carátula en grande, cuando se lea en `MUS 3`). Orden: `VIDEO_AUDIO_SORT_FIELDS` (`core/catalog/grid_orders.py`). Filtros: su tipo y, en «Metadatos», fecha y palabras clave.
- **Sin etiquetas**: no hay extractor de audio (`core/metadata/registry.py` ignora los tipos sin extractor). De cada canción solo se sabe lo del archivo (nombre, tamaño, fechas).
- **Sin miniatura**: la tarjeta dibuja el marcador. El registro de orígenes (`core/thumbnails/registry.py`) tiene anotado el hueco para las carátulas.
- **Datos del usuario**: valoración, marca, color y palabras clave, en el `.arca.json` de la carpeta (destino `FOLDER_FILE` de `core/userdata/policy.py`).
- **Edición**: el mecanismo «un campo, varios escritores» (14/11/2026; [core/userdata/LEEME.md](../core/userdata/LEEME.md)) ya admite campos sin XMP, de tablas de detalles y solo de algunos tipos de archivo. El grupo «Audio» de las colecciones inteligentes existe vacío (`core/catalog/smart_fields.py`).
- **Las imágenes de una carpeta de música** (`cover.jpg`, `folder.jpg`) no entran en el catálogo: la carpeta es de Música y solo cataloga audio.

## 2. Dónde vive cada cosa

Como en Tracks: lo que no necesita ni Qt ni la base de datos, en un paquete de `core/` propio; el extractor, con los demás; el escritor, con los demás escritores.

| Qué | Dónde | Notas |
|---|---|---|
| Tabla campo ↔ etiqueta de cada formato; leer y escribir etiquetas y carátulas con mutagen | `core/audio/` (sin Qt ni BD): `tag_map.py` (la tabla), `tag_reader.py` (`read_audio`), `picture_types.py` (los tipos de imagen); desde `MUS 1.1` | **Una sola tabla** para el extractor y para el escritor: los dos entienden lo mismo |
| Extractor | `core/metadata/audio/` (nuevo): `extractor.py`, `fields.py`, `inspect_cli.py` | `MetadataExtractor` con `details_table = "audio_details"`, como `TrackExtractor`; se registra en `core/metadata/registry.py` |
| Tabla de detalles | `core/catalog/catalog_schema.py`, la siguiente migración libre (la 5 fue el registro de operaciones de `CAT 4` y la 6, las carpetas de `CAT 5`) | `audio_details` (§3) |
| Consultas | `core/catalog/` | Datos de la sección del inspector (como `track_stats.py`), valores de las secciones de la barra, filas de la vista de lista |
| Origen de la miniatura | `core/thumbnails/sources/audio_cover_source.py` (nuevo) | Se registra en `core/thumbnails/registry.py` |
| Campos editables | `core/userdata/editable_fields.py` | Una línea por campo, con `table="audio_details"` y `media_types` de audio |
| Escritor | `core/userdata/audio_writer.py` (nuevo) | Declara qué campos sabe guardar en cada formato; el trabajo que escribe sigue siendo el de `sync.py` |
| Módulo y barra | `controllers/app_modules/audio_module.py`, `ui_helpers/sidebars/sections/` | Secciones nuevas dadas de alta en `section_registry.py` |
| Inspector | `ui_helpers/inspector/audio_section.py` (nuevo) | Como `track_section.py`; de la biblioteca `audio` (sale también en el Catálogo con canciones seleccionadas) |
| Vista de lista | `ui_helpers/widgets/` y `ui_helpers/models/` (nuevos) | Una vista más del centro (`CenterView`); sirve a otros módulos |

`core/audio/` y `core/metadata/audio/` no usan Qt. La interfaz no toca mutagen: lee del catálogo y pide los cambios por la cola de edición.

## 3. Datos

### 3.1 Columnas comunes (`media_items`)

Lo que ya tiene columna común se guarda ahí, para que el filtro de texto, el orden, las colecciones inteligentes y la sección «Fechas» funcionen sin nada nuevo:

| Etiqueta | Columna | Notas |
|---|---|---|
| Título | `title` | Si la canción no lo tiene, se queda el nombre del archivo (como en las fotos) |
| Artista | `creator` | |
| Año (o fecha) | `content_created_at` | Con `content_date_precision` según lo que traiga la etiqueta (`year` casi siempre). A comprobar en `MUS 1`: cómo ordena y cómo muestra «Fechas» una fecha de solo año |
| Comentario | `description` | |
| Duración | `duration` | Segundos |

### 3.2 `audio_details` (la siguiente migración libre)

Una fila por canción (`media_id`, clave primaria y ajena con borrado en cascada, como `track_details`). Propuesta, a cerrar en `MUS 1.2`:

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
| `cover_type` | TEXT | Tipo de la carátula (clave de `core/audio/picture_types.py`; vacío en M4A, que no tiene tipos) |
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

Un archivo puede traer varios géneros o varios artistas. En la primera versión se guardan **como un texto**, unidos con un separador fijo (`«; »`: decidido con el autor el 25/11/2026; ver abajo); al escribir un campo editado, se separa de nuevo en los formatos que admiten varios valores. `MUS 1.4` cuenta cuántas canciones reales traen varios valores: si la navegación por géneros o artistas los necesita por separado, se pasan a tablas propias, como las palabras clave (decisión del 14/11/2026).

**El separador, «; » y no la coma de las palabras clave**: en una palabra clave la coma está prohibida, pero en un artista no («Earth, Wind & Fire», «Crosby, Stills, Nash & Young»); si el escritor (`MUS 6`) separase por comas, un artista así acabaría como varios. El punto y coma casi no aparece en un nombre. Las palabras clave siguen con la coma (como Lightroom). En las 75 canciones del autor (25/11/2026) ninguna trae varios valores ni comas en esos campos.

### 3.5 Versiones

`AUDIO_FIELDS_VERSION` (nueva; se guarda en `media_items.scan_version`): al subirla, las canciones se releen solas al abrir el catálogo, como los GPX. Va a la tabla de versiones de [INDEX.md](INDEX.md) y a la lista de [CLAUDE.md](../CLAUDE.md). Las carátulas como miniatura no cambian el resultado de las miniaturas que ya existen: a decidir en `MUS 3.1` si hace falta subir `THUMBNAIL_VERSION` o basta con reintentar las que no tenían origen.

## 4. Lectura

- `AudioExtractor.extract(path)` abre el archivo con mutagen, traduce las etiquetas con la tabla de §3.3 y entrega las columnas comunes y las de `audio_details`. No usa ExifTool (como el de tracks).
- Un archivo sin etiquetas no es un error: se guardan los datos técnicos y el título queda como el nombre del archivo. Un archivo dañado o que mutagen no entiende, a `scan_errors`, como los demás.
- **Un extractor nunca escribe datos del usuario**: valoración, marca, color y palabras clave siguen saliendo del `.arca.json`.
- **Datos técnicos** (duración, formato, kbps, kHz, canales, bits): de mutagen, que ya se necesita para las etiquetas; basta para las filas de §7.1. **MediaInfo** (propuesta del autor el 25/11/2026) no se usa por ahora: añadiría una biblioteca nativa que empaquetar en tres sistemas (`GEN 5`) sin nada nuevo que mostrar. Si se elige para Vídeo (`VID 1.1`), podría servir aquí de respaldo (MKA, que mutagen no lee; WMA) o para unos «datos técnicos ampliados» (codificador, VBR o CBR...). Por eso, en `AudioInfo` los datos técnicos van aparte: otra fuente los podría rellenar sin tocar el resto.
- Diagnóstico: `python -m core.metadata.audio.inspect_cli archivo` enseña las etiquetas tal cual las da mutagen y los campos ya traducidos, para comparar con Mp3tag.

## 5. Escritura

**Regla** (el autor, 16/11/2026): las etiquetas y las carátulas se guardan **en el propio archivo, sin generar copias**, como hace Mp3tag y como ya se hace con el XMP de un JPEG o un HEIC.

- **Por la cola de siempre**: editar cambia el catálogo y marca el campo como pendiente; el trabajo de `sync.py` lo escribe en segundo plano, lo comprueba releyendo y quita la marca. La opción «Escribir los cambios en los archivos» y la pregunta de las tandas grandes valen igual.
- **Un campo, varios escritores**: el escritor de audio declara qué campos sabe guardar en cada formato. Lo que no sabe (o un formato que aún no escribe) va al `.arca.json`, como hoy.
- **Solo lo editado**: se cambian los campos pendientes y se conservan las etiquetas que la aplicación no conoce. La versión de ID3 no se cambia; el ID3v1, solo si ya estaba.
- **El audio no se toca**: tras escribir se comprueba, además de las etiquetas, que los bytes del audio son los mismos que antes.
- **Sin riesgo de perder o corromper un archivo** (decidido por el autor el 16/11/2026): mutagen escribe sobre el propio archivo, así que la aplicación escribe en un **archivo temporal de la misma carpeta, lo comprueba y sustituye el original** (lo que hace ExifTool con las fotos). Si algo falla, el original sigue intacto y el temporal se borra. «Sin generar copias» quiere decir que no quedan archivos duplicados, no que no haya temporal.
- **Fecha de modificación**: cambia, como en las fotos; el catálogo anota el tamaño y la fecha nuevos sin releer ni regenerar la miniatura.
- **Archivo cambiado fuera** (Mp3tag, otro programa): la regla de las fotos: se escribe lo pendiente y el archivo queda para releer.

## 6. Carátulas

- **Como miniatura** (`MUS 3`): la carátula incrustada es el origen (`AudioCoverSource`); cuadrada, con la escalera de tamaños de siempre y sin ampliar por encima del original. De reserva, si se decide, `folder.jpg` / `cover.jpg` de la carpeta.
  - **En la caché, como las fotos** (acordado con el autor el 25/11/2026): el motor de miniaturas extrae la carátula de cada canción y guarda sus tamaños en `cache/audio/...`, por el `id` de la canción, igual que `cache/photo/...`. La cuadrícula, la vista individual y el inspector la leen de la caché, nunca del archivo, sin nada nuevo en ellos; al cambiar la carátula, su miniatura se regenera como la de una foto editada. La vista individual, del tamaño mayor (a 1:1, el original, del archivo); el inspector, del de 480 (a 354 px de ancho basta).
  - **La carátula del álbum**: no hay caché propia. La futura vista de álbumes (`MUS 5.3`) o la tarjeta agrupada (`GEN 17`) elige la carátula que comparten sus canciones (la misma `cover_hash`) y usa la miniatura de una de ellas. La huella sirve también para encontrar álbumes con carátulas distintas.
  - **Lo que cuesta**: la carátula de un álbum se repite en la caché una vez por canción (con carátulas de 600 px, unos 150 KB por canción: alrededor de 1,5 GB por cada 10 000). Se mide en `MUS 3` con la música del autor; si pesa, quitar los tamaños grandes, que en una carátula sobran, o guardar una sola copia por huella (otra organización de la caché: solo si el espacio llega a importar, como `GEN 4.5`).
- **En el inspector** (`MUS 9`): la carátula en grande; cambiarla arrastrando una imagen, con «Elegir…», pegándola o desde `folder.jpg`, para una canción, para la selección o para el álbum; extraerla a un archivo; quitarla.
  - **Cómo se ve** (acordado con el autor el 25/11/2026, tras ver una muestra): la imagen a todo el ancho, con el mismo margen a la izquierda y a la derecha que el resto de filas (8 px), y debajo **dos filas**: «Tipo» (un desplegable) e «Imagen» (formato, tamaño y peso: «JPEG · 600 × 600 · 25 KB», con un botón a la derecha para hacerla cuadrada: M9). Si «Imagen» resulta larga, se divide en dos filas.
  - **Tipos** (los de ID3 y FLAC, en el orden de Mp3tag; textos propuestos, M7): Portada, Contraportada, Otra, Icono, Folleto, Soporte (CD, vinilo), Solista, Artista, Director, Grupo, Compositor, Letrista, Lugar de la grabación, Durante la grabación, Durante la actuación, Captura de vídeo, Ilustración, Logotipo del grupo y Logotipo de la discográfica. M4A no tiene tipos.
  - **Dónde va** (M8, por decidir): en su propia sección «Carátula», con un botón en la cabecera para sus acciones (añadir, quitar, cambiar el tipo, extraer...), o a continuación de «Audio», con un menú contextual sobre la propia imagen.
- **Al guardarla**: se prepara como JPEG con un tamaño máximo (por decidir: 1000–1400 px) y sustituye a la portada frontal que hubiera. Se escribe por la misma cola que las etiquetas y se rehacen sus miniaturas.

## 7. Interfaz

- **Barra izquierda** (`MUS 4`): «Artistas» (artista del álbum ▸ álbum; si falta, el artista), «Géneros» y «Años» (la sección «Fechas» que ya existe, si sirve con fechas de solo año). Secciones dadas de alta en `section_registry.py`: se pliegan, se ocultan y se reordenan como las demás.
- **Centro**: la cuadrícula (con la carátula) y la **vista de lista** (`GEN 18`, común a todos los módulos; lo de Música, en `MUS 5`), estilo Mp3tag: columnas a elegir, orden por columna y selección múltiple, compartida con la cuadrícula. Opcional: vista de álbumes.
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
- **A tener en cuenta en `MUS 2.1`**: «Artista del álbum» es la etiqueta más larga del inspector. La columna de etiquetas, común a todas las secciones, pasaría de 87 a 97 px, y los valores de «Metadatos» y «Track» se moverían 10 px a la derecha.
- La carátula va debajo, en «Audio» o en su propia sección (§6, M8).
- En el registro de secciones, detrás de las comunes (`order` de 400 en adelante: [DECISIONES.md](DECISIONES.md), 25/11/2026).

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
| **MUS 1.2** Tabla de detalles | `audio_details` (la siguiente migración libre) | `catalog_schema.py`; [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md), [INDEX.md](INDEX.md) | Un catálogo existente pasa solo al esquema siguiente (hoy, v7) |
| **MUS 1.3** Extractor | `AudioExtractor` con `AUDIO_FIELDS_VERSION`, registrado | Nuevo: `core/metadata/audio/`; `registry.py` | Al abrir el catálogo, las canciones se leen solas; título, artista y duración, en el catálogo |
| **MUS 1.4** Recuento | Cuántas canciones traen varios géneros o artistas, y qué tipos de etiqueta hay | Un guion de solo lectura | Decide §3.4 |

### Fase MUS 2 — Verlas

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| **MUS 2.1** Sección «Audio» del inspector | De solo lectura: los campos y los datos técnicos, con la forma de §7.1; con varias canciones, lo común y «Varios», y la duración sumada | Nuevos: `ui_helpers/inspector/audio_section.py`, la consulta en `core/catalog/`; `section_registry.py` | Los valores, los de Mp3tag |
| **MUS 2.2** Orden | Artista, álbum, pista, año y duración (álbum: por disco y pista) | `grid_orders.py`, `audio_module.py` | Un álbum sale en su orden |
| **MUS 2.3** Filtros y colecciones inteligentes | Campos del grupo «Audio» (`smart_fields.py`); columnas de «Metadatos» | `smart_fields.py` y lo que use la barra de filtros | «Género es…», «Álbum contiene…» |

### Fase MUS 3 — Carátulas como miniatura

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| **MUS 3.1** Carátula incrustada | `AudioCoverSource`; tarjeta cuadrada en la biblioteca de música | Nuevo: `core/thumbnails/sources/audio_cover_source.py`; `registry.py`; el delegado, si hace falta para la proporción | Las canciones con carátula la muestran; las demás, el marcador |
| **MUS 3.2** `folder.jpg` de reserva (si se decide) | La imagen de la carpeta cuando la canción no trae carátula | El mismo origen | — |

### Fase MUS 4 — Navegar

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| **MUS 4.1** «Artistas» | Artista del álbum ▸ álbum, con recuentos | Nueva sección en `ui_helpers/sidebars/sections/`; consulta en `core/catalog/`; `section_registry.py` | Elegir un álbum muestra sus canciones |
| **MUS 4.2** «Géneros» y «Años» | «Años»: la sección «Fechas», si vale con fechas de solo año | Lo mismo | — |
| **MUS 4.3** Listas que se recorren con las flechas | Ver la nota de abajo | `SidebarTreeView`, `CenterViewController` | Recorrer los álbumes con el teclado |

**Nota de `MUS 4.3`** (pregunta del autor el 12/11/2026): hoy los árboles de las barras no cogen el teclado (`SidebarTreeView`, `NoFocus`) y los atajos solo actúan con la cuadrícula o la vista individual enfocadas. Si la lista está en el centro (vista de lista o de carátulas), ya tiene el teclado; los atajos se le enganchan con `GridActions.watch`. Si está en la barra izquierda: ese árbol, y solo ese, aceptaría el teclado (una opción de `SidebarTreeView`); `CenterViewController._on_source_chosen` no debe llevarse el teclado al centro cuando se elige desde él (cada flecha sacaría de la lista); decidir qué hace un atajo («3») con la lista activa y, si se quiere, la búsqueda al teclear (las letras dejarían de ser atajos mientras la lista tenga el teclado). Vale también para las películas (`VID 5.4`).

### Fase MUS 5 — Vista de lista

> **Cambiado el 16/11/2026**: la vista de lista pasa a ser una fase general (`GEN 18`: la lista y sus columnas a elegir, 5.1 y 5.2 de abajo); de Música quedan sus columnas y la vista de álbumes (5.3).

Estilo Mp3tag. Es una vista más del centro, pensada para servir a otros módulos.

| Paso | Objetivo | Aceptación |
|---|---|---|
| **MUS 5.1** La lista | Una fila por canción con columnas fijas; selección compartida con la cuadrícula; atajos de clasificación | Se pasa de la cuadrícula a la lista con lo mismo seleccionado |
| **MUS 5.2** Columnas | Elegirlas, moverlas y cambiar su ancho; ordenar por columna; recordado por módulo | — |
| **MUS 5.3** Vista de álbumes (opcional) | Los álbumes con su carátula | — |

### Fase MUS 6 — Escribir en los archivos

Sin interfaz: se prueba con copias antes de que nada lo use. El escritor es una clase de `core/userdata/writers.py` (`GEN 14`, hecho el 16/11/2026): se registra sin tocar `sync.py`, y lo que no sabe guardar va solo al `.arca.json`.

| Paso | Objetivo | Archivos | Aceptación |
|---|---|---|---|
| **MUS 6.1** Escritor de MP3 | `write_tags` para ID3, con las reglas de §5 (solo lo editado, versión conservada, comprobación de etiquetas y de audio) | `core/audio/`; nuevo: `core/userdata/audio_writer.py` | Autoprueba de ida y vuelta; copias de canciones reales, leídas después por Mp3tag, foobar2000, el Explorador y el móvil |
| **MUS 6.2** En la cola | Campos de audio en `editable_fields.py`; `sync.py` usa el escritor; lo que no sabe guardar, al `.arca.json`; los errores, a la lista de errores (`GEN 6.1`) | `editable_fields.py`, `policy.py`, `sync.py` | Autoprueba de `sync` con audio: catálogo → archivos → catálogo nuevo; las fotos, igual que antes |
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

### Fase MUS 9 — Carátulas: cambiarlas y guardarlas

- **MUS 9.1** La carátula en grande en el inspector.
- **MUS 9.2** Escribir la carátula (`APIC`; después, FLAC y M4A) por la cola, con el tamaño máximo decidido; se rehacen las miniaturas.
- **MUS 9.3** Cambiarla: arrastrar, «Elegir…», pegar o `folder.jpg`; para una canción, la selección o el álbum.
- **MUS 9.4** Extraerla a un archivo; quitarla. Opcional: guardar también `folder.jpg`.

### Fase MUS 10 — Internet

Descargar etiquetas y carátulas (MusicBrainz y Cover Art Archive, sin clave). Lo descargado entra como una edición más: misma cola, misma marca de pendiente, mismo escritor.

### Por decidir

| | Para | Qué |
|---|---|---|
| **M1** | `MUS 1.4` | Las listas: texto o tablas propias (según el recuento) |
| **M2** | `MUS 3.2` | `folder.jpg` / `cover.jpg` como carátula de reserva |
| ~~**M3**~~ | `MUS 6.1` | Decidida el 16/11/2026: archivo temporal, comprobación y sustitución (§5) |
| **M4** | `MUS 9.2` | Tamaño máximo de la carátula (1000–1400 px) |
| **M5** | Después de `MUS 6` | La valoración, también en POPM (hoy, solo en el `.arca.json`: un solo destino por dato) |
| **M6** | `MUS 8.3` | Renombrar archivos desde las etiquetas |
| **M7** | Cada paso | Los textos del módulo y, si se quiere, llamarlo «Música» también en la interfaz |
| **M8** | `MUS 9.1` | La carátula en el inspector: en su propia sección «Carátula», con un botón en la cabecera para sus acciones, o a continuación de «Audio», con un menú contextual sobre la imagen (§6) |
| **M9** | `MUS 9` | El botón de hacer cuadrada la carátula: si se hace, recortando o rellenando (cambia la imagen guardada en el archivo) |
