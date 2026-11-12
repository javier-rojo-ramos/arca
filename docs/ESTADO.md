# Arca Media — Estado del proyecto

> Dónde está el proyecto HOY. Se actualiza al terminar cada paso: lo nuevo entra en «Pendiente de verificar» y en «Últimos cambios»; cuando el autor lo comprueba, pasa a «Verificado». El detalle de cómo se probó cada entrega está en [HISTORIAL.md](HISTORIAL.md).
> Índice: [INDEX.md](INDEX.md).

**Actualizado**: 12/11/2026.

**En resumen**: el Catálogo funciona de punta a punta con imágenes: añadir y sincronizar carpetas, metadatos con ExifTool, miniaturas, cuadrícula y vista individual, clasificación (valoración, marca, color y selección rápida) guardada también en los archivos, palabras clave, colecciones (también inteligentes, con grupos de reglas), barra de filtros («Texto», «Atributos», «Metadatos» y ajustes personalizados) e inspector, que edita las palabras clave en todos los módulos y, en las fotos y vídeos de Imagen, el título, el pie, el creador, el copyright, la ubicación y el GPS (también guardados en los archivos). El módulo Imagen navega por carpetas, fechas y palabras clave. Vídeo, audio, GPX y ebooks se catalogan y se clasifican en bibliotecas, pero los módulos Vídeo y Audio aún son provisionales. Lo siguiente, en [PENDIENTE.md](PENDIENTE.md).

## Pendiente de verificar en Windows (lo último entregado)

| Entrega | Qué comprobar |
|---|---|
| **Vista individual a 1:1, paso 1: leer el original** (12/11; nuevo `full_image` 1.0.0; `generator` 1.2.0) | Nada visible todavía: la aplicación, igual que antes (las miniaturas se generan como siempre). Pasan las autopruebas de `full_image`, `generator` y `job` |

## Comprobaciones sueltas

Detalles concretos de entregas ya verificadas que todavía no se han mirado. Se hacen cuando haya ocasión; no bloquean nada.

- **Vídeos**: uno de Android, uno de cámara (Sony, Canon, GoPro, DJI, `.MTS`) y una película con `python -m core.metadata.inspect_cli archivo --json salida.json`: fecha de captura (sobre todo los de cámara: ¿UTC o local?), tamaño girado, cámara y duración; pasar las salidas para ajustar las etiquetas. Que «Sin clasificar» se vacía casi entero. Que los vídeos del iPhone tienen objetivo, focal y apertura (inspector, vista «EXIF»).
- **Recorte de Lightroom** (fila «Recorte» del inspector): una foto vertical (orientación 6 u 8) recortada, un RAW con el recorte en el sidecar `.xmp` y un HEIC.
- **Inspector**: en «Metadatos», la fila «Flash» y la exposición redondeada como Lightroom («1/50 s», con el tiempo exacto en el texto emergente) en más fotos del móvil; Ctrl+A en un catálogo grande; en «Selección», un archivo ausente, un disco desconectado y el panel estrecho.
- **Marcador y duración**: canciones y GPX con su marcador; una foto con la miniatura fallida (paisaje); selección rápida, rechazada y no disponible sobre un marcador.
- **Palabras clave**: mover, borrar, purgar y marcar revisada, con los avisos de nombre repetido o no válido; «Familia > Ana» en «Últimas palabras clave» con dos «Ana»; la escritura comparada con Lightroom (`HierarchicalSubject` y `dc:subject`).
- **Eliminar**: un archivo abierto en otro programa (aviso; se queda), archivos de una unidad de red (aviso) y un RAW con su `.xmp` a la Papelera.
- **Colecciones inteligentes**: abrir el editor con doble clic; reglas con cada tipo de valor.
- **Detección con el catálogo abierto**: la comprobación (cada 5 s y al volver a la ventana) de archivos que desaparecen o vuelven.
- **Datos del usuario con Lightroom**: qué hace Lightroom con un sidecar de RAW creado por la aplicación al «Leer metadatos del archivo»; que `-overwrite_original` conserve en Windows la fecha de creación.
- **Metadatos de imagen**: `city` y `region` (se añadieron después de verificar `sublocation` y `country`).

## Nunca probado

- ExifTool en lote con RAW distintos de DNG (NEF, CR2, CR3, ARW, ORF, RW2, PEF, RAF) y con WebP.
- macOS y Linux.
- Empaquetado con PyInstaller (incluir `tools/exiftool`, datos de `pillow-heif` y `puremagic`).
- Cuadrícula con catálogos muy grandes (decenas de miles de tarjetas visibles a la vez; con una carpeta de unas 10 000 fotos va bien).
- Detección de unidades de red en Windows (`GetDriveTypeW`) y la papelera real (`QFile.moveToTrash`).

## Verificado por el autor (Windows)

- **Catálogo**: crear y abrir; añadir y sincronizar carpetas (más de 20 000 imágenes en segundos); ubicaciones sin solapes; archivos ausentes y ubicaciones desconectadas con su velo e indicador; quitar ausentes; «Quitar del catálogo…» de una carpeta o una ubicación (también desconectada; los archivos del disco no se tocan); esquema consolidado en la v1 (`APPLICATION_ID`); nombre Arca Media, con `settings.json` en `%LOCALAPPDATA%\arca` y `.arca.json`; menú Archivo > Salir (Ctrl+Q).
- **Metadatos de imagen** con ExifTool 13.59: JPEG, dos HEIC (uno vertical con `irot`) y un DNG coinciden con los paneles EXIF y Ubicación de Lightroom (DNG con `DefaultCropSize`: 3200 × 2128). Extractor de Pillow (`sublocation`, `country`). **Vídeo**: iPhone, horizontal y vertical.
- **Miniaturas**: motor y trabajo en segundo plano (encadenado tras los metadatos, progreso, cancelar, regenerar); escalera completa de 4 tamaños; 22 000 fotos (60 GB) en unos 20 min con 4 hilos, caché de 23 GB. Marcador dibujado y duración en los vídeos.
- **Cuadrícula**: lectura desde la BD y la caché, etiquetas de color como fondo, marca, valoración, atajos, menú contextual, banda inferior; selección rápida (círculo, `B`, fila, vaciar); orden por módulo («Orden: [campo] [↑]», recordado al cambiar de módulo y al reiniciar).
- **Aspecto**: tema oscuro con los grises de LightTable, zonas pegadas con una raya de 1 px (también bajo la barra de menús, 11/11), toolbar con cajas, acento ámbar, cuadrícula y tarjetas en grises neutros, botones de opción y casillas visibles (`ThemeStyle`), iconos teñidos de la barra de estado. Todos los colores, del tema (09/11: el número de la insignia al arrastrar, oscuro; en la barra inferior, el fondo con el ratón y el anillo del color activo, como en «Atributos»); iconos de los menús separados del borde y oscuros sobre la opción resaltada (09/11).
- **Datos del usuario**: lectura del XMP (HEIC de Lightroom Classic 15.6) y escritura fuera del catálogo (XMP incrustado, sidecar `.xmp` de un NEF, `.arca.json`); Lightroom reconoce los cinco colores. Ventana de opciones.
- **Barra lateral**: secciones Catálogo, Carpetas y Colecciones con recuentos; árbol de carpetas (subcarpetas, sincronizar, mostrar en el Explorador, quitar ausentes); colecciones del sistema, del usuario y conjuntos (crear, renombrar, borrar, arrastrar, añadir y quitar); estado guardado por catálogo y restaurado al abrir; toolbar de modos; «Añadir carpeta» recuerda la carpeta.
- **Barra inferior**: clasificar la selección (marca, estrellas, colores, selección rápida) con el estado de la selección siempre al día; botones de vista, orden y deslizador; del alto de la franja de «Atributos», con los botones de vista de 22 px y el deslizador centrado (11/11); de 34 px bajo la raya, como las franjas de la barra de filtros (12/11).
- **Módulos**: infraestructura con el Catálogo como primer módulo; el módulo activo se recuerda al reiniciar. **Imagen**: «Biblioteca - Imagen» (Todas las imágenes y su «Selección rápida»), «Carpetas» con imágenes y «Lista de palabras clave» con su filtro y recuentos con las hijas (alineada con «Carpetas» y el filtro a 8 px, 11/11); la barra izquierda solo navega; los árboles se abren como se dejaron.
- **Bibliotecas**: «¿Qué contiene esta carpeta?» (2a), vídeos por el nombre y «Sin clasificar» (2b-1), clasificación por metadatos (2c), submenú «Biblioteca» con la actual marcada; la tarjeta cambia a póster 2:3 al pasar un vídeo a Vídeos y vuelve a 16:9 al pasarlo a Imágenes.
- **Inspector**: sección «Selección» (siempre del mismo alto; sin selección, resumen de lo que se ve); sección «Metadatos» con sus tres vistas (comparada con Lightroom: coincide salvo la exposición redondeada y los ajustes corregidos después); recorte de Lightroom en el DNG y en un JPG enderezado; secciones plegadas recordadas; el desplegable de vistas de «Metadatos», alineado con el resto del inspector (10/11, comparado con capturas); el contenido, a 8 px de los dos bordes, y la caja de «Palabras clave» y el filtro de «Lista de palabras clave», a 8 px de la barra de su título (11/11); la «Lista de palabras clave», con los márgenes de la de la barra izquierda (árbol a todo el ancho, filtro a 8 px; 12/11).
- **Palabras clave**: lectura de los archivos (K1); campo en las colecciones inteligentes (K2); árbol en el módulo Imagen (K3); edición en el inspector (K4): caja con sugerencias, árbol con casillas, «Últimas palabras clave», gestionar el árbol (renombrar comprobado ida y vuelta con Lightroom), soltar tarjetas y flecha «ver sus fotos».
- **Eliminar archivos**: «Eliminar del catálogo» y «Eliminar del disco», con su ventana.
- **Tracks GPX**: distancia como Wikiloc; desnivel con umbral de 8 m (Bujaruelo, Ordesa, Pineta).
- **A.1: centro con varias vistas y vista individual** (08/11): botones de vista con iconos, vista recordada por módulo y al reiniciar, deslizador solo en la cuadrícula; vista individual nítida con precarga (la imagen que cabe, a su tamaño y sin ampliar, también al maximizar: 11/11), marcador y avisos de no disponible, «No hay archivos»; doble clic / Intro, Esc / G, flechas, Inicio y Fin; atajos y barra inferior sobre la foto vista.
- **A.2: el inspector edita en todos los módulos** (08/11): secciones según la biblioteca de lo resumido; editor y árbol de palabras clave con cualquier selección, también en el Catálogo; flecha «ver sus fotos» en el Catálogo y en Imagen; escritura de palabras clave en el `.arca.json` de un vídeo, una canción y un GPX.
- **A.3: barra de filtros** (08-09/11): la barra (pestañas, «Ninguno», candado, Ctrl+L, cada módulo lo suyo, oculta en la vista individual, recordada al reiniciar); «Texto» (todos los campos o solo el nombre, cuatro operadores, Ctrl+F); «Atributos» (marcas, estrellas con su operador y «sin valoración», colores, selección rápida y los tipos de cada módulo); «Metadatos» (columnas en cascada, añadir y quitar, alto, fechas en árbol; con unas 10 000 fotos, «muy ágil»); ajustes personalizados (el desplegable y la ventana «Gestionar ajustes personalizados»); la fila de las pestañas, «Texto» y «Atributos», de 34 px con lo de dentro centrado (12/11).
- **Colecciones inteligentes con grupos** (09/11): las colecciones de antes, igual (se guardan ya en JSON versión 2); el editor, con los colores del tema; «+ Añadir grupo», cada grupo con su «todas / alguna de», su «−» y su «+ Añadir regla»; el recuento en vivo con grupos; editar y volver a abrir; la lista baja hasta lo añadido.
- **Edición de metadatos (C.5), pasos 1 a 5** (10/11): un catálogo existente se abre y pasa solo al esquema v2; la relectura respeta lo editado (y un título borrado en otro programa vuelve a ser el nombre del archivo); el texto de las cajas, alineado con el de los demás valores; al asignar una palabra clave a un JPEG con palabras en IPTC, Lightroom («Leer metadatos del archivo») lo ve todo bien (resumen IPTC al día); Título, Pie, Creador y Copyright en las vistas «Por defecto» y «Ubicación», con el título en blanco si es el nombre del archivo; su edición en «Metadatos» (cajas, Intro que suelta el foco, Esc, Tab, Mayús+Intro, «Varios» y el aviso «Edición múltiple»; sin ayuda al pasar el ratón), escrita en los archivos («todo parece funcionar»); la ubicación, también editable; la opción «Preguntar antes de cambiar varios archivos con valores distintos» en Opciones > Metadatos. Antes, el paso 0: el resumen desajustado hace que Lightroom muestre el IPTC (ver [METADATOS.md](METADATOS.md)).
- **Edición del GPS, pasos 1 a 5** (11/11): el catálogo pasa solo al esquema v3 (la dirección, en `media_items`); GPS, altitud y dirección leídos primero del XMP, como Lightroom (`IMAGE_FIELDS_VERSION` 9: se releyeron las fotos); los cuatro campos, editables y protegidos al releer; cuatro fotos escritas por el escritor de la aplicación (solo EXIF, EXIF y XMP distintos, sin GPS y solo XMP, con hemisferio sur, oeste y altitudes bajo el nivel del mar) se ven en Lightroom Classic 16 exactamente como las lee la aplicación; las cajas de GPS, Altitud y Dirección en «Metadatos» (lo escrito se interpreta; lo que no vale vuelve con su aviso), con lo editado escrito en los archivos. Antes (paso 0), cómo lee y escribe Lightroom el GPS ([METADATOS.md](METADATOS.md)).
- **Limpieza de ruff** (11/11; solo importaciones y comentarios en 27 módulos): la aplicación, igual que antes.
- **Sección «Fechas» del módulo Imagen** (12/11): debajo de «Carpetas», los años (el más reciente arriba) con sus meses («01 Enero») y sus días («10 Miércoles»), y «Sin fecha»; cada fila muestra lo que cuenta, con los mismos números que la columna «Fecha de captura»; lo desplegado y el día elegido, recordados. Antes, la barra de Imagen dividida en un archivo por sección (`ui_helpers/sidebars/sections/`), con todo igual que antes.

## Últimos cambios

Los más recientes primero; se guardan los 10 últimos (los anteriores, en [HISTORIAL.md](HISTORIAL.md)).

- 12/11/2026: vista individual a 1:1, paso 1: leer el original a tamaño completo con el color de la caché (`core/thumbnails/full_image.py`); aún sin nada visible.
- 12/11/2026: las franjas de la barra de filtros (pestañas, «Texto», «Atributos») y la barra inferior, de 34 px (antes, 30), con lo de dentro centrado.
- 12/11/2026: «Lista de palabras clave» del inspector, con los márgenes de la de la barra izquierda (árbol a todo el ancho; filtro a 8 px).
- 12/11/2026: sección «Fechas» del módulo Imagen, paso 3 (último): la sección, debajo de «Carpetas» (años, «01 Enero», «10 Miércoles» y «Sin fecha», con sus recuentos).
- 12/11/2026: sección «Fechas» del módulo Imagen, paso 2: la barra de Imagen, dividida en un archivo por sección (`ui_helpers/sidebars/sections/`); nada cambia a la vista.
- 12/11/2026: sección «Fechas» del módulo Imagen, paso 1: los años, meses y días con sus recuentos, y el origen de la cuadrícula de cada fila (`core/catalog/timeline.py`); aún sin nada visible.
- 11/11/2026: vista individual, la imagen que cabe se ve a su tamaño (sin ampliarla); el deslizador de la barra inferior, centrado (1 px más abajo).
- 11/11/2026: la barra inferior, del alto de la franja de «Atributos» (30 px bajo la raya; botones de vista de 22 px).
- 11/11/2026: barra de Imagen, «Lista de palabras clave» alineada con «Carpetas» (filtro a 8 px; nombres en la columna de las flechas de las subcarpetas; números con los de las carpetas).
- 11/11/2026: las cajas de texto bajo el título de una sección, a 8 px de la cabecera (antes, 4); corregidas las fechas de lo hecho hoy, que decían 12/11.