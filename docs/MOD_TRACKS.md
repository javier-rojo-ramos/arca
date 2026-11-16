# Arca Media — Módulo Tracks y mapa (`MapView`): arquitectura y plan

> Documento del módulo Tracks (`TracksModule`, biblioteca `tracks`: los GPX) y del **componente de mapa**, que usan también el Catálogo e Imagen. Hasta el 16/11/2026 se llamaba `MAPA.md` ([HISTORIAL.md](HISTORIAL.md) lo cita con ese nombre). Tiene dos partes: **I, arquitectura** (secciones 0 a 9) y **II, planificación** (secciones 10 y 11; fases y pasos, con los códigos `TRK` de [PENDIENTE.md](PENDIENTE.md) y el mismo número que aquí).
> **Estado (16/11/2026): hechas las fases 0 a 5; pendientes, la 6 (edición), la 7 (creación) y la 8 (fotos y tracks).** Las secciones conservan su número de siempre: el código y los demás documentos las citan (§5.3, §10, §11...). Si el código y este documento no coinciden, manda el código.
> Índice: [INDEX.md](INDEX.md). Lo que queda del mapa fuera de Tracks: `GEN 8` de [PENDIENTE.md](PENDIENTE.md).

## Resumen

**Objetivo**: ver en un mapa lo que hay en el catálogo (fotos como marcadores, tracks como líneas), ubicar las fotos, y un módulo Tracks para ver los GPX con su perfil de elevación, editarlos y crearlos.

**En qué punto está**

| Fase | Qué | Estado |
|---|---|---|
| 0 | Prueba de concepto (QtWebEngine + Leaflet) | Hecha el 13/11/2026 |
| 1 | Componente base (`MapView`) | Hecha el 13/11/2026 |
| 2 | Mapa en el Catálogo (ver y seleccionar) | Hecha el 13/11/2026 |
| 3 | Mapa en Imagen (ubicar fotos, tira de fotos, deshacer) | Hecha el 13/11/2026 |
| 4 | Tracks, lo básico (módulo, track activo, waypoints, inspector, recorrido en la tarjeta, actividad) | Hecha el 14/11/2026 |
| 5 | Perfil de elevación | Hecha el 15/11/2026 (el 5.4, eje por tiempo, en espera) |
| 6 | Edición de los GPX | Pendiente (`TRK 6`) |
| 7 | Creación de tracks | Pendiente (`TRK 7`) |
| 8 | Fotos y tracks | Pendiente (`TRK 8`) |

Lo entregado y lo que falta por comprobar de cada fase, en [ESTADO.md](ESTADO.md); cómo funciona hoy, en [FLUJOS.md](FLUJOS.md) §16.

**Las ideas del diseño**

1. **Tecnología: QtWebEngine + Leaflet + `QWebChannel`**, con los recursos (Leaflet, JS y CSS propios) en local, sin CDN. Motivo: los tres requisitos imprescindibles (topográfico, elevación, edición de GPX) salen con piezas maduras y la parte difícil (editar miles de vértices, agrupar miles de marcadores) es mucho más barata en un lienzo web que en QML. **Plan alternativo: Qt Location (QML) en un `QQuickWidget`**; lo decide la fase 0 con criterios medibles (§1.4 y §10).
2. **`MapView(QWidget)` es una fachada**: recibe datos sencillos (`MapMarker`, `MapTrack`), emite intenciones (selección, soltar, mover, editar) y **nunca cambia datos**. La tecnología queda detrás de un `MapBackend`: cambiar de plan no toca los módulos.
3. **El mapa es una vista más del centro** (`CenterView.MAP`, que ya existe): muestra **lo mismo que la cuadrícula** (mismo `GridSource` y mismo filtro), con las fotos como marcadores y los tracks como líneas. Así el modo Catálogo no necesita nada especial: una colección estática ya puede contener tracks y fotos (los tracks son filas de `media_items`).
4. **El modelo vive en Python, no en JavaScript**: la página solo pinta y avisa. El track en edición, el deshacer, la validación, el perfil y la correlación están en `core/` sin Qt, con autoprueba.
5. **Perfil de elevación: widget nativo dibujado con `QPainter`** (colores del tema), no dentro de la página web.
6. **Teselas por un esquema propio** (`arca-map://`) servido desde Python: caché en disco controlada, sin conexión, `User-Agent` correcto y claves fuera del JavaScript. Capas de partida: IGN España (MTN ráster, base y ortofoto) y OpenTopoMap.
7. **Elevación**: la `ele` del GPX; si falta, teselas «terrarium» (AWS Terrain Tiles) decodificadas con Pillow. Sin dependencias nuevas.
8. **Puntos de los tracks: no se guardan en SQLite.** El GPX es la fuente; en la base solo va un **contorno simplificado** por track (columna nueva `track_details.overview`, migración 4) para pintar muchos a la vez. La geometría completa se lee del archivo a demanda, en segundo plano.
9. **Coordenadas de las fotos**: se reutiliza tal cual la edición del GPS del 11/11/2026 (`update_metadata_fields`, bits de pendiente, escritura con las reglas de `core/userdata/`).
10. **Orden**: fase 0 → componente base → Catálogo → Imagen → Tracks (lo básico, el perfil de elevación, la edición y la creación; las fotos de la ruta y la correlación, al final). El de Tracks se revisó con el autor el 14/11/2026 (§10).

**Decisiones del autor** (detalle en §11). Abiertas: **D4** (para `TRK 8`), **D8** (`TRK 6.2`), **D12** (`TRK 6.5`), **D13** (`TRK 7.2`) y **D9** (los textos, en cada paso).

| # | Decisión | Recomendación o lo decidido |
|---|---|---|
| ~~D1~~ | Geoetiquetar desde el mapa escribe en los archivos: **decidido el 13/11/2026** | Sí, con la regla de la edición del GPS en el inspector; confirmación al soltar muchas fotos a la vez |
| ~~D2~~ | Editar un GPX existente: ¿se sobrescribe o siempre se exporta a otro archivo? | **Decidida el 16/11/2026 (el autor): se guarda sobre el propio GPX, sin generar copias.** (La recomendación era: siempre a un archivo nuevo) |
| ~~D3~~ | Modo Imagen: tira de fotos debajo del mapa: **decidido el 13/11/2026** | Al ancho del centro; ocultable con un botón en el extremo derecho de la barra inferior (solo con el mapa) y con F9 (F6 hasta el 15/11/2026); alto ajustable y recordado (100 px como mínimo); tarjetas compactas, sin banda; también en el mapa del Catálogo (confirmado por el autor) |
| D4 | «Fotos de una ruta»: ¿basta con una colección hecha a mano, o se calcula (por hora y cercanía)? | Las dos: la colección ya funciona; en Tracks, calculado |
| ~~D5~~ | Capas de partida: **decidido el 13/11/2026** (§3.1) | Callejero de OpenStreetMap, tres del IGN y OpenTopoMap, sin claves |
| ~~D6~~ | Deshacer en el mapa: **decidido el 13/11/2026** | Ctrl+Z, lo hecho en el mapa, mientras la aplicación esté abierta (si se hace un deshacer global, el mapa será el primero en usarlo) |
| ~~D7~~ | Al recolocar una foto, su altitud: **decidido el 13/11/2026** | Se deja como está |
| D8 | Puntos insertados en un GPX: ¿hora interpolada o sin hora? | Interpolada por distancia entre los dos vecinos |
| D9 | Textos, icono y atajo de la vista «Mapa»; textos de las capas | Los propone cada paso; decide el autor |
| ~~D10~~ | Identificación ante los servidores de teselas: **decidido el 13/11/2026** | `ArcaMedia/<versión>`, sin datos personales |
| ~~D11~~ | La banda del perfil y la tira de fotos: **decidido el 15/11/2026** | Conviven bajo el mapa, cada una con su botón; en Tracks la tira empieza oculta |
| D12 | Las horas al invertir un track | Quitarlas, con aviso |
| D13 | El servicio de enrutado | Sin elegir: se compara al llegar al paso |

---

# Parte I — Arquitectura

Las secciones 1 a 9 son el diseño que se escribió el 13/11/2026, antes de implementar. **Contrastado con el código el 16/11/2026**: lo que describen de lo ya hecho (§1 a §5 y §8) se ha corregido donde el código es distinto, y lo que aún no existe está marcado como **pendiente**. §6 (correlación foto-track) y §7.2 a §7.5 (edición de GPX) son diseño de lo pendiente; §7.4 hay que rehacerlo en el paso 6.1 (D2: un GPX editado se guarda sobre su propio archivo). No se ha revisado línea a línea el JavaScript de la página ni cada método: si algo no coincide, manda el código.

## Lo que hay hecho (16/11/2026)

Dónde está cada pieza ya implementada. Qué hace cada archivo, en el mapa de [ARQUITECTURA.md](ARQUITECTURA.md) y en la cabecera de cada `.py`.

| Capa | Archivos | Qué hacen |
|---|---|---|
| Componente de mapa | `ui_helpers/map/` (`map_view.py`, `map_backend.py`, `web_backend.py`, `web_bridge.py`, `map_scheme.py`, `map_types.py`); `resources/map/` (`index.html`, `arca_map.js`, `arca_map.css`, `vendor/`) | `MapView`, la fachada; detrás, la página con Leaflet y el esquema `arca-map://` |
| Capas y teselas | `core/maps/` (`tile_layers.py`, `tile_store.py`); `ui_helpers/dialogs/map_layer_dialog.py` | Las capas, la caché en disco y las capas propias de Opciones > Mapa |
| Mapa en la ventana | `controllers/map_controller.py`, `controllers/map_framing.py`; `ui_helpers/widgets/map_page.py`, `map_filmstrip.py` | La vista «Mapa» del centro, el encuadre recordado por módulo y la tira de fotos |
| Consultas y cambios | `core/catalog/map_queries.py`, `geotagging.py`, `track_stats.py`; `controllers/undo_history.py` | Lo que pinta el mapa, ubicar fotos (con deshacer) y los datos del inspector |
| Lectura de los GPX | `core/metadata/track/` (`gpx_reader.py`, `extractor.py`); `core/tracks/gpx_document.py` | El resumen para el catálogo (`TRACK_EXTRACTOR_VERSION`) y el lector completo, sin pérdidas |
| Cálculos sobre recorridos | `core/tracks/` (`geodesy.py`, `simplify.py`, `profile.py`, `activities.py`) | Distancias, el contorno simplificado, el perfil y la lista de actividades |
| Módulo Tracks | `controllers/app_modules/tracks_module.py` (sobre `library_module.py`); `ui_helpers/sidebars/library_sidebar.py` | El módulo, con su barra (biblioteca, carpetas y fechas) |
| Track activo y perfil | `controllers/track_detail_controller.py`, `track_profile_controller.py`; `ui_helpers/widgets/elevation_profile.py`; `ui_helpers/helpers/profile_painter.py`, `profile_style.py`, `profile_format.py` | El recorrido completo del track elegido y la banda del perfil, sincronizada con el mapa |
| Inspector, tarjeta y opciones | `ui_helpers/inspector/track_section.py`; `ui_helpers/helpers/track_outline.py`; `ui_helpers/dialogs/tracks_settings_page.py` | La sección «Track», el recorrido dibujado en la tarjeta y Opciones > Tracks |

**Todavía no existe** (lo crearán las fases 6 a 8): `core/tracks/track_model.py` (edición), `core/tracks/cleanup.py`, `core/tracks/correlation.py`, `core/maps/dem.py` (modelo de elevaciones), `core/maps/routing.py` y `controllers/track_edit_controller.py`.

---

## 0. Punto de partida (lo que había antes de empezar el mapa)

Lo que existía el 13/11/2026 y se ha reutilizado (comprobado entonces en el código; hoy el módulo Tracks ya existe y `registry.py` no tiene módulos provisionales):

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

> **Cómo quedó**: se eligió y se implementó la opción A (resultado de la fase 0, en §10). En `resources/map/vendor/` están Leaflet 1.9.4 y Supercluster 8.0.1, sin modificar, con sus licencias y un `LEEME.txt`. El resto de la sección es el razonamiento de la elección, que sigue valiendo.

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

**Relación con la «isla QML» de la vista individual** (sugerida para los cortes horizontales al arrastrar a 1:1, resueltos el 13/11/2026 al componerse la ventana con la GPU: [ESTADO.md](ESTADO.md)): son dos decisiones independientes y la propuesta no cambia. Que la vista individual acabe usando QML quitaría a la opción B la pega de «un lenguaje nuevo», pero no sus puntos débiles (madurez de Qt Location y edición de tracks grandes). Lo que sí comparten: un `QWebEngineView`, un `QQuickWidget` y un `QOpenGLWidget` hacen los tres que la ventana pase a componerse con la GPU. Puede que, con solo existir el mapa, los cortes desaparezcan o cambien; no se sabe hasta probarlo, así que la fase 0 lo mide (punto 8) antes de decidir nada sobre la vista individual. Si hiciera falta actuar, `QOpenGLWidget` (ya anotado en PENDIENTE) lo resuelve sin meter QML.

---

## 2. API del componente

### 2.1 Dónde vive cada cosa

```
ui_helpers/map/                       ── Componente de mapa ──
  map_view.py          ► MapView(QWidget): la fachada. Lo ÚNICO que conocen los módulos y controladores
  map_types.py           MapMarker, MapTrack, MapWaypoint, MapBounds, MapViewport, MapHit, HitKind,
                         MapMode, SelectionMode (dataclasses y enumeraciones; sin Qt)
  map_backend.py         MapBackend: contrato interno (lo que MapView pide a la tecnología)
  web_backend.py         WebMapBackend: QWebEngineView + QWebChannel + página local
  web_bridge.py          MapBridge(QObject): ranuras y señales expuestas a JavaScript
  map_scheme.py          MapSchemeHandler: sirve arca-map:// (recursos, teselas, miniaturas)
resources/map/           index.html, arca_map.js, arca_map.css, vendor/ (Leaflet, Supercluster)
ui_helpers/widgets/map_page.py            MapPage(QWidget): página del centro (mapa + perfil + tira de fotos)
ui_helpers/widgets/map_filmstrip.py       La tira de fotos bajo el mapa
ui_helpers/widgets/elevation_profile.py   ElevationProfile(QWidget): perfil dibujado con QPainter
                                          (con ui_helpers/helpers/profile_painter.py, profile_style.py, profile_format.py)
controllers/map_controller.py             MapController: une MapView con el modelo, la selección y la BD
controllers/map_framing.py                MapFraming: el último encuadre de cada módulo (sin Qt)
controllers/track_detail_controller.py    El recorrido completo, los waypoints y el perfil del track activo
controllers/track_profile_controller.py   La banda del perfil y su sincronización con el mapa
controllers/undo_history.py               UndoHistory: Ctrl+Z (hoy, lo hecho en el mapa)
controllers/app_modules/tracks_module.py  TracksModule
core/maps/               tile_layers.py (► lista de capas), tile_store.py (caché en disco)
core/tracks/             geodesy.py, gpx_document.py, simplify.py, profile.py, activities.py
core/catalog/            map_queries.py, geotagging.py, track_stats.py

PENDIENTE (fases 6 a 8; aún no existen):
controllers/track_edit_controller.py      TrackEditController: sesión de edición, deshacer, guardar
core/maps/               dem.py (modelo de elevaciones), routing.py (enrutado)
core/tracks/             track_model.py (edición), cleanup.py (errores del GPS), correlation.py (fotos por la hora)
map_types.py             TrackEditIntent, TrackPatch y los modos EDIT_TRACK / DRAW_TRACK de MapMode
```

`MapView` **no** se promociona en el `.ui`: lo crea `MapPage.map_view()` la primera vez que se pide (y avisa con `map_created`); Chromium no arranca si nunca se abre el mapa.

### 2.2 Datos que recibe

No recibe un `QAbstractItemModel`: `MediaGridModel` no lleva coordenadas (solo lo que pinta la tarjeta) y atar el mapa a un modelo de Qt impediría cambiar de tecnología. Recibe **datos inmutables y sencillos** (`ui_helpers/map/map_types.py`, sin Qt):

```python
Position = tuple[float, float]         # (latitud, longitud)

@dataclass(frozen=True, slots=True)
class MapMarker:
    media_id: int
    latitude: float
    longitude: float
    media_type: str = "photo"          # valor de MediaType (para el dibujo sin miniatura)
    has_thumbnail: bool = True         # la miniatura se pide a arca-map://thumb/<media_id>
    direction: float | None = None     # gps_direction, por si se dibuja el rumbo (hoy no se dibuja)

@dataclass(frozen=True, slots=True)
class MapTrack:
    track_id: int                      # media_items.id del GPX
    name: str
    segments: tuple[tuple[Position, ...], ...]
    detailed: bool = False             # False = contorno simplificado; True = recorrido completo

@dataclass(frozen=True, slots=True)
class MapWaypoint:                     # punto de interés del track activo (paso 4.3b)
    latitude: float
    longitude: float
    name: str = ""
    description: str = ""

@dataclass(frozen=True, slots=True)
class MapBounds:
    south: float; west: float; north: float; east: float

@dataclass(frozen=True, slots=True)
class MapViewport:                     # lo que se ve: centro, zoom y caja
    latitude: float; longitude: float; zoom: float; bounds: MapBounds

@dataclass(frozen=True, slots=True)
class MapHit:                          # qué hay bajo el ratón (menú contextual)
    kind: HitKind                      # EMPTY, MARKER, CLUSTER o TRACK
    latitude: float; longitude: float
    media_ids: tuple[int, ...] = ()
    track_id: int | None = None
    point_index: int | None = None
```

`SelectionMode`: `REPLACE` y `TOGGLE`. `MapMode`: hoy solo `BROWSE` (los modos de edición llegan con la fase 6).

### 2.3 Señales (el mapa avisa; nunca cambia nada)

| Señal | Cuándo | Quién la atiende |
|---|---|---|
| `ready()` | La página está cargada (lo pedido antes se guarda en cola y se aplica aquí) | `MapController` |
| `load_failed(str)` | La tecnología no arranca (se muestra un aviso en la página, no una ventana) | `MapController` |
| `viewport_changed(MapViewport)` | Se mueve o cambia el zoom (con retardo) | `MapController`: recuerda el encuadre de cada módulo (`MapFraming`) |
| `selection_requested(list[int], SelectionMode)` | Clic en un marcador o en un grupo (`REPLACE`), Ctrl+clic (`TOGGLE`), clic en vacío (`REPLACE` con lista vacía) | `MapController` → `selectionModel` de la cuadrícula |
| `marker_activated(int)` | Doble clic en un marcador | `CenterViewController.open_single` |
| `media_dropped(MediaDrag, float, float)` | Se sueltan tarjetas (`MEDIA_IDS_MIME`) en un punto | `MapController` → cola de cambios |
| `markers_moved(list[int], float, float)` | Se arrastra un marcador ya ubicado (o un grupo) a otro punto | Igual |
| `track_clicked(int)` | Clic en la línea de un track | Selección / track activo |
| `track_hovered(int, int)` | El ratón pasa a menos de 24 px (`HOVER_PX`) de la línea del track activo: `(track_id, índice de punto)`; `-1` al salir | `TrackProfileController` → `ElevationProfile.set_cursor` |
| `edit_requested(TrackEditIntent)` (**pendiente, fase 6: aún no existe**) | En modo edición: mover, insertar, borrar, cortar, añadir al final | `TrackEditController` |
| `context_menu_requested(MapHit, QPoint)` | Botón derecho (qué hay debajo y dónde) | El controlador abre un `QMenu` nativo |
| `fit_requested()` | Botón «Encuadrar» (encima del zoom; 15/11/2026) | `MapController` → `fit_preferred(lo seleccionado en la cuadrícula)` |
| `layer_changed(str)` | El usuario cambia de capa | Guardarla en `settings.json` |

### 2.4 Métodos

```python
class MapView(QWidget):
    # Marcadores (fotos y vídeos con coordenadas)
    def set_markers(self, markers: Sequence[MapMarker]) -> None: ...
    def update_markers(self, markers: Sequence[MapMarker]) -> None: ...   # añadir o mover unos pocos
    def remove_markers(self, media_ids: Sequence[int]) -> None: ...
    def markers(self) -> tuple[MapMarker, ...]: ...
    def set_selected_ids(self, media_ids: Sequence[int]) -> None: ...
    def selected_ids(self) -> tuple[int, ...]: ...
    def set_thumbnail_provider(self, provider: Callable[[int], Path | None] | None) -> None: ...
    def set_drop_enabled(self, enabled: bool) -> None: ...                # soltar tarjetas (Imagen)
    def drop_enabled(self) -> bool: ...
    def set_preview_markers(self, markers: Sequence[MapMarker]) -> None: ...  # para la correlación (aún sin uso)

    # Tracks
    def set_tracks(self, tracks: Sequence[MapTrack]) -> None: ...
    def set_track_geometry(self, track: MapTrack) -> None: ...    # sustituye el contorno por el detalle
    def tracks(self) -> tuple[MapTrack, ...]: ...
    def track(self, track_id: int) -> MapTrack | None: ...
    def set_active_track(self, track_id: int | None) -> bool: ...
    def active_track(self) -> int | None: ...
    def set_track_cursor(self, track_id: int, point_index: int | None) -> None: ...   # el punto ámbar
    def set_track_range(self, track_id: int, first: int, last: int) -> None: ...     # el tramo elegido en el perfil
    def clear_track_range(self) -> None: ...
    def set_track_colors(self, track: str, active: str) -> None: ...                  # Opciones > Tracks
    def set_waypoints(self, waypoints: Sequence[MapWaypoint]) -> None: ...            # los del track activo
    def waypoints(self) -> tuple[MapWaypoint, ...]: ...

    # Encuadre (los 'fit_*' devuelven si había algo que encuadrar)
    def fit_bounds(self, bounds: MapBounds, *, animate: bool = True) -> None: ...
    def fit_content(self, *, animate: bool = True) -> bool: ...        # todo lo que hay
    def fit_selection(self, *, animate: bool = True) -> bool: ...
    def fit_track(self, track_id: int, *, animate: bool = True) -> bool: ...
    def fit_ids(self, media_ids: Sequence[int], *, animate: bool = True) -> bool: ...   # fotos y tracks de esos id
    def show_default_view(self) -> None: ...  # el encuadre de partida (DEFAULT_VIEW: España)
    def fit_preferred(self, media_ids: Sequence[int] = ()) -> None: ...  # el botón «Encuadrar»: esos id; si no, todo; si no, el de partida
    def center_on(self, latitude: float, longitude: float, zoom: float | None = None) -> None: ...
    def viewport(self) -> MapViewport | None: ...

    # Capas
    def layers(self) -> tuple[TileLayer, ...]: ...
    def set_layers(self, layers: Sequence[TileLayer]) -> None: ...
    def base_layer(self) -> str: ...
    def set_base_layer(self, key: str) -> bool: ...

    # Ciclo de vida
    def is_ready(self) -> bool: ...
    def clear(self) -> None: ...              # al cerrar el catálogo
    def save_state(self) -> dict: ...         # capa y encuadre (JSON)
    def restore_state(self, state: object) -> None: ...
```

**Pendiente** (aún no existen): `set_mode(MapMode)` y `show_edit_segment(track_id, TrackPatch)`, de la edición (fase 6), y `set_overlay_visible(key, visible)` (capas superpuestas: no hay ninguna).

Reglas de la API:

- **Todo va por `media_items.id`**; nada de filas, rutas ni objetos de la tecnología.
- Las llamadas anteriores a `ready` se guardan y se aplican al llegar (la página carga de forma asíncrona).
- `MapView` es instanciable más de una vez (comparten perfil y manejador del esquema), pensando en la sección «Ubicación» del inspector (PENDIENTE, `GEN 8.1`); cada instancia cuesta memoria: se decidirá entonces.
- Los controles sobre el mapa (zoom, «Encuadrar», escala, atribución) los dibuja la página con variables CSS que `WebMapBackend` genera desde `COLORS` (`ui_theme.py`). El selector de capas y los botones de modo son **widgets nativos** en la barra inferior o en `MapPage`, no en la página.
- El menú contextual de Chromium se desactiva; el propio es un `QMenu` nativo.
- La vista **no coge el teclado** (como las barras, [DECISIONES.md](DECISIONES.md) del 12/11/2026): los atajos de clasificación siguen yendo a la tira de fotos. Excepción: en modo edición, `Supr`, `Esc`, `Ctrl+Z` y `Ctrl+Y` los atiende `TrackEditController` con atajos del `MapPage`.

### 2.5 Contrato interno con la página (solo para `WebMapBackend`)

- **Python → JS**: llamadas a funciones de `arca_map.js` con JSON compacto (marcadores como `[id, lat, lon, tipo, miniatura]`, `marker_payload`; tracks con cada segmento como una lista plana `[lat, lon, lat, lon...]` de 6 decimales, `track_payload`: no como polilínea codificada, que solo se usa para guardar el contorno en el catálogo). Nunca se construye JavaScript concatenando textos del usuario: siempre `json.dumps`.
- **JS → Python**: ranuras de `MapBridge` (`on_loaded`, `on_ready`, `on_viewport`, `on_select`, `on_fit`, `on_activate`, `on_track_click`, `on_track_hover`, `on_markers_moved`, `on_context_menu`). El JS no guarda más estado que lo que pinta. Las listas viajan como texto JSON ([TRAMPAS.md](TRAMPAS.md)). La ranura de la edición (`on_edit`) llegará con la fase 6.
- **Soltar tarjetas** (comprobado en la fase 0: los eventos llegan al widget interno de la vista, no a la subclase): un filtro de eventos en los hijos del `QWebEngineView` acepta `DragEnter`/`DragMove` solo si el arrastre trae `MEDIA_IDS_MIME` y no pasa el evento a Chromium; en `Drop` guarda el `MediaDrag`, pide a la página la coordenada del punto (`arca.dropPoint`, con `runJavaScript`: no hay una ranura para ello) y, con la respuesta, emite `media_dropped`. Durante el arrastre, la página pinta un marcador fantasma (`set_drop_cursor`).
- **Seguridad**: la página solo puede navegar dentro de `arca-map://` (`acceptNavigationRequest`); sin acceso a `file://` ni a la red directa (las teselas pasan por el esquema).

### 2.6 Cómo lo usan los tres modos

Ningún módulo toca `MapView` directamente. Lo hace `MapController` (uno, creado en `_conectar_vistas` como `CenterViewController`), que recibe el `ModuleHost`, el modelo y la vista de la cuadrícula, el `InspectorController` (para la cola de cambios) y el `MapPage`. Cada módulo solo **declara** lo que quiere:

- `AppModule.views()` incluye o no `CenterView.MAP` (ya existe).
- `AppModule.map_options() -> MapOptions` (dataclass sin Qt, en `center_views.py`): `allow_geotag` (soltar y mover fotos), `show_profile` (la banda del perfil) y `filmstrip_starts_visible` (si la tira se ve mientras el usuario no la muestre u oculte en ese módulo). Por defecto: sin geoetiquetado, sin perfil y con la tira a la vista. Lo previsto para más adelante (`allow_track_edit`, `related_photos`) aún no existe.

| Modo | `views()` | `map_options()` | Qué se ve |
|---|---|---|---|
| Catálogo | cuadrícula, individual, **mapa** | Las de partida (con la tira) | Lo del origen: marcadores y contornos de tracks. Solo ver y seleccionar |
| Imagen | cuadrícula, individual, **mapa** | `allow_geotag` | Marcadores; soltar desde la tira; mover los ubicados; quitar la ubicación; deshacer |
| Tracks | cuadrícula, **mapa** (la inicial) | `show_profile`; la tira empieza oculta | El track elegido con detalle y sus waypoints, los demás en contorno y atenuados, el perfil debajo |

---

## 3. Capas y teselas

### 3.1 Proveedores

Lista declarativa en `core/maps/tile_layers.py` (`TILE_LAYERS`, sin Qt; ► «aquí se añade una capa»). Cada `TileLayer`: clave estable (`key`), nombre para el usuario, plantilla de dirección (`{z}`, `{x}`, `{y}` y, opcional, `{s}`), atribución, formato de las teselas (`extension`), zoom mínimo y máximo, `subdomains` y `allow_prefetch` (si sus condiciones permiten descargar por adelantado). No hay un campo «necesita clave»: ninguna capa la usa. La capa de partida es `DEFAULT_LAYER_KEY` (`osm`). **Las condiciones cambian: hay que volver a leerlas antes de activar una capa nueva.**

| Capa | Tipo | Servicio | Condiciones (resumen) | Atribución |
|---|---|---|---|---|
| **IGN España, MTN ráster** | Topográfico (el de los mapas 1:25 000 y 1:50 000) | WMTS `https://www.ign.es/wmts/mapa-raster`, capa `MTN`, matriz `GoogleMapsCompatible` | Gratuito, CC BY 4.0; sin clave | «© Instituto Geográfico Nacional de España» |
| IGN España, base | Callejero y base | WMTS `https://www.ign.es/wmts/ign-base`, capa `IGNBaseTodo` | Igual | Igual |
| IGN España, PNOA | Ortofoto | WMTS `https://www.ign.es/wmts/pnoa-ma`, capa `OI.OrthoimageCoverage` | Igual | «PNOA cedido por © Instituto Geográfico Nacional de España» |
| **OpenTopoMap** | Topográfico mundial (curvas de nivel, sombreado) | `https://{a-c}.tile.opentopomap.org/{z}/{x}/{y}.png`, zoom ≤ 17 | Gratuito con uso moderado; sin descargas masivas; CC BY-SA | «© OpenStreetMap, SRTM · © OpenTopoMap (CC BY-SA)» |
| OpenStreetMap estándar | Base mundial | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | Política de uso estricta: `User-Agent` propio, caché obligatoria, prohibida la descarga anticipada; no garantizado para uso intensivo | «© OpenStreetMap contributors» |
| IGN Francia (Plan IGN) | Topográfico (Pirineo francés) | WMTS de la Géoplateforme | Abierto sin clave para Plan IGN; SCAN 25 requiere clave | «© IGN-F / Géoplateforme» |
| Thunderforest Outdoors, MapTiler Outdoor, Stadia Terrain | Topográficos mundiales de más calidad | Con **clave** | Planes gratuitos con tope mensual y, en algunos, solo para uso no comercial: al ser una aplicación de empresa, hay que leer la licencia (D5) | La de cada uno |

**Decidido el 13/11/2026 (D5)** y hecho en `core/maps/tile_layers.py`: «Callejero (OpenStreetMap)» (el mapa «normal» de todo el mundo, para fotos de viajes y de ciudades; es la capa con la que empieza el mapa), «OpenTopoMap», «Mapa base (IGN)», «Topográfico (IGN)» y «Ortofoto (PNOA)» (en ese orden, el del autor). Las claves, si algún día se usan, van en `settings.json` y se añaden en Python al pedir la tesela: nunca llegan a la página.

**Capas del usuario** (por durabilidad, §1.5; hecho en el paso 2.4): Opciones > Mapa permite añadir capas propias (nombre, plantilla de dirección, zoom máximo y atribución; `ui_helpers/dialogs/map_layer_dialog.py`), guardadas en `settings.json` con claves `user_…` (`user_layer`, `user_layers_from_settings`, `check_url_template`). Si un servicio cambia de dirección o cierra, se corrige sin tocar el código.

La **atribución** de la capa activa se muestra siempre en la esquina del mapa (es condición de todas).

### 3.2 Cómo se piden: el esquema `arca-map://`

La página no habla con Internet. Todo lo pide a un esquema propio que atiende `MapSchemeHandler` (`QWebEngineUrlSchemeHandler`):

| Dirección | Qué devuelve |
|---|---|
| `arca-map://app/...` | Los recursos de `resources/map/` (página, JS, CSS, Leaflet) y `qwebchannel.js`, que viene dentro de Qt |
| `arca-map://tiles/<capa>/<z>/<x>/<y>` | La tesela: de la caché si está y vale; si no, se descarga (`QNetworkAccessManager`), se guarda y se devuelve |
| `arca-map://thumb/<media_id>` | La miniatura del marcador: la da una función que se le pasa al abrir el catálogo (`set_thumbnail_provider`), que la saca de la caché de miniaturas |

Ventajas: caché y uso sin conexión controlados por la aplicación; un único sitio para el `User-Agent` (`tile_layers.user_agent`) y, si un día hay claves, no llegan a la página; mismo origen para todo (sin problemas de CORS); las miniaturas llegan sin convertirlas a texto. **No implementado**: un límite propio de peticiones simultáneas por servidor ni reintentos (no han hecho falta).

Dos obligaciones de Qt (en [TRAMPAS.md](TRAMPAS.md)): el esquema se **registra antes de crear `QApplication`** (`register_map_scheme()`, que llama `main.py`) y QtWebEngine debe importarse también antes. Si en el equipo falta QtWebEngine, la aplicación sigue adelante sin mapa.

El manejador se ejecuta en el hilo principal y no se nota (medido en la fase 0, §10): leer una tesela de la caché es inmediato y las descargas son asíncronas. La alternativa que se había previsto (que Leaflet pidiera las teselas por `https`) no ha hecho falta.

### 3.3 Caché local

- `core/maps/tile_store.py` (`TileStore`, sin Qt): ruta `<raíz>/<capa>/<z>/<x>/<y>.<ext>`, escritura atómica (como `ThumbnailCache`), fecha de descarga = fecha del archivo. Solo guarda imágenes (`looks_like_image`): una página de error de un servidor no se queda en la caché.
- **Por aplicación, no por catálogo**: las teselas no son datos del catálogo y se pueden volver a bajar. La carpeta es `TILE_CACHE_DIR` de `config/app_paths.py`: `cache/tiles`, junto a `settings.json`.
- **Caducidad**: 30 días (`DEFAULT_MAX_AGE_DAYS`; la política de OSM pide 7 como mínimo). Una tesela caducada se devuelve en el acto y se renueva por detrás; sin conexión, vale siempre.
- **Tope de tamaño**: configurable en Opciones > Mapa (2 GB de partida), donde también se ve lo que ocupa y se puede vaciar. La limpieza de las descargadas hace más tiempo (`prune`) la lanza `MapController` en otro hilo al crearse el mapa y al cambiar el tope (no al arrancar: si nunca se abre el mapa, no se recorre la caché).

### 3.4 Sin conexión

- Lo que está en la caché se ve; lo que no, queda con el fondo del mapa (el color de la cuadrícula). **El aviso «Sin conexión» que se había previsto no está implementado.**
- Marcadores, tracks, selección, perfil y edición funcionan igual: no dependen de la red.
- **Descargar una zona para usarla sin conexión**: posible más adelante y solo con las capas que lo permitan (campo `allow_prefetch`; OSM estándar lo prohíbe). No está en el plan inicial.

---

## 4. Elevación

### 4.1 De dónde sale

> **Cómo quedó**: hoy el perfil usa solo la `ele` de cada punto del GPX (punto 1). El modelo de elevaciones del punto 2 (`core/maps/dem.py`) **está pendiente** (paso 6.8) y, con él, la marca de «altitud estimada».

1. **La `ele` de cada punto del GPX**: siempre que exista. Es la que usa hoy el resumen (`gpx_reader`).
2. **Si falta** (rutas planificadas, puntos insertados, GPX sin altitud): un **modelo digital de elevaciones** por teselas, en `core/maps/dem.py`:
   - Fuente: **AWS Terrain Tiles, formato «terrarium»** (`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`; datos abiertos, sin clave, con atribución). Altura = `R × 256 + G + B / 256 − 32768`. Se decodifica con **Pillow** (ya es dependencia).
   - Zoom 12 o 13 (unos 20-40 m por píxel en España), interpolación bilineal entre los cuatro píxeles vecinos. Usa el mismo `TileStore` (capa `dem`): una ruta de 20 km son 2-6 teselas.
   - `sample_elevations(points, fetch) -> list[float | None]`; la descarga es una función que se le pasa (en un trabajo en segundo plano, con `urllib`), para que `core/` siga sin Qt.
   - Mejora posterior, si la precisión no basta: MDT05 del IGN (5 m, solo España).
3. La altitud **nunca se sustituye en silencio**: los puntos con `ele` del GPX la conservan. El perfil indica cuándo es estimada (texto a decidir). «Rellenar la altitud que falta» y «Sustituir toda la altitud por la del modelo» serán acciones explícitas de la edición.

### 4.2 Cómo se calcula el perfil (`core/tracks/profile.py`, sin Qt)

- **Distancia**: acumulada en 2D con haversine entre puntos consecutivos **del mismo segmento**, igual que `gpx_reader` (entre segmentos no se suma; el perfil marca el salto). La función de haversine está en `core/tracks/geodesy.py` (`haversine_m`) y `gpx_reader` la importa de allí: una sola implementación.
- **Desnivel acumulado**: el mismo método del umbral (`ELEVATION_THRESHOLD_M` = 8 m, calibrado con Wikiloc; repetido en `profile.py`, y la autoprueba comprueba que da lo mismo). Así el perfil dice **los mismos números** que el catálogo y el inspector. No se cambia el cálculo (obligaría a subir `TRACK_EXTRACTOR_VERSION` y a recalibrar).
- **Suavizado, solo para dibujar**: mediana móvil sobre una ventana de distancia (30 m) para quitar los picos del GPS; los números (mínima, máxima, desnivel) salen de los datos sin suavizar.
- **Reducción para pintar**: mínimo y máximo por columna de píxel (como mucho dos puntos por píxel de ancho); 50 000 puntos se dibujan como ~2 000.
- Resultado: `ElevationProfileData` (distancias, altitudes, índice del punto original de cada muestra, saltos de segmento, mínimos, máximos, desnivel; el tramo estimado, todavía no). Funciones: `build_profile`, `range_stats` (las estadísticas de un tramo), `index_at_distance` y `drawing_runs` (la reducción para pintar). Constantes: `SMOOTHING_WINDOW_M` = 30 y `SLOPE_WINDOW_M` = 200. Con la **pendiente** (%) de cada punto, medida sobre la altitud suavizada en una ventana de 200 m (elegida con los GPX del autor el 15/11/2026, al verla dibujada: con 100 m, los colores cambiaban casi en cada punto; con 300 m se pierden las rampas cortas), para pintarla por colores; el widget añade una histéresis del 2 % al decidir la franja. Opcional más adelante: eje de tiempo en vez de distancia.

### 4.3 Con qué se dibuja

`ElevationProfile(QWidget)` en `ui_helpers/widgets/elevation_profile.py` (hecho el 15/11/2026, paso 5.2), con `QPainter`: arriba, los totales o los datos del tramo elegido; ejes con marcas «redondas» y las unidades en ellas; el área y la línea, con la pendiente por colores (por inclinación, cinco franjas de verde a rojo, con histéresis) en el área o solo en la línea; el cursor (línea vertical y círculo ámbar, como el punto del mapa, con una etiqueta de altitud, distancia, pendiente y hora) y el tramo elegido arrastrando. Todo el aspecto, en un estilo que se puede cambiar (`ProfileStyle`, `profile_style.py`; colores de partida en `ProfileColors`); el dibujo, en `profile_painter.py`, y los textos, en `profile_format.py`.

- Por qué no QtCharts o QtGraphs (están instalados): es un solo gráfico de área; a mano son ~250 líneas, se controla el aspecto al píxel como el resto de la aplicación y no entra otro módulo de Qt.
- Por qué no dentro de la página web: el perfil debe verse igual con cualquier tecnología de mapa y probarse sin ella.

Sincronización (hecha en el paso 5.3b; la hace `TrackProfileController`, que crea `MapController`, no los widgets entre sí; sin eco: los métodos que se llaman desde fuera no avisan):

- Perfil → mapa: `ElevationProfile.cursor_moved(int)` → `MapView.set_track_cursor(track_id, point_index)`.
- Mapa → perfil: `MapView.track_hovered(track_id, point_index)` → `ElevationProfile.set_cursor(point_index)`. La página busca el punto más cercano de la **línea** del track activo, a menos de 24 px (`HOVER_PX`), sobre el recorrido completo.
- Arrastrar en el perfil elige un tramo → `range_selected(first, last)` → `MapView.set_track_range`, que lo resalta en ámbar; un clic en el perfil (`selection_cleared`) o Esc lo quitan de los dos (`clear_track_range`). En la edición será la forma cómoda de **recortar** (§7).
- Solo mientras el mapa tiene el recorrido **completo** de ese track: sus índices de punto son entonces los del perfil (con el contorno serían otros).

El recorrido completo, los waypoints y el perfil los calcula `TrackDetailController` en segundo plano, de una vez (`TrackDetail`), con memoria de los 5 últimos (`CACHE_SIZE`).

---

## 5. Modelo de datos

### 5.1 Coordenadas de las fotos (ya existe)

`media_items.latitude`, `longitude`, `altitude`, `gps_direction` (bloque B, editables; [MODELO_DE_DATOS.md](MODELO_DE_DATOS.md)). No hace falta ninguna columna nueva.

- **Leer para el mapa**: `core/catalog/map_queries.py`, `fetch_map_items(conn, source, filters) -> MapItems`: una sola consulta con `source_condition` que devuelve (a) los elementos con latitud y longitud (id, coordenadas, tipo, estado de la miniatura, dirección) y (b) los de tipo `track` con su `overview` y su caja. No se añaden columnas a `fetch_grid_rows`: la cuadrícula sigue pidiendo solo lo que pinta.
- **Escribir** (hecho, pasos 3.2 a 3.4): soltar, mover o quitar la ubicación de N fotos → `core/catalog/geotagging.py`: `set_media_position(conn, ids, latitud, longitud)` (con `None`, quita la ubicación), que pasa por `update_metadata_fields` (las mismas comprobaciones y bits de pendiente que el inspector) y devuelve las coordenadas de antes; con ellas, `restore_media_positions` deshace el cambio (`UndoHistory`). Va por la cola del inspector (`InspectorController.request_edit`). Solo cambian la latitud y la longitud (D7). **Pendiente** (`TRK 8`): la función de la correlación (cada foto, su punto), `update_media_positions`.
- **Índice**: no hace falta para pintar (se consulta por origen, como la cuadrícula). Para «las fotos de la zona de este track» sí convendrá un índice parcial, `idx_media_geo ON media_items(latitude, longitude) WHERE latitude IS NOT NULL`: **no existe**; irá en la migración del paso que lo use (fase 8).

### 5.2 ¿Las coordenadas se escriben también en el archivo? (D1, decide el autor)

> **Decidido el 13/11/2026 (D1): la opción 1**, igual que la edición a mano. Soltar 50 fotos o más pide confirmación (`_CONFIRM_FROM`, en `map_controller.py`) y lo hecho en el mapa se deshace con Ctrl+Z. Lo que sigue es cómo se planteó.

Hoy **ya está decidido para la edición a mano** (11/11/2026): lo editado en el inspector se escribe en el EXIF/XMP, en el sidecar de los RAW o en el `.arca.json`, con `write_user_data_to_files` activado. La pregunta es si el geoetiquetado **desde el mapa y por lotes** sigue la misma regla.

| Opción | A favor | En contra |
|---|---|---|
| **1. Igual que la edición a mano** (recomendada) | Un solo comportamiento; Lightroom ve las coordenadas; sobreviven a recrear el catálogo; sin código nuevo de escritura | Un arrastre o una correlación pueden reescribir cientos de originales de golpe |
| 2. Solo en la base de datos | No toca ningún archivo | Se pierde al recrear el catálogo; incoherente con el inspector (el mismo campo, dos reglas); habría que impedir que la escritura pendiente lo llevase al archivo |
| 3. Preguntar en cada operación por lotes | El usuario decide cada vez | Una pregunta más; las coordenadas «solo en la base» necesitarían una marca nueva para que no se escriban después |

Con la opción 1, las salvaguardas: la ventana de vista previa de la correlación dice cuántos archivos se van a escribir; soltar sobre el mapa más de N fotos (propuesta: 50) pide confirmación; y el deshacer del mapa (D6).

### 5.3 Tracks y sus puntos

- **Lo que hay**: una fila en `media_items` (tipo `track`, biblioteca `tracks`, salida en `latitude`/`longitude`) y su resumen en `track_details` (caja, llegada, distancia, desnivel, horas UTC, recuentos).
- **Lo nuevo (migración 4)**: `track_details.overview TEXT`: el recorrido **simplificado** (Douglas-Peucker, tolerancia ~15 m, tope de 1 000 puntos entre todos los segmentos), como polilínea codificada (el formato de Google, precisión 5; un segmento por línea). Lo calcula `TrackExtractor` (`core/tracks/simplify.py`: `OVERVIEW_TOLERANCE_M` = 15, `OVERVIEW_MAX_POINTS` = 1 000); con ello `TRACK_EXTRACTOR_VERSION` subió a 3 (hoy es 5, por la actividad; los GPX se releen solos). Sirve para pintar cientos de tracks sin abrir ningún archivo y, más adelante, para la miniatura del recorrido (hecha el 14/11/2026: paso 4.5).
- **Los puntos completos no van a SQLite.** Opciones consideradas:

| Opción | Valoración |
|---|---|
| **A. Leer el GPX a demanda** (recomendada) | El archivo es la fuente y no se duplica nada. 30 000 puntos se leen en décimas de segundo, en segundo plano, y se guardan en memoria (los últimos 5 tracks). **Hecho así**: `read_gpx_path` en `core/tracks/gpx_document.py`; la memoria, en `TrackDetailController` |
| B. Tabla `track_points` | 1 000 tracks × 10 000 puntos = 10 millones de filas y cientos de MB en el catálogo, para un dato que ya está en los archivos; con un GPX ausente, el contorno de `overview` ya da para verlo |
| C. Un archivo binario por track en `cache/track/` del catálogo | Solo si se mide que A es lenta con archivos enormes; se puede añadir después sin cambiar nada más |

- **Track nuevo o editado** (pendiente, fases 6 y 7): un track **editado** se guarda sobre su propio GPX (D2, 16/11/2026) y el catálogo lo relee como cualquier archivo que cambia. Uno **nuevo** no existe en el catálogo hasta que se guarda en una carpeta catalogada y esa carpeta se sincroniza (hoy solo se catalogan carpetas completas: PENDIENTE, `CAT 1.1`); al guardarlo se ofrece sincronizarla.

### 5.4 Relación de los tracks con las colecciones

**No hace falta nada nuevo**: un track es un `media_items`, así que una colección estática (`collection_items`) ya puede contener tracks y fotos, y una inteligente puede mezclarlos con reglas. El mapa del Catálogo pinta lo que haya en el origen: los `track`, como líneas; lo que tenga coordenadas, como marcadores. Es justo «juntar los GPX de una ruta con sus fotos» (PENDIENTE, `TRK 8`).

Lo que queda por decidir (D4): si además se quiere la relación **calculada** («las fotos de esta ruta» sin hacer la colección a mano). Propuesta (**pendiente**, `TRK 8`: la función aún no existe): una consulta, sin tabla nueva, `fetch_track_photos(conn, track_id, margin_s, max_distance_m)` en `map_queries.py`: fotos y vídeos cuya hora (convertida a UTC, §6) cae entre `started_at` y `ended_at` con un margen, o, si el track no tiene horas, dentro de su caja y a menos de cierta distancia del contorno. El módulo Tracks la usa para pintar las fotos junto al track ([DECISIONES.md](DECISIONES.md), «Vistas del centro»), y una acción «Crear colección con esta ruta y sus fotos» la convierte en colección estática. Una tabla de enlaces (`track_media`) solo si se quiere fijar la relación a mano foto a foto: no se propone.

---

## 6. Correlación foto-track (geoetiquetado automático)

> **Pendiente entero** (`TRK 8`): no existen `core/tracks/correlation.py`, la ventana ni su controlador. Es el diseño de partida. Lo único hecho es `MapView.set_preview_markers`, todavía sin uso.

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

> **Hecho**: solo §7.1 (el lector completo, paso 4.1). **Pendiente** (`TRK 6` y `TRK 7`): §7.2 a §7.5; no existen `track_model.py`, `TrackEditController`, `write_gpx` ni los modos de edición del mapa.

### 7.1 Leer sin perder nada (`core/tracks/gpx_document.py`, sin Qt)

`read_gpx` (el del extractor) es un resumen en streaming y tira los puntos: no sirve para editar. Por eso hay un lector **completo y sin pérdidas**, aparte (el del extractor no se toca). Como está hoy:

```python
@dataclass(slots=True)
class TrackPoint:
    latitude: float
    longitude: float
    elevation: float | None = None
    time: datetime | None = None            # UTC, con zona
    extra: tuple[Element, ...] = ()         # el resto de hijos del punto, tal cual (pulso, cadencia, hdop...)
    elevation_estimated: bool = False       # altitud puesta por el modelo de elevaciones (al leer, siempre False)

@dataclass(slots=True)
class GpxDocument:
    version: str                            # '1.0' o '1.1'
    creator: str | None
    namespace: str                          # el de las etiquetas GPX
    namespaces: tuple[tuple[str, str], ...] # (prefijo, dirección), en su orden: para guardar con los mismos prefijos
    root_attributes: dict[str, str]         # p. ej. xsi:schemaLocation
    metadata: Element | None                # <metadata> entero (GPX 1.1), tal cual
    header: ...                             # en GPX 1.0, los datos sueltos de <gpx> (name, desc, author...), tal cual
    waypoints: ...                          # los puntos de interés (Waypoint), con sus campos
    tracks: ...                             # GpxTrack, con sus TrackSegment (o las rutas, si el archivo solo tenía rutas)
    routes: ...                             # las rutas que no se usan como recorrido, tal cual
    extensions: ...                         # los <extensions> del documento, tal cual
    skipped_points: int                     # puntos ignorados por no ser válidos
    skipped_waypoints: int
```

Dos lecturas: `read_gpx_document(path)` (el archivo entero, para editar) y `read_gpx_path(path)` (solo el recorrido, `TrackPath` con sus `PathSegment`: para verlo en el mapa y para el perfil).

- **Cambiado al implementarlo (paso 4.1, 14/11/2026)**: lo que no se edita se guarda como elementos XML sueltos (`Element`), no como texto: los tracks del autor tienen de 1 000 a 10 000 puntos (la memoria no aprieta) y así, al exportar, todo va en un solo árbol con los espacios de nombres declarados una vez. Los waypoints se leen con sus campos (nombre, descripción, símbolo), para verlos y editarlos. Y hay una lectura rápida aparte, `read_gpx_path`, solo con el recorrido. El resto de este apartado es el diseño original.
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
- **Dónde** (D2; **cambiado el 16/11/2026**: el autor decide que un GPX editado se guarda sobre el propio archivo, sin generar copias, y «Exportar a GPX…» queda para guardar en otro archivo; lo que sigue es el diseño anterior, a rehacer en el paso 6.1): por defecto «Exportar a GPX…» a un archivo **nuevo** (se propone `<nombre> (editado).gpx` junto al original); el original no se modifica nunca, como manda el principio del proyecto. Si el autor quiere «Guardar» sobre el original, sería una excepción nueva de ese principio (con copia `.bak`) y habría que anotarla en [CLAUDE.md](../CLAUDE.md) y [ARQUITECTURA.md](ARQUITECTURA.md).
- El atributo `creator`: se conserva el del original en los editados; en los nuevos, el nombre de la aplicación.
- Si la carpeta de destino está catalogada, al terminar se ofrece sincronizarla para que el GPX aparezca (con su `overview` y su resumen).
- Cambios sin exportar: al salir del modo edición, cambiar de track o cerrar el catálogo, se pregunta (exportar, descartar, cancelar).

### 7.5 Interacción en el mapa (modo `EDIT_TRACK` / `DRAW_TRACK`)

- Solo se pintan **asas** de los vértices visibles y con el zoom suficiente (tope ~300); con el zoom lejano se ve la línea y se edita por tramos (seleccionar en el perfil, cortar, borrar).
- Arrastrar un asa → `MovePoint`; clic sobre la línea entre dos asas → `InsertPoint`; clic en un asa + `Supr` → `DeletePoints`; menú contextual en un asa: «Cortar aquí», «Borrar desde aquí hasta el final», «Borrar hasta aquí»; en `DRAW_TRACK`, cada clic en el mapa → `AppendPoint` y doble clic termina.
- La página solo emite la intención (`edit_requested`); el cambio lo hace `TrackEditController` y vuelve como `TrackPatch`. Durante un arrastre, la página mueve el asa por su cuenta (fluidez) y confirma al soltar.

---

## 8. Rendimiento

> **Cómo quedó**: medido en la fase 0 (§10): un track de 10 000 puntos y 20 000 marcadores agrupados, fluido; los tracks reales del autor tienen de 1 000 a 10 000 puntos, así que los 50 000 de los objetivos son margen, no requisito. De la tabla, **está hecho**: la agrupación con Supercluster, el dibujo en `canvas` (`preferCanvas`), los tres niveles de los tracks (contorno, recorrido completo del activo con memoria de los 5 últimos), la carga con `db.execute_async` y número de generación, y la caché de teselas. **No está hecho** (o no ha hecho falta): `smoothFactor` (no se usa), el límite de 2 peticiones por servidor y `fetch_track_photos`; la fila de la edición es de la fase 6.

Objetivos: 20 000 fotos con coordenadas en un origen; un track activo de 50 000 puntos; 500 tracks en contorno; nada bloquea la interfaz.

| Problema | Solución |
|---|---|
| **Miles de marcadores** | Agrupación en la página con **Supercluster** (índice espacial, cientos de miles de puntos en milisegundos). Al mover o cambiar el zoom se piden los grupos de lo visible y se pintan como mucho unos cientos de elementos. Cada grupo: miniatura de una de sus fotos y el número (como Lightroom); los marcadores sueltos, su miniatura (`arca-map://thumb/<id>`, cargada solo si se ve). Clic en un grupo: selecciona todas sus fotos |
| **Selección con grupos** | El índice acumula por grupo cuántas de sus fotos están seleccionadas (propiedad agregada de Supercluster): el grupo se resalta sin recorrer sus hijos. `set_selected_ids` con 20 000 ids (Ctrl+A) es un conjunto en JS y un repintado de lo visible |
| **Pasar los datos a la página** | Una sola llamada con una lista compacta (`[id, lat, lon, tipo, miniatura]`): 20 000 marcadores ≈ 0,7 MB de JSON. Los cambios pequeños (soltar, mover), con `update_markers`: no se reenvía todo |
| **Tracks largos** | Tres niveles: (1) el **contorno** de `track_details.overview` (≤ 1 000 puntos) para todos los tracks del origen, sin abrir archivos; (2) la **geometría completa** solo del track activo, leída en segundo plano y enviada como lista plana de coordenadas (`track_payload`); (3) al pintar, Leaflet simplifica por nivel de zoom (`smoothFactor`) sobre `canvas` y recorta a lo visible. Mientras llega la completa se ve el contorno |
| **Simplificación** | `core/tracks/simplify.py`: Douglas-Peucker iterativo (sin recursión: 100 000 puntos) y codificación de polilíneas. Se usa al extraer (`overview`) y para el perfil no hace falta (reduce por píxel) |
| **Edición de tracks grandes** | Asas solo de lo visible; cada orden repinta un rango (`TrackPatch`), no el track entero; el perfil se recalcula entero (50 000 puntos: milisegundos) con un retardo de 100 ms durante los arrastres |
| **Carga en segundo plano** | Consultas con `db.execute_async` (`fetch_map_items`, `fetch_track_photos`); lectura de GPX completos en el mismo grupo de hilos (la función recibe `conn` para sacar la ruta y luego lee el archivo) con memoria de los 5 últimos; elevación del modelo como trabajo (`JobManager`) si hay que descargar teselas. Cada respuesta lleva un número de generación: las tardías se descartan (patrón de `MetadataFilterController`) y se comprueba `if self.db is None: return` |
| **Trabajo inútil** | `MapController` no consulta nada mientras el mapa no se ve: marca «pendiente» en `modelReset` y carga al mostrarse (como los módulos inactivos en `ModuleHost.refresh`). La selección se sincroniza con un retardo corto y por tramos (`selection()`), como `CenterViewController._remember_shown` |
| **Teselas** | Caché en disco, 2 peticiones simultáneas por servidor, cancelación de las que ya no se ven (Leaflet las aborta al cambiar el zoom) |
| **Arranque** | Chromium no se inicia hasta la primera vez que se abre el mapa; el import de `QtWebEngineWidgets` en `main.py` no lo arranca (medir en la fase 0 cuánto retrasa el inicio) |

---

## 9. Riesgos y preguntas abiertas (por gravedad)

> **Cómo quedó cada uno** (16/11/2026). **Resueltos**: 1 (los eventos de arrastre llegan al widget interno: `WebMapBackend` pone un filtro en los hijos de la vista; 1-3 px de diferencia), 2 (la ventana se compone con la GPU desde que se abre, con su opción: sin parpadeo y sin cortes en la vista individual), 5 (la vista y sus hijos van en `NoFocus`), 7 (el manejador en Python no se nota), 15 (marcadores con miniatura; los grupos, de 44 px) y 16 (los vídeos se recolocan como las fotos: `LOCATABLE_MEDIA_TYPES`). **Decididos**: 4 (D1 el 13/11/2026 y D2 el 16/11/2026: en los dos casos se escribe en los archivos). **Medido**: 11 (unos 170 MB más con el mapa vacío; 400-500 MB más con un track y 20 000 marcadores). **Siguen abiertos**: 3 (macOS y Linux), 6 (condiciones de los servicios), 8 (pantallas con escalado: no se usa `detectRetina` y solo se ha probado al 100 %), 9 (empaquetado, `GEN 5`), 10 (zonas horarias, con la correlación), 12, 13, 14, 17 y 18 (`GEN 8.1`).

**Graves (pueden cambiar el plan)**

1. **Soltar tarjetas sobre `QWebEngineView`**: que la subclase reciba los eventos de arrastre con `MEDIA_IDS_MIME` y que la coordenada del píxel sea exacta con el escalado de Windows (125-150 %). Si los eventos los recibe el widget interno, alternativa: filtro de eventos sobre él o una capa transparente encima solo mientras dura el arrastre. → Fase 0.
2. **QtWebEngine dentro de la ventana real**: al crear el primer `QWebEngineView`, Qt puede pasar la ventana entera a componerse con la GPU (parpadeo o recreación de la ventana al abrir el mapa por primera vez, y posible cambio en cómo se pintan la cuadrícula y la vista individual). Puede ser bueno (el «tearing» de la vista individual a 1:1: [TRAMPAS.md](TRAMPAS.md)) o malo. → Fase 0, dentro de una ventana con un `QListView` grande.
3. **macOS y Linux, sin probar** (como todo el proyecto): QtWebEngine es la pieza más delicada fuera de Windows (bibliotecas del sistema y entorno aislado en Linux; firma del proceso auxiliar en macOS al empaquetar).
4. **Modificar archivos del usuario por lotes** (D1) y **sobrescribir un GPX** (D2): no son riesgos técnicos, sino de datos; el diseño propone lo conservador y deja la decisión al autor.

**Medios**

5. **Teclado**: que Chromium no se quede el foco (los atajos de clasificación deben seguir en la tira de fotos). → Fase 0.
6. **Condiciones de los servicios de teselas**: cambian; OSM estándar y OpenTopoMap no garantizan servicio y prohíben el uso intensivo; los de pago por clave pueden excluir el uso en empresa. IGN es el más seguro para España. Revisar al implementar el paso de las capas.
7. **Rendimiento del esquema `arca-map://` en Python** (decenas de teselas por movimiento, con el GIL). Alternativa dentro del plan A en §3.2. → Fase 0.
8. **Pantallas con escalado**: las teselas ráster se ven borrosas al 150 % si no se piden las del nivel siguiente a mitad de tamaño (`detectRetina`), y entonces los rótulos salen más pequeños. Hay que elegir viendo el resultado. → Fase 0 (captura para el autor).
9. **Empaquetado futuro**: +220 MB aproximados, proceso `QtWebEngineProcess.exe` y carpeta `resources` de Qt que PyInstaller debe incluir. Anotado en PENDIENTE, `GEN 5`; no condiciona el diseño.
10. **Zonas horarias en la correlación**: fotos sin desfase guardado hechas en otro huso; la ventana deja elegir la zona, pero el valor por defecto (la del equipo) puede ser incorrecto en un viaje. Mejora posible: deducir la zona de las coordenadas del track (`timezonefinder`, ya anotada en `track/extractor.py`).
11. **Memoria**: un proceso Chromium (100-300 MB) más las miniaturas de los marcadores. Medir en la fase 0 con 20 000 marcadores.

**Leves / preguntas abiertas**

12. Tracks que cruzan el antimeridiano o con cajas enormes: se pintan, pero `fit_bounds` puede encuadrar mal. Sin tratamiento especial de momento.
13. Coordenadas 0, 0: la lectura ya las toma por «sin GPS» ([DECISIONES.md](DECISIONES.md), 11/11/2026); el mapa no deja soltar exactamente ahí.
14. Formatos de track distintos de GPX (`.tcx`, `.fit`, `.kml`): fuera de este diseño; el modelo interno no depende del formato, así que se podrán añadir lectores.
15. ¿Marcador con miniatura o un punto simple? (aspecto; se decide viéndolo en el paso 1.3).
16. ¿Los vídeos con GPS se pueden recolocar igual que las fotos? El mecanismo lo permite (van al `.arca.json`); se propone que sí.
17. Privacidad: los servidores de teselas ven qué zonas se consultan (no las fotos ni sus coordenadas exactas). Aceptable para uso interno; anotarlo.
18. Sección «Ubicación» del inspector con un mapa pequeño (PENDIENTE, `GEN 8.1`): posible con una segunda `MapView`; no está en este plan.

---

# Parte II — Planificación

Las fases 0 a 5 están hechas (se conservan, tachadas, como registro de lo que se pidió y cómo se aceptó). Lo pendiente son las fases 6, 7 y 8; su lista corta, en [PENDIENTE.md](PENDIENTE.md) (`TRK 6`, `TRK 7`, `TRK 8`).

## 10. Plan de implementación

Reglas para quien lo implemente: un paso cada vez, con el visto bueno del autor antes de los que tocan varios archivos; al terminar cada paso, lo que manda [CLAUDE.md](../CLAUDE.md) («Al terminar cada paso: actualizar la documentación»): `ESTADO.md` siempre, el mapa de `ARQUITECTURA.md` con cada archivo nuevo, `PRUEBAS.md` con cada autoprueba, `MODELO_DE_DATOS.md` e `INDEX.md` con la migración y la versión, `FLUJOS.md` con un apartado nuevo «Mapa», `TRAMPAS.md` con lo que se descubra y `DECISIONES.md` con lo que decida el autor. **En cada paso**, además de sus criterios: `ruff check` de lo tocado, las autopruebas de los módulos tocados y que la aplicación arranca y la cuadrícula, la vista individual y el inspector siguen igual (lo comprueba el autor).

Antes de empezar (13/11/2026; las tres están ya decididas): resolver D1, D2 y D3 y recordar al autor que haga un commit.

### Resultado de la fase 0 (13/11/2026): se sigue con el plan A

Hecha en `scripts/poc_map/` (borrada el 13/11/2026, al terminar el paso 1.5: todo lo suyo está en `ui_helpers/map/`; sigue en el historial de git) y probada por el autor en Windows (pantalla al 100 %, PySide6 6.11.2, Python 3.14.8). Todos los criterios se cumplen:

| Qué | Resultado |
|---|---|
| Mapa y fluidez | Listo 134 ms después de crear la vista web; track de 10 000 puntos (8 ms) y 20 000 marcadores agrupados (47 ms), fluido al mover y hacer zoom. El autor aclara que sus tracks reales tienen de 1 000 a 10 000 puntos: el objetivo de 50 000 de §8 queda como margen, no como requisito |
| Parpadeo al crear el mapa | Apenas se nota |
| Soltar tarjetas | Funciona, con 1-3 px de diferencia (incluye lo que se mueve el ratón al soltar). **Los eventos de arrastre no llegan a la subclase de `QWebEngineView`, sino a su widget interno**: `WebMapBackend` debe poner un filtro de eventos en los hijos de la vista (como `MapWebView._watch_children` de la prueba). La capa transparente no hace falta |
| Teclado | Con la vista y sus hijos en `NoFocus`, las flechas siguen en la lista, también tras un clic en el mapa |
| Ida y vuelta Python ↔ página | 0,17 ms de mediana (máximo 0,67 ms) |
| Esquema `arca-map://` | 362 teselas sin errores (IGN MTN y OpenTopoMap; las direcciones de §3.1 valen), unos 100 ms por descarga; segunda vez y sin conexión, de la caché. El manejador se ejecuta en el hilo principal y no se nota |
| Memoria | Unos 170 MB más con el mapa vacío y unos 400-500 MB más con el track y los 20 000 marcadores cargados (714 MB en total en la prueba, que incluye una imagen de 96 MB). Es el coste de Chromium; a vigilar con datos reales |
| Cortes horizontales de la foto | **Desaparecen en cuanto existe la vista web** (antes de crearla, los mismos cortes que en la vista individual). Confirma que basta con que la ventana se componga con la GPU (hecho el 13/11/2026: [ESTADO.md](ESTADO.md)) |

Aprendido para la implementación (irá a [TRAMPAS.md](TRAMPAS.md) con el paso 1.3): `QNetworkRequest.setHeader(UserAgentHeader, ...)` no acepta `bytes` desde Python (avisa y no pone la cabecera): usar `setRawHeader`; una lista de JavaScript devuelta por `runJavaScript` no llega bien a Python: devolver texto JSON. 

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
| ~~**1.1** Capas y almacén de teselas~~ (hecho el 13/11/2026) | `TILE_LAYERS` y `TileStore` (rutas, escritura atómica, caducidad, tope) | Nuevos: `core/maps/__init__.py`, `tile_layers.py`, `tile_store.py` | Fase 0 (direcciones comprobadas) | Autopruebas: plantillas de dirección, ruta de cada tesela, caducidad, limpieza por tamaño (carpeta temporal, sin red) | Módulos nuevos sin Qt: nada los importa todavía |
| ~~**1.2** Tipos y contrato~~ (hecho el 13/11/2026; sin los tipos de la edición de tracks, que se añadirán con la fase 7) | `map_types.py` (dataclasses, enumeraciones) y `MapBackend` | Nuevos: `ui_helpers/map/__init__.py`, `map_types.py`, `map_backend.py` | — | Autoprueba de `map_types` (validación de coordenadas, `MapBounds` de una lista) | Nada los importa todavía |
| ~~**1.3** `MapView` con WebEngine~~ (hecho el 13/11/2026; pendiente de que el autor lo vea) | Mapa que se ve, con capas, marcadores agrupados, selección y encuadre; esquema `arca-map://` (recursos y teselas) | Nuevos: `map_view.py`, `web_backend.py`, `web_bridge.py`, `map_scheme.py`, `resources/map/*`. **`main.py`**: registrar el esquema e importar WebEngine antes de `QApplication` | 1.1, 1.2 | Autoprueba **con ventana** (la ejecuta el autor): mapa con 5 000 marcadores, cambio de capa, clic selecciona (se imprime la señal), `fit_content`. Colores solo por variables del tema | La aplicación arranca igual (medir el tiempo de arranque antes y después); nada usa aún `MapView` |
| ~~**1.4** Miniaturas y tracks en el mapa~~ (hecho el 13/11/2026; pendiente de que el autor lo vea; las miniaturas ya iban en el 1.3) | `arca-map://thumb/`, `set_tracks`, `set_track_geometry`, `set_active_track`, `set_track_cursor`, `track_hovered` | `map_scheme.py`, `web_backend.py`, `arca_map.js` | 1.3 | En la autoprueba con ventana: un GPX real en contorno y en detalle; el cursor sigue al ratón | Igual que 1.3 |
| ~~**1.5** Soltar y mover~~ (hecho el 13/11/2026; pendiente de que el autor lo vea; solo se arrastran las fotos sueltas, no los grupos) | `media_dropped`, `markers_moved`, `set_drop_enabled`, menú contextual | `web_backend.py`, `arca_map.js` | 1.3 | En la autoprueba: soltar desde una lista y arrastrar un marcador imprimen ids y coordenadas correctas | Igual |

### Fase 2 — Modo Catálogo (solo ver y seleccionar)

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| ~~**2.1** Contorno de los tracks~~ (hecho el 13/11/2026; los tracks se releen solos al abrir el catálogo) | Migración 4 (`track_details.overview`), simplificación y lectura | Nuevos: `core/tracks/__init__.py`, `geodesy.py`, `simplify.py`. Cambios: `catalog_schema.py` (migración al final), `track/gpx_reader.py` (usa `geodesy`; recoge los puntos para el contorno), `track/extractor.py` (`TRACK_EXTRACTOR_VERSION` = 3) | — | Autopruebas: Douglas-Peucker (tolerancia, tope, segmentos), codificar y decodificar, migración sobre un catálogo v3. Un catálogo real se abre, pasa a v4 y relee los GPX | Autopruebas de `catalog_schema`, `gpx_reader`, `extractor` y `processor`; la distancia y el desnivel de Bujaruelo, Ordesa y Pineta **no cambian** (comparar antes y después con `track/inspect_cli`) |
| ~~**2.2** Consulta del mapa~~ (hecho el 13/11/2026; además de lo previsto, cuenta las fotos y vídeos sin coordenadas, `unlocated`) | `fetch_map_items(conn, source, filters)` | Nuevo: `core/catalog/map_queries.py` | 2.1 | Autoprueba con un catálogo en memoria: mismo recuento que `count_grid_items` para los que tienen coordenadas; tracks con su contorno; respeta el filtro | No toca `media_queries` (solo importa `source_condition`) |
| ~~**2.3** Página y controlador~~ (hecho el 13/11/2026; atajo M y Esc de vuelta al mapa, pedidos por el autor; sin `map_options`, que llegará con la tira de fotos del paso 3.1) | `MapPage` (crea `MapView` al mostrarse), `MapController` (carga al ver el mapa, generación, selección en los dos sentidos, doble clic → vista individual, guarda capa y encuadre). `CatalogModule.views()` añade `MAP`; icono y texto de la vista | Nuevos: `ui_helpers/widgets/map_page.py`, `controllers/map_controller.py`. Cambios: `center_views.py` (icono; `MapOptions`), `base.py` (`map_options`), `catalog_module.py`, `main_window_controller.py` (**solo** crear el controlador y añadir la página en `_conectar_vistas`), `app_constants.py` (icono), `.qrc` + `build_ui.py`, `app_config_manager.py` (claves nuevas en `DEFAULTS`) | 1.3-1.5, 2.2; D9 | Catálogo: el botón «Mapa» muestra las fotos con GPS de lo elegido a la izquierda y los tracks; cambiar de carpeta o de filtro actualiza el mapa; seleccionar en el mapa selecciona en la cuadrícula (se ve al volver con G) y al revés; el inspector sigue la selección; la vista se recuerda por módulo | Autoprueba de `center_views` y `module_view_state`; con la vista en cuadrícula o individual, todo igual; Imagen no ofrece aún el mapa |
| ~~**2.4** Opciones~~ (hecho el 13/11/2026, sin «capa por defecto»: ya se recuerda la última elegida; además, el mapa al día tras un cambio del inspector) | Página «Mapa» en la ventana de opciones: capa por defecto, capas del usuario (añadir, cambiar, quitar), tamaño de la caché, vaciarla | `settings_dialog.py`, `app_config_manager.py` | 2.3 | Las opciones se guardan y se aplican (`apply_settings`) | El resto de páginas, igual |

### Fase 3 — Modo Imagen (geoetiquetar)

| Paso | Objetivo | Archivos | Depende de | Aceptación | Cómo comprobar que no rompe nada |
|---|---|---|---|---|---|
| ~~**3.1** Tira de fotos (según D3)~~ (hecho el 13/11/2026; también en el Catálogo; aún sin menú contextual en la tira) | En `MapPage`, una tira horizontal debajo del mapa: un segundo `MediaGridView` con el **mismo modelo y el mismo `selectionModel`** que la cuadrícula; atajos con `GridActions.watch`. Arrastra **sin imagen** (una opción de `MediaGridView`): sobre el mapa solo se ve el círculo ámbar que dice dónde caen (el autor, 13/11/2026) | `map_page.py`, `map_controller.py`, `image_module.py` (`views`, `map_options`) | 2.3 | En Imagen, vista «Mapa»: tira con las fotos del origen; la selección de la tira, la del mapa y la de la cuadrícula son la misma; los atajos («3», «P») funcionan con el ratón sobre el mapa | La cuadrícula no cambia (mismo modelo); probar selección múltiple y Ctrl+A |
| ~~**3.2** Soltar para ubicar~~ (hecho el 13/11/2026, con el mover de 3.3: al dejar soltar, el mapa ya deja arrastrar las fotos sueltas y tenía que guardarse) | `media_dropped` → `update_metadata_fields` por `InspectorController.request_edit`; confirmación a partir de N; el marcador aparece sin recargar todo | `map_controller.py` | 3.1; D1 | Arrastrar una o varias fotos de la tira al mapa: aparecen ahí; el inspector («Metadatos», GPS) muestra las coordenadas; con la escritura activada, Lightroom las lee | Autoprueba de `media_queries`; la edición del GPS en el inspector sigue igual |
| ~~**3.3** Recolocar y quitar~~ (hecho el 13/11/2026) | ~~`markers_moved` (igual que 3.2)~~ (hecho con 3.2); menú contextual «Quitar la ubicación» (latitud y longitud a vacío) | `map_controller.py` | 3.2; D7 | Arrastrar un marcador lo mueve y queda pendiente de escribir; quitar la ubicación lo borra del mapa | — |
| ~~**3.4** Deshacer en el mapa (según D6)~~ (hecho el 13/11/2026: `controllers/undo_history.py` y `core/catalog/geotagging.py`; sin rehacer) | El primer cliente de un deshacer para toda la aplicación (acordado el 13/11/2026; [PENDIENTE.md](PENDIENTE.md), `GEN 1`): un historial de cambios que saben deshacerse, con Ctrl+Z en la ventana; de momento, solo lo llena el mapa (ids → coordenadas anteriores) | `map_controller.py` (si crece, `controllers/geotag_history.py`) | 3.3 | Ctrl+Z devuelve las fotos a donde estaban (o las deja sin ubicación) | Ctrl+Z no hace nada fuera del mapa |
| ~~**3.5** Ver quién no tiene ubicación~~ (hecho el 13/11/2026: el campo ya existía, «Tiene coordenadas GPS»; solo hacía falta el ajuste de fábrica «Sin ubicación». Con él, la fase 3 está completa) | Campo «Ubicación GPS» (tiene / no tiene) en `smart_fields.py` si no existe, y un ajuste de fábrica «Sin ubicación» en `filter_presets.py` | `smart_fields.py`, `filter_presets.py` | — | El filtro deja en la tira solo las fotos sin GPS | Autopruebas de `smart_fields`, `smart_rules`, `filter_presets` |

### Plan del módulo Tracks (revisado el 14/11/2026)

Acordado con el autor el 14/11/2026, con su lista de funciones de edición y de creación: primero lo básico del módulo, después el perfil de elevación, la edición y la creación, **de lo más útil a lo menos necesario**. Sustituye a las fases 4 a 7 que había (ver, elevación, correlación, edición): la correlación foto-track y «las fotos de la ruta» pasan a la fase 8. Los diseños de §4 (elevación) y §7 (edición) siguen valiendo, con lo que se añade aquí.

**Para todo el plan**:

- **Guardar** (D2, decidida el 16/11/2026): un track editado se guarda **sobre su propio GPX, sin generar copias**; uno nuevo, o «Exportar a GPX…», en un archivo nuevo; si la carpeta está catalogada, se ofrece sincronizarla para que aparezca.
- **Track activo**: el único track seleccionado (en el mapa, la tira o la cuadrícula). De él son el recorrido con detalle, el perfil y los datos del inspector.
- **Deshacer y rehacer**: la edición tiene su historial en `core/` (`EditHistory`, sin Qt), con Ctrl+Z y Ctrl+Y mientras se edita; fuera de ella sigue el deshacer general (`UndoHistory`).
- **Todo cambio es una orden** que sabe deshacerse (§7.2), también las limpiezas y la simplificación: enseñan lo que van a cambiar, se aplican de una vez y se deshacen de una vez.
- **Servicios ajenos** (teselas de elevación, enrutado): necesitan red y ven la zona que se consulta. La aplicación funciona sin ellos (línea recta, perfil sin altitud) y sus direcciones se cambian en Opciones > Mapa.

### Fase 4 — Tracks: lo básico

| Paso | Objetivo | Archivos | Depende de | Aceptación |
|---|---|---|---|---|
| ~~**4.1** Lector completo~~ (hecho el 14/11/2026) | `read_gpx_path` (el recorrido en arrays compactos: para ver) y `read_gpx_document` (el archivo entero: tracks, puntos, waypoints y lo que no se edita, tal cual) | Nuevo: `core/tracks/gpx_document.py` | 2.1 | Autoprueba: GPX 1.0 y 1.1, varios segmentos, extensiones, waypoints, rutas; el mismo recorrido que `read_gpx` |
| ~~**4.2** Módulo Tracks~~ (hecho el 14/11/2026; la barra es `ui_helpers/sidebars/library_sidebar.py`, pensada también para Vídeo y Audio; sin vista individual) | `TracksModule` en lugar del provisional (el botón, el icono y el modo `tracks` ya existen). Barra con «Biblioteca - Tracks», «Carpetas» y «Fechas» (`FolderSection` y `DateSection` con la biblioteca `tracks`; dadas de alta en `section_registry.py`); vistas mapa (inicial) y cuadrícula; orden por fecha, distancia, desnivel y duración | Nuevos: `tracks_module.py`, `ui_helpers/sidebars/tracks_sidebar.py`. Cambios: `registry.py`, `section_registry.py`, `grid_orders.py` | 2.3 | El módulo lista los GPX y los muestra en el mapa en contorno; se recuerda como los demás; Catálogo e Imagen, igual |
| ~~**4.3** Track activo con detalle~~ (hecho el 14/11/2026 en `controllers/track_detail_controller.py`, sin los waypoints, que pasan a un paso 4.3b; se encuadra solo si se elige fuera del mapa) | Al elegir un track: su recorrido completo en segundo plano (memoria de los 5 últimos), encuadrado y resaltado; los demás, atenuados; sus waypoints, a la vista | `map_controller.py`, `arca_map.js` | 4.1, 4.2 | Un GPX largo se ve entero y nítido al acercar; cambiar de track deprisa no mezcla respuestas |
| ~~**4.4** Sección «Track» del inspector~~ (hecho el 14/11/2026; la consulta, en `core/catalog/track_stats.py`; con varios tracks, sumados; además, la velocidad media) | Distancia, desnivel de subida y de bajada, altitudes, duración, fechas, puntos y actividad (hoy no se ven en ningún sitio). De la biblioteca `tracks` (aparece también en el Catálogo con tracks seleccionados) | Nuevo: `ui_helpers/inspector/track_section.py`; `section_registry.py`, `inspector_panel.py` | — | Los números, los del catálogo (`track_details`) |
| ~~**4.5** Miniatura del recorrido~~ (hecho el 14/11/2026: dibujado al vuelo en el delegado, `ui_helpers/helpers/track_outline.py`; `THUMBNAIL_VERSION` no cambia) | El contorno (`overview`) dibujado en la tarjeta de los tracks, en la cuadrícula y en la tira | A decidir en el paso: dibujado en el delegado o un origen más del motor de miniaturas (esto último sube `THUMBNAIL_VERSION`) | 2.1 | Cada track se reconoce por su forma |
| ~~**4.6a** Lista de actividades~~ (hecho el 14/11/2026) | La actividad de un track, como clave en inglés (la del `<type>` del GPX, con los nombres de deporte de FIT) que se muestra en español; traductor de lo que traen los GPX | Nuevo: `core/tracks/activities.py`; `track_stats.py`, `track_section.py` | 4.4 | Autoprueba; el inspector dice «Senderismo» para `hiking` |
| ~~**4.6b** Actividad editable~~ (hecho el 14/11/2026, sin migración: sobre `track_details.activity_type`, generalizando el mecanismo de edición; `TRACK_EXTRACTOR_VERSION` 5) | Desplegable en la fila «Actividad» del inspector; protegida de la relectura y guardada en el `.arca.json` | `editable_fields.py`, `xmp_writer.py`, `catalog_schema.py`, extractor de tracks (`TRACK_EXTRACTOR_VERSION` 4), `track_section.py`, `smart_fields.py`; pasos en [PENDIENTE.md](PENDIENTE.md) | 4.6a | Cambiar la actividad de uno o varios tracks; sobrevive a releer el GPX y a recrear el catálogo; las fotos se escriben igual que antes |

### Fase 5 — Perfil de elevación

| Paso | Objetivo | Archivos | Depende de | Aceptación |
|---|---|---|---|---|
| ~~**5.1** Cálculo~~ (hecho el 15/11/2026; con la pendiente de cada punto, que pide el 5.2) | `build_profile(path) -> ElevationProfileData` (§4.2) y las estadísticas de un tramo (distancia, subida, bajada, tiempo, velocidad media) | Nuevo: `core/tracks/profile.py` | 4.1 | Autoprueba: distancia y desnivel **iguales** a los de `read_gpx` con los mismos archivos; saltos de segmento; reducción por píxel |
| ~~**5.2** Widget~~ (hecho el 15/11/2026; con `ProfileStyle`, los tres modos de la pendiente y una ventana de prueba) | `ElevationProfile` (§4.3): área, ejes, cursor (distancia, altitud, hora) y selección de un tramo arrastrando; pendiente por colores, de verde a rojo (adelantada del 5.4, a petición del autor); el aspecto, en parámetros (colores, grosores...) para poder personalizarlo | Nuevo: `ui_helpers/widgets/elevation_profile.py`; colores en `theme_colors.py` | 5.1 | Autoprueba con ventana (el autor): un perfil real, a su gusto |
| ~~**5.3** Banda bajo el mapa~~ (hecho el 15/11/2026 en dos pasos: 5.3a, la banda, con `controllers/track_profile_controller.py`; 5.3b, la sincronización y el tramo en el mapa, `setTrackRange`) | El perfil del track activo en una banda ocultable (botón y atajo) y de alto ajustable y recordado, como la tira de fotos (D11: conviven; en Tracks la tira empieza oculta y luego recuerda su estado); cursor sincronizado en los dos sentidos (el mismo círculo ámbar en el mapa y en el perfil); el tramo elegido, resaltado en el mapa, con sus estadísticas | `map_page.py`, `map_controller.py`, `arca_map.js` | 5.2, 4.3 | Pasar por el perfil mueve el punto en el mapa y al revés, sin retraso; Catálogo e Imagen, sin perfil |
| **5.4** Extras (en espera, decidido por el autor el 15/11/2026: aportaría sobre todo con las fotos de la ruta, fase 8) | Eje por tiempo además de por distancia | `profile.py`, `elevation_profile.py` | 5.3 | — |

### Fase 6 — Edición

Imprescindibles (6.1 a 6.5) y útiles (6.6 a 6.8).

| Paso | Objetivo | Archivos | Depende de | Aceptación |
|---|---|---|---|---|
| **6.1** Exportar sin pérdidas | `write_gpx` (§7.4) | `core/tracks/gpx_document.py` | 4.1; D2 | Autoprueba: leer → escribir → leer da lo mismo (extensiones, waypoints, metadatos, prefijos); con los GPX del autor, `read_gpx` da el mismo resumen antes y después |
| **6.2** Modelo de edición | `TrackModel`, las órdenes (mover, insertar, borrar un punto o un rango, cortar, unir, invertir), `EditHistory` con deshacer y rehacer, `TrackPatch`, validación (§7.2, §7.3) | Nuevo: `core/tracks/track_model.py` (si crece, `track_commands.py` y `track_validation.py`) | 6.1; D8, D12 | Autoprueba: cada orden, su deshacer y su rehacer; fusión de arrastres; avisos |
| **6.3** Editar en el mapa | Modo edición del track activo: asas de los vértices visibles; mover, borrar e **insertar arrastrando el punto medio fantasma** entre dos vértices; barra de edición (deshacer, rehacer, exportar, salir); Ctrl+Z / Ctrl+Y; el perfil, al día; aviso de cambios sin exportar | Nuevo: `controllers/track_edit_controller.py`; `web_backend.py`, `arca_map.js`, `map_page.py`, `tracks_module.py` | 6.2, 5.3 | Editar un track real y exportarlo; abre bien en otro programa; el original no cambia |
| **6.4** Tramos | Seleccionar un rango en el perfil o en el mapa; sus estadísticas; borrarlo; recortar el principio o el final («Borrar hasta aquí», «Borrar desde aquí»); quedarse solo con el tramo | `track_edit_controller.py`, `arca_map.js`, `elevation_profile.py` | 6.3 | Quitar el trozo del coche del principio y del final de un track |
| **6.5** Dividir, unir, invertir | Cortar en un punto (dos segmentos, o exportar cada parte); unir segmentos; añadir los de otro GPX y unirlos; invertir el sentido | `track_edit_controller.py`, `track_model.py` | 6.3 | Unir dos GPX de una misma salida; los avisos de horas aparecen |
| **6.6** Simplificar | Douglas-Peucker (`simplify.py`, que ya existe) con tolerancia ajustable, viendo los puntos que quedan antes de aplicar; el resultado se guarda | `track_model.py`, `track_edit_controller.py`; un diálogo o una fila en la barra de edición | 6.3 | Un track de 3 000 puntos, a unos cientos sin que cambie su forma a la vista |
| **6.7** Limpiar errores del GPS | Detectores que **proponen** puntos: duplicados, picos de posición, saltos de velocidad imposibles y nubes de puntos estando parado; se ven resaltados y se quitan como una sola orden | Nuevo: `core/tracks/cleanup.py`; `track_edit_controller.py` | 6.3 | Autoprueba con tracks inventados (un pico, una nube, un salto); en uno real, lo que propone es razonable |
| **6.8** Elevación | El modelo de elevaciones (`core/maps/dem.py`, §4.1) y sus tres acciones: «Rellenar la altitud que falta», «Sustituir por la del modelo» y «Suavizar la altitud» | Nuevo: `core/maps/dem.py`; `track_model.py` (`SetElevations`), `track_edit_controller.py` | 6.3, 1.1 | Autoprueba con una tesela generada (sin red); un track real con y sin su altitud da perfiles parecidos |

### Fase 7 — Creación

| Paso | Objetivo | Archivos | Depende de | Aceptación |
|---|---|---|---|---|
| **7.1** Dibujar punto a punto | Modo de dibujo: cada clic añade un punto; distancia acumulada y número de puntos en vivo; deshacer y rehacer (el mismo historial); altitud del modelo para cada punto; exportar a una carpeta y ofrecer sincronizarla | `track_edit_controller.py`, `arca_map.js`, `tracks_module.py` | 6.3, 6.8 | Se dibuja una ruta, se exporta y, tras sincronizar, aparece en Tracks con su distancia y su perfil |
| **7.2** Enrutado por caminos | Entre el último punto y el clic, la línea sigue la red de caminos, con perfil a pie, en bici o en coche; se activa y se desactiva tramo a tramo; sin red o con error, línea recta | Nuevo: `core/maps/routing.py` (un proveedor intercambiable); Opciones > Mapa (servidor, clave si hace falta) | 7.1; D13 | Dos clics en un sendero conocido dan una línea que lo sigue |
| **7.3** Waypoints | Añadir, mover, cambiar y borrar puntos de interés, con nombre, descripción y símbolo (leerlos y verlos, desde 4.1 y 4.3) | `track_model.py`, `track_edit_controller.py`, `arca_map.js` | 6.3 | Un waypoint creado aquí se ve con su nombre en otro programa |

### Fase 8 — Fotos y tracks

Lo que no estaba en la lista del autor, para después: **las fotos de la ruta** (antes 4.4: `fetch_track_photos`, D4, y «Crear colección con esta ruta y sus fotos») y **ubicar fotos por la hora con un GPX** (antes fase 6: `core/tracks/correlation.py`, `update_media_positions`, `GeotagDialog`; §6).

### Después (sin fecha)

Descarga de zonas para usarlas sin conexión; sección «Ubicación» del inspector con mapa; rumbo de la foto (`gps_direction`) dibujado y editable en el mapa; MDT05 del IGN; otros formatos de track.

### Sobre el orden

Hasta la fase 3, el sugerido al principio (base → Catálogo → Imagen). Desde la 4, el acordado el 14/11/2026: lo básico de Tracks, el perfil, la edición y la creación, cada bloque de lo más útil a lo menos necesario. Dependencias que fijan el orden dentro de él: el perfil necesita el lector completo (4.1) y el track activo (4.3); editar en el mapa (6.3), el perfil sincronizado (5.3); dibujar (7.1), la altitud del modelo (6.8). La fase 8 no depende de la edición y se puede adelantar.

---

## 11. Decisiones del autor (detalle)

- **D1. Escritura de las coordenadas en los archivos.** Opciones y salvaguardas en §5.2. Recomendación: la misma regla que la edición a mano. Bloquea el paso 3.2.
- **D2. Guardar un GPX editado.** **Decidida el 16/11/2026 (el autor): sobre el propio archivo, sin generar copias** ([DECISIONES.md](DECISIONES.md)); cómo se hace con seguridad, en el paso 6.1. Lo que se recomendaba: siempre «Exportar a GPX…» a un archivo nuevo; el original no se toca. Alternativa: permitir «Guardar» con copia `.bak` (excepción nueva del principio de los originales). Bloquea 7.3.
- **D3. Modo Imagen: cómo conviven la cuadrícula y el mapa.** (a) Mapa con una **tira de fotos** debajo, como el módulo Mapa de Lightroom (recomendada: reutiliza el modelo y la selección; el mapa conserva el ancho); (b) cuadrícula y mapa lado a lado con un separador. También: si el Catálogo lleva la tira. Bloquea 3.1.
- **D4. «Fotos de una ruta».** Colección a mano (ya funciona) y, en Tracks, cálculo por hora y cercanía con sus umbrales (margen de tiempo, distancia máxima). Bloquea 4.4.
- **D5. Capas de partida** y si interesa alguna con clave. Bloquea 1.1 (la lista) y 2.4.
- **D6. Deshacer en el mapa.** La aplicación no tiene deshacer; arrastrar por error es fácil. Recomendación: sí, limitado al mapa y a la sesión. Bloquea 3.4.
- **D7. Altitud al recolocar una foto.** Dejarla, vaciarla o rellenarla con el modelo de elevaciones. Recomendación: dejarla (como Lightroom) y ofrecer el relleno más adelante. Afecta a 3.3.
- **D8. Hora de los puntos insertados en un GPX.** Interpolada por distancia (recomendada: algunos servicios rechazan tracks con puntos sin hora) o sin hora. Afecta a 7.2.
- **D9. Textos y aspecto**: icono y atajo de la vista «Mapa», nombres de las capas, textos de la ventana de correlación, de la barra de edición y de los avisos; marcador con miniatura o punto. Cada paso los propone antes de escribirlos.
- ~~**D11. La banda del perfil y la tira de fotos**~~ (decidido por el autor el 15/11/2026): conviven bajo el mapa, cada una con su botón; en Tracks la tira empieza oculta y luego recuerda su estado.
- **D12. Horas al invertir un track** (para 6.5). Recomendación: quitarlas, con aviso (conservarlas dejaría un track que retrocede en el tiempo).
- **D13. Servicio de enrutado** (para 7.2). Sin elegir: al llegar al paso, comparar BRouter, OpenRouteService y GraphHopper (perfiles de senderismo, si piden clave, condiciones de uso) y que decida el autor.
- **D10. Identificación ante los servidores de teselas**: `User-Agent` con el nombre y la versión de la aplicación; OSM recomienda añadir una forma de contacto. Recomendación: sin datos personales, salvo que el autor quiera ponerlos.
