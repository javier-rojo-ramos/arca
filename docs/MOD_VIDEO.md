# Arca Media — Módulo Vídeo: arquitectura y plan

> Documento del módulo Vídeo (`VideoModule`, biblioteca `video`: películas, series, documentales, eventos deportivos...). Tiene dos partes: **I, arquitectura** y **II, planificación** (fases y pasos, con los códigos `VID` de [PENDIENTE.md](PENDIENTE.md)).
> **Estado (16/11/2026): diseño acordado con el autor (propuesta del asistente, aprobada); sin implementar.** Todo lo de la parte I que no esté en «Punto de partida» es lo PREVISTO: cuando un paso se entregue, su parte se corrige aquí y pasa a los demás documentos. Las decisiones, al final. Si el código y este documento no coinciden, manda el código.
> Índice: [INDEX.md](INDEX.md). Decisiones: [DECISIONES.md](DECISIONES.md) (16/11/2026).

## Resumen

**Objetivo** (el autor, 16/11/2026): catalogar películas, series, documentales, eventos deportivos...; verlos como las fotos o la música (por carpetas, género, director, visto / no visto, puntuación, y con la valoración, la marca y el color de siempre); y mostrar de cada uno una **ficha**, que se descarga de la web (sobre todo en películas y series) y se completa a mano. Al estilo de VisualDivX o EMDB.

**Las ideas del diseño**:

1. **La ficha es de la obra, no del archivo.** Una película suele ser un archivo, pero una serie son muchos, y una película puede venir en dos partes o en dos versiones. La ficha (título, sinopsis, reparto, cartel) vive en una tabla de **obras**; cada archivo apunta a la suya y, si es un episodio, dice su temporada y su número.
2. **Una tarjeta por obra, sobre la cuadrícula de siempre.** Las obras salen solas de los archivos (por el nombre y la carpeta). En los listados de títulos se ve una tarjeta por obra (un archivo que la representa); al entrar en una serie, sus episodios. Todo lo que ya funciona (valoración, marca, color, palabras clave, selección, filtros, colecciones) sigue siendo por archivo (§10).
3. **Géneros y personas, en tablas propias desde el principio**: navegar por director, por actor o por género es el centro del módulo (a diferencia de Música, donde las listas empiezan como texto).
4. **Lo descargado entra como una edición más** (decisión del 14/11/2026): un proveedor de fichas intercambiable entrega los mismos campos que se editan a mano; no hay un segundo mecanismo.
5. **El archivo de vídeo no se escribe.** La ficha y lo personal (visto, lo editado a mano) se guardan en el catálogo y, para sobrevivir a recrearlo, en el `.arca.json` de la carpeta. Escribir dentro de un MKV o un MP4 es lento y casi ningún programa lo lee (V3).
6. **Primero útil sin internet**: datos técnicos, título y año sacados del nombre, ficha a mano y visto / no visto; la descarga llega después y rellena lo mismo.

---

# Parte I — Arquitectura

## 1. Punto de partida (lo que ya existe)

- **Bibliotecas**: los vídeos personales (móvil, cámara) son de la biblioteca Imágenes; las películas y series, de `video`. La clasificación está hecha (`core/catalog/libraries.py`): por la declaración de la carpeta, por el nombre (`S01E02`, año entre paréntesis, etiquetas de ripeo), por los metadatos (cámara, una fecha que solo escribe una cámara o GPS → Imagen; más de 40 minutos sin cámara → Vídeo) y a mano (menú «Biblioteca»). En una carpeta declarada de vídeo solo se cataloga vídeo: los carteles sueltos no entran.
- **Extractor**: `core/metadata/video/` (ExifTool, `VIDEO_FIELDS_VERSION` 4), pensado para los clips: fecha, duración, tamaño girado, GPS, cámara, objetivo, `video_codec` y `frame_rate` (`video_details`). Comprobado con vídeos de iPhone; sin comprobar con películas (ESTADO, «Comprobaciones sueltas»).
- **Módulo**: `controllers/app_modules/video_module.py` (`VideoModule`, sobre `LibraryModule`), con la barra común (biblioteca, carpetas y fechas), cuadrícula y vista individual; orden `VIDEO_AUDIO_SORT_FIELDS`.
- **Tarjeta**: en la biblioteca Vídeos, proporción de cartel (2:3), con el marcador dibujado y la duración. Sin miniatura real.
- **Carpeta del catálogo**: `media_assets/posters` y `media_assets/backdrops` ya se crean (vacías). Decidido antes: los carteles viven en el catálogo, descargados.
- **Datos del usuario**: valoración, marca, color y palabras clave, en el `.arca.json` de la carpeta. El grupo «Vídeo» de las colecciones inteligentes existe vacío.
- **En el catálogo del autor** (16/11/2026): 2 vídeos en la biblioteca Vídeos (los dos MKV) y una carpeta declarada de vídeo.

## 2. Conceptos

| Concepto | Qué es | Dónde |
|---|---|---|
| **Archivo** | Un vídeo del disco. Lo que se selecciona, se valora y se marca | `media_items` + `video_details` |
| **Obra** | Lo que describe una ficha: una película, una serie, un documental, un evento deportivo u «otro» | Tabla nueva (`video_works`) |
| **Tipo de obra** | `movie`, `series`, `documentary`, `sports`, `other`: clave en inglés, texto en español (como la actividad de los tracks) | `video_works.kind` |
| **Episodio** | Un archivo de una obra de tipo serie, con su temporada y su número (y, más adelante, su título y su sinopsis) | Columnas nuevas de `video_details` |
| **Ficha** | Los datos de la obra, su cartel y su fondo | `video_works`, tablas de géneros y de personas, `media_assets/` |
| **Proveedor** | El servicio web del que se descarga una ficha | `core/video/providers/` |

Una película con un solo archivo tiene su obra, creada sola a partir del nombre: el usuario no tiene que saber que existe. Varios archivos pueden compartir obra (episodios; partes; versiones).

## 3. Dónde vive cada cosa

| Qué | Dónde | Notas |
|---|---|---|
| Sacar título, año, temporada y episodio del nombre | `core/video/name_parser.py` (nuevo; sin Qt ni BD) | Amplía lo que `guess_video_library` ya reconoce |
| Tipos de obra y su traducción | `core/video/kinds.py` (nuevo) | Como `core/tracks/activities.py` |
| Proveedores de fichas | `core/video/providers/` (nuevo; sin Qt): una interfaz (`search`, `fetch`) y un módulo por servicio | Red solo aquí; intercambiable y configurable, como el enrutado de Tracks |
| Datos técnicos de película | `core/metadata/video/` (ampliar) | Audio, subtítulos, contenedor (§5) |
| Esquema | `core/catalog/catalog_schema.py`, una migración | §4 |
| Obras, géneros, personas: consultas y cambios | `core/catalog/video_works.py` (nuevo) | Reciben `conn`, sin `commit` |
| Descarga (trabajo largo) | Un trabajo de `JobManager` | Por lotes, con `cancel_event` |
| Imágenes de la ficha | `media_assets/posters`, `media_assets/backdrops` | Un archivo por obra |
| Miniaturas | `core/thumbnails/sources/`: `video_poster_source.py`, `video_frame_source.py` (nuevos) | El cartel primero; si no hay, un fotograma |
| Lo que sobrevive fuera del catálogo | `core/userdata/` (`folder_file.py`, `sync.py`) | §7 |
| Módulo y barra | `video_module.py`, `ui_helpers/sidebars/sections/` | Secciones en `section_registry.py` |
| Inspector | `ui_helpers/inspector/video_section.py` (nuevo) | Sección «Ficha» |
| Vista «Ficha» del centro | `ui_helpers/widgets/` (nuevo) | Una vista más de `CenterView` |
| Ventana «Identificar…» | `ui_helpers/dialogs/` + un controlador propio | Ventana, por ser por lotes |

## 4. Datos (propuesta, a cerrar en `VID 2.1`)

**`video_works`** (una fila por obra):

| Columna | Qué es |
|---|---|
| `id` | |
| `kind` | Tipo de obra |
| `title`, `original_title`, `sort_title` | Título, título original y título para ordenar («Padrino, El») |
| `year`, `release_date` | Año y fecha de estreno |
| `overview`, `tagline` | Sinopsis y frase |
| `runtime_min` | Duración oficial |
| `countries`, `original_language`, `studio`, `certification` | País, idioma original, productora, clasificación por edades |
| `web_score`, `web_votes` | Puntuación de la web (0–10) y número de votos |
| `collection_name` | Saga («El Señor de los Anillos») |
| `provider`, `provider_id`, `imdb_id` | De dónde salió la ficha y sus identificadores |
| `poster_file`, `backdrop_file` | Archivos en `media_assets/` |
| `fetched_at`, `edited_mask` | Cuándo se descargó; qué campos ha cambiado el usuario (no se pisan al volver a descargar) |

**Géneros y personas** (como las palabras clave):

- `video_genres` (`id`, `name`) y `video_work_genres` (`work_id`, `genre_id`).
- `video_people` (`id`, `name`, identificador del proveedor) y `video_credits` (`work_id`, `person_id`, `role`: `director` / `cast` / `writer`; `character`; `position`).

**`video_details`** (columnas nuevas, por archivo):

| Columna | Qué es |
|---|---|
| `work_id` | La obra del archivo |
| `season_number`, `episode_number`, `episode_title` | Si es un episodio |
| `part_number`, `edition` | Parte (CD1, CD2) o versión («Montaje del director») |
| `watched`, `watched_at` | Visto / no visto y cuándo (dato del usuario, por archivo) |
| `container`, `audio_codec`, `audio_channels`, `audio_languages`, `subtitle_languages`, `bitrate`, `hdr` | Datos técnicos (§5) |

`media_items` no cambia: `title` (el de la tarjeta: el de la película, o «S01E02 · título del episodio»), `content_created_at` (el año de estreno, con precisión de año: así «Fechas» y el orden por fecha sirven), `duration`, `width` y `height`.

**Puntuación**: dos cosas distintas. La **de la web** (0–10, de solo lectura) y la **personal**, que es la valoración de estrellas de siempre.

## 5. Lectura (datos técnicos)

El extractor de vídeo se amplía para lo que importa en una película: contenedor, códec y canales de audio, idiomas de audio y de subtítulos, tasa de bits, HDR. Sube `VIDEO_FIELDS_VERSION` (los vídeos se releen solos). A decidir en `VID 1.1` con películas reales (`inspect_cli`): si ExifTool lo da bien en MKV y MP4, o hace falta `ffprobe` (que llegará de todos modos con `ffmpeg` para los fotogramas, V6). Primera prueba, el 21/11/2026, con una MKV de `mkvmerge`: ExifTool da, por pista, el códec de vídeo (`Track1:VideoCodecID`, «V_MPEGH/ISO/HEVC»), los fotogramas por segundo, la tasa de bits (`BPS`), el audio (códec «A_AC3», canales e idioma) y los subtítulos (formato e idioma); de la MKV, hoy solo se leen los fotogramas por segundo. Los subtítulos sueltos (`.srt` junto al vídeo) se pueden contar sin catalogarlos.

**Un extractor nunca escribe datos del usuario** ni la biblioteca; tampoco la obra: la crea y la enlaza un paso aparte, tras la lectura (como `classify_pending_videos`).

## 6. La ficha: de dónde sale

1. **Del nombre** (`VID 2`): `name_parser` saca título, año, temporada y episodio de «El padrino (1972) 1080p.mkv» o de «Serie/Temporada 1/Serie S01E02.mkv» (también de las carpetas). Con eso se crea la obra y se enlazan sus archivos (las reglas, en §10.1). Sin internet.
2. **A mano** (`VID 6`): cualquier campo se edita en la ficha; lo editado queda marcado y una descarga posterior no lo pisa.
3. **De la web** (`VID 7`): «Identificar…» busca la obra en el proveedor con el título y el año, enseña los candidatos (cartel, año, sinopsis) y, al elegir, descarga la ficha, el reparto, el cartel y el fondo. Por lotes: lo que coincide con claridad se propone solo; lo dudoso se revisa. Nada se descarga sin que el usuario lo pida.

**Proveedor**: una interfaz y un módulo por servicio; la clave de acceso, en Opciones (nunca en el repositorio). Los textos, en español. El servicio se decide en V2.

## 7. Qué se guarda fuera del catálogo

El catálogo se puede recrear volviendo a añadir las carpetas; lo que el usuario ha puesto no debe perderse. Propuesta (V3): en el `.arca.json` de la carpeta, por archivo, además de lo de hoy: **la identificación** (proveedor e identificador de la obra, tipo, temporada y episodio), **visto / no visto** y **los campos de la ficha editados a mano**. Lo descargado no se guarda fuera: con el identificador se vuelve a descargar.

Visto / no visto y los campos de texto de la ficha pasan por el mecanismo de edición que ya existe (`editable_fields.py`: campo de una tabla de detalles, sin XMP, solo de vídeo → `.arca.json`), como la actividad de un track.

## 8. Miniaturas

- **Cartel** (`VideoPosterSource`): si la obra tiene cartel, es la miniatura de sus archivos (la tarjeta 2:3 ya existe).
- **Fotograma** (`VideoFrameSource`, con `ffmpeg` en `tools/ffmpeg`, hacia el 10 % de la duración): cuando no hay cartel. Sirve también a los vídeos personales de Imagen (16:9).
- Al descargar o cambiar un cartel se rehacen las miniaturas de sus archivos. A decidir en su paso si hace falta subir `THUMBNAIL_VERSION`.

## 9. Interfaz

- **Barra izquierda**: «Biblioteca - Vídeos» (todos, por tipo —películas, series, documentales, eventos deportivos—, «No vistos», «Sin ficha» y «Selección rápida»), «Carpetas», «Series» (serie ▸ temporada), «Géneros», «Directores», «Reparto» y «Años». Dadas de alta en `section_registry.py`. Las listas largas (reparto) llevan filtro, como la «Lista de palabras clave».
- **Centro**: la cuadrícula de carteles; la **vista «Ficha»** (`VID 8`), al estilo de VisualDivX: el cartel en grande, el título, el año, la duración, las puntuaciones, la sinopsis, el director, el reparto, los datos técnicos y, en una serie, sus episodios; con «Reproducir» (abre el archivo en el reproductor del sistema, V7). La vista de lista (`GEN 18`) sirve aquí.
- **Inspector**: sección «Ficha» (resumen y, con `VID 6`, edición), y las de siempre. Visto / no visto: un botón en la ficha, una orden del menú y un atajo; se filtra en «Atributos».
- **Orden, filtros y colecciones inteligentes** (grupo «Vídeo»): título, año, duración, tipo, género, director, actor, visto, puntuación de la web, resolución, códec, idioma.
- **Ventanas**: «Identificar…» y la descarga por lotes.

## 10. Obras: cómo se forman y cómo se ven

Acordado con el autor el 16/11/2026. Añadir contenido no cambia: se leen carpetas y entran archivos. **Las obras no las crea el usuario: salen de los archivos.** Con películas de un solo archivo no se nota nada: cada archivo tiene su obra y su ficha, y la palabra «obra» no aparece en la interfaz.

### 10.1 Cómo se asigna cada archivo a su obra

Tras leer los metadatos, un paso automático (como `classify_pending_videos`) agrupa los vídeos de la biblioteca Vídeos por su nombre y su carpeta:

| Caso | Regla | Resultado |
|---|---|---|
| `El padrino (1972) 1080p.mkv` | Sin marca de episodio ni de parte | Una obra de tipo película, con ese título y ese año: un archivo, una obra |
| `Serie/Temporada 1/Serie S01E02.mkv` | Marca de episodio (`S01E02`, `1x02`) | Obra de tipo serie; su nombre, el texto anterior a la marca o el de la carpeta; los episodios con el mismo nombre comparten obra |
| `Ben-Hur (1959) CD1.avi` y `… CD2.avi` | Marca de parte, con el mismo título y año, en la misma carpeta | Una obra con dos partes |
| Dos archivos con el mismo título y año (1080p y 4K) | Mismo título **y** año | Una obra con dos versiones; sin año, no se juntan |

Cuando la regla se equivoca, se corrige a mano sobre la selección: **«Agrupar en una obra»**, **«Separar»** y cambiar la temporada y el número de un episodio. Lo corregido se guarda en el `.arca.json` (§7) y el paso automático no lo vuelve a tocar.

### 10.2 Qué muestra la cuadrícula

- **En los listados de títulos** («Todos», «Películas», «Series», un género, un director...): **una tarjeta por obra**. Una película es su tarjeta de siempre; una película en dos partes, una tarjeta; una serie, una tarjeta con su cartel y un número («24 episodios»). «Películas» es así la lista de películas, en la cuadrícula o en la vista de lista (`GEN 18`), con una fila por película.
- **Al entrar en una serie** (doble clic, Intro, o serie ▸ temporada en la barra): sus episodios, una tarjeta por archivo.
- **En «Carpetas»**: los archivos tal cual, como ahora.

No hace falta una cuadrícula nueva: la consulta devuelve **un archivo representante por obra** (el primer episodio, la primera parte) y el recuento. La tarjeta sigue siendo un archivo: la selección, los filtros y las colecciones funcionan igual.

### 10.3 Acciones sobre una tarjeta que agrupa varios archivos

Estrellas, marca, color, visto / no visto y palabras clave **se aplican a todos los archivos de la obra**: en una película en dos partes es lo natural; en una serie equivale a valorar o marcar como vista la serie entera, y dentro cada episodio se puede cambiar por separado. La tarjeta agrupada muestra el valor común, o ninguno si sus archivos difieren (como «Varios» en el inspector).

### 10.4 En el plan

Primero, solo películas: un archivo, una obra, la cuadrícula como está (el esquema ya lleva la tabla de obras). La tarjeta agrupada, «Agrupar» y «Separar» llegan con las series (`VID 5.3`), sobre la tarjeta agrupada común (`GEN 17`, que usará también Ebooks).

## 11. Riesgos

1. **Emparejar archivo y obra**: los nombres de archivo son irregulares. Por eso la identificación siempre se puede corregir a mano y nada se descarga sin confirmar cuando hay duda.
2. **El servicio web**: condiciones de uso (uso interno de una empresa), clave, límites, cambios de su API. Por eso es un proveedor intercambiable y la aplicación funciona sin él.
3. **Series**: es lo que más complica el modelo (obra ▸ temporada ▸ episodio). Se deja para después de las películas, pero el esquema lo prevé desde el principio para no migrar dos veces.
4. **Tamaño**: carteles y fondos en `media_assets` (unos cientos de KB por obra).
5. **Eventos deportivos**: no hay un servicio comparable; ficha a mano.

---

# Parte II — Planificación

Cada paso deja la aplicación funcionando. Hasta `VID 6` no hace falta internet.

### Fase VID 1 — Datos técnicos y nombre

| Paso | Objetivo | Aceptación |
|---|---|---|
| **VID 1.1** Datos técnicos de película | Ampliar el extractor (contenedor, audio, subtítulos, tasa de bits, HDR); la siguiente `VIDEO_FIELDS_VERSION`; migración con las columnas | `inspect_cli` con películas reales (MKV, MP4, AVI); los clips de Imagen, igual |
| **VID 1.2** Leer el nombre | `core/video/name_parser.py`: título, año, temporada, episodio, parte | Autoprueba con una lista de nombres reales del autor |

### Fase VID 2 — Obras

| Paso | Objetivo | Aceptación |
|---|---|---|
| **VID 2.1** El esquema | `video_works`, géneros, personas, créditos y las columnas de `video_details` (una migración) | Un catálogo existente pasa solo al esquema nuevo |
| **VID 2.2** Crear y enlazar | Tras leer los metadatos, cada vídeo de la biblioteca Vídeos tiene su obra, con las reglas de §10.1 (episodios, partes y versiones comparten la suya) | Autoprueba; en el catálogo real, cada película con su título y su año |
| **VID 2.3** Tipo de obra | `core/video/kinds.py`; se deduce (episodio → serie; si no, película) y se cambia a mano | — |

### Fase VID 3 — Verlas

| Paso | Objetivo |
|---|---|
| **VID 3.1** Sección «Ficha» del inspector, de solo lectura: lo de la obra y los datos técnicos del archivo |
| **VID 3.2** Orden propio: título (el de ordenar), año, duración, resolución |
| **VID 3.3** Campos del grupo «Vídeo» en filtros y colecciones inteligentes |

### Fase VID 4 — Miniaturas

| Paso | Objetivo |
|---|---|
| **VID 4.1** Fotograma con `ffmpeg` (también para los vídeos de Imagen) |
| **VID 4.2** El cartel como miniatura, cuando la obra lo tiene (se ve con `VID 6.4` o `VID 7`) |

### Fase VID 5 — Navegar

| Paso | Objetivo |
|---|---|
| **VID 5.1** «Biblioteca - Vídeos» por tipo, «Sin ficha» |
| **VID 5.2** «Géneros», «Directores», «Reparto» y «Años» |
| **VID 5.3** Series: la sección «Series» (serie ▸ temporada), **la tarjeta agrupada** (una por obra en los listados, con su recuento; entrar muestra los episodios; las acciones, a todos sus archivos) y «Agrupar en una obra» / «Separar» (§10) |
| **VID 5.4** Listas que se recorren con las flechas (lo de `MUS 4.3`) |

### Fase VID 6 — Visto / no visto y ficha a mano

| Paso | Objetivo |
|---|---|
| **VID 6.1** Visto / no visto: botón, menú, atajo, filtro en «Atributos», «No vistos» en la barra; guardado en el `.arca.json` |
| **VID 6.2** Editar los campos de texto de la ficha en el inspector |
| **VID 6.3** Editar géneros, director y reparto (cajas con sugerencias, como las palabras clave) |
| **VID 6.4** Poner el cartel a mano (arrastrar, «Elegir…», pegar) |
| **VID 6.5** Cambiar la temporada y el número de un episodio, la parte y la versión |
| **VID 6.6** Lo identificado y lo editado, en el `.arca.json`; se recupera al recrear el catálogo |

### Fase VID 7 — Descargar de la web

Antes: la base común de los servicios web (`GEN 19`) y los trabajos fuera del controlador principal (`GEN 15`).

| Paso | Objetivo |
|---|---|
| **VID 7.1** El proveedor (`core/video/providers/`): buscar y traer una ficha; Opciones > Vídeo (clave, idioma) |
| **VID 7.2** «Identificar…» para una obra: candidatos, elegir, descargar ficha, reparto, cartel y fondo |
| **VID 7.3** Por lotes: proponer las coincidencias claras, revisar las dudosas; en segundo plano y cancelable |
| **VID 7.4** «Actualizar la ficha» sin pisar lo editado a mano |

### Fase VID 8 — Vista «Ficha»

| Paso | Objetivo |
|---|---|
| **VID 8.1** La vista del centro, de solo lectura, con «Reproducir» |
| **VID 8.2** Edición en la propia ficha |
| **VID 8.3** Pulsar un director, un actor o un género lleva a sus obras |

### Fase VID 9 — Series a fondo

| Paso | Objetivo |
|---|---|
| **VID 9.1** Los episodios en la ficha de la serie; título y sinopsis de cada episodio, descargados |
| **VID 9.2** Progreso: episodios vistos de cada temporada; «siguiente episodio» |

### Fase VID 10 — Extras (sin orden)

Sagas en la barra; tráiler; importar y exportar `.nfo` (para Kodi, Jellyfin y similares); un proveedor para eventos deportivos; obras sin archivo («lo que quiero ver» o lo que está en un disco guardado).

### Decisiones

Tomadas con el autor el 16/11/2026 (el porqué, en [DECISIONES.md](DECISIONES.md)). Lo que queda abierto se cierra en su paso.

| | Qué | Decidido |
|---|---|---|
| **V1** | La ficha, por obra o por archivo | **Por obra** (tabla propia). Los archivos se asignan solos y la cuadrícula muestra una tarjeta por obra (§10) |
| **V2** | El servicio web | TMDb, como proveedor intercambiable. **Antes de `VID 7.1`, comprobar sus condiciones para el uso interno de la empresa**; si no valen, otro proveedor |
| **V3** | Qué se guarda fuera del catálogo | En el `.arca.json`: identificación, visto y lo editado a mano. El archivo de vídeo no se escribe. `.nfo`, solo importar y exportar (`VID 10`) |
| **V4** | Visto / no visto | Por archivo (cada episodio); desde una tarjeta agrupada, a todos sus archivos |
| **V5** | Tipos de obra | Película, serie, documental, evento deportivo y otro. Añadir uno es una línea en `kinds.py` |
| **V6** | `ffmpeg` / `ffprobe` en `tools/` | Sí para los fotogramas; para los datos técnicos, solo si ExifTool no basta (se ve en `VID 1.1`) |
| **V7** | Reproducir | Con el reproductor del sistema |
| **V8** | Secciones de la barra | Las de §9; el orden, en `VID 5` |
| **V9** | Episodios con ficha propia (título, sinopsis, fecha) | Sí, después de las películas (`VID 9`) |
| **V11** | Acciones sobre una tarjeta agrupada | A todos los archivos de la obra (§10.3) |

**Abierto**: **V10**, los textos del módulo («Ficha», «Identificar…», «Visto», «Agrupar en una obra»...): se proponen en cada paso.
