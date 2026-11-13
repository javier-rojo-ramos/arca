# Arca Media — Mapa (`MapView`): diseño y plan de implementación

> **Diseño; fase 0 hecha el 13/11/2026 (se sigue con el plan A: QtWebEngine + Leaflet), el resto sin implementar.** Componente de mapa único para los módulos Catálogo, Imagen y Tracks: tecnología, API, capas, elevación, datos, correlación foto-track, edición de GPX, rendimiento, riesgos y plan por pasos. Cuando un paso se entregue, su parte pasa a [FLUJOS.md](FLUJOS.md), [ARQUITECTURA.md](ARQUITECTURA.md) y [DECISIONES.md](DECISIONES.md), y aquí se tacha.
> Índice: [INDEX.md](INDEX.md). Punto de la hoja de ruta: [PENDIENTE.md](PENDIENTE.md), A.5 y A.6.

## Resumen

**Decisiones clave que propone este documento**

1. **Tecnología: QtWebEngine + Leaflet + `QWebChannel`**, con los recursos (Leaflet, JS y CSS propios) en local, sin CDN. Motivo: los tres requisitos imprescindibles (topográfico, elevación, edición de GPX) salen con piezas maduras y la parte difícil (editar miles de vértices, agrupar miles de marcadores) es mucho más barata en un lienzo web que en QML. **Plan alternativo: Qt Location (QML) en un `QQuickWidget`**; lo decide la fase 0 con criterios medibles (§1.4 y §10).
2. **`MapView(QWidget)` es una fachada**: recibe datos sencillos (`MapMarker`, `MapTrack`), emite intenciones (selección, soltar, mover, editar) y **nunca cambia datos**. La tecnología queda detrás de un `MapBackend`: cambiar de plan no toca los módulos.
3. **El mapa es una vista más del centro** (`CenterView.MAP`, que ya existe): muestra **lo mismo que la cuadrícula** (mismo `GridSource` y mismo filtro), con las fotos como marcadores y los tracks como líneas. Así el modo Catálogo no necesita nada especial: una colección estática ya puede contener tracks y fotos (los tracks son filas de `media_items`).
4. **El modelo vive en Python, no en JavaScript**: la página solo pinta y avisa. El track en edición, el deshacer, la validación, el perfil y la correlación están en `core/` sin Qt, con autoprueba.
5. **Perfil de elevación: widget nativo dibujado con `QPainter`** (colores del tema), no dentro de la página web.
6. **Teselas por un esquema propio** (`arca-map://`) servido desde Python: caché en disco controlada, sin conexión, `User-Agent` correcto y claves fuera del JavaScript. Capas de partida: IGN España (MTN ráster, base y ortofoto) y OpenTopoMap.
7. **Elevación**: la `ele` del GPX; si falta, teselas «terrarium» (AWS Terrain Tiles) decodificadas con Pillow. Sin dependencias nuevas.
8. **Puntos de los tracks: no se guardan en SQLite.** El GPX es la fuente; en la base solo va un **contorno simplificado** por track (columna nueva `track_details.overview`, migración 4) para pintar muchos a la vez. La geometría completa se lee del archivo a demanda, en segundo plano.
9. **Coordenadas de las fotos**: se reutiliza tal cual la edición del GPS del 11/11/2026 (`update_metadata_fields`, bits de pendiente, escritura con las reglas de `core/userdata/`).
10. **Orden**: fase 0 → componente base → Catálogo → Imagen → Tracks (ver, elevación, correlación, edición). Es el sugerido; solo se añade la correlación entre la elevación y la edición.

**Decisiones pendientes del autor** (detalle y recomendación en §11)

| # | Decisión | Recomendación |
|---|---|---|
| D1 | Geoetiquetar desde el mapa, ¿escribe en los archivos? | Sí, con el mecanismo actual del GPS (ya decidido para la edición a mano); en lotes, la ventana de vista previa dice cuántos archivos se van a escribir |
| D2 | Editar un GPX existente: ¿se sobrescribe o siempre se exporta a otro archivo? | Siempre a un archivo nuevo («Exportar a GPX…»); el original no se toca (principio del proyecto) |
| D3 | Modo Imagen: ¿mapa con tira de fotos debajo (como Lightroom) o cuadrícula y mapa lado a lado? | Tira de fotos debajo |
| D4 | «Fotos de una ruta»: ¿basta con una colección hecha a mano, o se calcula (por hora y cercanía)? | Las dos: la colección ya funciona; en Tracks, calculado |
| D5 | Capas de partida y si se usa alguna con clave (Thunderforest, MapTiler) | IGN + OpenTopoMap, sin claves |
| D6 | Deshacer al mover fotos en el mapa (hoy la aplicación no tiene deshacer) | Un deshacer simple, solo del mapa, mientras dure la sesión |
| D7 | Al recolocar una foto, ¿qué pasa con su altitud? | Dejarla como está; rellenarla con el modelo de elevaciones, más adelante y preguntando |
| D8 | Puntos insertados en un GPX: ¿hora interpolada o sin hora? | Interpolada por distancia entre los dos vecinos |
| D9 | Textos, icono y atajo de la vista «Mapa»; textos de las capas | Los propone cada paso; decide el autor |
| D10 | Identificación ante los servidores de teselas (`User-Agent` con o sin contacto) | Nombre y versión de la aplicación, sin datos personales |

---

## 0. Punto de partida (lo que ya existe y se reutiliza)

Comprobado en el código el 13/11/2026:

| Pieza | Dónde | Para qué sirve aquí |
|---|---|---|
| `CenterView.MAP` | `controllers/app_modules/center_views.py` | La vista ya está declarada (sin icono ni página). `AppModule.views()` decide qué módulos la ofrecen |
| `CenterViewController` | `controllers/center_view_controller.py` | Pone la página de `stacked_widget_main`; una vista sin página cae en la cuadrícula (`_show`). Recibe las páginas en `pages` |
| `ModuleHost`, `ModuleViewState` | `controllers/app_modules/` | Recuerdan la vista por módulo y por catálogo. Nada que cambiar |
| `MediaGridModel` + `selectionModel` de `list_view_grid` | `ui_helpers/models/media_grid_model.py` | Origen (`source`), filtro (`filter_rules`), `row_of_id`, `media_ids`, `modelReset`. La vista individual ya comparte modelo y selección: el mapa hará lo mismo |
| Arrastre de tarjetas | `ui_helpers/models/media_mime.py` (`MEDIA_IDS_MIME`, `decode_media_ids`) | Lo que llega al soltar sobre el mapa. No hay que tocar la cuadrícula |
| `source_condition` | `core/catalog/media_queries.py` | Único sitio que traduce `GridSource` + filtro a SQL: la consulta del mapa lo reutiliza |
| GPS de las fotos | `media_items.latitude`, `longitude`, `altitude`, `gps_direction`; `update_metadata_fields`; `core/userdata/editable_fields.py` | Leer y **editar** coordenadas, con escritura en los archivos ya comprobada con Lightroom ([DECISIONES.md](DECISIONES.md), 11/11/2026) |
| Cola de cambios | `InspectorController.request_edit` → `user_data_changed` | Por aquí van los cambios de coordenadas (avisa de errores, refresca, lanza la escritura) |
| Tracks | `core/metadata/track/gpx_reader.py` (`read_gpx`, haversine, umbral de 8 m), `extractor.py`, tabla `track_details` (caja, salida, llegada, distancia, desnivel, horas UTC) | Resumen de cada GPX. **No guarda los puntos** (lectura en streaming) |
| Biblioteca `tracks` | `core/catalog/libraries.py` | Existe; **el módulo Tracks no** (`registry.py` solo tiene Catálogo, Imagen y dos provisionales) |
| Colecciones | `collections`, `collection_items` | Un track es un `media_items`: ya cabe en una colección estática junto a fotos |
| Miniaturas | `ThumbnailCache.resolve` | Miniatura de 160 px para los marcadores |
| Secciones de barra por biblioteca | `ui_helpers/sidebars/sections/` (`FolderSection`, `DateSection`) | La barra del módulo Tracks, sin código nuevo de árboles |
| Dependencias instaladas | `.venv`: PySide6 6.11.2 (Essentials + Addons), QtPy 2.4.3, Pillow, defusedxml | `QtWebEngineWidgets`, `QtWebChannel`, `QtLocation`, `QtQuickWidgets`, `QtCharts` y `QtNetwork` **importan bien** con Python 3.14.8 en Windows |

Reglas del proyecto que condicionan el diseño ([CLAUDE.md](../CLAUDE.md)): `core/` sin Qt; nada de BD ni trabajo largo en el hilo principal; funciones con `conn` primero y sin `commit`; migraciones solo al final; ningún color suelto; clases de interfaz de menos de ~400 líneas; nada de lógica nueva en `main_window_controller.py`; Qt siempre por `qtpy`.

---

## 1. Tecnología del mapa

### 1.1 Opciones

- **A. QtWebEngine + Leaflet + `QWebChannel`**: un `QWebEngineView` con una página local; Python y JavaScript se hablan por un objeto puente.
- **B. Qt Location (QML) en un `QQuickWidget`**: elemento `Map` con el complemento `osm` y elementos `MapPolyline`, `MapQuickItem`, `MapItemView`.
- **C. Mapa propio con `QGraphicsView`** (teselas como `QPixmap`, elementos como `QGraphicsItem`): se añade a la comparación porque el proyecto ya dibuja casi todo a mano y no tiene ni QML ni web.

Dentro de A, **Leaflet frente a MapLibre GL JS**: se elige Leaflet (1.9, BSD) con dibujo en `canvas`. Las capas topográficas viables son ráster; Leaflet no necesita WebGL (que dentro de QtWebEngine depende de los controladores gráficos y cae a un modo por software lento) y su código es pequeño y fácil de depurar. MapLibre solo ganaría con teselas vectoriales o relieve 3D, que no son requisito.

### 1.2 Comparación

| Criterio | A. WebEngine + Leaflet | B. Qt Location (QML) | C. `QGraphicsView` propio |
|---|---|---|---|
| **Topográfico** | Cualquier servicio XYZ o WMTS (IGN, OpenTopoMap...), varias capas y superposiciones, sin límite | Complemento `osm`: sus capas de fábrica y **una** dirección propia por parámetro (`osm.mapping.custom.host`); cambiar entre varias capas propias obliga a recrear el complemento. A comprobar en 6.11 | Cualquiera: las teselas las pide nuestro código |
| **Elevación** | Igual en las tres: el perfil es un widget nativo aparte y los datos salen de `core/` | Igual | Igual |
| **Edición de GPX** | Arrastrar vértices, insertar en un tramo, borrar, cortar: eventos de ratón sobre un `canvas`; solo se pintan las asas de lo visible. Hay muchos ejemplos | Hay que hacerlo en QML: un `MapQuickItem` por asa y `MapPolyline` que se rehace entera al mover un punto; con decenas de miles de puntos es el punto débil conocido | Todo a mano, pero con control total (`QGraphicsItem`) |
| **Arrastre desde widgets nativos** | Indirecto: el `QWebEngineView` recibe la soltada, hay que interceptarla en Python y pedir a la página la coordenada del píxel. **Es la mayor incógnita** (fase 0) | Directo (`DropArea` de QML, `map.toCoordinate`) | Directo y trivial |
| **Agrupar miles de marcadores** | Supercluster o Leaflet.markercluster (decenas de miles sin problema) | No tiene: hay que agrupar en Python y repintar al cambiar el zoom | A mano |
| **Rendimiento** | Bueno con `canvas` y simplificación por zoom; coste fijo de un proceso Chromium (memoria, primer arranque) | Bueno en el mapa base; flojo con líneas muy largas y muchos elementos | Bueno si se hace bien; depende de nosotros |
| **Tamaño** | `Qt6WebEngineCore.dll` pesa 203 MB en `.venv` (más ~15 MB de recursos). Ya está en la rueda de PySide6: no cambia el desarrollo; sí el paquete futuro | Pequeño (ya incluido) | Nulo |
| **Mantenimiento** | Tres lenguajes (Python, JS, CSS), pero el JS es un pintor sin estado; Leaflet es estable desde hace años | Un lenguaje nuevo en el proyecto (QML) y un módulo de Qt con poca actividad y pocas extensiones | Solo Python, pero todo el mapa es código nuestro (gestos, zoom suave, teselas, HiDPI) |
| **PySide6 + Python 3.14** | Windows: comprobado que importa. macOS y Linux: las ruedas oficiales lo incluyen, **sin probar** (como el resto del proyecto); en Linux necesita bibliotecas del sistema (`libnss3`...) | Windows: comprobado que importa. macOS y Linux: incluido, sin probar | Sin riesgo |
| **Integración con el tema** | Los colores se inyectan como variables CSS desde `COLORS` (ningún color en el JS ni en el CSS) | Propiedades QML desde Python | Directa |
| **Teclado** | Chromium tiende a quedarse el foco; hay que dejar la vista sin foco para que los atajos sigan en las fotos (fase 0) | Sin problema | Sin problema |

### 1.3 Recomendación

**Opción A: QtWebEngine + Leaflet + `QWebChannel`.**

- De los tres requisitos imprescindibles, el que más trabajo y más riesgo tiene es la **edición de GPX**; en A es donde resulta más barata y con más referencias. El topográfico también es donde menos límites tiene.
- Su debilidad real, **el arrastre desde la cuadrícula**, se resuelve en un punto (interceptar la soltada y convertir píxel → coordenada) y se comprueba en un día en la fase 0.
- El tamaño no cuenta hoy (no hay empaquetado) y el uso es interno.
- El JavaScript queda reducido a «pintar y avisar» (§2.5): el estado, la lógica y las pruebas siguen en Python, que es lo que el autor mantiene.

Bibliotecas web, todas copiadas a `resources/map/vendor/` (nada de CDN: funciona sin conexión y no cambia sola): Leaflet 1.9.x (BSD-2) y Supercluster (ISC) para agrupar. Nada más: la edición y el cursor del track son código propio (los complementos de edición de Leaflet crean un marcador por vértice y no sirven con tracks grandes).

### 1.4 Plan alternativo

**Opción B, Qt Location en un `QQuickWidget`**, si la fase 0 falla en lo que es propio de WebEngine (criterios en §10). Lo que cambia: `QmlMapBackend` en lugar de `WebMapBackend`; el agrupamiento pasa a Python (`core/maps/clustering.py`, rejilla por nivel de zoom); la edición muestra asas solo para los vértices visibles con un tope (p. ej. 300). Lo que **no** cambia: `MapView`, los controladores, todo `core/` (teselas, elevación, perfil, modelo del track, correlación) y el widget del perfil.

Si B también fallara por el rendimiento de `MapPolyline` con tracks grandes, queda la opción C, que reutiliza el almacén de teselas de §3 y no tiene incógnitas técnicas, solo trabajo.

### 1.5 Durabilidad (el proyecto debe durar entre 10 y 20 años)

Valorado el 13/11/2026, a petición del autor. No cambia la recomendación, pero fija cómo se hace:

- **Qué envejece peor en cada opción.** A: QtWebEngine es el módulo más pesado de Qt y el que más tarda en llegar a plataformas nuevas; a cambio, es estratégico para Qt y la web es la plataforma más compatible hacia atrás que existe (un Leaflet congelado de hoy seguirá funcionando en el Chromium de dentro de 15 años). B: Qt Location ya desapareció una vez (no existió de Qt 6.0 a 6.4 y volvió en 6.5) y tiene poca actividad: es la apuesta con peor historial. C: solo depende de QtWidgets y de Python; es la más duradera y la más cara de escribir.
- **Lo que protege al proyecto no es la tecnología elegida, sino lo poco que depende de ella**: todo lo que tiene valor (modelo del track, deshacer, perfil, correlación, lectura y escritura de GPX, almacén de teselas, consultas) está en `core/`, en Python puro y con autoprueba; `MapView` y `MapBackend` aíslan el resto. Si dentro de unos años QtWebEngine deja de servir, se reescribe **un** archivo de fondo (`web_backend.py` y la página), no el mapa.
- **Reglas para la parte web** (son las que la hacen durar): bibliotecas copiadas en `resources/map/vendor/` con su versión y su licencia anotadas en un `LEEME.txt`; **sin cadena de construcción** (ni `npm`, ni empaquetadores, ni TypeScript): JavaScript llano que se abre y se lee; el JS propio, pequeño y sin estado; las mínimas bibliotecas (Leaflet y Supercluster; si Supercluster diera problemas, la agrupación pasa a Python sin cambiar la API).
- **Lo que seguro que cambiará en 20 años son los servicios de teselas** (direcciones, condiciones, cierres), con cualquier tecnología. Por eso la lista de capas es declarativa, el usuario puede **añadir una capa propia** (plantilla de dirección y atribución) desde las opciones sin tocar código (§3.1), y lo esencial (tracks, marcadores, perfil, edición) funciona sin ninguna capa.
- **Datos**: nada del mapa crea un formato propio. Las coordenadas van a las etiquetas estándar (EXIF/XMP) y los tracks son GPX 1.1.

**Relación con la «isla QML» de la vista individual** (sugerida para los cortes horizontales al arrastrar a 1:1; [PENDIENTE.md](PENDIENTE.md), B): son dos decisiones independientes y la propuesta no cambia. Que la vista individual acabe usando QML quitaría a la opción B la pega de «un lenguaje nuevo», pero no sus puntos débiles (madurez de Qt Location y edición de tracks grandes). Lo que sí comparten: un `QWebEngineView`, un `QQuickWidget` y un `QOpenGLWidget` hacen los tres que la ventana pase a componerse con la GPU. Puede que, con solo existir el mapa, los cortes desaparezcan o cambien; no se sabe hasta probarlo, así que la fase 0 lo mide (punto 8) antes de decidir nada sobre la vista individual. Si hiciera falta actuar, `QOpenGLWidget` (ya anotado en PENDIENTE) lo resuelve sin meter QML.

---

## 2. API del componente

### 2.1 Dónde vive cada cosa

```
ui_helpers/map/                       ── Componente de mapa ──
  map_view.py          ► MapView(QWidget): la fachada. Lo ÚNICO que conocen los módulos y controladores
  map_types.py           MapMarker, MapTrack, MapBounds, MapViewport, MapHit, MapMode, SelectionMode,
                         TrackEditIntent (dataclasses y enumeraciones; sin Qt)
  map_backend.py         MapBackend: contrato interno (lo que MapView pide a la tecnología)
  web_backend.py         WebMapBackend: QWebEngineView + QWebChannel + página local
  web_bridge.py          MapBridge(QObject): ranuras y señales expuestas a JavaScript
  map_scheme.py          MapSchemeHandler: sirve arca-map:// (recursos, teselas, miniaturas)
resources/map/           index.html, arca_map.js, arca_map.css, vendor/ (Leaflet, Supercluster)
ui_helpers/widgets/elevation_profile.py   ElevationProfile(QWidget): perfil dibujado con QPainter
ui_helpers/widgets/map_page.py            MapPage(QWidget): página del centro (mapa + tira de fotos + perfil)
controllers/map_controller.py             MapController: une MapView con el modelo, la selección y la BD
controllers/track_edit_controller.py      TrackEditController: sesión de edición, deshacer, exportar
controllers/app_modules/tracks_module.py  TracksModule
core/maps/               tile_layers.py (► lista de capas), tile_store.py (caché en disco), dem.py (elevación)
core/tracks/             geodesy.py, gpx_document.py, track_model.py, simplify.py, profile.py, correlation.py
core/catalog/map_queries.py, geotagging.py
```

`MapView` **no** se promociona en el `.ui`: lo crea `MapPage` en código la primera vez que se muestra (Chromium no arranca si nunca se abre el mapa).

### 2.2 Datos que recibe

No recibe un `QAbstractItemModel`: `MediaGridModel` no lleva coordenadas (solo lo que pinta la tarjeta) y atar el mapa a un modelo de Qt impediría cambiar de tecnología. Recibe **datos inmutables y sencillos** (`ui_helpers/map/map_types.py`, sin Qt):

```python
@dataclass(frozen=True, slots=True)
class MapMarker:
    media_id: int
    latitude: float
    longitude: float
    media_type: str            # valor de MediaType (para el dibujo sin miniatura)
    has_thumbnail: bool        # la miniatura se pide a arca-map://thumb/<media_id>
    direction: float | None    # gps_direction, por si se dibuja el rumbo

@dataclass(frozen=True, slots=True)
class MapTrack:
    track_id: int              # media_items.id del GPX (negativo: track nuevo, aún sin archivo)
    name: str
    segments: tuple[tuple[tuple[float, float], ...], ...]   # (lat, lon) por segmento
    detailed: bool             # False = contorno simplificado; True = geometría completa

@dataclass(frozen=True, slots=True)
class MapBounds:
    south: float; west: float; north: float; east: float
```

### 2.3 Señales (el mapa avisa; nunca cambia nada)

| Señal | Cuándo | Quién la atiende |
|---|---|---|
| `ready()` | La página está cargada (lo pedido antes se guarda en cola y se aplica aquí) | `MapController` |
| `load_failed(str)` | La tecnología no arranca (se muestra un aviso en la página, no una ventana) | `MapController` |
| `viewport_changed(MapViewport)` | Se mueve o cambia el zoom (con retardo) | Guardar el encuadre |
| `selection_requested(list[int], SelectionMode)` | Clic en un marcador o en un grupo (`REPLACE`), Ctrl+clic (`TOGGLE`), clic en vacío (`REPLACE` con lista vacía) | `MapController` → `selectionModel` de la cuadrícula |
| `marker_activated(int)` | Doble clic en un marcador | `CenterViewController.open_single` |
| `media_dropped(MediaDrag, float, float)` | Se sueltan tarjetas (`MEDIA_IDS_MIME`) en un punto | `MapController` → cola de cambios |
| `markers_moved(list[int], float, float)` | Se arrastra un marcador ya ubicado (o un grupo) a otro punto | Igual |
| `track_clicked(int)` | Clic en la línea de un track | Selección / track activo |
| `track_hovered(int, int)` | El ratón pasa cerca del track activo: `(track_id, índice de punto)`; `-1` al salir | `ElevationProfile.set_cursor` |
| `edit_requested(TrackEditIntent)` | En modo edición: mover, insertar, borrar, cortar, añadir al final | `TrackEditController` |
| `context_menu_requested(MapHit, QPoint)` | Botón derecho (qué hay debajo y dónde) | El controlador abre un `QMenu` nativo |
| `layer_changed(str)` | El usuario cambia de capa | Guardarla en `settings.json` |

### 2.4 Métodos

```python
class MapView(QWidget):
    # Marcadores (fotos y vídeos con coordenadas)
    def set_markers(self, markers: Sequence[MapMarker]) -> None: ...
    def update_markers(self, markers: Sequence[MapMarker]) -> None: ...   # añadir o mover unos pocos
    def remove_markers(self, media_ids: Sequence[int]) -> None: ...
    def set_selected_ids(self, media_ids: Sequence[int]) -> None: ...
    def set_preview_markers(self, markers: Sequence[MapMarker]) -> None: ...  # propuesta de la correlación

    # Tracks
    def set_tracks(self, tracks: Sequence[MapTrack]) -> None: ...
    def set_track_geometry(self, track: MapTrack) -> None: ...    # sustituye el contorno por el detalle
    def set_active_track(self, track_id: int | None) -> None: ...
    def set_track_cursor(self, track_id: int, point_index: int | None) -> None: ...

    # Encuadre
    def fit_bounds(self, bounds: MapBounds, *, animate: bool = True) -> None: ...
    def fit_content(self) -> None: ...        # todo lo que hay
    def fit_selection(self) -> None: ...
    def center_on(self, latitude: float, longitude: float, zoom: int | None = None) -> None: ...
    def viewport(self) -> MapViewport | None: ...

    # Capas
    def set_layers(self, layers: Sequence[TileLayer]) -> None: ...
    def set_base_layer(self, key: str) -> None: ...
    def base_layer(self) -> str: ...
    def set_overlay_visible(self, key: str, visible: bool) -> None: ...

    # Modo de interacción
    def set_mode(self, mode: MapMode) -> None: ...   # BROWSE, EDIT_TRACK, DRAW_TRACK
    def show_edit_segment(self, track_id: int, patch: TrackPatch) -> None: ...  # repinta lo editado
    def set_drop_enabled(self, enabled: bool) -> None: ...

    # Ciclo de vida
    def is_ready(self) -> bool: ...
    def clear(self) -> None: ...              # al cerrar el catálogo
    def save_state(self) -> dict: ...         # capa y encuadre (JSON)
    def restore_state(self, state: object) -> None: ...
```

Reglas de la API:

- **Todo va por `media_items.id`**; nada de filas, rutas ni objetos de la tecnología.
- Las llamadas anteriores a `ready` se guardan y se aplican al llegar (la página carga de forma asíncrona).
- `MapView` es instanciable más de una vez (comparten perfil y manejador del esquema), pensando en la sección «Ubicación» del inspector (PENDIENTE A.5); cada instancia cuesta memoria: se decidirá entonces.
- Los controles sobre el mapa (zoom, escala, atribución) los dibuja la página con variables CSS que `WebMapBackend` genera desde `COLORS` (`ui_theme.py`). El selector de capas y los botones de modo son **widgets nativos** en la barra inferior o en `MapPage`, no en la página.
- El menú contextual de Chromium se desactiva; el propio es un `QMenu` nativo.
- La vista **no coge el teclado** (como las barras, [DECISIONES.md](DECISIONES.md) del 12/11/2026): los atajos de clasificación siguen yendo a la tira de fotos. Excepción: en modo edición, `Supr`, `Esc`, `Ctrl+Z` y `Ctrl+Y` los atiende `TrackEditController` con atajos del `MapPage`.

### 2.5 Contrato interno con la página (solo para `WebMapBackend`)

- **Python → JS**: llamadas a funciones de `arca_map.js` con JSON compacto (marcadores como `[id, lat, lon, tipo, miniatura]`; tracks como polilíneas codificadas). Nunca se construye JavaScript concatenando textos del usuario: siempre `json.dumps`.
- **JS → Python**: ranuras de `MapBridge` (`on_select`, `on_drop_point`, `on_marker_moved`, `on_track_hover`, `on_edit`, `on_viewport`, `on_context_menu`). El JS no guarda más estado que lo que pinta.
- **Soltar tarjetas** (comprobado en la fase 0: los eventos llegan al widget interno de la vista, no a la subclase): un filtro de eventos en los hijos del `QWebEngineView` acepta `DragEnter`/`DragMove` solo si el arrastre trae `MEDIA_IDS_MIME` y no pasa el evento a Chromium; en `Drop` guarda el `MediaDrag`, pide a la página la coordenada del punto (`containerPointToLatLng`) y, con la respuesta, emite `media_dropped`. Durante el arrastre, la página pinta un marcador fantasma (`set_drop_cursor`).
- **Seguridad**: la página solo puede navegar dentro de `arca-map://` (`acceptNavigationRequest`); sin acceso a `file://` ni a la red directa (las teselas pasan por el esquema).

### 2.6 Cómo lo usan los tres modos

Ningún módulo toca `MapView` directamente. Lo hace `MapController` (uno, creado en `_conectar_vistas` como `CenterViewController`), que recibe el `ModuleHost`, el modelo y la vista de la cuadrícula, el `InspectorController` (para la cola de cambios) y el `MapPage`. Cada módulo solo **declara** lo que quiere:

- `AppModule.views()` incluye o no `CenterView.MAP` (ya existe).
- Un método nuevo, `AppModule.map_options() -> MapOptions` (dataclass sin Qt en `center_views.py` o junto a él): `show_filmstrip` (tira de fotos), `allow_geotag` (soltar y mover), `show_profile` (perfil), `allow_track_edit`, `related_photos` (añadir las fotos de la ruta). Por defecto, todo apagado.

| Modo | `views()` | `map_options()` | Qué se ve |
|---|---|---|---|
| Catálogo | cuadrícula, individual, **mapa** | todo apagado, salvo la tira si se decide (D3) | Lo del origen: marcadores y contornos de tracks. Solo ver y seleccionar |
| Imagen | cuadrícula, individual, **mapa** | tira + geoetiquetado | Marcadores; soltar desde la tira; mover los ubicados |
| Tracks | **mapa** (inicial), cuadrícula | perfil + edición + fotos de la ruta | El track elegido con detalle, los demás en contorno, perfil debajo |

---

## 3. Capas y teselas

### 3.1 Proveedores

Lista declarativa en `core/maps/tile_layers.py` (`TILE_LAYERS`, sin Qt; ► «aquí se añade una capa»): clave estable, nombre para el usuario, plantilla de dirección, zoom mínimo y máximo, atribución, si necesita clave y si permite descarga anticipada. **Las condiciones cambian: hay que volver a leerlas antes de activar cada capa** (las direcciones se comprueban en la fase 0).

| Capa | Tipo | Servicio | Condiciones (resumen) | Atribución |
|---|---|---|---|---|
| **IGN España, MTN ráster** | Topográfico (el de los mapas 1:25 000 y 1:50 000) | WMTS `https://www.ign.es/wmts/mapa-raster`, capa `MTN`, matriz `GoogleMapsCompatible` | Gratuito, CC BY 4.0; sin clave | «© Instituto Geográfico Nacional de España» |
| IGN España, base | Callejero y base | WMTS `https://www.ign.es/wmts/ign-base`, capa `IGNBaseTodo` | Igual | Igual |
| IGN España, PNOA | Ortofoto | WMTS `https://www.ign.es/wmts/pnoa-ma`, capa `OI.OrthoimageCoverage` | Igual | «PNOA cedido por © Instituto Geográfico Nacional de España» |
| **OpenTopoMap** | Topográfico mundial (curvas de nivel, sombreado) | `https://{a-c}.tile.opentopomap.org/{z}/{x}/{y}.png`, zoom ≤ 17 | Gratuito con uso moderado; sin descargas masivas; CC BY-SA | «© OpenStreetMap, SRTM · © OpenTopoMap (CC BY-SA)» |
| OpenStreetMap estándar | Base mundial | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | Política de uso estricta: `User-Agent` propio, caché obligatoria, prohibida la descarga anticipada; no garantizado para uso intensivo | «© OpenStreetMap contributors» |
| IGN Francia (Plan IGN) | Topográfico (Pirineo francés) | WMTS de la Géoplateforme | Abierto sin clave para Plan IGN; SCAN 25 requiere clave | «© IGN-F / Géoplateforme» |
| Thunderforest Outdoors, MapTiler Outdoor, Stadia Terrain | Topográficos mundiales de más calidad | Con **clave** | Planes gratuitos con tope mensual y, en algunos, solo para uso no comercial: al ser una aplicación de empresa, hay que leer la licencia (D5) | La de cada uno |

Propuesta de partida (D5): IGN MTN (por defecto en España), IGN base, PNOA y OpenTopoMap (por defecto fuera). Las claves, si algún día se usan, van en `settings.json` y se añaden en Python al pedir la tesela: nunca llegan a la página.

**Capas del usuario** (por durabilidad, §1.5): además de las de fábrica, las opciones permiten añadir capas propias (nombre, plantilla de dirección XYZ o WMTS, zoom máximo y atribución), guardadas en `settings.json`. Si un servicio cambia de dirección o cierra, se corrige sin tocar el código.

La **atribución** de la capa activa se muestra siempre en la esquina del mapa (es condición de todas).

### 3.2 Cómo se piden: el esquema `arca-map://`

La página no habla con Internet. Todo lo pide a un esquema propio que atiende `MapSchemeHandler` (`QWebEngineUrlSchemeHandler`):

| Dirección | Qué devuelve |
|---|---|
| `arca-map://app/...` | Los recursos de `resources/map/` (página, JS, CSS, Leaflet) |
| `arca-map://tiles/<capa>/<z>/<x>/<y>` | La tesela: de la caché si está y vale; si no, se descarga (`QNetworkAccessManager`), se guarda y se devuelve |
| `arca-map://thumb/<media_id>` | La miniatura de 160 px de la caché del catálogo (`ThumbnailCache.resolve`) |

Ventajas: caché y modo sin conexión controlados por la aplicación; un único sitio para el `User-Agent`, las claves, el límite de peticiones simultáneas (2 por servidor) y los reintentos; mismo origen para todo (sin problemas de CORS); las miniaturas llegan sin convertirlas a texto.

Dos obligaciones de Qt (van a [TRAMPAS.md](TRAMPAS.md) cuando se implemente): el esquema se **registra antes de crear `QApplication`** (`QWebEngineUrlScheme.registerScheme`) y `QtWebEngineWidgets` debe importarse (o ponerse `Qt.AA_ShareOpenGLContexts`) también antes. Es el único cambio en `main.py`.

Si en la fase 0 el manejador en Python resultara lento, la alternativa **dentro del mismo plan** es que Leaflet pida las teselas por `https` y usar la caché HTTP del perfil de WebEngine (se pierde el control del modo sin conexión).

### 3.3 Caché local

- `core/maps/tile_store.py` (`TileStore`, sin Qt): ruta `<carpeta de caché de la aplicación>/tiles/<capa>/<z>/<x>/<y>.<ext>`, escritura atómica (como `ThumbnailCache`), fecha de descarga = fecha del archivo.
- **Por aplicación, no por catálogo**: las teselas no son datos del catálogo y se pueden volver a bajar. La carpeta sale de `config/app_paths.py` (junto a `settings.json`, en una subcarpeta `cache`).
- **Caducidad**: 30 días (la política de OSM pide 7 como mínimo). Una tesela caducada se sigue sirviendo y se renueva en segundo plano; sin conexión, vale siempre.
- **Tope de tamaño**: configurable (propuesta: 2 GB), con limpieza de las menos usadas al arrancar, en segundo plano. Opción en la ventana de opciones (página nueva «Mapa»): tamaño, «Vaciar la caché de mapas».

### 3.4 Sin conexión

- Lo que está en la caché se ve; lo que no, una tesela lisa del color de fondo del tema y un aviso discreto en el mapa («Sin conexión: se muestra lo guardado»; texto a decidir).
- Marcadores, tracks, selección, perfil y edición funcionan igual: no dependen de la red.
- **Descargar una zona para usarla sin conexión**: posible más adelante y solo con las capas que lo permitan (campo `allow_prefetch`; OSM estándar lo prohíbe). No está en el plan inicial.

---

## 4. Elevación

### 4.1 De dónde sale

1. **La `ele` de cada punto del GPX**: siempre que exista. Es la que usa hoy el resumen (`gpx_reader`).
2. **Si falta** (rutas planificadas, puntos insertados, GPX sin altitud): un **modelo digital de elevaciones** por teselas, en `core/maps/dem.py`:
   - Fuente: **AWS Terrain Tiles, formato «terrarium»** (`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`; datos abiertos, sin clave, con atribución). Altura = `R × 256 + G + B / 256 − 32768`. Se decodifica con **Pillow** (ya es dependencia).
   - Zoom 12 o 13 (unos 20-40 m por píxel en España), interpolación bilineal entre los cuatro píxeles vecinos. Usa el mismo `TileStore` (capa `dem`): una ruta de 20 km son 2-6 teselas.
   - `sample_elevations(points, fetch) -> list[float | None]`; la descarga es una función que se le pasa (en un trabajo en segundo plano, con `urllib`), para que `core/` siga sin Qt.
   - Mejora posterior, si la precisión no basta: MDT05 del IGN (5 m, solo España).
3. La altitud **nunca se sustituye en silencio**: los puntos con `ele` del GPX la conservan. El perfil indica cuándo es estimada (texto a decidir). «Rellenar la altitud que falta» y «Sustituir toda la altitud por la del modelo» serán acciones explícitas de la edición.

### 4.2 Cómo se calcula el perfil (`core/tracks/profile.py`, sin Qt)

- **Distancia**: acumulada en 2D con haversine entre puntos consecutivos **del mismo segmento**, igual que `gpx_reader` (entre segmentos no se suma; el perfil marca el salto). La función de haversine pasa a `core/tracks/geodesy.py` y `gpx_reader` la importa de allí: una sola implementación.
- **Desnivel acumulado**: el mismo método del umbral (`ELEVATION_THRESHOLD_M` = 8 m, calibrado con Wikiloc). Así el perfil dice **los mismos números** que el catálogo y el inspector. No se cambia el cálculo (obligaría a subir `TRACK_EXTRACTOR_VERSION` y a recalibrar).
- **Suavizado, solo para dibujar**: mediana móvil sobre una ventana de distancia (propuesta: 30 m) para quitar los picos del GPS; los números (mínima, máxima, desnivel) salen de los datos sin suavizar.
- **Reducción para pintar**: mínimo y máximo por columna de píxel (como mucho dos puntos por píxel de ancho); 50 000 puntos se dibujan como ~2 000.
- Resultado: `ElevationProfileData` (distancias, altitudes, índice del punto original de cada muestra, saltos de segmento, mínimos, máximos, desnivel, tramo estimado). Opcional más adelante: pendiente por tramo (color) y eje de tiempo en vez de distancia.

### 4.3 Con qué se dibuja

`ElevationProfile(QWidget)` en `ui_helpers/widgets/elevation_profile.py`, con `QPainter`: área rellena, ejes con marcas «redondas», línea vertical y etiqueta en el cursor (distancia, altitud y, si hay, hora). Colores de `COLORS` (campos nuevos en `ThemeColors` si hacen falta).

- Por qué no QtCharts o QtGraphs (están instalados): es un solo gráfico de área; a mano son ~250 líneas, se controla el aspecto al píxel como el resto de la aplicación y no entra otro módulo de Qt.
- Por qué no dentro de la página web: el perfil debe verse igual con cualquier tecnología de mapa y probarse sin ella.

Sincronización (la hace `MapController`, no los widgets entre sí):

- Perfil → mapa: `ElevationProfile.cursor_moved(point_index | None)` → `MapView.set_track_cursor(track_id, point_index)`.
- Mapa → perfil: `MapView.track_hovered(track_id, point_index)` → `ElevationProfile.set_cursor(point_index)`. La página busca el vértice más cercano al ratón (dentro de unos píxeles) sobre la geometría completa; con 50 000 puntos es menos de 1 ms, una vez por fotograma.
- Arrastrar en el perfil selecciona un tramo → `range_selected(first, last)` → el mapa lo resalta; en edición, es la forma cómoda de **recortar** (§7).

---

## 5. Modelo de datos

### 5.1 Coordenadas de las fotos (ya existe)

`media_items.latitude`, `longitude`, `altitude`, `gps_direction` (bloque B, editables; [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md)). No hace falta ninguna columna nueva.

- **Leer para el mapa**: `core/catalog/map_queries.py`, `fetch_map_items(conn, source, filters) -> MapItems`: una sola consulta con `source_condition` que devuelve (a) los elementos con latitud y longitud (id, coordenadas, tipo, estado de la miniatura, dirección) y (b) los de tipo `track` con su `overview` y su caja. No se añaden columnas a `fetch_grid_rows`: la cuadrícula sigue pidiendo solo lo que pinta.
- **Escribir**: soltar o mover N fotos en un punto → `update_metadata_fields(conn, ids, {"latitude": ..., "longitude": ...})`, que ya existe, por la cola del inspector (`InspectorController.request_edit`). La correlación (cada foto, su punto) necesita una función nueva, `update_media_positions(conn, positions: Mapping[int, Position])`, en `core/catalog/geotagging.py`, que reutiliza `normalize_value` y `bits_for` de `editable_fields.py` (mismas validaciones y mismos bits de pendiente).
- **Índice**: no hace falta para pintar (se consulta por origen, como la cuadrícula). Para «las fotos de la zona de este track» sí conviene un índice parcial, `idx_media_geo ON media_items(latitude, longitude) WHERE latitude IS NOT NULL`: va en la migración del paso que lo use (§10, fase 6), no antes.

### 5.2 ¿Las coordenadas se escriben también en el archivo? (D1, decide el autor)

Hoy **ya está decidido para la edición a mano** (11/11/2026): lo editado en el inspector se escribe en el EXIF/XMP, en el sidecar de los RAW o en el `.arca.json`, con `write_user_data_to_files` activado. La pregunta es si el geoetiquetado **desde el mapa y por lotes** sigue la misma regla.

| Opción | A favor | En contra |
|---|---|---|
| **1. Igual que la edición a mano** (recomendada) | Un solo comportamiento; Lightroom ve las coordenadas; sobreviven a recrear el catálogo; sin código nuevo de escritura | Un arrastre o una correlación pueden reescribir cientos de originales de golpe |
| 2. Solo en la base de datos | No toca ningún archivo | Se pierde al recrear el catálogo; incoherente con el inspector (el mismo campo, dos reglas); habría que impedir que la escritura pendiente lo llevase al archivo |
| 3. Preguntar en cada operación por lotes | El usuario decide cada vez | Una pregunta más; las coordenadas «solo en la base» necesitarían una marca nueva para que no se escriban después |

Con la opción 1, las salvaguardas: la ventana de vista previa de la correlación dice cuántos archivos se van a escribir; soltar sobre el mapa más de N fotos (propuesta: 50) pide confirmación; y el deshacer del mapa (D6).

### 5.3 Tracks y sus puntos

- **Lo que hay**: una fila en `media_items` (tipo `track`, biblioteca `tracks`, salida en `latitude`/`longitude`) y su resumen en `track_details` (caja, llegada, distancia, desnivel, horas UTC, recuentos).
- **Lo nuevo (migración 4)**: `track_details.overview TEXT`: el recorrido **simplificado** (Douglas-Peucker, tolerancia ~15 m, tope de 1 000 puntos entre todos los segmentos), como polilínea codificada (el formato de Google, precisión 5; un segmento por línea). Lo calcula `TrackExtractor` → sube `TRACK_EXTRACTOR_VERSION` a 3 (los GPX se releen solos; es rápido). Sirve para pintar cientos de tracks sin abrir ningún archivo y, más adelante, para la miniatura del recorrido (PENDIENTE A.6, GPX-c).
- **Los puntos completos no van a SQLite.** Opciones consideradas:

| Opción | Valoración |
|---|---|
| **A. Leer el GPX a demanda** (recomendada) | El archivo es la fuente y no se duplica nada. 30 000 puntos se leen en décimas de segundo, en segundo plano, y se guardan en memoria (los últimos 5 tracks). Función nueva `read_gpx_points` en `core/tracks/gpx_document.py` |
| B. Tabla `track_points` | 1 000 tracks × 10 000 puntos = 10 millones de filas y cientos de MB en el catálogo, para un dato que ya está en los archivos; con un GPX ausente, el contorno de `overview` ya da para verlo |
| C. Un archivo binario por track en `cache/track/` del catálogo | Solo si se mide que A es lenta con archivos enormes; se puede añadir después sin cambiar nada más |

- **Track nuevo o editado**: no existe en el catálogo hasta que se exporta a un GPX dentro de una carpeta catalogada y esa carpeta se sincroniza (hoy solo se catalogan carpetas completas: PENDIENTE C.8). El paso de exportar ofrece sincronizarla al terminar.

### 5.4 Relación de los tracks con las colecciones

**No hace falta nada nuevo**: un track es un `media_items`, así que una colección estática (`collection_items`) ya puede contener tracks y fotos, y una inteligente puede mezclarlos con reglas. El mapa del Catálogo pinta lo que haya en el origen: los `track`, como líneas; lo que tenga coordenadas, como marcadores. Es justo «juntar los GPX de una ruta con sus fotos» (PENDIENTE, B).

Lo que queda por decidir (D4): si además se quiere la relación **calculada** («las fotos de esta ruta» sin hacer la colección a mano). Propuesta: una consulta, sin tabla nueva, `fetch_track_photos(conn, track_id, margin_s, max_distance_m)` en `map_queries.py`: fotos y vídeos cuya hora (convertida a UTC, §6) cae entre `started_at` y `ended_at` con un margen, o, si el track no tiene horas, dentro de su caja y a menos de cierta distancia del contorno. El módulo Tracks la usa para pintar las fotos junto al track ([DECISIONES.md](DECISIONES.md), «Vistas del centro»), y una acción «Crear colección con esta ruta y sus fotos» la convierte en colección estática. Una tabla de enlaces (`track_media`) solo si se quiere fijar la relación a mano foto a foto: no se propone.

---

## 6. Correlación foto-track (geoetiquetado automático)

### 6.1 Cálculo (`core/tracks/correlation.py`, sin Qt ni BD)

Entradas: los puntos del track (o de varios) con hora UTC; las fotos con su hora local (`content_created_at`), su desfase si lo tienen (`timezone_offset`) y sus coordenadas actuales; y las opciones.

1. **Hora UTC de cada foto** = hora local − zona + corrección del reloj.
   - **Zona**: la de la foto si la trae (EXIF `OffsetTimeOriginal`, columna `timezone_offset`); si no, la que elija el usuario para el lote (por defecto, la del equipo **en la fecha de la foto**, con su horario de verano: lo mismo que hace `TrackExtractor`).
   - **Corrección del reloj de la cámara**: desfase configurable en horas, minutos y segundos, con signo. Ayuda para calcularlo: elegir una foto y pinchar en el mapa dónde se hizo → se propone el desfase que la lleva al punto del track más cercano a ese sitio.
2. **Posición**: se buscan (búsqueda binaria) los dos puntos del track que rodean esa hora y se interpola linealmente (también la altitud).
   - Si entre esos dos puntos pasan más de `max_gap_s` (propuesta: 300 s; pausa del GPS o cambio de segmento), no se interpola: se toma el más cercano en el tiempo si está a menos de `max_snap_s` (propuesta: 60 s); si no, **sin posición**.
   - Fuera del intervalo del track: sin posición (salvo el margen `max_snap_s`).
3. **Resultado por foto** (`Match`): posición propuesta, estado (`INTERPOLATED`, `SNAPPED`, `NO_TRACK_TIME`, `OUT_OF_RANGE`, `NO_PHOTO_TIME`), diferencia de tiempo con el punto usado y, si la foto ya tenía coordenadas, la distancia entre la antigua y la nueva.

Fotos con la fecha incompleta (`content_date_precision` distinta de segundo) no se correlacionan.

### 6.2 Vista previa (`ui_helpers/dialogs/geotag_dialog.py` + `controllers/geotag_controller.py`)

Una ventana (es una operación por lotes: [DECISIONES.md](DECISIONES.md), «Inspector único…»), que se abre con las fotos seleccionadas y el track (o los tracks) elegidos:

- Arriba: la zona horaria, el desfase del reloj (cajas y botones de ±1 s / ±1 min) y las opciones (intervalo máximo; «Sustituir las coordenadas que ya tienen», apagado por defecto; «Escribir también la altitud», a decidir).
- En el centro: una lista (miniatura, nombre, hora, estado, diferencia) y el recuento: «132 con posición · 5 fuera del track · 3 ya ubicadas (no se cambian)».
- En el mapa del centro, mientras la ventana está abierta: las posiciones propuestas como marcadores de vista previa (`MapView.set_preview_markers`), que se mueven en vivo al tocar el desfase. El cálculo es instantáneo (cientos de fotos × búsqueda binaria), así que no necesita trabajo en segundo plano; sí la lectura inicial de los puntos y de las fotos.
- Botones: «Aplicar» (N archivos) y «Cancelar». Al aplicar: `update_media_positions` por la cola de cambios → `user_data_changed` → se refrescan el mapa, el inspector y la escritura pendiente.

El último desfase y la zona se recuerdan en `settings.json` (clave nueva en `DEFAULTS`), porque suelen repetirse con la misma cámara.

---

## 7. Edición de GPX

### 7.1 Leer sin perder nada (`core/tracks/gpx_document.py`, sin Qt)

`read_gpx` (el del extractor) es un resumen en streaming y tira los puntos: no sirve para editar. Hace falta un lector **completo y sin pérdidas**, aparte (el del extractor no se toca):

```python
@dataclass(slots=True)
class TrackPoint:
    latitude: float
    longitude: float
    elevation: float | None
    time: datetime | None          # UTC
    extra: bytes | None            # el resto de hijos del punto, tal cual (pulso, cadencia, temperatura...)
    elevation_estimated: bool = False   # altitud puesta por el modelo de elevaciones

class GpxDocument:
    root_attributes, namespaces    # version, creator, xmlns:*, schemaLocation
    metadata: bytes | None         # <metadata> entero, sin tocar
    waypoints: list[bytes]         # cada <wpt>, sin tocar
    routes: list[bytes]            # cada <rte>, sin tocar
    tracks: list[GpxTrack]         # cabecera sin tocar (name, desc, type, extensions) + segmentos
    trailing: list[bytes]          # <extensions> del documento
```

- Se lee con `defusedxml` (como hoy). Cada parte que no se edita se guarda **como fragmento XML ya serializado** (`bytes`), no como árbol: un track de 100 000 puntos ocupa decenas de MB, no cientos, y al exportar esos fragmentos se escriben tal cual.
- Los prefijos de los espacios de nombres (`gpxtpx:`, `ns3:`...) se recogen con los eventos `start-ns` y se registran antes de escribir, para que no salgan como `ns0`.
- **Qué se conserva al exportar**: `<metadata>`, waypoints, rutas, nombre, descripción y tipo de cada track, las extensiones del documento, de los tracks y de **cada punto que no se borra** (mover un punto conserva su hora y sus extensiones). **Qué no**: los comentarios XML y el formato exacto (sangrías, orden de atributos): el resultado es equivalente, no idéntico byte a byte. La autoprueba lo comprueba: leer → exportar sin editar → leer da el mismo documento.
- Rutas planificadas (`<rte>` sin `<trk>`): se editan igual, convertidas en un track de un segmento al abrir; al exportar se avisa de que salen como track.

### 7.2 Modelo en edición y deshacer (`core/tracks/track_model.py`, sin Qt)

`TrackModel` envuelve un `GpxDocument` y solo se cambia con **órdenes** (cada una sabe deshacerse):

| Orden | Qué hace |
|---|---|
| `MovePoint(ref, lat, lon)` | Mueve un punto (conserva hora y extras; la altitud queda como estaba o se marca para recalcular: D7) |
| `InsertPoint(segment, index, lat, lon)` | Inserta en un tramo (altitud y hora interpoladas entre los vecinos: D8) |
| `AppendPoint(segment, lat, lon)` | Añade al final (crear un GPX marcando puntos) o al principio |
| `DeletePoints(segment, first, last)` | Borra un punto o un rango (recortar el principio o el final es esto) |
| `SplitSegment(segment, index)` | Corta un segmento en dos por un punto |
| `JoinSegments(first, second)` | Une dos segmentos consecutivos (o de dos tracks del documento) |
| `ReverseSegment(segment)` | Invierte el sentido (útil al unir; las horas se quitan, con aviso) |
| `SetElevations(refs, values)` | Rellena o sustituye altitudes con el modelo de elevaciones |

- `EditHistory`: dos pilas (deshacer y rehacer) en Python puro. No se usa `QUndoStack` porque el modelo está en `core/` (sin Qt) y así el deshacer se prueba en la autoprueba, sin ventana. Arrastres seguidos del mismo punto se funden en una sola orden. Tope: 200 órdenes.
- Cada orden devuelve un `TrackPatch` (qué segmento y qué rango han cambiado): el controlador repinta solo eso en el mapa (`MapView.show_edit_segment`) y recalcula el perfil.
- **Unir tracks de archivos distintos**: se abre el segundo GPX y sus segmentos se añaden al documento en edición (`import_segments`); después, `JoinSegments`.

### 7.3 Validación

Al editar (en caliente, sin bloquear) y, sobre todo, antes de exportar:

- **Errores** (impiden exportar): latitud o longitud fuera de rango; ningún segmento con al menos dos puntos.
- **Avisos** (se enseñan; se puede exportar): horas que retroceden dentro de un segmento o al unir dos; puntos con hora mezclados con puntos sin ella; saltos imposibles (velocidad absurda entre dos puntos seguidos: suele ser un vértice mal arrastrado); segmentos de un solo punto (se descartan al exportar); altitudes estimadas mezcladas con medidas.
- La lista de avisos es un `list[ValidationIssue]` con el punto afectado: un clic lleva el mapa hasta él.

### 7.4 Exportar

- `write_gpx(document, path)`: GPX 1.1, UTF-8, escritura atómica (archivo temporal + sustitución, como `folder_file.py`). Un GPX 1.0 de origen se exporta como 1.1.
- **Dónde** (D2): por defecto «Exportar a GPX…» a un archivo **nuevo** (se propone `<nombre> (editado).gpx` junto al original); el original no se modifica nunca, como manda el principio del proyecto. Si el autor quiere «Guardar» sobre el original, sería una excepción nueva de ese principio (con copia `.bak`) y habría que anotarla en [CLAUDE.md](../CLAUDE.md) y [ARQUITECTURA.md](ARQUITECTURA.md).
- El atributo `creator`: se conserva el del original en los editados; en los nuevos, el nombre de la aplicación.
- Si la carpeta de destino está catalogada, al terminar se ofrece sincronizarla para que el GPX aparezca (con su `overview` y su resumen).
- Cambios sin exportar: al salir del modo edición, cambiar de track o cerrar el catálogo, se pregunta (exportar, descartar, cancelar).

### 7.5 Interacción en el mapa (modo `EDIT_TRACK` / `DRAW_TRACK`)

- Solo se pintan **asas** de los vértices visibles y con el zoom suficiente (tope ~300); con el zoom lejano se ve la línea y se edita por tramos (seleccionar en el perfil, cortar, borrar).
- Arrastrar un asa → `MovePoint`; clic sobre la línea entre dos asas → `InsertPoint`; clic en un asa + `Supr` → `DeletePoints`; menú contextual en un asa: «Cortar aquí», «Borrar desde aquí hasta el final», «Borrar hasta aquí»; en `DRAW_TRACK`, cada clic en el mapa → `AppendPoint` y doble clic termina.
- La página solo emite la intención (`edit_requested`); el cambio lo hace `TrackEditController` y vuelve como `TrackPatch`. Durante un arrastre, la página mueve el asa por su cuenta (fluidez) y confirma al soltar.

---

## 8. Rendimiento

Objetivos: 20 000 fotos con coordenadas en un origen; un track activo de 50 000 puntos; 500 tracks en contorno; nada bloquea la interfaz.

| Problema | Solución |
|---|---|
| **Miles de marcadores** | Agrupación en la página con **Supercluster** (índice espacial, cientos de miles de puntos en milisegundos). Al mover o cambiar el zoom se piden los grupos de lo visible y se pintan como mucho unos cientos de elementos. Cada grupo: miniatura de una de sus fotos y el número (como Lightroom); los marcadores sueltos, su miniatura (`arca-map://thumb/<id>`, cargada solo si se ve). Clic en un grupo: selecciona todas sus fotos |
| **Selección con grupos** | El índice acumula por grupo cuántas de sus fotos están seleccionadas (propiedad agregada de Supercluster): el grupo se resalta sin recorrer sus hijos. `set_selected_ids` con 20 000 ids (Ctrl+A) es un conjunto en JS y un repintado de lo visible |
| **Pasar los datos a la página** | Una sola llamada con una lista compacta (`[id, lat, lon, tipo, miniatura]`): 20 000 marcadores ≈ 0,7 MB de JSON. Los cambios pequeños (soltar, mover), con `update_markers`: no se reenvía todo |
| **Tracks largos** | Tres niveles: (1) el **contorno** de `track_details.overview` (≤ 1 000 puntos) para todos los tracks del origen, sin abrir archivos; (2) la **geometría completa** solo del track activo, leída en segundo plano y enviada como polilínea codificada (50 000 puntos ≈ 250 kB); (3) al pintar, Leaflet simplifica por nivel de zoom (`smoothFactor`) sobre `canvas` y recorta a lo visible. Mientras llega la completa se ve el contorno |
| **Simplificación** | `core/tracks/simplify.py`: Douglas-Peucker iterativo (sin recursión: 100 000 puntos) y codificación de polilíneas. Se usa al extraer (`overview`) y para el perfil no hace falta (reduce por píxel) |
| **Edición de tracks grandes** | Asas solo de lo visible; cada orden repinta un rango (`TrackPatch`), no el track entero; el perfil se recalcula entero (50 000 puntos: milisegundos) con un retardo de 100 ms durante los arrastres |
| **Carga en segundo plano** | Consultas con `db.execute_async` (`fetch_map_items`, `fetch_track_photos`); lectura de GPX completos en el mismo grupo de hilos (la función recibe `conn` para sacar la ruta y luego lee el archivo) con memoria de los 5 últimos; elevación del modelo como trabajo (`JobManager`) si hay que descargar teselas. Cada respuesta lleva un número de generación: las tardías se descartan (patrón de `MetadataFilterController`) y se comprueba `if self.db is None: return` |
| **Trabajo inútil** | `MapController` no consulta nada mientras el mapa no se ve: marca «pendiente» en `modelReset` y carga al mostrarse (como los módulos inactivos en `ModuleHost.refresh`). La selección se sincroniza con un retardo corto y por tramos (`selection()`), como `CenterViewController._remember_shown` |
| **Teselas** | Caché en disco, 2 peticiones simultáneas por servidor, cancelación de las que ya no se ven (Leaflet las aborta al cambiar el zoom) |
| **Arranque** | Chromium no se inicia hasta la primera vez que se abre el mapa; el import de `QtWebEngineWidgets` en `main.py` no lo arranca (medir en la fase 0 cuánto retrasa el inicio) |

---

## 9. Riesgos y preguntas abiertas (por gravedad)

**Graves (pueden cambiar el plan)**

1. **Soltar tarjetas sobre `QWebEngineView`**: que la subclase reciba los eventos de arrastre con `MEDIA_IDS_MIME` y que la coordenada del píxel sea exacta con el escalado de Windows (125-150 %). Si los eventos los recibe el widget interno, alternativa: filtro de eventos sobre él o una capa transparente encima solo mientras dura el arrastre. → Fase 0.
2. **QtWebEngine dentro de la ventana real**: al crear el primer `QWebEngineView`, Qt puede pasar la ventana entera a componerse con la GPU (parpadeo o recreación de la ventana al abrir el mapa por primera vez, y posible cambio en cómo se pintan la cuadrícula y la vista individual). Puede ser bueno (el «tearing» anotado en [PENDIENTE.md](PENDIENTE.md), B) o malo. → Fase 0, dentro de una ventana con un `QListView` grande.
3. **macOS y Linux, sin probar** (como todo el proyecto): QtWebEngine es la pieza más delicada fuera de Windows (bibliotecas del sistema y entorno aislado en Linux; firma del proceso auxiliar en macOS al empaquetar).
4. **Modificar archivos del usuario por lotes** (D1) y **sobrescribir un GPX** (D2): no son riesgos técnicos, sino de datos; el diseño propone lo conservador y deja la decisión al autor.

**Medios**

5. **Teclado**: que Chromium no se quede el foco (los atajos de clasificación deben seguir en la tira de fotos). → Fase 0.
6. **Condiciones de los servicios de teselas**: cambian; OSM estándar y OpenTopoMap no garantizan servicio y prohíben el uso intensivo; los de pago por clave pueden excluir el uso en empresa. IGN es el más seguro para España. Revisar al implementar el paso de las capas.
7. **Rendimiento del esquema `arca-map://` en Python** (decenas de teselas por movimiento, con el GIL). Alternativa dentro del plan A en §3.2. → Fase 0.
8. **Pantallas con escalado**: las teselas ráster se ven borrosas al 150 % si no se piden las del nivel siguiente a mitad de tamaño (`detectRetina`), y entonces los rótulos salen más pequeños. Hay que elegir viendo el resultado. → Fase 0 (captura para el autor).
9. **Empaquetado futuro**: +220 MB aproximados, proceso `QtWebEngineProcess.exe` y carpeta `resources` de Qt que PyInstaller debe incluir. Se anota en PENDIENTE C.9 cuando se implemente; no condiciona el diseño.
10. **Zonas horarias en la correlación**: fotos sin desfase guardado hechas en otro huso; la ventana deja elegir la zona, pero el valor por defecto (la del equipo) puede ser incorrecto en un viaje. Mejora posible: deducir la zona de las coordenadas del track (`timezonefinder`, ya anotada en `track/extractor.py`).
11. **Memoria**: un proceso Chromium (100-300 MB) más las miniaturas de los marcadores. Medir en la fase 0 con 20 000 marcadores.

**Leves / preguntas abiertas**

12. Tracks que cruzan el antimeridiano o con cajas enormes: se pintan, pero `fit_bounds` puede encuadrar mal. Sin tratamiento especial de momento.
13. Coordenadas 0, 0: la lectura ya las toma por «sin GPS» ([DECISIONES.md](DECISIONES.md), 11/11/2026); el mapa no deja soltar exactamente ahí.
14. Formatos de track distintos de GPX (`.tcx`, `.fit`, `.kml`): fuera de este diseño; el modelo interno no depende del formato, así que se podrán añadir lectores.
15. ¿Marcador con miniatura o un punto simple? (aspecto; se decide viéndolo en el paso 1.3).
16. ¿Los vídeos con GPS se pueden recolocar igual que las fotos? El mecanismo lo permite (van al `.arca.json`); se propone que sí.
17. Privacidad: los servidores de teselas ven qué zonas se consultan (no las fotos ni sus coordenadas exactas). Aceptable para uso interno; anotarlo.
18. Sección «Ubicación» del inspector con un mapa pequeño (PENDIENTE A.5): posible con una segunda `MapView`; no está en este plan.

---

## 10. Plan de implementación

Reglas para quien lo implemente: un paso cada vez, con el visto bueno del autor antes de los que tocan varios archivos; al terminar cada paso, lo que manda [CLAUDE.md](../CLAUDE.md) («Al terminar cada paso: actualizar la documentación»): `ESTADO.md` siempre, el mapa de `ARQUITECTURA.md` con cada archivo nuevo, `PRUEBAS.md` con cada autoprueba, `MODELO_DE_DATOS.md` e `INDEX.md` con la migración y la versión, `FLUJOS.md` con un apartado nuevo «Mapa», `TRAMPAS.md` con lo que se descubra y `DECISIONES.md` con lo que decida el autor. **En cada paso**, además de sus criterios: `ruff check` de lo tocado, las autopruebas de los módulos tocados y que la aplicación arranca y la cuadrícula, la vista individual y el inspector siguen igual (lo comprueba el autor).

Antes de empezar: resolver D1, D2 y D3 (condicionan las fases 3 y 7) y recordar al autor que haga un commit.

### Resultado de la fase 0 (13/11/2026): se sigue con el plan A

Hecha en `scripts/poc_map/` y probada por el autor en Windows (pantalla al 100 %, PySide6 6.11.2, Python 3.14.8). Todos los criterios se cumplen:

| Qué | Resultado |
|---|---|
| Mapa y fluidez | Listo 134 ms después de crear la vista web; track de 10 000 puntos (8 ms) y 20 000 marcadores agrupados (47 ms), fluido al mover y hacer zoom. El autor aclara que sus tracks reales tienen de 1 000 a 10 000 puntos: el objetivo de 50 000 de §8 queda como margen, no como requisito |
| Parpadeo al crear el mapa | Apenas se nota |
| Soltar tarjetas | Funciona, con 1-3 px de diferencia (incluye lo que se mueve el ratón al soltar). **Los eventos de arrastre no llegan a la subclase de `QWebEngineView`, sino a su widget interno**: `WebMapBackend` debe poner un filtro de eventos en los hijos de la vista (como `MapWebView._watch_children` de la prueba). La capa transparente no hace falta |
| Teclado | Con la vista y sus hijos en `NoFocus`, las flechas siguen en la lista, también tras un clic en el mapa |
| Ida y vuelta Python ↔ página | 0,17 ms de mediana (máximo 0,67 ms) |
| Esquema `arca-map://` | 362 teselas sin errores (IGN MTN y OpenTopoMap; las direcciones de §3.1 valen), unos 100 ms por descarga; segunda vez y sin conexión, de la caché. El manejador se ejecuta en el hilo principal y no se nota |
| Memoria | Unos 170 MB más con el mapa vacío y unos 400-500 MB más con el track y los 20 000 marcadores cargados (714 MB en total en la prueba, que incluye una imagen de 96 MB). Es el coste de Chromium; a vigilar con datos reales |
| Cortes horizontales de la foto | **Desaparecen en cuanto existe la vista web** (antes de crearla, los mismos cortes que en la vista individual). Confirma que basta con que la ventana se componga con la GPU; ver [PENDIENTE.md](PENDIENTE.md), B |

Aprendido para la implementación (irá a [TRAMPAS.md](TRAMPAS.md) con el paso 1.3): `QNetworkRequest.setHeader(UserAgentHeader, ...)` no acepta `bytes` desde Python (avisa y no pone la cabecera): usar `setRawHeader`; una lista de JavaScript devuelta por `runJavaScript` no llega bien a Python: devolver texto JSON. La prueba se conserva como referencia hasta el paso 1.5 y después se borra.

### Fase 0 — Prueba de concepto (no es código de producción)

**Objetivo**: decidir entre el plan A y el B con datos, en la máquina del autor.

**Archivos** (nuevos, aislados; se borran o se quedan como herramienta, a decidir): `scripts/poc_map/poc_map.py`, `scripts/poc_map/page/` (página, JS, Leaflet). No se toca nada de la aplicación ni se usa `qtpy` todavía (basta que funcione; el código de verdad se escribe en la fase 1).

**Qué hace**: una ventana con un `QListView` a la izquierda (modelo sencillo que arrastra `MEDIA_IDS_MIME`, con 2-3 miniaturas de prueba), y un `QWebEngineView` a la derecha, dentro de un `QStackedWidget`, con:

1. capa topográfica del IGN (MTN) y OpenTopoMap, con un botón nativo para cambiar;
2. un GPX real del autor (p. ej. Ordesa, y otro de más de 30 000 puntos) dibujado como línea;
3. un marcador arrastrable que, al soltarlo, imprime en Python su latitud y longitud (ida y vuelta por `QWebChannel`);
4. soltar un elemento de la lista sobre el mapa: Python imprime los `id` y la coordenada, y aparece un marcador justo bajo el puntero;
5. las teselas servidas por el esquema `arca-map://` con caché en una carpeta temporal (segunda ejecución sin red: se ven);
6. 20 000 marcadores aleatorios agrupados (Supercluster);
7. la vista web sin foco: pulsar teclas con el ratón sobre el mapa sigue moviendo la selección de la lista;
8. una tercera página con una foto grande que se arrastra con el ratón (dibujada con `QPainter`, como la vista individual a 1:1), para ver si los cortes horizontales al arrastrar deprisa cambian **antes y después** de crear la vista web (la ventana pasa a componerse con la GPU; §1.5). Solo se observa: no decide entre el plan A y el B.

**Como abre una ventana, la ejecuta el autor** (`.venv\Scripts\python.exe scripts/poc_map/poc_map.py`); el guion escribe en la consola las medidas (tiempo hasta `ready`, memoria del proceso y de sus hijos, tiempo de `set_markers`, error en píxeles de la soltada).

**Se sigue con el plan A si**: (a) el mapa se ve y se mueve con fluidez con el track grande y los 20 000 marcadores (sin tirones apreciables al arrastrar o hacer zoom); (b) la soltada cae a menos de 2 px del puntero con el escalado de pantalla del autor; (c) el primer `ready` tarda menos de ~3 s y no hay parpadeo molesto de la ventana (lo juzga el autor); (d) las teclas no se quedan en el mapa; (e) arrastrar el marcador responde sin retraso visible.

**Se pasa al plan B (Qt Location) si** falla (a), (b), (c) o (e) sin arreglo razonable (para (b) hay tres intentos: subclase, filtro de eventos, capa transparente), o si QtWebEngine no llega a pintar en la máquina del autor ni con el modo por software. Fallar solo (5) no cambia de plan: teselas por `https` con la caché de WebEngine. Si se pasa a B, se repite esta misma prueba con `QQuickWidget` + `Map` antes de seguir.

### Fase 1 — Componente base

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| **1.1** Capas y almacén de teselas | `TILE_LAYERS` y `TileStore` (rutas, escritura atómica, caducidad, tope) | Nuevos: `core/maps/__init__.py`, `tile_layers.py`, `tile_store.py` | Fase 0 (direcciones comprobadas) | Autopruebas: plantillas de dirección, ruta de cada tesela, caducidad, limpieza por tamaño (carpeta temporal, sin red) | Módulos nuevos sin Qt: nada los importa todavía |
| **1.2** Tipos y contrato | `map_types.py` (dataclasses, enumeraciones) y `MapBackend` | Nuevos: `ui_helpers/map/__init__.py`, `map_types.py`, `map_backend.py` | — | Autoprueba de `map_types` (validación de coordenadas, `MapBounds` de una lista) | Nada los importa todavía |
| **1.3** `MapView` con WebEngine | Mapa que se ve, con capas, marcadores agrupados, selección y encuadre; esquema `arca-map://` (recursos y teselas) | Nuevos: `map_view.py`, `web_backend.py`, `web_bridge.py`, `map_scheme.py`, `resources/map/*`. **`main.py`**: registrar el esquema e importar WebEngine antes de `QApplication` | 1.1, 1.2 | Autoprueba **con ventana** (la ejecuta el autor): mapa con 5 000 marcadores, cambio de capa, clic selecciona (se imprime la señal), `fit_content`. Colores solo por variables del tema | La aplicación arranca igual (medir el tiempo de arranque antes y después); nada usa aún `MapView` |
| **1.4** Miniaturas y tracks en el mapa | `arca-map://thumb/`, `set_tracks`, `set_track_geometry`, `set_active_track`, `set_track_cursor`, `track_hovered` | `map_scheme.py`, `web_backend.py`, `arca_map.js` | 1.3 | En la autoprueba con ventana: un GPX real en contorno y en detalle; el cursor sigue al ratón | Igual que 1.3 |
| **1.5** Soltar y mover | `media_dropped`, `markers_moved`, `set_drop_enabled`, menú contextual | `web_backend.py`, `arca_map.js` | 1.3 | En la autoprueba: soltar desde una lista y arrastrar un marcador imprimen ids y coordenadas correctas | Igual |

### Fase 2 — Modo Catálogo (solo ver y seleccionar)

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| **2.1** Contorno de los tracks | Migración 4 (`track_details.overview`), simplificación y lectura | Nuevos: `core/tracks/__init__.py`, `geodesy.py`, `simplify.py`. Cambios: `catalog_schema.py` (migración al final), `track/gpx_reader.py` (usa `geodesy`; recoge los puntos para el contorno), `track/extractor.py` (`TRACK_EXTRACTOR_VERSION` = 3) | — | Autopruebas: Douglas-Peucker (tolerancia, tope, segmentos), codificar y decodificar, migración sobre un catálogo v3. Un catálogo real se abre, pasa a v4 y relee los GPX | Autopruebas de `catalog_schema`, `gpx_reader`, `extractor` y `processor`; la distancia y el desnivel de Bujaruelo, Ordesa y Pineta **no cambian** (comparar antes y después con `track/inspect_cli`) |
| **2.2** Consulta del mapa | `fetch_map_items(conn, source, filters)` | Nuevo: `core/catalog/map_queries.py` | 2.1 | Autoprueba con un catálogo en memoria: mismo recuento que `count_grid_items` para los que tienen coordenadas; tracks con su contorno; respeta el filtro | No toca `media_queries` (solo importa `source_condition`) |
| **2.3** Página y controlador | `MapPage` (crea `MapView` al mostrarse), `MapController` (carga al ver el mapa, generación, selección en los dos sentidos, doble clic → vista individual, guarda capa y encuadre). `CatalogModule.views()` añade `MAP`; icono y texto de la vista | Nuevos: `ui_helpers/widgets/map_page.py`, `controllers/map_controller.py`. Cambios: `center_views.py` (icono; `MapOptions`), `base.py` (`map_options`), `catalog_module.py`, `main_window_controller.py` (**solo** crear el controlador y añadir la página en `_conectar_vistas`), `app_constants.py` (icono), `.qrc` + `build_ui.py`, `app_config_manager.py` (claves nuevas en `DEFAULTS`) | 1.3-1.5, 2.2; D9 | Catálogo: el botón «Mapa» muestra las fotos con GPS de lo elegido a la izquierda y los tracks; cambiar de carpeta o de filtro actualiza el mapa; seleccionar en el mapa selecciona en la cuadrícula (se ve al volver con G) y al revés; el inspector sigue la selección; la vista se recuerda por módulo | Autoprueba de `center_views` y `module_view_state`; con la vista en cuadrícula o individual, todo igual; Imagen no ofrece aún el mapa |
| **2.4** Opciones | Página «Mapa» en la ventana de opciones: capa por defecto, capas del usuario (añadir, cambiar, quitar), tamaño de la caché, vaciarla | `settings_dialog.py`, `app_config_manager.py` | 2.3 | Las opciones se guardan y se aplican (`apply_settings`) | El resto de páginas, igual |

### Fase 3 — Modo Imagen (geoetiquetar)

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| **3.1** Tira de fotos (según D3) | En `MapPage`, una tira horizontal debajo del mapa: un segundo `MediaGridView` con el **mismo modelo y el mismo `selectionModel`** que la cuadrícula; atajos con `GridActions.watch` | `map_page.py`, `map_controller.py`, `image_module.py` (`views`, `map_options`) | 2.3 | En Imagen, vista «Mapa»: tira con las fotos del origen; la selección de la tira, la del mapa y la de la cuadrícula son la misma; los atajos («3», «P») funcionan con el ratón sobre el mapa | La cuadrícula no cambia (mismo modelo); probar selección múltiple y Ctrl+A |
| **3.2** Soltar para ubicar | `media_dropped` → `update_metadata_fields` por `InspectorController.request_edit`; confirmación a partir de N; el marcador aparece sin recargar todo | `map_controller.py` | 3.1; D1 | Arrastrar una o varias fotos de la tira al mapa: aparecen ahí; el inspector («Metadatos», GPS) muestra las coordenadas; con la escritura activada, Lightroom las lee | Autoprueba de `media_queries`; la edición del GPS en el inspector sigue igual |
| **3.3** Recolocar y quitar | `markers_moved` (igual que 3.2); menú contextual «Quitar la ubicación» (latitud y longitud a vacío) | `map_controller.py` | 3.2; D7 | Arrastrar un marcador lo mueve y queda pendiente de escribir; quitar la ubicación lo borra del mapa | — |
| **3.4** Deshacer en el mapa (según D6) | Pila sencilla de «ids → coordenadas anteriores» en `MapController`, Ctrl+Z con el mapa a la vista | `map_controller.py` (si crece, `controllers/geotag_history.py`) | 3.3 | Ctrl+Z devuelve las fotos a donde estaban (o las deja sin ubicación) | Ctrl+Z no hace nada fuera del mapa |
| **3.5** Ver quién no tiene ubicación | Campo «Ubicación GPS» (tiene / no tiene) en `smart_fields.py` si no existe, y un ajuste de fábrica «Sin ubicación» en `filter_presets.py` | `smart_fields.py`, `filter_presets.py` | — | El filtro deja en la tira solo las fotos sin GPS | Autopruebas de `smart_fields`, `smart_rules`, `filter_presets` |

### Fase 4 — Modo Tracks: ver

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| **4.1** Lector completo | `GpxDocument`, `TrackPoint`, `read_gpx_document`, `read_gpx_points` (solo la geometría, rápido) | Nuevo: `core/tracks/gpx_document.py` | 2.1 | Autoprueba: GPX 1.0 y 1.1, varios segmentos, extensiones, rutas; mismo número de puntos que `read_gpx` | Módulo nuevo; `gpx_reader` no se toca |
| **4.2** Módulo Tracks | `TracksModule` con barra («Biblioteca - Tracks», «Carpetas», «Fechas» reutilizando `FolderSection` y `DateSection` con `library="tracks"`), vistas mapa (inicial) y cuadrícula, orden y columnas de filtro propios; botón en la toolbar | Nuevos: `tracks_module.py`, `ui_helpers/sidebars/tracks_sidebar.py`. Cambios: `registry.py`, `ui/main_window.ui` (botón) + `build_ui.py`, `mode_toolbar.py`, `grid_orders.py` (distancia, desnivel, si se quieren) | 2.3 | El módulo aparece, lista los GPX y los muestra en el mapa en contorno; se recuerda como los demás | Catálogo e Imagen, igual; autoprueba de `module_view_state` |
| **4.3** Track activo con detalle | Al elegir un track: geometría completa en segundo plano (memoria de 5), encuadre, resaltado; los demás, atenuados | `map_controller.py` | 4.1, 4.2 | Un GPX de 30 000 puntos se ve entero y nítido al acercar; cambiar de track deprisa no mezcla respuestas | — |
| **4.4** Fotos de la ruta (según D4) | `fetch_track_photos` y su pintado junto al track; acción «Crear colección con esta ruta y sus fotos» | `map_queries.py`, `map_controller.py`, `tracks_module.py`; migración con `idx_media_geo` si se mide que hace falta | 4.3 | Las fotos hechas durante la ruta aparecen como marcadores; la colección creada se ve en el Catálogo con su mapa | Autoprueba de `map_queries` |

### Fase 5 — Elevación

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| **5.1** Cálculo del perfil | `build_profile(points) -> ElevationProfileData` | Nuevo: `core/tracks/profile.py` | 4.1 | Autoprueba: distancia y desnivel **iguales** a los de `read_gpx` con los mismos archivos; saltos de segmento; reducción por píxel | Módulo nuevo |
| **5.2** Widget del perfil | `ElevationProfile` (dibujo, cursor, selección de tramo) | Nuevo: `ui_helpers/widgets/elevation_profile.py`; colores nuevos en `theme_colors.py` si hacen falta | 5.1 | Autoprueba con ventana (el autor): un perfil real, cursor con el ratón; aspecto a su gusto | Autoprueba de `theme_colors` |
| **5.3** Sincronización | Perfil bajo el mapa en Tracks (`map_options.show_profile`), cursor en los dos sentidos, tramo resaltado | `map_page.py`, `map_controller.py` | 5.2, 4.3 | Pasar por el perfil mueve el punto en el mapa y al revés, sin retraso | Catálogo e Imagen no muestran perfil |
| **5.4** Altitud del modelo | `dem.py` (decodificar terrarium, interpolar), capa `dem` en el almacén, trabajo en segundo plano; perfil «estimado» para GPX sin `ele` | Nuevo: `core/maps/dem.py`; `map_controller.py` | 5.3, 1.1 | Autoprueba con una tesela de prueba generada (sin red). Una ruta planificada sin altitud muestra un perfil creíble (comparar un track real con y sin su `ele`) | — |

### Fase 6 — Correlación foto-track

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| **6.1** Cálculo | `correlate(points, photos, options) -> list[Match]` | Nuevo: `core/tracks/correlation.py` | 4.1 | Autoprueba: interpolación, pausa larga, fuera de rango, zona y desfase, foto sin hora | Módulo nuevo |
| **6.2** Guardar posiciones distintas | `update_media_positions` (mismos bits y validaciones que `update_metadata_fields`) | Nuevo: `core/catalog/geotagging.py` | — | Autoprueba: bits de pendiente, par latitud-longitud, no toca otras columnas | Autoprueba de `editable_fields` y `media_queries` |
| **6.3** Ventana de vista previa | `GeotagDialog` + `GeotagController`; marcadores de vista previa en el mapa; desfase recordado | Nuevos: `ui_helpers/dialogs/geotag_dialog.py`, `controllers/geotag_controller.py`; menú de la cuadrícula o del track (`grid_actions.py`); `app_config_manager.py` | 6.1, 6.2, 3.2; D1 | Con una salida real (fotos + GPX del mismo día): las posiciones propuestas siguen el track; cambiar el desfase las mueve en vivo; «Aplicar» las guarda y quedan pendientes de escribir | La ventana se abre sola: la prueba el autor |

### Fase 7 — Edición de GPX

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| **7.1** Exportar sin pérdidas | `write_gpx`; ida y vuelta | `core/tracks/gpx_document.py` | 4.1 | Autoprueba: leer → escribir → leer da lo mismo (extensiones, waypoints, metadatos, prefijos); con GPX reales del autor (Garmin, Wikiloc, móvil), `read_gpx` da el mismo resumen antes y después | — |
| **7.2** Modelo y deshacer | `TrackModel`, órdenes, `EditHistory`, `TrackPatch`, validación | Nuevo: `core/tracks/track_model.py` (si pasa de ~400 líneas, `track_commands.py` y `track_validation.py`) | 7.1 | Autoprueba: cada orden y su deshacer; fusión de arrastres; avisos de validación | Módulo nuevo |
| **7.3** Editar en el mapa | `TrackEditController`, modo `EDIT_TRACK` (asas, mover, insertar, borrar), barra de edición nativa (deshacer, rehacer, exportar, salir), aviso de cambios sin exportar | Nuevo: `controllers/track_edit_controller.py`; `web_backend.py`, `arca_map.js`, `map_page.py`, `tracks_module.py` | 7.2, 5.3; D2 | Mover, insertar y borrar puntos de un track real; Ctrl+Z / Ctrl+Y; el perfil se actualiza; «Exportar a GPX…» crea un archivo que abre bien en otro programa; el original no cambia (comparar su fecha y tamaño) | Fuera del modo edición, el mapa se comporta igual |
| **7.4** Recortar, cortar y unir | Selección de tramo en el perfil → borrar; «Cortar aquí»; unir segmentos; añadir los de otro GPX | `track_edit_controller.py`, `arca_map.js` | 7.3 | Recortar el principio y el final de un track; unir dos GPX de una misma salida; los avisos de horas aparecen | — |
| **7.5** Crear un GPX nuevo | Modo `DRAW_TRACK`: marcar puntos, altitud del modelo, exportar a una carpeta (y ofrecer sincronizarla) | `track_edit_controller.py`, `tracks_module.py` | 7.3, 5.4 | Se dibuja una ruta, se exporta y, tras sincronizar la carpeta, aparece en Tracks con su distancia y su perfil estimado | — |

### Después (sin fecha)

Descarga de zonas para usarlas sin conexión; sección «Ubicación» del inspector con mapa; miniatura del recorrido en la tarjeta de los tracks (con `overview`); rumbo de la foto (`gps_direction`) dibujado y editable en el mapa; pendiente por colores en el perfil; MDT05 del IGN; otros formatos de track.

### Sobre el orden

Se mantiene el sugerido (base → Catálogo → Imagen → Tracks: ver, elevación, edición). Encaja con la arquitectura: el Catálogo solo necesita «pintar lo del origen», Imagen añade escribir coordenadas con un mecanismo que ya existe, y Tracks es el único que pide un módulo nuevo y un modelo de edición. El único añadido es la **correlación (fase 6) entre la elevación y la edición**: necesita el lector completo (4.1) y el geoetiquetado (fase 3), no depende de editar GPX y da valor antes. Las fases 5, 6 y 7 son independientes entre sí a partir de la 4: el autor puede cambiar su orden.

---

## 11. Decisiones pendientes del autor (detalle)

- **D1. Escritura de las coordenadas en los archivos.** Opciones y salvaguardas en §5.2. Recomendación: la misma regla que la edición a mano. Bloquea el paso 3.2.
- **D2. Guardar un GPX editado.** Recomendación: siempre «Exportar a GPX…» a un archivo nuevo; el original no se toca. Alternativa: permitir «Guardar» con copia `.bak` (excepción nueva del principio de los originales). Bloquea 7.3.
- **D3. Modo Imagen: cómo conviven la cuadrícula y el mapa.** (a) Mapa con una **tira de fotos** debajo, como el módulo Mapa de Lightroom (recomendada: reutiliza el modelo y la selección; el mapa conserva el ancho); (b) cuadrícula y mapa lado a lado con un separador. También: si el Catálogo lleva la tira. Bloquea 3.1.
- **D4. «Fotos de una ruta».** Colección a mano (ya funciona) y, en Tracks, cálculo por hora y cercanía con sus umbrales (margen de tiempo, distancia máxima). Bloquea 4.4.
- **D5. Capas de partida** y si interesa alguna con clave. Bloquea 1.1 (la lista) y 2.4.
- **D6. Deshacer en el mapa.** La aplicación no tiene deshacer; arrastrar por error es fácil. Recomendación: sí, limitado al mapa y a la sesión. Bloquea 3.4.
- **D7. Altitud al recolocar una foto.** Dejarla, vaciarla o rellenarla con el modelo de elevaciones. Recomendación: dejarla (como Lightroom) y ofrecer el relleno más adelante. Afecta a 3.3.
- **D8. Hora de los puntos insertados en un GPX.** Interpolada por distancia (recomendada: algunos servicios rechazan tracks con puntos sin hora) o sin hora. Afecta a 7.2.
- **D9. Textos y aspecto**: icono y atajo de la vista «Mapa», nombres de las capas, textos de la ventana de correlación, de la barra de edición y de los avisos; marcador con miniatura o punto. Cada paso los propone antes de escribirlos.
- **D10. Identificación ante los servidores de teselas**: `User-Agent` con el nombre y la versión de la aplicación; OSM recomienda añadir una forma de contacto. Recomendación: sin datos personales, salvo que el autor quiera ponerlos.
