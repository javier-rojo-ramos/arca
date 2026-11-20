# Arca Media — Arquitectura

> Cómo está montada la aplicación: principios, componentes, reglas de arquitectura, qué hace cada archivo (mapa) y qué se ejecuta en cada hilo.
> Índice: [INDEX.md](INDEX.md).

## Qué es y principios

Catalogador de archivos multimedia (tipo DAM) de escritorio y multiplataforma (Windows, macOS, Linux), inspirado en Lightroom, FastStone, Mp3tag y VisualDivX. Pensado para gestionar colecciones de **imágenes** (en curso), **vídeo, audio y ebooks** (previstos). Uso interno de la empresa; se empaquetará con PyInstaller (pendiente: [PENDIENTE.md](PENDIENTE.md), `GEN 5`).

Principios:

- **Los archivos originales no se mueven, no se renombran ni se borran; lo que el usuario edita sí se guarda en ellos, sin generar copias** (regla del 16/11/2026; [DECISIONES.md](DECISIONES.md)). Previsto: las etiquetas y carátulas del audio ([MOD_MUSICA.md](MOD_MUSICA.md)) y los GPX editados ([MOD_TRACKS.md](MOD_TRACKS.md)). Hoy se escribe: la valoración, la marca, el color, las palabras clave y los metadatos descriptivos editados en la aplicación (título, pie de ilustración, creador, copyright y ubicación) con las reglas de `core/userdata/` (XMP incrustado, sidecar `.xmp` o `.arca.json`; ver su `LEEME.md`), y se envía a la papelera lo que el usuario pide eliminar del disco.
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
  app_modules.py                     MODULES: la ficha de cada módulo (clave, título, biblioteca, icono, inicial y título de su sección «Biblioteca - …»), en el orden de la toolbar; AQUÍ se da de alta un módulo. La leen los módulos, el registro de secciones y el inspector (module_spec, library_modules, library_badge)
  app_constants.py                   Constantes, iconos (AppIcons), tamaños de miniatura, claves compartidas de settings.json
  app_logging_manager.py             setup_logging (loguru + InterceptHandler); desde la 1.09, los errores fatales (nativos) dejan la pila de cada hilo en '<log>.crash.log' (faulthandler); desde la 1.10, al cerrar bien (lo llama main.py), discard_recovered_crash_dump lo vacía si solo trae excepciones de COM recuperadas. Módulo compartido con otros programas del autor
controllers/
  main_window_controller.py          Controlador de la ventana: catálogo activo, ventana de opciones; crea y conecta los trabajos (job_coordinator.py), añadir y sincronizar carpetas (folder_import.py) y eliminar (remove_actions.py); conecta la cuadrícula (modelo, atajos y guardado de rating/flag/color) y crea los módulos (_configurar_modulos)
  inspector_controller.py            InspectorController: selección de la cuadrícula -> resumen en segundo plano -> inspector; cambios de las secciones en cola (edit_requested -> user_data_changed; request_edit con on_done: el resultado, para deshacer); flecha «ver sus fotos» (navigate_requested); lo desplegado del árbol del inspector (save_state / restore_state); «Mostrar en el Explorador»
  job_coordinator.py                 JobCoordinator: los trabajos en segundo plano (metadatos, miniaturas, escritura en los archivos, eliminar): nombres y títulos, el gestor de cada catálogo (attach/detach), las reglas del encadenado, la escritura diferida, la pregunta de los pendientes, «Regenerar miniaturas», sus barras en la barra de estado y la ventana «Leyendo metadatos»; lo que toca la cuadrícula lo pide con señales (GEN 15.1)
  folder_import.py                   FolderImport: «Añadir carpeta» (elegir, «¿Qué contiene esta carpeta?», add_folder en segundo plano con su avance, una a la vez), «Sincronizar carpeta», el resumen (con quitar los ausentes al sincronizar) y «Quitar archivos ausentes» (GEN 15.2)
  file_actions.py                    FileActions: «Crear nueva carpeta...» (CAT 4.4a y CAT 5: la ventana, con lo elegido o vacía, el plan, la confirmación si hay algo que avisar y el trabajo), mover tarjetas soltadas en una carpeta (CAT 4.4b: el plan, la confirmación y el trabajo), mover una carpeta soltada en otra (CAT 4.4c: el plan, la confirmación y el trabajo de renombrar; al terminar, la de destino desplegada), «Cambiar nombre...» de una carpeta (CAT 4.3; al terminar, folder_renamed para los módulos) y de un archivo (CAT 4.2: ¿uno solo?, ¿algo en marcha?, ¿está en el disco?, la ventana, el plan —si el nombre no se puede usar, el motivo y otra vez la ventana—, el trabajo «Moviendo archivos») y lo que se hace al terminar
  remove_actions.py                  RemoveActions: «Eliminar...» (¿algo en marcha?, plan de la papelera, la ventana, el trabajo) y lo que se hace al terminar cualquier trabajo de quitar; busy_reason y start_removal_job también para folder_actions (GEN 15.3)
  folder_actions.py                  FolderActions: «Quitar del catálogo...» de una carpeta de la barra lateral (cuenta, pregunta y lanza el trabajo por remove_actions) y «Mostrar en el Explorador»
  locate_actions.py                  LocateActions: «Localizar...» de una ubicación desconectada (CAT 6.3): elegir dónde está ahora, comprobar, preguntar y cambiarla en el catálogo
  collection_actions.py              CollectionActions: une barra lateral + menú de la cuadrícula + BD para las colecciones del usuario (crear, renombrar, borrar, soltar, añadir, quitar); lo crea CatalogModule
  filter_controller.py               FilterController: barra de filtros <-> filtro del módulo activo (ModuleHost.set_filter / filter_changed); Ctrl+L; oculta la franja en la vista individual
  filter_preset_controller.py        FilterPresetController: desplegable de ajustes personalizados <-> lista (settings.json, filter_presets) y filtro del módulo activo; pide el nombre al guardar y si se reemplaza
  metadata_progress.py               MetadataProgress: mientras se leen los metadatos (más de 2 s), abre la ventana «Leyendo metadatos», que bloquea la aplicación (espera a que se cierre otra modal); la cierra al terminar, fallar o cancelar (GEN 20)
  metadata_filter_controller.py      MetadataFilterController: panel «Metadatos» <-> recuentos en segundo plano (columnas de partida del módulo, solo lo que cambia, respuestas tardías fuera, alto guardado)
  undo_history.py                    UndoHistory: deshacer en toda la aplicación (Ctrl+Z en la ventana; pasos UndoStep con su descripción y su forma de deshacerse; se vacía al cerrar el catálogo). Hoy lo llena el mapa
  map_controller.py                  MapController: la vista «Mapa» (lo mismo que la cuadrícula, pedido con map_queries solo con el mapa a la vista; selección en los dos sentidos; encuadre al cambiar de origen; aviso de lo que no sale; desplegable de la capa en la barra inferior, guardado en settings.json; doble clic → vista individual; capas propias, tope de la caché al crear el mapa; la tira de fotos: botón de la barra inferior y F9, si se ve y su alto en settings.json, doble clic → vista individual, la actual a la vista; ubicar fotos soltándolas y mover las ubicadas donde el módulo lo permite, por la cola del inspector, con confirmación a partir de 50; «Quitar la ubicación» con el botón derecho; cada cambio, en el historial de deshacer); attach / detach, set_edit_queue, set_undo_history, refresh (tras un cambio del inspector), apply_settings
  track_detail_controller.py         TrackDetailController: el recorrido completo del track activo y su perfil (TrackDetail), leídos y calculados en segundo plano (load_track_detail), con memoria de los 5 últimos; lo pone en el mapa en lugar del contorno y lo da a quien lo pida (request, detail_ready, detail_failed)
  track_profile_controller.py        TrackProfileController: la banda del perfil bajo el mapa de Tracks (qué perfil se ve según los tracks seleccionados, textos sin track activo o con el motivo si no se puede leer, botón btn_map_profile y F10, alto y visibilidad en settings.json) y su sincronización con el mapa (punto ámbar en los dos sentidos, tramo resaltado, Esc); menú del botón derecho con la pendiente; apply_settings
  sidebar_visibility.py              SidebarVisibility: mostrar u ocultar las barras laterales (menú «Ver» con F7 y F8, Tab para las dos, «Ocultar barra» en el menú de las secciones; sidebars_visible en settings.json)
  map_framing.py                     MapFraming: el último encuadre del mapa de cada módulo con su origen (sin Qt; to_state / from_state, guardado por catálogo)
  center_view_controller.py          CenterViewController: vista del centro del módulo activo en pantalla (página de stacked_widget_main, botones de vista, deslizador solo en la cuadrícula) y navegación (doble clic / Intro, G, M, Esc a la vista de la que se vino, flechas, Inicio, Fin, rueda; un solo archivo seleccionado en la vista individual; el teclado del mapa, en su página y en la tira: watch_map_widget); al elegir algo en una barra (source_chosen), el teclado al centro y la primera foto seleccionada; al recargar, siempre un archivo actual (el que recuerda el módulo, la selección que había o el que ocupa su lugar)
  app_modules/                       ── Módulos de la aplicación (Catálogo, Imagen, Vídeo, Audio) ── ([FLUJOS.md §11](FLUJOS.md))
    base.py                            AppModule (clase base: barra izquierda, qué muestra la cuadrícula, orden, vistas, qué permite su mapa (map_options), tipos y columnas de partida del filtro, ciclo de vida) y ModuleContext
    registry.py                      ► LISTA de módulos en el orden de la toolbar (aquí se da de alta uno nuevo)
    module_host.py                     ModuleHost: toolbar de modos, barras laterales, módulo activo -> cuadrícula, estado por catálogo; source_chosen (el usuario elige otra cosa en una barra); el archivo actual de cada módulo (set_current_media)
    module_view_state.py               ModuleViewState: lo elegido en cada módulo (orden, vista del centro, filtro y archivo actual) y cómo se guarda por catálogo (claves 'orders', 'views', 'filters' y 'current'); sin Qt
    center_views.py                    CenterView: vistas del centro (cuadrícula, individual, lista, mapa) con su texto emergente e icono; MapOptions (qué permite el mapa de un módulo: ubicar fotos); sin Qt
    catalog_module.py                  CatalogModule: barra CatalogSidebar (contadores, árboles, colecciones, opción de subcarpetas, estado)
    image_module.py                    ImageModule: módulo de biblioteca (LibraryModule) con la barra común y una sección de más, la «Lista de palabras clave» (árbol con recuentos); vistas: cuadrícula, individual y mapa (en el que se ubican fotos); una palabra pedida sin biblioteca se limita a Imagen
    library_module.py                  LibraryModule: base de los módulos de una biblioteca (Imagen, Tracks, Vídeo, Audio) con la barra LibrarySidebar (contadores, carpetas, fechas y las secciones de más, leídos de una vez en segundo plano; vuelta a «Todos», salvo si una sección oculta filas; estado; menú de las carpetas); la subclase pone library, texts y, si las tiene, extra_sections
    tracks_module.py                   TracksModule (hereda de LibraryModule): barra LibrarySidebar (Biblioteca - Tracks con su selección rápida, carpetas con tracks y fechas), estado; vistas: cuadrícula y mapa (el inicial; solo mira); orden por fecha, distancia, desnivel y duración
    video_module.py                    VideoModule (hereda de LibraryModule): biblioteca Vídeos (películas y series); cuadrícula e individual; orden con «Duración»
    audio_module.py                    AudioModule (hereda de LibraryModule): biblioteca Música; solo cuadrícula; orden con «Duración»
    placeholder_module.py              PlaceholderModule: botón sin módulo todavía (página «próximamente»); sin uso desde el 15/11/2026 (Vídeo y Audio ya tienen el suyo)
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
  helpers/app_icon.py                build_app_icon: el icono de la ventana con el juego de cada sistema (resources/icons/: .ico en Windows, PNG de macos/ en macOS, PNG de windows/ y linux/ en el resto); app_icon_files
  helpers/ui_icons.py                tinted_icon: SVG monocromos del .qrc teñidos al dibujarse (paleta, color fijo o hover); menu_icon, para las opciones de los menús
  helpers/ui_info.py                 show_info_window: ventana de información con HTML (QTextBrowser); hoy no la usa nadie
  mixins/window_snap.py              WindowSnapMixin: ajuste magnético de la ventana a los bordes (desactivado en macOS)
  delegates/thumbnails_delegate.py   ThumbnailsDelegate: dibuja la tarjeta (con 'location_pin', la chincheta de lo que tiene ubicación, que se pulsa: location_clicked; o, con 'compact', solo la imagen, sin la banda y con la chincheta: la de la tira del mapa; miniatura o marcador por tipo, duración, nombre, estrellas, marca, fondo de color, aviso de no disponible y círculo de la selección rápida)
  models/media_roles.py              Roles compartidos modelo <-> delegado (ROLE_RATING, ROLE_FLAG, ROLE_COLOR_LABEL, ROLE_MEDIA_TYPE, ROLE_DURATION...)
  models/media_grid_model.py         MediaGridModel: lista desde la BD + miniaturas desde la caché + edición del usuario; set_located (quién tiene coordenadas, sin recargar); request_media_file (ruta y dimensiones de UN archivo, en segundo plano)
  models/full_image_loader.py        FullImageLoader: miniatura grande (2560 px o la mayor que haya) de la caché en un hilo propio, con memoria de 5 imágenes y precarga; para la vista individual
  models/original_image_loader.py    OriginalImageLoader: el ORIGINAL de una foto (load_full_image) en un hilo propio, solo el último pedido, en RGB32; para la vista individual a 1:1
  helpers/grid_actions.py            GridActions: atajos de teclado (estilo Lightroom; F2, cambiar nombre) y menú contextual de la cuadrícula
  helpers/ui_color_labels.py         Etiquetas de color en la interfaz: su color (del tema, MARK_COLORS), textos, mezcla (blend) e icono de menú
  helpers/card_marks.py              Dibujo de estrellas, marca (recuadro / X) y círculo de la selección rápida: lo comparten la tarjeta y la barra inferior
  helpers/card_glyphs.py             Dibujo de la chincheta de la ubicación (draw_location_pin), del marcador de tipo (sin miniatura; draw_type_glyph, solo el dibujo, para la fila «Atributos») y del indicador de no disponible (también como icono, availability_icon: en las barras, la carpeta que falta y la ubicación desconectada), y el velo de rechazada o no disponible (veil): lo comparten la tarjeta y la vista individual
  helpers/profile_style.py           Estilo del perfil de elevación, sin Qt: ProfileStyle (colores, cómo se ve la pendiente —SlopeMode: sin colores, en el área o en la línea—, umbrales e histéresis, grosores, rejilla, cursor, letra) y slope_bands (la franja de pendiente de cada punto, con histéresis)
  helpers/profile_format.py          Marcas de los ejes del perfil (nice_range, ticks, distance_tick_label, altitude_tick_label) y sus textos (totals_text, range_text, cursor_lines), sin Qt
  helpers/profile_painter.py         Dibujo del perfil con QPainter: build_layout (dónde va cada cosa y la escala), render_static (rejilla, ejes, área y línea, en un QPixmap que el widget guarda) y paint_overlay (línea de arriba, tramo elegido y cursor)
  helpers/track_appearance.py        Lo que elige el usuario del aspecto de los tracks (Opciones > Tracks), leído y validado: track_colors (TrackColors), track_colors_to_settings, slope_mode; lo que no valga, lo del tema
  helpers/track_outline.py           El recorrido de un track como dibujo de su tarjeta: outline_from_overview (el contorno del catálogo, encajado con su proporción real) y draw_track_outline (al vuelo, con los colores del tema)
  helpers/zoom_geometry.py           Cuentas del zoom 1:1 de la vista individual (sin Qt): zoomed_size, can_zoom, relative_point, offset_keeping, clamp_offset (sin huecos, centrada si cabe, en píxeles físicos enteros)
  helpers/theme_colors.py            Colores del tema con nombre por función (ThemeColors; DARK), de las tarjetas y lo que va encima de la imagen (CardColors; DARK_CARDS) de las marcas de clasificación (MarkColors; DARK_MARKS) y del perfil de elevación (ProfileColors; DARK_PROFILE), sin Qt: el ÚNICO sitio de los colores de la interfaz
  helpers/theme_qss.py               QSS de los componentes generales (barras de desplazamiento, separadores, botones, campos, menús...) a partir de un ThemeColors
  helpers/gpu_composition.py         map_gpu_allowed y apply_map_gpu_setting: la GPU en los mapas (sin ella, '--disable-gpu' para Chromium antes de crear QApplication); enable_gpu_composition: la ventana principal, dibujada con la GPU desde que se abre (un QQuickWidget invisible antes de mostrarla: sin cortes al arrastrar y sin el parpadeo al abrir el mapa); gpu_allowed (la opción, '--sin-gpu' y, sin elegir, default_gpu_setting: sí en Windows y macOS, no en Linux)
  helpers/theme_style.py             ThemeStyle: QProxyStyle sobre Fusion que dibuja los botones de opción y las casillas (también las de listas y árboles) con los colores del tema
  helpers/ui_theme.py                Tema: los juegos activos (COLORS, CARD_COLORS, MARK_COLORS, PROFILE_COLORS), paleta oscura de Fusion (build_palette), hoja de estilos global (QSS: la general + las piezas propias), tooltips, colores compartidos de la cuadrícula (GRID_BG, GRID_LINE) y de los iconos (SIDEBAR_ICON_COLOR, SIDEBAR_ICON_OPEN_COLOR, TOOLBAR_ICON_ACCENT_COLOR; None = paleta), TOOLBAR_MARGIN
  helpers/mode_toolbar.py            ModeToolbar: botones de modo de la toolbar (Catálogo, Imagen, Vídeo, Audio, Tracks), exclusivos; icono en acento solo en el modo activo (al pasar el ratón cambia la caja); páginas provisionales (la crea ModuleHost)
  dialogs/settings_dialog.py         SettingsDialog: ventana de opciones (columna de secciones + páginas; PAGES = General: aceleración por GPU (la ventana y los mapas), Catálogo, Metadatos: escribir en los archivos y el aviso «Edición múltiple»; Mapa: capas propias y caché de teselas; Tracks y Paneles, en su archivo)
  dialogs/tracks_settings_page.py    TracksSettingsPage: página «Tracks» de la ventana de opciones (colores de los tracks en el mapa, con su muestra y QColorDialog, y cómo se ve la pendiente del perfil)
  dialogs/section_layout_page.py     SectionLayoutPage: página «Paneles» de la ventana de opciones (las secciones de las dos barras de cualquier módulo: casillas, orden, restaurar); edita una copia y la aplica al modelo al aceptar
  dialogs/map_layer_dialog.py        MapLayerDialog: «Añadir capa» / «Cambiar capa» (nombre, dirección de las teselas, atribución, zoom máximo; lo que no vale se dice debajo)
  dialogs/collection_dialog.py       CollectionDialog: "Crear colección" / "Crear conjunto" (nombre, conjunto, incluir la selección)
  dialogs/smart_collection_dialog.py SmartCollectionDialog: crear / editar una colección inteligente (reglas y grupos de reglas, recuento en vivo)
  dialogs/filter_presets_dialog.py   FilterPresetsDialog: «Gestionar ajustes personalizados» (ordenar, cambiar el nombre, eliminar, restaurar los de fábrica); devuelve la lista nueva
  dialogs/folder_content_dialog.py   FolderContentDialog: «¿Qué contiene esta carpeta?» al añadir una carpeta (FOLDER_CONTENT_TEXTS)
  dialogs/metadata_progress_dialog.py  MetadataProgressDialog: «Leyendo metadatos», modal respecto a la ventana: texto del autor, barra, «1.234 de 22.012» y «Cancelar»; Esc y Alt+F4 no la cierran (el botón de cerrar, en gris; el icono, el de la ventana principal)
  dialogs/new_folder_dialog.py       NewFolderDialog: «Nueva carpeta dentro de «...»»: el nombre (con la línea del motivo fija), «Incluir los N archivos seleccionados» y el aviso, que cambia con la casilla (CAT 4.4a y CAT 5)
  dialogs/rename_dialog.py           RenameDialog (archivo o, con folder_files, carpeta): «Cambiar el nombre de «...»»: el nombre sin la extensión (que se ve al lado), el motivo si no vale (naming.py) y el aviso de que el nombre cambia también en el disco
  dialogs/remove_dialog.py           RemoveDialog: «Eliminar N archivos del catálogo», como Lightroom: explicación y botones «Eliminar del disco» / «Eliminar del catálogo» (por defecto) / «Cancelar»
  sidebars/catalog_sidebar.py        CatalogSidebar: barra lateral del catálogo (Catálogo, Carpetas, Colecciones); soltar tarjetas en una colección (añadir) o en una carpeta (mover, CAT 4.4b), y una carpeta en otra (moverla, CAT 4.4c); emite GridSource
  sidebars/folder_drag.py            FolderTreeDrag: arrastrar una carpeta del árbol de «Carpetas» para moverla (CAT 4.4c; FOLDER_MIME, FolderDrag) y, al arrastrar algo sobre él, desplazar la barra lateral cerca del borde y desplegar una carpeta al pararse encima
  sidebars/library_sidebar.py        LibrarySidebar: barra de los módulos de una biblioteca (Imagen, Tracks, Vídeo, Audio), solo para navegar: «Biblioteca - …» (todo y su selección rápida), Carpetas, Fechas y las secciones de más de cada módulo (ExtraSection: id, título, cómo se crea y la consulta que la rellena; en Imagen, la Lista de palabras clave), con sus textos en LibraryTexts. Es el contenedor: una sola fila elegida y el estado guardado; cada sección con árbol, en sections/
  sidebars/sections/tree_section.py  TreeSection: base de las secciones con árbol de la barra de un módulo (set_tree, hides_rows, views, find_item, owns, reveal, save_state / restore_state, reset; señal rebuilt), make_item y TEXT_NAME_INDENT
  sidebars/sections/folder_section.py  FolderSection: «Carpetas» con lo de una biblioteca (recuentos, opción de subcarpetas, lo desplegado, menú «Mostrar en el Explorador»)
  sidebars/sections/date_section.py  DateSection: «Fechas» (años ▸ meses ▸ días con recuentos y «Sin fecha»; filas con date_source; lo desplegado en expanded_dates); date_label, date_tooltip
  sidebars/sections/keyword_section.py KeywordSection: «Lista de palabras clave» (filtro y árbol con recuentos que incluyen las hijas; las que no tienen nada, en gris; lo desplegado en KeywordExpansion)
  layout/section_registry.py         SECTION_REGISTRY (sin Qt): el registro de modos y de secciones plegables de las dos barras (SectionSpec: id estable, título, barras, modos, posición y estado de partida); AQUÍ se da de alta una sección. Los modos y los títulos «Biblioteca - …» salen de config/app_modules.py
  layout/section_layout.py           SectionLayout (sin Qt): la colocación por modo y barra (lista ordenada de SectionEntry: id, visible, expanded); mover, ocultar, plegar, restaurar; to_state / from_state con versión (LAYOUT_VERSION) y fusión con el registro
  layout/section_layout_model.py     SectionLayoutModel: la única fuente de verdad de la colocación; lee y guarda 'section_layout' en settings.json y avisa con layout_changed(modo, barra); working_copy / apply para editar una copia y aplicarla de una vez (Opciones); la primera vez importa lo plegado que se guardaba antes. Lo crea el controlador y llega a los módulos en ModuleContext.section_layout
  helpers/sidebar_icons.py           load_sidebar_icons: iconos de unidades, carpetas y colecciones (barras del Catálogo e Imagen), con sus variantes ':open' y ':menu', y el aviso de la carpeta que falta y de la ubicación desconectada (con sus textos)
  widgets/keyword_checklist.py       KeywordChecklist: filtro + árbol de palabras con casillas de tres estados (editor del inspector); padres de lo asignado resaltados; menú contextual y soltar tarjetas
  widgets/recent_keywords.py         RecentKeywords: «Últimas palabras clave», 6 botones de ancho fijo (asignar / quitar con un clic)
  helpers/signal_blocker.py          blocked_signals: bloquear las señales de varios objetos Qt en un 'with'
  helpers/keyword_menu.py            Menú contextual de los árboles de palabras clave (crear, renombrar, mover, borrar, purgar): pregunta y devuelve la operación; «Borrar» devuelve el recuento (fetch_keyword_usage) y confirm_keyword_deletion pregunta después; «Purgar», la lista (fetch_unused_keywords) y ask_keyword_purge pregunta enseñándola
  helpers/keyword_expansion.py       KeywordExpansion: palabras desplegadas de cada árbol (SIDEBAR, INSPECTOR), para recuperarlas al abrir
  widgets/sidebar_tree_view.py       SidebarTreeView (alto ajustado, sin scroll propio, sin teclado ni «búsqueda al teclear», sin elegir filas al mover el ratón con el botón pulsado, ROLE_SOURCE / ROLE_COUNT / ROLE_EMPHASIS) + CountDelegate (name_indent: el nombre, unos px más a la derecha)
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
  widgets/map_page.py                MapPage: página del mapa en el centro (crea el MapView la primera vez que se pide; aviso encima, '#lbl_map_notice'; coge el teclado del mapa; debajo, la banda del perfil —ElevationProfile, en Tracks— y la tira, con separadores para sus altos, que se reparten juntos)
  widgets/elevation_profile.py       ElevationProfile: el perfil de elevación de un track (set_profile, set_style, set_cursor y set_selection sin señales; cursor_moved, range_selected y selection_cleared al usar el ratón; no coge el teclado). Con --ventana, una ventana para ajustar el aspecto
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
    track_section.py                   TrackSection: «Track» (distancia, desnivel, altitud, duración, velocidad, puntos, actividad y programa de los tracks seleccionados; con varios, sumados); pide sus datos con fetch_track_stats
    formatting.py                      Textos: tamaños (24,3 MB), fechas por precisión, rangos, nombres de meses y días (MONTH_NAMES, WEEKDAY_NAMES), tipos («434 fotos · 20 vídeos»), origen de la fecha; metadatos: dimensiones, exposición, compensación, GPS, dirección, programa y medición (códigos EXIF), duración, fps, códec
  ► metadata_fields.py                 CAMPOS y VISTAS de la sección «Metadatos» (aquí se añaden): InspectorField (etiqueta, columnas por tipo de medio, formato), PRESETS, COMMON_HEAD, display_value; EDITABLE_KEYS (los que se editan) y editor_value
  widgets/media_grid_view.py         MediaGridView: QListView de la cuadrícula con imagen de arrastre pequeña y semitransparente (o sin imagen: set_drag_image); «No hay archivos» si está vacía
  models/media_mime.py               MIME propio del arrastre (application/x-arca-media-ids: {catalog, ids})
  map/                               ── Componente de mapa (diseño y plan en docs/MOD_TRACKS.md; componente base; lo usa la vista «Mapa»: controllers/map_controller.py) ──
    map_types.py                       Datos que entran y salen del mapa: MapMarker, MapTrack, MapBounds (bounds_of), MapViewport, MapHit, MapMode, SelectionMode; is_valid_position; DEFAULT_VIEW (encuadre de partida); sin Qt
    map_view.py                      ► MapView: el mapa (fachada; lo único que conocen los módulos): marcadores, selección, tracks (activo, punto señalado, tramo resaltado; track(id)), soltar tarjetas y mover fotos (set_drop_enabled), vista previa, botón derecho, capas, encuadre, estado; guarda lo pedido y se lo pasa al fondo cuando está listo
    map_backend.py                     MapBackend (con set_track_range: el tramo resaltado): contrato del fondo del mapa (lo que MapView pide a la tecnología que pinta: señales y métodos); solo declara
    web_backend.py                     WebMapBackend: el fondo con QtWebEngine + Leaflet (al verse y al cambiar de tamaño, la página vuelve a medir su espacio; página de resources/map/, colores del tema como variables CSS, sin foco; recoge los arrastres de tarjetas con un filtro en los widgets internos de la vista); css_color, marker_payload, track_payload
    web_bridge.py                      MapBridge: lo que la página puede decirle a Python (QWebChannel): cargada, lista, encuadre, selección, doble clic, clic en un track y punto bajo el ratón, fotos arrastradas, botón derecho y botón «Encuadrar»
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
    track_stats.py                     fetch_track_stats: los datos de los tracks seleccionados, juntos (TrackStats: sumas, altitud mínima y máxima, textos comunes o MIXED, velocidad media), para la sección «Track» del inspector
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
    folder_tree.py                     Árbol de carpetas con recuentos (fetch_folder_tree, build_folder_tree, sort_key natural): las de los archivos y las de la tabla folders (CAT 5); las que ya no están en el disco (find_missing_folders, CAT 6.2)
    catalog_folders.py                 Las carpetas del catálogo (tabla folders, CAT 5: también las vacías): add_folders, sync_folders (tras recorrer), remove_folders, folders_under, folder_paths
    missing_items.py                   Contar y quitar del catálogo los ausentes de una carpeta (y sus miniaturas) y las carpetas apuntadas que ya no existen en el disco (count_missing, CAT 6.2c)
    relocation.py                      «Localizar...» (CAT 6.3): plan_location_relocation (la carpeta nueva vale: sin solapes; cuántos de sus archivos están, hasta 1 000) y relocate_location (ruta y nombre nuevos de la ubicación; nunca toca el disco) (sin Qt)
    folder_removal.py                  Quitar del catálogo una carpeta entera (y, si es la raíz, su ubicación): count_folder_items, remove_folder_from_catalog (trabajo; usa remove_media_items)
    empty_folders.py                   Carpetas del catálogo vacías en el disco, para borrarlas al quitar una carpeta (CAT 3): candidate_folders, plan_empty_folders, remove_empty_folders (lo que sobra, a la Papelera; la carpeta, con os.rmdir); sin BD ni Qt
    media_removal.py                   Eliminar: plan_removal (qué puede ir a la papelera: no los ausentes, desconectados ni en red), remove_media_items (trabajo: quitar del catálogo y, si se pide, papelera + sidecar del RAW + entrada del .arca.json), is_network_path
    catalog_schema.py                  Esquema SQL: MIGRATIONS, apply_migrations, configure_connection
    catalog_builder.py                 CatalogBuilder: crea carpetas + catalogo.db (WAL) + esquema
    catalog_opener.py                  open_catalog: valida un catálogo existente (marca APPLICATION_ID) y aplica sus migraciones
    storage_locations.py               register_folder (ubicaciones sin solapes), locate_folder (lo mismo, solo lectura), make_relative_path, refresh_location_status
    availability.py                    check_availability: discos desconectados (y cuáles han cambiado: switched_locations), carpetas que faltan, con sus archivos (missing_folders, CAT 6.2b), y archivos visibles que faltan o vuelven (sin Qt)
    scan_filter.py                     ScanFilter: descarta basura, ocultos, temporales, enlaces
    media_detector.py                  MediaTypeDetector: tipo de medio y MIME (extensión, mimetypes, puremagic)
    folder_scanner.py                  FolderScanner: recorre carpetas y entrega ScanCandidate
    catalog_writer.py                  save_candidates, mark_missing, replace_walk_issues...
    folder_importer.py                 add_folder: orquesta registrar + escanear + guardar
  database/db_manager.py             CatalogDatabaseManager: consultas asíncronas (QThreadPool, 4 hilos, compartidos con los trabajos largos); mide la espera de cada tarea en la cola (QueueStats: las de 100 ms o más, al registro; resumen al cerrar el catálogo)
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
    writers.py                         UserDataWriter (la interfaz de un escritor), WriteItem, FolderFileWriter (.arca.json) y XmpFileWriter (ExifTool); split_items (un archivo entre el escritor de su formato y el .arca.json) y default_writers. AQUÍ se añade un escritor nuevo
    sync.py                            write_pending_user_data (trabajo: qué hay pendiente, lo reparte entre los escritores de writers.py y anota el resultado) y la lectura al importar (apply_file_user_data, apply_folder_files)
  file_ops/                          ── Operaciones con archivos en el disco: renombrar y mover con el catálogo al día (CAT 4; reglas en docs/DECISIONES.md, 19/11/2026) ──
    naming.py                          Nombres válidos en Windows, macOS y Linux (name_problem, clean_name) y renombrar sin la extensión (rename_keeping_extension)
    moves.py                           Mover y renombrar archivos (crear una carpeta, con lo elegido o vacía, apuntada en folders: plan_new_folder, execute_new_folder; mover a una carpeta: plan_move, con la biblioteca de destino; la de destino se apunta en folders; renombrar una carpeta: plan_folder_rename, execute_folder_rename, renamed_folder_path; moverla a otra de su ubicación: plan_folder_move, con el mismo trabajo): rename_request / move_requests → plan_file_moves (qué se hará y qué se omite) → execute_file_moves (trabajo: archivo, su .xmp, su entrada del .arca.json y el catálogo, con el registro file_operations) y reconcile_file_operations (al abrir el catálogo, lo que quedó a medias)
  thumbnails/                        ── Generar y guardar las miniaturas ── (ver core/thumbnails/LEEME.md)
    sizes.py                           ThumbnailSize: 160 / 480 / 1200 / 2560 px (lado largo) y calidad JPEG
    cache.py                           ThumbnailCache: ruta derivada del id, escritura atómica, resolve(), read() (lee los bytes reintentando si el archivo está bloqueado); ThumbnailStorageError
    imaging.py                         Orientación, modos de color, conversión a sRGB, escalera sin ampliar
    generator.py                       generate_thumbnails (UN archivo), load_source_image (prueba los orígenes) y THUMBNAIL_VERSION
    full_image.py                      load_full_image: el original a tamaño completo (RAW: su mayor vista previa), derecho y en sRGB como la caché, para la vista individual a 1:1; sin Qt
    registry.py                      ► qué origen lee cada tipo de medio y extensión
    sources/                           base.py, pillow_source.py, heif_source.py (HEIC), psd_source.py (PSD: su imagen combinada), raw_preview_source.py (RAW, vía ExifTool)
    job.py                             generate_pending_thumbnails (trabajo) e invalidate_thumbnails (regenerar a demanda)
    inspect_cli.py                     Diagnóstico: genera miniaturas de archivos reales y las cuenta
    _testing.py                        Utilidades solo para las autopruebas de core/thumbnails (perfiles ICC de prueba)
  maps/                              ── Mapas (diseño y plan en docs/MOD_TRACKS.md; los usa ui_helpers/map/) ──
    tile_layers.py                   ► LISTA de capas del mapa (TileLayer, TILE_LAYERS: aquí se añade una), tile_url, is_valid_tile, user_agent; capas del usuario (user_layer, check_url_template, all_layers, new_user_key, de y a settings.json); sin Qt ni red
    tile_store.py                      TileStore: caché de teselas en disco (una carpeta por capa, escritura atómica, caducidad a los 30 días, tope de tamaño con 'prune', 'clear'); image_mime (tipo de una tesela por sus bytes); sin Qt ni red
  tracks/                            ── Cálculos sobre recorridos (sin Qt ni base de datos; docs/MOD_TRACKS.md) ──
    geodesy.py                         haversine_m y EARTH_RADIUS_M: el ÚNICO sitio donde se calculan distancias sobre la Tierra
    simplify.py                        Contorno de un track: simplify_track (distancia radial + Douglas-Peucker, tope de puntos), polilínea codificada (encode/decode_polyline) y encode_overview / decode_overview
    gpx_document.py                    Lector completo del GPX (sin Qt): read_gpx_path (el recorrido en arrays compactos, TrackPath) y read_gpx_document (GpxDocument: tracks, segmentos, puntos, waypoints y lo que no se edita, tal cual)
    profile.py                         Perfil de elevación (sin Qt): build_profile (de un TrackPath: distancia acumulada, altitud tal cual y suavizada, pendiente y hora de cada punto; los totales, los del catálogo), range_stats (un tramo), index_at_distance (el cursor) y drawing_runs (lo que se dibuja, por trozos y reducido por columna de píxeles)
    activities.py                      Actividades de un track (sin Qt): ACTIVITIES (clave en inglés, texto en español), normalize_activity (el traductor de lo que traen los GPX), activity_label
tools/exiftool/                      ExifTool (no se versiona; ver tools/exiftool/LEEME.txt)
scripts/build_ui.py                  Compila ui/*.ui con pyside6-uic y resources/recursos.qrc con pyside6-rcc (genera resources/recursos_rc.py)
scripts/export_qtbase_es.py          Copia la traducción al español de Qt (qtbase_es.qm) a resources/locales
scripts/run_selftests.py             Ejecuta de una vez todas las autopruebas que no abren ventana y dice cuáles fallan (docs/PRUEBAS.md)
scripts/smoke_main_window.py         Prueba de humo de la ventana principal, fuera de pantalla, con la configuración en una carpeta temporal y un catálogo de prueba: añadir carpeta, valorar, regenerar, eliminar y cerrar (docs/PRUEBAS.md)
resources/map/                       Página del mapa (index.html, arca_map.js, arca_map.css) y vendor/ (Leaflet y Supercluster copiados; ver su LEEME.txt). Se lee del disco, no va en el .qrc
resources/                           recursos.qrc (lista de iconos e imágenes), images/ (SVG), icons/ (icono de la aplicación: svg/ los
                                     maestros, windows/ .ico y PNG, macos/ .icns y PNG, linux/ PNG; ver su README.md; no va en el .qrc),
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
