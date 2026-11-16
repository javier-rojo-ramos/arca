# Arca Media — Módulo Imagen: arquitectura y plan

> Documento del módulo Imagen (`ImageModule`, biblioteca `image`: las fotos y los vídeos personales, de cámara o de móvil). Tiene dos partes: **I, arquitectura** (cómo funciona hoy) y **II, planificación** (lo que falta, con los códigos de [PENDIENTE.md](PENDIENTE.md)).
> **Estado (16/11/2026): el módulo funciona de punta a punta.** Este documento se ha escrito **a posteriori**, a partir del código, para tener en un solo sitio qué hace el módulo y dónde está cada cosa. No repite el detalle de [FLUJOS.md](FLUJOS.md), [METADATOS.md](METADATOS.md), [MINIATURAS.md](MINIATURAS.md) ni de los `LEEME.md`: enlaza a ellos. Si el código y este documento no coinciden, manda el código.
> Índice: [INDEX.md](INDEX.md).

## Resumen

**Qué es**: el módulo para las fotos, al estilo de Lightroom: navegar por carpetas, fechas y palabras clave; ver en cuadrícula, de una en una (con zoom 1:1) y en el mapa; clasificar (valoración, marca, color, selección rápida); poner palabras clave; y editar los metadatos descriptivos y la ubicación, que se guardan también en los archivos.

**Qué entra en Imagen**: las fotos y los vídeos personales. Un vídeo es de Imagen si lo dice su carpeta, su nombre (`IMG_`, `VID_`, `PXL_`...), sus metadatos (cámara o GPS) o el usuario (`core/catalog/libraries.py`); las películas van al módulo Vídeo ([MOD_VIDEO.md](MOD_VIDEO.md)).

**Qué es del módulo y qué es común**: del módulo son su barra izquierda y lo que declara (vistas, orden, filtros, opciones del mapa). La cuadrícula, la vista individual, el mapa, la barra de filtros, la barra inferior y el inspector son comunes a todos los módulos; aquí se cuenta lo que hacen con las imágenes.

| Función | Estado |
|---|---|
| Barra izquierda: biblioteca, carpetas, fechas, palabras clave | Hecho y verificado |
| Cuadrícula, vista individual con zoom 1:1 | Hecho y verificado |
| Mapa: ver, ubicar fotos soltándolas, mover, quitar la ubicación, deshacer | Hecho y verificado; «Sin ubicación» y la chincheta, pendientes de verificar |
| Clasificación, guardada en los archivos | Hecho y verificado |
| Palabras clave: leer, asignar, gestionar el árbol | Hecho y verificado |
| Metadatos: lectura con ExifTool y edición (título, pie, creador, copyright, ubicación, GPS) | Hecho y verificado con JPEG, HEIC y DNG; otros RAW, sin probar (`IMG 2`) |
| Miniaturas (cuatro tamaños) | Hecho y verificado; las de los vídeos, pendientes (`VID 4.1`) |
| Perfil de tarjeta, reconocimiento facial, ubicar por la hora con un GPX | Pendiente (`GEN 16` e `IMG 1`, `IMG 3`, `TRK 8`) |

---

# Parte I — Arquitectura

## 1. El módulo (`controllers/app_modules/image_module.py`)

`ImageModule(LibraryModule)` es pequeño (desde el 16/11/2026 es un módulo de biblioteca más, como Tracks, Vídeo y Audio): declara lo que quiere, y lo común (pasar a `ModuleHost` lo elegido en la barra, leer en segundo plano lo que muestra, lo guardado por catálogo) está en `LibraryModule`. La barra no sabe nada de la base de datos.

| Qué declara | Valor |
|---|---|
| Vistas (`views`) | Cuadrícula (la inicial), vista individual y mapa |
| Mapa (`map_options`) | `allow_geotag`: se ubican fotos soltándolas y se mueven las ubicadas |
| Tipos del filtro (`filter_media_types`) | Foto y vídeo |
| Columnas de partida de «Metadatos» (`filter_metadata_fields`) | Fecha de captura, modelo de la cámara y objetivo (como Lightroom) |
| Campos de orden (`sort_fields`) | Los seis comunes (`COMMON_SORT_FIELDS`, `core/catalog/grid_orders.py`) |
| Orden de partida (`default_order`) | Hora de captura, ascendente |

- `refresh` lee en segundo plano, de una vez, los contadores de la biblioteca, el árbol de carpetas (`folder_tree.fetch_folder_tree(conn, "image")`), la línea de tiempo (`timeline.fetch_timeline`) y el árbol de palabras clave con sus recuentos (`keywords.fetch_keyword_tree`).
- `show_source`: lo pide el inspector (la flecha «ver sus fotos» de una palabra clave); la elige en la barra.
- `save_state` / `restore_state`: lo desplegado y la fila elegida, por catálogo (los escribe `ModuleHost` en `settings.json`).
- Cómo encajan los módulos en la ventana: [FLUJOS.md](FLUJOS.md) §11.

## 2. Barra izquierda (`ui_helpers/sidebars/library_sidebar.py`)

Es la barra común (`LibrarySidebar`), con la «Lista de palabras clave» como sección de más (`ExtraSection`, declarada en `image_module.py`). Solo navega: una fila elegida en toda la barra, que produce un `GridSource`. Cada sección con árbol es un archivo de `ui_helpers/sidebars/sections/` (`tree_section.py` es la base); la barra hace de contenedor. Las secciones se pliegan, se ocultan y se reordenan (`ui_helpers/layout/section_registry.py`; [FLUJOS.md](FLUJOS.md) §9).

| Sección | Qué muestra | De dónde sale |
|---|---|---|
| «Biblioteca - Imagen» | «Todas las imágenes» y «Selección rápida», con sus números | `count_grid_items` |
| «Carpetas» (`folder_section.py`) | Las ubicaciones y carpetas que tienen algo de Imagen; menú «Mostrar en el Explorador» | `fetch_folder_tree`; con la opción de subcarpetas del Catálogo |
| «Fechas» (`date_section.py`) | Años (el más reciente arriba), meses («01 Enero»), días («10 Miércoles») y «Sin fecha» | `timeline.fetch_timeline`; cada fila es `timeline.date_source`, con la misma regla que la columna «Fecha de captura» del filtro |
| «Lista de palabras clave» (`keyword_section.py`) | El árbol, con filtro y recuentos (con las hijas); en gris, las que no tienen nada en Imagen | `keywords.fetch_keyword_tree` |

Los árboles no cogen el teclado: tras elegir una fila, los atajos siguen yendo a las fotos.

## 3. Centro: las vistas

| Vista | Dónde | Notas |
|---|---|---|
| Cuadrícula | `ui_helpers/models/media_grid_model.py`, `ui_helpers/delegates/thumbnails_delegate.py` | Común. La tarjeta: miniatura, valoración, marca, color, círculo de selección rápida y, si tiene ubicación, la chincheta, que lleva al mapa. [FLUJOS.md](FLUJOS.md) §6 |
| Vista individual | `ui_helpers/widgets/single_media_view.py`, `single_view_zoom.py`; `ui_helpers/models/full_image_loader.py`; `core/thumbnails/full_image.py` | La imagen que cabe, nítida y con precarga de la siguiente; zoom 1:1 con el original (clic, Z, arrastrar; Ctrl + rueda). En un RAW, el 1:1 es su mayor vista previa. [FLUJOS.md](FLUJOS.md) §11 |
| Mapa | `controllers/map_controller.py` y el componente de mapa | Marcadores de lo que tiene coordenadas y la tira de fotos debajo. En Imagen, además: soltar fotos de la tira para ubicarlas (pregunta a partir de 50), moverlas, «Quitar la ubicación» y Ctrl+Z (`core/catalog/geotagging.py`, `controllers/undo_history.py`). [MOD_TRACKS.md](MOD_TRACKS.md) y [FLUJOS.md](FLUJOS.md) §16 |

Entrar, salir y navegar entre vistas (doble clic, Intro, Esc, G, M, flechas), y el archivo actual recordado por módulo: `controllers/center_view_controller.py`.

## 4. Inspector (panel derecho)

Es el mismo en todos los módulos y depende solo de la selección ([FLUJOS.md](FLUJOS.md) §12; `ui_helpers/inspector/`, `controllers/inspector_controller.py`). Con imágenes seleccionadas:

| Sección | Archivo | Qué hace |
|---|---|---|
| «Selección» | `selection_section.py` | Nombre, carpeta, tamaño, fecha, contenido, biblioteca y estado; sin selección, el resumen de lo que se ve |
| «Metadatos» | `metadata_section.py`, `metadata_fields.py`, `editable_row.py`, `value_parsing.py` | **Solo de la biblioteca Imagen.** Tres vistas: «Por defecto», «Ubicación» y «EXIF». Edita título, pie de ilustración, creador, copyright, ubicación (sublugar, ciudad, provincia, país y su código), GPS, altitud y dirección; con varios archivos, «Varios» y el aviso «Edición múltiple» |
| «Palabras clave» | `keyword_editor_section.py` | La caja con sugerencias y «Últimas palabras clave» |
| «Lista de palabras clave» | `keyword_list_section.py` | El árbol con casillas: marcar, soltar fotos sobre una palabra, gestionar el árbol (`ui_helpers/helpers/keyword_menu.py`) y la flecha «ver sus fotos» |

## 5. Filtros, orden y colecciones inteligentes

- **Barra de filtros** (común; [FLUJOS.md](FLUJOS.md) §15; `controllers/filter_controller.py`): «Texto», «Atributos» (marcas, estrellas, colores, selección rápida, foto o vídeo), «Metadatos» (columnas en cascada) y los ajustes personalizados, entre ellos «Ubicación» y «Sin ubicación».
- **Un solo motor** para filtros y colecciones inteligentes: las reglas (`RuleSet`) y los campos de `core/catalog/smart_fields.py` (grupos «Estándar» e «Imagen»); la lista y lo que se ve de cada campo, en [METADATOS.md](METADATOS.md).

## 6. Datos

- **Tablas**: `media_items` (lo común: título, creador, fecha, tamaño, GPS, ubicación, clasificación), `photo_details` (cámara, objetivo, exposición, recorte de Lightroom), `video_details` (los vídeos personales: cámara, objetivo, códec) y `keywords` / `media_keywords`. Esquema y quién escribe cada columna: [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md).
- **Lectura** (`core/metadata/image/`: `fields.py`, `rules.py`, `extractor.py`; `pillow_extractor.py` como reserva sin ExifTool, y `core/metadata/video/` para los vídeos): una lista de campos declarativa, con su prioridad entre etiquetas (el XMP primero en el GPS, como Lightroom). `IMAGE_FIELDS_VERSION` 9 y `VIDEO_FIELDS_VERSION` 2: al subirlas, se relee solo. Detalle y recetas: [METADATOS.md](METADATOS.md) y [core/metadata/LEEME.md](../core/metadata/LEEME.md).
- **Un extractor nunca escribe datos del usuario**: la valoración, la marca, el color y las palabras clave que trae el archivo viajan aparte y el procesador decide si se aplican.

## 7. Lo que se guarda en los archivos (`core/userdata/`)

Valoración, marca, color, palabras clave y los metadatos editados se guardan en el catálogo **y en el propio archivo**, para que otros programas los vean y sobrevivan a recrear el catálogo. Un destino por formato (`policy.py`):

| Destino | Formatos |
|---|---|
| XMP dentro del archivo | JPEG, TIFF, PNG, WebP, GIF, PSD, DNG, HEIC/HEIF/AVIF |
| Sidecar `.xmp` junto al original | RAW propietarios (CR2, CR3, NEF, ARW, ORF, RW2, RAF, PEF...) |
| `.arca.json` de la carpeta | Lo demás (los vídeos, BMP, JPEG XL...) |

Solo se escribe lo cambiado, en segundo plano, comprobando lo escrito; al releer manda el archivo, salvo en lo que está pendiente de escribir. Reglas, flujo y recetas: [core/userdata/LEEME.md](../core/userdata/LEEME.md); la escritura de los metadatos descriptivos y del GPS, comparada con Lightroom, en [METADATOS.md](METADATOS.md).

## 8. Miniaturas (`core/thumbnails/`)

Cuatro tamaños (160, 480, 1200 y 2560 px de lado largo), en la caché del catálogo; orígenes por formato (`sources/`: Pillow, HEIF y la vista previa incrustada de los RAW, con ExifTool); `THUMBNAIL_VERSION` 2. Se generan en segundo plano tras leer los metadatos. Detalle: [MINIATURAS.md](MINIATURAS.md) y [core/thumbnails/LEEME.md](../core/thumbnails/LEEME.md). Los vídeos no tienen miniatura todavía: la tarjeta dibuja el marcador con la duración.

## 9. Lo verificado y lo que no

De [ESTADO.md](ESTADO.md):

- **Verificado por el autor en Windows**: metadatos de JPEG, HEIC (horizontal y vertical) y DNG, iguales a los paneles de Lightroom; vídeos de iPhone; lectura y escritura de la clasificación (XMP incrustado, sidecar de un NEF, `.arca.json`); edición de título y pie leída por Lightroom en un JPG y en un NEF con sidecar; GPS escrito y leído como en Lightroom Classic 16; 22 000 fotos con sus miniaturas.
- **Sin probar**: ExifTool con RAW distintos de DNG (NEF, CR2, CR3, ARW, ORF, RW2, PEF, RAF) y con WebP; la escritura de metadatos descriptivos con un DNG y un CR3; vídeos de Android y de cámara; macOS y Linux.
- **Comprobaciones sueltas** anotadas: el recorte de Lightroom en fotos verticales y en RAW con sidecar, `city` y `region`, un sidecar creado por la aplicación leído por Lightroom.

---

# Parte II — Planificación

Lo que falta del módulo, con los códigos de [PENDIENTE.md](PENDIENTE.md) (ahí está la lista vigente; esto es el resumen de lo que toca a Imagen).

### Fases del módulo

| Fase | Qué | Notas |
|---|---|---|
| `IMG 1` | La tarjeta de Imagen | Sus líneas de información (dimensiones, duración...), con el perfil de tarjeta común (`GEN 16`) |
| `IMG 2` | Verificar los RAW con ExifTool real | `inspect_cli --campos` con NEF, CR2/CR3, ARW, ORF, RW2, PEF, RAF y WebP, comparando con Lightroom |
| `IMG 3` | Reconocimiento facial | Personas como palabras clave especiales; importar las regiones de caras de Lightroom; por decidir, la detección propia |

### Fases de otras categorías que afectan a Imagen

| Fase | Qué |
|---|---|
| `GEN 1` | Deshacer en toda la aplicación (hoy, solo lo hecho en el mapa) |
| `GEN 2` | Más metadatos editables: la fecha (en su ventana), el estado del copyright, el género y la escena |
| `GEN 4` | Miniaturas, extras: PSD, `rawpy` (también para el 1:1 de los RAW), insignia «editada en Lightroom» |
| `GEN 7` | Guardar el filtro activo como colección inteligente |
| `GEN 16` | Perfil de tarjeta, común a todos los módulos |
| `GEN 8` | Sección «Ubicación» del inspector con el mapa; el rumbo de la foto en el mapa |
| `VID 4.1` | Fotograma de los vídeos con `ffmpeg`: da miniatura también a los vídeos de Imagen |
| `TRK 8` | Ubicar fotos por la hora con un GPX; las fotos de una ruta |

### Mejoras menores que tocan a Imagen

En las listas de [PENDIENTE.md](PENDIENTE.md): mantener el 1:1 y la zona al pasar de foto y más niveles de zoom (vista individual); una vista «Personalizada» y vistas IPTC y DNG en «Metadatos»; fusionar y arrastrar palabras clave, conjuntos de palabras, importar las de Lightroom; un solo componente para el árbol de carpetas del Catálogo y el de Imagen.

### Por decidir

Nada bloquea hoy. Al llegar a su paso: en `IMG 1`, qué líneas de información lleva la tarjeta y si el perfil es por módulo o por vista; en `IMG 3`, si la detección de caras es propia (biblioteca local, sin nube), dónde se guardan las regiones y si se escriben en el XMP.
