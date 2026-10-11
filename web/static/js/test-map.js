/* Автономная имитация Leaflet-карты для полного теста мониторинга. */
(() => {
  "use strict";

  const WIDTH = 1000;
  const HEIGHT = 620;
  const BOUNDS = { west: 27, east: 49, south: 46, north: 58 };
  const CENTER = { lat: (BOUNDS.south + BOUNDS.north) / 2, lng: (BOUNDS.west + BOUNDS.east) / 2 };
  const CYCLE_SECONDS = 180;
  const objects = [
    { id: 1, name: "Борт-101", color: "#ff5e66", lat: 50.9, lng: 35.0, aLat: 1.10, aLng: 2.15, phase: 0.00 },
    { id: 2, name: "Борт-202", color: "#ffb454", lat: 51.4, lng: 37.0, aLat: 1.55, aLng: 2.65, phase: 0.17 },
    { id: 3, name: "Борт-303", color: "#ae7bff", lat: 52.4, lng: 34.3, aLat: 1.35, aLng: 3.10, phase: 0.34 },
    { id: 4, name: "Борт-404", color: "#4dc8ff", lat: 49.7, lng: 39.0, aLat: 1.45, aLng: 2.40, phase: 0.51 },
    { id: 5, name: "Борт-505", color: "#f36dd2", lat: 53.1, lng: 38.2, aLat: 1.85, aLng: 3.30, phase: 0.68 },
    { id: 6, name: "Борт-606", color: "#ffd84d", lat: 50.3, lng: 32.6, aLat: 1.20, aLng: 2.80, phase: 0.85 },
  ];
  const statics = [
    { name: "Белгород", lat: 50.595, lng: 36.587 },
    { name: "Курск", lat: 51.737, lng: 36.187 },
  ];

  const mapElement = document.getElementById("test-map");
  const regionLayer = document.getElementById("regions");
  const gridLayer = document.getElementById("grid");
  const routeLayer = document.getElementById("routes");
  const staticLayer = document.getElementById("static-markers");
  const dynamicLayer = document.getElementById("dynamic-markers");
  const list = document.getElementById("object-list");
  let speed = 1;
  let paused = false;
  let elapsed = 0;
  let lastFrame = performance.now();

  const project = ({ lat, lng }) => ({
    x: (lng - BOUNDS.west) / (BOUNDS.east - BOUNDS.west) * WIDTH,
    y: (BOUNDS.north - lat) / (BOUNDS.north - BOUNDS.south) * HEIGHT,
  });
  const unproject = ({ x, y }) => ({
    lat: BOUNDS.north - y / HEIGHT * (BOUNDS.north - BOUNDS.south),
    lng: BOUNDS.west + x / WIDTH * (BOUNDS.east - BOUNDS.west),
  });
  const svgElement = (name, attributes = {}) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  };

  function containerScale() {
    const rect = mapElement.getBoundingClientRect();
    return { x: WIDTH / rect.width, y: HEIGHT / rect.height };
  }

  // Минимальный API L.Map, который обнаруживает штатный сборщик основной программы.
  mapElement._leaflet_map = {
    getZoom: () => 7,
    getCenter: () => ({ ...CENTER }),
    containerPointToLatLng(point) {
      const scale = containerScale();
      return unproject({ x: point.x * scale.x, y: point.y * scale.y });
    },
    latLngToContainerPoint(value) {
      const lat = Array.isArray(value) ? Number(value[0]) : Number(value.lat);
      const lng = Array.isArray(value) ? Number(value[1]) : Number(value.lng);
      const point = project({ lat, lng });
      const scale = containerScale();
      return { x: point.x / scale.x, y: point.y / scale.y };
    },
  };

  function drawGrid() {
    for (let lng = 28; lng <= 48; lng += 4) {
      const x = project({ lat: CENTER.lat, lng }).x;
      gridLayer.append(svgElement("line", { x1: x, y1: 0, x2: x, y2: HEIGHT }));
      const label = svgElement("text", { x: x + 5, y: HEIGHT - 10 });
      label.textContent = `${lng}°`;
      gridLayer.append(label);
    }
    for (let lat = 48; lat <= 56; lat += 2) {
      const y = project({ lat, lng: CENTER.lng }).y;
      gridLayer.append(svgElement("line", { x1: 0, y1: y, x2: WIDTH, y2: y }));
      const label = svgElement("text", { x: 8, y: y - 6 });
      label.textContent = `${lat}°`;
      gridLayer.append(label);
    }
  }

  function polygonPath(polygon) {
    return polygon.map((ring) => ring.map(([lng, lat], index) => {
      const point = project({ lat, lng });
      return `${index ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)}`;
    }).join(" ") + " Z").join(" ");
  }

  function drawRegions() {
    const topology = window.RUSSIA_MAP_TOPOLOGY;
    const geometries = topology?.objects?.collection?.geometries || [];
    const scale = topology?.transform?.scale || [1, 1];
    const translate = topology?.transform?.translate || [0, 0];
    const arcs = (topology?.arcs || []).map((arc) => {
      let x = 0;
      let y = 0;
      return arc.map(([dx, dy]) => {
        x += dx;
        y += dy;
        return [x * scale[0] + translate[0], y * scale[1] + translate[1]];
      });
    });
    const join = (indexes) => {
      const ring = [];
      indexes.forEach((index) => {
        const source = arcs[index < 0 ? ~index : index] || [];
        const points = index < 0 ? [...source].reverse() : source;
        ring.push(...(ring.length ? points.slice(1) : points));
      });
      return ring;
    };
    const polygons = [];
    geometries.forEach((geometry) => {
      if (geometry.type === "Polygon") polygons.push(geometry.arcs.map(join));
      if (geometry.type === "MultiPolygon") geometry.arcs.forEach((polygon) => polygons.push(polygon.map(join)));
    });
    polygons.forEach((polygon) => {
      const flat = polygon.flat();
      if (!flat.some(([lng, lat]) => lng >= BOUNDS.west - 2 && lng <= BOUNDS.east + 2 && lat >= BOUNDS.south - 2 && lat <= BOUNDS.north + 2)) return;
      regionLayer.append(svgElement("path", { d: polygonPath(polygon), "fill-rule": "evenodd" }));
    });
    (window.RUSSIA_ADDITIONAL_REGIONS?.features || []).forEach((feature) => {
      const geometry = feature.geometry || {};
      const extra = geometry.type === "Polygon" ? [geometry.coordinates] : (geometry.coordinates || []);
      extra.forEach((polygon) => regionLayer.append(svgElement("path", { d: polygonPath(polygon), class: "added" })));
    });
  }

  function positionAt(item, progress) {
    const angle = Math.PI * 2 * (progress + item.phase);
    return {
      lat: item.lat + item.aLat * Math.sin(angle * 1.07) + .22 * Math.sin(angle * 2.3),
      lng: item.lng + item.aLng * Math.cos(angle) + .38 * Math.sin(angle * 1.7),
    };
  }

  function drawRoutes() {
    objects.forEach((item) => {
      let d = "";
      for (let index = 0; index <= 120; index += 1) {
        const point = project(positionAt(item, index / 120));
        d += `${index ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)} `;
      }
      routeLayer.append(svgElement("path", { d, style: `--route:${item.color}` }));
    });
  }

  function drawStaticMarkers() {
    statics.forEach((item) => {
      const point = project(item);
      const group = svgElement("g", { class: "static-marker", transform: `translate(${point.x} ${point.y})` });
      group.append(svgElement("circle", { class: "pin", r: 11 }));
      group.append(svgElement("path", { class: "cross", d: "M-5 0H5 M0-5V5" }));
      const text = svgElement("text", { x: 16, y: -12 });
      text.textContent = item.name;
      group.append(text);
      staticLayer.append(group);
    });
  }

  function createObjects() {
    objects.forEach((item) => {
      const marker = svgElement("circle", {
        class: `leaflet-marker-icon map-incident map-incident_${item.name}`,
        r: 8,
        "data-name": item.name,
        style: `--marker-color:${item.color};background-color:${item.color}`,
      });
      const title = svgElement("title");
      title.textContent = item.name;
      marker.append(title);
      dynamicLayer.append(marker);
      const label = svgElement("text", { class: "marker-label" });
      label.textContent = item.name;
      dynamicLayer.append(label);
      const row = document.createElement("div");
      row.className = "object-row";
      row.innerHTML = `<i class="object-color" style="--color:${item.color}"></i><span class="object-name">#${item.id} · ${item.name}</span><span class="object-coords"></span>`;
      list.append(row);
      item.marker = marker;
      item.label = label;
      item.coords = row.querySelector(".object-coords");
    });
    document.getElementById("object-count").textContent = String(objects.length);
  }

  function update() {
    const progress = (elapsed % CYCLE_SECONDS) / CYCLE_SECONDS;
    objects.forEach((item) => {
      const geo = positionAt(item, progress);
      const point = project(geo);
      item.marker.setAttribute("cx", point.x);
      item.marker.setAttribute("cy", point.y);
      item.marker.dataset.lat = geo.lat.toFixed(6);
      item.marker.dataset.lng = geo.lng.toFixed(6);
      item.label.setAttribute("x", point.x + 12);
      item.label.setAttribute("y", point.y - 10);
      item.coords.textContent = `${geo.lat.toFixed(5)}°, ${geo.lng.toFixed(5)}°`;
    });
  }

  function animate(now) {
    const delta = Math.min(.1, (now - lastFrame) / 1000);
    lastFrame = now;
    if (!paused) elapsed += delta * speed;
    update();
    requestAnimationFrame(animate);
  }

  document.getElementById("pause").addEventListener("click", (event) => {
    paused = !paused;
    event.currentTarget.textContent = paused ? "Продолжить" : "Пауза";
  });
  document.getElementById("reset").addEventListener("click", () => { elapsed = 0; update(); });
  document.getElementById("speed").addEventListener("change", (event) => { speed = Number(event.target.value); });

  drawRegions();
  drawGrid();
  drawRoutes();
  drawStaticMarkers();
  createObjects();
  update();
  requestAnimationFrame(animate);
})();
