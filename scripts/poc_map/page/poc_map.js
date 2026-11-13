// Prueba de concepto del mapa (docs/MAPA.md, fase 0).
// La página solo pinta y avisa: Python llama a las funciones de 'arca' y recibe los
// avisos por el puente ('bridge', un QObject expuesto con QWebChannel).
"use strict";

const arca = (() => {
  let bridge = null;          // puente con Python
  let tiles = null;           // capa de teselas activa
  let track = null;           // línea del track
  let trackLatLngs = [];      // sus puntos
  let trackMerc = null;       // los mismos, proyectados (x, y por punto), para buscar el más cercano
  let trackCursor = null;     // punto señalado al pasar el ratón
  let lastHover = -1;
  let hoverFrame = 0;
  let lastMouse = null;
  let index = null;           // índice de Supercluster
  let ghost = null;           // marcador fantasma mientras se arrastra una tarjeta
  let pendingDrop = null;     // punto de la última soltada (para medir el error)

  const ATTRIBUTIONS = {
    ign_mtn: "© Instituto Geográfico Nacional de España",
    opentopo: "© OpenStreetMap, SRTM · © OpenTopoMap (CC BY-SA)",
  };
  // Metros de Mercator por píxel en el zoom 0 (teselas de 256 px)
  const MERC_WORLD = 40075016.686;
  const HOVER_PX = 12;

  const map = L.map("map", { preferCanvas: true }).setView([42.65, 0.03], 12);
  const markers = L.layerGroup().addTo(map);

  function setLayer(key) {
    if (tiles) map.removeLayer(tiles);
    tiles = L.tileLayer("arca-map://tiles/" + key + "/{z}/{x}/{y}", {
      maxNativeZoom: 17,
      maxZoom: 19,
      attribution: ATTRIBUTIONS[key] || "",
    }).addTo(map);
  }

  // --- Track ----------------------------------------------------------------

  // 'flat': [lat, lon, lat, lon, ...]
  function setTrack(flat) {
    const started = performance.now();
    if (track) map.removeLayer(track);
    trackLatLngs = [];
    trackMerc = new Float64Array(flat.length);
    for (let i = 0; i < flat.length; i += 2) {
      const latlng = L.latLng(flat[i], flat[i + 1]);
      const p = L.CRS.EPSG3857.project(latlng);
      trackLatLngs.push(latlng);
      trackMerc[i] = p.x;
      trackMerc[i + 1] = p.y;
    }
    track = L.polyline(trackLatLngs, { color: "#e0453a", weight: 3 }).addTo(map);
    map.fitBounds(track.getBounds(), { padding: [20, 20] });
    bridge.on_timing("set_track", performance.now() - started, trackLatLngs.length);
  }

  // El vértice más cercano al ratón (si está a menos de HOVER_PX píxeles)
  function hover() {
    hoverFrame = 0;
    if (!trackMerc || !lastMouse) return;
    const mouse = L.CRS.EPSG3857.project(lastMouse);
    let best = Infinity, bestIndex = -1;
    for (let i = 0; i < trackMerc.length; i += 2) {
      const dx = trackMerc[i] - mouse.x, dy = trackMerc[i + 1] - mouse.y;
      const d = dx * dx + dy * dy;
      if (d < best) { best = d; bestIndex = i / 2; }
    }
    const metersPerPixel = MERC_WORLD / (256 * Math.pow(2, map.getZoom()));
    const found = Math.sqrt(best) / metersPerPixel <= HOVER_PX ? bestIndex : -1;
    if (found >= 0) {
      if (!trackCursor) {
        trackCursor = L.circleMarker(trackLatLngs[found], {
          radius: 6, color: "#1a1a1a", fillColor: "#eca531", fillOpacity: 1, weight: 2,
          interactive: false,
        });
      }
      trackCursor.setLatLng(trackLatLngs[found]).addTo(map);
    } else if (trackCursor) {
      map.removeLayer(trackCursor);
    }
    if (found !== lastHover) {
      lastHover = found;
      bridge.on_track_hover(found);
    }
  }

  map.on("mousemove", (e) => {
    lastMouse = e.latlng;
    if (!hoverFrame) hoverFrame = requestAnimationFrame(hover);   // una vez por fotograma
  });

  // --- Marcadores agrupados ---------------------------------------------------

  // 'list': [[id, lat, lon], ...]
  function setMarkers(list) {
    const started = performance.now();
    const features = list.map((m) => ({
      type: "Feature",
      properties: { id: m[0] },
      geometry: { type: "Point", coordinates: [m[2], m[1]] },
    }));
    index = new Supercluster({ radius: 60, maxZoom: 17 }).load(features);
    renderClusters();
    bridge.on_timing("set_markers", performance.now() - started, list.length);
  }

  // Solo se pinta lo visible: los grupos y las fotos sueltas del encuadre
  function renderClusters() {
    markers.clearLayers();
    if (!index) return;
    const b = map.getBounds();
    const zoom = Math.round(map.getZoom());
    const clusters = index.getClusters([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], zoom);
    for (const c of clusters) {
      const [lon, lat] = c.geometry.coordinates;
      const isCluster = !!c.properties.cluster;
      const sample = isCluster ? index.getLeaves(c.id, 1)[0].properties.id : c.properties.id;
      const html = isCluster
        ? '<div class="cluster"><img src="arca-map://thumb/' + sample + '"><span>'
          + c.properties.point_count + "</span></div>"
        : '<div class="photo"><img src="arca-map://thumb/' + sample + '"></div>';
      const marker = L.marker([lat, lon], {
        icon: L.divIcon({ html: html, className: "", iconSize: [44, 44] }),
      });
      marker.on("click", () => {
        const ids = isCluster
          ? index.getLeaves(c.id, Infinity).map((leaf) => leaf.properties.id)
          : [sample];
        bridge.on_select(JSON.stringify(ids.slice(0, 20)), ids.length);
      });
      markers.addLayer(marker);
    }
  }

  map.on("moveend", renderClusters);

  // --- Marcador arrastrable ---------------------------------------------------

  function addDraggableMarker() {
    const marker = L.marker(map.getCenter(), {
      draggable: true,
      icon: L.divIcon({ html: '<div class="pin"></div>', className: "", iconSize: [22, 22] }),
      zIndexOffset: 1000,
    }).addTo(map);
    marker.on("dragend", () => {
      const p = marker.getLatLng();
      bridge.on_marker_moved(p.lat, p.lng);
    });
  }

  // --- Soltar tarjetas (el arrastre lo intercepta Python) -----------------------

  // x, y: píxeles de la vista (None = fin del arrastre)
  function setDropCursor(x, y) {
    if (x === null || x === undefined) {
      if (ghost) { map.removeLayer(ghost); ghost = null; }
      return;
    }
    const latlng = map.containerPointToLatLng([x, y]);
    if (!ghost) {
      ghost = L.circleMarker(latlng, {
        radius: 9, color: "#eca531", weight: 2, fillOpacity: 0.3, interactive: false,
      }).addTo(map);
    } else {
      ghost.setLatLng(latlng);
    }
  }

  function dropAt(x, y) {
    setDropCursor(null);
    const latlng = map.containerPointToLatLng([x, y]);
    L.circleMarker(latlng, {
      radius: 6, color: "#1a1a1a", fillColor: "#3fb950", fillOpacity: 1, weight: 2,
      interactive: false,
    }).addTo(map);
    pendingDrop = { x: x, y: y };   // el primer movimiento del ratón dirá dónde está de verdad
    return [latlng.lat, latlng.lng];
  }

  // Error de la soltada: distancia entre el punto que dijo Qt y donde la página ve el
  // ratón en su primer movimiento después de soltar
  document.addEventListener("mousemove", (e) => {
    if (!pendingDrop) return;
    const d = Math.hypot(e.clientX - pendingDrop.x, e.clientY - pendingDrop.y);
    pendingDrop = null;
    bridge.on_drop_error(d);
  }, true);

  // --- Ida y vuelta ------------------------------------------------------------

  function ping(token) {
    bridge.on_pong(token);
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    setLayer("ign_mtn");
    bridge.on_ready();
  });

  return { setLayer, setTrack, setMarkers, addDraggableMarker, setDropCursor, dropAt, ping };
})();
