# Arca Media — Arquitectura

> Cómo está montada la aplicación: principios, componentes, reglas de arquitectura, qué hace cada archivo (mapa) y qué se ejecuta en cada hilo.
> Índice: [INDEX.md](INDEX.md).

## Qué es y principios

Catalogador de archivos multimedia (tipo DAM) de escritorio y multiplataforma (Windows, macOS, Linux), inspirado en Lightroom, FastStone, Mp3tag y VisualDivX. Pensado para gestionar colecciones de **imágenes** (en curso), **vídeo, audio y ebooks** (previstos). Uso interno de la empresa; se empaquetará con PyInstaller (pendiente: [PENDIENTE.md](PENDIENTE.md), C.9).

Principios:

- **Los archivos originales no se mueven ni se modifican.** Las únicas excepciones: escribir la valoración, la marca, el color, las palabras clave y los metadatos descriptivos editados en la aplicación (título, pie de ilustración, creador, copyright y ubicación) con las reglas de `core/userdata/` (XMP incrustado, sidecar `.xmp` o `.arca.json`; ver su `LEEME.md`), y enviar a la papelera lo que el usuario pide eliminar del disco.
- **Un catálogo es una carpeta autónoma**: `catalogo.db` (SQLite en modo WAL) + `cache/<tipo>/` + `media_assets/{backdrops,covers,posters}/` + `export/`.
- **La referencia de metadatos es Lightroom Classic**: se leen los campos que muestran sus paneles EXIF y Ubicación.
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
| PyInstaller | Empaquetado (pendiente y sin probar; no está en `requirements.txt`) |


## Reglas de arquitectura

Las reglas (qué puede usar Qt, cómo se accede a la base de datos, migraciones, archivos del usuario, colores, tamaño de las clases) están en un solo sitio: [CLAUDE.md](../CLAUDE.md), «Reglas de arquitectura», junto a las de trabajo y de estilo. Aquí, solo el porqué de dos de ellas:

- La conexión (`conn`) va como **primer parámetro** para que la función se envíe tal cual a `CatalogDatabaseManager.execute_async` y se ejecute en un hilo secundario con su propia conexión.
- Los trabajos largos (`add_folder`, metadatos, miniaturas, escritura de los datos del usuario y eliminar) hacen `commit` **por lotes** para no bloquear la escritura al resto y conservar lo hecho si se cancelan (`threading.Event`); avisan del progreso.

## Mapa del proyecto (qué hace cada archivo)


```
main.py                              Arranque: logging, QApplication, MainWindowController
config/
  app_paths.py                       Rutas y nombre (APP_NAME, APP_VERSION), carpeta de configuración por SO
  app_config.py                      Instancia única (singleton) de la configuración: `from config.app_config import config`
  app_config_manager.py              ConfigManager: settings.json (claves: catalogo_ruta, thumbnail_size, write_user_data_to_files,
                                     main_splitter_state, show_subfolder_items, sidebar_state, inspector_metadata_preset, inspector_sections, active_module, filter_metadata_height, filter_presets, confirm_multi_edit,
                                     last_add_folder_parent, window_geometry; todas, con su valor por defecto, en DEFAULTS)
  app_info.py                        Texto de ayuda en HTML (pendiente de implementar; hoy no lo usa nadie)
  app_constants.py                   Constantes, iconos (AppIcons), tamaños de miniatura, claves compartidas de settings.json
  app_logging_manager.py             setup_logging (loguru + InterceptHandler)
controllers/
  main_window_controller.py          Controlador de la ventana: catálogo activo, añadir y sincronizar carpetas, quitar ausentes, trabajos (metadatos, miniaturas y escritura de datos del usuario), regenerar miniaturas, barra de estado, ventana de opciones; conecta la cuadrícula (modelo, atajos y guardado de rating/flag/color) y crea los módulos (_configurar_modulos)
  inspector_controller.py            InspectorController: selección de la cuadrícula -> resumen en segundo plano -> inspector; cambios de las secciones en cola (edit_requested -> user_data_changed); flecha «ver sus fotos» (navigate_requested); lo desplegado del árbol del inspector (save_state / restore_state); «Mostrar en el Explorador»
  folder_actions.py                  FolderActions: «Quitar del catálogo...» de una carpeta de la barra lateral (cuenta, pregunta y pide al controlador el trabajo JOB_REMOVE)
  collection_actions.py              CollectionActions: une barra lateral + menú de la cuadrícula + BD para las colecciones del usuario (crear, renombrar, borrar, soltar, añadir, quitar); lo crea CatalogModule
  filter_controller.py               FilterController: barra de filtros <-> filtro del módulo activo (ModuleHost.set_filter / filter_changed); Ctrl+L; oculta la franja en la vista individual
  filter_preset_controller.py        FilterPresetController: desplegable de ajustes personalizados <-> lista (settings.json, filter_presets) y filtro del módulo activo; pide el nombre al guardar y si se reemplaza
  metadata_filter_controller.py      MetadataFilterController: panel «Metadatos» <-> recuentos en segundo plano (columnas de partida del módulo, solo lo que cambia, respuestas tardías fuera, alto guardado)
  center_view_controller.py          CenterViewController: vista del centro del módulo activo en pantalla (página de stacked_widget_main, botones de vista, deslizador solo en la cuadrícula) y navegación (doble clic / Intro, Esc / G, flechas, Inicio, Fin; un solo archivo seleccionado en la vista individual)
  app_modules/                       ── Módulos de la aplicación (Catálogo, Imagen, Vídeo, Audio) ── ([FLUJOS.md §11](FLUJOS.md))
    base.py                            AppModule (clase base: barra izquierda, qué muestra la cuadrícula, orden, vistas, tipos y columnas de partida del filtro, ciclo de vida) y ModuleContext
    registry.py                      ► LISTA de módulos en el orden de la toolbar (aquí se da de alta uno nuevo)
    module_host.py                     ModuleHost: toolbar de modos, barras laterales, módulo activo -> cuadrícula, estado por catálogo
    module_view_state.py               ModuleViewState: lo elegido en cada módulo (orden, vista del centro y filtro) y cómo se guarda por catálogo (claves 'orders', 'views' y 'filters'); sin Qt
    center_views.py                    CenterView: vistas del centro (cuadrícula, individual, lista, mapa) con su texto emergente e icono; sin Qt
    catalog_module.py                  CatalogModule: barra CatalogSidebar (contadores, árboles, colecciones, opción de subcarpetas, estado)
    image_module.py                    ImageModule: barra ImageSidebar (Biblioteca - Imagen con su selección rápida, carpetas con imágenes y árbol de palabras clave con recuentos), estado
    placeholder_module.py              PlaceholderModule: botón sin módulo todavía (página «próximamente»)
ui/main_window.ui, main_window.py    Interfaz de Qt Designer (main_window.py se GENERA con build_ui.py; no editar a mano).
                                     Widgets promocionados: widget_catalog_sidebar (CatalogSidebar), list_view_grid (MediaGridView),
                                     widget_single_view (SingleMediaView), widget_filter_bar (FilterBar, en frame_main_top) y, en
                                     frame_main_bottom, widget_view_buttons (ViewButtons), widget_sort_control (SortControl) y
                                     widget_organize_bar (OrganizeBar)
ui_helpers/                          Diálogos (ui_file_dialogs), mensajes (ui_message), barra de estado (ui_status),
                                     iconos, tema, widgets/job_progress_widget.py
  helpers/ui_file_dialogs.py         Diálogos de archivos y carpetas (QFileDialog): select_file, select_files, select_folder, save_file
  helpers/ui_message.py              MessageBoxHelper: avisos, errores y preguntas (QMessageBox); question_with_checkbox («No volver a mostrar»)
  helpers/ui_status.py               message_bar: mensaje con icono teñido y temporizador en la barra de estado
  helpers/ui_icons.py                tinted_icon: SVG monocromos del .qrc teñidos al dibujarse (paleta, color fijo o hover); menu_icon, para las opciones de los menús
  helpers/ui_info.py                 show_info_window: ventana de información con HTML (QTextBrowser); hoy no la usa nadie
  mixins/window_snap.py              WindowSnapMixin: ajuste magnético de la ventana a los bordes (desactivado en macOS)
  delegates/thumbnails_delegate.py   ThumbnailsDelegate: dibuja la tarjeta (miniatura o marcador por tipo, duración, nombre, estrellas, marca, fondo de color, aviso de no disponible y círculo de la selección rápida)
  models/media_roles.py              Roles compartidos modelo <-> delegado (ROLE_RATING, ROLE_FLAG, ROLE_COLOR_LABEL, ROLE_MEDIA_TYPE, ROLE_DURATION...)
  models/media_grid_model.py         MediaGridModel: lista desde la BD + miniaturas desde la caché + edición del usuario
  models/full_image_loader.py        FullImageLoader: miniatura grande (2560 px o la mayor que haya) de la caché en un hilo propio, con memoria de 5 imágenes y precarga; para la vista individual
  helpers/grid_actions.py            GridActions: atajos de teclado (estilo Lightroom) y menú contextual de la cuadrícula
  helpers/ui_color_labels.py         Etiquetas de color en la interfaz: su color (del tema, MARK_COLORS), textos, mezcla (blend) e icono de menú
  helpers/card_marks.py              Dibujo de estrellas, marca (recuadro / X) y círculo de la selección rápida: lo comparten la tarjeta y la barra inferior
  helpers/card_glyphs.py             Dibujo del marcador de tipo (sin miniatura; draw_type_glyph, solo el dibujo, para la fila «Atributos») y del indicador de no disponible, y el velo de rechazada o no disponible (veil): lo comparten la tarjeta y la vista individual
  helpers/theme_colors.py            Colores del tema con nombre por función (ThemeColors; DARK), de las tarjetas y lo que va encima de la imagen (CardColors; DARK_CARDS) y de las marcas de clasificación (MarkColors; DARK_MARKS), sin Qt: el ÚNICO sitio de los colores de la interfaz
  helpers/theme_qss.py               QSS de los componentes generales (barras de desplazamiento, separadores, botones, campos, menús...) a partir de un ThemeColors
  helpers/theme_style.py             ThemeStyle: QProxyStyle sobre Fusion que dibuja los botones de opción y las casillas (también las de listas y árboles) con los colores del tema
  helpers/ui_theme.py                Tema: los juegos activos (COLORS, CARD_COLORS, MARK_COLORS), paleta oscura de Fusion (build_palette), hoja de estilos global (QSS: la general + las piezas propias), tooltips, colores compartidos de la cuadrícula (GRID_BG, GRID_LINE) y de los iconos (SIDEBAR_ICON_COLOR, SIDEBAR_ICON_OPEN_COLOR, TOOLBAR_ICON_ACCENT_COLOR; None = paleta), TOOLBAR_MARGIN
  helpers/mode_toolbar.py            ModeToolbar: botones de modo de la toolbar, exclusivos; icono en acento solo en el modo activo (al pasar el ratón cambia la caja); páginas provisionales (la crea ModuleHost)
  dialogs/settings_dialog.py         SettingsDialog: ventana de opciones (columna de secciones + páginas; PAGES = General, Catálogo, Metadatos: escribir en los archivos y el aviso «Edición múltiple»)
  dialogs/collection_dialog.py       CollectionDialog: "Crear colección" / "Crear conjunto" (nombre, conjunto, incluir la selección)
  dialogs/smart_collection_dialog.py SmartCollectionDialog: crear / editar una colección inteligente (reglas y grupos de reglas, recuento en vivo)
  dialogs/filter_presets_dialog.py   FilterPresetsDialog: «Gestionar ajustes personalizados» (ordenar, cambiar el nombre, eliminar, restaurar los de fábrica); devuelve la lista nueva
  dialogs/folder_content_dialog.py   FolderContentDialog: «¿Qué contiene esta carpeta?» al añadir una carpeta (FOLDER_CONTENT_TEXTS)
  dialogs/remove_dialog.py           RemoveDialog: «Eliminar N archivos del catálogo», como Lightroom: explicación y botones «Eliminar del disco» / «Eliminar del catálogo» (por defecto) / «Cancelar»
  sidebars/catalog_sidebar.py        CatalogSidebar: barra lateral del catálogo (Catálogo, Carpetas, Colecciones); emite GridSource
  sidebars/image_sidebar.py          ImageSidebar: barra del módulo Imagen, solo para navegar (Biblioteca - Imagen, Carpetas con imágenes y Lista de palabras clave con su filtro)
  helpers/sidebar_icons.py           load_sidebar_icons: iconos de unidades, carpetas y colecciones (barras del Catálogo e Imagen), con sus variantes ':open' y ':menu'
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
  widgets/filter_bar.py              FilterBar: barra de filtros de la franja superior («Filtro activo:», pestañas, «Ninguno», desplegable de ajustes, candado; paneles debajo); solo muestra y avisa
  widgets/filter_preset_button.py    FilterPresetButton: el desplegable de los ajustes personalizados (nombre del que coincide, «Personalizado» o, con «Ninguno», «Sin filtro»; acciones arriba y lista con ✓); solo muestra y avisa
  widgets/attribute_filter_row.py    AttributeFilterRow: fila de «Atributos» de la barra de filtros (marca, ≥/≤/= y estrellas, colores y «sin color», selección rápida, tipos del módulo); iconos dibujados; avisa en el acto
  widgets/metadata_column.py         MetadataColumnWidget: una columna de «Metadatos» de la barra de filtros (menú de campos y engranaje; valores con recuentos, fechas en árbol, selección); value_text
  widgets/metadata_filter_panel.py   MetadataFilterPanel: el panel «Metadatos» (de 1 a 6 columnas, añadir y quitar, borde para el alto); columns_to_refresh (qué recontar)
  widgets/text_filter_row.py         TextFilterRow: fila de «Texto» de la barra de filtros (campo, operador, caja; avisa tras 300 ms al escribir)
  widgets/smart_rule_row.py          SmartRuleRow: una regla del editor de colecciones inteligentes ([campo ▾] [operador ▾] [valor] [−]; menú de campos por grupos y secciones, control del valor según el tipo); DEFAULT_RULE
  widgets/smart_rule_group.py        SmartRuleGroup: un grupo de reglas del editor (cabecera con su «todas / alguna de» y «−», sus SmartRuleRow, su «+ Añadir regla»); MATCH_CHOICES
  widgets/view_buttons.py            ViewButtons: botones de vista de la barra inferior (uno por vista del módulo activo); set_views y señal view_requested (no sabe qué es una vista)
  widgets/single_media_view.py       SingleMediaView: vista individual (archivo actual de la cuadrícula, mismo modelo y selección): imagen ajustada y nítida, marcador sin miniatura, aviso de no disponible, «No hay archivos»
  inspector/                         ── Inspector: el panel DERECHO ── ([FLUJOS.md §12](FLUJOS.md))
    inspector_panel.py               ► InspectorPanel y DEFAULT_SECTIONS (aquí se añade una sección)
    base_section.py                    InspectorSection (title, title_for, key, libraries / fits, applies_to, show_summary; datos propios con data_request / show_data; header_widget; señal edit_requested), InfoGrid (etiqueta | valor | icono; ROW_SPACING) e IconCell (icono o botón; ICON_Y_OFFSET)
    keywords_section.py                Sección «Palabras clave» de solo lectura (las asignadas, separadas por comas, con «*» las que no tienen todos). Sin usar desde el 08/11/2026: el editor la sustituye en todos los módulos
    keyword_editor_section.py          «Palabras clave» (con cualquier selección, en todos los módulos): caja con comas (KeywordTextEdit: Intro, Esc, sugerencias, Ctrl+K) y «Últimas palabras clave»; cambios con apply_keyword_changes
    keyword_list_section.py            «Lista de palabras clave» (siempre): KeywordChecklist (árbol con casillas, flecha «ver sus fotos», soltar tarjetas); cambios con apply_keyword_changes
    metadata_section.py                Sección «Metadatos» (biblioteca Imagen): desplegable de vistas en la cabecera, filas de metadata_fields.py, valores con fetch_field_values; los campos de EDITABLE_KEYS, con cajas (cambios con update_metadata_fields; aviso «Edición múltiple»)
    editable_row.py                    EditableValue: caja editable de una línea o de varias (Intro, Esc, Tab, Mayús+Intro; «Varios» como Lightroom; señal committed)
    selection_section.py               Sección «Selección»: nombre, carpeta, tamaño, fecha, contenido, biblioteca y estado
    formatting.py                      Textos: tamaños (24,3 MB), fechas por precisión, rangos, tipos («434 fotos · 20 vídeos»), origen de la fecha; metadatos: dimensiones, exposición, compensación, GPS, dirección, programa y medición (códigos EXIF), duración, fps, códec
  ► metadata_fields.py                 CAMPOS y VISTAS de la sección «Metadatos» (aquí se añaden): InspectorField (etiqueta, columnas por tipo de medio, formato), PRESETS, COMMON_HEAD, display_value; EDITABLE_KEYS (los que se editan) y editor_value
  widgets/media_grid_view.py         MediaGridView: QListView de la cuadrícula con imagen de arrastre pequeña y semitransparente
  models/media_mime.py               MIME propio del arrastre (application/x-arca-media-ids: {catalog, ids})
  helpers/ui_file_manager.py         "Mostrar en el Explorador/Finder" multiplataforma (reveal_in_file_manager) y papelera del sistema (move_to_trash, con QFile.moveToTrash)
core/
  catalog/                           ── Crear, abrir y llenar el catálogo ──
    media_types.py                     MediaType (photo, video, audio, ebook, track, other) y CACHEABLE_MEDIA_TYPES
    libraries.py                     ► BIBLIOTECAS (Library, LIBRARY_NAMES: su nombre en toda la interfaz) y tipo de contenido de las carpetas: qué se cataloga en cada una (ALLOWED_MEDIA_TYPES), biblioteca de cada archivo (library_for), detección de vídeos por el nombre (guess_video_library: patrones al principio del archivo), corrección manual (set_library, CLASSIFIABLE_MEDIA_TYPES), classify_pending_videos, count_unclassified, declaraciones con herencia (FolderContentResolver, set_folder_content, folder_content_for)
    color_labels.py                    Etiquetas de color canónicas y equivalencia con Lightroom (xmp:Label, photoshop:LabelColor); sin Qt
    media_queries.py                   SQL de la cuadrícula (fetch_grid_rows, count_grid_items); _source_condition traduce
                                       el GridSource a SQL (ÚNICO sitio; pública como source_condition); guardado de rating/flag/color (update_user_field) y de los metadatos editados (update_metadata_fields); sin Qt
    selection_summary.py               Resumen para el inspector: fetch_selection_summary (ids) y fetch_source_summary (origen); SelectionSummary
    keywords.py                        Palabras clave en el catálogo: ensure_keyword_path, resolve_flat_keyword (sueltas), set_media_keywords (manda el archivo), keyword_tree, fetch_keyword_tree, filter_keyword_tree; edición: assign_keyword, remove_keyword, diff_keyword_text, apply_keyword_changes; sin Qt
    selection_metadata.py              Valores comunes de unos campos en la selección (común / «Varios» / vacío); FieldSource dice de qué columnas sale cada campo por tipo de medio
    grid_source.py                     GridSource (ALL / FOLDER / SMART / COLLECTION / QUICK / KEYWORD): qué muestra la cuadrícula; inmutable; source_to_dict / source_from_dict. UNCLASSIFIED = «Sin clasificar»
    grid_filter.py                   ► FILTRO de la barra de filtros: GridFilter (pestañas encendidas, candado, filas de Texto y Atributos, columnas de Metadatos: MetadataFilter, metadata_rule) -> rule_sets() (conjuntos de reglas con AND, que se suman al origen); filter_to_dict / filter_from_dict; sin Qt
    filter_presets.py                  AJUSTES PERSONALIZADOS de la barra de filtros: FilterPreset (nombre + GridFilter), los de fábrica, la lista de settings.json (filter_presets), cuál coincide con el filtro, cuáles valen para un módulo, elegir y restaurar
    grid_orders.py                   ► ÓRDENES de la cuadrícula: SORT_FIELDS (campos del desplegable), GridOrder (campo + dirección; to_state / from_state), order_by_sql (NULL al final, desempate por nombre e id); sin Qt
    smart_fields.py                  ► CAMPOS de las colecciones inteligentes (grupos, secciones, tipo, columna SQL, unidades; browse = también columna de «Metadatos»)
    metadata_values.py                 Valores y recuentos de una columna de «Metadatos» (fetch_metadata_values: cascada, fechas en árbol, lo elegido a 0); sin Qt
    smart_rules.py                     Rule, RuleSet (con grupos de un nivel): validación, rules_to_sql, JSON (rules_to_json / rules_from_json) y describe_rule(s)
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
    editable_fields.py               ► metadatos descriptivos editables: columna, bit de pendiente, etiquetas XMP y antiguas, clave del .arca.json
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
    _testing.py                        Utilidades solo para las autopruebas de core/thumbnails (perfiles ICC de prueba)
tools/exiftool/                      ExifTool (no se versiona; ver tools/exiftool/LEEME.txt)
scripts/build_ui.py                  Compila ui/*.ui con pyside6-uic y resources/recursos.qrc con pyside6-rcc (genera resources/recursos_rc.py)
scripts/export_qtbase_es.py          Copia la traducción al español de Qt (qtbase_es.qm) a resources/locales
resources/                           recursos.qrc (lista de iconos e imágenes), images/ (SVG), icons/ (icono de la aplicación),
                                     locales/qtbase_es.qm (traducción de Qt) y recursos_rc.py (se GENERA con build_ui.py; no editar)
repomix.config.json                  Qué entra en el REPOMIX (ver la nota de abajo)
.gitattributes                       Finales de línea LF (ver TRAMPAS.md)
requirements.txt                     Dependencias de .venv (salida de 'pip freeze', en UTF-8; ver PRUEBAS.md)
ruff.toml                            Configuración de Ruff (excluye tests/ y ui/)
CLAUDE.md                            Reglas de trabajo para la IA (Claude Code): cómo leer el proyecto, convenciones y qué actualizar
docs/                                Esta documentación (empieza por docs/INDEX.md)
```

> El REPOMIX no incluye `scripts/` (`build_ui.py`, `export_qtbase_es.py`), `resources/` (SVG y `.qrc`), `tools/` ni el `ui/main_window.py` generado (`repomix.config.json`): si hace falta revisarlos, hay que adjuntarlos aparte.


## Qué ocurre en cada hilo


| Hilo principal | Hilo secundario |
|---|---|
| Menús, diálogos, barra de estado, widgets, señales, temporizador de escritura | `add_folder`, `process_pending_metadata`, `generate_pending_thumbnails` (con su grupo de hilos de generación), `write_pending_user_data`, `remove_media_items`, ExifTool (subproceso), toda la BD, la lectura de miniaturas de la cuadrícula (pool propio del modelo, solo lee un JPEG y devuelve una `QImage`) y la imagen grande de la vista individual (`FullImageLoader`, un hilo propio) |
