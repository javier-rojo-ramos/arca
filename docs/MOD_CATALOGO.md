# Arca Media — Módulo Catálogo: arquitectura y plan

> Documento del módulo Catálogo (`CatalogModule`: todos los archivos, de todas las bibliotecas) y de lo que es **del catálogo entero**: crearlo y abrirlo, añadir y sincronizar carpetas, las bibliotecas, las colecciones, los archivos ausentes y eliminar. Tiene dos partes: **I, arquitectura** (cómo funciona hoy) y **II, planificación** (lo que falta, con los códigos de [PENDIENTE.md](PENDIENTE.md)).
> **Estado (16/11/2026): funciona de punta a punta.** Escrito **a posteriori**, a partir del código, para tener en un solo sitio qué hace y dónde está cada cosa. No repite el detalle de [FLUJOS.md](FLUJOS.md), [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md) ni [ARQUITECTURA.md](ARQUITECTURA.md): enlaza a ellos. Si el código y este documento no coinciden, manda el código.
> Índice: [INDEX.md](INDEX.md).

## Resumen

**Qué es**: el módulo que ve **todo** lo catalogado, sea del tipo que sea, y desde el que se gestiona el catálogo: qué carpetas tiene, qué hay en cada una, qué falta y cómo se agrupa en colecciones. Los demás módulos ([Imagen](MOD_IMAGEN.md), [Música](MOD_MUSICA.md), [Vídeo](MOD_VIDEO.md), [Tracks](MOD_TRACKS.md)) miran cada uno su biblioteca.

| Función | Estado |
|---|---|
| Crear y abrir un catálogo (carpeta autónoma, migraciones) | Hecho y verificado |
| Añadir y sincronizar carpetas; ubicaciones sin solapes | Hecho y verificado (más de 20 000 imágenes en segundos) |
| Bibliotecas: «¿Qué contiene esta carpeta?», clasificación de los vídeos, submenú «Biblioteca» | Hecho y verificado |
| Archivos ausentes y ubicaciones desconectadas | Hecho y verificado; la detección con el catálogo abierto, por comprobar |
| Barra: Catálogo, Carpetas y Colecciones | Hecho y verificado |
| Colecciones: del sistema, conjuntos, estáticas e inteligentes (con grupos de reglas) | Hecho y verificado |
| Quitar del catálogo y eliminar del disco (papelera) | Hecho y verificado; unidades de red y la papelera real, sin probar |
| Vista de mapa (ver y seleccionar) | Hecho y verificado |
| Archivos sueltos, fusión de ubicaciones, duplicados (hashes) | Pendiente (`CAT 1`, `CAT 2`) |

---

# Parte I — Arquitectura

## 1. Qué es un catálogo

- **Una carpeta autónoma**: `catalogo.db` (SQLite en modo WAL), `cache/<tipo>/` (las miniaturas) y `media_assets/` (`backdrops`, `covers`, `posters`). La crea `core/catalog/catalog_builder.py`; la abre `catalog_opener.py` (comprueba que es SQLite y de esta aplicación, `APPLICATION_ID`, y aplica las migraciones).
- **Esquema**: `core/catalog/catalog_schema.py` (`MIGRATIONS`, solo se añade al final; hoy, v4). Tablas, bloques de columnas y quién escribe cada uno: [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md).
- **Lo que no está en el catálogo**: la configuración (`settings.json`, en la carpeta de la aplicación; el catálogo abierto, el estado de cada barra por catálogo) y la caché de teselas del mapa.
- **Sobrevive a recrearlo**: lo que el usuario pone en los archivos (valoración, marca, color, palabras clave, metadatos editados; `core/userdata/`) vuelve al añadir de nuevo las carpetas. Las colecciones, no: solo están en la base de datos.
- **Acceso a la base de datos**: la interfaz nunca la toca en el hilo principal. Consultas con `db.execute_async` (`core/database/db_manager.py`); trabajos largos con `JobManager` (`core/workers/job_manager.py`). Qué corre en cada hilo: [ARQUITECTURA.md](ARQUITECTURA.md).
- Crear, abrir y cerrar, paso a paso: [FLUJOS.md](FLUJOS.md) §2 y §10.

## 2. El módulo (`controllers/app_modules/catalog_module.py`)

| Qué declara | Valor |
|---|---|
| Vistas (`views`) | Cuadrícula (la inicial), vista individual y mapa |
| Mapa | Solo ver y seleccionar (con la tira de fotos); no se ubican fotos aquí |
| Tipos del filtro (`filter_media_types`) | Foto, vídeo, audio y track |
| Columnas de partida de «Metadatos» (`filter_metadata_fields`) | Tipo de archivo, fecha de captura y palabra clave |
| Campos de orden (`sort_fields`) | Los seis comunes (`COMMON_SORT_FIELDS`) |
| Orden de partida (`default_order`) | Nombre (con tipos mezclados, la hora de captura dejaría al final lo que no la tiene) |

- `refresh` rellena la barra en segundo plano: los contadores de las filas (`count_grid_items`), el árbol de carpetas (`fetch_folder_tree`) y el de colecciones (`fetch_collection_tree`).
- Crea y conecta `CollectionActions` (`controllers/collection_actions.py`): la barra, el menú de la cuadrícula y la base de datos.
- `save_state` / `restore_state`: lo desplegado y la fila elegida, por catálogo.
- **Lo que sigue en el controlador principal** (`main_window_controller.py`, con `controllers/folder_actions.py`): las operaciones con el catálogo entero que se piden desde la barra (añadir, sincronizar o mostrar una carpeta, quitar ausentes, vaciar la selección rápida).

## 3. Barra izquierda (`ui_helpers/sidebars/catalog_sidebar.py`)

Tres secciones plegables; cada fila lleva un `GridSource` (qué mostrar) y su recuento. La barra no sabe nada de SQL. Detalle: [FLUJOS.md](FLUJOS.md) §9.

| Sección | Filas | Notas |
|---|---|---|
| «Catálogo» | «Todos los archivos», «Selección rápida» y «Sin clasificar» | «Sin clasificar» solo se ve si hay algo sin biblioteca |
| «Carpetas» | Una raíz por ubicación y su árbol, con recuentos | Botón «+»: añadir carpeta. Menú: «Sincronizar carpeta», «Mostrar en el Explorador», «Quitar archivos ausentes del catálogo», «Quitar del catálogo…». La opción «Mostrar los elementos de las subcarpetas» (Opciones > Catálogo) decide qué se ve al elegir una |
| «Colecciones» | Las del sistema (Clasificación, Etiqueta, Marcadas, Rechazadas) y las del usuario | Botón «+» y menú: crear conjunto, colección o colección inteligente; renombrar; borrar; soltar tarjetas sobre una colección |

## 4. Carpetas, ubicaciones y bibliotecas

**Añadir una carpeta** (sirve también para reescanear; [FLUJOS.md](FLUJOS.md) §3):

1. Se elige la carpeta y se responde a **«¿Qué contiene esta carpeta?»** (`FolderContentDialog`): «Detectar automáticamente» o una biblioteca.
2. `storage_locations.register_folder`: la reutiliza si está dentro de una ubicación existente, crea una nueva si no, y **rechaza** la que contiene ubicaciones existentes (`OverlappingLocationError`) y la del propio catálogo.
3. `folder_scanner.py` la recorre (`scan_filter.py`, `media_detector.py`) y `folder_importer.py` inserta por lotes; lo que no encaja con el contenido declarado de su carpeta se ignora.
4. Lo que ya no está se marca **ausente** (solo si el recorrido fue completo y fiable).
5. Después se encadenan, en segundo plano: leer los metadatos, generar las miniaturas y escribir lo pendiente en los archivos.

**Bibliotecas** (`core/catalog/libraries.py`): qué módulo gestiona cada archivo (`media_items.library`), aparte de su tipo técnico (`media_type`). Se decide por carpeta, no archivo a archivo:

| La carpeta contiene | Se cataloga | Biblioteca |
|---|---|---|
| Detectar automáticamente | Todo lo soportado | Por tipo; el vídeo, por su nombre y, después, por sus metadatos; lo dudoso queda «Sin clasificar» |
| Imágenes | Fotos y vídeos | `image` |
| Vídeos | Solo vídeos | `video` |
| Música | Solo audio | `audio` |
| Libros | Solo ebooks | `ebook` |
| Tracks GPS | Solo GPX | `tracks` |

La biblioteca se corrige a mano con el submenú «Biblioteca» de la cuadrícula (queda fijada: ni el escáner ni la detección la cambian). Los nombres para el usuario salen siempre de `LIBRARY_NAMES`.

## 5. Archivos ausentes y ubicaciones desconectadas

- **Ausente**: el archivo ya no está donde estaba (`is_missing`). Se ve con su velo e indicador, conserva sus datos y vuelve solo si reaparece. «Quitar archivos ausentes del catálogo» los borra (`missing_items.py`).
- **Sin conexión**: la ubicación entera no está (disco desconectado); sus archivos no se marcan ausentes (`storage_locations.refresh_location_status`).
- **Con el catálogo abierto**: `availability.check_availability` comprueba cada pocos segundos, y al volver a la ventana, los archivos que desaparecen o vuelven.

## 6. Colecciones

- **Del sistema** (`system_collections.py`): inteligentes fijas (Clasificación 1 a 5, Etiqueta por color, Marcadas, Rechazadas).
- **Del usuario** (`user_collections.py`; tablas `collections` y `collection_items`): **conjuntos** (carpetas de colecciones), **estáticas** (los archivos que se le añaden: arrastrando, o con el menú de la cuadrícula) e **inteligentes** (unas reglas).
- **Inteligentes**: reglas en JSON con versión (`collections.rules_json`, versión 2, con grupos de un nivel); los campos, en `smart_fields.py`; el SQL, en `smart_rules.py`. El editor (`SmartCollectionDialog`) cuenta en vivo cuántos archivos cumplen. Unas reglas ilegibles no rompen la barra.
- **El mismo motor** sirve a la barra de filtros de todos los módulos y a las secciones «Fechas» y «Sin clasificar»: un solo sitio traduce origen y filtro a SQL (`media_queries.source_condition`).

## 7. Centro, inspector y filtros

Son los comunes a todos los módulos:

- **Cuadrícula y vista individual**: [FLUJOS.md](FLUJOS.md) §6 y §11. Con tipos mezclados, cada tarjeta se dibuja según el suyo (foto, vídeo con su duración, canción, track con su recorrido).
- **Mapa**: lo del origen elegido, como marcadores y líneas; solo ver y seleccionar ([MOD_TRACKS.md](MOD_TRACKS.md), [FLUJOS.md](FLUJOS.md) §16).
- **Inspector**: las secciones según la biblioteca de lo seleccionado ([FLUJOS.md](FLUJOS.md) §12); las palabras clave y la clasificación se editan aquí con cualquier tipo de archivo.
- **Barra de filtros** y **barra inferior** (clasificar la selección, vistas, orden, tamaño de las tarjetas): [FLUJOS.md](FLUJOS.md) §14 y §15.

## 8. Quitar y eliminar

| Orden | Qué hace | Dónde |
|---|---|---|
| «Eliminar del catálogo» | Quita los archivos del catálogo; siguen en su carpeta y vuelven al sincronizar | `media_removal.py` |
| «Eliminar del disco» | Además, los envía a la Papelera (con el sidecar de un RAW). Los ausentes, los de una ubicación desconectada y los de una unidad de red solo se quitan del catálogo | `media_removal.py`; la papelera se le pasa como función desde la interfaz |
| «Quitar del catálogo…» (carpeta o ubicación) | Quita esa carpeta entera, también desconectada; los archivos del disco no se tocan | `folder_removal.py` |
| «Quitar archivos ausentes del catálogo» | Borra del catálogo los ausentes de una carpeta | `missing_items.py` |

Paso a paso y la ventana (`RemoveDialog`): [FLUJOS.md](FLUJOS.md) §13.

## 9. Dónde está cada cosa

| Qué | Archivos |
|---|---|
| Crear, abrir, esquema | `core/catalog/catalog_builder.py`, `catalog_opener.py`, `catalog_schema.py` |
| Carpetas y escaneo | `storage_locations.py`, `folder_scanner.py`, `scan_filter.py`, `media_detector.py`, `folder_importer.py`, `folder_tree.py` |
| Bibliotecas | `libraries.py`, `media_types.py` |
| Disponibilidad | `availability.py`, `missing_items.py` |
| Colecciones y reglas | `system_collections.py`, `user_collections.py`, `smart_fields.py`, `smart_rules.py` |
| Qué muestra la cuadrícula | `grid_source.py`, `media_queries.py`, `grid_orders.py`, `grid_filter.py` |
| Quitar y eliminar | `media_removal.py`, `folder_removal.py` |
| Módulo y barra | `controllers/app_modules/catalog_module.py`, `ui_helpers/sidebars/catalog_sidebar.py`, `controllers/collection_actions.py`, `controllers/folder_actions.py` |
| Base de datos y trabajos | `core/database/db_manager.py`, `core/workers/job_manager.py` |

Todos los de la primera columna sin ruta están en `core/catalog/`. El mapa completo, en [ARQUITECTURA.md](ARQUITECTURA.md).

## 10. Lo verificado y lo que no

De [ESTADO.md](ESTADO.md):

- **Verificado por el autor en Windows**: crear y abrir; añadir y sincronizar carpetas; ubicaciones sin solapes; ausentes y desconectadas; quitar ausentes; «Quitar del catálogo…»; las bibliotecas y la clasificación de los vídeos; la barra con sus tres secciones y su estado guardado; las colecciones, también las inteligentes con grupos; eliminar del catálogo y del disco.
- **Sin probar**: cuadrícula con decenas de miles de tarjetas visibles a la vez; la detección de unidades de red en Windows y la papelera real; macOS y Linux.
- **Comprobaciones sueltas** anotadas: un archivo abierto en otro programa al eliminar, archivos de una unidad de red, un RAW con su `.xmp` a la Papelera; abrir el editor de colecciones inteligentes con doble clic y reglas con cada tipo de valor; la detección de archivos que desaparecen o vuelven con el catálogo abierto.

---

# Parte II — Planificación

Lo que falta, con los códigos de [PENDIENTE.md](PENDIENTE.md) (ahí está la lista vigente).

### Fases del módulo

| Fase | Qué | Notas |
|---|---|---|
| `CAT 1.1` | Añadir archivos sueltos | Hoy solo carpetas completas; `action_add_files` está sin conectar. Lo necesita también un track nuevo creado en Tracks |
| `CAT 1.2` | Fusión de ubicaciones solapadas | Hoy se rechazan |
| `CAT 2` | Hashes: duplicados, comprobación de integridad y reasociar un archivo renombrado fuera | Columnas `hash_partial`, `hash_full`, `hash_verified_at`; pasos por definir |

### Fases de otras categorías que afectan al Catálogo

| Fase | Qué |
|---|---|
| `GEN 3` | Datos del usuario, lo que falta: notas y colecciones en el archivo de carpeta (para que las colecciones sobrevivan a recrear el catálogo) |
| `GEN 5` | Empaquetado |
| `GEN 6` | La lista de errores de escaneo (`scan_errors`), las acciones de menú sin conectar y separar «Abrir catálogo» de «Nuevo catálogo» |
| `GEN 7` | Guardar el filtro activo como colección inteligente |
| `GEN 9` | Módulo Ebooks (la biblioteca `ebook` existe; no hay extractor ni módulo) |
| `GEN 10` | Optimizaciones: un grupo de hilos propio para los trabajos, más índices |

### Mejoras menores

En la lista de CATÁLOGO de [PENDIENTE.md](PENDIENTE.md): mover colecciones entre conjuntos arrastrando; orden personalizado en las colecciones estáticas; exportar e importar colecciones; «Clasificación» del sistema con «≥»; duplicar una colección del sistema; campo «Colección» en las inteligentes; «Guardar la selección rápida como colección»; «Últimos archivos añadidos»; filtro «ocultar ausentes» y «Localizar…» un archivo ausente; cambiar el tipo de contenido de una carpeta ya catalogada (aparcado).

### Por decidir

Nada bloquea hoy. Al llegar a su paso: en `CAT 1.1`, dónde se registra un archivo suelto (¿una ubicación propia?); en `CAT 2`, cuándo se calculan los hashes (al importar o a petición) y qué se hace con un duplicado.
