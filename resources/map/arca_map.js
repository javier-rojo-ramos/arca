// Página del mapa de Arca Media (docs/MAPA.md). La carga ui_helpers/map/web_backend.py.
//
// REGLA: esta página solo PINTA y AVISA. No guarda más estado que lo que dibuja, no
// decide nada y no cambia datos. Python llama a las funciones de 'arca' (siempre con
// argumentos en JSON) y recibe los avisos por 'bridge' (ui_helpers/map/web_bridge.py).
// JavaScript llano, sin cadena de construcción: lo que se lee aquí es lo que se ejecuta.
//
// Arranque: la página avisa con 'on_loaded' -> Python llama a 'init' (colores del tema,
// textos y encuadre inicial) -> se crea el mapa -> 'on_ready'.
"use strict";

// El punto de un recorrido más cercano a (x, y), mirando sus TRAMOS y no solo sus vértices:
// así el punto señalado se desliza por la línea aunque los vértices estén lejos unos de
// otros (el contorno de un track tiene pocos puntos; con el zoom cerca, quedan a muchos
// píxeles). Función suelta y sin Leaflet, para poder probarla sola (la autoprueba de
// 'ui_helpers/map/map_view.py' la ejecuta tal cual).
//   merc:   [x0, y0, x1, y1, ...] en metros de Mercator, todos los segmentos seguidos
//   starts: starts[i] = 1 si el punto i empieza un segmento (no hay tramo desde el anterior)
// Devuelve {index, x, y, d2}: el vértice más cercano de ese tramo (el índice que viaja a
// Python), el punto sobre la línea y su distancia al cuadrado. index = -1 sin puntos.
function arcaNearestOnPath(merc, starts, x, y) {
  let best = Infinity, bestIndex = -1, bestX = 0, bestY = 0;
  const count = merc.length / 2;
  for (let i = 0; i < count; i++) {
    const bx = merc[2 * i], by = merc[2 * i + 1];
    let px = bx, py = by, index = i;
    if (i > 0 && !starts[i]) {
      // Proyección del ratón sobre el tramo que llega a este punto, sin salirse de él
      const ax = merc[2 * i - 2], ay = merc[2 * i - 1];
      const vx = bx - ax, vy = by - ay;
      const length2 = vx * vx + vy * vy;
      let t = length2 > 0 ? ((x - ax) * vx + (y - ay) * vy) / length2 : 1;
      t = t < 0 ? 0 : (t > 1 ? 1 : t);
      px = ax + t * vx;
      py = ay + t * vy;
      index = t < 0.5 ? i - 1 : i;
    }
    const dx = px - x, dy = py - y;
    const d2 = dx * dx + dy * dy;
    if (d2 < best) { best = d2; bestIndex = index; bestX = px; bestY = py; }
  }
  return { index: bestIndex, x: bestX, y: bestY, d2: best };
}

const arca = (() => {
  let bridge = null;             // puente con Python
  let map = null;                // el mapa de Leaflet
  let colors = {};               // colores del tema (los mismos que las variables CSS)
  let tiles = null;              // capa de teselas que se ve
  let layers = {};               // clave -> {key, attribution, min_zoom, max_zoom}
  let layerKey = null;
  let group = null;              // lo que está pintado (fotos y grupos del encuadre)
  let index = null;              // índice de Supercluster
  const items = new Map();       // id -> [id, lat, lon, tipo, miniatura (1/0)]
  let selected = new Set();      // id seleccionados
  const tracks = new Map();      // id -> {id, halo, line, points, merc, starts}
  let activeTrack = null;        // id del track activo (el único que avisa del ratón)
  let trackCursor = null;        // punto señalado en un track
  let lastHover = -1;            // último índice avisado con 'on_track_hover'
  let hoverFrame = 0;
  let lastMouse = null;
  let dropEnabled = false;       // se pueden soltar tarjetas y arrastrar las fotos sueltas
  let ghost = null;              // señal del punto donde caería una tarjeta arrastrada
  let preview = null;            // marcadores provisionales (propuesta de la correlación)
  let waypoints = null;          // puntos de interés del track activo

  const MARKER_SIZE = 44;        // lado del recuadro de una foto o de un grupo, en px
  const SMALL_MARKER_SIZE = 18;  // una foto suelta sin miniatura: no hay nada que enseñar
  const CLUSTER_RADIUS = 60;     // fotos a menos de estos px se agrupan
  const FIT_PADDING = 40;        // margen al encuadrar, en px
  const FIT_MAX_ZOOM = 16;       // al encuadrar un solo punto no se acerca más que esto
  // Sensibilidad del punto del track activo: a cuántos px de su línea, como mucho, lo
  // "engancha" el ratón (pedido por el autor el 14/11/2026: 24; antes, 12)
  const HOVER_PX = 24;
  const DIMMED_OPACITY = 0.45;   // con un track activo, opacidad de los demás
  const MERC_WORLD = 40075016.686;  // metros de Mercator del mundo entero (zoom 0 = 256 px)

  // --- Arranque ----------------------------------------------------------------

  function init(config) {
    colors = config.colors;
    const style = document.documentElement.style;
    for (const [name, value] of Object.entries(colors)) {
      style.setProperty("--arca-" + name, value);
    }
    map = L.map("map", { preferCanvas: true, zoomControl: false });
    map.attributionControl.setPrefix(false);
    L.control.zoom({
      zoomInTitle: config.texts.zoom_in,
      zoomOutTitle: config.texts.zoom_out,
    }).addTo(map);
    map.setView([config.view[0], config.view[1]], config.view[2]);
    group = L.layerGroup().addTo(map);
    preview = L.layerGroup().addTo(map);
    waypoints = L.layerGroup().addTo(map);

    map.on("moveend", () => {
      render();
      reportViewport();
    });
    // Clic en el mapa vacío: se pide dejar la selección vacía (lo decide Python)
    map.on("click", () => bridge.on_select("[]", false));
    map.on("contextmenu", (e) => contextMenu("empty", e, {}));
    map.on("mousemove", (e) => {
      lastMouse = e.latlng;
      if (!hoverFrame) hoverFrame = requestAnimationFrame(hover);   // una vez por fotograma
    });
    map.on("mouseout", () => {
      lastMouse = null;
      if (!hoverFrame) hoverFrame = requestAnimationFrame(hover);
    });
    bridge.on_ready();
  }

  function reportViewport() {
    const c = map.getCenter(), b = map.getBounds();
    bridge.on_viewport(c.lat, c.lng, map.getZoom(),
                       b.getSouth(), b.getWest(), b.getNorth(), b.getEast());
  }

  // --- Capas ---------------------------------------------------------------------

  // list: [{key, attribution, min_zoom, max_zoom}, ...]
  function setLayers(list) {
    layers = {};
    for (const layer of list) layers[layer.key] = layer;
  }

  function setBaseLayer(key) {
    const layer = layers[key];
    if (!layer || key === layerKey) return;
    if (tiles) map.removeLayer(tiles);
    layerKey = key;
    // Las teselas las sirve Python (caché en disco y descarga): la página no sale a Internet
    tiles = L.tileLayer("arca-map://tiles/" + key + "/{z}/{x}/{y}", {
      minNativeZoom: layer.min_zoom,
      maxNativeZoom: layer.max_zoom,   // más cerca, se amplían las del último zoom
      maxZoom: 20,
      attribution: layer.attribution,
    }).addTo(map);
  }

  // --- Marcadores agrupados ---------------------------------------------------------

  // list: [[id, lat, lon, tipo, miniatura], ...]
  function setMarkers(list) {
    items.clear();
    for (const item of list) items.set(item[0], item);
    rebuild();
  }

  function updateMarkers(list) {
    for (const item of list) items.set(item[0], item);
    rebuild();
  }

  function removeMarkers(ids) {
    for (const id of ids) {
      items.delete(id);
      selected.delete(id);
    }
    rebuild();
  }

  function setSelected(ids) {
    selected = new Set(ids);
    rebuild();
  }

  // Rehace el índice. Cada grupo lleva cuántas de sus fotos están seleccionadas ('sel'),
  // así se resalta sin recorrer sus fotos al pintar.
  function rebuild() {
    const features = [];
    for (const item of items.values()) {
      features.push({
        type: "Feature",
        properties: { id: item[0], thumb: item[4], sel: selected.has(item[0]) ? 1 : 0 },
        geometry: { type: "Point", coordinates: [item[2], item[1]] },
      });
    }
    index = new Supercluster({
      radius: CLUSTER_RADIUS,
      maxZoom: 19,
      map: (properties) => ({ sel: properties.sel }),
      reduce: (accumulated, properties) => { accumulated.sel += properties.sel; },
    }).load(features);
    render();
  }

  // Pinta solo lo que cae en el encuadre: unos cientos de elementos como mucho
  function render() {
    if (!group) return;
    group.clearLayers();
    if (!index || items.size === 0) return;
    const b = map.getBounds();
    const zoom = Math.round(map.getZoom());
    const visible = index.getClusters([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], zoom);
    for (const feature of visible) group.addLayer(markerFor(feature));
  }

  function markerFor(feature) {
    const [lon, lat] = feature.geometry.coordinates;
    const properties = feature.properties;
    const isCluster = !!properties.cluster;
    // Un grupo enseña la miniatura de una de sus fotos
    const sample = isCluster ? index.getLeaves(feature.id, 1)[0].properties : properties;
    // Una foto suelta sin miniatura: un punto pequeño (un grupo conserva su tamaño: lleva el número)
    const small = !isCluster && !sample.thumb;
    const size = small ? SMALL_MARKER_SIZE : MARKER_SIZE;

    const box = document.createElement("div");
    box.className = "arca-photo" + (properties.sel > 0 ? " selected" : "") + (small ? " small" : "");
    if (sample.thumb) {
      const image = document.createElement("img");
      image.draggable = false;
      image.onerror = () => box.classList.add("no-thumb");
      image.src = "arca-map://thumb/" + sample.id;
      box.appendChild(image);
    } else {
      box.classList.add("no-thumb");
    }
    if (isCluster) {
      const count = document.createElement("span");
      count.className = "count";
      count.textContent = properties.point_count;
      box.appendChild(count);
    }

    const marker = L.marker([lat, lon], {
      icon: L.divIcon({ html: box, className: "", iconSize: [size, size] }),
      keyboard: false,
      // Solo se arrastran las fotos sueltas: mover un grupo entero de un tirón sería
      // demasiado fácil de hacer sin querer
      draggable: dropEnabled && !isCluster,
    });
    const idsOf = () => (isCluster
      ? index.getLeaves(feature.id, Infinity).map((leaf) => leaf.properties.id)
      : [properties.id]);
    marker.on("contextmenu", (e) => contextMenu(isCluster ? "cluster" : "marker", e, { ids: idsOf() }));
    // Arrastrada a otro sitio: se avisa y se queda donde se soltó. Quien manda (Python)
    // la confirma con 'updateMarkers' o la devuelve a su sitio
    marker.on("dragend", () => {
      const p = marker.getLatLng();
      bridge.on_markers_moved(JSON.stringify([properties.id]), p.lat, p.lng);
    });
    marker.on("click", (e) => {
      const ids = idsOf();
      const toggle = e.originalEvent.ctrlKey || e.originalEvent.metaKey;
      bridge.on_select(JSON.stringify(ids), toggle);
    });
    marker.on("dblclick", () => {
      if (isCluster) {
        // Doble clic en un grupo: acercarse hasta que se separe
        map.setView([lat, lon], Math.min(index.getClusterExpansionZoom(feature.id), 20));
      } else {
        bridge.on_activate(properties.id);
      }
    });
    return marker;
  }

  // --- Tracks ---------------------------------------------------------------------
  //
  // Cada track son DOS líneas: un borde claro debajo ('halo') y la línea de color encima,
  // para que se lea sobre cualquier mapa. Sus puntos se numeran seguidos entre todos sus
  // segmentos: ese índice es el que viaja a Python y vuelve.

  // list: [{id, name, detailed, segments: [[lat, lon, lat, lon, ...], ...]}, ...]
  function setTracks(list) {
    for (const track of tracks.values()) removeTrack(track);
    tracks.clear();
    hideTrackCursor();
    for (const data of list) addTrack(data);
    if (activeTrack !== null && !tracks.has(activeTrack)) activeTrack = null;
    restyleTracks();
  }

  // Cambia la geometría de un track (su contorno por el detalle); si no estaba, lo añade
  function setTrackGeometry(data) {
    const old = tracks.get(data.id);
    if (old) removeTrack(old);
    if (trackCursor && trackCursor.trackId === data.id) hideTrackCursor();
    // Sus puntos se numeran de otra forma: el último índice avisado ya no vale
    if (data.id === activeTrack) lastHover = -1;
    addTrack(data);
    restyleTracks();
  }

  function addTrack(data) {
    const segments = [];
    const points = [];
    const merc = [];
    const starts = [];             // 1 = ese punto empieza un segmento
    for (const flat of data.segments) {
      const latlngs = [];
      for (let i = 0; i + 1 < flat.length; i += 2) {
        const latlng = L.latLng(flat[i], flat[i + 1]);
        const projected = L.CRS.EPSG3857.project(latlng);
        starts.push(latlngs.length === 0 ? 1 : 0);
        latlngs.push(latlng);
        points.push(latlng);
        merc.push(projected.x, projected.y);
      }
      if (latlngs.length) segments.push(latlngs);
    }
    const halo = L.polyline(segments, { interactive: false }).addTo(map);
    // 'bubblingMouseEvents: false': un clic en la línea no cuenta además como clic en el mapa
    const line = L.polyline(segments, { bubblingMouseEvents: false }).addTo(map);
    if (data.name) line.bindTooltip(textBlock([data.name]), { sticky: true });
    line.on("click", () => bridge.on_track_click(data.id));
    const track = {
      id: data.id, halo, line, points,
      merc: Float64Array.from(merc), starts: Uint8Array.from(starts),
    };
    line.on("contextmenu", (e) => contextMenu("track", e, {
      track: data.id,
      index: nearestPoint(track, e.latlng).index,
    }));
    tracks.set(data.id, track);
  }

  function removeTrack(track) {
    map.removeLayer(track.halo);
    map.removeLayer(track.line);
  }

  function setActiveTrack(id) {
    activeTrack = id;
    hideTrackCursor();
    lastHover = -1;
    map.getContainer().classList.remove("arca-hide-cursor");
    restyleTracks();
  }

  // El activo, más grueso, con su color y por encima de los demás, que se atenúan
  // mientras haya uno activo (sin ninguno, todos se ven igual)
  function restyleTracks() {
    const anyActive = tracks.has(activeTrack);
    for (const track of tracks.values()) {
      const active = track.id === activeTrack;
      const weight = active ? 4 : 3;
      const fade = anyActive && !active ? DIMMED_OPACITY : 1;
      track.halo.setStyle({
        color: colors["track-halo"], weight: weight + 3, opacity: 0.85 * fade,
      });
      track.line.setStyle({
        color: active ? colors["track-active"] : colors["track"],
        weight: weight,
        opacity: fade,
      });
    }
    const active = tracks.get(activeTrack);
    if (active) {
      active.halo.bringToFront();
      active.line.bringToFront();
    }
  }

  // index null = quitar la señal
  function setTrackCursor(id, pointIndex) {
    const track = tracks.get(id);
    if (!track || pointIndex === null || pointIndex < 0 || pointIndex >= track.points.length) {
      hideTrackCursor();
      return;
    }
    showTrackCursor(track, pointIndex);
  }

  // 'latlng' (opcional): dónde pintarlo, si no es justo en el vértice (el ratón sobre un
  // tramo: el punto va por la línea)
  function showTrackCursor(track, pointIndex, latlng) {
    const position = latlng || track.points[pointIndex];
    if (!trackCursor) {
      trackCursor = L.circleMarker(position, {
        radius: 6, weight: 2, fillOpacity: 1, interactive: false,
        color: colors["text-on-accent"], fillColor: colors["accent"],
      });
    }
    const added = map.hasLayer(trackCursor);
    trackCursor.trackId = track.id;
    trackCursor.setLatLng(position);
    // Ponerlo en el mapa y subirlo, solo al aparecer: mientras se mueve (una vez por
    // fotograma) basta con cambiarle el sitio
    if (!added) {
      trackCursor.addTo(map);
      trackCursor.bringToFront();
    }
  }

  // El sitio de la LÍNEA de un track más cercano a un punto del mapa: el vértice que le
  // toca ('index'), a cuántos píxeles queda y dónde está ('latlng')
  function nearestPoint(track, latlng) {
    const mouse = L.CRS.EPSG3857.project(latlng);
    const nearest = arcaNearestOnPath(track.merc, track.starts, mouse.x, mouse.y);
    const metersPerPixel = MERC_WORLD / (256 * Math.pow(2, map.getZoom()));
    return {
      index: nearest.index,
      pixels: Math.sqrt(nearest.d2) / metersPerPixel,
      latlng: nearest.index < 0 ? null
        : L.CRS.EPSG3857.unproject(L.point(nearest.x, nearest.y)),
    };
  }

  function hideTrackCursor() {
    if (trackCursor) map.removeLayer(trackCursor);
  }

  // El ratón sobre el track activo (a menos de HOVER_PX píxeles de su LÍNEA): el punto
  // ámbar lo sigue por la línea, en cada fotograma, y a Python se le avisa solo cuando
  // cambia el vértice que le toca. Con 10 000 puntos son unas decenas de miles de
  // operaciones: muy por debajo de un milisegundo.
  function hover() {
    hoverFrame = 0;
    const track = tracks.get(activeTrack);
    if (!track) return;
    let found = -1, position = null;
    if (lastMouse) {
      const nearest = nearestPoint(track, lastMouse);
      if (nearest.index >= 0 && nearest.pixels <= HOVER_PX) {
        found = nearest.index;
        position = nearest.latlng;
      }
    }
    if (found >= 0) {
      showTrackCursor(track, found, position);
    } else if (lastHover >= 0) {
      hideTrackCursor();   // solo al salir: no quita un punto puesto desde Python (el perfil)
    }
    if (found === lastHover) return;
    lastHover = found;
    // El punto ámbar ya hace de cursor: el del ratón se oculta para no taparlo
    map.getContainer().classList.toggle("arca-hide-cursor", found >= 0);
    bridge.on_track_hover(track.id, found);
  }

  // --- Soltar tarjetas, mover fotos y vista previa ---------------------------------------
  //
  // El arrastre de tarjetas lo recoge Python (los eventos no llegan a la página): aquí
  // solo se pinta dónde caería y se traduce un píxel de la vista a coordenadas.

  function setDropEnabled(enabled) {
    dropEnabled = enabled;
    render();   // las fotos sueltas pasan a poder arrastrarse (o dejan de poder)
  }

  // x, y: píxeles de la vista; null = fin del arrastre
  function setDropCursor(x, y) {
    if (x === null) {
      if (ghost) { map.removeLayer(ghost); ghost = null; }
      return;
    }
    const latlng = map.containerPointToLatLng([x, y]);
    if (!ghost) {
      ghost = L.circleMarker(latlng, {
        radius: 9, weight: 2, fillOpacity: 0.35, interactive: false,
        color: colors["accent"], fillColor: colors["accent"],
      }).addTo(map);
    } else {
      ghost.setLatLng(latlng);
    }
  }

  // Coordenadas [lat, lon] de un píxel de la vista (donde se ha soltado)
  function dropPoint(x, y) {
    setDropCursor(null, null);
    const latlng = map.containerPointToLatLng([x, y]);
    return [latlng.lat, latlng.lng];
  }

  // Un bloque de texto para un texto emergente: una línea por elemento (los vacíos, no),
  // la primera en negrita si hay más. Como TEXTO, nunca como HTML: los nombres vienen de
  // los archivos del usuario (un GPX bajado de internet puede traer cualquier cosa)
  function textBlock(lines) {
    const block = document.createElement("div");
    const shown = lines.filter((line) => line);
    shown.forEach((line, i) => {
      const row = document.createElement("div");
      row.textContent = line;
      if (i === 0 && shown.length > 1) row.style.fontWeight = "bold";
      block.appendChild(row);
    });
    return block;
  }

  // Puntos de interés del track activo. list: [[lat, lon, nombre, descripción], ...];
  // vacía = quitarlos. Solo se miran: un rombo pequeño con su nombre al pasar el ratón
  function setWaypoints(list) {
    waypoints.clearLayers();
    for (const item of list) {
      const marker = L.marker([item[0], item[1]], {
        // El rombo es el <i> de dentro: el elemento de fuera lo coloca Leaflet con un
        // 'transform', y girarlo a él lo movería de sitio
        icon: L.divIcon({ className: "arca-waypoint", html: "<i></i>", iconSize: [12, 12] }),
        keyboard: false,
        // Un clic en él no cuenta como clic en el mapa (no quita la selección)
        bubblingMouseEvents: false,
      });
      if (item[2] || item[3]) {
        marker.bindTooltip(textBlock([item[2], item[3]]), { direction: "top", offset: [0, -8] });
      }
      waypoints.addLayer(marker);
    }
  }

  // list: [[id, lat, lon], ...]; vacía = quitarlos
  function setPreviewMarkers(list) {
    preview.clearLayers();
    for (const item of list) {
      preview.addLayer(L.circleMarker([item[1], item[2]], {
        radius: 6, weight: 2, fillOpacity: 0.9, interactive: false,
        color: colors["text-on-accent"], fillColor: colors["accent"],
      }));
    }
  }

  // Botón derecho: qué hay debajo y dónde (el menú lo abre Python, con un QMenu)
  function contextMenu(kind, e, extra) {
    const hit = Object.assign({ kind: kind, lat: e.latlng.lat, lon: e.latlng.lng }, extra);
    bridge.on_context_menu(JSON.stringify(hit), e.originalEvent.clientX, e.originalEvent.clientY);
  }

  // --- Encuadre ---------------------------------------------------------------------

  // La vista ha cambiado de tamaño o vuelve a verse: Leaflet mide otra vez su espacio y
  // pinta lo que falte (si no, se queda pintado solo lo que se veía antes)
  function refreshSize() {
    if (!map) return;
    map.invalidateSize({ pan: false });
    render();
  }

  function fitBounds(south, west, north, east, animate) {
    map.invalidateSize({ pan: false });  // encuadrar con el tamaño de ahora
    map.fitBounds([[south, west], [north, east]], {
      padding: [FIT_PADDING, FIT_PADDING],
      maxZoom: FIT_MAX_ZOOM,
      animate: animate,
    });
  }

  // zoom null = sin cambiarlo
  function setView(latitude, longitude, zoom) {
    map.invalidateSize({ pan: false });
    map.setView([latitude, longitude], zoom === null ? map.getZoom() : zoom);
  }

  function clear() {
    items.clear();
    selected = new Set();
    rebuild();
    setTracks([]);
    activeTrack = null;
    setWaypoints([]);
    setPreviewMarkers([]);
    setDropCursor(null, null);
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    bridge.on_loaded();
  });

  return {
    init, setLayers, setBaseLayer, setMarkers, updateMarkers, removeMarkers, setSelected,
    setTracks, setTrackGeometry, setActiveTrack, setTrackCursor, setWaypoints,
    setDropEnabled, setDropCursor, dropPoint, setPreviewMarkers,
    fitBounds, setView, refreshSize, clear,
  };
})();
