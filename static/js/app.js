/* ============================================================
   B&S TERMINAL — frontend application
   Command-driven SPA. No frameworks, no build step.
   ============================================================ */

"use strict";

/* ---------------- state ---------------- */

const state = {
  func: "MKT",
  ticker: "AAPL",
  gpRange: "1Y",
  theme: localStorage.getItem("bns-theme") || "dark",
  renderToken: 0,
};

const FUNCTIONS = {
  MKT: "MARKETS",
  NDQ: "NASDAQ",
  BSE: "BSE INDIA",
  GP: "PRICE CHART",
  DES: "PROFILE",
  VOL: "VOLATILITY",
  IV: "IMPLIED VOL",
  N: "NEWS",
  OV: "OPTION VAL",
  GBM: "GBM SIM",
  MC: "MONTE CARLO",
  HB: "HEDGE BACKTEST",
  HELP: "HELP",
};

const ALIASES = { W: "MKT", MON: "MKT", NASDAQ: "NDQ", INDIA: "BSE", SENSEX: "BSE",
                  G: "GP", BT: "HB", "?": "HELP", NEWS: "N", IMPLIED: "IV", SMILE: "IV" };

const $ = (sel) => document.querySelector(sel);
const main = $("#main");

/* ---------------- utils ---------------- */

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmt(x, dp = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return Number(x).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

function pctf(x, dp = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return (x * 100).toFixed(dp) + "%";
}

function chgCls(x) { return x >= 0 ? "up" : "dn"; }
function arrow(x) { return x >= 0 ? "▲" : "▼"; }

function setStatus(msg) { $("#status-msg").textContent = msg; }

function errBox(e) {
  return `<div class="error-box">ERROR — ${esc(e.message || e)}</div>`;
}

/* ---------------- theme ---------------- */

function applyTheme() {
  document.documentElement.setAttribute("data-theme", state.theme);
  $("#theme-label").textContent = state.theme === "dark" ? "LIGHT" : "DARK";
  $("#theme-icon").textContent = state.theme === "dark" ? "◐" : "◑";
  localStorage.setItem("bns-theme", state.theme);
}

$("#theme-toggle").addEventListener("click", () => {
  state.theme = state.theme === "dark" ? "light" : "dark";
  applyTheme();
  render(); // re-render so charts pick up new palette
});

function palette() {
  const s = getComputedStyle(document.documentElement);
  const v = (name) => s.getPropertyValue(name).trim();
  return {
    bg: v("--bg"), panel: v("--panel"), text: v("--text"), muted: v("--muted"),
    accent: v("--accent"), up: v("--up"), dn: v("--dn"), grid: v("--grid"),
    cyan: v("--cyan"), purple: v("--purple"), border: v("--border"),
  };
}

function baseLayout(title, height = 380, extra = {}) {
  const p = palette();
  return Object.assign({
    title: title ? { text: `<b>${title}</b>`, font: { color: p.accent, size: 13 }, x: 0 } : undefined,
    paper_bgcolor: p.bg, plot_bgcolor: p.bg,
    font: { family: "IBM Plex Mono, monospace", color: p.text, size: 11 },
    height,
    margin: { l: 55, r: 15, t: title ? 42 : 18, b: 40 },
    xaxis: { gridcolor: p.grid, zeroline: false, linecolor: p.border, tickfont: { color: p.muted, size: 10 } },
    yaxis: { gridcolor: p.grid, zeroline: false, linecolor: p.border, tickfont: { color: p.muted, size: 10 } },
    legend: { orientation: "h", y: 1.02, x: 0, font: { size: 10, color: p.muted }, bgcolor: "rgba(0,0,0,0)" },
    hoverlabel: { bgcolor: p.panel, font: { family: "IBM Plex Mono, monospace" } },
  }, extra);
}

const PLOT_CFG = { displayModeBar: false, responsive: true };

/* Plotly.newPlot does not remove arbitrary child HTML (e.g. loading
   placeholders), so always clear the target element first. */
function plot(el, traces, layout) {
  if (typeof el === "string") el = $(el);
  if (!el) return;
  el.innerHTML = "";
  Plotly.newPlot(el, traces, layout, PLOT_CFG);
}

/* ---------------- clocks ---------------- */

function marketOpen(tz, openMin, closeMin) {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-US",
    { timeZone: tz, hour12: false, weekday: "short", hour: "2-digit", minute: "2-digit" })
    .formatToParts(now);
  const get = (t) => parts.find((p) => p.type === t)?.value;
  const wd = get("weekday");
  const mins = parseInt(get("hour"), 10) % 24 * 60 + parseInt(get("minute"), 10);
  const weekday = !["Sat", "Sun"].includes(wd);
  return { open: weekday && mins >= openMin && mins < closeMin,
           time: `${get("hour")}:${get("minute")}` };
}

function tickClocks() {
  const ny = marketOpen("America/New_York", 9 * 60 + 30, 16 * 60);
  const bom = marketOpen("Asia/Kolkata", 9 * 60 + 15, 15 * 60 + 30);
  $("#time-ny").textContent = ny.time;
  $("#time-bom").textContent = bom.time;
  for (const [id, m] of [["ny", ny], ["bom", bom]]) {
    $(`#dot-${id}`).className = `dot ${m.open ? "open" : "closed"}`;
    const el = $(`#mkt-${id}`);
    el.textContent = m.open ? "OPEN" : "CLOSED";
    el.className = `mkt ${m.open ? "open" : "closed"}`;
  }
}
setInterval(tickClocks, 15000);
tickClocks();

/* ---------------- navigation ---------------- */

function looksLikeTicker(tok) {
  return /^[A-Z0-9^.\-=]{1,14}$/.test(tok);
}

function nav(func, ticker) {
  state.func = func;
  if (ticker) state.ticker = ticker;
  $("#sec-context").textContent = `${state.ticker} · ${FUNCTIONS[state.func]}`;
  document.querySelectorAll(".fkey").forEach((b) =>
    b.classList.toggle("active", b.dataset.f === state.func));
  render();
}

function runCommand(raw) {
  const parts = raw.trim().toUpperCase().split(/\s+/).filter(Boolean);
  if (!parts.length) return;
  const head = ALIASES[parts[0]] || parts[0];
  if (FUNCTIONS[head]) {
    nav(head, parts[1] && looksLikeTicker(parts[1]) ? parts[1] : undefined);
  } else if (parts.length === 1 && looksLikeTicker(head)) {
    // bare ticker -> load its chart, Bloomberg style
    nav(["GP", "DES", "VOL", "N", "IV"].includes(state.func) ? state.func : "GP", head);
  } else {
    nav("HELP");
  }
}

$("#cmdline").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { runCommand(e.target.value); e.target.value = ""; }
});
$("#cmd-go").addEventListener("click", () => {
  runCommand($("#cmdline").value); $("#cmdline").value = "";
});
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== $("#cmdline")) {
    e.preventDefault(); $("#cmdline").focus();
  }
});

/* function keys */
const fkeysNav = $("#fkeys");
for (const [code, label] of Object.entries(FUNCTIONS)) {
  const b = document.createElement("button");
  b.className = "fkey"; b.dataset.f = code;
  b.textContent = `${code} · ${label}`;
  b.addEventListener("click", () => nav(code));
  fkeysNav.appendChild(b);
}

/* clicking: watchlist add/remove buttons, or ticker cells -> chart */
main.addEventListener("click", (e) => {
  const add = e.target.closest("[data-wl-add]");
  if (add) { wlAdd(add.dataset.wlAdd); return; }
  const rm = e.target.closest("[data-wl-rm]");
  if (rm) { wlRemove(rm.dataset.wlRm, rm.dataset.t); return; }
  const td = e.target.closest("[data-nav-ticker]");
  if (td) nav("GP", td.dataset.navTicker);
});

/* ---------------- ticker tape ---------------- */

async function loadTape() {
  try {
    const quotes = await api("/api/tape");
    const cells = quotes.filter((q) => q.last !== null).map((q) =>
      `<span class="tk">${esc(q.ticker.replace("^", ""))}</span>` +
      `<span class="px">${fmt(q.last)}</span>` +
      `<span class="chg ${chgCls(q.chg)}">${arrow(q.chg)} ${fmt(q.chg_pct)}%</span>`
    ).join("");
    $("#tape").innerHTML = cells + cells; // duplicated for seamless loop
  } catch (_) {
    $("#tape").innerHTML = `<span class="px">TAPE UNAVAILABLE — CHECK CONNECTION</span>`;
  }
}
loadTape();
setInterval(loadTape, 90000);

/* ---------------- shared components ---------------- */

function quoteTable(rows, title, sub = "", section = null) {
  const rmTh = section ? `<th></th>` : "";
  const rmTd = (q) => section
    ? `<td class="rm" title="REMOVE FROM WATCHLIST" data-wl-rm="${esc(section)}" data-t="${esc(q.ticker)}">✕</td>`
    : "";
  let body = `<table class="q"><tr><th>TICKER</th><th>NAME</th><th>LAST</th><th>CHG</th><th>CHG%</th>${rmTh}</tr>`;
  for (const q of rows) {
    if (q.last === null) {
      body += `<tr><td class="tk">${esc(q.ticker)}</td><td class="nm">${esc(q.name)}</td><td>—</td><td>—</td><td>—</td>${rmTd(q)}</tr>`;
      continue;
    }
    body += `<tr>
      <td class="tk" data-nav-ticker="${esc(q.ticker)}">${esc(q.ticker)}</td>
      <td class="nm">${esc(q.name)}</td>
      <td class="px">${fmt(q.last)}</td>
      <td class="${chgCls(q.chg)}">${q.chg >= 0 ? "+" : ""}${fmt(q.chg)}</td>
      <td class="${chgCls(q.chg)}">${q.chg >= 0 ? "+" : ""}${fmt(q.chg_pct)}%</td>${rmTd(q)}</tr>`;
  }
  body += `</table>`;
  const subHTML = section
    ? `<input class="wl-in" id="wl-in-${esc(section)}" maxlength="14"
         placeholder="${section === "bse" ? "ADD SYMBOL (e.g. TITAN)" : "ADD SYMBOL (e.g. PLTR)"}">
       <button class="wl-btn" data-wl-add="${esc(section)}">+ ADD</button>`
    : sub;
  return panel(title, body, subHTML);
}

/* --- watchlist add / remove --- */

async function wlPost(action, section, ticker) {
  const r = await fetch(`/api/watchlist/${action}?section=${encodeURIComponent(section)}` +
                        `&ticker=${encodeURIComponent(ticker)}`, { method: "POST" });
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

async function wlAdd(section) {
  const inp = $(`#wl-in-${section}`);
  const val = (inp?.value || "").trim();
  if (!val) return;
  setStatus(`ADDING ${val.toUpperCase()}…`);
  try {
    const res = await wlPost("add", section, val);
    setStatus(`ADDED ${res.ticker}`);
    render();
    loadTape();
  } catch (e) {
    setStatus(`ADD FAILED — ${String(e.message).toUpperCase()}`);
    if (inp) { inp.focus(); inp.select(); }
  }
}

async function wlRemove(section, ticker) {
  setStatus(`REMOVING ${ticker}…`);
  try {
    await wlPost("remove", section, ticker);
    setStatus(`REMOVED ${ticker}`);
    render();
    loadTape();
  } catch (e) {
    setStatus(`REMOVE FAILED — ${String(e.message).toUpperCase()}`);
  }
}

main.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.id && e.target.id.startsWith("wl-in-")) {
    wlAdd(e.target.id.replace("wl-in-", ""));
  }
});

function panel(title, bodyHTML, sub = "", pad = false) {
  return `<div class="panel"><div class="ttl"><span>${title}</span><span class="sub">${sub}</span></div>
          <div class="body${pad ? " pad" : ""}">${bodyHTML}</div></div>`;
}

function metricCard(k, v, d = "", dCls = "") {
  return `<div class="metric"><div class="k">${k}</div><div class="v">${v}</div>
          ${d ? `<div class="d ${dCls}">${d}</div>` : ""}</div>`;
}

function indexCards(indices) {
  return `<div class="index-cards">` + indices.map((q) => {
    if (q.last === null) return `<div class="index-card"><div class="nm">${esc(q.name)}</div><div class="px">—</div></div>`;
    return `<div class="index-card">
      <div class="nm">${esc(q.name)}</div>
      <div class="px">${fmt(q.last)}</div>
      <div class="chg ${chgCls(q.chg)}">${arrow(q.chg)} ${q.chg >= 0 ? "+" : ""}${fmt(q.chg)} (${q.chg >= 0 ? "+" : ""}${fmt(q.chg_pct)}%)</div>
    </div>`;
  }).join("") + `</div>`;
}

function moversHTML(watchlist) {
  const valid = watchlist.filter((q) => q.chg_pct !== null);
  const sorted = [...valid].sort((a, b) => b.chg_pct - a.chg_pct);
  const winners = sorted.slice(0, 3), losers = sorted.slice(-3).reverse();
  const chip = (q) => `<span class="mover" data-nav-ticker="${esc(q.ticker)}">
    <b>${esc(q.ticker)}</b> <span class="${chgCls(q.chg_pct)}">${q.chg_pct >= 0 ? "+" : ""}${fmt(q.chg_pct)}%</span></span>`;
  return `<div class="movers">${winners.map(chip).join("")}<span style="color:var(--faint)">|</span>${losers.map(chip).join("")}</div>`;
}

function newsHTML(items) {
  if (!items.length) return `<div class="news-item"><span class="hl">NO HEADLINES AVAILABLE</span></div>`;
  return items.map((n) => `<div class="news-item">
      ${n.link ? `<a class="hl" href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>`
               : `<span class="hl">${esc(n.title)}</span>`}
      <div class="src">${esc(n.provider)} · ${esc(n.when)}</div></div>`).join("");
}

async function drawBenchmark(elId, ticker, range = "6M", title) {
  try {
    const h = await api(`/api/history?ticker=${encodeURIComponent(ticker)}&range=${range}`);
    const p = palette();
    const el = document.getElementById(elId);
    if (!el) return;
    plot(el, [{
      x: h.t, y: h.c, type: "scatter", mode: "lines",
      line: { color: p.accent, width: 1.6 },
      fill: "tozeroy", fillcolor: state.theme === "dark" ? "rgba(255,159,10,0.06)" : "rgba(163,94,0,0.07)",
    }], baseLayout(title, 300, {
      yaxis: Object.assign(baseLayout().yaxis, {
        range: [Math.min(...h.c.filter(Number.isFinite)) * 0.97,
                Math.max(...h.c.filter(Number.isFinite)) * 1.02],
      }),
    }), PLOT_CFG);
  } catch (e) {
    const el = document.getElementById(elId);
    if (el) el.innerHTML = errBox(e);
  }
}

/* ============================================================
   PAGES
   ============================================================ */

/* ---------------- MKT / NDQ / BSE ---------------- */

function marketSectionHTML(key, m, focused) {
  const stat = m.status;
  return `
    <div class="mkt-head">
      <h2>${esc(m.label)}</h2>
      <span class="status ${stat.open ? "up" : "dn"}">● ${stat.label}</span>
      <span style="color:var(--muted);font-size:11px">LOCAL ${stat.local_time}</span>
    </div>
    ${indexCards(m.indices)}
    <div class="grid-2">
      <div>${quoteTable(m.watchlist, "WATCHLIST", "", key)}</div>
      <div>
        ${panel("MOVERS", moversHTML(m.watchlist), "TOP GAINERS | TOP LOSERS")}
        ${panel("BENCHMARK — 6M", `<div class="chart" id="bench-${key}"></div>`)}
        ${focused ? `<div id="news-${key}"></div>` : ""}
      </div>
    </div>`;
}

async function pageMKT(token) {
  main.innerHTML = `<div class="loading">LOADING GLOBAL MARKETS…</div>`;
  const mkts = await api("/api/markets");
  if (token !== state.renderToken) return;
  main.innerHTML =
    marketSectionHTML("nasdaq", mkts.nasdaq, false) +
    `<div style="height:18px"></div>` +
    marketSectionHTML("bse", mkts.bse, false);
  drawBenchmark("bench-nasdaq", mkts.nasdaq.benchmark, "6M", "NASDAQ COMPOSITE");
  drawBenchmark("bench-bse", mkts.bse.benchmark, "6M", "S&P BSE SENSEX");
}

async function pageMarketFocus(token, key, newsTicker) {
  main.innerHTML = `<div class="loading">LOADING ${key.toUpperCase()}…</div>`;
  const mkts = await api("/api/markets");
  if (token !== state.renderToken) return;
  const m = mkts[key];
  main.innerHTML = marketSectionHTML(key, m, true) +
    panel("RELATIVE PERFORMANCE — WATCHLIST 6M (REBASED = 100)",
          `<div class="chart" id="relperf-${key}"></div>`);
  drawBenchmark(`bench-${key}`, m.benchmark, "6M",
    key === "nasdaq" ? "NASDAQ COMPOSITE" : "S&P BSE SENSEX");

  // headline panel
  api(`/api/news?ticker=${encodeURIComponent(newsTicker)}&limit=6`).then((items) => {
    const el = document.getElementById(`news-${key}`);
    if (el && token === state.renderToken) el.innerHTML = panel("HEADLINES", newsHTML(items));
  }).catch(() => {});

  // relative performance of first 6 watchlist names
  const p = palette();
  const colors = [p.accent, p.cyan, p.up, p.purple, p.dn, p.muted];
  const traces = [];
  const names = m.watchlist.slice(0, 6).map((q) => q.ticker);
  await Promise.all(names.map(async (t, i) => {
    try {
      const h = await api(`/api/history?ticker=${encodeURIComponent(t)}&range=6M`);
      const base = h.c.find(Number.isFinite);
      traces.push({ x: h.t, y: h.c.map((v) => (v / base) * 100), name: t.replace(".BO", ""),
                    type: "scatter", mode: "lines", line: { width: 1.4, color: colors[i % 6] } });
    } catch (_) {}
  }));
  if (token !== state.renderToken) return;
  const el = document.getElementById(`relperf-${key}`);
  if (el) plot(el, traces, baseLayout(null, 360), PLOT_CFG);
}

/* ---------------- GP price chart ---------------- */

async function pageGP(token) {
  const ranges = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"];
  main.innerHTML = `
    <div class="panel"><div class="body form-row">
      <div class="field"><label>SECURITY</label>
        <input id="gp-ticker" value="${esc(state.ticker)}" style="width:170px"></div>
      <div class="field"><label>RANGE</label>
        <div class="range-btns">${ranges.map((rg) =>
          `<button class="fkey${rg === state.gpRange ? " active" : ""}" data-range="${rg}">${rg}</button>`).join("")}
        </div></div>
    </div></div>
    <div class="grid-4 metric-row" id="gp-metrics"></div>
    <div class="panel"><div class="body"><div class="chart" id="gp-chart"><div class="loading">LOADING…</div></div></div></div>`;

  $("#gp-ticker").addEventListener("keydown", (e) => {
    if (e.key === "Enter") nav("GP", e.target.value.trim().toUpperCase());
  });
  document.querySelectorAll("[data-range]").forEach((b) =>
    b.addEventListener("click", () => { state.gpRange = b.dataset.range; render(); }));

  try {
    const h = await api(`/api/history?ticker=${encodeURIComponent(state.ticker)}&range=${state.gpRange}`);
    if (token !== state.renderToken) return;

    const c = h.c.filter(Number.isFinite);
    const last = c[c.length - 1], first = c[0];
    const chg = last - first, chgP = (last / first - 1) * 100;
    const hi = Math.max(...h.h.filter(Number.isFinite)), lo = Math.min(...h.l.filter(Number.isFinite));
    $("#gp-metrics").innerHTML =
      metricCard("LAST", fmt(last)) +
      metricCard(`CHG (${state.gpRange})`, `${chg >= 0 ? "+" : ""}${fmt(chg)}`,
        `${chg >= 0 ? "+" : ""}${fmt(chgP)}%`, chgCls(chg)) +
      metricCard(`HIGH (${state.gpRange})`, fmt(hi)) +
      metricCard(`LOW (${state.gpRange})`, fmt(lo));

    const p = palette();
    const traces = [{
      x: h.t, open: h.o, high: h.h, low: h.l, close: h.c, type: "candlestick",
      name: state.ticker, increasing: { line: { color: p.up }, fillcolor: p.up },
      decreasing: { line: { color: p.dn }, fillcolor: p.dn }, yaxis: "y",
    }];
    // moving averages on daily/weekly data
    if (["1d", "1wk"].includes(h.interval) && h.c.length > 50) {
      const ma = (n) => h.c.map((_, i) =>
        i + 1 >= n ? h.c.slice(i + 1 - n, i + 1).reduce((a, b) => a + b, 0) / n : null);
      traces.push({ x: h.t, y: ma(20), name: "MA20", type: "scatter", mode: "lines",
                    line: { color: p.accent, width: 1 } });
      traces.push({ x: h.t, y: ma(50), name: "MA50", type: "scatter", mode: "lines",
                    line: { color: p.cyan, width: 1 } });
    }
    if (h.v.length) {
      traces.push({ x: h.t, y: h.v, type: "bar", name: "VOLUME", yaxis: "y2", opacity: 0.5,
                    marker: { color: h.c.map((cl, i) => (cl >= (h.o[i] ?? cl) ? p.up : p.dn)) } });
    }
    const layout = baseLayout(`${state.ticker} — ${state.gpRange}`, 560, {
      xaxis: Object.assign(baseLayout().xaxis, { rangeslider: { visible: false },
        rangebreaks: ["1d", "1wk", "1mo"].includes(h.interval) ? [{ bounds: ["sat", "mon"] }] : undefined }),
      yaxis: Object.assign(baseLayout().yaxis, { domain: [0.28, 1] }),
      yaxis2: Object.assign(baseLayout().yaxis, { domain: [0, 0.22] }),
      showlegend: true,
    });
    plot($("#gp-chart"), traces, layout);
  } catch (e) {
    if (token === state.renderToken) $("#gp-chart").innerHTML = errBox(e);
  }
}

/* ---------------- DES profile ---------------- */

async function pageDES(token) {
  main.innerHTML = `<div class="loading">LOADING PROFILE ${esc(state.ticker)}…</div>`;
  try {
    const d = await api(`/api/profile?ticker=${encodeURIComponent(state.ticker)}`);
    if (token !== state.renderToken) return;
    const kv = (k, v) => `<div class="cell"><div class="k">${k}</div><div class="v">${v ?? "—"}</div></div>`;
    main.innerHTML = `
      <div class="mkt-head"><h2>${esc(d.ticker)} — ${esc(d.name)}</h2></div>
      <div class="kv-grid">
        ${kv("LAST PRICE", d.last !== null && d.last !== undefined ? fmt(d.last) : "—")}
        ${kv("MARKET CAP", d.market_cap)}
        ${kv("P/E (TTM)", d.pe_ttm ? fmt(d.pe_ttm) : "—")}
        ${kv("P/E (FWD)", d.pe_fwd ? fmt(d.pe_fwd) : "—")}
        ${kv("52W HIGH", d.high_52w ? fmt(d.high_52w) : "—")}
        ${kv("52W LOW", d.low_52w ? fmt(d.low_52w) : "—")}
        ${kv("BETA", d.beta ? fmt(d.beta) : "—")}
        ${kv("DIV YIELD", d.div_yield ? pctf(d.div_yield) : "—")}
        ${kv("REVENUE (TTM)", d.revenue)}
        ${kv("NET MARGIN", d.net_margin ? pctf(d.net_margin) : "—")}
        ${kv("ROE", d.roe ? pctf(d.roe) : "—")}
        ${kv("EMPLOYEES", d.employees ? Number(d.employees).toLocaleString() : "—")}
        ${kv("SECTOR", esc(d.sector))}
        ${kv("INDUSTRY", esc(d.industry))}
        ${kv("EXCHANGE", esc(d.exchange))}
        ${kv("CURRENCY", esc(d.currency))}
      </div>
      ${d.summary ? panel("DESCRIPTION", `<div class="news-item"><span class="hl">${esc(d.summary)}</span></div>`) : ""}
      <div class="grid-2">
        <div class="panel"><div class="body"><div class="chart" id="des-chart"></div></div></div>
        <div id="des-news">${panel("HEADLINES", `<div class="loading">LOADING…</div>`)}</div>
      </div>`;
    drawBenchmark("des-chart", d.ticker, "1Y", `${d.ticker} — 1Y CLOSE`);
    api(`/api/news?ticker=${encodeURIComponent(d.ticker)}&limit=6`).then((items) => {
      if (token === state.renderToken)
        $("#des-news").innerHTML = panel(`${esc(d.ticker)} HEADLINES`, newsHTML(items));
    }).catch(() => {});
  } catch (e) {
    if (token === state.renderToken) main.innerHTML = errBox(e);
  }
}

/* ---------------- VOL ---------------- */

async function pageVOL(token) {
  main.innerHTML = `
    <div class="panel"><div class="body form-row">
      <div class="field"><label>SECURITY</label>
        <input id="vol-ticker" value="${esc(state.ticker)}" style="width:170px"></div>
      <span style="color:var(--muted);font-size:11px;padding-bottom:8px">
        REALIZED (21D / 63D ROLLING) + GARCH(1,1) ONE-DAY-AHEAD FORECAST — 2Y DAILY DATA, NO LOOK-AHEAD</span>
    </div></div>
    <div class="grid-4 metric-row" id="vol-metrics"></div>
    <div class="panel"><div class="body"><div class="chart" id="vol-chart"><div class="loading">FITTING ROLLING GARCH(1,1)…</div></div></div></div>`;

  $("#vol-ticker").addEventListener("keydown", (e) => {
    if (e.key === "Enter") nav("VOL", e.target.value.trim().toUpperCase());
  });

  try {
    const d = await api(`/api/vol?ticker=${encodeURIComponent(state.ticker)}&garch=true`);
    if (token !== state.renderToken) return;
    const m = d.metrics;
    $("#vol-metrics").innerHTML =
      metricCard("REALIZED VOL 21D", pctf(m.realized_21d)) +
      metricCard("REALIZED VOL 63D", pctf(m.realized_63d)) +
      metricCard("21D VOL — 2Y PERCENTILE", `${m.percentile_2y.toFixed(0)}%`) +
      metricCard("GARCH NEXT-DAY FCAST", m.garch_next_day ? pctf(m.garch_next_day) : "—");

    const p = palette();
    const traces = [
      { x: d.dates, y: d.close, name: "CLOSE", yaxis: "y2", type: "scatter", mode: "lines",
        line: { color: p.muted, width: 1 } },
      { x: d.dates, y: d.vol21, name: "REALIZED 21D", type: "scatter", mode: "lines",
        line: { color: p.accent, width: 1.5 } },
      { x: d.dates, y: d.vol63, name: "REALIZED 63D", type: "scatter", mode: "lines",
        line: { color: p.cyan, width: 1.5 } },
    ];
    if (d.garch) traces.push({ x: d.dates, y: d.garch, name: "GARCH(1,1) FCAST",
      type: "scatter", mode: "lines", line: { color: p.up, width: 1.4, dash: "dot" } });

    const layout = baseLayout(`${d.ticker} — PRICE & ANNUALIZED VOLATILITY (2Y)`, 560, {
      yaxis: Object.assign(baseLayout().yaxis, { domain: [0, 0.62], tickformat: ".0%" }),
      yaxis2: Object.assign(baseLayout().yaxis, { domain: [0.68, 1] }),
      xaxis: Object.assign(baseLayout().xaxis, { rangebreaks: [{ bounds: ["sat", "mon"] }] }),
      showlegend: true,
    });
    plot($("#vol-chart"), traces, layout);
  } catch (e) {
    if (token === state.renderToken) $("#vol-chart").innerHTML = errBox(e);
  }
}

/* ---------------- IV implied vol ---------------- */

async function pageIV(token) {
  const expParam = state.ivExpiry ? `&expiry=${encodeURIComponent(state.ivExpiry)}` : "";
  main.innerHTML = `
    <div class="panel"><div class="body form-row">
      <div class="field"><label>SECURITY</label>
        <input id="iv-ticker" value="${esc(state.ticker)}" style="width:170px"></div>
      <div class="field"><label>EXPIRY</label>
        <select id="iv-expiry"><option>LOADING…</option></select></div>
      <span style="color:var(--muted);font-size:11px;padding-bottom:8px">
        NEWTON–RAPHSON IV FROM MID QUOTES · OTM SKEW (PUTS BELOW SPOT, CALLS ABOVE) ·
        PREMIUM = ATM IV − REALIZED 21D</span>
    </div></div>
    <div class="grid-6 metric-row" id="iv-metrics"></div>
    <div class="grid-2">
      <div class="panel"><div class="body"><div class="chart" id="iv-smile"><div class="loading">INVERTING CHAIN…</div></div></div></div>
      <div class="panel"><div class="body"><div class="chart" id="iv-term"><div class="loading">TERM STRUCTURE…</div></div></div></div>
    </div>
    <div class="panel"><div class="body"><div class="chart" id="iv-hist"><div class="loading">REALIZED vs GARCH…</div></div></div></div>
    <div id="iv-note"></div>`;

  $("#iv-ticker").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      state.ivExpiry = null;
      nav("IV", e.target.value.trim().toUpperCase());
    }
  });

  try {
    const d = await api(`/api/iv?ticker=${encodeURIComponent(state.ticker)}${expParam}&garch=true`);
    if (token !== state.renderToken) return;
    state.ivExpiry = d.expiry;

    const sel = $("#iv-expiry");
    sel.innerHTML = d.expiries.map((ex) =>
      `<option value="${esc(ex)}"${ex === d.expiry ? " selected" : ""}>${esc(ex)}</option>`).join("");
    sel.addEventListener("change", () => { state.ivExpiry = sel.value; render(); });

    const m = d.metrics;
    const prem = m.vol_premium;
    $("#iv-metrics").innerHTML =
      metricCard("SPOT", fmt(d.spot)) +
      metricCard("ATM STRIKE", m.atm_strike != null ? fmt(m.atm_strike) : "—") +
      metricCard("ATM IV", m.atm_iv != null ? pctf(m.atm_iv) : "—") +
      metricCard("REALIZED 21D", m.realized_21d != null ? pctf(m.realized_21d) : "—") +
      metricCard("GARCH NEXT-DAY", m.garch_next_day != null ? pctf(m.garch_next_day) : "—") +
      metricCard("IV − REALIZED", prem != null ? (prem >= 0 ? "+" : "") + pctf(prem) : "—",
        prem == null ? "" : (prem >= 0 ? "OPTIONS EXPENSIVE vs HISTORY" : "OPTIONS CHEAP vs HISTORY"),
        prem == null ? "" : chgCls(prem));

    const p = palette();
    const callIV = d.calls.filter((x) => x.iv != null);
    const putIV = d.puts.filter((x) => x.iv != null);
    plot($("#iv-smile"), [
      { x: putIV.map((x) => x.strike), y: putIV.map((x) => x.iv), name: "PUT IV",
        type: "scatter", mode: "lines+markers",
        line: { color: p.purple, width: 1.3 }, marker: { size: 5 } },
      { x: callIV.map((x) => x.strike), y: callIV.map((x) => x.iv), name: "CALL IV",
        type: "scatter", mode: "lines+markers",
        line: { color: p.cyan, width: 1.3 }, marker: { size: 5 } },
      { x: d.otm_skew.map((x) => x.strike), y: d.otm_skew.map((x) => x.iv), name: "OTM SKEW",
        type: "scatter", mode: "lines",
        line: { color: p.accent, width: 2 } },
    ], baseLayout(`${d.chain_symbol} SMILE — ${d.expiry} (${d.T_days}D)`, 360, {
      yaxis: Object.assign(baseLayout().yaxis, { tickformat: ".0%" }),
      showlegend: true,
      shapes: [{ type: "line", x0: d.spot, x1: d.spot, yref: "paper", y0: 0, y1: 1,
                 line: { color: p.muted, width: 1, dash: "dot" } }],
    }));

    plot($("#iv-term"), [{
      x: d.term.map((x) => x.expiry),
      y: d.term.map((x) => x.atm_iv),
      name: "ATM IV", type: "scatter", mode: "lines+markers",
      line: { color: p.accent, width: 1.8 }, marker: { size: 7 },
    }], baseLayout("ATM IV TERM STRUCTURE", 360, {
      yaxis: Object.assign(baseLayout().yaxis, { tickformat: ".0%" }),
    }));

    const h = d.history;
    const traces = [
      { x: h.dates, y: h.vol21, name: "REALIZED 21D", type: "scatter", mode: "lines",
        line: { color: p.cyan, width: 1.4 } },
    ];
    if (h.garch) traces.push({ x: h.dates, y: h.garch, name: "GARCH(1,1) FCAST",
      type: "scatter", mode: "lines",
      line: { color: p.up, width: 1.4, dash: "dot" } });
    const layout = baseLayout(
      `${d.ticker} — IMPLIED vs REALIZED vs GARCH (LIVE ATM IV AS DASH)`, 420, {
        yaxis: Object.assign(baseLayout().yaxis, { tickformat: ".0%" }),
        showlegend: true,
        shapes: m.atm_iv == null ? [] : [{
          type: "line", xref: "paper", x0: 0, x1: 1, y0: m.atm_iv, y1: m.atm_iv,
          line: { color: p.accent, width: 1.6, dash: "dash" },
        }],
        annotations: m.atm_iv == null ? [] : [{
          xref: "paper", x: 1, y: m.atm_iv, xanchor: "right", yanchor: "bottom",
          text: "ATM IV", showarrow: false,
          font: { color: p.accent, size: 11, family: "IBM Plex Mono, monospace" },
        }],
      });
    plot($("#iv-hist"), traces, layout);

    $("#iv-note").innerHTML =
      `<div style="color:var(--faint);font-size:10.5px;letter-spacing:1px;margin-top:4px">
        CHAIN: ${esc(d.chain_symbol)} · IV SOLVED FROM BID/ASK MID VIA NEWTON–RAPHSON ON BLACK-SCHOLES.
        YAHOO DOES NOT PUBLISH HISTORICAL SINGLE-STOCK IV, SO THE AMBER DASH IS TODAY'S ATM IMPLIED —
        THE GAP TO REALIZED IS THE LIVE VOLATILITY RISK PREMIUM.
        ${d.ticker !== d.chain_symbol ? "INDEX/BSE TICKERS MAP TO THE LIQUID ETF OR NSE OPTIONS SYMBOL." : ""}
       </div>`;
  } catch (e) {
    if (token === state.renderToken) main.innerHTML = errBox(e);
  }
}

/* ---------------- N news ---------------- */

async function pageN(token) {
  main.innerHTML = `
    <div class="panel"><div class="body form-row">
      <div class="field"><label>SECURITY</label>
        <input id="n-ticker" value="${esc(state.ticker)}" style="width:170px"></div>
    </div></div>
    <div class="grid-2">
      <div id="n-sec">${panel("LOADING…", "")}</div>
      <div id="n-mkt">${panel("LOADING…", "")}</div>
    </div>`;
  $("#n-ticker").addEventListener("keydown", (e) => {
    if (e.key === "Enter") nav("N", e.target.value.trim().toUpperCase());
  });
  const isIndia = state.ticker.endsWith(".BO") || state.ticker.endsWith(".NS") || state.ticker === "^BSESN";
  const broad = isIndia ? "RELIANCE.BO" : "SPY";
  try {
    const [sec, mkt] = await Promise.all([
      api(`/api/news?ticker=${encodeURIComponent(state.ticker)}&limit=12`),
      api(`/api/news?ticker=${encodeURIComponent(broad)}&limit=12`),
    ]);
    if (token !== state.renderToken) return;
    $("#n-sec").innerHTML = panel(`${esc(state.ticker)} HEADLINES`, newsHTML(sec));
    $("#n-mkt").innerHTML = panel(isIndia ? "INDIA MARKET" : "BROAD MARKET (SPY)", newsHTML(mkt));
  } catch (e) {
    if (token === state.renderToken) main.innerHTML += errBox(e);
  }
}

/* ---------------- OV option valuation ---------------- */

function ovForm() {
  const f = (id, label, val, step = "any") =>
    `<div class="field"><label>${label}</label><input id="${id}" type="number" step="${step}" value="${val}"></div>`;
  return `
    <div class="panel"><div class="body form-row">
      ${f("ov-s", "SPOT S", 100)} ${f("ov-k", "STRIKE K", 100)}
      ${f("ov-t", "EXPIRY (TRADING DAYS)", 63, 1)} ${f("ov-r", "RATE r", 0.04)}
      ${f("ov-sig", "VOL σ (ANNUAL)", 0.25)}
      <div class="field"><label>TYPE</label>
        <select id="ov-type"><option value="call">CALL</option><option value="put">PUT</option></select></div>
      <button class="btn" id="ov-run">PRICE</button>
    </div></div>
    <div class="grid-6 metric-row" id="ov-metrics"></div>
    <div class="grid-2">
      <div class="panel"><div class="body"><div class="chart" id="ov-c1"></div></div></div>
      <div class="panel"><div class="body"><div class="chart" id="ov-c2"></div></div></div>
      <div class="panel"><div class="body"><div class="chart" id="ov-c3"></div></div></div>
      <div class="panel"><div class="body"><div class="chart" id="ov-c4"></div></div></div>
    </div>`;
}

async function runOV(token) {
  const qs = new URLSearchParams({
    S: $("#ov-s").value, K: $("#ov-k").value, T_days: $("#ov-t").value,
    r: $("#ov-r").value, sigma: $("#ov-sig").value, opt_type: $("#ov-type").value,
  });
  try {
    const d = await api(`/api/ov?${qs}`);
    if (token !== state.renderToken) return;
    const g = d.greeks;
    $("#ov-metrics").innerHTML =
      metricCard("PRICE", fmt(g.price, 4)) + metricCard("DELTA", fmt(g.delta, 4)) +
      metricCard("GAMMA", fmt(g.gamma, 5)) + metricCard("VEGA / 1%", fmt(g.vega, 4)) +
      metricCard("THETA / DAY", fmt(g.theta, 4)) + metricCard("RHO / 1%", fmt(g.rho, 4));
    const p = palette();
    const S = parseFloat($("#ov-s").value), K = parseFloat($("#ov-k").value);
    const mk = (el, key, color, title) => {
      const layout = baseLayout(title, 300, {
        shapes: [
          { type: "line", x0: K, x1: K, yref: "paper", y0: 0, y1: 1,
            line: { color: p.accent, width: 1, dash: "dash" } },
          { type: "line", x0: S, x1: S, yref: "paper", y0: 0, y1: 1,
            line: { color: p.muted, width: 1, dash: "dot" } },
        ],
      });
      plot(el, [{ x: d.spots, y: d.curves[key], type: "scatter",
        mode: "lines", line: { color, width: 1.8 } }], layout);
    };
    mk("#ov-c1", "price", p.accent, "PRICE VS SPOT");
    mk("#ov-c2", "delta", p.purple, "DELTA VS SPOT");
    mk("#ov-c3", "gamma", p.up, "GAMMA VS SPOT");
    mk("#ov-c4", "vega", p.cyan, "VEGA VS SPOT");
  } catch (e) {
    if (token === state.renderToken) $("#ov-metrics").innerHTML = errBox(e);
  }
}

function pageOV(token) {
  main.innerHTML = ovForm();
  $("#ov-run").addEventListener("click", () => runOV(state.renderToken));
  runOV(token);
}

/* ---------------- GBM simulator ---------------- */

function pageGBM(token) {
  const f = (id, label, val, step = "any") =>
    `<div class="field"><label>${label}</label><input id="${id}" type="number" step="${step}" value="${val}"></div>`;
  main.innerHTML = `
    <div class="panel"><div class="body form-row">
      ${f("gbm-s0", "SPOT S0", 100)} ${f("gbm-mu", "DRIFT μ", 0.08)}
      ${f("gbm-sig", "VOL σ", 0.25)} ${f("gbm-t", "HORIZON (DAYS)", 63, 1)}
      ${f("gbm-n", "PATHS (≤200)", 30, 1)} ${f("gbm-seed", "SEED", 42, 1)}
      <button class="btn" id="gbm-run">SIMULATE</button>
    </div></div>
    <div class="grid-3 metric-row" id="gbm-metrics"></div>
    <div class="panel"><div class="body"><div class="chart" id="gbm-chart"></div></div></div>`;

  const run = async () => {
    const token2 = state.renderToken;
    const qs = new URLSearchParams({
      S0: $("#gbm-s0").value, mu: $("#gbm-mu").value, sigma: $("#gbm-sig").value,
      T_days: $("#gbm-t").value, n_paths: $("#gbm-n").value, seed: $("#gbm-seed").value,
    });
    $("#gbm-chart").innerHTML = `<div class="loading">SIMULATING…</div>`;
    try {
      const d = await api(`/api/gbm?${qs}`);
      if (token2 !== state.renderToken) return;
      $("#gbm-metrics").innerHTML =
        metricCard("MEAN FINAL PRICE", fmt(d.stats.mean_final)) +
        metricCard("STD DEV", fmt(d.stats.std_final)) +
        metricCard("MIN / MAX", `${fmt(d.stats.min_final)} / ${fmt(d.stats.max_final)}`);
      const p = palette();
      const traces = d.paths.map((path) => ({
        x: d.t, y: path, type: "scatter", mode: "lines", hoverinfo: "skip",
        line: { width: 1, color: state.theme === "dark" ? "rgba(56,189,248,0.30)" : "rgba(11,107,203,0.25)" },
        showlegend: false,
      }));
      traces.push({ x: d.t, y: d.mean_path, name: "MEAN PATH", type: "scatter",
        mode: "lines", line: { color: p.accent, width: 3 } });
      plot($("#gbm-chart"), traces,
        baseLayout(`${d.paths.length} SIMULATED GBM PATHS`, 480, { showlegend: true }), PLOT_CFG);
    } catch (e) {
      if (token2 === state.renderToken) $("#gbm-chart").innerHTML = errBox(e);
    }
  };
  $("#gbm-run").addEventListener("click", run);
  run();
}

/* ---------------- MC pricer ---------------- */

function pageMC(token) {
  const f = (id, label, val, step = "any") =>
    `<div class="field"><label>${label}</label><input id="${id}" type="number" step="${step}" value="${val}"></div>`;
  main.innerHTML = `
    <div class="panel"><div class="body form-row">
      ${f("mc-s0", "SPOT S0", 100)} ${f("mc-k", "STRIKE K", 100)}
      ${f("mc-r", "RATE r", 0.04)} ${f("mc-sig", "VOL σ", 0.25)}
      ${f("mc-t", "EXPIRY (DAYS)", 63, 1)} ${f("mc-steps", "STEPS", 63, 1)}
      ${f("mc-n", "PATHS", 20000, 1000)}
      <div class="field"><label>TYPE</label>
        <select id="mc-type"><option value="call">CALL</option><option value="put">PUT</option></select></div>
      <button class="btn" id="mc-run">RUN PRICING</button>
    </div></div>
    <div class="grid-3 metric-row" id="mc-metrics"></div>
    <div class="grid-2">
      <div class="panel"><div class="body"><div class="chart" id="mc-c1"></div></div></div>
      <div class="panel"><div class="body"><div class="chart" id="mc-c2"></div></div></div>
    </div>`;

  const run = async () => {
    const token2 = state.renderToken;
    const qs = new URLSearchParams({
      S0: $("#mc-s0").value, K: $("#mc-k").value, r: $("#mc-r").value,
      sigma: $("#mc-sig").value, T_days: $("#mc-t").value, n_steps: $("#mc-steps").value,
      n_paths: $("#mc-n").value, opt_type: $("#mc-type").value, seed: 42,
    });
    $("#mc-c1").innerHTML = `<div class="loading">SIMULATING…</div>`;
    try {
      const d = await api(`/api/mc?${qs}`);
      if (token2 !== state.renderToken) return;
      $("#mc-metrics").innerHTML =
        metricCard("MONTE CARLO PRICE", fmt(d.mc_price, 4), `± ${fmt(d.ci95, 4)} (95% CI)`) +
        metricCard("BLACK-SCHOLES PRICE", fmt(d.bs_price, 4)) +
        metricCard("DIFFERENCE", `${d.diff >= 0 ? "+" : ""}${fmt(d.diff, 4)}`, "",
          Math.abs(d.diff) < d.ci95 ? "up" : "dn");
      const p = palette();
      const K = parseFloat($("#mc-k").value);
      plot($("#mc-c1"), [{ x: d.final_prices, type: "histogram", nbinsx: 60,
        marker: { color: p.cyan }, opacity: 0.85 }],
        baseLayout("SIMULATED FINAL PRICES", 340, {
          shapes: [{ type: "line", x0: K, x1: K, yref: "paper", y0: 0, y1: 1,
                     line: { color: p.accent, width: 1, dash: "dash" } }],
        }), PLOT_CFG);
      plot($("#mc-c2"), [{ x: d.payoffs, type: "histogram", nbinsx: 60,
        marker: { color: p.purple }, opacity: 0.85 }],
        baseLayout("OPTION PAYOFFS", 340), PLOT_CFG);
    } catch (e) {
      if (token2 === state.renderToken) $("#mc-c1").innerHTML = errBox(e);
    }
  };
  $("#mc-run").addEventListener("click", run);
  run();
}

/* ---------------- HB hedge backtest ---------------- */

const SCENARIOS = {
  "2008 FINANCIAL CRISIS": "2008-09-01",
  "CALM PERIOD (2017)": "2017-01-03",
  "COVID CRASH (2020)": "2020-02-14",
  "SVB / REGIONAL BANK CRISIS (2023)": "2023-03-01",
};

function pageHB(token) {
  const f = (id, label, val, opts = "") =>
    `<div class="field"><label>${label}</label><input id="${id}" ${opts} value="${val}"></div>`;
  main.innerHTML = `
    <div class="panel"><div class="ttl"><span>HISTORICAL DELTA-HEDGE BACKTEST</span>
      <span class="sub">SHORT ONE OPTION, HEDGE WITH THE UNDERLYING — STATIC vs ROLLING vs GARCH VOL</span></div>
    <div class="body form-row">
      ${f("hb-ticker", "SECURITY", state.ticker, 'style="width:150px"')}
      <div class="field"><label>SCENARIO</label>
        <select id="hb-scenario">${Object.keys(SCENARIOS).map((s) =>
          `<option>${s}</option>`).join("")}</select></div>
      ${f("hb-start", "START DATE", "2023-03-01", 'type="date"')}
      ${f("hb-window", "WINDOW (DAYS)", 63, 'type="number" min="20" max="252"')}
      ${f("hb-kmult", "STRIKE % OF S0", 1.0, 'type="number" step="0.01"')}
      ${f("hb-r", "RATE r", 0.04, 'type="number" step="any"')}
      ${f("hb-tc", "TXN COST", 0.001, 'type="number" step="any"')}
      ${f("hb-reb", "REBAL EVERY N", 1, 'type="number" min="1"')}
      <div class="field"><label>TYPE</label>
        <select id="hb-type"><option value="call">CALL</option><option value="put">PUT</option></select></div>
      <button class="btn" id="hb-run">RUN BACKTEST</button>
    </div></div>
    <div id="hb-out"></div>`;

  $("#hb-scenario").addEventListener("change", (e) => {
    $("#hb-start").value = SCENARIOS[e.target.value];
  });
  $("#hb-scenario").value = "SVB / REGIONAL BANK CRISIS (2023)";

  $("#hb-run").addEventListener("click", async () => {
    const token2 = state.renderToken;
    const out = $("#hb-out");
    out.innerHTML = `<div class="loading">REPLAYING HEDGE ENGINE (GARCH REFITS)…</div>`;
    const qs = new URLSearchParams({
      ticker: $("#hb-ticker").value.trim().toUpperCase(),
      start: $("#hb-start").value, window_days: $("#hb-window").value,
      k_mult: $("#hb-kmult").value, r: $("#hb-r").value, tc: $("#hb-tc").value,
      rebalance: $("#hb-reb").value, opt_type: $("#hb-type").value,
    });
    try {
      const d = await api(`/api/backtest?${qs}`);
      if (token2 !== state.renderToken) return;
      const p = palette();
      const s = d.strategies;
      out.innerHTML = `
        <div class="grid-3 metric-row">
          ${metricCard("START PRICE", fmt(d.start_price))}
          ${metricCard("STRIKE", fmt(d.strike))}
          ${metricCard("REALIZED VOL (WINDOW)", pctf(d.realized_vol))}
        </div>
        <div class="grid-3 metric-row">
          ${Object.values(s).map((st) => metricCard(st.label,
            `HEDGED ${st.hedged_pnl >= 0 ? "+" : ""}${fmt(st.hedged_pnl)}`,
            `UNHEDGED ${st.unhedged_pnl >= 0 ? "+" : ""}${fmt(st.unhedged_pnl)}`,
            chgCls(st.hedged_pnl))).join("")}
        </div>
        <div class="grid-2">
          <div class="panel"><div class="body"><div class="chart" id="hb-c1"></div></div></div>
          <div class="panel"><div class="body"><div class="chart" id="hb-c2"></div></div></div>
        </div>
        <div class="panel"><div class="body"><div class="chart" id="hb-c3"></div></div></div>
        <div style="color:var(--faint);font-size:10.5px;letter-spacing:1px;margin-top:4px">
          HEDGED P&amp;L CLOSER TO 0 WITH LOWER VARIANCE = BETTER HEDGE. CRISIS WINDOWS ARE WHERE
          VOL FORECASTING EARNS ITS KEEP.</div>`;

      plot($("#hb-c1"), [{ x: d.dates, y: d.prices, type: "scatter",
        mode: "lines", line: { color: p.cyan, width: 1.6 }, name: "PRICE" }],
        baseLayout(`${d.ticker} — PRICE PATH`, 330, {
          shapes: [{ type: "line", x0: d.dates[0], x1: d.dates[d.dates.length - 1],
                     y0: d.strike, y1: d.strike, line: { color: p.accent, width: 1, dash: "dash" } }],
        }), PLOT_CFG);

      plot($("#hb-c2"), [
        { x: d.dates, y: s.static.sigma_series, name: "STATIC σ", type: "scatter",
          mode: "lines", line: { color: p.muted, dash: "dot" } },
        { x: d.dates, y: s.rolling.sigma_series, name: "ROLLING", type: "scatter",
          mode: "lines", line: { color: p.purple } },
        { x: d.dates, y: s.garch.sigma_series, name: "GARCH", type: "scatter",
          mode: "lines", line: { color: p.up } },
      ], baseLayout("HEDGE VOL SERIES", 330, {
        yaxis: Object.assign(baseLayout().yaxis, { tickformat: ".0%" }), showlegend: true,
      }), PLOT_CFG);

      plot($("#hb-c3"), [
        { y: s.static.portfolio_value, name: "STATIC σ", type: "scatter", mode: "lines",
          line: { color: p.muted, width: 1.4 } },
        { y: s.rolling.portfolio_value, name: "ROLLING", type: "scatter", mode: "lines",
          line: { color: p.purple, width: 1.4 } },
        { y: s.garch.portfolio_value, name: "GARCH", type: "scatter", mode: "lines",
          line: { color: p.up, width: 1.4 } },
      ], baseLayout("HEDGE PORTFOLIO VALUE (CASH + STOCK, PRE-PAYOUT)", 340,
        { showlegend: true }), PLOT_CFG);
    } catch (e) {
      if (token2 === state.renderToken) out.innerHTML = errBox(e);
    }
  });
}

/* ---------------- HELP ---------------- */

function pageHELP() {
  const rows = [
    ["MKT", "GLOBAL MARKETS — NASDAQ + BSE SECTIONS, INDICES, WATCHLISTS, MOVERS"],
    ["NDQ", "NASDAQ SECTION — COMPOSITE, WATCHLIST, RELATIVE PERFORMANCE, HEADLINES"],
    ["BSE", "BSE INDIA SECTION — SENSEX, .BO WATCHLIST, RELATIVE PERFORMANCE"],
    ["GP <TICKER>", "PRICE CHART — CANDLES, VOLUME, MA20/MA50 (E.G. GP RELIANCE.BO)"],
    ["DES <TICKER>", "SECURITY PROFILE — FUNDAMENTALS, DESCRIPTION, HEADLINES"],
    ["VOL <TICKER>", "VOLATILITY MONITOR — REALIZED 21D/63D + GARCH(1,1) FORECAST"],
    ["IV <TICKER>", "IMPLIED VOL — SMILE / SKEW, TERM STRUCTURE, vs REALIZED & GARCH"],
    ["N <TICKER>", "NEWS HEADLINES — SECURITY + BROAD MARKET"],
    ["OV", "OPTION VALUATION — BLACK-SCHOLES PRICE & GREEK CURVES"],
    ["GBM", "GEOMETRIC BROWNIAN MOTION PATH SIMULATOR"],
    ["MC", "MONTE CARLO OPTION PRICER VS CLOSED FORM"],
    ["HB", "HISTORICAL DELTA-HEDGE BACKTEST — STATIC vs ROLLING vs GARCH VOL"],
    ["<TICKER>", "A BARE SYMBOL LOADS ITS CHART — E.G.  TSLA  OR  TCS.BO"],
    ["/", "KEYBOARD SHORTCUT — FOCUS THE COMMAND LINE"],
  ];
  main.innerHTML = panel("COMMAND REFERENCE",
    `<table class="q help-table"><tr><th style="text-align:left">COMMAND</th><th style="text-align:left">FUNCTION</th></tr>` +
    rows.map(([c, d2]) => `<tr><td>${c}</td><td>${d2}</td></tr>`).join("") + `</table>`) +
    `<div style="color:var(--faint);font-size:11px;letter-spacing:1px">
      INDIAN (BSE) SYMBOLS USE THE .BO SUFFIX — RELIANCE.BO, TCS.BO, HDFCBANK.BO …
      US SYMBOLS ARE PLAIN — AAPL, NVDA, MSFT. INDICES: ^IXIC, ^BSESN, ^NSEI, ^GSPC.</div>`;
}

/* ---------------- router ---------------- */

const PAGES = {
  MKT: pageMKT,
  NDQ: (t) => pageMarketFocus(t, "nasdaq", "QQQ"),
  BSE: (t) => pageMarketFocus(t, "bse", "RELIANCE.BO"),
  GP: pageGP,
  DES: pageDES,
  VOL: pageVOL,
  IV: pageIV,
  N: pageN,
  OV: pageOV,
  GBM: pageGBM,
  MC: pageMC,
  HB: pageHB,
  HELP: pageHELP,
};

async function render() {
  const token = ++state.renderToken;
  setStatus(`LOADING ${state.func}…`);
  try {
    await PAGES[state.func](token);
    if (token === state.renderToken) setStatus("READY");
  } catch (e) {
    if (token === state.renderToken) {
      main.innerHTML = errBox(e);
      setStatus("ERROR");
    }
  }
}

/* ---------------- boot ---------------- */
applyTheme();
nav("MKT");
