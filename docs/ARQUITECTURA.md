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
main.py                              Arranque: logging, esquema del mapa (antes de QApplication), QApplication, MainWindowController
config/
  app_paths.py                       Rutas y nombre (APP_NAME, APP_VERSION), carpeta de configuración por SO
  app_config.py                      Instancia única (singleton) de la configuración: `from config.app_config import config`
  app_config_manager.py              ConfigManager: settings.json (claves: catalogo_ruta, thumbnail_size, write_user_data_to_files,
                                     main_splitter_state, show_subfolder_items, sidebar_state, inspector_metadata_preset, inspector_sections, active_module, filter_metadata_height, filter_presets, confirm_multi_edit,
                                     last_add_folder_parent, map_layer, map_user_layers, map_cache_mb, map_filmstrip, gpu_rendering, section_layout, window_geometry; todas, con su valor por defecto, en DEFAULTS)
  app_info.py                        Texto de ayuda en HTML (pendiente de implementar; hoy no lo usa nadie)
  app_constants.py                   Constantes, iconos (AppIcons), tamaños de miniatura, claves compartidas de settings.json
  app_logging_manager.py             setup_logging (loguru + InterceptHandler)
controllers/
  main_window_controller.py          Controlador de la ventana: catálogo activo, añadir y sincronizar carpetas, quitar ausentes, trabajos (metadatos, miniaturas y escritura de datos del usuario), regenerar miniaturas, barra de estado, ventana de opciones; conecta la cuadrícula (modelo, atajos y guardado de rating/flag/color) y crea los módulos (_configurar_modulos)
  inspector_controller.py            InspectorController: selección de la cuadrícula -> resumen en segundo plano -> inspector; cambios de las secciones en cola (edit_requested -> user_data_changed; request_edit con on_done: el resultado, para deshacer); flecha «ver sus fotos» (navigate_requested); lo desplegado del árbol del inspector (save_state / restore_state); «Mostrar en el Explorador»
  folder_actions.py                  FolderActions: «Quitar del catálogo...» de una carpeta de la barra lateral (cuenta, pregunta y pide al controlador el trabajo JOB_REMOVE)
  collection_actions.py              CollectionActions: une barra lateral + menú de la cuadrícula + BD para las colecciones del usuario (crear, renombrar, borrar, soltar, añadir, quitar); lo crea CatalogModule
  filter_controller.py               FilterController: barra de filtros <-> filtro del módulo activo (ModuleHost.set_filter / filter_changed); Ctrl+L; oculta la franja en la vista individual
  filter_preset_controller.py        FilterPresetController: desplegable de ajustes personalizados <-> lista (settings.json, filter_presets) y filtro del módulo activo; pide el nombre al guardar y si se reemplaza
  metadata_filter_controller.py      MetadataFilterController: panel «Metadatos» <-> recuentos en segundo plano (columnas de partida del módulo, solo lo que cambia, respuestas tardías fuera, alto guardado)
  undo_history.py                    UndoHistory: deshacer en toda la aplicación (Ctrl+Z en la ventana; pasos UndoStep con su descripción y su forma de deshacerse; se vacía al cerrar el catálogo). Hoy lo llena el mapa
  map_controller.py                  MapController: la vista «Mapa» (lo mismo que la cuadrícula, pedido con map_queries solo con el mapa a la vista; selección en los dos sentidos; encuadre al cambiar de origen; aviso de lo que no sale; desplegable de la capa en la barra inferior, guardado en settings.json; doble clic → vista individual; capas propias, tope de la caché al crear el mapa; la tira de fotos: botón de la barra inferior y F6, si se ve y su alto en settings.json, doble clic → vista individual, la actual a la vista; ubicar fotos soltándolas y mover las ubicadas donde el módulo lo permite, por la cola del inspector, con confirmación a partir de 50; «Quitar la ubicación» con el botón derecho; cada cambio, en el historial de deshacer); attach / detach, set_edit_queue, set_undo_history, refresh (tras un cambio del inspector), apply_settings
  center_view_controller.py          CenterViewController: vista del centro del módulo activo en pantalla (página de stacked_widget_main, botones de vista, deslizador solo en la cuadrícula) y navegación (doble clic / Intro, G, M, Esc a la vista de la que se vino, flechas, Inicio, Fin, rueda; un solo archivo seleccionado en la vista individual; el teclado del mapa, en su página y en la tira: watch_map_widget); al elegir algo en una barra (source_chosen), el teclado al centro y la primera foto seleccionada; al recargar, siempre un archivo actual (el que recuerda el módulo, la selección que había o el que ocupa su lugar)
  app_modules/                       ── Módulos de la aplicación (Catálogo, Imagen, Vídeo, Audio) ── ([FLUJOS.md §11](FLUJOS.md))
    base.py                            AppModule (clase base: barra izquierda, qué muestra la cuadrícula, orden, vistas, qué permite su mapa (map_options), tipos y columnas de partida del filtro, ciclo de vida) y ModuleContext
    registry.py                      ► LISTA de módulos en el orden de la toolbar (aquí se da de alta uno nuevo)
    module_host.py                     ModuleHost: toolbar de modos, barras laterales, módulo activo -> cuadrícula, estado por catálogo; source_chosen (el usuario elige otra cosa en una barra); el archivo actual de cada módulo (set_current_media)
    module_view_state.py               ModuleViewState: lo elegido en cada módulo (orden, vista del centro, filtro y archivo actual) y cómo se guarda por catálogo (claves 'orders', 'views', 'filters' y 'current'); sin Qt
    center_views.py                    CenterView: vistas del centro (cuadrícula, individual, lista, mapa) con su texto emergente e icono; MapOptions (qué permite el mapa de un módulo: ubicar fotos); sin Qt
    catalog_module.py                  CatalogModule: barra CatalogSidebar (contadores, árboles, colecciones, opción de subcarpetas, estado)
    image_module.py                    ImageModule: barra ImageSidebar (Biblioteca - Imagen con su selección rápida, carpetas con imágenes, fechas y árbol de palabras clave con recuentos), estado; vistas: cuadrícula, individual y mapa (en el que se ubican fotos)
    placeholder_module.py              PlaceholderModule: botón sin módulo todavía (página «próximamente»)
ui/main_window.ui, main_window.py    Interfaz de Qt Designer (main_window.py se GENERA con build_ui.py; no editar a mano).
                                     Widgets promocionados: widget_catalog_sidebar (CatalogSidebar), list_view_grid (MediaGridView),
                                     widget_single_view (SingleMediaView), widget_filter_bar (FilterBar, en frame_main_top) y, en
                                     frame_main_bottom, widget_view_buttons (ViewButtons), widget_sort_control (SortControl) y
                                     widget_organize_bar (OrganizeBar)
ui_helpers/                          Diálogos (ui_file_dialogs), mensajes (ui_message), barra de estado (ui_status),
                                     iconos, tema, widgets/job_progress_widget.py
  helpers/ui_file_dialogs.py         Diálogos de archivos y carpetas (QFileDialog): select_file, select_files, select_folder, save_file
  helpers/ui_message.py              MessageBoxHelper: avisos, errores y preguntas (QMessageBox); question_with_checkbox («No volver a mostrar»); details (texto largo en «Mostrar los detalles…»)
  helpers/ui_status.py               message_bar: mensaje con icono teñido y temporizador en la barra de estado
  helpers/ui_icons.py                tinted_icon: SVG monocromos del .qrc teñidos al dibujarse (paleta, color fijo o hover); menu_icon, para las opciones de los menús
  helpers/ui_info.py                 show_info_window: ventana de información con HTML (QTextBrowser); hoy no la usa nadie
  mixins/window_snap.py              WindowSnapMixin: ajuste magnético de la ventana a los bordes (desactivado en macOS)
  delegates/thumbnails_delegate.py   ThumbnailsDelegate: dibuja la tarjeta (o, con 'compact', solo la imagen, sin la banda y con la chincheta de lo que tiene ubicación: la de la tira del mapa; miniatura o marcador por tipo, duración, nombre, estrellas, marca, fondo de color, aviso de no disponible y círculo de la selección rápida)
  models/media_roles.py              Roles compartidos modelo <-> delegado (ROLE_RATING, ROLE_FLAG, ROLE_COLOR_LABEL, ROLE_MEDIA_TYPE, ROLE_DURATION...)
  models/media_grid_model.py         MediaGridModel: lista desde la BD + miniaturas desde la caché + edición del usuario; set_located (quién tiene coordenadas, sin recargar); request_media_file (ruta y dimensiones de UN archivo, en segundo plano)
  models/full_image_loader.py        FullImageLoader: miniatura grande (2560 px o la mayor que haya) de la caché en un hilo propio, con memoria de 5 imágenes y precarga; para la vista individual
  models/original_image_loader.py    OriginalImageLoader: el ORIGINAL de una foto (load_full_image) en un hilo propio, solo el último pedido, en RGB32; para la vista individual a 1:1
  helpers/grid_actions.py            GridActions: atajos de teclado (estilo Lightroom) y menú contextual de la cuadrícula
  helpers/ui_color_labels.py         Etiquetas de color en la interfaz: su color (del tema, MARK_COLORS), textos, mezcla (blend) e icono de menú
  helpers/card_marks.py              Dibujo de estrellas, marca (recuadro / X) y círculo de la selección rápida: lo comparten la tarjeta y la barra inferior
  helpers/card_glyphs.py             Dibujo de la chincheta de la ubicación (draw_location_pin), del marcador de tipo (sin miniatura; draw_type_glyph, solo el dibujo, para la fila «Atributos») y del indicador de no disponible, y el velo de rechazada o no disponible (veil): lo comparten la tarjeta y la vista individual
  helpers/zoom_geometry.py           Cuentas del zoom 1:1 de la vista individual (sin Qt): zoomed_size, can_zoom, relative_point, offset_keeping, clamp_offset (sin huecos, centrada si cabe, en píxeles físicos enteros)
  helpers/theme_colors.py            Colores del tema con nombre por función (ThemeColors; DARK), de las tarjetas y lo que va encima de la imagen (CardColors; DARK_CARDS) y de las marcas de clasificación (MarkColors; DARK_MARKS), sin Qt: el ÚNICO sitio de los colores de la interfaz
  helpers/theme_qss.py               QSS de los componentes generales (barras de desplazamiento, separadores, botones, campos, menús...) a partir de un ThemeColors
  helpers/gpu_composition.py         enable_gpu_composition: la ventana principal, dibujada con la GPU desde que se abre (un QQuickWidget invisible antes de mostrarla: sin cortes al arrastrar y sin el parpadeo al abrir el mapa); gpu_allowed (la opción, '--sin-gpu' y, sin elegir, default_gpu_setting: sí en Windows y macOS, no en Linux)
  helpers/theme_style.py             ThemeStyle: QProxyStyle sobre Fusion que dibuja los botones de opción y las casillas (también las de listas y árboles) con los colores del tema
  helpers/ui_theme.py                Tema: los juegos activos (COLORS, CARD_COLORS, MARK_COLORS), paleta oscura de Fusion (build_palette), hoja de estilos global (QSS: la general + las piezas propias), tooltips, colores compartidos de la cuadrícula (GRID_BG, GRID_LINE) y de los iconos (SIDEBAR_ICON_COLOR, SIDEBAR_ICON_OPEN_COLOR, TOOLBAR_ICON_ACCENT_COLOR; None = paleta), TOOLBAR_MARGIN
  helpers/mode_toolbar.py            ModeToolbar: botones de modo de la toolbar (Catálogo, Imagen, Vídeo, Audio, Tracks), exclusivos; icono en acento solo en el modo activo (al pasar el ratón cambia la caja); páginas provisionales (la crea ModuleHost)
  dialogs/settings_dialog.py         SettingsDialog: ventana de opciones (columna de secciones + páginas; PAGES = General: aceleración por GPU, Catálogo, Metadatos: escribir en los archivos y el aviso «Edición múltiple»; Mapa: capas propias y caché de teselas)
  dialogs/section_layout_page.py     SectionLayoutPage: página «Paneles» de la ventana de opciones (las secciones de las dos barras de cualquier módulo: casillas, orden, restaurar); edita una copia y la aplica al modelo al aceptar
  dialogs/map_layer_dialog.py        MapLayerDialog: «Añadir capa» / «Cambiar capa» (nombre, dirección de las teselas, atribución, zoom máximo; lo que no vale se dice debajo)
  dialogs/collection_dialog.py       CollectionDialog: "Crear colección" / "Crear conjunto" (nombre, conjunto, incluir la selección)
  dialogs/smart_collection_dialog.py SmartCollectionDialog: crear / editar una colección inteligente (reglas y grupos de reglas, recuento en vivo)
  dialogs/filter_presets_dialog.py   FilterPresetsDialog: «Gestionar ajustes personalizados» (ordenar, cambiar el nombre, eliminar, restaurar los de fábrica); devuelve la lista nueva
  dialogs/folder_content_dialog.py   FolderContentDialog: «¿Qué contiene esta carpeta?» al añadir una carpeta (FOLDER_CONTENT_TEXTS)
  dialogs/remove_dialog.py           RemoveDialog: «Eliminar N archivos del catálogo», como Lightroom: explicación y botones «Eliminar del disco» / «Eliminar del catálogo» (por defecto) / «Cancelar»
  sidebars/catalog_sidebar.py        CatalogSidebar: barra lateral del catálogo (Catálogo, Carpetas, Colecciones); emite GridSource
  sidebars/image_sidebar.py          ImageSidebar: barra del módulo Imagen, solo para navegar (Biblioteca - Imagen, Carpetas, Fechas y Lista de palabras clave). Es el contenedor: Biblioteca - Imagen, las secciones en orden (una lista), una sola fila elegida y el estado guardado; cada sección con árbol, en sections/
  sidebars/sections/tree_section.py  TreeSection: base de las secciones con árbol de la barra de un módulo (views, find_item, owns, reveal, save_state / restore_state, reset; señal rebuilt), make_item y TEXT_NAME_INDENT
  sidebars/sections/folder_section.py  FolderSection: «Carpetas» con lo de una biblioteca (recuentos, opción de subcarpetas, lo desplegado, menú «Mostrar en el Explorador»)
  sidebars/sections/date_section.py  DateSection: «Fechas» (años ▸ meses ▸ días con recuentos y «Sin fecha»; filas con date_source; lo desplegado en expanded_dates); date_label, date_tooltip
  sidebars/sections/keyword_section.py KeywordSection: «Lista de palabras clave» (filtro y árbol con recuentos que incluyen las hijas; las que no tienen nada, en gris; lo desplegado en KeywordExpansion)
  layout/section_registry.py         SECTION_REGISTRY (sin Qt): el registro de modos y de secciones plegables de las dos barras (SectionSpec: id estable, título, barras, modos, posición y estado de partida); AQUÍ se da de alta una sección o un modo
  layout/section_layout.py           SectionLayout (sin Qt): la colocación por modo y barra (lista ordenada de SectionEntry: id, visible, expanded); mover, ocultar, plegar, restaurar; to_state / from_state con versión (LAYOUT_VERSION) y fusión con el registro
  layout/section_layout_model.py     SectionLayoutModel: la única fuente de verdad de la colocación; lee y guarda 'section_layout' en settings.json y avisa con layout_changed(modo, barra); working_copy / apply para editar una copia y aplicarla de una vez (Opciones); la primera vez importa lo plegado que se guardaba antes. Lo crea el controlador y llega a los módulos en ModuleContext.section_layout
  helpers/sidebar_icons.py           load_sidebar_icons: iconos de unidades, carpetas y colecciones (barras del Catálogo e Imagen), con sus variantes ':open' y ':menu'
  widgets/keyword_checklist.py       KeywordChecklist: filtro + árbol de palabras con casillas de tres estados (editor del inspector); padres de lo asignado resaltados; menú contextual y soltar tarjetas
  widgets/recent_keywords.py         RecentKeywords: «Últimas palabras clave», 6 botones de ancho fijo (asignar / quitar con un clic)
  helpers/signal_blocker.py          blocked_signals: bloquear las señales de varios objetos Qt en un 'with'
  helpers/keyword_menu.py            Menú contextual de los árboles de palabras clave (crear, renombrar, mover, borrar, purgar): pregunta y devuelve la operación; «Borrar» devuelve el recuento (fetch_keyword_usage) y confirm_keyword_deletion pregunta después; «Purgar», la lista (fetch_unused_keywords) y ask_keyword_purge pregunta enseñándola
  helpers/keyword_expansion.py       KeywordExpansion: palabras desplegadas de cada árbol (SIDEBAR, INSPECTOR), para recuperarlas al abrir
  widgets/sidebar_tree_view.py       SidebarTreeView (alto ajustado, sin scroll propio, sin teclado ni «búsqueda al teclear», ROLE_SOURCE / ROLE_COUNT / ROLE_EMPHASIS) + CountDelegate (name_indent: el nombre, unos px más a la derecha)
  widgets/section_stack.py           SectionStack: las secciones plegables de una barra, colocadas por el modelo (orden, visibles, plegadas; bind, set_mode, set_available) y su menú (clic derecho en una cabecera o en el fondo de la barra: casillas para mostrar u ocultar y «Restaurar por defecto»; build_menu, show_menu, watch_empty_area) y el reordenar arrastrando las cabeceras (drop_target, drop_index, la raya); la usan CatalogSidebar, ImageSidebar e InspectorPanel
  widgets/collapsible_section.py     CollapsibleSection: sección plegable con cabecera y botones ("+"); header_menu_requested (clic derecho en la cabecera) y header_drag_started / _moved / _finished (arrastrarla por el título)
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
  widgets/single_media_view.py       SingleMediaView: vista individual (archivo actual de la cuadrícula, mismo modelo y selección): imagen ajustada y nítida, marcador sin miniatura, aviso de no disponible, «No hay archivos»; el zoom, en single_view_zoom.py
  widgets/map_page.py                MapPage: página del mapa en el centro (crea el MapView la primera vez que se pide; aviso encima, '#lbl_map_notice'; coge el teclado del mapa; la tira debajo, con un separador para su alto)
  widgets/map_filmstrip.py           MapFilmstrip: la tira de fotos del mapa (una MediaGridView de una fila, con el modelo y la selección de la cuadrícula, tarjetas compactas del alto de la tira, de 100 px como mínimo, la rueda a los lados, arrastre sin imagen)
  widgets/single_view_zoom.py        SingleViewZoom: zoom 1:1 de la vista individual (lupa, clic, arrastre con la mano, Z, el original en segundo plano, vuelta a la ajustada); magnifier_cursor
  inspector/                         ── Inspector: el panel DERECHO ── ([FLUJOS.md §12](FLUJOS.md))
    inspector_panel.py               ► InspectorPanel y DEFAULT_SECTIONS (aquí se añade una sección)
    base_section.py                    InspectorSection (title, title_for, key, libraries / fits, applies_to, show_summary; datos propios con data_request / show_data; header_widget; señal edit_requested), InfoGrid (etiqueta | valor | icono; ROW_SPACING) e IconCell (icono o botón; ICON_Y_OFFSET)
    keywords_section.py                Sección «Palabras clave» de solo lectura (las asignadas, separadas por comas, con «*» las que no tienen todos). Sin usar desde el 08/11/2026: el editor la sustituye en todos los módulos
    keyword_editor_section.py          «Palabras clave» (con cualquier selección, en todos los módulos): caja con comas (KeywordTextEdit: Intro, Esc, sugerencias, Ctrl+K) y «Últimas palabras clave»; cambios con apply_keyword_changes
    keyword_list_section.py            «Lista de palabras clave» (siempre): KeywordChecklist (árbol con casillas, flecha «ver sus fotos», soltar tarjetas); cambios con apply_keyword_changes
    metadata_section.py                Sección «Metadatos» (biblioteca Imagen): desplegable de vistas en la cabecera, filas de metadata_fields.py, valores con fetch_field_values; los campos de EDITABLE_KEYS, con cajas (cambios con update_metadata_fields; aviso «Edición múltiple»)
    editable_row.py                    EditableValue: caja editable de una línea o de varias (Intro, Esc, Tab, Mayús+Intro; «Varios» como Lightroom; señal committed; reject: vuelve y avisa junto a la caja)
    value_parsing.py                   Lo escrito en las cajas del GPS, la altitud y la dirección (formas aceptadas, límites, avisos INVALID_TEXTS); NUMERIC_COLUMNS: las columnas de cada caja; sin Qt
    selection_section.py               Sección «Selección»: nombre, carpeta, tamaño, fecha, contenido, biblioteca y estado
    formatting.py                      Textos: tamaños (24,3 MB), fechas por precisión, rangos, nombres de meses y días (MONTH_NAMES, WEEKDAY_NAMES), tipos («434 fotos · 20 vídeos»), origen de la fecha; metadatos: dimensiones, exposición, compensación, GPS, dirección, programa y medición (códigos EXIF), duración, fps, códec
  ► metadata_fields.py                 CAMPOS y VISTAS de la sección «Metadatos» (aquí se añaden): InspectorField (etiqueta, columnas por tipo de medio, formato), PRESETS, COMMON_HEAD, display_value; EDITABLE_KEYS (los que se editan) y editor_value
  widgets/media_grid_view.py         MediaGridView: QListView de la cuadrícula con imagen de arrastre pequeña y semitransparente (o sin imagen: set_drag_image); «No hay archivos» si está vacía
  models/media_mime.py               MIME propio del arrastre (application/x-arca-media-ids: {catalog, ids})
  map/                               ── Componente de mapa (diseño y plan en docs/MAPA.md; componente base; lo usa la vista «Mapa»: controllers/map_controller.py) ──
    map_types.py                       Datos que entran y salen del mapa: MapMarker, MapTrack, MapBounds (bounds_of), MapViewport, MapHit, MapMode, SelectionMode; is_valid_position; sin Qt
    map_view.py                      ► MapView: el mapa (fachada; lo único que conocen los módulos): marcadores, selección, tracks (activo, punto señalado), soltar tarjetas y mover fotos (set_drop_enabled), vista previa, botón derecho, capas, encuadre, estado; guarda lo pedido y se lo pasa al fondo cuando está listo
    map_backend.py                     MapBackend: contrato del fondo del mapa (lo que MapView pide a la tecnología que pinta: señales y métodos); solo declara
    web_backend.py                     WebMapBackend: el fondo con QtWebEngine + Leaflet (al verse y al cambiar de tamaño, la página vuelve a medir su espacio; página de resources/map/, colores del tema como variables CSS, sin foco; recoge los arrastres de tarjetas con un filtro en los widgets internos de la vista); css_color, marker_payload, track_payload
    web_bridge.py                      MapBridge: lo que la página puede decirle a Python (QWebChannel): cargada, lista, encuadre, selección, doble clic, clic en un track y punto bajo el ratón, fotos arrastradas y botón derecho
    map_scheme.py                      Esquema arca-map:// (MapSchemeHandler: recursos de la página, teselas con caché y descarga, miniaturas); register_map_scheme (antes de QApplication), shared_handler
  helpers/ui_file_manager.py         "Mostrar en el Explorador/Finder" multiplataforma (reveal_in_file_manager) y papelera del sistema (move_to_trash, con QFile.moveToTrash)
core/
  catalog/                           ── Crear, abrir y llenar el catálogo ──
    media_types.py                     MediaType (photo, video, audio, ebook, track, other) y CACHEABLE_MEDIA_TYPES
    libraries.py                     ► BIBLIOTECAS (Library, LIBRARY_NAMES: su nombre en toda la interfaz) y tipo de contenido de las carpetas: qué se cataloga en cada una (ALLOWED_MEDIA_TYPES), biblioteca de cada archivo (library_for), detección de vídeos por el nombre (guess_video_library: patrones al principio del archivo), corrección manual (set_library, CLASSIFIABLE_MEDIA_TYPES), classify_pending_videos, count_unclassified, declaraciones con herencia (FolderContentResolver, set_folder_content, folder_content_for)
    color_labels.py                    Etiquetas de color canónicas y equivalencia con Lightroom (xmp:Label, photoshop:LabelColor); sin Qt
    media_queries.py                   SQL de la cuadrícula (fetch_grid_rows, count_grid_items); _source_condition traduce
                                       el GridSource a SQL (ÚNICO sitio; pública como source_condition); guardado de rating/flag/color (update_user_field) y de los metadatos editados (update_metadata_fields); fetch_media_file (ruta y dimensiones de UN archivo); sin Qt
    geotagging.py                      Ubicar fotos recordando las coordenadas de antes: set_media_position (poner, mover o quitar; por update_metadata_fields), restore_media_positions (deshacer), PositionChange; sin Qt
    map_queries.py                     Consultas del mapa: fetch_map_items (lo mismo que la cuadrícula, con source_condition: los puntos con coordenadas, los tracks con su contorno decodificado y cuántas fotos y vídeos no tienen coordenadas); MapPoint, MapTrackOutline, MapItems; sin Qt
    selection_summary.py               Resumen para el inspector: fetch_selection_summary (ids) y fetch_source_summary (origen); SelectionSummary
    keywords.py                        Palabras clave en el catálogo: ensure_keyword_path, resolve_flat_keyword (sueltas), set_media_keywords (manda el archivo), keyword_tree, fetch_keyword_tree, filter_keyword_tree; edición: assign_keyword, remove_keyword, diff_keyword_text, apply_keyword_changes; árbol: create, rename, move, delete_keyword, purge_unused_keywords, fetch_keyword_usage (lo que afecta borrar, de todo el catálogo y por tipo), fetch_unused_keywords / delete_unused_keywords (lo que purgaría, con su ruta, y borrar exactamente eso); sin Qt
    selection_metadata.py              Valores comunes de unos campos en la selección (común / «Varios» / vacío); FieldSource dice de qué columnas sale cada campo por tipo de medio
    grid_source.py                     GridSource (ALL / FOLDER / SMART / COLLECTION / QUICK / KEYWORD): qué muestra la cuadrícula; inmutable; source_to_dict / source_from_dict. UNCLASSIFIED = «Sin clasificar»
    grid_filter.py                   ► FILTRO de la barra de filtros: GridFilter (pestañas encendidas, candado, filas de Texto y Atributos, columnas de Metadatos: MetadataFilter, metadata_rule) -> rule_sets() (conjuntos de reglas con AND, que se suman al origen); filter_to_dict / filter_from_dict; sin Qt
    filter_presets.py                  AJUSTES PERSONALIZADOS de la barra de filtros: FilterPreset (nombre + GridFilter), los de fábrica, la lista de settings.json (filter_presets), cuál coincide con el filtro, cuáles valen para un módulo, elegir y restaurar
    grid_orders.py                   ► ÓRDENES de la cuadrícula: SORT_FIELDS (campos del desplegable), GridOrder (campo + dirección; to_state / from_state), order_by_sql (NULL al final, desempate por nombre e id); sin Qt
    smart_fields.py                  ► CAMPOS de las colecciones inteligentes (grupos, secciones, tipo, columna SQL, unidades; browse = también columna de «Metadatos»)
    metadata_values.py                 Valores y recuentos de una columna de «Metadatos» (fetch_metadata_values: cascada, fechas en árbol, lo elegido a 0); sin Qt
    timeline.py                        Sección «Fechas» (línea de tiempo): fetch_timeline (años > meses > días de una biblioteca, con «Sin fecha»; usa fetch_metadata_values), date_source (origen de una fila), is_date_source; sin Qt
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
    track/gpx_reader.py                read_gpx -> GpxSummary (distancia 2D haversine, desnivel con umbral, fechas, caja, actividad; con collect_points, los puntos por segmentos en arrays compactos)
    track/extractor.py                 TrackExtractor (GPX -> track_details, también su contorno 'overview'; TRACK_EXTRACTOR_VERSION = 3)
    track/inspect_cli.py               Diagnóstico de GPX (resumen y desnivel con varios umbrales)
    inspect_cli.py                     Herramienta de diagnóstico (qué lee ExifTool / qué se guardaría; --campos elige imagen o vídeo según el archivo)
  userdata/                          ── Datos del usuario fuera del catálogo ── (ver core/userdata/LEEME.md)
    policy.py                        ► destino de cada formato: XMP incrustado, sidecar .xmp o archivo de carpeta
    editable_fields.py               ► metadatos descriptivos editables: columna, bit de pendiente, etiquetas XMP y antiguas, clave del .arca.json
    folder_file.py                     Archivo de carpeta '.arca.json' (lectura, escritura atómica, copia .bak)
    xmp_writer.py                      Escritura en XMP con ExifTool (solo los campos pendientes; comprueba releyendo); el GPS, también en el EXIF
    sync.py                            write_pending_user_data (trabajo) y la lectura al importar (apply_file_user_data, apply_folder_files)
  thumbnails/                        ── Generar y guardar las miniaturas ── (ver core/thumbnails/LEEME.md)
    sizes.py                           ThumbnailSize: 160 / 480 / 1200 / 2560 px (lado largo) y calidad JPEG
    cache.py                           ThumbnailCache: ruta derivada del id, escritura atómica, resolve(); ThumbnailStorageError
    imaging.py                         Orientación, modos de color, conversión a sRGB, escalera sin ampliar
    generator.py                       generate_thumbnails (UN archivo), load_source_image (prueba los orígenes) y THUMBNAIL_VERSION
    full_image.py                      load_full_image: el original a tamaño completo (RAW: su mayor vista previa), derecho y en sRGB como la caché, para la vista individual a 1:1; sin Qt
    registry.py                      ► qué origen lee cada tipo de medio y extensión
    sources/                           base.py, pillow_source.py, heif_source.py (HEIC), raw_preview_source.py (RAW, vía ExifTool)
    job.py                             generate_pending_thumbnails (trabajo) e invalidate_thumbnails (regenerar a demanda)
    inspect_cli.py                     Diagnóstico: genera miniaturas de archivos reales y las cuenta
    _testing.py                        Utilidades solo para las autopruebas de core/thumbnails (perfiles ICC de prueba)
  maps/                              ── Mapas (diseño y plan en docs/MAPA.md; los usa ui_helpers/map/) ──
    tile_layers.py                   ► LISTA de capas del mapa (TileLayer, TILE_LAYERS: aquí se añade una), tile_url, is_valid_tile, user_agent; capas del usuario (user_layer, check_url_template, all_layers, new_user_key, de y a settings.json); sin Qt ni red
    tile_store.py                      TileStore: caché de teselas en disco (una carpeta por capa, escritura atómica, caducidad a los 30 días, tope de tamaño con 'prune', 'clear'); image_mime (tipo de una tesela por sus bytes); sin Qt ni red
  tracks/                            ── Cálculos sobre recorridos (sin Qt ni base de datos; docs/MAPA.md) ──
    geodesy.py                         haversine_m y EARTH_RADIUS_M: el ÚNICO sitio donde se calculan distancias sobre la Tierra
    simplify.py                        Contorno de un track: simplify_track (distancia radial + Douglas-Peucker, tope de puntos), polilínea codificada (encode/decode_polyline) y encode_overview / decode_overview
    gpx_document.py                    Lector completo del GPX (sin Qt): read_gpx_path (el recorrido en arrays compactos, TrackPath) y read_gpx_document (GpxDocument: tracks, segmentos, puntos, waypoints y lo que no se edita, tal cual)
tools/exiftool/                      ExifTool (no se versiona; ver tools/exiftool/LEEME.txt)
scripts/build_ui.py                  Compila ui/*.ui con pyside6-uic y resources/recursos.qrc con pyside6-rcc (genera resources/recursos_rc.py)
scripts/export_qtbase_es.py          Copia la traducción al español de Qt (qtbase_es.qm) a resources/locales
resources/map/                       Página del mapa (index.html, arca_map.js, arca_map.css) y vendor/ (Leaflet y Supercluster copiados; ver su LEEME.txt). Se lee del disco, no va en el .qrc
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
