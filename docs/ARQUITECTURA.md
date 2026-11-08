# Arca Media — Arquitectura

> Cómo está montada la aplicación: principios, componentes, reglas de arquitectura, qué hace cada archivo (mapa) y qué se ejecuta en cada hilo.
> Índice: [INDEX.md](INDEX.md).

## Qué es y principios

Catalogador de archivos multimedia (tipo DAM) de escritorio y multiplataforma (Windows, macOS, Linux), inspirado en Lightroom, FastStone, Mp3tag y VisualDivX. Pensado para gestionar colecciones de **imágenes** (en curso), **vídeo, audio y ebooks** (previstos). Uso interno de la empresa; se empaqueta con PyInstaller.

Principios:

- **Los archivos originales no se mueven ni se modifican.** Hoy la aplicación solo los lee.
- **Un catálogo es una carpeta autónoma**: `catalogo.db` (SQLite en modo WAL) + `cache/<tipo>/` + `media_assets/{backdrops,covers,posters}/` + `export/`.
- **La referencia de metadatos es Lightroom Classic**: se leen (y más adelante se editarán) los campos que muestran sus paneles EXIF y Ubicación.
- La interfaz **nunca** toca la base de datos ni hace trabajo largo en el hilo principal.

| Componente | Uso |
|---|---|
| Python 3.14 + PySide6 (a través de `qtpy`) | Aplicación y interfaz |
| SQLite (`sqlite3`) | Catálogo; esquema versionado con migraciones |
| ExifTool 13.x (programa externo) | Lectura de EXIF, XMP e IPTC de fotos, RAW y HEIC (y vídeo/audio más adelante); vista previa incrustada de los RAW para las miniaturas |
| Pillow (+ `defusedxml`) | Miniaturas de las imágenes (decodificar, girar, convertir a sRGB, reducir); también alternativa a ExifTool para metadatos (solo JPEG, PNG, TIFF, WebP, GIF y BMP) |
| `pillow-heif` (o su versión ligera `pi-heif`) | Decodificar HEIC en las miniaturas (sin ella, los HEIC no tienen miniatura) |
| `puremagic` | Detección del tipo de archivo por contenido |
| `loguru` | Registro |
| PyInstaller | Empaquetado |


## Reglas de arquitectura

- `core/` no usa Qt, salvo `core/database/db_manager.py` y `core/workers/*`.
- Toda función que accede a la BD recibe la conexión (`conn`) como **primer parámetro**; así se envía tal cual a `CatalogDatabaseManager.execute_async` y se ejecuta en un hilo secundario con su propia conexión.
- Los trabajos largos (`add_folder`, metadatos y miniaturas) hacen `commit` **por lotes**, obedecen un `threading.Event` de cancelación y avisan del progreso.

Las reglas de trabajo y de estilo están en [CLAUDE.md](../CLAUDE.md).

## Mapa del proyecto (qué hace cada archivo)


```
main.py                              Arranque: logging, QApplication, MainWindowController
config/
  app_paths.py                       Rutas y nombre (APP_NAME, APP_VERSION), carpeta de configuración por SO
  app_config.py                      Instancia única (singleton) de la configuración: `from config.app_config import config`
  app_config_manager.py              ConfigManager: settings.json (claves: catalogo_ruta, thumbnail_size, write_user_data_to_files,
                                     main_splitter_state, show_subfolder_items, sidebar_state, inspector_metadata_preset, inspector_sections, active_module...)
  app_info.py                        Texto de ayuda en HTML (pendiente de implementar)
  app_constants.py                   Constantes, iconos (AppIcons), tamaños de miniatura, claves compartidas de settings.json
  app_logging_manager.py             setup_logging (loguru + InterceptHandler)
controllers/
  main_window_controller.py          Controlador de la ventana: catálogo activo, añadir y sincronizar carpetas, quitar ausentes, trabajos (metadatos, miniaturas y escritura de datos del usuario), regenerar miniaturas, barra de estado, ventana de opciones; conecta la cuadrícula (modelo, atajos y guardado de rating/flag/color) y crea los módulos (_configurar_modulos)
  inspector_controller.py            InspectorController: selección de la cuadrícula -> resumen en segundo plano -> inspector; módulo activo (set_module); cambios de las secciones en cola (edit_requested -> user_data_changed); «Mostrar en el Explorador»
  folder_actions.py                  FolderActions: «Quitar del catálogo...» de una carpeta de la barra lateral (cuenta, pregunta y pide al controlador el trabajo JOB_REMOVE)
  collection_actions.py              CollectionActions: une barra lateral + menú de la cuadrícula + BD para las colecciones del usuario (crear, renombrar, borrar, soltar, añadir, quitar); lo crea CatalogModule
  center_view_controller.py          CenterViewController: vista del centro del módulo activo en pantalla (página de stacked_widget_main, botones de vista, deslizador solo en la cuadrícula)
  app_modules/                       ── Módulos de la aplicación (Catálogo, Imagen, Vídeo, Audio) ── ([FLUJOS.md §11](FLUJOS.md))
    base.py                            AppModule (clase base: barra izquierda, panel derecho, qué muestra la cuadrícula, ciclo de vida) y ModuleContext
    registry.py                      ► LISTA de módulos en el orden de la toolbar (aquí se da de alta uno nuevo)
    module_host.py                     ModuleHost: toolbar de modos, barras laterales, módulo activo -> cuadrícula, estado por catálogo
    module_view_state.py               ModuleViewState: lo elegido en cada módulo (orden y vista del centro) y cómo se guarda por catálogo (claves 'orders' y 'views'); sin Qt
    center_views.py                    CenterView: vistas del centro (cuadrícula, individual, lista, mapa) con su texto emergente e icono; sin Qt
    catalog_module.py                  CatalogModule: barra CatalogSidebar (contadores, árboles, colecciones, opción de subcarpetas, estado)
    image_module.py                    ImageModule: barra ImageSidebar (contador de la biblioteca Imagen y árbol de palabras clave con recuentos), estado
    placeholder_module.py              PlaceholderModule: botón sin módulo todavía (página «próximamente»)
ui/main_window.ui, main_window.py    Interfaz de Qt Designer (main_window.py se GENERA con build_ui.py; no editar a mano).
                                     Widgets promocionados: widget_catalog_sidebar (CatalogSidebar), list_view_grid (MediaGridView),
                                     widget_organize_bar (OrganizeBar, en frame_main_bottom)
ui_helpers/                          Diálogos (ui_file_dialogs), mensajes (ui_message), barra de estado (ui_status),
                                     iconos, tema, widgets/job_progress_widget.py
  helpers/ui_icons.py                tinted_icon: SVG monocromos del .qrc teñidos al dibujarse (paleta, color fijo o hover)
  helpers/ui_info.py                 show_info_window: ventana de información con HTML (QTextBrowser)
  mixins/window_snap.py              WindowSnapMixin: ajuste magnético de la ventana a los bordes (desactivado en macOS)
  delegates/thumbnails_delegate.py   ThumbnailsDelegate: dibuja la tarjeta (miniatura o marcador por tipo, duración, nombre, estrellas, marca, fondo de color, aviso de no disponible y círculo de la selección rápida)
  models/media_roles.py              Roles compartidos modelo <-> delegado (ROLE_RATING, ROLE_FLAG, ROLE_COLOR_LABEL, ROLE_MEDIA_TYPE, ROLE_DURATION...)
  models/media_grid_model.py         MediaGridModel: lista desde la BD + miniaturas desde la caché + edición del usuario
  helpers/grid_actions.py            GridActions: atajos de teclado (estilo Lightroom) y menú contextual de la cuadrícula
  helpers/ui_color_labels.py         Colores y textos de las etiquetas de color en la interfaz
  helpers/card_marks.py              Dibujo de estrellas, marca (recuadro / X) y círculo de la selección rápida: lo comparten la tarjeta y la barra inferior
  helpers/card_glyphs.py             Dibujo del marcador de tipo (sin miniatura) y del indicador de no disponible: lo comparten la tarjeta y la vista individual
  helpers/theme_colors.py            Colores del tema con nombre por función (ThemeColors; DARK) y de las tarjetas (CardColors; DARK_CARDS), sin Qt: el ÚNICO sitio de los colores de la interfaz
  helpers/theme_qss.py               QSS de los componentes generales (barras de desplazamiento, separadores, botones, campos, menús...) a partir de un ThemeColors
  helpers/theme_style.py             ThemeStyle: QProxyStyle sobre Fusion que dibuja los botones de opción y las casillas (también las de listas y árboles) con los colores del tema
  helpers/ui_theme.py                Tema: paleta oscura de Fusion (build_palette), hoja de estilos global (QSS: la general + las piezas propias), tooltips, colores compartidos de la cuadrícula (GRID_BG, GRID_LINE) y de los iconos (SIDEBAR_ICON_COLOR, SIDEBAR_ICON_OPEN_COLOR, TOOLBAR_ICON_ACCENT_COLOR; None = paleta), TOOLBAR_MARGIN
  helpers/mode_toolbar.py            ModeToolbar: botones de modo de la toolbar, exclusivos; icono en acento al pasar el ratón y en el modo activo; páginas provisionales (la crea ModuleHost)
  dialogs/settings_dialog.py         SettingsDialog: ventana de opciones (columna de secciones + páginas; PAGES = General, Catálogo, Metadatos)
  dialogs/collection_dialog.py       CollectionDialog: "Crear colección" / "Crear conjunto" (nombre, conjunto, incluir la selección)
  dialogs/smart_collection_dialog.py SmartCollectionDialog: crear / editar una colección inteligente (reglas, recuento en vivo)
  dialogs/folder_content_dialog.py   FolderContentDialog: «¿Qué contiene esta carpeta?» al añadir una carpeta (FOLDER_CONTENT_TEXTS)
  dialogs/remove_dialog.py           RemoveDialog: «Eliminar N archivos del catálogo», como Lightroom: explicación y botones «Eliminar del disco» / «Eliminar del catálogo» (por defecto) / «Cancelar»
  sidebars/catalog_sidebar.py        CatalogSidebar: barra lateral del catálogo (Catálogo, Carpetas, Colecciones); emite GridSource
  sidebars/image_sidebar.py          ImageSidebar: barra del módulo Imagen, solo para navegar (Biblioteca - Imagen, Carpetas con imágenes y Lista de palabras clave con su filtro)
  helpers/sidebar_icons.py           load_sidebar_icons: iconos de unidades, carpetas y colecciones (barras del Catálogo e Imagen)
  widgets/keyword_checklist.py       KeywordChecklist: filtro + árbol de palabras con casillas de tres estados (editor del inspector); padres de lo asignado resaltados; menú contextual y soltar tarjetas
  widgets/recent_keywords.py         RecentKeywords: «Últimas palabras clave», 6 botones de ancho fijo (asignar / quitar con un clic)
  helpers/signal_blocker.py          blocked_signals: bloquear las señales de varios objetos Qt en un 'with'
  helpers/keyword_menu.py            Menú contextual de los árboles de palabras clave (crear, renombrar, mover, borrar, purgar): pregunta y devuelve la operación
  helpers/keyword_expansion.py       KeywordExpansion: palabras desplegadas de cada árbol (SIDEBAR, INSPECTOR), para recuperarlas al abrir
  widgets/sidebar_tree_view.py       SidebarTreeView (alto ajustado, sin scroll propio, ROLE_SOURCE / ROLE_COUNT / ROLE_EMPHASIS) + CountDelegate
  widgets/collapsible_section.py     CollapsibleSection: sección plegable con cabecera y botones ("+")
  widgets/elided_label.py            ElidedLabel: etiqueta de una línea que recorta con «…» (por la derecha, la izquierda o el centro)
  widgets/organize_bar.py            OrganizeBar: barra inferior para clasificar la selección (marcar, rechazar, estrellas, colores, selección rápida); attach(vista, modelo)
  widgets/sort_control.py            SortControl: «Orden: [campo] [↑]» a la izquierda de la barra inferior; set_options(campos, orden) y señal order_requested (no sabe nada de los módulos)
  widgets/view_buttons.py            ViewButtons: botones de vista de la barra inferior (uno por vista del módulo activo); set_views y señal view_requested (no sabe qué es una vista)
  inspector/                         ── Inspector: el panel DERECHO ── ([FLUJOS.md §12](FLUJOS.md))
    inspector_panel.py               ► InspectorPanel y DEFAULT_SECTIONS (aquí se añade una sección)
    base_section.py                    InspectorSection (title, title_for, key, modules / hidden_in / shown_in, applies_to, show_summary; datos propios con data_request / show_data; header_widget; señal edit_requested), InfoGrid (etiqueta | valor | icono; ROW_SPACING) e IconCell (icono o botón; ICON_Y_OFFSET)
    keywords_section.py                Sección «Palabras clave» (cualquier selección, menos en Imagen): las asignadas, separadas por comas, con «*» las que no tienen todos; valores con fetch_selection_keywords
    keyword_editor_section.py          «Palabras clave» en Imagen: caja con comas (KeywordTextEdit: Intro, Esc, sugerencias, Ctrl+K); cambios con apply_keyword_changes
    keyword_list_section.py            «Lista de palabras clave» en Imagen: KeywordChecklist (árbol con casillas); cambios con apply_keyword_changes
    metadata_section.py                Sección «Metadatos» (biblioteca Imagen): desplegable de vistas en la cabecera, filas de metadata_fields.py, valores con fetch_field_values
    selection_section.py               Sección «Selección»: nombre, carpeta, tamaño, fecha, contenido, biblioteca y estado
    formatting.py                      Textos: tamaños (24,3 MB), fechas por precisión, rangos, tipos («434 fotos · 20 vídeos»), origen de la fecha; metadatos: dimensiones, exposición, compensación, GPS, dirección, programa y medición (códigos EXIF), duración, fps, códec
  ► metadata_fields.py                 CAMPOS y VISTAS de la sección «Metadatos» (aquí se añaden): InspectorField (etiqueta, columnas por tipo de medio, formato), PRESETS, COMMON_HEAD, display_value
  widgets/media_grid_view.py         MediaGridView: QListView de la cuadrícula con imagen de arrastre pequeña y semitransparente
  models/media_mime.py               MIME propio del arrastre (application/x-arca-media-ids: {catalog, ids})
  helpers/ui_file_manager.py         "Mostrar en el Explorador/Finder" multiplataforma (reveal_in_file_manager) y papelera del sistema (move_to_trash, con QFile.moveToTrash)
core/
  catalog/                           ── Crear, abrir y llenar el catálogo ──
    media_types.py                     MediaType (photo, video, audio, ebook, track, other) y CACHEABLE_MEDIA_TYPES
    libraries.py                     ► BIBLIOTECAS (Library, LIBRARY_NAMES: su nombre en toda la interfaz) y tipo de contenido de las carpetas: qué se cataloga en cada una (ALLOWED_MEDIA_TYPES), biblioteca de cada archivo (library_for), detección de vídeos por el nombre (guess_video_library: patrones al principio del archivo), corrección manual (set_library, CLASSIFIABLE_MEDIA_TYPES), classify_pending_videos, count_unclassified, declaraciones con herencia (FolderContentResolver, set_folder_content, folder_content_for)
    color_labels.py                    Etiquetas de color canónicas y equivalencia con Lightroom (xmp:Label, photoshop:LabelColor); sin Qt
    media_queries.py                   SQL de la cuadrícula (fetch_grid_rows, count_grid_items); _source_condition traduce
                                       el GridSource a SQL (ÚNICO sitio; pública como source_condition); guardado de rating/flag/color (update_user_field); sin Qt
    selection_summary.py               Resumen para el inspector: fetch_selection_summary (ids) y fetch_source_summary (origen); SelectionSummary
    keywords.py                        Palabras clave en el catálogo: ensure_keyword_path, resolve_flat_keyword (sueltas), set_media_keywords (manda el archivo), keyword_tree, fetch_keyword_tree, filter_keyword_tree; edición: assign_keyword, remove_keyword, diff_keyword_text, apply_keyword_changes; sin Qt
    selection_metadata.py              Valores comunes de unos campos en la selección (común / «Varios» / vacío); FieldSource dice de qué columnas sale cada campo por tipo de medio
    grid_source.py                     GridSource (ALL / FOLDER / SMART / COLLECTION / QUICK): qué muestra la cuadrícula; inmutable. UNCLASSIFIED = «Sin clasificar»
    grid_orders.py                   ► ÓRDENES de la cuadrícula: SORT_FIELDS (campos del desplegable), GridOrder (campo + dirección; to_state / from_state), order_by_sql (NULL al final, desempate por nombre e id); sin Qt
    smart_fields.py                  ► CAMPOS de las colecciones inteligentes (grupos, secciones, tipo, columna SQL, unidades)
    smart_rules.py                     Rule, RuleSet: validación, rules_to_sql, JSON (rules_to_json / rules_from_json) y describe_rule
    system_collections.py              SYSTEM_COLLECTIONS: Clasificación (1..5), Etiqueta (Rojo..Púrpura), Marcadas, Rechazadas
    user_collections.py                Colecciones del usuario: árbol, crear, renombrar, borrar, añadir y quitar elementos
    folder_tree.py                     Árbol de carpetas con recuentos (fetch_folder_tree, build_folder_tree, sort_key natural)
    missing_items.py                   Contar y quitar del catálogo los ausentes de una carpeta (y sus miniaturas)
    folder_removal.py                  Quitar del catálogo una carpeta entera (y, si es la raíz, su ubicación): count_folder_items, remove_folder_from_catalog (trabajo; usa remove_media_items)
    media_removal.py                   Eliminar: plan_removal (qué puede ir a la papelera: no los ausentes, desconectados ni en red), remove_media_items (trabajo: quitar del catálogo y, si se pide, papelera + sidecar del RAW + entrada del .arca.json), is_network_path
    catalog_schema.py                  Esquema SQL: MIGRATIONS, apply_migrations, configure_connection
    catalog_builder.py                 CatalogBuilder: crea carpetas + catalogo.db (WAL) + esquema
    catalog_opener.py                  open_catalog: valida un catálogo existente (marca APPLICATION_ID) y aplica sus migraciones
    storage_locations.py               register_folder (ubicaciones sin solapes), locate_folder (lo mismo, solo lectura), make_relative_path, refresh_location_status
    availability.py                    check_availability: discos desconectados y archivos visibles que faltan o vuelven (sin Qt)
    scan_filter.py                     ScanFilter: descarta basura, ocultos, temporales, enlaces
    media_detector.py                  MediaTypeDetector: tipo de medio y MIME (extensión, mimetypes, puremagic)
    folder_scanner.py                  FolderScanner: recorre carpetas y entrega ScanCandidate
    catalog_writer.py                  save_candidates, mark_missing, replace_walk_issues...
    folder_importer.py                 add_folder: orquesta registrar + escanear + guardar
  database/db_manager.py             CatalogDatabaseManager: consultas asíncronas (QThreadPool, 4 hilos)
  jobs/progress.py                   JobProgress, protocolo JobResult, throttled (sin Qt)
  workers/
    job_manager.py                   JobManager: lanza/cancela trabajos con progreso (sobre db_manager)
  metadata/                          ── Leer metadatos de los archivos ── (ver core/metadata/LEEME.md)
    registry.py                      ► qué extractor lee cada tipo de medio
    processor.py                       process_pending_metadata: recorre los pendientes
    base.py                            Contrato de extractor, ExtractionResult, PROTECTED_COLUMNS
    exiftool_runner.py                 Ejecuta ExifTool por lotes; find_exiftool, find_sidecars
    exiftool_extractor.py              Extractor genérico (lotes, sidecars, lista de campos, reglas)
    field_spec.py                      FieldSpec, common()/detail(), conversores, parse_datetime
    keyword_tags.py                    read_keywords: palabras clave de las etiquetas de ExifTool (lr:HierarchicalSubject, dc:Subject, IPTC:Keywords) -> FileKeywords
    image/fields.py                  ► LISTA de campos de imagen (aquí se añaden) + IMAGE_FIELDS_VERSION
    image/rules.py                     Reglas: fecha de captura, orientación/tamaño, flash, GPS
    image/extractor.py                 ImageExtractor (ExifTool)
    image/pillow_extractor.py          Alternativa sin ExifTool
    video/fields.py                  ► LISTA de campos de vídeo (etiquetas sin grupo = cualquier grupo) + VIDEO_FIELDS_VERSION
    video/rules.py                     Reglas: fecha de captura (hora local de Keys/XML/H264/XMP, o QuickTime en UTC -> local), tamaño con rotación, GPS
    video/extractor.py                 VideoExtractor (ExifTool; tabla video_details)
    image/_fixtures.py                 Datos reales de ExifTool para las autopruebas
    track/gpx_reader.py                read_gpx -> GpxSummary (distancia 2D haversine, desnivel con umbral, fechas, caja, actividad)
    track/extractor.py                 TrackExtractor (GPX -> track_details; TRACK_EXTRACTOR_VERSION = 2)
    track/inspect_cli.py               Diagnóstico de GPX (resumen y desnivel con varios umbrales)
    inspect_cli.py                     Herramienta de diagnóstico (qué lee ExifTool / qué se guardaría; --campos elige imagen o vídeo según el archivo)
  userdata/                          ── Datos del usuario fuera del catálogo ── (ver core/userdata/LEEME.md)
    policy.py                        ► destino de cada formato: XMP incrustado, sidecar .xmp o archivo de carpeta
    folder_file.py                     Archivo de carpeta '.arca.json' (lectura, escritura atómica, copia .bak)
    xmp_writer.py                      Escritura en XMP con ExifTool (solo los campos pendientes; comprueba releyendo)
    sync.py                            write_pending_user_data (trabajo) y la lectura al importar (apply_file_user_data, apply_folder_files)
  thumbnails/                        ── Generar y guardar las miniaturas ── (ver core/thumbnails/LEEME.md)
    sizes.py                           ThumbnailSize: 160 / 480 / 1200 / 2560 px (lado largo) y calidad JPEG
    cache.py                           ThumbnailCache: ruta derivada del id, escritura atómica, resolve(); ThumbnailStorageError
    imaging.py                         Orientación, modos de color, conversión a sRGB, escalera sin ampliar
    generator.py                       generate_thumbnails (UN archivo) y THUMBNAIL_VERSION
    registry.py                      ► qué origen lee cada tipo de medio y extensión
    sources/                           base.py, pillow_source.py, heif_source.py (HEIC), raw_preview_source.py (RAW, vía ExifTool)
    job.py                             generate_pending_thumbnails (trabajo) e invalidate_thumbnails (regenerar a demanda)
    inspect_cli.py                     Diagnóstico: genera miniaturas de archivos reales y las cuenta
tools/exiftool/                      ExifTool (no se versiona; ver tools/exiftool/LEEME.txt)
scripts/build_ui.py                  Compila ui/*.ui con pyside6-uic y resources/recursos.qrc con pyside6-rcc
ruff.toml                            Configuración de Ruff (excluye tests/ y ui/)
CLAUDE.md                            Reglas de trabajo para la IA (Claude Code): cómo leer el proyecto, convenciones y qué actualizar
docs/                                Esta documentación (empieza por docs/INDEX.md)
```

> El REPOMIX no incluye `build_ui.py`, `resources/` (SVG y `.qrc`) ni `tools/`: si hace falta revisarlos, hay que adjuntarlos aparte.


## Qué ocurre en cada hilo


| Hilo principal | Hilo secundario |
|---|---|
| Menús, diálogos, barra de estado, widgets, señales, temporizador de escritura | `add_folder`, `process_pending_metadata`, `generate_pending_thumbnails` (con su grupo de hilos de generación), `write_pending_user_data`, ExifTool (subproceso), toda la BD, y la lectura de miniaturas de la cuadrícula (pool propio del modelo, solo lee un JPEG y devuelve una `QImage`) |
