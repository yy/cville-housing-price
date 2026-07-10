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

const fmt = new Intl.NumberFormat("en-US");
const usd = (v) => "$" + fmt.format(Math.round(v));
const delta = (v) => (v >= 0 ? "+" : "−") + usd(Math.abs(v));

let MODE = "factor"; // "factor" | "allin"
let META = null;

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  center: [-78.55, 38.02],
  zoom: 9.4,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }));

const fillColor = () =>
  MODE === "factor"
    ? [
        "case",
        ["==", ["get", "factor"], null],
        "rgba(0,0,0,0.04)",
        ["interpolate", ["linear"], ["get", "factor"], ...DIVERGING.flat()],
      ]
    : [
        "case",
        ["==", ["get", "factor"], null],
        "rgba(0,0,0,0.04)",
        ["interpolate", ["linear"], ["get", "allin_mo"], ...SEQUENTIAL.flat()],
      ];

map.on("error", (e) => console.log("[app] map error:", e.error && e.error.message));
map.once("style.load", async () => {
  META = await fetch("data/meta.json").then((r) => r.json());
  document.getElementById("meta").textContent =
    `${fmt.format(META.n_sales)} sales ${META.window[0].slice(0, 4)}–` +
    `${META.window[1].slice(0, 4)} · hedonic model R² ${META.r2.toFixed(2)}` +
    ` · built ${META.built}`;

  map.addSource("factors", { type: "geojson", data: "data/factors.geojson" });
  map.addSource("localities", { type: "geojson", data: "data/localities.geojson" });

  map.addLayer({
    id: "factor-fill",
    type: "fill",
    source: "factors",
    paint: { "fill-color": fillColor(), "fill-opacity": 0.78 },
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
    id: "locality-line",
    type: "line",
    source: "localities",
    paint: { "line-color": "#0b0b0b", "line-width": 1.6 },
  });

  buildLegend();
  wireModeSwitch();
  wireInteraction();
  drawInsight();
});

/* ---------------------------------------------------------------- legend */

function buildLegend() {
  const el = document.getElementById("legend");
  if (MODE === "factor") {
    const stops = DIVERGING.map((d) => d[1]).join(",");
    const dm = (f) => delta(META.base_monthly * (f - 1)) + "/mo";
    el.innerHTML =
      `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
      `<div class="ticks"><span>${dm(0.65)}</span>` +
      `<span>avg ${usd(META.base_monthly)}/mo</span><span>${dm(1.55)}</span></div>` +
      `<div class="assumption">Typical home ≈ ${usd(META.ref_price)} · ` +
      `${(META.mortgage.rate * 100).toFixed(1)}% 30-yr fixed, ` +
      `${META.mortgage.down * 100}% down</div>`;
  } else {
    const stops = SEQUENTIAL.map((d) => d[1]).join(",");
    el.innerHTML =
      `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
      `<div class="ticks"><span>${usd(2300)}/mo</span><span></span>` +
      `<span>${usd(3600)}/mo</span></div>` +
      `<div class="assumption">Mortgage + driving for one downtown commuter · ` +
      `$${META.commute.cost_per_mile.toFixed(2)}/mile, ` +
      `${META.commute.days_per_month} days/mo</div>`;
  }
}

function wireModeSwitch() {
  document.querySelectorAll("#mode button").forEach((b) => {
    b.onclick = () => {
      MODE = b.dataset.mode;
      document
        .querySelectorAll("#mode button")
        .forEach((x) => x.classList.toggle("active", x === b));
      map.setPaintProperty("factor-fill", "fill-color", fillColor());
      buildLegend();
    };
  });
}

/* ----------------------------------------------------------- interaction */

function wireInteraction() {
  const tooltip = document.getElementById("tooltip");
  const detail = document.getElementById("detail");

  map.on("mousemove", "factor-fill", (e) => {
    const p = e.features[0].properties;
    map.getCanvas().style.cursor = "pointer";
    map.setFilter("factor-hover", ["==", ["get", "GEOID"], p.GEOID]);
    if (p.factor == null) { tooltip.hidden = true; return; }
    const head =
      MODE === "factor"
        ? `${(+p.factor).toFixed(2)}× · ${delta(p.mo_delta)}/mo`
        : `${usd(p.allin_mo)}/mo all-in`;
    tooltip.innerHTML =
      `<div class="tt-factor">${head}</div>` +
      `<div class="tt-sub">${usd(p.median_ppsf)}/sqft · ${p.dist_mi} mi out · ${p.n_sales} sales</div>`;
    tooltip.hidden = false;
    tooltip.style.left = e.originalEvent.clientX + 14 + "px";
    tooltip.style.top = e.originalEvent.clientY + 14 + "px";
  });
  map.on("movestart", () => (tooltip.hidden = true));
  map.on("mouseleave", "factor-fill", () => {
    map.getCanvas().style.cursor = "";
    map.setFilter("factor-hover", ["==", ["get", "GEOID"], ""]);
    tooltip.hidden = true;
  });

  map.on("click", "factor-fill", (e) => {
    const p = e.features[0].properties;
    if (p.factor == null) return;
    document.getElementById("d-title").textContent =
      `${p.locality === "cville" ? "Charlottesville" : "Albemarle"} · block group ${p.GEOID.slice(5)}`;
    document.getElementById("d-factor").textContent = (+p.factor).toFixed(2) + "×";
    document.getElementById("d-ci").textContent =
      `95% CI ${(+p.factor_lo).toFixed(2)}–${(+p.factor_hi).toFixed(2)}`;
    document.getElementById("d-table").innerHTML = [
      ["Typical home here", usd(p.est_price)],
      ["Monthly payment", usd(p.mo_pay) + "/mo"],
      ["vs. metro average", delta(p.mo_delta) + "/mo"],
      ["Distance to jobs", p.dist_mi + " mi"],
      ["Est. driving cost", usd(p.drive_mo) + "/mo"],
      ["All-in monthly", usd(p.allin_mo) + "/mo"],
      ["Median sale price", usd(p.median_price)],
      ["Median $/sqft", usd(p.median_ppsf)],
      ["Sales in window", fmt.format(p.n_sales)],
    ]
      .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`)
      .join("");
    document.getElementById("d-pooled").hidden = !(p.pooled === true || p.pooled === "true");
    detail.hidden = false;
  });
  document.getElementById("close").onclick = () => (detail.hidden = true);
}

/* -------------------------------------------------- cost-of-distance chart */

async function drawInsight() {
  const data = await fetch("data/insight.json").then((r) => r.json());
  const svg = document.getElementById("chart");
  const W = 300, H = 190, m = { l: 44, r: 16, t: 12, b: 26 };
  const xmax = 20, ymin = 1600, ymax = 3400;
  const x = (mi) => m.l + (Math.min(mi, xmax) / xmax) * (W - m.l - m.r);
  const y = (v) => H - m.b - ((Math.min(v, ymax) - ymin) / (ymax - ymin)) * (H - m.t - m.b);
  let s = "";

  // bike-range band
  s += `<rect x="${x(0)}" y="${m.t}" width="${x(data.bike_range_mi) - x(0)}" height="${H - m.t - m.b}" fill="rgba(11,11,11,0.05)"/>`;
  s += `<text x="${x(data.bike_range_mi / 2)}" y="${m.t + 10}" class="c-band" text-anchor="middle">bike range</text>`;

  // grid + axes
  for (const gv of [2000, 2500, 3000]) {
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(gv)}" y2="${y(gv)}" class="c-grid"/>`;
    s += `<text x="${m.l - 4}" y="${y(gv) + 3}" class="c-tick" text-anchor="end">$${gv / 1000}k</text>`;
  }
  for (const mi of [0, 5, 10, 15, 20]) {
    s += `<text x="${x(mi)}" y="${H - m.b + 14}" class="c-tick" text-anchor="middle">${mi}${mi === 20 ? " mi" : ""}</text>`;
  }

  // per-BG dots (housing payment); dots beyond the y-range are dropped
  let off = 0;
  for (const b of data.bgs) {
    if (b.mo_pay > ymax) { off++; continue; }
    s += `<circle cx="${x(b.dist_mi)}" cy="${y(b.mo_pay)}" r="2.4" class="c-dot"
      data-g="${b.GEOID}" data-p="${b.mo_pay}" data-a="${b.allin_mo}" data-d="${b.dist_mi}"/>`;
  }
  if (off) {
    s += `<text x="${W - m.r}" y="${m.t + 8}" class="c-tick" text-anchor="end">▲ ${off} pricier areas off scale</text>`;
  }

  // binned lines
  const line = (key) =>
    data.bins.map((b, i) => `${i ? "L" : "M"}${x(b.mi)},${y(b[key])}`).join("");
  s += `<path d="${line("allin")}" class="c-line c-allin"/>`;
  s += `<path d="${line("housing")}" class="c-line c-housing"/>`;

  const last = data.bins[data.bins.length - 1];
  s += `<text x="${x(last.mi) - 2}" y="${y(last.housing) + 12}" class="c-lab c-lab-housing" text-anchor="end">housing</text>`;
  s += `<text x="${x(last.mi) - 2}" y="${y(last.allin) - 6}" class="c-lab c-lab-allin" text-anchor="end">+ driving</text>`;

  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = s;

  const tooltip = document.getElementById("tooltip");
  svg.addEventListener("mousemove", (e) => {
    const t = e.target;
    if (!t.classList.contains("c-dot")) { tooltip.hidden = true; return; }
    tooltip.innerHTML =
      `<div class="tt-factor">${usd(t.dataset.p)}/mo · ${usd(t.dataset.a)} all-in</div>` +
      `<div class="tt-sub">${t.dataset.d} mi from downtown/UVA</div>`;
    tooltip.hidden = false;
    tooltip.style.left = e.clientX + 14 + "px";
    tooltip.style.top = e.clientY + 14 + "px";
  });
  svg.addEventListener("mouseleave", () => (tooltip.hidden = true));
}
