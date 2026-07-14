"use strict";

const form = document.getElementById("search-form");
const queryInput = document.getElementById("query");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");

const TREND = {
  up: { arrow: "↑", word: "Up", cls: "up" },
  down: { arrow: "↓", word: "Down", cls: "down" },
  flat: { arrow: "→", word: "Flat", cls: "flat" },
  unknown: { arrow: "–", word: "N/A", cls: "unknown" },
};

// Remembers the last candidate list so the detail view can offer "back to matches".
let lastPicker = null;

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = queryInput.value.trim();
  if (q) handleSearch(q);
});

async function handleSearch(q) {
  lastPicker = null; // a fresh search clears any previous picker context

  // A registration number is unambiguous — go straight to the detail view.
  if (/^\d+$/.test(q)) {
    return loadCharity(q);
  }

  showStatus("loading", "Searching for “" + q + "”…");
  resultEl.hidden = true;
  try {
    const resp = await fetch("/api/search?q=" + encodeURIComponent(q));
    const data = await resp.json();
    if (!resp.ok) {
      showStatus("error", data.error || "Something went wrong.");
      return;
    }
    if (data.count === 0) {
      showStatus("error", "No charities found matching “" + q + "”.");
      return;
    }
    if (data.count === 1) {
      // Only one match — no need to make the user pick.
      return loadCharity(data.results[0].reg_charity_number);
    }
    hideStatus();
    renderPicker(q, data.results, data.total);
  } catch (err) {
    showStatus("error", "Could not reach the server. Is it running?");
  }
}

async function loadCharity(regnoOrQuery) {
  showStatus("loading", "Loading charity…");
  resultEl.hidden = true;
  try {
    const resp = await fetch("/api/charity?q=" + encodeURIComponent(regnoOrQuery));
    const data = await resp.json();
    if (!resp.ok) {
      showStatus("error", data.error || "Something went wrong.");
      return;
    }
    hideStatus();
    render(data, String(regnoOrQuery));
  } catch (err) {
    showStatus("error", "Could not reach the server. Is it running?");
  }
}

function renderPicker(query, results, total) {
  lastPicker = { query, results, total };
  const truncated =
    total && total > results.length
      ? `<div class="hint">Showing the top ${results.length} of ${total} matches — add more words (e.g. “cancer research”) to narrow it down.</div>`
      : "";
  const items = results
    .map((r) => {
      const since = r.registered_year ? ` &middot; since ${escapeHtml(r.registered_year)}` : "";
      return `
        <li class="pick" data-regno="${r.reg_charity_number}">
          <span class="pick-name">${escapeHtml(r.charity_name)}</span>
          <span class="pick-meta">Reg. ${r.reg_charity_number} &middot; ${escapeHtml(r.reg_status)}${since}</span>
        </li>`;
    })
    .join("");
  resultEl.innerHTML = `
    <div class="card">
      <div class="section-title">Matches for “${escapeHtml(query)}” — pick one</div>
      ${truncated}
      <ul class="picker">${items}</ul>
    </div>`;
  resultEl.hidden = false;
  resultEl.querySelectorAll(".pick").forEach((el) => {
    el.addEventListener("click", () => loadCharity(el.dataset.regno));
  });
}

function render(d, q) {
  const hot = d.hot_prospect
    ? `<span class="hot-badge">🔥 Hot prospect (${fmtPct(d.hot_prospect_change)} income YoY)</span>`
    : "";

  const meta = [
    `Reg. no. ${d.reg_charity_number}`,
    d.reg_status,
    d.website ? `<a href="${escapeAttr(d.website)}" target="_blank" rel="noopener">Website</a>` : null,
  ].filter(Boolean).join(" &middot; ");

  resultEl.innerHTML = `
    ${backLink()}
    <div class="card">
      <div class="card-head">
        <div>
          <h2>${escapeHtml(d.charity_name)}</h2>
          <div class="meta">${meta}</div>
        </div>
        ${hot}
      </div>
      ${financialsTable(d)}
      ${barChart(d)}
      <div class="actions">
        <a href="/api/charity.csv?q=${encodeURIComponent(q)}">↓ Download CSV</a>
      </div>
    </div>
    <div class="card">
      <div class="section-title">Key people / trustees</div>
      ${trusteesList(d.trustees)}
    </div>
    ${activitiesCard(d.activities)}
  `;
  resultEl.hidden = false;

  const back = document.getElementById("back-link");
  if (back) {
    back.addEventListener("click", (e) => {
      e.preventDefault();
      renderPicker(lastPicker.query, lastPicker.results, lastPicker.total);
    });
  }
}

// Shown above the detail view only when we arrived here from a candidate list.
function backLink() {
  return lastPicker
    ? `<a class="back" id="back-link" href="#">← Back to matches</a>`
    : "";
}

function financialsTable(d) {
  const years = d.financials;
  if (!years || years.length === 0) {
    return `<p class="empty">No financial history published for this charity.</p>`;
  }
  const headCells = years.map((y) => `<th>${escapeHtml(y.label)}</th>`).join("");
  const incomeCells = years.map((y) => `<td>${money(y.income)}</td>`).join("");
  const expCells = years.map((y) => `<td>${money(y.expenditure)}</td>`).join("");

  return `
    <table>
      <thead>
        <tr><th>&nbsp;</th>${headCells}<th>Trend</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>Income</td>${incomeCells}<td>${trendCell(d.income_trend, d.income_change)}</td>
        </tr>
        <tr>
          <td>Expenditure</td>${expCells}<td>${trendCell(d.expenditure_trend, d.expenditure_change)}</td>
        </tr>
      </tbody>
    </table>`;
}

function barChart(d) {
  const years = (d.financials || []).filter(
    (y) => y.income != null || y.expenditure != null
  );
  if (years.length === 0) return "";

  const vals = [];
  years.forEach((y) => {
    if (y.income != null) vals.push(y.income);
    if (y.expenditure != null) vals.push(y.expenditure);
  });
  const maxVal = Math.max(...vals, 0);
  if (maxVal <= 0) return "";

  const W = 600, H = 320;
  const plotLeft = 30, plotRight = W - 20;
  const plotWidth = plotRight - plotLeft;
  const chartTop = 54, chartBottom = 268;
  const chartHeight = chartBottom - chartTop;
  const groupWidth = plotWidth / years.length;
  const barWidth = Math.min(46, groupWidth * 0.3);

  let bars = "";
  years.forEach((y, i) => {
    const cx = plotLeft + groupWidth * (i + 0.5);
    const pair = [
      { v: y.income, color: "var(--bar-income)", dx: -(barWidth / 2) - 3 },
      { v: y.expenditure, color: "var(--bar-exp)", dx: barWidth / 2 + 3 },
    ];
    pair.forEach((p) => {
      if (p.v == null) return;
      const h = (p.v / maxVal) * chartHeight;
      const x = cx + p.dx - barWidth / 2;
      const yTop = chartBottom - h;
      bars += `<rect x="${x.toFixed(1)}" y="${yTop.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${p.color}"><title>${escapeHtml(y.label)} — ${money(p.v)}</title></rect>`;
      bars += `<text class="bar-val" x="${(x + barWidth / 2).toFixed(1)}" y="${(yTop - 6).toFixed(1)}" text-anchor="middle">${moneyShort(p.v)}</text>`;
    });
    bars += `<text class="bar-year" x="${cx.toFixed(1)}" y="${(chartBottom + 20).toFixed(1)}" text-anchor="middle">${escapeHtml(y.label)}</text>`;
  });

  const baseline = `<line x1="${plotLeft}" y1="${chartBottom}" x2="${plotRight}" y2="${chartBottom}" stroke="var(--border)" />`;
  const legend = `
    <g transform="translate(${W / 2 - 55}, 24)">
      <rect x="0" y="-10" width="12" height="12" rx="2" fill="var(--bar-income)"></rect>
      <text class="legend" x="17" y="0">Income</text>
      <rect x="82" y="-10" width="12" height="12" rx="2" fill="var(--bar-exp)"></rect>
      <text class="legend" x="99" y="0">Expenditure</text>
    </g>`;

  return `
    <div class="chart">
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Income and expenditure by year">
        ${legend}
        ${baseline}
        ${bars}
      </svg>
    </div>`;
}

function trendCell(direction, change) {
  const t = TREND[direction] || TREND.unknown;
  const pct = change === null || change === undefined ? "" : ` ${fmtPct(change)}`;
  return `<span class="trend ${t.cls}">${t.arrow} ${t.word}${pct}</span>`;
}

function trusteesList(trustees) {
  if (!trustees || trustees.length === 0) {
    return `<p class="empty">Not published by the API for this charity.</p>`;
  }
  const items = trustees.map((t) => {
    const chair = t.is_chair ? `<span class="chair">Chair</span>` : "";
    const appointed = t.appointed ? `<span class="appointed">since ${escapeHtml(t.appointed)}</span>` : "";
    return `<li>${escapeHtml(t.name)}${chair}${appointed}</li>`;
  }).join("");
  return `<ul class="trustees">${items}</ul>`;
}

function activitiesCard(activities) {
  if (!activities || activities.length === 0) return "";
  const items = activities.map((a) => `<li>${escapeHtml(a)}</li>`).join("");
  return `
    <div class="card">
      <div class="section-title">What the charity does</div>
      <ul class="trustees">${items}</ul>
    </div>`;
}

// ---- helpers ----

function money(v) {
  if (v === null || v === undefined) return "–";
  return "£" + Math.round(v).toLocaleString("en-GB");
}

// Compact form for bar labels: £62.8m / £540k / £320.
function moneyShort(v) {
  if (v === null || v === undefined) return "";
  const a = Math.abs(v);
  if (a >= 1e6) return "£" + (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "m";
  if (a >= 1e3) return "£" + Math.round(v / 1e3) + "k";
  return "£" + Math.round(v);
}

function fmtPct(change) {
  if (change === null || change === undefined) return "";
  const pct = (change * 100).toFixed(1);
  return (change >= 0 ? "+" : "") + pct + "%";
}

function showStatus(kind, msg) {
  statusEl.className = "status " + kind;
  statusEl.textContent = msg;
  statusEl.hidden = false;
}
function hideStatus() { statusEl.hidden = true; }

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, "&quot;");
}
