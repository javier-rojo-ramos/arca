# Arca Media — Herramientas y pruebas

> Autopruebas de cada módulo, ventanas que se pueden abrir solas y herramientas de diagnóstico (ExifTool, miniaturas, GPX).
> Índice: [INDEX.md](INDEX.md).

**Entorno** (Windows, desde la raíz del proyecto): todo se ejecuta con el Python de `.venv` (`.venv\Scripts\python.exe`; en macOS y Linux, `.venv/bin/python`); en este documento, `python` es ese. Ruff se instala aparte (no está en `.venv`).

```
python -m venv .venv                                                            # crear el entorno (una vez)
.venv\Scripts\python.exe -m pip install -r requirements.txt                     # instalar las dependencias
.venv\Scripts\python.exe main.py                                                # arrancar la aplicación
.venv\Scripts\python.exe -m pip freeze | Out-File -Encoding utf8 requirements.txt   # regenerar requirements.txt (PowerShell)
```

Al regenerar `requirements.txt` desde PowerShell no se usa `>`: en Windows PowerShell 5.1 lo escribe en UTF-16 y Git lo trata como binario.

**Autopruebas** (desde la raíz del proyecto; cada una termina con "Autoprueba finalizada correctamente"). Las que dicen «una ventana» (`organize_bar`, `theme_style`) y las de `--ventana` se quedan abiertas hasta que alguien las cierra:

```
# core.jobs
python -m core.jobs.progress

# core.database
python -m core.database.db_manager

# core.catalog
python -m core.catalog.availability
python -m core.catalog.catalog_builder
python -m core.catalog.catalog_opener
python -m core.catalog.catalog_schema
python -m core.catalog.catalog_writer
python -m core.catalog.color_labels
python -m core.catalog.filter_presets
python -m core.catalog.folder_importer
python -m core.catalog.folder_removal
python -m core.catalog.folder_scanner
python -m core.catalog.folder_tree
python -m core.catalog.grid_filter
python -m core.catalog.grid_orders
python -m core.catalog.grid_source
python -m core.catalog.keywords                                (árbol, asignar y quitar, caja de texto, gestionar el árbol, recuentos)
python -m core.catalog.libraries
python -m core.catalog.media_detector
python -m core.catalog.media_queries
python -m core.catalog.media_removal                           (papelera simulada: nunca toca la del sistema)
python -m core.catalog.metadata_values                         (cada fila filtra lo que cuenta)
python -m core.catalog.missing_items
python -m core.catalog.scan_filter
python -m core.catalog.selection_metadata
python -m core.catalog.selection_summary
python -m core.catalog.smart_fields
python -m core.catalog.smart_rules
python -m core.catalog.storage_locations
python -m core.catalog.system_collections
python -m core.catalog.timeline                                (cada fila muestra lo que cuenta)
python -m core.catalog.user_collections

# core.metadata
python -m core.metadata.exiftool_extractor
python -m core.metadata.exiftool_runner
python -m core.metadata.field_spec
python -m core.metadata.image.extractor
python -m core.metadata.image.fields
python -m core.metadata.image.pillow_extractor
python -m core.metadata.inspect_cli --autoprueba
python -m core.metadata.keyword_tags                           (palabras clave de las etiquetas de ExifTool: rutas y sueltas)
python -m core.metadata.processor
python -m core.metadata.track.extractor
python -m core.metadata.track.gpx_reader
python -m core.metadata.track.inspect_cli ruta.gpx    (diagnóstico de GPX: resumen y desnivel con varios umbrales)
python -m core.metadata.video.extractor
python -m core.metadata.video.fields
python -m core.metadata.video.rules

# core.thumbnails
python -m core.thumbnails.cache
python -m core.thumbnails.full_image                          (el original entero, derecho y en sRGB; RAW con ExifTool simulado)
python -m core.thumbnails.generator
python -m core.thumbnails.imaging
python -m core.thumbnails.job
python -m core.thumbnails.sizes

# core.maps
python -m core.maps.tile_layers                                (capas del mapa: claves, direcciones, teselas válidas; sin red)
python -m core.maps.tile_store                                 (caché de teselas: rutas, caducidad, tope de tamaño; sin red)

# ui_helpers.map
python -m ui_helpers.map.map_types                             (marcadores, tracks y rectángulos del mapa; sin Qt)
python -m ui_helpers.map.map_view                              (MapView con un fondo simulado; sin ventana)
python -m ui_helpers.map.map_view --ventana                    (una ventana: el mapa de verdad, con 5 000 marcadores de prueba; descarga teselas)

# core.userdata
python -m core.userdata.editable_fields                        (las etiquetas que se escriben son las mismas que se leen)
python -m core.userdata.folder_file
python -m core.userdata.policy
python -m core.userdata.sync                                   (ExifTool; ida y vuelta completa)
python -m core.userdata.xmp_writer                             (ExifTool)

# controllers
python -m controllers.app_modules.center_views                 (vistas del centro; sin Qt)
python -m controllers.app_modules.module_view_state            (orden, vista y filtro por módulo, guardar y recuperar; sin Qt)
python -m controllers.center_view_controller                   (página, botones, deslizador y navegación con teclas y con la rueda, con un host de mentira; sin ventana)
python -m controllers.filter_controller                        (barra <-> filtro con un host de mentira, Ctrl+L, Ctrl+F, fila de Texto, vista individual; sin ventana)
python -m controllers.filter_preset_controller                 (ajustes del módulo, el que coincide, elegir, restaurar, guardar y reemplazar, con host y configuración de mentira y las preguntas cambiadas; sin ventana)
python -m controllers.folder_actions                           (solo el texto del aviso)
python -m controllers.metadata_filter_controller               (columnas de partida, qué se recuenta, respuestas tardías, alto guardado, con host, modelo y BD de mentira; sin ventana)

# ui_helpers
python -m ui_helpers.dialogs.filter_presets_dialog             (subir, bajar, arrastrar, cambiar el nombre con vacío y repetido, eliminar, restaurar los de fábrica; sin ventana. Con --ventana, la ventana con los de fábrica y uno más)
python -m ui_helpers.dialogs.smart_collection_dialog           (crear y editar, añadir y quitar reglas y grupos, recuento y recuentos tardíos, errores en rojo, lo elegido; sin ventana. Con --ventana, la ventana con un contador simulado y un aviso de ejemplo)
python -m ui_helpers.helpers.card_glyphs                       (dibuja marcadores e indicadores en una imagen; sin ventana)
python -m ui_helpers.helpers.card_marks                        (dibuja las marcas en una imagen; necesita PySide6)
python -m ui_helpers.helpers.keyword_menu                      (lógica del menú de los árboles de palabras clave; sin ventana)
python -m ui_helpers.helpers.theme_colors                      (contraste y formato de los colores del tema; marcas legibles sobre la banda)
python -m ui_helpers.helpers.theme_qss                         (la hoja general, solo con colores del tema)
python -m ui_helpers.helpers.theme_style                       (colores de los indicadores y una ventana con todos sus estados)
python -m ui_helpers.helpers.zoom_geometry                     (cuentas del zoom 1:1 de la vista individual; sin Qt)
python -m ui_helpers.inspector.editable_row                    (cajas editables; sin ventana)
python -m ui_helpers.inspector.formatting
python -m ui_helpers.inspector.keyword_editor_section
python -m ui_helpers.inspector.keywords_section
python -m ui_helpers.inspector.metadata_fields                 (todas las vistas sobre una foto y un vídeo de ejemplo)
python -m ui_helpers.inspector.metadata_section                (su aviso «Edición múltiple»; sin ventana)
python -m ui_helpers.inspector.value_parsing                   (lo escrito en las cajas del GPS, la altitud y la dirección; sin Qt)
python -m ui_helpers.sidebars.sections.date_section            (textos de las fechas, árbol, orígenes y lo desplegado; sin ventana)
python -m ui_helpers.models.full_image_loader                  (caché temporal: la mayor miniatura, sin miniatura, memoria; sin ventana)
python -m ui_helpers.models.original_image_loader              (el original entero y derecho en RGB32, solo el último pedido, cancelar, archivo que no existe; sin ventana)
python -m ui_helpers.widgets.attribute_filter_row              (clics en marcas, estrellas, colores, selección rápida y tipos; operador; dibujo; sin ventana)
python -m ui_helpers.widgets.filter_bar                        (pestañas, «Ninguno», candado y paneles; sin ventana)
python -m ui_helpers.widgets.filter_preset_button              (texto del botón, menú, ✓, qué se puede pulsar; sin ventana)
python -m ui_helpers.widgets.keyword_checklist
python -m ui_helpers.widgets.metadata_column                   (textos, selección, fechas, menú de campos y engranaje; sin ventana. Con --ventana, tres columnas de ejemplo en una ventana)
python -m ui_helpers.widgets.metadata_filter_panel             (columnas, añadir y quitar, qué recontar, alto y arrastre; sin ventana. Con --ventana, el panel sobre un catálogo de ejemplo en memoria, con la cascada)
python -m ui_helpers.widgets.organize_bar                      (lógica de la barra y la barra sola en una ventana)
python -m ui_helpers.widgets.recent_keywords
python -m ui_helpers.widgets.single_media_view                 (dibuja en una imagen con un modelo de mentira; sin ventana)
python -m ui_helpers.widgets.single_view_zoom                  (lupa, caché pequeña, clic, arrastre, Z, Ctrl + rueda y rueda a 1:1, original de otro tamaño, ventana, vuelta a la ajustada; eventos a mano, sin ventana)
python -m ui_helpers.widgets.smart_rule_group                  (grupo nuevo, ida y vuelta, añadir y quitar reglas, la última no se quita, señales, errores; sin ventana)
python -m ui_helpers.widgets.smart_rule_row                    (cada tipo de valor de ida y vuelta, cambios de campo y de operador, sugerencias de palabras clave, [−]; sin ventana)
python -m ui_helpers.widgets.sort_control                      (lógica del control del orden; sin ventana)
python -m ui_helpers.widgets.text_filter_row                   (opciones, pausa al escribir, la «×», set_filter; sin ventana, tarda ~1 s)
python -m ui_helpers.widgets.view_buttons                      (lógica de los botones de vista; sin ventana)
```

El modelo, el delegado, `GridActions`, la barra lateral, `MediaGridView` y los módulos (`controllers/app_modules/`) (UI) no tienen autoprueba: se prueban a mano en la aplicación (qué falta por ver, en [ESTADO.md](ESTADO.md)). La ventana de opciones se puede abrir sola, sin el resto de la aplicación ni tocar `settings.json`: `python -m ui_helpers.dialogs.settings_dialog`. Lo mismo «¿Qué contiene esta carpeta?»: `python -m ui_helpers.dialogs.folder_content_dialog`. Y la ventana «Eliminar» (con una selección mixta inventada): `python -m ui_helpers.dialogs.remove_dialog`.

**Diagnóstico de metadatos** (solo lectura):

```
python -m core.metadata.inspect_cli foto.jpg                 # etiquetas clave por grupo
python -m core.metadata.inspect_cli foto.dng --todo          # todas las etiquetas
python -m core.metadata.inspect_cli foto.heic --campos       # lo que se guardaría en la BD, columna por columna
python -m core.metadata.inspect_cli foto.nef --json salida.json
python -m core.metadata.inspect_cli video.mov --todo         # todas las etiquetas de un vídeo
python -m core.metadata.inspect_cli video.mp4 --campos       # lo que se guardaría (media_items y video_details)
```

**Diagnóstico de miniaturas** (solo lectura; deja una caché de prueba en la carpeta de salida):

```
python -m core.thumbnails.inspect_cli foto.jpg foto.heic foto.dng --salida C:\Temp\prueba
python -m core.thumbnails.inspect_cli foto.dng --detalle          # qué vistas previas trae un RAW y cuál se usa
python -m core.thumbnails.inspect_cli foto.nef --tamanos 160,480
```

**Instalar ExifTool**: Windows, ejecutable de exiftool.org renombrado a `exiftool.exe` junto a su carpeta `exiftool_files` en `tools/exiftool`; macOS, `brew install exiftool`; Linux, `sudo apt install libimage-exiftool-perl`.

**`pillow-heif`** (HEIC en las miniaturas): ya está en `requirements.txt`; vale también la versión ligera `pi-heif`.


**Consejo**: las salidas de `python -m core.metadata.inspect_cli archivo --json salida.json` de los archivos con los que se esté trabajando (cuidado: incluyen coordenadas GPS y rutas) ahorran muchas dudas sobre qué etiquetas trae cada formato.
