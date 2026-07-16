/* Housing price factor map + cost-of-distance insight */

const DIVERGING = [
  [0.65, "#104281"],
  [0.8, "#3987e5"],
  [0.92, "#9ec5f4"],
  [1.0, "#f0efec"],
  [1.09, "#f2b8b5"],
  [1.25, "#e34948"],
  [1.55, "#9c2726"],
];
// sequential blues for absolute $/month (all-in)
const SEQUENTIAL = [
  [2300, "#cde2fb"],
  [2600, "#9ec5f4"],
  [2900, "#5598e7"],
  [3200, "#256abf"],
  [3600, "#0d366b"],
];
// sequential aqua for ACS median gross rent
const RENT_SEQ = [
  [800, "#d6f0e5"],
  [1200, "#9adfc4"],
  [1600, "#4cc39a"],
  [2000, "#149268"],
  [2500, "#07523a"],
];

const fmt = new Intl.NumberFormat("en-US");
const usd = (v) => "$" + fmt.format(Math.round(v));
const delta = (v) => (v >= 0 ? "+" : "−") + usd(Math.abs(v));

let MODE = "factor"; // "factor" | "allin" | "rent" | "rentfactor" | "zori"
let META = null;
let ERAS = null; // site/data/eras.json (per-era factors for the time slider)
let ERA_IDX = 0; // index into ERAS.eras; last = headline window
let INSIGHT = null; // site/data/insight.json (cost-of-distance chart data)

const latestEra = () => !ERAS || ERA_IDX === ERAS.eras.length - 1;
const eraLabel = () => (ERAS ? ERAS.eras[ERA_IDX].label : "");
const eraRec = (geoid) => {
  if (!ERAS) return null;
  const recs = ERAS.areas[geoid];
  return recs ? recs[ERAS.eras[ERA_IDX].key] : null;
};

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  center: [-78.55, 38.02],
  zoom: 9.4,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }));

const ZORI_SEQ = [
  [1800, "#d6f0e5"],
  [2000, "#9adfc4"],
  [2200, "#4cc39a"],
  [2400, "#149268"],
  [2600, "#07523a"],
];

const RAMPS = {
  factor: ["factor", DIVERGING],
  allin: ["allin_mo", SEQUENTIAL],
  rent: ["acs_rent", RENT_SEQ],
  rentfactor: ["rent_factor", DIVERGING],
  zori: ["zori", ZORI_SEQ],
};

const fillColor = () => {
  const [prop, ramp] = RAMPS[MODE];
  if (MODE === "factor" && !latestEra()) {
    // older era: factors come from eras.json via feature-state (ef = -1
    // marks "no data in this era")
    return [
      "case",
      ["<", ["coalesce", ["feature-state", "ef"], -1], 0],
      "rgba(0,0,0,0.04)",
      [
        "interpolate",
        ["linear"],
        ["coalesce", ["feature-state", "ef"], 1],
        ...ramp.flat(),
      ],
    ];
  }
  return [
    "case",
    ["==", ["get", prop], null],
    "rgba(0,0,0,0.04)",
    ["interpolate", ["linear"], ["get", prop], ...ramp.flat()],
  ];
};

map.on("error", (e) => console.log("[app] map error:", e.error && e.error.message));
map.once("style.load", async () => {
  META = await fetch("data/meta.json", { cache: "no-cache" }).then((r) =>
    r.json()
  );
  window.__v = "?v=" + encodeURIComponent(META.built);
  ERAS = await fetch("data/eras.json" + window.__v)
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  if (ERAS) ERA_IDX = ERAS.eras.length - 1;
  document.getElementById("meta").textContent =
    `${fmt.format(META.n_sales)} sales ${META.window[0].slice(0, 4)}–` +
    `${META.window[1].slice(0, 4)} · hedonic model R² ${META.r2.toFixed(2)}` +
    ` · built ${META.built}`;

  map.addSource("factors", {
    type: "geojson",
    data: "data/factors.geojson" + window.__v,
    promoteId: "GEOID",
  });
  map.addSource("localities", { type: "geojson", data: "data/localities.geojson" + window.__v });
  map.addSource("surface", { type: "geojson", data: "data/surface.geojson" + window.__v });
  map.addSource("zori", { type: "geojson", data: "data/zori.geojson" + window.__v });

  map.addLayer({
    id: "factor-fill",
    type: "fill",
    source: "factors",
    paint: { "fill-color": fillColor(), "fill-opacity": 0.78 },
  });
  map.setPaintProperty("factor-fill", "fill-color-transition", { duration: 500 });
  map.addLayer({
    id: "surface-fill",
    type: "fill",
    source: "surface",
    layout: { visibility: "none" },
    paint: {
      "fill-color": [
        "interpolate",
        ["linear"],
        ["get", "factor_fine"],
        ...DIVERGING.flat(),
      ],
      "fill-opacity": 0.82,
      "fill-antialias": false,
    },
  });
  map.addLayer({
    id: "factor-line",
    type: "line",
    source: "factors",
    paint: { "line-color": "rgba(11,11,11,0.25)", "line-width": 0.6 },
  });
  map.addLayer({
    id: "factor-hover",
    type: "line",
    source: "factors",
    paint: { "line-color": "#0b0b0b", "line-width": 2 },
    filter: ["==", ["get", "GEOID"], ""],
  });
  map.addLayer({
    id: "zori-fill",
    type: "fill",
    source: "zori",
    layout: { visibility: "none" },
    paint: {
      "fill-color": [
        "interpolate",
        ["linear"],
        ["get", "zori"],
        ...ZORI_SEQ.flat(),
      ],
      "fill-opacity": 0.72,
    },
  });
  map.addLayer({
    id: "zori-line",
    type: "line",
    source: "zori",
    layout: { visibility: "none" },
    paint: { "line-color": "rgba(11,11,11,0.35)", "line-width": 0.8 },
  });
  map.addLayer({
    id: "locality-line",
    type: "line",
    source: "localities",
    paint: { "line-color": "#0b0b0b", "line-width": 1.6 },
  });
  buildLegend();
  wireModeSwitch();
  wireInteraction();
  buildEraUI();
  await drawInsight();
  initStory();
});

function syncSurface() {
  const zori = MODE === "zori";
  const fine =
    document.getElementById("fine").checked && MODE === "factor" && latestEra();
  const vis = (on) => (on ? "visible" : "none");
  map.setLayoutProperty("surface-fill", "visibility", vis(fine && !zori));
  map.setLayoutProperty("factor-fill", "visibility", vis(!fine && !zori));
  map.setLayoutProperty("factor-line", "visibility", vis(!fine && !zori));
  map.setLayoutProperty("zori-fill", "visibility", vis(zori));
  map.setLayoutProperty("zori-line", "visibility", vis(zori));
}

/* ------------------------------------------------------------- time slider */

function buildEraUI() {
  const wrap = document.getElementById("era-wrap");
  if (!ERAS || ERAS.eras.length < 2) {
    wrap.hidden = true;
    ERAS = null;
    return;
  }
  const n = ERAS.eras.length;
  const slider = document.getElementById("era");
  slider.max = n - 1;
  slider.value = ERA_IDX;
  slider.setAttribute("aria-label", "sales window");
  const ticks = document.getElementById("era-ticks");
  ticks.innerHTML = ERAS.eras
    .map(
      (e, i) =>
        `<span data-i="${i}" class="${i === ERA_IDX ? "active" : ""}">${e.label}</span>`
    )
    .join("");
  ticks
    .querySelectorAll("span")
    .forEach((s) => (s.onclick = () => applyEra(+s.dataset.i)));
  slider.oninput = () => applyEra(+slider.value);
  wrap.hidden = MODE !== "factor";
}

function applyEra(i) {
  if (!ERAS) return;
  ERA_IDX = Math.max(0, Math.min(i, ERAS.eras.length - 1));
  const slider = document.getElementById("era");
  slider.value = ERA_IDX;
  document
    .querySelectorAll("#era-ticks span")
    .forEach((s, j) => s.classList.toggle("active", j === ERA_IDX));
  if (!latestEra()) {
    const key = ERAS.eras[ERA_IDX].key;
    for (const g in ERAS.areas) {
      const rec = ERAS.areas[g][key];
      map.setFeatureState(
        { source: "factors", id: g },
        { ef: rec ? rec.factor : -1 }
      );
    }
    document.getElementById("fine").checked = false; // surface is headline-only
  }
  document.getElementById("fine-wrap").style.display =
    MODE === "factor" && latestEra() ? "" : "none";
  syncSurface();
  if (MODE !== "zori") {
    map.setPaintProperty("factor-fill", "fill-color", fillColor());
  }
  buildLegend();
  document.getElementById("detail").hidden = true;
}

/* ---------------------------------------------------------------- legend */

function buildLegend() {
  const el = document.getElementById("legend");
  if (MODE === "factor") {
    const stops = DIVERGING.map((d) => d[1]).join(",");
    if (!latestEra()) {
      el.innerHTML =
        `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
        `<div class="ticks"><span>0.65×</span>` +
        `<span>1.00 = typical</span><span>1.55×</span></div>` +
        `<div class="assumption">Factors from ${eraLabel()} sales · ` +
        `each era normalized to its own typical location</div>`;
      return;
    }
    const dm = (f) => delta(META.base_monthly * (f - 1)) + "/mo";
    el.innerHTML =
      `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
      `<div class="ticks"><span>${dm(0.65)}</span>` +
      `<span>typical ${usd(META.base_monthly)}/mo</span><span>${dm(1.55)}</span></div>` +
      `<div class="assumption">Typical home ≈ ${usd(META.ref_price)} · ` +
      `${(META.mortgage.rate * 100).toFixed(1)}% 30-yr fixed, ` +
      `${META.mortgage.down * 100}% down</div>`;
  } else if (MODE === "allin") {
    const stops = SEQUENTIAL.map((d) => d[1]).join(",");
    el.innerHTML =
      `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
      `<div class="ticks"><span>${usd(2300)}/mo</span><span></span>` +
      `<span>${usd(3600)}/mo</span></div>` +
      `<div class="assumption">Mortgage + driving for one downtown commuter · ` +
      `$${META.commute.cost_per_mile.toFixed(2)}/mile, ` +
      `${META.commute.days_per_month} days/mo</div>`;
  } else if (MODE === "rent") {
    const stops = RENT_SEQ.map((d) => d[1]).join(",");
    el.innerHTML =
      `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
      `<div class="ticks"><span>${usd(800)}/mo</span><span></span>` +
      `<span>${usd(2500)}/mo</span></div>` +
      `<div class="assumption">ACS 2019–23 median gross rent (incl. utilities) · ` +
      `gray = too few renters to estimate</div>`;
  } else if (MODE === "rentfactor") {
    const stops = DIVERGING.map((d) => d[1]).join(",");
    el.innerHTML =
      `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
      `<div class="ticks"><span>0.65×</span><span>1.0 = expected</span><span>1.55×</span></div>` +
      `<div class="assumption">Observed rent ÷ rent expected from the housing stock ` +
      `(bedrooms, type, age; ACS + PUMS)</div>`;
  } else {
    const stops = ZORI_SEQ.map((d) => d[1]).join(",");
    el.innerHTML =
      `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
      `<div class="ticks"><span>${usd(1800)}/mo</span><span></span>` +
      `<span>${usd(2600)}/mo</span></div>` +
      `<div class="assumption">Zillow Observed Rent Index by ZIP · market asking rents, ` +
      `updated monthly</div>`;
  }
}

function setMode(mode) {
  MODE = mode;
  document
    .querySelectorAll("#mode button")
    .forEach((x) => x.classList.toggle("active", x.dataset.mode === mode));
  if (MODE !== "zori") {
    map.setPaintProperty("factor-fill", "fill-color", fillColor());
  }
  document.getElementById("fine-wrap").style.display =
    MODE === "factor" && latestEra() ? "" : "none";
  document.getElementById("era-wrap").hidden = !(MODE === "factor" && ERAS);
  syncSurface();
  buildLegend();
}

function wireModeSwitch() {
  document.querySelectorAll("#mode button").forEach((b) => {
    b.onclick = () => setMode(b.dataset.mode);
  });
  document.getElementById("fine").onchange = syncSurface;
}

/* ----------------------------------------------------------- interaction */

function wireInteraction() {
  const tooltip = document.getElementById("tooltip");
  const detail = document.getElementById("detail");

  map.on("mousemove", "factor-fill", (e) => {
    const p = e.features[0].properties;
    map.getCanvas().style.cursor = "pointer";
    map.setFilter("factor-hover", ["==", ["get", "GEOID"], p.GEOID]);
    let head, sub;
    if (MODE === "factor" && !latestEra()) {
      const rec = eraRec(p.GEOID);
      if (!rec) { tooltip.hidden = true; return; }
      head = `${rec.factor.toFixed(2)}× in ${eraLabel()}`;
      sub =
        `95% CI ${rec.lo.toFixed(2)}–${rec.hi.toFixed(2)}` +
        (rec.pooled ? " · pooled" : "");
    } else {
      const prop = RAMPS[MODE][0];
      if (p[prop] == null) { tooltip.hidden = true; return; }
      head = {
        factor: () => `${(+p.factor).toFixed(2)}× · ${delta(p.mo_delta)}/mo`,
        allin: () => `${usd(p.allin_mo)}/mo all-in`,
        rent: () => `${usd(p.acs_rent)}/mo median rent`,
        rentfactor: () => `${(+p.rent_factor).toFixed(2)}× rent factor`,
      }[MODE]();
      sub = `${usd(p.median_ppsf)}/sqft · ${p.dist_mi} mi out · ${p.n_sales} sales`;
    }
    tooltip.innerHTML =
      `<div class="tt-factor">${head}</div>` +
      `<div class="tt-sub">${sub}</div>`;
    tooltip.hidden = false;
    tooltip.style.left = e.originalEvent.clientX + 14 + "px";
    tooltip.style.top = e.originalEvent.clientY + 14 + "px";
  });
  map.on("mousemove", "zori-fill", (e) => {
    const p = e.features[0].properties;
    tooltip.innerHTML =
      `<div class="tt-factor">${usd(p.zori)}/mo · ZIP ${p.zip}</div>` +
      `<div class="tt-sub">${p.zori_yoy != null ? p.zori_yoy + "% y/y" : "y/y n/a"}</div>`;
    tooltip.hidden = false;
    tooltip.style.left = e.originalEvent.clientX + 14 + "px";
    tooltip.style.top = e.originalEvent.clientY + 14 + "px";
  });
  map.on("mouseleave", "zori-fill", () => (tooltip.hidden = true));
  map.on("mousemove", "surface-fill", (e) => {
    const f = e.features[0].properties.factor_fine;
    tooltip.innerHTML =
      `<div class="tt-factor">${(+f).toFixed(2)}× · ${delta(META.base_monthly * (f - 1))}/mo</div>` +
      `<div class="tt-sub">smoothed local estimate</div>`;
    tooltip.hidden = false;
    tooltip.style.left = e.originalEvent.clientX + 14 + "px";
    tooltip.style.top = e.originalEvent.clientY + 14 + "px";
  });
  map.on("mouseleave", "surface-fill", () => (tooltip.hidden = true));
  map.on("movestart", () => (tooltip.hidden = true));
  map.on("mouseleave", "factor-fill", () => {
    map.getCanvas().style.cursor = "";
    map.setFilter("factor-hover", ["==", ["get", "GEOID"], ""]);
    tooltip.hidden = true;
  });

  map.on("click", "factor-fill", (e) => {
    const p = e.features[0].properties;
    const eraMode = MODE === "factor" && !latestEra();
    const rec = eraMode ? eraRec(p.GEOID) : null;
    if (eraMode ? !rec : p.factor == null) return;
    document.getElementById("d-title").textContent =
      `${p.locality === "cville" ? "Charlottesville" : "Albemarle"} · block group ${p.GEOID.slice(5)}`;
    const f = eraMode ? rec.factor : +p.factor;
    const lo = eraMode ? rec.lo : +p.factor_lo;
    const hi = eraMode ? rec.hi : +p.factor_hi;
    document.getElementById("d-factor").textContent = f.toFixed(2) + "×";
    document.getElementById("d-ci").textContent =
      `95% CI ${lo.toFixed(2)}–${hi.toFixed(2)}`;
    const eraNote = document.getElementById("d-era");
    eraNote.hidden = !eraMode;
    if (eraMode) {
      eraNote.textContent =
        `Factor from ${eraLabel()} sales. Dollar rows below reflect the ` +
        `current (${ERAS.eras[ERAS.eras.length - 1].label}) window.`;
    }
    document.getElementById("d-table").innerHTML = [
      ["Typical home here", usd(p.est_price)],
      ["Monthly payment", usd(p.mo_pay) + "/mo"],
      ["vs. typical location", delta(p.mo_delta) + "/mo"],
      ["Distance to jobs", p.dist_mi + " mi"],
      ["Est. driving cost", usd(p.drive_mo) + "/mo"],
      ["All-in (1 commuter drives)", usd(p.allin_mo) + "/mo"],
      ["All-in (2 commuters drive)", usd(p.allin2_mo) + "/mo"],
      ["Median sale price", usd(p.median_price)],
      ["Median $/sqft", usd(p.median_ppsf)],
      ["Sales in window", fmt.format(p.n_sales)],
      ...(p.acs_rent != null ? [["Median rent (ACS)", usd(p.acs_rent) + "/mo"]] : []),
      ...(p.rent_factor != null
        ? [["Rent factor", (+p.rent_factor).toFixed(2) + "×"]]
        : []),
    ]
      .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`)
      .join("");
    document.getElementById("d-pooled").hidden = !(
      eraMode ? rec.pooled === 1 : Number(p.pooled) === 1
    );
    detail.hidden = false;
  });
  document.getElementById("close").onclick = () => (detail.hidden = true);
}

/* -------------------------------------------------- cost-of-distance chart */

function renderChart(svg, data, opts = {}) {
  const show = opts.show || ["housing", "allin", "allin2"];
  const bands = opts.bands || "ebike"; // "ebike" | "both" | "none"
  const W = 300, H = 190, m = { l: 44, r: 16, t: 12, b: 26 };
  const xmax = 20, ymin = 1600, ymax = 3400;
  const x = (mi) => m.l + (Math.min(mi, xmax) / xmax) * (W - m.l - m.r);
  const y = (v) => H - m.b - ((Math.min(v, ymax) - ymin) / (ymax - ymin)) * (H - m.t - m.b);
  let s = "";

  // range bands (soft context; the real bikeability signal is the
  // green dots = inside the urban ring)
  if (bands === "both") {
    s += `<rect x="${x(0)}" y="${m.t}" width="${x(data.bike_range_mi) - x(0)}" height="${H - m.t - m.b}" fill="rgba(14,122,84,0.14)"/>`;
    s += `<rect x="${x(data.bike_range_mi)}" y="${m.t}" width="${x(data.ebike_range_mi) - x(data.bike_range_mi)}" height="${H - m.t - m.b}" fill="rgba(14,122,84,0.07)"/>`;
    s += `<text x="${x(data.bike_range_mi / 2)}" y="${m.t + 10}" class="c-band c-band-zone" text-anchor="middle">bike</text>`;
    s += `<text x="${x((data.bike_range_mi + data.ebike_range_mi) / 2)}" y="${m.t + 10}" class="c-band c-band-zone" text-anchor="middle">e-bike</text>`;
  } else if (bands === "ebike") {
    s += `<rect x="${x(0)}" y="${m.t}" width="${x(data.ebike_range_mi) - x(0)}" height="${H - m.t - m.b}" fill="rgba(11,11,11,0.05)"/>`;
    s += `<text x="${x(data.ebike_range_mi / 2)}" y="${m.t + 10}" class="c-band" text-anchor="middle">≈ e-bike range</text>`;
  }

  // grid + axes
  for (const gv of [2000, 2500, 3000]) {
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(gv)}" y2="${y(gv)}" class="c-grid"/>`;
    s += `<text x="${m.l - 4}" y="${y(gv) + 3}" class="c-tick" text-anchor="end">$${gv / 1000}k</text>`;
  }
  for (const mi of [0, 5, 10, 15, 20]) {
    s += `<text x="${x(mi)}" y="${H - m.b + 14}" class="c-tick" text-anchor="middle">${mi}${mi === 20 ? " mi" : ""}</text>`;
  }

  // per-BG dots (housing payment); green = inside the bikeable urban ring
  let off = 0;
  for (const b of data.bgs) {
    if (b.mo_pay > ymax) { off++; continue; }
    s += `<circle cx="${x(b.dist_mi)}" cy="${y(b.mo_pay)}" r="${opts.zone && b.in_zone ? 3.2 : 2.4}"
      class="c-dot${b.in_zone ? " c-dot-zone" : ""}"
      data-g="${b.GEOID}" data-p="${b.mo_pay}" data-a="${b.allin_mo}" data-d="${b.dist_mi}" data-z="${b.in_zone ? 1 : 0}"/>`;
  }
  if (off) {
    s += `<text x="${W - m.r}" y="${H - m.b - 4}" class="c-tick" text-anchor="end">▲ ${off} pricier areas off scale</text>`;
  }

  // LOESS curves
  const c = data.curves;
  const line = (key) => {
    let d = "", pen = false;
    for (let i = 0; i < c.mi.length; i++) {
      if (c[key][i] == null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${x(c.mi[i])},${y(c[key][i])}`;
      pen = true;
    }
    return d;
  };
  const order = ["allin2", "allin", "housing"];
  for (const key of order) {
    if (show.includes(key)) s += `<path d="${line(key)}" class="c-line c-${key}"/>`;
  }

  const at = c.mi.indexOf(16) >= 0 ? c.mi.indexOf(16) : c.mi.length - 4;
  for (const [key, cls, dy, label] of [
    ["housing", "c-lab-housing", 14, "housing"],
    ["allin", "c-lab-allin", -7, "+ 1 commuter"],
    ["allin2", "c-lab-allin2", -7, "+ 2 commuters"],
  ]) {
    if (!show.includes(key)) continue;
    s += `<text x="${x(c.mi[at])}" y="${y(c[key][at]) + dy}" class="c-lab ${cls}" text-anchor="middle">${label}</text>`;
  }

  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.classList.toggle("zone-hi", !!opts.zone);
  svg.innerHTML = s;

  if (svg.dataset.tt) return;
  svg.dataset.tt = "1";
  const tooltip = document.getElementById("tooltip");
  svg.addEventListener("mousemove", (e) => {
    const t = e.target;
    if (!t.classList || !t.classList.contains("c-dot")) { tooltip.hidden = true; return; }
    tooltip.innerHTML =
      `<div class="tt-factor">${usd(t.dataset.p)}/mo · ${usd(t.dataset.a)} all-in</div>` +
      `<div class="tt-sub">${t.dataset.d} mi from downtown/UVA` +
      `${t.dataset.z === "1" ? " · city proper" : ""}</div>`;
    tooltip.hidden = false;
    tooltip.style.left = e.clientX + 14 + "px";
    tooltip.style.top = e.clientY + 14 + "px";
  });
  svg.addEventListener("mouseleave", () => (tooltip.hidden = true));
}

async function drawInsight() {
  INSIGHT = await fetch("data/insight.json" + window.__v).then((r) => r.json());
  renderChart(document.getElementById("chart"), INSIGHT);
}

/* ------------------------------------------------------------- story mode */

let storyTimer = null;

function fillStoryNumbers(data) {
  const c = data.curves;
  const idx = [];
  for (let i = 0; i < c.mi.length; i++) if (c.allin[i] != null) idx.push(i);
  const first = idx[0], last = idx[idx.length - 1];
  const mid = [];
  for (let i = 0; i < c.mi.length; i++) {
    if (c.mi[i] >= 8 && c.mi[i] <= 13 && c.allin2[i] != null) mid.push(c.allin2[i]);
  }
  const vals = {
    "housing-near": usd(c.housing[first]),
    "housing-far": usd(c.housing[last]),
    "far-mi": `${c.mi[last]} miles`,
    "allin-near": usd(c.allin[first]),
    "allin-far": usd(c.allin[last]),
    "allin2-near": usd(c.allin2[first]),
    "allin2-mid": mid.length
      ? `${usd(Math.min(...mid))}–${usd(Math.max(...mid))}`
      : "",
    "bike-mi": data.bike_range_mi,
    "ebike-mi": data.ebike_range_mi,
  };
  document.querySelectorAll("#story [data-fill]").forEach((el) => {
    const v = vals[el.dataset.fill];
    if (v != null && v !== "") el.textContent = v;
  });
}

function applyStoryStep(i, el) {
  clearTimeout(storyTimer);
  if (i <= 1) setMode("factor");
  if (i === 0 && ERAS) applyEra(ERAS.eras.length - 1);
  if (i === 1 && ERAS) {
    // animate the repricing: pre-pandemic map, then dissolve to current
    applyEra(0);
    storyTimer = setTimeout(() => applyEra(ERAS.eras.length - 1), 1800);
  }
  if (i >= 2 && INSIGHT) {
    if (ERAS && !latestEra()) applyEra(ERAS.eras.length - 1);
    const optsBy = {
      2: { show: ["housing"], bands: "none" },
      3: { show: ["housing", "allin"], bands: "none" },
      4: { show: ["housing", "allin", "allin2"], bands: "none" },
      5: { show: ["housing", "allin", "allin2"], bands: "both", zone: true },
    };
    const svg = el.querySelector("svg");
    if (svg) renderChart(svg, INSIGHT, optsBy[i] || {});
  }
}

function initStory() {
  const story = document.getElementById("story");
  const btn = document.getElementById("story-btn");
  if (!story || !btn) return;
  if (INSIGHT) fillStoryNumbers(INSIGHT);

  const steps = story.querySelectorAll(".story-step");
  const obs = new IntersectionObserver(
    (entries) => {
      for (const en of entries) {
        if (en.isIntersecting) applyStoryStep(+en.target.dataset.step, en.target);
      }
    },
    { root: story, threshold: 0.5 }
  );
  steps.forEach((s) => obs.observe(s));

  const enter = () => {
    story.hidden = false;
    document.body.classList.add("storying");
    story.scrollTop = 0;
    applyStoryStep(0, steps[0]);
  };
  const exit = () => {
    clearTimeout(storyTimer);
    story.hidden = true;
    document.body.classList.remove("storying");
    if (ERAS) applyEra(ERAS.eras.length - 1);
    setMode("factor");
  };
  btn.onclick = enter;
  document.getElementById("story-exit").onclick = exit;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !story.hidden) exit();
  });
}
