# Arca Media — Pendiente (hoja de ruta)

> Solo lo que falta. Lo entregado sale de aquí: su detalle está en [HISTORIAL.md](HISTORIAL.md) y lo que falte por comprobar, en [ESTADO.md](ESTADO.md).
> Índice: [INDEX.md](INDEX.md).

**Plan de interfaz** (acordado el 29/10/2026 y revisado el 08/11/2026; ver [FLUJOS.md §11](FLUJOS.md) y [DECISIONES.md](DECISIONES.md)): el mismo esqueleto en todos los módulos (izquierda navegar, centro ver, derecha el inspector), la edición en el inspector y ventanas solo para lo pesado o por lotes, una tarjeta configurable por «perfiles» y un único motor de filtros (`RuleSet`) con estado por módulo.

## Cómo se nombra (desde el 16/11/2026)

- Lo pendiente se agrupa en **categorías**: GENERAL (lo que comparten los módulos o no es de ninguno) y una por módulo: CATÁLOGO, IMAGEN, MÚSICA (el módulo Audio), VÍDEO y TRACKS.
- Cada funcionalidad principal es una **fase**, con el código de su categoría y un número: `GEN 1`, `CAT 1`, `IMG 1`, `MUS 1`, `VID 1`, `TRK 6`. Sus **pasos** son `X.1`, `X.2`...: `TRK 6.3` es el paso 3 de la fase 6 de Tracks. Un paso que se parte lleva letra (`6.3a`, `6.3b`).
- Los números no se reutilizan: una fase terminada sale de aquí y su número queda libre para siempre. El número no fija el orden: el orden se decide al planificar (ver «En curso»).
- Las fases de TRACKS conservan el número de [MOD_TRACKS.md](MOD_TRACKS.md) §10 (allí, las fases 0 a 3 fueron el mapa; la 4 y la 5, lo básico de Tracks y el perfil de elevación, hechas el 14 y el 15/11/2026).
- Lo pequeño no es una fase: va en la lista **«Mejoras menores»** de su categoría, sin número.
- Cada módulo tiene su documento `MOD_` ([MOD_TRACKS.md](MOD_TRACKS.md), [MOD_MUSICA.md](MOD_MUSICA.md)), con su arquitectura y el detalle de sus fases; aquí, solo la lista.
- Cada módulo tiene su documento `MOD_` ([MOD_TRACKS.md](MOD_TRACKS.md), [MOD_MUSICA.md](MOD_MUSICA.md)), con su arquitectura y el detalle de sus fases; aquí, solo la lista.
- Cada módulo tiene su documento `MOD_` ([MOD_TRACKS.md](MOD_TRACKS.md), [MOD_MUSICA.md](MOD_MUSICA.md)), con su arquitectura y el detalle de sus fases; aquí, solo la lista.
- [HISTORIAL.md](HISTORIAL.md) y las cabeceras del código citan los bloques de antes (A.1 a A.7, B, C.1 a C.12): la tabla del final dice a qué corresponde cada uno.

## En curso

- **TRACKS**: terminadas las fases 4 y 5; lo siguiente del plan acordado es `TRK 6` (edición).
- **MÚSICA y VÍDEO**: los dos módulos muestran ya su biblioteca, con la barra de Tracks (biblioteca, carpetas y fechas; 15/11/2026). Música está definida ([MOD_MUSICA.md](MOD_MUSICA.md), 16/11/2026): lo siguiente, `MUS 1`. Vídeo, por definir (será `MOD_VIDEO.md`).

---

## GENERAL

### Fase GEN 1 — Deshacer en toda la aplicación

Acordado con el autor el 13/11/2026: un solo historial de cambios en el que cada cambio sabe deshacerse, con Ctrl+Z en toda la ventana. **Empezado**: `controllers/undo_history.py` (`UndoHistory`), que hoy llena el mapa (ubicar, mover y quitar la ubicación). Nunca lo que no tiene vuelta atrás («Eliminar del disco», «Purgar»). Deshacer algo ya escrito en los archivos es otro cambio más, que se vuelve a escribir.

- **GEN 1.1** Rehacer (Ctrl+Y).
- **GEN 1.2** La valoración, la marca y el color.
- **GEN 1.3** Los metadatos del inspector.
- **GEN 1.4** Las palabras clave.

### Fase GEN 2 — Más metadatos editables

El mecanismo está hecho (título, pie, creador, copyright y ubicación desde el 10/11/2026; GPS, altitud y dirección desde el 11/11/2026; la actividad de un track, el 14/11/2026; receta en [COMO_AMPLIAR.md](COMO_AMPLIAR.md)). La escritura con un NEF real y su sidecar, probada el 14/11/2026; sin probar con un DNG y con un CR3. La edición de las etiquetas de audio y de las fichas de vídeo, en `MUS 6`, `MUS 7` y `VID 4`.

- **GEN 2.1** La fecha (ventana propia, por biblioteca).
- **GEN 2.2** El estado del copyright, el género y la escena.

### Fase GEN 3 — Datos del usuario, lo que falta

- **GEN 3.1** `xmp:Rating = -1` de Bridge como rechazo.
- **GEN 3.2** Los errores de la fase `userdata`, en la lista de `scan_errors` de la interfaz (`GEN 6.1`; hoy solo se avisa en la barra de estado y en el registro), y no reintentar en cada pasada los que fallan siempre (solo lectura).
- **GEN 3.3** Notas y colecciones en el archivo de carpeta (caben como claves nuevas: se conservan las desconocidas).

### Fase GEN 4 — Miniaturas: extras

Las de vídeo y las carátulas de audio, en `VID 2` y `MUS 3`.

- **GEN 4.1** PSD.
- **GEN 4.2** `rawpy`: RAW sin vista previa o con una pequeña; también para el 1:1 de la vista individual, que hoy en un RAW es su mayor vista previa (en un DNG de Lightroom, a veces de solo 1024 px).
- **GEN 4.3** Limpiar los huérfanos de la caché y comprobar que los archivos existen.
- **GEN 4.4** Insignia «editada en Lightroom» a partir de `XMP-crs:HasCrop` / `HasSettings` (y, opcional, aplicar solo el recorte cuando `CropAngle` sea 0).
- **GEN 4.5** Solo si el espacio llegara a importar (hoy ≈ 38 % de los originales): el tamaño de 2560 solo a demanda y, después, WebP en los dos tamaños grandes; las dos cosas obligan a subir `THUMBNAIL_VERSION`. Medir antes cuánto pesa cada `cache/photo/<tamaño>`.

### Fase GEN 5 — Empaquetado

Incluir `tools/exiftool` (`--add-data`), `--collect-data puremagic`, `defusedxml` y los datos de `pillow-heif`; QtWebEngine (el mapa: unos 220 MB más, el proceso `QtWebEngineProcess.exe` y la carpeta `resources` de Qt; [MOD_TRACKS.md](MOD_TRACKS.md) §9); comprobar que la ruta a `tools/exiftool` (basada en `__file__`) vale dentro del paquete; probar en macOS y Linux. Pasos, por definir.

### Fase GEN 6 — Interfaz sin terminar

- **GEN 6.1** La lista de `scan_errors`.
- **GEN 6.2** Las acciones de menú sin conectar (`action_add_files`, `action_save`, `action_save_as`, `action_convert_format`, `action_about`).
- **GEN 6.3** Separar «Abrir catálogo» de «Nuevo catálogo», si se quiere un diálogo propio.

### Fase GEN 7 — «Guardar filtro activo como colección inteligente…»

En el desplegable de ajustes personalizados de la barra de filtros (los grupos de reglas que necesitaba ya están). Por decidir: si se guarda también el origen que se ve (con una casilla; una carpeta solo se puede guardar por su ruta relativa, y una colección estática necesitaría un campo «Colección») y si la cuadrícula pasa a la colección nueva.

### Fase GEN 8 — Mapa: lo que queda fuera de Tracks

De [MOD_TRACKS.md](MOD_TRACKS.md) §10, «Después (sin fecha)»:

- **GEN 8.1** Sección «Ubicación» del inspector con el mapa.
- **GEN 8.2** El rumbo de la foto (`gps_direction`), dibujado y editable en el mapa.
- **GEN 8.3** Descarga de zonas para usarlas sin conexión.

### Fase GEN 9 — Módulo Ebooks

Sin categoría propia hasta que se planifique. Extractor de ebooks con su tabla de detalles; decidir si PDF y CBZ cuentan como ebook. El grupo «Ebooks» de las colecciones inteligentes existe vacío; en `resources/images` está `library_books.svg` sin registrar.

### Fase GEN 10 — Optimizaciones (cuando se midan)

Pedir a ExifTool solo las etiquetas necesarias, `-stay_open` o varios procesos; un grupo de hilos propio para los trabajos (hoy comparten los 4 del gestor de BD: metadatos o escritura, miniaturas y añadir carpeta pueden ocupar 3 a la vez); más índices (p. ej. por valoración).

### Mejoras menores (GENERAL)

- **Cuadrícula**: recordar el desplazamiento exacto de cada módulo (desde el 12/11/2026 cada módulo recuerda su archivo actual, que queda a la vista al volver, pero no la posición; al recargar con el mismo origen, la posición se conserva); refresco por filas al terminar los metadatos (hoy recarga entera); recargar una colección inteligente que se está viendo cuando un elemento deja de cumplir las reglas; un módulo sin cuadrícula oculta el deslizador (y el orden, si no ofrece campos).
- **Vista individual**: mantener el 1:1 y la zona al pasar de foto (como Lightroom, para comparar el enfoque de una ráfaga); más niveles de zoom con Ctrl + rueda (2:1, 4:1, para ver los píxeles).- **Inspector**: en «Metadatos», una vista «Personalizada» (el usuario elige los campos; en `settings.json`) y vistas IPTC y DNG; miniatura grande arriba cuando la selección es de una sola biblioteca.
- **Palabras clave**: fusionar dos palabras (hoy, renombrar una con el nombre de otra hermana avisa); arrastrar una palabra a otra para moverla; «Mover a…» con un árbol filtrable si la lista se hace larga; «Conjuntos de palabras clave» personalizables (como Lightroom) junto a «Últimas palabras clave»; quitar una palabra de «Últimas» sin borrarla. Opcional: importar el `.txt` de *Metadatos > Exportar palabras clave* de Lightroom (palabras sin usar, categorías entre corchetes → `include_on_export = 0`, sinónimos entre llaves); importador de solo lectura del catálogo de Lightroom (`.lrcat`) para traer palabras, valoraciones y colecciones de los vídeos.
- **Secciones de las barras** (personalizables desde el 14/11/2026; [FLUJOS.md §9](FLUJOS.md)): si se quiere, mover una sección de una barra a la otra (el registro ya lo admite: `SectionSpec.sidebars`; faltaría que la sección sirva en las dos y revisar `reset` de una sola barra); un icono propio para la página «Paneles».
- **Una sola barra de biblioteca**: `ImageSidebar` y `LibrarySidebar` (la de Tracks, Vídeo y Audio) hacen casi lo mismo; pasar Imagen a `LibrarySidebar` con la «Lista de palabras clave» como sección opcional. Es una refactorización: paso aparte.
- **«Abrir en su módulo»**: atajo de navegación («ver esta foto en su línea de tiempo»), con baja prioridad.
- **Mapa**: si se quiere, la distancia a la que el punto ámbar engancha la línea del track activo (`HOVER_PX`, 24 px), como opción en Opciones > Mapa.
- **Aspecto**: fuente de la aplicación (incluida en `resources/fonts`, p. ej. Inter, con tamaño fijo); esquinas redondeadas de los menús; si el autor lo pide, una opción para que la etiqueta de color sea una franja inferior en lugar de teñir la tarjeta.
- **Omitido a propósito de la v1 del esquema**: borrado suave (`deleted_at`), `dominant_color`, milisegundos y zona de las fechas secundarias, normalización de `country_code` (el XMP admite 2 o 3 letras; hoy se guarda tal cual).

---

## CATÁLOGO

### Fase CAT 1 — Archivos sueltos y ubicaciones solapadas

- **CAT 1.1** Añadir archivos sueltos (hoy solo carpetas completas; `action_add_files` está sin conectar).
- **CAT 1.2** Fusión de ubicaciones solapadas (hoy se rechazan).

### Fase CAT 2 — Hashes

`hash_partial`, `hash_full`, `hash_verified_at`. Pasos, por definir:

- Duplicados.
- Comprobación de integridad.
- Reasociar un archivo renombrado fuera de la aplicación.

### Mejoras menores (CATÁLOGO)

- **Barra lateral y colecciones**: mover colecciones entre conjuntos arrastrando; «Orden personalizado» en las colecciones estáticas (`collection_items.position`); exportar e importar colecciones, o que sobrevivan a recrear el catálogo (hoy solo están en la BD); «Clasificación» del sistema con «≥» en lugar de «=»; «Duplicar» una colección del sistema como inteligente del usuario; campo «Colección» (pertenencia) en las inteligentes; «Guardar la selección rápida como colección»; «Últimos archivos añadidos» en la sección Catálogo.
- **Archivos ausentes**: filtro «ocultar ausentes»; en la vista individual, «Localizar…» junto al aviso de archivo no encontrado.
- **Bibliotecas**: 2b-2, **aparcado** (el autor no cree probable cambiar una carpeta de «Música» a «Fotos y vídeos»): cambiar el tipo de contenido de una carpeta ya catalogada desde su menú, ofreciendo quitar lo que ya no encaja. Que la biblioteca puesta a mano sobreviva a recrear el catálogo: no por ahora (sería una clave `library` en el `.arca.json`).
- Posible: un solo componente para el árbol de carpetas del Catálogo y el de Imagen.

---

## IMAGEN

### Fase IMG 1 — Perfil de tarjeta

Proporción y líneas de información (dimensiones, duración...); las de la vista individual ya se piden por archivo (`fetch_media_file`). Es la «tarjeta configurable por perfiles» del plan de interfaz: lo que se haga aquí sirve a los demás módulos. Pasos, por definir.

### Fase IMG 2 — Verificar los RAW con ExifTool real

`inspect_cli --campos` con NEF, CR2/CR3, ARW, ORF, RW2, PEF, RAF y WebP; comparar con Lightroom (tamaño y orientación, sobre todo; `DefaultCropSize` solo existe en los DNG). Hecho con JPEG, HEIC (horizontal y vertical) y DNG.

### Fase IMG 3 — Reconocimiento facial

Anotado el 03/11/2026: personas como palabras clave especiales (Lightroom las guarda en «[Personas]»). Si procede, importar las regiones de caras de Lightroom (`XMP-mwg-rs:RegionInfo`: nombre y rectángulo de cada cara, tipo `Face`), que ya están en los archivos etiquetados. Por decidir: detección y agrupación propias (biblioteca local, sin nube), dónde se guardan las regiones (tabla nueva) y si se escriben de vuelta en el XMP.

---

## MÚSICA (módulo Audio)

Definido con el autor el 16/11/2026. La arquitectura, el detalle de cada paso (archivos, cómo se acepta) y lo que queda por decidir (M1 a M7), en [MOD_MUSICA.md](MOD_MUSICA.md). El escritor (`MUS 6`) va antes que la edición (`MUS 7`), a propósito.

### Fase MUS 1 — Leer las etiquetas

- **MUS 1.1** Base de audio: mutagen (la instala el autor), la tabla campo ↔ etiqueta y la lectura, en `core/audio/`.
- **MUS 1.2** La tabla `audio_details` (migración 5).
- **MUS 1.3** El extractor (`core/metadata/audio/`, `AUDIO_FIELDS_VERSION`): las canciones se leen solas al abrir el catálogo.
- **MUS 1.4** Recuento de las canciones con varios géneros o artistas (decide si las listas van en tablas).

### Fase MUS 2 — Verlas

- **MUS 2.1** Sección «Audio» del inspector, de solo lectura.
- **MUS 2.2** Orden propio: artista, álbum, pista, año y duración.
- **MUS 2.3** Campos del grupo «Audio» en filtros y colecciones inteligentes.

### Fase MUS 3 — Carátulas como miniatura

- **MUS 3.1** La carátula incrustada, origen de la miniatura (cuadrada, sin ampliar).
- **MUS 3.2** `folder.jpg` o `cover.jpg` de reserva, si se decide.

### Fase MUS 4 — Navegar

- **MUS 4.1** Sección «Artistas» (artista del álbum ▸ álbum).
- **MUS 4.2** Secciones «Géneros» y «Años».
- **MUS 4.3** Listas que se recorren con las flechas (álbumes; vale también para las películas, `VID 1.3`): el detalle, en [MOD_MUSICA.md](MOD_MUSICA.md).

### Fase MUS 5 — Vista de lista

Estilo Mp3tag; una vista más del centro, que sirve a otros módulos.

- **MUS 5.1** La lista, con la selección compartida con la cuadrícula.
- **MUS 5.2** Columnas a elegir y orden por columna.
- **MUS 5.3** Opcional: vista de álbumes con su carátula.

### Fase MUS 6 — Escribir en los archivos

En el propio archivo, sin generar copias (regla del 16/11/2026). Sin interfaz: se prueba con copias.

- **MUS 6.1** Escritor de MP3 (ID3): solo lo editado, la versión de ID3 conservada, comprobando las etiquetas y que el audio no cambia.
- **MUS 6.2** En la cola de escritura: los campos de audio en `editable_fields.py` y el escritor en `sync.py`; lo que no sabe guardar, al `.arca.json`. La marca de pendiente sigue siendo un bit por campo (caben 63; se revisa con Vídeo).
- **MUS 6.3** FLAC.
- **MUS 6.4** M4A y Ogg/Opus.

### Fase MUS 7 — Editar

- **MUS 7.1** Edición en la sección «Audio» del inspector.
- **MUS 7.2** Con varias canciones («Varios», «Edición múltiple»).
- **MUS 7.3** Opcional: editar en la vista de lista.

### Fase MUS 8 — Herramientas por lotes

- **MUS 8.1** Numerar pistas, mayúsculas y minúsculas, buscar y reemplazar.
- **MUS 8.2** Nombre de archivo → etiqueta.
- **MUS 8.3** Etiqueta → nombre de archivo (renombra originales: con su decisión, M6).

### Fase MUS 9 — Carátulas: cambiarlas y guardarlas

- **MUS 9.1** La carátula en grande en el inspector.
- **MUS 9.2** Escribirla en el archivo, por la misma cola.
- **MUS 9.3** Cambiarla: arrastrar, «Elegir…», pegar o `folder.jpg`; para una canción, la selección o el álbum.
- **MUS 9.4** Extraerla o quitarla.

### Fase MUS 10 — Internet

Etiquetas y carátulas de MusicBrainz y Cover Art Archive, como una edición más.

---

## VÍDEO

### Fase VID 1 — Navegación propia

La base está (15/11/2026: `VideoModule` con su biblioteca, carpetas y fechas). Falta:

- **VID 1.1** Secciones de la barra: directores y actores.
- **VID 1.2** Campos de orden (duración...) y de colecciones inteligentes (el grupo «Vídeo» existe vacío).
- **VID 1.3** Listas que se recorren con las flechas (películas): lo de `MUS 4.3`.

### Fase VID 2 — Miniaturas de vídeo

Lo piensa el autor. Fotograma con `ffmpeg` (en `tools/ffmpeg`, como ExifTool; hacia el 10 % de la duración, para evitar negros), como un origen más del motor (`video_frame`) con la misma escalera de tamaños. Por decidir: en las películas, fotograma o marcador de póster hasta descargar la portada.

### Fase VID 3 — Fichas de películas

Descarga de fichas (p. ej. TMDb) y de la portada (`media_assets/posters`). Lo descargado entra como una edición más, por la misma cola que lo editado a mano. Pasos, por definir.

### Fase VID 4 — Edición de los metadatos

Como `MUS 6` y `MUS 7`: el escritor de vídeo (etiquetas del contenedor, `.nfo` o solo `.arca.json`: por decidir) y las listas (reparto), en tablas propias.

### Mejoras menores (VÍDEO)

- **Vídeo convertido** (`.MOV` → `.mp4` en HEVC, pregunta del autor): hoy, al sincronizar, el `.MOV` queda ausente y el `.mp4` entra como nuevo (pierde valoración, marca, color y colecciones). Idea: si un ausente y un nuevo de la misma carpeta comparten nombre base y duración (± 1 s), proponer reasociarlos (mismo id, ruta nueva).

---

## TRACKS

Plan revisado con el autor el 14/11/2026: lo básico, el perfil de elevación, la edición y la creación, de lo más útil a lo menos necesario. El detalle de cada paso (archivos, de qué depende, cómo se acepta) está en [MOD_TRACKS.md](MOD_TRACKS.md) §10; las decisiones, en §11.

### Fase TRK 5 — Perfil de elevación (queda un paso)

- **TRK 5.4** Extras, **en espera** (el autor, 15/11/2026): eje por tiempo además de por distancia.

### Fase TRK 6 — Edición

Imprescindibles (6.1 a 6.5) y útiles (6.6 a 6.8).

- **TRK 6.1** Guardar sin pérdidas, sobre el propio GPX (D2, decidida el 16/11/2026). Incluye que la actividad editada vaya al `<type>` del GPX exportado.
- **TRK 6.2** El modelo de edición, con deshacer y rehacer.
- **TRK 6.3** Editar en el mapa: mover, borrar e insertar con el punto medio fantasma.
- **TRK 6.4** Tramos: seleccionar, estadísticas, borrar, recortar el principio o el final.
- **TRK 6.5** Dividir, unir e invertir.
- **TRK 6.6** Simplificar.
- **TRK 6.7** Limpiar errores del GPS: duplicados, picos, saltos de velocidad, nubes estando parado.
- **TRK 6.8** La elevación (modelo de elevaciones): rellenar, sustituir, suavizar.

### Fase TRK 7 — Creación

- **TRK 7.1** Dibujar punto a punto (estadísticas en vivo, altitud del modelo, exportar).
- **TRK 7.2** El enrutado por caminos.
- **TRK 7.3** Los waypoints (nombre, descripción, símbolo).

### Fase TRK 8 — Fotos y tracks

Para después; no depende de la edición y se puede adelantar. Pasos, por definir:

- Las fotos de la ruta y «Crear colección con esta ruta y sus fotos».
- Ubicar fotos por la hora con un GPX.

### Por decidir (TRACKS)

Detalle y recomendación en [MOD_TRACKS.md](MOD_TRACKS.md) §11; ninguna bloquea hasta su paso. **D2, decidida** (el autor, 16/11/2026): un GPX editado se guarda sobre el propio archivo, sin generar copias; cómo se hace con seguridad, en `TRK 6.1`. **D2, decidida** (el autor, 16/11/2026): un GPX editado se guarda sobre el propio archivo, sin generar copias; cómo se hace con seguridad, en `TRK 6.1`. **D2, decidida** (el autor, 16/11/2026): un GPX editado se guarda sobre el propio archivo, sin generar copias; cómo se hace con seguridad, en `TRK 6.1`.

| Decisión | Para | Qué |
|---|---|---|
| **D8** | `TRK 6.2` | Hora de los puntos insertados (recomendado: interpolada) |
| **D12** | `TRK 6.5` | Las horas al invertir un track (recomendado: quitarlas con aviso) |
| **D13** | `TRK 7.2` | El servicio de enrutado (a comparar al llegar) |
| **D4** | `TRK 8` | Cómo se calculan las fotos de una ruta |
| **D9** | Cada paso | Los textos del módulo (se proponen en cada paso) |

### Mejoras menores (TRACKS)

- **Sección «Track» del inspector**: sin selección no sale (el inspector solo da a las secciones los id seleccionados); si se quiere el total de lo que se ve («Todos los tracks: 93,7 km»), hace falta pasarles el origen. Tiempo en movimiento (sin las paradas): `core/tracks/profile.py` aún no lo calcula.
- **Waypoints**: el símbolo de cada uno (`<sym>`, que ya se lee) con un dibujo propio.
- **Perfil**: el resto de su estilo (`ProfileStyle`), si se quiere, en Opciones > Tracks.
- **Sin fecha** ([MOD_TRACKS.md](MOD_TRACKS.md) §10): MDT05 del IGN; otros formatos de track.

---

## Equivalencia con la numeración anterior

Para leer [HISTORIAL.md](HISTORIAL.md), [DECISIONES.md](DECISIONES.md) y las cabeceras del código, que citan los bloques de antes. Lo que no aparece (A.1, A.2, casi todo A.3) está terminado.

| Antes | Ahora |
|---|---|
| A.3 (lo que queda: guardar el filtro como colección inteligente) | `GEN 7` |
| A.4 (módulo Imagen completo) | `IMG 1` |
| A.5 (vista de lista; vista de mapa) | `MUS 5`; `GEN 8` y las fases de TRACKS |
| A.6 (módulos Vídeo, Audio y Tracks) | `MUS 1` a `MUS 10`, `VID 1` a `VID 4`, fases de TRACKS |
| A.7 («Abrir en su módulo») | Mejoras menores (GENERAL) |
| B (mejoras anotadas) | Las «Mejoras menores» de cada categoría; el deshacer, `GEN 1`; el reconocimiento facial, `IMG 3`; la edición para Audio y Vídeo, `MUS 6`, `MUS 7` y `VID 4` |
| C.1 (verificar con ExifTool real) | `IMG 2` |
| C.2 (miniaturas de vídeo y audio) | `VID 2`, `VID 3` (portadas), `MUS 3` y `MUS 9` |
| C.3 (miniaturas, extras) | `GEN 4` |
| C.4 (datos del usuario, lo que falta) | `GEN 3`; la valoración en POPM, M5 de [MOD_MUSICA.md](MOD_MUSICA.md) |
| C.5 (más metadatos editables) | `GEN 2` |
| C.6 (extractores de audio y ebooks) | `MUS 1`; `GEN 9` |
| C.7 (hashes) | `CAT 2` |
| C.8 (archivos sueltos, ubicaciones solapadas) | `CAT 1` |
| C.9 (empaquetado) | `GEN 5` |
| C.10 (interfaz) | `GEN 6` |
| C.11 (optimizaciones) | `GEN 10` |
| C.12 (omitido de la v1) | Mejoras menores (GENERAL) |
| Fases 4 a 8 de [MOD_TRACKS.md](MOD_TRACKS.md) §10 | `TRK 4` a `TRK 8` (el mismo número) |
