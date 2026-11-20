# Arca Media — Pendiente (hoja de ruta)

> Solo lo que falta. Lo entregado sale de aquí: su detalle está en [HISTORIAL.md](HISTORIAL.md) y lo que falte por comprobar, en [ESTADO.md](ESTADO.md).
> Índice: [INDEX.md](INDEX.md).

**Plan de interfaz** (acordado el 29/10/2026 y revisado el 08/11/2026; ver [FLUJOS.md §11](FLUJOS.md) y [DECISIONES.md](DECISIONES.md)): el mismo esqueleto en todos los módulos (izquierda navegar, centro ver, derecha el inspector), la edición en el inspector y ventanas solo para lo pesado o por lotes, una tarjeta configurable por «perfiles» y un único motor de filtros (`RuleSet`) con estado por módulo.

## Cómo se nombra (desde el 16/11/2026)

- Lo pendiente se agrupa en **categorías**: GENERAL (lo que comparten los módulos o no es de ninguno) y una por módulo: CATÁLOGO, IMAGEN, MÚSICA (el módulo Audio), VÍDEO, EBOOKS (Libros) y TRACKS.
- Cada funcionalidad principal es una **fase**, con el código de su categoría y un número: `GEN 1`, `CAT 1`, `IMG 1`, `MUS 1`, `VID 1`, `EBK 1`, `TRK 6`. Sus **pasos** son `X.1`, `X.2`...: `TRK 6.3` es el paso 3 de la fase 6 de Tracks. Un paso que se parte lleva letra (`6.3a`, `6.3b`).
- Los números no se reutilizan: una fase terminada sale de aquí y su número queda libre para siempre. El número no fija el orden: el orden se decide al planificar (ver «En curso»).
- Las fases de TRACKS conservan el número de [MOD_TRACKS.md](MOD_TRACKS.md) §10 (allí, las fases 0 a 3 fueron el mapa; la 4 y la 5, lo básico de Tracks y el perfil de elevación, hechas el 14 y el 15/11/2026).
- Lo pequeño no es una fase: va en la lista **«Mejoras menores»** de su categoría, sin número.
- Cada módulo tiene su documento `MOD_` ([MOD_CATALOGO.md](MOD_CATALOGO.md), [MOD_IMAGEN.md](MOD_IMAGEN.md), [MOD_TRACKS.md](MOD_TRACKS.md), [MOD_MUSICA.md](MOD_MUSICA.md), [MOD_VIDEO.md](MOD_VIDEO.md), [MOD_EBOOKS.md](MOD_EBOOKS.md)), con su arquitectura y el detalle de sus fases; aquí, solo la lista.
- [HISTORIAL.md](HISTORIAL.md) y las cabeceras del código citan los bloques de antes (A.1 a A.7, B, C.1 a C.12): la tabla del final dice a qué corresponde cada uno.

## En curso

- **CATÁLOGO** (19/11/2026): hechas `CAT 3` (carpetas vacías), `CAT 4.1` a `4.4` (renombrar y mover en el mismo disco, nueva carpeta) y `CAT 5` (el árbol replica las carpetas del disco, también las vacías; no estaba en el plan: pedida por el autor y hecha en un paso, detalle en [HISTORIAL.md](HISTORIAL.md)); todas, verificadas por el autor. Hecho y verificado el `4.4c` (mover una carpeta arrastrándola, 20/11/2026). Lo que queda de `CAT 4`: `4.5` (mover entre discos) y `4.6` (renombrado múltiple). En marcha (20/11/2026), `CAT 6` (carpetas que faltan y «Localizar…»): hechos y verificados del `6.1` al `6.3`; el `6.4` («Localizar…» de una carpeta que falta), en espera.
- **TRACKS**: terminadas las fases 4 y 5; lo siguiente del plan acordado es `TRK 6` (edición).
- **MÚSICA y VÍDEO**: los dos módulos muestran ya su biblioteca, con la barra de Tracks (biblioteca, carpetas y fechas; 15/11/2026). Música está definida ([MOD_MUSICA.md](MOD_MUSICA.md), 16/11/2026): lo siguiente, `MUS 1`. Vídeo, también ([MOD_VIDEO.md](MOD_VIDEO.md), 16/11/2026): lo siguiente, `VID 1`.
- **EBOOKS**: definido ([MOD_EBOOKS.md](MOD_EBOOKS.md), 16/11/2026); el módulo aún no existe. Lo primero, `EBK 1`; antes de `EBK 2`, una carpeta de prueba con libros reales.
- **Preparar el crecimiento** (16/11/2026): hechos `GEN 11` (el guion de autopruebas), `GEN 13` (una sola barra de biblioteca), `GEN 12` (una ficha por módulo), `GEN 14` (los escritores) y `GEN 15.1` a `15.3` (los trabajos, añadir carpetas y eliminar, fuera del controlador; 18/11/2026). De `GEN 15` queda `15.4`, en espera (en todo caso, antes de `VID 7`). `MUS 1` a `MUS 3` y `VID 1` a `VID 4` no dependen de nada de esto.

---

## GENERAL

### Fase GEN 1 — Deshacer en toda la aplicación

Acordado con el autor el 13/11/2026: un solo historial de cambios en el que cada cambio sabe deshacerse, con Ctrl+Z en toda la ventana. **Empezado**: `controllers/undo_history.py` (`UndoHistory`), que hoy llena el mapa (ubicar, mover y quitar la ubicación). Nunca lo que no tiene vuelta atrás («Eliminar del disco», «Purgar»). Deshacer algo ya escrito en los archivos es otro cambio más, que se vuelve a escribir.

- **GEN 1.1** Rehacer (Ctrl+Y).
- **GEN 1.2** La valoración, la marca y el color.
- **GEN 1.3** Los metadatos del inspector.
- **GEN 1.4** Las palabras clave.

### Fase GEN 2 — Más metadatos editables

El mecanismo está hecho (título, pie, creador, copyright y ubicación desde el 10/11/2026; GPS, altitud y dirección desde el 11/11/2026; la actividad de un track, el 14/11/2026; receta en [COMO_AMPLIAR.md](COMO_AMPLIAR.md)). La escritura con un NEF real y su sidecar, probada el 14/11/2026; sin probar con un DNG y con un CR3. La edición de las etiquetas de audio y de las fichas de vídeo, en `MUS 6`, `MUS 7` y `VID 6`.

- **GEN 2.1** La fecha (ventana propia, por biblioteca).
- **GEN 2.2** El estado del copyright, el género y la escena.

### Fase GEN 3 — Datos del usuario, lo que falta

- **GEN 3.1** `xmp:Rating = -1` de Bridge como rechazo.
- **GEN 3.2** Los errores de la fase `userdata`, en la lista de `scan_errors` de la interfaz (`GEN 6.1`; hoy solo se avisa en la barra de estado y en el registro), y no reintentar en cada pasada los que fallan siempre (solo lectura).
- **GEN 3.3** Notas y colecciones en el archivo de carpeta (caben como claves nuevas: se conservan las desconocidas).

### Fase GEN 4 — Miniaturas: extras

Las de vídeo y las carátulas de audio, en `VID 4` y `MUS 3`.

- **GEN 4.2** `rawpy`: RAW sin vista previa o con una pequeña; también para el 1:1 de la vista individual, que hoy en un RAW es su mayor vista previa (en un DNG de Lightroom, a veces de solo 1024 px).
- **GEN 4.3** Limpiar los huérfanos de la caché y comprobar que los archivos existen.
- **GEN 4.4** Insignia «editada en Lightroom» a partir de `XMP-crs:HasCrop` / `HasSettings` (y, opcional, aplicar solo el recorte cuando `CropAngle` sea 0).
- **GEN 4.5** Solo si el espacio llegara a importar (hoy ≈ 38 % de los originales): el tamaño de 2560 solo a demanda y, después, WebP en los dos tamaños grandes; las dos cosas obligan a subir `THUMBNAIL_VERSION`. Medir antes cuánto pesa cada `cache/photo/<tamaño>`.

### Fase GEN 5 — Empaquetado

Incluir `tools/exiftool` (`--add-data`), `--collect-data puremagic`, `defusedxml` y los datos de `pillow-heif`; QtWebEngine (el mapa: unos 220 MB más, el proceso `QtWebEngineProcess.exe` y la carpeta `resources` de Qt; [MOD_TRACKS.md](MOD_TRACKS.md) §9); comprobar que la ruta a `tools/exiftool` (basada en `__file__`) vale dentro del paquete; probar en macOS y Linux; el icono del ejecutable, `--icon resources/icons/windows/arca-media.ico` en Windows y `resources/icons/macos/arca-media.icns` en macOS (en Linux, un `.desktop`; ver `resources/icons/README.md`), y la carpeta `resources/icons/` dentro del paquete, porque el de la ventana se lee del disco (`ui_helpers/helpers/app_icon.py`). Pasos, por definir.

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

### Fase GEN 10 — Optimizaciones (cuando se midan)

Pedir a ExifTool solo las etiquetas necesarias, `-stay_open` o varios procesos; un grupo de hilos propio para los trabajos (hoy comparten los 4 del gestor de BD: metadatos o escritura, miniaturas y añadir carpeta pueden ocupar 3 a la vez); más índices (p. ej. por valoración).

### Preparar el crecimiento (`GEN 15` a `GEN 19`)

Acordado con el autor el 16/11/2026, tras analizar el código ([DECISIONES.md](DECISIONES.md)): lo que conviene refactorizar o hacer común **antes** de los módulos nuevos, para que no lo pague cada uno por separado. Son refactorizaciones: no cambian lo que hace la aplicación, y cada una va en su paso, sin mezclarla con una funcionalidad. El orden, en «En curso». Hecho: `GEN 11`, el guion que lanza todas las autopruebas (`scripts/run_selftests.py`, 16/11/2026): se ejecuta antes y después de cada una de estas; y `GEN 13`, una sola barra de biblioteca (16/11/2026): Imagen usa `LibrarySidebar` y `LibraryModule`, y una sección nueva de un módulo es un `ExtraSection` ([COMO_AMPLIAR.md](COMO_AMPLIAR.md)); y `GEN 12`, una ficha por módulo (16/11/2026): `config/app_modules.py` (`MODULES`), de donde leen los módulos, el registro de secciones y el inspector; y `GEN 14`, los escritores con una interfaz común (16/11/2026): `core/userdata/writers.py`; un escritor nuevo se registra sin tocar `sync.py`, y lo que no sabe guardar va al `.arca.json`. Queda para `MUS 6` la lectura de un formato repartido.

### Fase GEN 15 — Los trabajos, fuera del controlador principal

`main_window_controller.py` tiene 2 036 líneas y 81 métodos (18/11/2026); la cadena metadatos → miniaturas → escritura, con sus esperas, vive ahí. Antes de `VID 7` (descargas). Plan aprobado por el autor el 18/11/2026 (refactorización: nada cambia en la aplicación; el código se mueve tal cual y lo movido pasa a nombres en inglés):

- ~~**GEN 15.1** El encadenado de los trabajos, a `controllers/job_coordinator.py` (`JobCoordinator`)~~ (hecho el 18/11/2026: el controlador, de 2 036 a 1 668 líneas; con una autoprueba de las reglas).
- ~~**GEN 15.2** Añadir y sincronizar carpetas~~ (hecho el 18/11/2026: `controllers/folder_import.py`; «Mostrar en el Explorador», a `folder_actions.py`).
- ~~**GEN 15.3** Eliminar~~ (hecho el 18/11/2026: `controllers/remove_actions.py`; el controlador, en 1 270 líneas).
- **GEN 15.4** (opcional, **en espera**: medido el 18/11/2026, no hace falta por ahora) El grupo de hilos propio para los trabajos (de `GEN 10`): sí cambia cuántas cosas corren a la vez. **Medida** (el autor, generando 6 392 miniaturas y navegando, con escrituras mientras tanto; «muy fluido»): 502 tareas, ninguna esperó 100 ms o más en la cola (la que más, `fetch_metadata_values`, 95 ms). No se midió el peor caso (tres trabajos largos a la vez: recorrido, lectura y miniaturas): si alguna vez se nota, el registro lo dirá. Desde el 18/11/2026 se mide la espera en la cola de la base de datos (`db_manager` 1.1.0; cómo leerla, en [PRUEBAS.md](PRUEBAS.md), «Diagnóstico de la cola de la base de datos»): hacerlo si, durante una importación grande, las consultas de la interfaz esperan a menudo 300 ms o más; si no, en todo caso antes de `VID 7` (las descargas ocuparían más hilos).

### Fase GEN 16 — Perfil de tarjeta

La «tarjeta configurable por perfiles» del plan de interfaz: la proporción y las líneas de información de la tarjeta, por biblioteca (hoy, una tabla de proporciones y un caso especial para los carteles en el delegado). Lo necesitan Música (cuadrada), Vídeo (cartel) y Ebooks; lo propio de Imagen, en `IMG 1`.

### Fase GEN 17 — Tarjeta agrupada

Una tarjeta que representa a varios archivos (uno de ellos y el recuento); entrar muestra los archivos; las acciones, a todos. Diseñada una vez para Vídeo (obras: `VID 5.3`; [MOD_VIDEO.md](MOD_VIDEO.md) §10) y Ebooks (un libro en varios formatos: `EBK 9`).

### Fase GEN 18 — Vista de lista

Una vista más del centro, estilo Mp3tag, para todos los módulos.

- **GEN 18.1** La lista, con la selección compartida con la cuadrícula y los atajos de clasificación.
- **GEN 18.2** Columnas a elegir, moverlas, su ancho y el orden por columna; recordado por módulo.

Las columnas de cada módulo, en su fase (`MUS 5`, `EBK 5.3`).

### Fase GEN 19 — Base común de los servicios web

Vídeo, Ebooks y Música descargarán datos, cada uno de su proveedor, y los tres necesitan lo mismo: identificarse, limitar las peticiones, guardar en caché, la clave en Opciones y un trabajo cancelable. Antes del primero (`VID 7`).

### Mejoras menores (GENERAL)

- **Cuadrícula**: recordar el desplazamiento exacto de cada módulo (desde el 12/11/2026 cada módulo recuerda su archivo actual, que queda a la vista al volver, pero no la posición; al recargar con el mismo origen, la posición se conserva); refresco por filas al terminar los metadatos (hoy recarga entera); recargar una colección inteligente que se está viendo cuando un elemento deja de cumplir las reglas; un módulo sin cuadrícula oculta el deslizador (y el orden, si no ofrece campos).
- **Vista individual**: mantener el 1:1 y la zona al pasar de foto (como Lightroom, para comparar el enfoque de una ráfaga); más niveles de zoom con Ctrl + rueda (2:1, 4:1, para ver los píxeles).
- **Inspector**: en «Metadatos», una vista «Personalizada» (el usuario elige los campos; en `settings.json`) y vistas IPTC y DNG; miniatura grande arriba cuando la selección es de una sola biblioteca.
- **Palabras clave**: fusionar dos palabras (hoy, renombrar una con el nombre de otra hermana avisa); arrastrar una palabra a otra para moverla; «Mover a…» con un árbol filtrable si la lista se hace larga; «Conjuntos de palabras clave» personalizables (como Lightroom) junto a «Últimas palabras clave»; quitar una palabra de «Últimas» sin borrarla. Opcional: importar el `.txt` de *Metadatos > Exportar palabras clave* de Lightroom (palabras sin usar, categorías entre corchetes → `include_on_export = 0`, sinónimos entre llaves); importador de solo lectura del catálogo de Lightroom (`.lrcat`) para traer palabras, valoraciones y colecciones de los vídeos.
- **Secciones de las barras** (personalizables desde el 14/11/2026; [FLUJOS.md §9](FLUJOS.md)): si se quiere, mover una sección de una barra a la otra (el registro ya lo admite: `SectionSpec.sidebars`; faltaría que la sección sirva en las dos y revisar `reset` de una sola barra); un icono propio para la página «Paneles».
- **«Abrir en su módulo»**: atajo de navegación («ver esta foto en su línea de tiempo»), con baja prioridad.
- **Mapa**: si se quiere, la distancia a la que el punto ámbar engancha la línea del track activo (`HOVER_PX`, 24 px), como opción en Opciones > Mapa.
- **Aspecto**: fuente de la aplicación (incluida en `resources/fonts`, p. ej. Inter, con tamaño fijo); esquinas redondeadas de los menús; si el autor lo pide, una opción para que la etiqueta de color sea una franja inferior en lugar de teñir la tarjeta.
- **Omitido a propósito de la v1 del esquema**: borrado suave (`deleted_at`), `dominant_color`, milisegundos y zona de las fechas secundarias, normalización de `country_code` (el XMP admite 2 o 3 letras; hoy se guarda tal cual).

---

## CATÁLOGO

Cómo funciona hoy y dónde está cada cosa: [MOD_CATALOGO.md](MOD_CATALOGO.md).

### Fase CAT 1 — Archivos sueltos y ubicaciones solapadas

- **CAT 1.1** Añadir archivos sueltos (hoy solo carpetas completas; `action_add_files` está sin conectar).
- **CAT 1.2** Fusión de ubicaciones solapadas (hoy se rechazan).

### Fase CAT 2 — Hashes

`hash_partial`, `hash_full`, `hash_verified_at`. Pasos, por definir:

- Duplicados.
- Comprobación de integridad.
- Reasociar un archivo renombrado fuera de la aplicación.

### Fase CAT 4 — Operaciones con archivos

Acordado con el autor el 19/11/2026 (cambia la regla de los originales: [DECISIONES.md](DECISIONES.md); `CAT 3`, las carpetas vacías, hecha el mismo día). Renombrar y mover desde la aplicación con el catálogo al día: el `id` no cambia, así que se conservan valoración, palabras clave, colecciones y miniaturas; con el archivo van su `.xmp` y su entrada del `.arca.json`. Con el patrón de «Eliminar» (plan, aviso, trabajo y refresco) y un **registro de operaciones** (una migración) para lo que quede a medias si la aplicación se cierra.

- **CAT 4.1** El núcleo, sin interfaz (`core/file_ops/`), con autoprueba:
  - ~~**4.1a** Validar los nombres (Windows, macOS y Linux) y renombrar sin la extensión (`naming.py`)~~ (hecho el 19/11/2026).
  - ~~**4.1b** El registro de operaciones (migración 5) y su revisión al abrir el catálogo; el plan y la ejecución de mover o renombrar archivos (archivo, `.xmp`, entrada del `.arca.json` y catálogo)~~ (hecho el 19/11/2026). El estado de la barra (rutas en `settings.json`) va con la interfaz (`CAT 4.2` y `4.3`).
- ~~**CAT 4.2** Renombrar un archivo («Cambiar nombre…», F2)~~ (hecho el 19/11/2026).
- ~~**CAT 4.3** Renombrar una carpeta~~ (hecho el 19/11/2026). La raíz de una ubicación (cambia la ubicación: `storage_locations`), en un paso aparte, sin número todavía.
- **CAT 4.4** Mover archivos en el mismo disco y crear carpetas:
  - ~~**4.4a** «Nueva carpeta…» en el menú de una carpeta, con «Incluir los archivos seleccionados» (como Lightroom)~~ (hecho el 19/11/2026; vacía, desde `CAT 5`).
  - ~~**4.4b** Arrastrar tarjetas a una carpeta del árbol del Catálogo~~ (hecho el 19/11/2026).
  - ~~**4.4c** Mover una carpeta arrastrándola a otra del árbol del Catálogo~~ (hecho y verificado el 20/11/2026, en dos pasos, el núcleo y el arrastre; acordado con el autor, reglas en [DECISIONES.md](DECISIONES.md)).
  - Mover varias carpetas a la vez (elegir varias en el árbol, con sus archivos juntos en la cuadrícula, como Lightroom) y a otra ubicación del mismo disco: más adelante, si hace falta.
  - «Mover a…» desde el menú de la tarjeta (sin ratón, o con muchas carpetas): más adelante, si hace falta.
- **CAT 4.5** Mover entre discos (copiar, comprobar y borrar el original).
- **CAT 4.6** Renombrado múltiple con plantilla (también para `MUS 8.3`).
- Después: deshacer renombrar y mover con Ctrl+Z (`GEN 1`).

### Fase CAT 6 — Carpetas que faltan y «Localizar…»

Acordado con el autor el 20/11/2026 ([DECISIONES.md](DECISIONES.md)): que el árbol de «Carpetas» diga qué carpeta falta en el disco (borrada, renombrada o movida fuera de la aplicación) y qué ubicación está desconectada, y poder decirle al catálogo dónde están ahora. «Localizar…» solo cambia el catálogo, nunca el disco.

- ~~**CAT 6.1** El árbol, al día al conectar o desconectar un disco con la aplicación abierta~~ (hecho y verificado el 20/11/2026; antes solo cambiaban las tarjetas).
- ~~**CAT 6.2** La carpeta que falta~~ (hecho y verificado el 20/11/2026):
  - ~~**6.2a** Marcarla en el árbol (el del Catálogo y el de los módulos), con el aviso naranja de las tarjetas en lugar de su icono y el texto atenuado (las de dentro, solo atenuadas), su texto emergente y su menú; la ubicación desconectada, con el aviso gris en lugar del disco~~ (hecho el 20/11/2026).
  - ~~**6.2b** Sus archivos, ausentes: cuando la comprobación de disponibilidad ve que falta una carpeta, marca como ausentes todos sus archivos (lo mismo que «Sincronizar» en la de encima; decidido por el autor el 20/11/2026)~~ (hecho el 20/11/2026).
  - ~~**6.2c** «Quitar archivos ausentes del catálogo…» quita también las carpetas apuntadas que ya no existen en el disco (si no, la carpeta se quedaba en el árbol, con 0); la pregunta y el mensaje las nombran~~ (hecho el 20/11/2026; pedido por el autor).
- ~~**CAT 6.3** «Localizar…» de una ubicación desconectada o movida (un disco externo con otra letra): cambia la ruta de su raíz (las de dentro son relativas), con el recuento de lo que se encuentra en la carpeta nueva antes de confirmar (si no hay nada, no se permite) y las reglas de añadir una carpeta (sin solapes); la ubicación pasa a llamarse como la carpeta nueva~~ (hecho y verificado el 20/11/2026: se miran hasta 1 000 archivos repartidos; la opción, arriba en el menú y solo donde se puede; después no se sincroniza).
- **CAT 6.4** «Localizar…» de una carpeta que falta: sus rutas en el catálogo (como la parte de catálogo de `CAT 4.3`), conservando los `id`; como en el `6.3`, cuántos de sus archivos están, la pregunta y, al localizarla, se desmarcan los que están (el `6.2b` los marcó ausentes). **En espera** (decidido por el autor el 20/11/2026, tras probar el resto de `CAT 6`): hoy se arregla sincronizando la carpeta de encima y quitando los ausentes (sus datos vuelven de los archivos; se pierde sobre todo en qué colecciones estaban); se hará si en el uso real hace falta. **Por decidir**, con la propuesta del asistente: (1) dónde puede estar la carpeta nueva: en la misma ubicación (propuesta: solo esto por ahora), en otra ubicación del catálogo o fuera de todas (rechazadas con un aviso; el traslado entre discos desde la aplicación es `CAT 4.5`); (2) si la carpeta nueva ya está en el catálogo (se sincronizó la de encima tras renombrarla fuera): rechazarlo con una explicación (propuesta: lo práctico es «Quitar del catálogo…» la antigua; los datos que están en los archivos se conservan, se pierden sobre todo las colecciones) o fusionar (las fichas antiguas con sus colecciones; se perdería lo editado en las nuevas).
- Después, si hace falta: reconocer el disco por su identificador de volumen y proponer «Localizar…» solo cuando aparece con otra letra.

### Mejoras menores (CATÁLOGO)

- **Barra lateral y colecciones**: mover colecciones entre conjuntos arrastrando; «Orden personalizado» en las colecciones estáticas (`collection_items.position`); exportar e importar colecciones, o que sobrevivan a recrear el catálogo (hoy solo están en la BD); «Clasificación» del sistema con «≥» en lugar de «=»; «Duplicar» una colección del sistema como inteligente del usuario; campo «Colección» (pertenencia) en las inteligentes; «Guardar la selección rápida como colección»; «Últimos archivos añadidos» en la sección Catálogo.
- **Carpetas**: «Eliminar carpetas vacías…» (las que siguen vacías en el disco, en lote, del disco y del catálogo, con su aviso; lo propuso el autor el 20/11/2026, sin decidir).
- **Archivos ausentes**: filtro «ocultar ausentes»; en la vista individual, «Localizar…» junto al aviso de archivo no encontrado.
- **Bibliotecas**: 2b-2, **aparcado** (el autor no cree probable cambiar una carpeta de «Música» a «Fotos y vídeos»): cambiar el tipo de contenido de una carpeta ya catalogada desde su menú, ofreciendo quitar lo que ya no encaja. Que la biblioteca puesta a mano sobreviva a recrear el catálogo: no por ahora (sería una clave `library` en el `.arca.json`).
- Posible: un solo componente para el árbol de carpetas del Catálogo y el de Imagen.

---

## IMAGEN

Cómo funciona hoy el módulo y dónde está cada cosa: [MOD_IMAGEN.md](MOD_IMAGEN.md).

### Fase IMG 1 — La tarjeta de Imagen

Las líneas de información de la tarjeta de Imagen (dimensiones, duración...; las de la vista individual ya se piden por archivo: `fetch_media_file`), con el perfil de tarjeta común (`GEN 16`).

### Fase IMG 2 — Verificar los RAW con ExifTool real

`inspect_cli --campos` con NEF, CR2/CR3, ARW, ORF, RW2, PEF, RAF y WebP; comparar con Lightroom (tamaño y orientación, sobre todo; `DefaultCropSize` solo existe en los DNG). Hecho con JPEG, HEIC (horizontal y vertical) y DNG.

### Fase IMG 3 — Reconocimiento facial

Anotado el 03/11/2026: personas como palabras clave especiales (Lightroom las guarda en «[Personas]»). Si procede, importar las regiones de caras de Lightroom (`XMP-mwg-rs:RegionInfo`: nombre y rectángulo de cada cara, tipo `Face`), que ya están en los archivos etiquetados. Por decidir: detección y agrupación propias (biblioteca local, sin nube), dónde se guardan las regiones (tabla nueva) y si se escriben de vuelta en el XMP.

---

## MÚSICA (módulo Audio)

Definido con el autor el 16/11/2026. La arquitectura, el detalle de cada paso (archivos, cómo se acepta) y lo que queda por decidir (M1 a M7), en [MOD_MUSICA.md](MOD_MUSICA.md). El escritor (`MUS 6`) va antes que la edición (`MUS 7`), a propósito.

### Fase MUS 1 — Leer las etiquetas

- **MUS 1.1** Base de audio: mutagen (la instala el autor), la tabla campo ↔ etiqueta y la lectura, en `core/audio/`.
- **MUS 1.2** La tabla `audio_details` (la siguiente migración libre; la 5 es el registro de operaciones de `CAT 4` y la 6, las carpetas de `CAT 5`).
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
- **MUS 4.3** Listas que se recorren con las flechas (álbumes; vale también para las películas, `VID 5.4`): el detalle, en [MOD_MUSICA.md](MOD_MUSICA.md).

### Fase MUS 5 — La lista en Música

La vista de lista es de todos los módulos (`GEN 18`). Aquí, lo de Música:

- **MUS 5.1** Sus columnas (título, artista, álbum, pista, año, duración...).
- **MUS 5.3** Opcional: vista de álbumes con su carátula.

### Fase MUS 6 — Escribir en los archivos

En el propio archivo, sin generar copias (regla del 16/11/2026). Sin interfaz: se prueba con copias.

- **MUS 6.1** Escritor de MP3 (ID3): solo lo editado, la versión de ID3 conservada, comprobando las etiquetas y que el audio no cambia.
- **MUS 6.2** En la cola de escritura: los campos de audio en `editable_fields.py` y el escritor, registrado en `writers.py` (`GEN 14`, hecho); la lectura de un formato repartido entre el archivo y el `.arca.json`; lo que no sabe guardar, al `.arca.json`. La marca de pendiente sigue siendo un bit por campo (caben 63; se revisa con Vídeo).
- **MUS 6.3** FLAC.
- **MUS 6.4** M4A y Ogg/Opus.

### Fase MUS 7 — Editar

- **MUS 7.1** Edición en la sección «Audio» del inspector.
- **MUS 7.2** Con varias canciones («Varios», «Edición múltiple»).
- **MUS 7.3** Opcional: editar en la vista de lista.

### Fase MUS 8 — Herramientas por lotes

- **MUS 8.1** Numerar pistas, mayúsculas y minúsculas, buscar y reemplazar.
- **MUS 8.2** Nombre de archivo → etiqueta.
- **MUS 8.3** Etiqueta → nombre de archivo (renombra originales: con el motor de `CAT 4`, M6).

### Fase MUS 9 — Carátulas: cambiarlas y guardarlas

- **MUS 9.1** La carátula en grande en el inspector.
- **MUS 9.2** Escribirla en el archivo, por la misma cola.
- **MUS 9.3** Cambiarla: arrastrar, «Elegir…», pegar o `folder.jpg`; para una canción, la selección o el álbum.
- **MUS 9.4** Extraerla o quitarla.

### Fase MUS 10 — Internet

Etiquetas y carátulas de MusicBrainz y Cover Art Archive, como una edición más.

---

## VÍDEO

Definido con el autor el 16/11/2026. La arquitectura, el detalle de cada paso y las decisiones (V1 a V11), en [MOD_VIDEO.md](MOD_VIDEO.md). La ficha es de la **obra** (película, serie, documental, evento deportivo), no del archivo; las obras salen solas de los archivos. Hasta `VID 6` no hace falta internet.

### Fase VID 1 — Datos técnicos y nombre

- **VID 1.1** Datos técnicos de película: contenedor, audio, subtítulos, tasa de bits, HDR (`VIDEO_FIELDS_VERSION` 3). Se decide si basta ExifTool o hace falta `ffprobe`.
- **VID 1.2** Leer el nombre (`core/video/name_parser.py`): título, año, temporada, episodio, parte.

### Fase VID 2 — Obras

- **VID 2.1** El esquema: `video_works`, géneros, personas, créditos y las columnas nuevas de `video_details`.
- **VID 2.2** Crear las obras y enlazar los archivos, por el nombre y la carpeta.
- **VID 2.3** El tipo de obra (película, serie, documental, evento deportivo, otro).

### Fase VID 3 — Verlas

- **VID 3.1** Sección «Ficha» del inspector, de solo lectura.
- **VID 3.2** Orden propio: título, año, duración, resolución.
- **VID 3.3** Campos del grupo «Vídeo» en filtros y colecciones inteligentes.

### Fase VID 4 — Miniaturas

- **VID 4.1** Fotograma con `ffmpeg` (en `tools/ffmpeg`, como ExifTool; hacia el 10 % de la duración, para evitar negros), como un origen más del motor; también para los vídeos de Imagen.
- **VID 4.2** El cartel como miniatura, cuando la obra lo tiene.

### Fase VID 5 — Navegar

- **VID 5.1** «Biblioteca - Vídeos» por tipo; «Sin ficha».
- **VID 5.2** «Géneros», «Directores», «Reparto» y «Años».
- **VID 5.3** Series: sección «Series» (serie ▸ temporada) y «Agrupar en una obra» / «Separar», sobre la tarjeta agrupada común (`GEN 17`).
- **VID 5.4** Listas que se recorren con las flechas (lo de `MUS 4.3`).

### Fase VID 6 — Visto / no visto y ficha a mano

- **VID 6.1** Visto / no visto: botón, menú, atajo, filtro en «Atributos» y «No vistos» en la barra.
- **VID 6.2** Editar los campos de texto de la ficha en el inspector.
- **VID 6.3** Editar géneros, director y reparto.
- **VID 6.4** Poner el cartel a mano.
- **VID 6.5** Cambiar la temporada y el número de un episodio, la parte y la versión.
- **VID 6.6** La identificación, visto y lo editado, en el `.arca.json` (el archivo de vídeo no se escribe).

### Fase VID 7 — Descargar de la web

Antes de empezar: comprobar las condiciones de TMDb para el uso interno de la empresa (V2).

- **VID 7.1** El proveedor de fichas (`core/video/providers/`) y Opciones > Vídeo.
- **VID 7.2** «Identificar…» para una obra: candidatos, elegir, descargar la ficha, el reparto, el cartel y el fondo.
- **VID 7.3** Por lotes, en segundo plano y cancelable.
- **VID 7.4** «Actualizar la ficha» sin pisar lo editado a mano.

### Fase VID 8 — Vista «Ficha»

- **VID 8.1** La vista del centro, al estilo de VisualDivX, con «Reproducir» (reproductor del sistema).
- **VID 8.2** Edición en la propia ficha.
- **VID 8.3** Pulsar un director, un actor o un género lleva a sus obras.

### Fase VID 9 — Series a fondo

- **VID 9.1** Los episodios en la ficha de la serie, con su título y su sinopsis descargados.
- **VID 9.2** Progreso de episodios vistos; «siguiente episodio».

### Fase VID 10 — Extras (sin orden)

Sagas en la barra; tráiler; importar y exportar `.nfo`; un proveedor para eventos deportivos; obras sin archivo.

### Mejoras menores (VÍDEO)

- **Vídeo convertido** (`.MOV` → `.mp4` en HEVC, pregunta del autor): hoy, al sincronizar, el `.MOV` queda ausente y el `.mp4` entra como nuevo (pierde valoración, marca, color y colecciones). Idea: si un ausente y un nuevo de la misma carpeta comparten nombre base y duración (± 1 s), proponer reasociarlos (mismo id, ruta nueva).

---

## EBOOKS (Libros)

Definido con el autor el 16/11/2026, como punto de partida. La arquitectura, lo básico de los formatos, el detalle de cada paso y las decisiones (E1 a E10), en [MOD_EBOOKS.md](MOD_EBOOKS.md). El módulo aún no existe. Hasta `EBK 6` no se escribe en ningún libro; el escritor (`EBK 7`) va antes que la edición (`EBK 8`). Antes de `EBK 2` hace falta una carpeta de prueba con libros reales (en el catálogo del autor no hay ninguno).

### Fase EBK 1 — El módulo

- **EBK 1.1** Su línea en `MODULES` (`config/app_modules.py`), botón en la toolbar, icono y `EbookModule` (sobre `LibraryModule`: biblioteca, carpetas y fechas).
- **EBK 1.2** Los formatos que se catalogan: `.azw` y, solo en carpetas declaradas de libros, `.pdf`.

### Fase EBK 2 — Leer los metadatos

- **EBK 2.1** Lector de OPF y de EPUB (`core/ebooks/`): campos, portada y DRM.
- **EBK 2.2** La tabla `ebook_details` (una migración).
- **EBK 2.3** El extractor (`core/metadata/ebook/`, `EBOOK_FIELDS_VERSION`), con EPUB.
- **EBK 2.4** El `metadata.opf` de Calibre, si está junto al libro.
- **EBK 2.5** PDF y Kindle (MOBI, AZW3), con ExifTool: a comprobar con archivos reales.

### Fase EBK 3 — Verlos

- **EBK 3.1** Sección «Libro» del inspector, de solo lectura.
- **EBK 3.2** Orden propio: autor, título, serie y número, año.
- **EBK 3.3** Campos del grupo «Libros electrónicos» en filtros y colecciones inteligentes.

### Fase EBK 4 — Portadas como miniatura

- **EBK 4.1** La portada del EPUB y el `cover.jpg` de Calibre.
- **EBK 4.2** La de MOBI / AZW3.
- **EBK 4.3** La primera página del PDF (necesita una dependencia nueva: E4).

### Fase EBK 5 — Navegar

- **EBK 5.1** Secciones «Autores» (autor ▸ serie) y «Series».
- **EBK 5.2** Secciones «Materias», «Idiomas» y «Años».
- **EBK 5.3** La vista de lista (`GEN 18`) y las listas que se recorren con las flechas (lo de `MUS 4.3`).

### Fase EBK 6 — Leído / no leído y abrir

- **EBK 6.1** Leído / no leído: menú, atajo, filtro en «Atributos» y «No leídos» en la barra; en el `.arca.json`.
- **EBK 6.2** Abrir el libro con el programa del sistema.

### Fase EBK 7 — Escribir en los archivos

Sin interfaz: se prueba con copias.

- **EBK 7.1** Escritor de EPUB (el OPF dentro del ZIP), comprobando que el resto del libro no cambia.
- **EBK 7.2** En la cola de escritura; lo que no sabe guardar, y los libros con DRM, al `.arca.json`.
- **EBK 7.3** PDF con ExifTool, si la prueba con lectores reales sale bien (E5).

### Fase EBK 8 — Editar

- **EBK 8.1** Edición en la sección «Libro», de un libro y de varios.
- **EBK 8.2** Cambiar la portada de un EPUB.
- **EBK 8.3** Por lotes: nombre del archivo → título y autor; mayúsculas y minúsculas; buscar y reemplazar.

### Fase EBK 9 — Un libro, varios formatos

Una tarjeta por libro (EPUB, MOBI y PDF del mismo), con la tarjeta agrupada común (`GEN 17`).

### Fase EBK 10 — Internet

Datos y portada por ISBN, o por título y autor, como una edición más.

### Fase EBK 11 — Extras (sin orden)

Cómics (CBZ, CBR); FB2 completo; exportar un `metadata.opf` para Calibre.

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

Detalle y recomendación en [MOD_TRACKS.md](MOD_TRACKS.md) §11; ninguna bloquea hasta su paso. **D2, decidida** (el autor, 16/11/2026): un GPX editado se guarda sobre el propio archivo, sin generar copias; cómo se hace con seguridad, en `TRK 6.1`.

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
| A.4 (módulo Imagen completo) | `GEN 16`; `IMG 1` |
| A.5 (vista de lista; vista de mapa) | `GEN 18` y `MUS 5`; `GEN 8` y las fases de TRACKS |
| A.6 (módulos Vídeo, Audio y Tracks) | `MUS 1` a `MUS 10`, `VID 1` a `VID 10`, fases de TRACKS |
| A.7 («Abrir en su módulo») | Mejoras menores (GENERAL) |
| B (mejoras anotadas) | Las «Mejoras menores» de cada categoría; el deshacer, `GEN 1`; el reconocimiento facial, `IMG 3`; la edición para Audio y Vídeo, `MUS 6`, `MUS 7` y `VID 6` |
| C.1 (verificar con ExifTool real) | `IMG 2` |
| C.2 (miniaturas de vídeo y audio) | `VID 4`, `VID 7` (carteles), `MUS 3` y `MUS 9` |
| C.3 (miniaturas, extras) | `GEN 4` |
| C.4 (datos del usuario, lo que falta) | `GEN 3`; la valoración en POPM, M5 de [MOD_MUSICA.md](MOD_MUSICA.md) |
| C.5 (más metadatos editables) | `GEN 2` |
| C.6 (extractores de audio y ebooks) | `MUS 1`; `EBK 2` |
| `GEN 9` (módulo Ebooks; solo del 16/11/2026) | La categoría EBOOKS: `EBK 1` a `EBK 11` |
| C.7 (hashes) | `CAT 2` |
| C.8 (archivos sueltos, ubicaciones solapadas) | `CAT 1` |
| C.9 (empaquetado) | `GEN 5` |
| C.10 (interfaz) | `GEN 6` |
| C.11 (optimizaciones) | `GEN 10` |
| C.12 (omitido de la v1) | Mejoras menores (GENERAL) |
| Fases 4 a 8 de [MOD_TRACKS.md](MOD_TRACKS.md) §10 | `TRK 4` a `TRK 8` (el mismo número) |
