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
  let tiles = null;              // capa de teselas que se ve
  let layers = {};               // clave -> {key, attribution, min_zoom, max_zoom}
  let layerKey = null;
  let group = null;              // lo que está pintado (fotos y grupos del encuadre)
  let index = null;              // índice de Supercluster
  const items = new Map();       // id -> [id, lat, lon, tipo, miniatura (1/0)]
  let selected = new Set();      // id seleccionados

  const MARKER_SIZE = 44;        // lado del recuadro de una foto o de un grupo, en px
  const CLUSTER_RADIUS = 60;     // fotos a menos de estos px se agrupan
  const FIT_PADDING = 40;        // margen al encuadrar, en px
  const FIT_MAX_ZOOM = 16;       // al encuadrar un solo punto no se acerca más que esto

  // --- Arranque ----------------------------------------------------------------

  function init(config) {
    const style = document.documentElement.style;
    for (const [name, value] of Object.entries(config.colors)) {
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

    const box = document.createElement("div");
    box.className = "arca-photo" + (properties.sel > 0 ? " selected" : "");
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
      icon: L.divIcon({ html: box, className: "", iconSize: [MARKER_SIZE, MARKER_SIZE] }),
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
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    bridge.on_loaded();
  });

  return {
    init, setLayers, setBaseLayer, setMarkers, updateMarkers, removeMarkers, setSelected,
    fitBounds, setView, clear,
  };
})();
