# Arca Media — Estado del proyecto

> Dónde está el proyecto HOY. Se actualiza al terminar cada paso: lo nuevo entra en «Pendiente de verificar» y en «Últimos cambios»; cuando el autor lo comprueba, pasa a «Verificado». El detalle de cómo se probó cada entrega está en [HISTORIAL.md](HISTORIAL.md).
> Índice: [INDEX.md](INDEX.md).

**Actualizado**: 10/11/2026.

**En resumen**: el Catálogo funciona de punta a punta con imágenes: añadir y sincronizar carpetas, metadatos con ExifTool, miniaturas, cuadrícula y vista individual, clasificación (valoración, marca, color y selección rápida) guardada también en los archivos, palabras clave, colecciones (también inteligentes, con grupos de reglas), barra de filtros («Texto», «Atributos», «Metadatos» y ajustes personalizados) e inspector, que edita las palabras clave en todos los módulos. El módulo Imagen navega por carpetas y palabras clave. Vídeo, audio, GPX y ebooks se catalogan y se clasifican en bibliotecas, pero los módulos Vídeo y Audio aún son provisionales. Lo siguiente, en [PENDIENTE.md](PENDIENTE.md).

## Pendiente de verificar en Windows (lo último entregado)

| Entrega | Qué comprobar |
|---|---|
| **Iconos de los menús** (09/11; `theme_qss` 1.3.0, `ui_icons` 1.3.0, `sidebar_icons` 1.1.0, `catalog_sidebar` 1.12.1) | Clic derecho en una colección inteligente: el icono de «Editar colección inteligente…» ya no va pegado al borde izquierdo, y con la opción resaltada (ámbar) es oscuro, como el texto. Igual en el «+» de Colecciones (crear conjunto, colección o colección inteligente) y en los cuadraditos del submenú de etiquetas de la cuadrícula (solo la posición) |
| **Colores, todos del tema** (09/11; `theme_colors` 1.6.0, `ui_theme` 1.14.0, `card_marks` 1.1.0, `card_glyphs` 1.2.0, `ui_color_labels` 1.1.0, `thumbnails_delegate` 2.14.0, `single_media_view` 1.0.1, `media_grid_view` 1.2.0, `organize_bar` 1.1.0, `selection_section` 1.3.2, `ui_icons` 1.2.1) | Todo se ve igual que antes (comprobado sin ventana, píxel a píxel: tarjetas en nueve estados, marcas, etiquetas, círculos de «Estado» del inspector, fila «Atributos» y vista individual), salvo dos cosas: **arrastrar tarjetas**, el número de la insignia ámbar es ahora oscuro (antes blanco); **barra inferior**, al pasar el ratón por una zona el fondo es algo más claro, y el anillo del color activo, gris claro en vez de blanco (los mismos que la fila «Atributos» de la barra de filtros) |

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
- **Aspecto**: tema oscuro con los grises de LightTable, zonas pegadas con una raya de 1 px, toolbar con cajas, acento ámbar, cuadrícula y tarjetas en grises neutros, botones de opción y casillas visibles (`ThemeStyle`), iconos teñidos de la barra de estado.
- **Datos del usuario**: lectura del XMP (HEIC de Lightroom Classic 15.6) y escritura fuera del catálogo (XMP incrustado, sidecar `.xmp` de un NEF, `.arca.json`); Lightroom reconoce los cinco colores. Ventana de opciones.
- **Barra lateral**: secciones Catálogo, Carpetas y Colecciones con recuentos; árbol de carpetas (subcarpetas, sincronizar, mostrar en el Explorador, quitar ausentes); colecciones del sistema, del usuario y conjuntos (crear, renombrar, borrar, arrastrar, añadir y quitar); estado guardado por catálogo y restaurado al abrir; toolbar de modos; «Añadir carpeta» recuerda la carpeta.
- **Barra inferior**: clasificar la selección (marca, estrellas, colores, selección rápida) con el estado de la selección siempre al día; botones de vista, orden y deslizador.
- **Módulos**: infraestructura con el Catálogo como primer módulo; el módulo activo se recuerda al reiniciar. **Imagen**: «Biblioteca - Imagen» (Todas las imágenes y su «Selección rápida»), «Carpetas» con imágenes y «Lista de palabras clave» con su filtro y recuentos con las hijas; la barra izquierda solo navega; los árboles se abren como se dejaron.
- **Bibliotecas**: «¿Qué contiene esta carpeta?» (2a), vídeos por el nombre y «Sin clasificar» (2b-1), clasificación por metadatos (2c), submenú «Biblioteca» con la actual marcada; la tarjeta cambia a póster 2:3 al pasar un vídeo a Vídeos y vuelve a 16:9 al pasarlo a Imágenes.
- **Inspector**: sección «Selección» (siempre del mismo alto; sin selección, resumen de lo que se ve); sección «Metadatos» con sus tres vistas (comparada con Lightroom: coincide salvo la exposición redondeada y los ajustes corregidos después); recorte de Lightroom en el DNG y en un JPG enderezado; secciones plegadas recordadas.
- **Palabras clave**: lectura de los archivos (K1); campo en las colecciones inteligentes (K2); árbol en el módulo Imagen (K3); edición en el inspector (K4): caja con sugerencias, árbol con casillas, «Últimas palabras clave», gestionar el árbol (renombrar comprobado ida y vuelta con Lightroom), soltar tarjetas y flecha «ver sus fotos».
- **Eliminar archivos**: «Eliminar del catálogo» y «Eliminar del disco», con su ventana.
- **Tracks GPX**: distancia como Wikiloc; desnivel con umbral de 8 m (Bujaruelo, Ordesa, Pineta).
- **A.1: centro con varias vistas y vista individual** (08/11): botones de vista con iconos, vista recordada por módulo y al reiniciar, deslizador solo en la cuadrícula; vista individual nítida con precarga, marcador y avisos de no disponible, «No hay archivos»; doble clic / Intro, Esc / G, flechas, Inicio y Fin; atajos y barra inferior sobre la foto vista.
- **A.2: el inspector edita en todos los módulos** (08/11): secciones según la biblioteca de lo resumido; editor y árbol de palabras clave con cualquier selección, también en el Catálogo; flecha «ver sus fotos» en el Catálogo y en Imagen; escritura de palabras clave en el `.arca.json` de un vídeo, una canción y un GPX.
- **A.3: barra de filtros** (08-09/11): la barra (pestañas, «Ninguno», candado, Ctrl+L, cada módulo lo suyo, oculta en la vista individual, recordada al reiniciar); «Texto» (todos los campos o solo el nombre, cuatro operadores, Ctrl+F); «Atributos» (marcas, estrellas con su operador y «sin valoración», colores, selección rápida y los tipos de cada módulo); «Metadatos» (columnas en cascada, añadir y quitar, alto, fechas en árbol; con unas 10 000 fotos, «muy ágil»); ajustes personalizados (el desplegable y la ventana «Gestionar ajustes personalizados»).
- **Colecciones inteligentes con grupos** (09/11): las colecciones de antes, igual (se guardan ya en JSON versión 2); el editor, con los colores del tema; «+ Añadir grupo», cada grupo con su «todas / alguna de», su «−» y su «+ Añadir regla»; el recuento en vivo con grupos; editar y volver a abrir; la lista baja hasta lo añadido.

## Últimos cambios

Los más recientes primero; se guardan los 10 últimos (los anteriores, en [HISTORIAL.md](HISTORIAL.md)).

- 10/11/2026: edición de los metadatos descriptivos (C.5), paso 0: prueba de escritura con ExifTool y Lightroom, sin tocar el código; decisiones, plan y resultados anotados.
- 09/11/2026: los iconos de los menús ya no van pegados al borde izquierdo y, en la opción resaltada, son oscuros como el texto.
- 09/11/2026: todos los colores de la interfaz salen del tema (`theme_colors.py`): las marcas de clasificación, las etiquetas, lo que va encima de la imagen y el estado de los archivos; la barra inferior, con el mismo fondo y anillo que «Atributos»; el número del arrastre, oscuro sobre el ámbar.
- 09/11/2026: revisión de la documentación: quitados los pasos hechos y las decisiones sustituidas; lo entregado hasta el 07/11 pasa a «Verificado» y sus detalles sin mirar, a «Comprobaciones sueltas».
- 09/11/2026: colecciones inteligentes con grupos, subpaso 3: «+ Añadir grupo» en el editor; cada grupo con su «todas / alguna de», sus reglas y su «+ Añadir regla»; la lista baja hasta lo añadido.
- 09/11/2026: colecciones inteligentes con grupos, subpaso 2: las filas de reglas del editor pasan a su propio archivo (sin cambios de comportamiento); los colores del editor salen del tema.
- 09/11/2026: colecciones inteligentes con grupos, subpaso 1: el motor de reglas admite grupos de un nivel (SQL, validación, JSON versión 2 y texto emergente); aún sin cambios en el editor.
- 09/11/2026: filtros personalizados, subpaso 3: ventana «Gestionar ajustes personalizados» (ordenar, cambiar el nombre, eliminar, restaurar los de fábrica).
- 09/11/2026: filtros personalizados, subpaso 2: desplegable de ajustes personalizados antes del candado (guardar con nombre, restaurar, elegir uno de la lista; cinco de fábrica), sin la ventana de gestión todavía.
- 09/11/2026: filtros personalizados, subpaso 1: motor de los ajustes personalizados de la barra de filtros (guardar, elegir, restaurar, cuál coincide, los de fábrica), aún sin desplegable.
