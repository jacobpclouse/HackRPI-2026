/* DarkWatch globe. Orbits are propagated in the browser with satellite.js. */
(function () {
  const cfg = window.DARKWATCH_CONFIG || {};
  const state = {
    viewer: null,
    sats: [],
    familiesOn: {},
    region: null,
    coverage: null,
    story: null,
    sceneOn: false,
    layers: { scene: null, tracks: [], dets: [], mpas: null, swath: null, track: null, pick: null },
    basemap: "imagery",
    speed: 1,
    step: "globe",
    showPossible: false,
  };

  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function banner(text) {
    const el = $("banner");
    if (!text) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = text;
  }

  function setStep(step) {
    state.step = step;
    document.querySelectorAll(".steps button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.step === step);
    });
  }

  const SPEEDS = [1, 10, 60, 300];

  function clockDate() {
    return Cesium.JulianDate.toDate(state.viewer.clock.currentTime);
  }

  function pad(n) { return String(n).padStart(2, "0"); }

  function offsetLabel(ms) {
    const sign = ms < 0 ? "\u2212" : "+";
    const s = Math.floor(Math.abs(ms) / 1000);
    return "T" + sign + pad(Math.floor(s / 3600)) + ":" + pad(Math.floor((s % 3600) / 60)) + ":" + pad(s % 60);
  }

  function setSpeed(next) {
    state.speed = next;
    state.viewer.clock.multiplier = next;
    $("speed").textContent = next + "\u00d7";
  }

  function returnToLive() {
    state.viewer.clock.currentTime = Cesium.JulianDate.now();
    setSpeed(1);
  }

  function renderClock() {
    const now = clockDate();
    const offset = now.getTime() - Date.now();
    const live = state.speed === 1 && Math.abs(offset) <= 5000;
    $("clock").textContent = now.toISOString().slice(11, 19) + "Z";
    const badge = $("clock-mode");
    badge.textContent = live ? "LIVE" : "SIM " + offsetLabel(offset);
    badge.className = "clock-mode " + (live ? "live" : "sim");
    $("live").hidden = live;
  }

  async function getJSON(url) {
    const response = await fetch(url);
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (err) { /* keep status text */ }
      throw new Error(detail);
    }
    return response.json();
  }

  function imagery(mode) {
    if (mode === "osm") {
      return new Cesium.UrlTemplateImageryProvider({
        url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        credit: "© OpenStreetMap contributors",
        maximumLevel: 19,
      });
    }
    return new Cesium.UrlTemplateImageryProvider({
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      credit: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
      maximumLevel: 19,
    });
  }

  async function bootViewer() {
    if (cfg.ionToken) {
      Cesium.Ion.defaultAccessToken = cfg.ionToken;
    }
    const provider = imagery("imagery");
    const viewer = new Cesium.Viewer("cesium", {
      animation: false,
      timeline: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: true,
      baseLayer: new Cesium.ImageryLayer(provider),
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    });
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#0b1c2c");
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#071018");
    viewer.clock.shouldAnimate = true;
    viewer.clock.multiplier = state.speed;
    viewer.clock.currentTime = Cesium.JulianDate.now();
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(8, 20, 18000000),
    });
    state.viewer = viewer;
    window.viewer = viewer;
    // onTick fires once per rendered frame.
    viewer.clock.onTick.addEventListener((clock) => {
      updateSatellites(Cesium.JulianDate.toDate(clock.currentTime));
      renderClock();
    });
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((click) => {
      const picked = viewer.scene.pick(click.position);
      if (picked && picked.id && picked.id.satellite) return;
      const cartesian = viewer.camera.pickEllipsoid(click.position, Cesium.Ellipsoid.WGS84);
      if (!cartesian) return;
      const carto = Cesium.Cartographic.fromCartesian(cartesian);
      selectPoint(Cesium.Math.toDegrees(carto.latitude), Cesium.Math.toDegrees(carto.longitude));
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    viewer.selectedEntityChanged.addEventListener((entity) => {
      if (entity && entity.satellite) showSatellite(entity.satellite);
    });
  }

  function updateSatellites(date) {
    if (!window.satellite) return;
    const gmst = satellite.gstime(date);
    for (const sat of state.sats) {
      if (!sat.entity.show) continue;
      const pv = satellite.propagate(sat.satrec, date);
      if (!pv.position || !isFinite(pv.position.x)) continue;
      const geo = satellite.eciToGeodetic(pv.position, gmst);
      const lat = satellite.degreesLat(geo.latitude);
      const lon = satellite.degreesLong(geo.longitude);
      sat.entity.position = Cesium.Cartesian3.fromDegrees(lon, lat, geo.height * 1000);
      sat.lat = lat;
      sat.lon = lon;
    }
  }

  async function loadSatellites() {
    const data = await getJSON("/api/satellites");
    const viewer = state.viewer;
    const families = {};
    for (const rec of data.satellites) {
      let satrec;
      try {
        satrec = satellite.twoline2satrec(rec.tle1, rec.tle2);
      } catch (err) {
        continue;
      }
      const entity = viewer.entities.add({
        name: rec.name,
        position: Cesium.Cartesian3.fromDegrees(0, 0, 700000),
        point: {
          pixelSize: rec.coverage === "systematic" ? 8 : 4,
          color: Cesium.Color.fromCssColorString(rec.color),
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 1,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: rec.coverage === "systematic" ? rec.name : "",
          font: "12px IBM Plex Sans, sans-serif",
          fillColor: Cesium.Color.fromCssColorString("#e7eef5"),
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(10, -8),
          show: rec.coverage === "systematic",
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scaleByDistance: new Cesium.NearFarScalar(8e5, 1, 2e7, 0.35),
        },
      });
      entity.satellite = rec;
      state.sats.push({ rec, satrec, entity });
      families[rec.family] = families[rec.family] || { count: 0, coverage: rec.coverage, color: rec.color };
      families[rec.family].count += 1;
      state.familiesOn[rec.family] = true;
    }
    const skipped = (data.skipped || []).filter((row) => row.reason && !/not a SAR mission/.test(row.reason));
    $("catalog-status").textContent =
      data.count + " SAR objects from CelesTrak " + (data.fetched_at || "") +
      (skipped.length ? " · " + skipped.length + " excluded after name/altitude checks" : "");
    const box = $("families");
    box.innerHTML = "";
    Object.keys(families).sort().forEach((name) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip on";
      btn.textContent = name + " " + families[name].count;
      btn.style.borderColor = families[name].color;
      btn.addEventListener("click", () => {
        state.familiesOn[name] = !state.familiesOn[name];
        btn.classList.toggle("on", state.familiesOn[name]);
        for (const sat of state.sats) {
          if (sat.rec.family === name) sat.entity.show = state.familiesOn[name] && $("toggle-sats").checked;
        }
      });
      box.appendChild(btn);
    });
    if (skipped.length) {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent = skipped.slice(0, 4).map((row) => (row.name || "query") + ": " + row.reason).join(" ");
      box.after(note);
    }
    updateSatellites(Cesium.JulianDate.toDate(viewer.clock.currentTime));
  }

  async function loadRegions() {
    const data = await getJSON("/api/regions");
    const box = $("regions");
    box.innerHTML = "";
    for (const region of data.regions) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "region";
      btn.innerHTML = "<strong>" + esc(region.name) + "</strong><small>" + esc(region.blurb) + "</small>";
      btn.addEventListener("click", () => selectRegion(region, btn));
      box.appendChild(btn);
    }
  }

  async function loadMpas() {
    const data = await getJSON("/api/mpas");
    if (!data.features || !data.features.length) return;
    const ds = await Cesium.GeoJsonDataSource.load(data, {
      stroke: Cesium.Color.fromCssColorString("#7dffb3"),
      fill: Cesium.Color.fromCssColorString("#7dffb3").withAlpha(0.12),
      strokeWidth: 2,
      clampToGround: true,
    });
    await state.viewer.dataSources.add(ds);
    state.layers.mpas = ds;
  }

  function markPoint(lat, lon, name) {
    if (state.layers.pick) state.viewer.entities.remove(state.layers.pick);
    state.layers.pick = state.viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      point: { pixelSize: 10, color: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 2 },
      label: {
        text: name,
        font: "13px IBM Plex Sans",
        pixelOffset: new Cesium.Cartesian2(0, -18),
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
  }

  async function selectRegion(region, button) {
    state.region = region;
    document.querySelectorAll(".region").forEach((el) => el.classList.remove("active"));
    if (button) button.classList.add("active");
    markPoint(region.lat, region.lon, region.name);
    state.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(region.lon, region.lat, 1800000),
      duration: 1.6,
    });
    setStep("passes");
    await loadCoverage(region.lat, region.lon, region.name);
  }

  async function selectPoint(lat, lon) {
    const region = {
      id: "custom",
      name: lat.toFixed(2) + "°, " + lon.toFixed(2) + "°",
      lat, lon,
      has_scene: false,
      blurb: "Clicked point",
    };
    document.querySelectorAll(".region").forEach((el) => el.classList.remove("active"));
    await selectRegion(region, null);
  }

  async function loadCoverage(lat, lon, title) {
    $("tl-title").textContent = "Computing passes for " + title + "…";
    $("tl-gap").textContent = "";
    $("tl-bar").innerHTML = "";
    $("tl-note").textContent = "Propagating the live catalog. This is the first request for this point.";
    try {
      const start = clockDate();
      start.setUTCSeconds(0, 0);
      start.setUTCMinutes(start.getUTCMinutes() - (start.getUTCMinutes() % 10));
      const data = await getJSON("/api/coverage?lat=" + lat + "&lon=" + lon + "&hours=48&start=" + encodeURIComponent(start.toISOString()));
      state.coverage = data;
      drawTimeline(data, "Next 48 h · " + title);
      renderPassDetail(data);
    } catch (err) {
      banner(err.message);
      $("tl-title").textContent = "Pass prediction failed";
      $("tl-note").textContent = err.message;
    }
  }

  function drawTimeline(data, title) {
    $("tl-title").textContent = title;
    const start = Date.parse(data.start);
    const end = Date.parse(data.end);
    const span = Math.max(1, end - start);
    const pct = (iso) => ((Date.parse(iso) - start) / span) * 100;
    const bar = $("tl-bar");
    bar.innerHTML = "";
    for (const gap of data.gaps || []) {
      const el = document.createElement("div");
      el.className = "tl-gap";
      el.style.left = pct(gap.start) + "%";
      el.style.width = Math.max(0.4, pct(gap.end) - pct(gap.start)) + "%";
      el.title = gap.label;
      bar.appendChild(el);
    }
    const passes = state.showPossible ? data.passes : (data.passes || []).filter((p) => p.coverage === "systematic");
    for (const pass of passes) {
      const el = document.createElement("div");
      el.className = "tl-pass " + pass.coverage;
      el.style.left = pct(pass.center) + "%";
      el.style.background = pass.color || "";
      el.title = pass.name + " · " + pass.label + " · " + pass.center.slice(11, 16) + "Z";
      bar.appendChild(el);
    }
    if (data.observed) {
      const obs = document.createElement("div");
      obs.className = "tl-obs";
      obs.style.left = pct(data.observed) + "%";
      obs.title = "Observed Sentinel-1 acquisition";
      bar.appendChild(obs);
    }
    const axis = $("tl-axis");
    axis.innerHTML = "";
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const t = new Date(start + (span * i) / ticks);
      const label = document.createElement("span");
      label.textContent = (t.getUTCMonth() + 1) + "/" + t.getUTCDate() + " " + String(t.getUTCHours()).padStart(2, "0") + "Z";
      axis.appendChild(label);
    }
    const longest = data.longest_gap;
    $("tl-gap").textContent = longest ? longest.label : "No gap in this window";
    const tasked = data.longest_gap_if_all_tasked;
    $("tl-note").textContent =
      data.systematic_pass_count + " systematic passes, " + data.possible_pass_count +
      " possible tasked accesses. " +
      (tasked ? "If every tasked access were an image, the longest hole would be " + tasked.label.replace("no systematic swath for ", "") + ". " : "") +
      (data.note || "");
  }

  function renderPassDetail(data) {
    const longest = data.longest_gap;
    const rows = (data.passes || []).filter((p) => p.coverage === "systematic").slice(0, 12);
    const html = [
      "<p><span class='tag systematic'>Systematic</span> " + data.systematic_pass_count +
      " swath overflights. <span class='tag possible'>Possible</span> " + data.possible_pass_count +
      " tasked accesses, not pictures.</p>",
      longest ? "<p class='ethics'>" + esc(longest.label) + " (" + longest.start.slice(5, 16).replace("T", " ") + "Z → " + longest.end.slice(5, 16).replace("T", " ") + "Z). Computed from the pass list.</p>" : "",
      "<div class='list'>",
    ];
    for (const pass of rows) {
      html.push(
        "<div class='sat-card'><strong>" + esc(pass.name) + "</strong> " +
        "<span class='tag systematic'>" + esc(pass.family) + "</span>" +
        "<small>" + esc(pass.center.replace("T", " ").replace("Z", " Z")) +
        " · cross-track " + pass.cross_km + " km</small></div>"
      );
    }
    html.push("</div>");
    html.push("<p class='hint'><button type='button' id='toggle-possible'>" +
      (state.showPossible ? "Hide" : "Show") + " tasked passes on the timeline</button></p>");
    $("detail-title").textContent = "Next passes";
    $("detail-body").innerHTML = html.join("");
    const toggle = $("toggle-possible");
    if (toggle) {
      toggle.addEventListener("click", () => {
        state.showPossible = !state.showPossible;
        if (state.coverage) {
          drawTimeline(state.coverage, $("tl-title").textContent);
          renderPassDetail(state.coverage);
        }
      });
    }
  }

  async function showSatellite(rec) {
    const when = Cesium.JulianDate.toDate(state.viewer.clock.currentTime).toISOString();
    $("detail-title").textContent = rec.name;
    $("detail-body").innerHTML =
      "<p><span class='tag " + rec.coverage + "'>" + esc(rec.label) + "</span> " + esc(rec.family) + "</p>" +
      "<div class='kv'><span>NORAD</span><b>" + rec.norad + "</b></div>" +
      "<div class='kv'><span>GP epoch</span><b>" + esc(rec.epoch) + "</b></div>" +
      "<div class='kv'><span>Look model</span><b>" + esc(rec.look) + "</b></div>" +
      "<p class='hint'>" + esc(rec.note) + "</p>" +
      "<p class='hint'>Swath is computed on the server from the same GP record. The icon is propagated here with satellite.js.</p>";
    try {
      const feature = await getJSON("/api/swath?norad=" + rec.norad + "&at=" + encodeURIComponent(when));
      drawSwath(feature);
      drawGroundTrack(rec);
    } catch (err) {
      banner(err.message);
    }
  }

  function drawSwath(feature) {
    if (state.layers.swath) {
      state.viewer.entities.remove(state.layers.swath);
      state.layers.swath = null;
    }
    if (!feature.geometry) {
      banner(feature.properties && feature.properties.error);
      return;
    }
    banner("");
    const ring = feature.geometry.coordinates[0];
    const flat = [];
    for (const pair of ring) flat.push(pair[0], pair[1]);
    const color = Cesium.Color.fromCssColorString(feature.properties.color || "#3ddef2");
    const possible = feature.properties.coverage === "possible";
    state.layers.swath = state.viewer.entities.add({
      polygon: {
        hierarchy: Cesium.Cartesian3.fromDegreesArray(flat),
        material: possible
          ? new Cesium.StripeMaterialProperty({
              evenColor: color.withAlpha(0.28),
              oddColor: color.withAlpha(0.05),
              repeat: 16,
            })
          : color.withAlpha(0.28),
        outline: true,
        outlineColor: color,
        height: 0,
      },
    });
  }

  function drawGroundTrack(rec) {
    if (state.layers.track) state.viewer.entities.remove(state.layers.track);
    const sat = state.sats.find((item) => item.rec.norad === rec.norad);
    if (!sat) return;
    const now = Cesium.JulianDate.toDate(state.viewer.clock.currentTime);
    const positions = [];
    for (let sec = -180; sec <= 360; sec += 20) {
      const date = new Date(now.getTime() + sec * 1000);
      const pv = satellite.propagate(sat.satrec, date);
      if (!pv.position) continue;
      const geo = satellite.eciToGeodetic(pv.position, satellite.gstime(date));
      positions.push(satellite.degreesLong(geo.longitude), satellite.degreesLat(geo.latitude));
    }
    state.layers.track = state.viewer.entities.add({
      polyline: {
        positions: Cesium.Cartesian3.fromDegreesArray(positions),
        width: 2,
        material: Cesium.Color.fromCssColorString(rec.color).withAlpha(0.9),
        clampToGround: true,
      },
    });
  }

  async function openScene() {
    setStep("scene");
    let scene;
    try {
      scene = await getJSON("/api/scene");
    } catch (err) {
      banner(err.message);
      $("detail-title").textContent = "Scene unavailable";
      $("detail-body").innerHTML = "<p>" + esc(err.message) + "</p>";
      return;
    }
    const [west, south, east, north] = scene.meta.bbox;
    const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
    state.viewer.camera.flyTo({ destination: rect, duration: 1.8 });
    await clearSceneLayers();
    const provider = await Cesium.SingleTileImageryProvider.fromUrl("/api/scene/preview.png", { rectangle: rect });
    state.layers.scene = state.viewer.imageryLayers.addImageryProvider(provider);
    const dets = await getJSON("/api/detections");
    const ais = await getJSON("/api/ais");
    addDetections(dets);
    addTracks(ais);
    const summary = scene.summary;
    $("detail-title").textContent = "Sentinel-1 scene";
    $("detail-body").innerHTML =
      "<p><strong>" + esc(summary.scene_id) + "</strong></p>" +
      "<div class='kv'><span>Acquisition</span><b>" + esc(summary.scene_time) + "</b></div>" +
      "<div class='kv'><span>Detections</span><b>" + summary.detections + "</b></div>" +
      "<div class='kv'><span>Matched to AIS</span><b>" + summary.matched + "</b></div>" +
      "<div class='kv'><span>Unmatched</span><b>" + summary.unmatched + "</b></div>" +
      "<div class='kv'><span>AIS fixes interpolated</span><b>" + summary.ais_interpolated_for_match + "</b></div>" +
      "<p class='ethics'>" + esc(summary.note) + "</p>" +
      "<div class='list' id='det-list'></div>";
    const list = $("det-list");
    const rows = dets.features.slice().sort((a, b) => Number(a.properties.matched) - Number(b.properties.matched));
    for (const feature of rows) {
      const p = feature.properties;
      const card = document.createElement("div");
      card.className = "det-card" + (p.matched ? "" : " unmatched");
      const where = p.in_mpa ? "inside " + (p.mpa_name || "MPA") : (p.near_mpa ? "within 5 km of " + (p.mpa_name || "an MPA") : "not in a packaged MPA");
      card.innerHTML = "<strong>" + esc(p.id) + "</strong> " +
        (p.matched
          ? "<span class='tag ok'>AIS " + esc(p.name || p.mmsi) + "</span>"
          : "<span class='tag red'>potential dark vessel</span>") +
        "<small>" + (p.matched ? esc(p.match_km) + " km" : "confidence " + esc(p.confidence)) +
        " · " + esc(p.peak_db) + " dB · " + esc(p.shore_km) + " km offshore · " + esc(where) + "</small>";
      card.addEventListener("click", () => focusDetection(feature));
      list.appendChild(card);
    }
    state.sceneOn = true;
    banner("");
  }

  function addDetections(collection) {
    const show = $("toggle-det").checked;
    for (const feature of collection.features) {
      const [lon, lat] = feature.geometry.coordinates;
      const matched = feature.properties.matched;
      const color = matched ? Cesium.Color.fromCssColorString("#7dffb3") : Cesium.Color.fromCssColorString("#ff5a5a");
      const entity = state.viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        show,
        ellipse: {
          semiMinorAxis: matched ? 450 : 700,
          semiMajorAxis: matched ? 450 : 700,
          material: color.withAlpha(0.35),
          outline: true,
          outlineColor: color,
          height: 0,
        },
        label: {
          text: feature.properties.id,
          font: "12px IBM Plex Mono",
          fillColor: color,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -16),
          show: !matched,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      entity.detection = feature;
      state.layers.dets.push(entity);
    }
  }

  function addTracks(collection) {
    const show = $("toggle-ais").checked;
    for (const feature of collection.features) {
      const flat = [];
      for (const pair of feature.geometry.coordinates) flat.push(pair[0], pair[1]);
      if (flat.length < 4) continue;
      const entity = state.viewer.entities.add({
        show,
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArray(flat),
          width: 1.4,
          material: Cesium.Color.fromCssColorString("#9ec9ea").withAlpha(0.75),
          clampToGround: true,
        },
      });
      state.layers.tracks.push(entity);
    }
  }

  async function focusDetection(feature) {
    const [lon, lat] = feature.geometry.coordinates;
    state.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(lon, lat, 25000),
      duration: 1.1,
    });
    const props = feature.properties;
    if (props.matched) return;
    $("detail-title").textContent = props.id + " · potential dark vessel";
    $("detail-body").innerHTML = "<p>Asking for a short brief…</p>";
    try {
      const brief = await getJSON("/api/briefs/" + encodeURIComponent(props.id));
      $("detail-body").innerHTML =
        "<p>" + esc(brief.text) + "</p>" +
        "<p class='hint'>Brief source: " + esc(brief.provider) + (brief.error ? " (" + esc(brief.error) + ")" : "") + "</p>" +
        "<p><button type='button' id='narrate-det'>Play this brief</button></p>";
      $("narrate-det").addEventListener("click", () => playNarration("candidate", props.id));
    } catch (err) {
      $("detail-body").innerHTML = "<p>" + esc(err.message) + "</p>";
    }
  }

  async function clearSceneLayers() {
    const viewer = state.viewer;
    if (state.layers.scene) {
      viewer.imageryLayers.remove(state.layers.scene, true);
      state.layers.scene = null;
    }
    for (const entity of state.layers.tracks) viewer.entities.remove(entity);
    for (const entity of state.layers.dets) viewer.entities.remove(entity);
    state.layers.tracks = [];
    state.layers.dets = [];
    state.sceneOn = false;
  }

  async function openGaps() {
    setStep("gaps");
    const region = state.region;
    if (!region || region.id !== "kattegat") {
      if (!state.coverage) {
        $("detail-body").innerHTML = "<p>Pick the Kattegat preset for the scene-day story, or any region for a 48-hour gap.</p>";
        return;
      }
      $("detail-title").textContent = "Coverage gaps";
      renderPassDetail(state.coverage);
      return;
    }
    $("detail-title").textContent = "Coverage gaps";
    $("detail-body").innerHTML = "<p>Computing scene-day passes and AIS silences…</p>";
    try {
      const story = await getJSON("/api/story");
      state.story = story;
      const day = story.scene_day;
      day.observed = story.observed_acquisition.time;
      drawTimeline(day, "2 Nov 2026 · Kattegat scene day");
      const v = story.validation;
      const offset = v.nearest ? Math.abs(v.nearest.offset_s) : null;
      const offsetMin = offset == null
        ? "no predicted Sentinel-1 pass"
        : (offset < 90 ? offset.toFixed(0) + " s" : (offset / 60).toFixed(1) + " min");
      const longest = day.longest_gap;
      const up = story.upcoming.longest_gap;
      const silenceRows = (story.ais_silences || []).slice(0, 8).map((row) => {
        return "<div class='sat-card'><strong>" + esc(row.name) + "</strong> <small>MMSI " + esc(row.mmsi) +
          " · no public AIS report for " + row.duration_h + " h" +
          (row.overlaps_coverage_gap ? " · " + (row.overlap_gap_s / 3600).toFixed(1) + " h of that sits in a SAR gap" : " · does not overlap a SAR gap") +
          "</small></div>";
      }).join("");
      $("detail-body").innerHTML =
        "<p>Observed acquisition <strong>" + esc(story.observed_acquisition.time) + "</strong> (" +
        esc(story.observed_acquisition.platform) + "). Predicted Sentinel-1 offset: <strong>" + offsetMin +
        "</strong> (" + esc(v.quality) + ").</p>" +
        (longest ? "<p class='ethics'>Scene day: " + esc(longest.label) + ".</p>" : "") +
        (up ? "<p>Next 48 h from the fresh GP epoch: " + esc(up.label) + ".</p>" : "") +
        "<p>" + story.ais_silence_count + " tracks had no public AIS report for 30 minutes or more. " +
        story.silences_overlapping_gap + " of those holes overlap a systematic coverage gap. " +
        "Each swath pass is about a minute long, so a multi-hour reporting gap usually overlaps one. A missing report is not proof the transmitter was off.</p>" +
        "<div class='list'>" + silenceRows + "</div>" +
        "<p class='hint'>" + esc(v.meaning) + "</p>" +
        "<p class='ethics'>" + esc(story.ethics) + "</p>";
      if (v.quality === "poor" || v.quality === "none") {
        banner("Scene-day orbit prediction is " + v.quality + " relative to the real acquisition (" + offsetMin + "). Prefer the next-48h gap, which sits on the fresh GP epoch.");
      } else {
        banner("");
      }
    } catch (err) {
      banner(err.message);
      $("detail-body").innerHTML = "<p>" + esc(err.message) + "</p>";
    }
  }

  async function playNarration(which, detId) {
    const url = "/api/narrate?which=" + encodeURIComponent(which || "opening") + (detId ? "&det_id=" + encodeURIComponent(detId) : "");
    let data;
    try {
      const response = await fetch(url, { method: "POST" });
      data = await response.json();
    } catch (err) {
      banner(err.message);
      return;
    }
    $("detail-title").textContent = "Narration";
    $("detail-body").innerHTML =
      "<p>" + esc(data.text) + "</p>" +
      "<p class='hint'>Voice: " + esc(data.provider) + (data.reason ? " — " + esc(data.reason) : "") +
      (data.error ? " — " + esc(data.error) : "") + "</p>";
    if (data.audio_url) {
      const audio = new Audio(data.audio_url);
      audio.play();
      return;
    }
    if (window.speechSynthesis) {
      const utter = new SpeechSynthesisUtterance(data.text);
      utter.rate = 0.96;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utter);
      $("detail-body").insertAdjacentHTML("beforeend", "<p class='hint'>Playing the browser voice. This is not Fish Audio.</p>");
    }
  }

  function wire() {
    document.querySelectorAll(".steps button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const step = btn.dataset.step;
        if (step === "globe") {
          setStep("globe");
          state.viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(10, 18, 18000000), duration: 1.4 });
          return;
        }
        if (step === "passes") {
          if (state.region) await selectRegion(state.region, document.querySelector(".region.active"));
          else setStep("passes");
          return;
        }
        if (step === "scene") {
          const kat = state.region && state.region.id === "kattegat";
          if (!kat) {
            const btnK = [...document.querySelectorAll(".region")].find((el) => el.textContent.startsWith("Kattegat"));
            if (btnK) btnK.click();
          }
          await openScene();
          return;
        }
        if (step === "gaps") await openGaps();
      });
    });
    $("narrate").addEventListener("click", () => playNarration("opening"));
    $("basemap").addEventListener("click", () => {
      state.basemap = state.basemap === "imagery" ? "osm" : "imagery";
      $("basemap").textContent = state.basemap === "imagery" ? "Imagery" : "OSM";
      const layer = state.viewer.imageryLayers.get(0);
      state.viewer.imageryLayers.remove(layer, true);
      state.viewer.imageryLayers.addImageryProvider(imagery(state.basemap), 0);
    });
    $("speed").addEventListener("click", () => {
      setSpeed(SPEEDS[(SPEEDS.indexOf(state.speed) + 1) % SPEEDS.length]);
    });
    $("live").addEventListener("click", returnToLive);
    document.addEventListener("keydown", (event) => {
      if (event.target.closest("input, textarea")) return;
      if (event.key === "l" || event.key === "L") returnToLive();
    });
    $("toggle-sats").addEventListener("change", (event) => {
      for (const sat of state.sats) {
        sat.entity.show = event.target.checked && state.familiesOn[sat.rec.family] !== false;
      }
    });
    $("toggle-mpa").addEventListener("change", (event) => {
      if (state.layers.mpas) state.layers.mpas.show = event.target.checked;
    });
    $("toggle-ais").addEventListener("change", (event) => {
      for (const entity of state.layers.tracks) entity.show = event.target.checked;
    });
    $("toggle-det").addEventListener("change", (event) => {
      for (const entity of state.layers.dets) entity.show = event.target.checked;
    });
  }

  async function main() {
    wire();
    try {
      await bootViewer();
    } catch (err) {
      banner("Cesium failed to start: " + err.message);
      return;
    }
    try {
      await Promise.all([loadSatellites(), loadRegions(), loadMpas()]);
    } catch (err) {
      banner(err.message);
    }
  }

  main();
})();
