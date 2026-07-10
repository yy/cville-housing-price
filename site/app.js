/* Housing price factor map */

const DIVERGING = [
  [0.65, "#104281"],
  [0.8, "#3987e5"],
  [0.92, "#9ec5f4"],
  [1.0, "#f0efec"],
  [1.09, "#f2b8b5"],
  [1.25, "#e34948"],
  [1.55, "#9c2726"],
];

const fmt = new Intl.NumberFormat("en-US");
const usd = (v) => "$" + fmt.format(Math.round(v));
const delta = (v) => (v >= 0 ? "+" : "−") + usd(Math.abs(v));

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  center: [-78.55, 38.02],
  zoom: 9.4,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }));

map.on("error", (e) => console.log("[app] map error:", e.error && e.error.message));
map.once("style.load", async () => {
  console.log("[app] style loaded, adding data layers");
  const meta = await fetch("data/meta.json").then((r) => r.json());
  document.getElementById("meta").textContent =
    `${fmt.format(meta.n_sales)} sales ${meta.window[0].slice(0, 4)}–` +
    `${meta.window[1].slice(0, 4)} · hedonic model R² ${meta.r2.toFixed(2)}` +
    ` · built ${meta.built}`;

  map.addSource("factors", { type: "geojson", data: "data/factors.geojson" });
  map.addSource("localities", { type: "geojson", data: "data/localities.geojson" });

  map.addLayer({
    id: "factor-fill",
    type: "fill",
    source: "factors",
    paint: {
      "fill-color": [
        "case",
        ["==", ["get", "factor"], null],
        "rgba(0,0,0,0.04)",
        ["interpolate", ["linear"], ["get", "factor"], ...DIVERGING.flat()],
      ],
      "fill-opacity": 0.78,
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
    id: "locality-line",
    type: "line",
    source: "localities",
    paint: { "line-color": "#0b0b0b", "line-width": 1.6 },
  });

  buildLegend(meta);
  wireInteraction();
});

function buildLegend(meta) {
  const el = document.getElementById("legend");
  const stops = DIVERGING.map((d) => d[1]).join(",");
  const dm = (f) => delta(meta.base_monthly * (f - 1)) + "/mo";
  el.innerHTML =
    `<div class="bar" style="background:linear-gradient(to right,${stops})"></div>` +
    `<div class="ticks"><span>${dm(0.65)}</span>` +
    `<span>avg ${usd(meta.base_monthly)}/mo</span><span>${dm(1.55)}</span></div>` +
    `<div class="assumption">Typical home ≈ ${usd(meta.ref_price)} · ` +
    `${(meta.mortgage.rate * 100).toFixed(1)}% 30-yr fixed, ` +
    `${meta.mortgage.down * 100}% down</div>`;
}

function wireInteraction() {
  const tooltip = document.getElementById("tooltip");
  const detail = document.getElementById("detail");

  map.on("mousemove", "factor-fill", (e) => {
    const p = e.features[0].properties;
    map.getCanvas().style.cursor = "pointer";
    map.setFilter("factor-hover", ["==", ["get", "GEOID"], p.GEOID]);
    if (p.factor == null) { tooltip.hidden = true; return; }
    tooltip.innerHTML =
      `<div class="tt-factor">${(+p.factor).toFixed(2)}× · ${delta(p.mo_delta)}/mo</div>` +
      `<div class="tt-sub">${usd(p.median_ppsf)}/sqft · ${p.n_sales} sales</div>`;
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
      ["Median sale price", usd(p.median_price)],
      ["Median $/sqft", usd(p.median_ppsf)],
      ["Median size", fmt.format(p.median_sqft) + " sqft"],
      ["Sales in window", fmt.format(p.n_sales)],
    ]
      .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`)
      .join("");
    document.getElementById("d-pooled").hidden = !(p.pooled === true || p.pooled === "true");
    detail.hidden = false;
  });
  document.getElementById("close").onclick = () => (detail.hidden = true);
}
