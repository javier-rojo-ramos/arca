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
  const tracks = new Map();      // id -> {id, halo, line, points, merc}
  let activeTrack = null;        // id del track activo (el único que avisa del ratón)
  let trackCursor = null;        // punto señalado en un track
  let lastHover = -1;            // último índice avisado con 'on_track_hover'
  let hoverFrame = 0;
  let lastMouse = null;

  const MARKER_SIZE = 44;        // lado del recuadro de una foto o de un grupo, en px
  const SMALL_MARKER_SIZE = 18;  // una foto suelta sin miniatura: no hay nada que enseñar
  const CLUSTER_RADIUS = 60;     // fotos a menos de estos px se agrupan
  const FIT_PADDING = 40;        // margen al encuadrar, en px
  const FIT_MAX_ZOOM = 16;       // al encuadrar un solo punto no se acerca más que esto
  const HOVER_PX = 12;           // distancia al track activo para señalar su punto, en px
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

    map.on("moveend", () => {
      render();
      reportViewport();
    });
    // Clic en el mapa vacío: se pide dejar la selección vacía (lo decide Python)
    map.on("click", () => bridge.on_select("[]", false));
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
    });
    marker.on("click", (e) => {
      const ids = isCluster
        ? index.getLeaves(feature.id, Infinity).map((leaf) => leaf.properties.id)
        : [properties.id];
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
    addTrack(data);
    restyleTracks();
  }

  function addTrack(data) {
    const segments = [];
    const points = [];
    const merc = [];
    for (const flat of data.segments) {
      const latlngs = [];
      for (let i = 0; i + 1 < flat.length; i += 2) {
        const latlng = L.latLng(flat[i], flat[i + 1]);
        const projected = L.CRS.EPSG3857.project(latlng);
        latlngs.push(latlng);
        points.push(latlng);
        merc.push(projected.x, projected.y);
      }
      if (latlngs.length) segments.push(latlngs);
    }
    const halo = L.polyline(segments, { interactive: false }).addTo(map);
    // 'bubblingMouseEvents: false': un clic en la línea no cuenta además como clic en el mapa
    const line = L.polyline(segments, { bubblingMouseEvents: false }).addTo(map);
    if (data.name) line.bindTooltip(data.name, { sticky: true });
    line.on("click", () => bridge.on_track_click(data.id));
    tracks.set(data.id, { id: data.id, halo, line, points, merc: Float64Array.from(merc) });
  }

  function removeTrack(track) {
    map.removeLayer(track.halo);
    map.removeLayer(track.line);
  }

  function setActiveTrack(id) {
    activeTrack = id;
    hideTrackCursor();
    lastHover = -1;
    restyleTracks();
  }

  // El activo, más grueso, con su color y por encima de los demás
  function restyleTracks() {
    for (const track of tracks.values()) {
      const active = track.id === activeTrack;
      const weight = active ? 4 : 3;
      track.halo.setStyle({ color: colors["track-halo"], weight: weight + 3, opacity: 0.85 });
      track.line.setStyle({
        color: active ? colors["track-active"] : colors["track"],
        weight: weight,
        opacity: 1,
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

  function showTrackCursor(track, pointIndex) {
    if (!trackCursor) {
      trackCursor = L.circleMarker(track.points[pointIndex], {
        radius: 6, weight: 2, fillOpacity: 1, interactive: false,
        color: colors["text-on-accent"], fillColor: colors["accent"],
      });
    }
    trackCursor.trackId = track.id;
    trackCursor.setLatLng(track.points[pointIndex]).addTo(map);
    trackCursor.bringToFront();
  }

  function hideTrackCursor() {
    if (trackCursor) map.removeLayer(trackCursor);
  }

  // El punto del track activo más cercano al ratón (si está a menos de HOVER_PX píxeles).
  // Con 10 000 puntos son 10 000 restas: muy por debajo de un milisegundo.
  function hover() {
    hoverFrame = 0;
    const track = tracks.get(activeTrack);
    if (!track) return;
    let found = -1;
    if (lastMouse) {
      const mouse = L.CRS.EPSG3857.project(lastMouse);
      const merc = track.merc;
      let best = Infinity, bestIndex = -1;
      for (let i = 0; i < merc.length; i += 2) {
        const dx = merc[i] - mouse.x, dy = merc[i + 1] - mouse.y;
        const d = dx * dx + dy * dy;
        if (d < best) { best = d; bestIndex = i / 2; }
      }
      const metersPerPixel = MERC_WORLD / (256 * Math.pow(2, map.getZoom()));
      if (bestIndex >= 0 && Math.sqrt(best) / metersPerPixel <= HOVER_PX) found = bestIndex;
    }
    if (found === lastHover) return;
    lastHover = found;
    if (found >= 0) showTrackCursor(track, found); else hideTrackCursor();
    bridge.on_track_hover(track.id, found);
  }

  // --- Encuadre ---------------------------------------------------------------------

  function fitBounds(south, west, north, east, animate) {
    map.fitBounds([[south, west], [north, east]], {
      padding: [FIT_PADDING, FIT_PADDING],
      maxZoom: FIT_MAX_ZOOM,
      animate: animate,
    });
  }

  // zoom null = sin cambiarlo
  function setView(latitude, longitude, zoom) {
    map.setView([latitude, longitude], zoom === null ? map.getZoom() : zoom);
  }

  function clear() {
    items.clear();
    selected = new Set();
    rebuild();
    setTracks([]);
    activeTrack = null;
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    bridge.on_loaded();
  });

  return {
    init, setLayers, setBaseLayer, setMarkers, updateMarkers, removeMarkers, setSelected,
    setTracks, setTrackGeometry, setActiveTrack, setTrackCursor,
    fitBounds, setView, clear,
  };
})();
