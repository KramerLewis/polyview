/* polyview: renders web/data/site.json. No dependencies. */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function money(v, digits) {
    if (v == null || Number.isNaN(v)) return "—";
    const a = Math.abs(v), sign = v < 0 ? "−" : "";
    if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(digits ?? (a >= 1e11 ? 1 : 2))}B`;
    if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(digits ?? (a >= 1e8 ? 0 : 1))}M`;
    if (a >= 1e3) return `${sign}$${Math.round(a / 1e3)}K`;
    return `${sign}$${Math.round(a)}`;
  }
  const pct = (v) => (v == null || !isFinite(v) ? "—" : `${(v * 100).toFixed(1)}%`);
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  // Spending above the final budget usually means nonappropriated or local
  // funds recorded against the agency (DECISIONS D-026), so say so plainly.
  const unspentLabel = (budget, actual) => {
    if (!budget) return "—";
    const u = 1 - actual / budget;
    return u < 0 ? `${pct(-u)} over budget` : `${pct(u)} unspent`;
  };

  /* ---------- tooltip ---------- */
  const tip = $("#tooltip");
  function bindTips(root) {
    root.querySelectorAll("[data-tip]").forEach((el) => {
      const show = (e) => {
        tip.innerHTML = el.dataset.tip;
        tip.hidden = false;
        const r = el.getBoundingClientRect();
        const x = e && e.clientX ? e.clientX : r.left + r.width / 2;
        const y = e && e.clientY ? e.clientY : r.top;
        const w = tip.offsetWidth, h = tip.offsetHeight;
        tip.style.left = `${Math.max(8, Math.min(window.innerWidth - w - 8, x + 12))}px`;
        tip.style.top = `${Math.max(8, y - h - 12)}px`;
      };
      el.addEventListener("mousemove", show);
      el.addEventListener("focus", () => show());
      el.addEventListener("mouseleave", () => (tip.hidden = true));
      el.addEventListener("blur", () => (tip.hidden = true));
    });
  }

  /* ---------- bar chart: current fill over budget track, optional original tick ---------- */
  function bars(el, rows, { legend, tableHeads } = {}) {
    const max = Math.max(...rows.map((r) => Math.max(r.track ?? 0, r.value, r.tick ?? 0)), 1);
    const w = (v) => `${Math.max(0, (v / max) * 100)}%`;
    let html = legend ? `<div class="legend">${legend}</div>` : "";
    html += rows.map((r) => `
      <div class="bar-row" tabindex="0" data-tip="${esc(r.tip)}">
        <div class="name">${esc(r.name)}</div>
        <div class="track" aria-hidden="true">
          ${r.track != null ? `<div class="budget" style="width:${w(r.track)}"></div>` : ""}
          <div class="fill" style="width:${w(r.value)}"></div>
          ${r.tick != null ? `<div class="tick" style="left:calc(${w(r.tick)} - 1px)"></div>` : ""}
        </div>
        <div class="val">${r.label}${r.sub ? `<small>${r.sub}</small>` : ""}</div>
      </div>`).join("");
    if (tableHeads) {
      html += `<details class="table-view"><summary>Show as table</summary>
        <div class="table-wrap"><table class="data"><thead><tr>${tableHeads.map((h, i) =>
          `<th class="${i ? "num" : ""}">${esc(h)}</th>`).join("")}</tr></thead><tbody>
        ${rows.map((r) => `<tr>${r.cells.map((c, i) => `<td class="${i ? "num" : ""}">${esc(c)}</td>`).join("")}</tr>`).join("")}
        </tbody></table></div></details>`;
    }
    el.innerHTML = html;
    bindTips(el);
  }

  /* ---------- sortable table ---------- */
  function table(el, cols, rows, { onClick, initialSort } = {}) {
    let sort = initialSort || { key: null, dir: -1 };
    function render() {
      const sorted = [...rows];
      if (sort.key) {
        const col = cols.find((c) => c.key === sort.key);
        const val = col.sortValue || ((r) => r[sort.key]);
        sorted.sort((a, b) => {
          const x = val(a), y = val(b);
          if (x == null && y == null) return 0;
          if (x == null) return 1;
          if (y == null) return -1;
          return (typeof x === "string" ? x.localeCompare(y) : x - y) * sort.dir;
        });
      }
      el.innerHTML = `<thead><tr>${cols.map((c) => `<th scope="col" data-key="${c.key}"
          class="${c.num ? "num" : ""}" ${sort.key === c.key ? `aria-sort="${sort.dir > 0 ? "ascending" : "descending"}"` : ""}
          tabindex="0">${esc(c.label)}</th>`).join("")}</tr></thead>
        <tbody>${sorted.map((r, i) => `<tr data-i="${rows.indexOf(r)}" ${onClick ? 'class="clickable" tabindex="0"' : ""}>
          ${cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.render ? c.render(r) : esc(r[c.key])}</td>`).join("")}</tr>`).join("")}
        </tbody>`;
      el.querySelectorAll("th").forEach((th) => {
        const go = () => {
          const k = th.dataset.key;
          sort = { key: k, dir: sort.key === k ? -sort.dir : (cols.find((c) => c.key === k).num ? -1 : 1) };
          render();
        };
        th.addEventListener("click", go);
        th.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), go()));
      });
      if (onClick) {
        el.querySelectorAll("tbody tr").forEach((tr) => {
          const go = () => {
            el.querySelectorAll("tbody tr").forEach((t) => t.removeAttribute("aria-selected"));
            tr.setAttribute("aria-selected", "true");
            onClick(rows[+tr.dataset.i]);
          };
          tr.addEventListener("click", go);
          tr.addEventListener("keydown", (e) => e.key === "Enter" && go());
        });
      }
    }
    render();
    return { update(newRows) { rows = newRows; render(); } };
  }

  /* ---------- views ---------- */
  function overview(d) {
    const b = d.budget;
    const total = b.by_budget.reduce((s, x) => s + x.current, 0);
    const orig = b.by_budget.reduce((s, x) => s + x.original, 0);
    const c = d.completed;
    $("#stats").innerHTML = `
      <div class="stat"><div class="label">2025-27 enacted, all three budgets</div>
        <div class="value">${money(total, 1)}</div>
        <div class="sub">${money(total - orig, 1)} added by 2026 supplementals</div></div>
      <div class="stat"><div class="label">Operating budget, NGF-O</div>
        <div class="value">${money(b.ngfo.current, 1)}</div>
        <div class="sub">General Fund–State and 3 related accounts, the figure the Legislature balances to</div></div>
      <div class="stat"><div class="label">Capital money carried forward</div>
        <div class="value">${money(b.by_budget.find((x) => x.budget === "capital").reappropriated, 1)}</div>
        <div class="sub">reappropriated from earlier bienniums</div></div>
      <div class="stat"><div class="label">2023-25: share of final budget spent</div>
        <div class="value">${pct(c.actual / c.final_budget)}</div>
        <div class="sub">${money(c.actual, 1)} of ${money(c.final_budget, 1)}</div></div>`;

    bars($("#by-budget"), b.by_budget.map((x) => ({
      name: cap(x.budget), value: x.current, tick: x.original, label: money(x.current),
      sub: `${x.current >= x.original ? "+" : ""}${money(x.current - x.original)} since 2025`,
      tip: `<b>${cap(x.budget)} budget</b><br>Current: ${money(x.current)}<br>Originally enacted: ${money(x.original)}`
        + (x.reappropriated ? `<br>Plus ${money(x.reappropriated)} reappropriated` : "")
        + `<br><span class="muted">${esc(x.bills.join(" · "))}</span>`,
      cells: [cap(x.budget), money(x.original), money(x.current), money(x.reappropriated)],
    })), {
      legend: `<span><span class="key" style="background:var(--accent)"></span>Current</span>
               <span><span class="key" style="background:var(--tick);width:3px"></span>Originally enacted (2025)</span>`,
      tableHeads: ["Budget", "Original", "Current", "Reappropriated"],
    });

    bars($("#by-source"), b.by_fund_source.filter((x) => x.current > 0).map((x) => ({
      name: x.source, value: x.current, label: money(x.current), sub: pct(x.current / total),
      tip: `<b>${esc(x.source)}</b><br>${money(x.current)} (${pct(x.current / total)} of total)`,
      cells: [x.source, money(x.original), money(x.current)],
    })), { tableHeads: ["Fund source", "Original", "Current"] });

    $("#completed-note").textContent = `The ${c.biennium} biennium (July 2023 – June 2025). Final budget vs. actual spending on appropriated lines for all three budgets, budgetary basis. Another ${money(c.other_actual, 1)} was recorded without an appropriation line (mostly bond debt service paid under statutory authority) and is not included. Source: ${c.source}.`;
    const top = [...d.agencies].filter((a) => a.budget_2325 > 0)
      .sort((x, y) => y.budget_2325 - x.budget_2325).slice(0, 12);
    bars($("#completed"), top.map((a) => ({
      name: a.name, track: a.budget_2325, value: Math.max(0, a.actual_2325), label: money(a.actual_2325),
      sub: `of ${money(a.budget_2325)} · ${unspentLabel(a.budget_2325, a.actual_2325)}`,
      tip: `<b>${esc(a.name)}</b><br>Final budget: ${money(a.budget_2325)}<br>Actual: ${money(a.actual_2325)}<br>Unspent: ${money(a.budget_2325 - a.actual_2325)}`,
      cells: [a.name, money(a.budget_2325), money(a.actual_2325), unspentLabel(a.budget_2325, a.actual_2325)],
    })), {
      legend: `<span><span class="key" style="background:var(--track)"></span>Final budget</span>
               <span><span class="key" style="background:var(--accent)"></span>Actually spent</span>`,
      tableHeads: ["Agency (12 largest)", "Final budget", "Actual", "Unspent"],
    });

    const hist = (key, el, label) => {
      const latest = d.history[d.history.length - 1], prev = d.history[d.history.length - 2];
      const prevBy = Object.fromEntries((prev ? prev[key] : []).map((x) => [x.line, x]));
      bars(el, latest[key].filter((x) => x.actual > 0).map((x) => ({
        name: x.line, value: x.actual, label: money(x.actual),
        sub: prevBy[x.line] ? `${prev.biennium}: ${money(prevBy[x.line].actual)}` : "",
        tip: `<b>${esc(x.line)}</b><br>${latest.biennium} actual: ${money(x.actual)}<br>${latest.biennium} budget: ${money(x.final)}`
          + (prevBy[x.line] ? `<br>${prev.biennium} actual: ${money(prevBy[x.line].actual)}` : ""),
        cells: [x.line, prevBy[x.line] ? money(prevBy[x.line].actual) : "—", money(x.actual), money(x.final)],
      })), {
        legend: `<span><span class="key" style="background:var(--accent)"></span>${latest.biennium} actual (${label})</span>`,
        tableHeads: ["Source", `${prev ? prev.biennium : ""} actual`, `${latest.biennium} actual`, `${latest.biennium} budget`],
      });
    };
    hist("revenue", $("#revenue"), "revenue");
    hist("spending", $("#spending"), "spending");
  }

  function outlook(d) {
    const o = d.outlook;
    if (!o) return;
    const [b1, b2] = o.bienniums;
    $("#outlook-note").innerHTML = `Near General Fund-Outlook (NGF-O) accounts only: the General Fund and three related
      accounts that the Legislature must balance over four years. ${esc(b2)} figures are an <strong>official projection</strong>,
      not actual results. Source: <a href="${esc(o.url)}">ERFC, ${esc(o.label)}</a>.`;
    const row = (label) => o.rows.find((r) => r.label === label && !r.is_detail);
    const end = row("NGF-O Projected Ending Balance");
    const y0 = +b1.slice(0, 4);
    const years = [y0 + 1, y0 + 2, y0 + 3, y0 + 4];
    const negatives = ["fy1", "fy2", "fy3", "fy4"].map((k, i) => [years[i], end[k]]).filter(([, v]) => v < 0);
    $("#outlook-callout").innerHTML = negatives.length ? `<div class="callout"><strong>Projected shortfall:</strong>
      the outlook projects a negative NGF-O balance of ${negatives.map(([y, v]) => `${money(v * 1e6)} at the end of
      fiscal year ${y}`).join(" and ")}. Rainy-day fund reserves are counted separately in the last rows.</div>` : "";
    const shown = ["NGF-O Beginning Balance", "Forecasted Revenues", "Other Resource Changes", "Total Revenues and Resources",
      "Enacted Appropriations", "Maintenance Level Total", "Policy Level Total", "Reversions", "Revised Appropriations",
      "NGF-O Projected Ending Balance", "BSA Ending Balance", "Total Reserves"];
    const names = { "NGF-O Beginning Balance": "Beginning balance", "Forecasted Revenues": "Forecast revenue",
      "Other Resource Changes": "Transfers and other resource changes", "Total Revenues and Resources": "Total available",
      "Enacted Appropriations": "Appropriations enacted in 2025", "Maintenance Level Total": "Changes to keep current services",
      "Policy Level Total": "New policy changes", "Reversions": "Assumed unspent (reversions)",
      "Revised Appropriations": "Total spending", "NGF-O Projected Ending Balance": "Ending balance",
      "BSA Ending Balance": "Rainy-day fund (BSA) balance", "Total Reserves": "Total reserves" };
    const bold = new Set(["Total Revenues and Resources", "Revised Appropriations", "NGF-O Projected Ending Balance", "Total Reserves"]);
    const fmt = (v) => v == null ? "—" : `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}M`;
    const cols = [["fy1", `FY ${years[0]}`], ["fy2", `FY ${years[1]}`], ["biennium1", b1], ["fy3", `FY ${years[2]}`],
      ["fy4", `FY ${years[3]}`], ["biennium2", `${b2} (projected)`]];
    $("#outlook-table").innerHTML = `<thead><tr><th>NGF-O, $ millions</th>${cols.map(([, h]) => `<th class="num">${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>${shown.map((l) => { const r = row(l); if (!r) return "";
        return `<tr${bold.has(l) ? ' style="font-weight:600"' : ""}><td>${esc(names[l] || l)}</td>${cols.map(([k]) =>
          `<td class="num">${fmt(r[k])}</td>`).join("")}</tr>`; }).join("")}</tbody>`;
  }

  function moneyFlow(d) {
    const flows = d.history.filter((h) => h.flow).map((h) => h.flow);
    if (!flows.length) return;
    const pick = $("#flow-pick");
    pick.innerHTML = flows.map((f, i) => `<option value="${i}">${esc(f.biennium)}</option>`).join("");
    pick.value = String(flows.length - 1);
    const draw = () => {
      const f = flows[+pick.value];
      $("#flow-note").innerHTML = `Actual revenue and spending for the ${esc(f.biennium)} biennium, all funds, budgetary basis
        (${esc(f.source)}). Colors follow each revenue source only as far as the fund it was deposited in: money mixes inside a
        fund, so it can't be traced to a particular program. Transfers between funds are netted out. The gray nodes show where
        spending used bond proceeds, transfers in or fund balances (${money(f.draw, 1)}), and where revenue was added to balances
        or transferred out (${money(f.surplus, 1)}).`;
      const el = $("#flow");
      if (el.clientWidth < 640) {
        // Phones: the same three columns as bar lists.
        const titles = ["Where it came from", "Which funds it went into", "What it paid for"];
        el.innerHTML = f.columns.map((c, i) => `<div class="flow-col"><h3>${titles[i]}</h3><div id="flow-col-${i}"></div></div>`).join("");
        f.columns.forEach((c, i) => {
          const tot = (n) => Math.max(...[f.links.filter((l) => l.from === n), f.links.filter((l) => l.to === n)]
            .map((ls) => ls.reduce((a, l) => a + l.value, 0)));
          bars($(`#flow-col-${i}`), c.map((n) => ({ name: n, value: tot(n), label: money(tot(n)),
            tip: `<b>${esc(n)}</b><br>${money(tot(n))}` })));
        });
      } else {
        window.renderSankey(el, f, { money, esc, bindTips });
      }
      $("#flow-table").innerHTML = `<thead><tr><th>From</th><th>To</th><th class="num">Amount</th></tr></thead><tbody>
        ${f.links.map((l) => `<tr><td>${esc(l.from)}</td><td>${esc(l.to)}</td><td class="num">${money(l.value)}</td></tr>`).join("")}</tbody>`;
    };
    pick.addEventListener("change", draw);
    let t;
    window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(draw, 150); });
    // Draw once the overview is visible, so the chart can measure its width.
    const whenVisible = () => { if (!$("#overview").hidden) { draw(); window.removeEventListener("hashchange", whenVisible); } };
    window.addEventListener("hashchange", whenVisible);
    requestAnimationFrame(whenVisible);
  }

  function collectionsView(d) {
    const c = d.collections;
    if (!c) return;
    const TOTAL = "Total General Fund-State";
    const val = {};
    c.values.forEach((v) => { (val[v.line] = val[v.line] || {})[v.period] = v.amount; });
    const months = Object.keys(val[TOTAL]).sort();
    const shift = (p, k) => { let [y, m] = p.split("-").map(Number); m += k; while (m > 12) { m -= 12; y++; } while (m < 1) { m += 12; y--; } return `${y}-${String(m).padStart(2, "0")}`; };
    const last = months[months.length - 1];
    const bStart = d.budget.biennium.slice(0, 4) + "-07";  // biennium starts in July
    const btd = months.filter((p) => p >= bStart);
    const prior = btd.map((p) => shift(p, -24));
    const sum = (line, ps) => ps.reduce((a, p) => a + (val[line] && val[line][p] != null ? val[line][p] : NaN), 0);
    const cur = sum(TOTAL, btd), prev = sum(TOTAL, prior);
    const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const periodLabel = (p) => { const [y, m] = p.split("-").map(Number); const n = shift(p, 1).split("-").map(Number);
      return `${MON[m - 1]} 11 – ${MON[n[1] - 1]} 10, ${n[0]}`; };
    const v = c.variance.find((x) => x.scope === "latest period" && x.line.startsWith("Total General Fund"));
    $("#coll-note").innerHTML = `General Fund–State tax collections reported by the Department of Revenue and the courts,
      by monthly collection period (each period mostly reflects the previous month's business activity). Source:
      <a href="${esc(c.source_url)}">${esc(c.source)}</a>. Growth partly reflects tax increases enacted in 2025,
      not only a growing economy. This is the General Fund only; the four-year outlook below uses a broader set of accounts.`;
    $("#coll-stats").innerHTML = `
      <div class="stat"><div class="label">Collected so far in ${esc(d.budget.biennium)}</div>
        <div class="value">${money(cur, 1)}</div>
        <div class="sub">${btd.length} monthly periods through ${periodLabel(last)}</div></div>
      <div class="stat"><div class="label">Same point in the last biennium</div>
        <div class="value">${isNaN(prev) ? "—" : `${cur >= prev ? "+" : "−"}${(Math.abs(cur / prev - 1) * 100).toFixed(1)}%`}</div>
        <div class="sub">${isNaN(prev) ? "" : `${money(prev, 1)} after the same ${btd.length} periods`}</div></div>
      ${v ? `<div class="stat"><div class="label">Latest month vs. ERFC's forecast</div>
        <div class="value">${v.actual >= v.estimate ? "+" : "−"}${money(Math.abs(v.actual - v.estimate))}</div>
        <div class="sub">${((v.actual / v.estimate - 1) * 100).toFixed(1)}% (${esc(v.period_text)})</div></div>` : ""}`;
    bars($("#coll-chart"), btd.slice().reverse().map((p) => {
      const a = val[TOTAL][p], b = val[TOTAL][shift(p, -24)];
      return { name: periodLabel(p), value: a, label: money(a), sub: b ? `2 years earlier: ${money(b)}` : "",
        tip: `<b>${periodLabel(p)}</b><br>Collected: ${money(a)}` + (b ? `<br>Same period 2 years earlier: ${money(b)}` : ""),
        cells: [periodLabel(p), money(a), b ? money(b) : "—"] };
    }), { tableHeads: ["Collection period", "Collected", "Two years earlier"] });
    const l12 = Array.from({ length: 12 }, (_, i) => shift(last, -i));
    const p12 = l12.map((p) => shift(p, -12));
    const lines = Object.keys(val).filter((l) => !["Department of Revenue-Total", "Revenue Act", "Non-Revenue Act", TOTAL].includes(l));
    const tableRows = lines.map((l) => ({ l, a: sum(l, l12), b: sum(l, p12) })).filter((r) => !isNaN(r.a))
      .sort((x, y) => y.a - x.a);
    tableRows.push({ l: TOTAL, a: sum(TOTAL, l12), b: sum(TOTAL, p12), total: true });
    $("#coll-table").innerHTML = `<thead><tr><th>Tax</th><th class="num">Last 12 months</th><th class="num">Prior 12 months</th>
      <th class="num">Change</th></tr></thead><tbody>${tableRows.map((r) => `<tr${r.total ? ' style="font-weight:600"' : ""}>
      <td>${esc(r.l === TOTAL ? "Total, General Fund–State" : r.l)}</td><td class="num">${money(r.a)}</td><td class="num">${isNaN(r.b) ? "—" : money(r.b)}</td>
      <td class="num">${isNaN(r.b) || !r.b ? "—" : `${r.a >= r.b ? "+" : "−"}${(Math.abs(r.a / r.b - 1) * 100).toFixed(1)}%`}</td></tr>`).join("")}</tbody>`;
  }

  function vintages(d) {
    const v = (d.outlook && d.outlook.vintages) || [];
    const bienniums = [...new Set(v.map((x) => x.biennium))].sort();
    const outlooks = [...new Set(v.map((x) => x.outlook))];
    const cell = (o, b) => { const x = v.find((y) => y.outlook === o && y.biennium === b); return x; };
    const fmt = (n) => n == null ? "—" : `${n < 0 ? "−" : ""}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}M`;
    $("#vintage-table").innerHTML = `<thead><tr><th>Outlook adopted for</th>${bienniums.map((b) =>
      `<th class="num">${esc(b)} ending balance</th>`).join("")}</tr></thead><tbody>${outlooks.map((o) => `<tr>
      <td><a href="${esc(v.find((x) => x.outlook === o).url)}">${esc(o)}</a></td>${bienniums.map((b) => {
        const x = cell(o, b); return `<td class="num">${x ? fmt(x.ending_balance) : '<span class="muted">—</span>'}</td>`;
      }).join("")}</tr>`).join("")}</tbody>`;
  }

  function agencies(d) {
    const rows = d.agencies.map((a) => ({
      ...a,
      change: a.orig_2527 ? (a.curr_2527 - a.orig_2527) : null,
      unspent: a.budget_2325 > 0 ? 1 - a.actual_2325 / a.budget_2325 : null,
    }));
    const cols = [
      { key: "name", label: "Agency" },
      { key: "curr_2527", label: "2025-27 current", num: true, render: (r) => money(r.curr_2527 || null) },
      { key: "change", label: "Change since 2025", num: true,
        render: (r) => r.change == null ? "—" : `${r.change > 0 ? "+" : ""}${money(r.change)}` },
      { key: "budget_2325", label: "2023-25 budget", num: true, render: (r) => money(r.budget_2325) },
      { key: "actual_2325", label: "2023-25 spent", num: true, render: (r) => money(r.actual_2325) },
      { key: "unspent", label: "Unspent", num: true,
        render: (r) => r.unspent == null ? "—" : unspentLabel(r.budget_2325, r.actual_2325) },
    ];
    const t = table($("#agency-table"), cols, rows, {
      initialSort: { key: "curr_2527", dir: -1 }, onClick: (a) => agencyDetail(a),
    });
    $("#agency-search").addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      t.update(rows.filter((r) => !q || r.name.toLowerCase().includes(q)
        || r.programs.some((p) => p.toLowerCase().includes(q))));
    });
  }

  function agencyDetail(a) {
    const el = $("#agency-detail");
    const budgets = Object.entries(a.by_budget_2527 || {});
    el.innerHTML = `<h2>${esc(a.name)}</h2>
      <p class="note">Agency code ${esc(a.code)}.</p>
      <h3>2025-27 appropriations by budget</h3>
      ${budgets.length ? `<ul>${budgets.map(([k, v]) => `<li>${cap(k)}: <b>${money(v)}</b></li>`).join("")}</ul>`
        : `<p class="muted">No 2025-27 appropriations found for this agency code.</p>`}
      ${a.gfs_curr_2527 ? `<p>Of which General Fund–State: <b>${money(a.gfs_curr_2527)}</b></p>` : ""}
      ${a.reapprop_2527 ? `<p>Capital money reappropriated from earlier bienniums: <b>${money(a.reapprop_2527)}</b></p>` : ""}
      ${a.programs.length ? `<h3>Programs named in the operating budget</h3><p>${a.programs.map(esc).join(" · ")}</p>` : ""}
      ${a.enacted_2325 ? `<h3>2023-25: enacted in the budget bills</h3>
        <p>${money(a.enacted_2325)} in new appropriations across the operating, transportation and capital budgets,
        after the 2024 and 2025 supplementals. <span class="muted">OFM's final budget authority below can differ:
        it includes capital money carried over from earlier bienniums and adjustments made after enactment.</span></p>` : ""}
      ${a.budget_2325 ? `<h3>2023-25: budgeted vs. spent</h3>
        <p>Final budget ${money(a.budget_2325)}, actual ${money(a.actual_2325)},
        difference ${money(a.budget_2325 - a.actual_2325)} (${unspentLabel(a.budget_2325, a.actual_2325)}).
        <span class="muted">Appropriated lines only.</span></p>
        ${a.actual_2325 > a.budget_2325 ? `<p class="note">Spending on appropriated lines exceeded the final budget.
        This is unusual and is listed for follow-up in DECISIONS D-026.</p>` : ""}` : ""}
      ${a.other_actual_2325 ? `<p class="note">Also in 2023-25: ${money(a.other_actual_2325)} recorded against this agency
        with no appropriation line in OFM's report (for example, bond debt service paid under statutory
        authority). It's shown separately because there is no budget to compare it with.</p>` : ""}
      ${a.paid_2527 ? `<h3>2025-27 payments to vendors and grantees so far</h3>
        <p>${money(a.paid_2527)}. <span class="muted">From the state's Open Checkbook. This excludes salaries and benefits
        and some payments to local governments, so it is <b>not</b> a measure of how much of the budget has been spent.</span></p>` : ""}
      ${a.projects.length ? `<h3>Capital projects (${a.projects.length})</h3>
        <div class="table-wrap"><table class="data"><thead><tr><th>Project</th><th class="num">New 2025-27</th>
        <th class="num">Reappropriated</th></tr></thead><tbody>
        ${a.projects.slice(0, 40).map((p) => `<tr><td>${esc(p.name)} <span class="muted">${esc(p.project)}</span></td>
          <td class="num">${money(p.new)}</td><td class="num">${money(p.reapprop)}</td></tr>`).join("")}
        </tbody></table></div>${a.projects.length > 40 ? `<p class="note">Showing the 40 largest.</p>` : ""}` : ""}`;
    el.hidden = false;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function districtsView(d) {
    const pick = $("#district-pick");
    for (let i = 1; i <= 49; i++) pick.insertAdjacentHTML("beforeend", `<option value="${i}">District ${i}</option>`);
    const byD = Object.fromEntries(d.districts.map((x) => [x.district, x]));
    const rc = Object.fromEntries(d.roll_calls.map((r) => [r.id, r]));
    const posLabel = { yea: "Yes", nay: "No", absent: "Absent", excused: "Excused" };
    const finalVote = (m, bill) => {
      const v = m.votes.find(([id]) => rc[id].bill === bill && rc[id].type === "final_passage");
      return v ? posLabel[v[1]] : "—";
    };
    const note = `Capital projects listed for each district in LEAP's ${esc(d.capital_version)} project list (the 2025 budget as
      revised by the 2026 supplemental). Amounts marked "multi-location"
      fund a project spanning several places and aren't specific to one district, so they're excluded from district totals.
      Large totals usually reflect where state facilities are (District 43 includes the University of Washington), so
      differences between districts aren't by themselves evidence of favoritism. LEAP's 2025 and 2026 lists flag 12 projects
      ($359M) differently as multi-location (for example, Western State Hospital's new forensic hospital in District 28);
      these are marked, and totals follow the current list.`;
    $("#district-chart-note").innerHTML = note;

    function projectTable(list) {
      return `<div class="table-wrap"><table class="data"><thead><tr><th>Project</th><th>Agency / program</th>
        <th class="num">2025-27</th></tr></thead><tbody>
        ${list.map((p) => `<tr><td>${esc(p.project)}${p.number ? ` <span class="muted">${esc(p.number)}</span>` : ""}
          ${p.multi_location ? ' <span class="muted">· multi-location</span>' : ""}
          ${p.flag_changed ? ` <span class="muted">· LEAP's 2025 list ${p.multi_location ? "did not mark this" : "marked this"} as multi-location</span>` : ""}
          ${p.preliminary ? ' <span class="muted">· preliminary</span>' : ""}${p.alt_financing ? ' <span class="muted">· alternative financing</span>' : ""}</td>
          <td>${esc(p.agency)}${p.program ? `<br><span class="muted">${esc(p.program)}</span>` : ""}</td>
          <td class="num">${money(p.amount)}</td></tr>`).join("") || '<tr><td colspan="3" class="muted">No projects listed.</td></tr>'}
        </tbody></table></div>`;
    }

    function show(n) {
      const x = byD[n] || { projects: [], local_total: 0, multi_total: 0 };
      const members = d.legislators.filter((m) => m.district === +n && m.votes.length);
      const proj = x.projects;
      $("#district-detail").innerHTML = `
        <div class="stats">
          <div class="stat"><div class="label">Location-specific capital projects</div>
            <div class="value">${money(x.local_total, 1)}</div>
            <div class="sub">${proj.filter((p) => !p.multi_location).length} projects in District ${n}, 2025-27</div></div>
          <div class="stat"><div class="label">Rank among 49 districts</div>
            <div class="value">${1 + d.districts.filter((o) => o.local_total > x.local_total).length}</div>
            <div class="sub">by location-specific capital dollars</div></div>
        </div>
        <h2>Legislators and their budget votes</h2>
        <div class="table-wrap"><table class="data"><thead><tr><th>Name</th><th>Chamber</th><th>Party</th>
          <th>2025-27 budget</th><th>2026 supplemental</th></tr></thead><tbody>
          ${members.map((m) => `<tr><td>${esc(m.name)}</td><td>${esc(m.chamber)}</td><td>${esc(m.party)}</td>
            <td>${finalVote(m, "ESSB 5167")}</td><td>${finalVote(m, "ESSB 5998")}</td></tr>`).join("")}
        </tbody></table></div>
        <p class="note">Final-passage votes on the operating budget. See the Legislators page for amendment votes.</p>
        <h2>Capital projects in District ${n}</h2>
        <p class="note">Current amounts, after the 2026 supplemental. Grant programs appear as one line per program;
          the individual local projects funded in 2025 are listed below.
          ${x.detail_local_total ? `Location-specific total as originally enacted in 2025: ${money(x.detail_local_total, 1)}.` : ""}</p>
        ${projectTable(proj)}
        ${x.detail.length ? `<details class="table-view"><summary>Project-by-project detail as enacted in 2025
          (${x.detail.length} projects)</summary>${projectTable(x.detail)}</details>` : ""}`;
      bindTips($("#district-detail"));
      try { localStorage.setItem("polyview-district", n); } catch (e) { /* storage unavailable */ }
    }
    let start = "1";
    try { start = localStorage.getItem("polyview-district") || "1"; } catch (e) { /* ignore */ }
    pick.value = start;
    pick.addEventListener("change", () => show(pick.value));
    show(start);

    const sorted = [...d.districts].sort((a, b) => b.local_total - a.local_total);
    bars($("#district-chart"), sorted.map((x) => ({
      name: `District ${x.district}`, value: x.local_total, label: money(x.local_total),
      tip: `<b>District ${x.district}</b><br>Location-specific: ${money(x.local_total)}<br>Multi-location (excluded): ${money(x.multi_total)}`,
      cells: [`District ${x.district}`, money(x.local_total), money(x.multi_total)],
    })), { tableHeads: ["District", "Location-specific", "Multi-location (excluded)"] });
  }

  function legislators(d) {
    const rc = Object.fromEntries(d.roll_calls.map((r) => [r.id, r]));
    const finalVote = (m, bill) => {
      const v = m.votes.find(([id]) => rc[id].bill === bill && rc[id].type === "final_passage");
      return v ? v[1] : null;
    };
    const posLabel = { yea: "Yes", nay: "No", absent: "Absent", excused: "Excused" };
    const rows = d.legislators.map((m) => ({
      ...m,
      v5167: finalVote(m, "ESSB 5167"),
      v5998: finalVote(m, "ESSB 5998"),
      amendments: m.votes.filter(([id]) => rc[id].type === "amendment").length,
    }));
    const cols = [
      { key: "district", label: "District", num: true, render: (r) => r.district ?? "—" },
      { key: "name", label: "Name" },
      { key: "chamber", label: "Chamber" },
      { key: "party", label: "Party" },
      { key: "v5167", label: "2025-27 budget", render: (r) => posLabel[r.v5167] || '<span class="muted">—</span>' },
      { key: "v5998", label: "2026 supplemental", render: (r) => posLabel[r.v5998] || '<span class="muted">—</span>' },
      { key: "amendments", label: "Amendment votes", num: true },
    ];
    const t = table($("#member-table"), cols, rows, { initialSort: { key: "district", dir: 1 } });
    const sel = $("#district-filter");
    for (let i = 1; i <= 49; i++) sel.insertAdjacentHTML("beforeend", `<option value="${i}">${i}</option>`);
    const apply = () => {
      const dist = sel.value, q = $("#member-search").value.trim().toLowerCase();
      t.update(rows.filter((r) => (!dist || r.district === +dist) && (!q || r.name.toLowerCase().includes(q))));
    };
    sel.addEventListener("change", apply);
    $("#member-search").addEventListener("input", apply);

    const typeLabel = { final_passage: "Final passage", passage: "Chamber passage", amendment: "Amendment", procedural: "Procedural" };
    table($("#rollcall-table"), [
      { key: "date", label: "Date" },
      { key: "bill", label: "Bill" },
      { key: "chamber", label: "Chamber" },
      { key: "type", label: "Type", render: (r) => typeLabel[r.type] || r.type },
      { key: "motion", label: "Motion", render: (r) => esc(r.motion)
          + (r.sponsor ? ` <span class="muted">(sponsor: ${esc(r.sponsor)})</span>` : "")
          + (r.effect ? `<details><summary>What it would do</summary><p>${esc(r.effect)}</p>
              ${r.url ? `<a href="${esc(r.url)}">Amendment text</a>` : ""}</details>` : "") },
      { key: "yea", label: "Yes", num: true },
      { key: "nay", label: "No", num: true },
    ], d.roll_calls, { initialSort: { key: "date", dir: 1 } });

    const amdCols = [
      { key: "date", label: "Date", render: (r) => `<span class="pos">${esc(r.date)}</span>` },
      { key: "bill", label: "Bill", render: (r) => `<span class="pos">${esc(r.bill)}</span>` },
      { key: "chamber", label: "Chamber" },
      { key: "number", label: "No.", num: true, sortValue: (r) => +r.number },
      { key: "sponsor", label: "Sponsor" },
      { key: "result", label: "Result", render: (r) => esc(r.result) + (r.recorded_vote ? ' <span class="muted">· recorded</span>' : "") },
      { key: "effect", label: "Effect", render: (r) => r.effect
          ? `<details><summary>${esc(r.effect.slice(0, 90))}${r.effect.length > 90 ? "…" : ""}</summary>${r.effect.length > 90 ? `<p>${esc(r.effect)}</p>` : ""}
             ${r.fiscal_impact ? `<p class="muted">Fiscal impact: ${esc(r.fiscal_impact)}</p>` : ""}
             <a href="${esc(r.url)}">Amendment text</a></details>`
          : '<span class="muted">—</span>' },
    ];
    const amdTable = table($("#amendment-table"), amdCols, d.amendments, { initialSort: { key: "date", dir: 1 } });
    $("#amd-filter").addEventListener("change", (e) => {
      const v = e.target.value;
      amdTable.update(d.amendments.filter((a) => !v || a.result.toLowerCase().startsWith(v.toLowerCase())));
    });
  }

  // "Data as of" lines under each section (D-043).
  function stamps(d) {
    const f = d.freshness;
    if (!f) return;
    const place = { budget: "#stats", flow: "#flow-note", collections: "#coll-note", outlook: "#outlook-note",
      completed: "#completed-note", districts: "#district-chart-note" };
    const line = (k) => { const x = f.sections[k]; if (!x) return "";
      return `<p class="asof">Data as of: ${esc(x.as_of)}${x.fetched ? ` · fetched ${esc(x.fetched)}` : ""}</p>`; };
    Object.entries(place).forEach(([k, sel]) => {
      const el = $(sel);
      if (el) el.insertAdjacentHTML(k === "budget" ? "beforebegin" : "afterend", line(k));
    });
    const lv = $("#member-table");
    if (lv) lv.closest(".table-wrap").insertAdjacentHTML("beforebegin", line("votes"));
    const names = { budget: "Enacted budgets", completed: "Budgeted vs. spent", flow: "Money flow", collections: "Tax collections",
      outlook: "Four-year outlook", districts: "Capital projects by district", votes: "Votes and amendments" };
    $("#freshness").innerHTML = `<div class="table-wrap"><table class="data"><thead><tr><th>Section</th><th>Reflects</th>
      <th>Last fetched</th></tr></thead><tbody>${Object.entries(f.sections).map(([k, x]) =>
        `<tr><td>${esc(names[k] || k)}</td><td>${esc(x.as_of)}</td><td>${esc(x.fetched || "—")}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="note">New source files are checked for weekly${f.checked_at ? ` (last check ${esc(f.checked_at.slice(0, 10))})` : ""}.
      Monthly tax reports and budget outlooks are picked up automatically once they pass their arithmetic checks;
      new budget bills and reports with new layouts are flagged for a person to add.</p>
      ${f.attention.length ? `<div class="callout"><strong>Waiting to be added:</strong><ul>${f.attention.map((a) =>
        `<li>${esc(a.what)}</li>`).join("")}</ul></div>` : ""}`;
  }

  function dataView(d) {
    $("#built-at").textContent = `Built ${d.built_at.replace("T", " ")} UTC.`;
    table($("#source-table"), [
      { key: "source", label: "Dataset" },
      { key: "url", label: "File", render: (r) => `<a href="${esc(r.url)}">${esc(r.url.replace(/^https:\/\//, "").slice(0, 70))}</a>` },
      { key: "fetched_at", label: "Fetched", render: (r) => esc(r.fetched_at.slice(0, 10)) },
      { key: "sha256", label: "SHA-256 (prefix)", render: (r) => `<code>${esc(r.sha256)}</code>` },
    ], d.sources, { initialSort: { key: "source", dir: 1 } });
  }

  /* ---------- routing ---------- */
  function route() {
    const id = (location.hash || "#overview").slice(1);
    const known = ["overview", "agencies", "districts", "legislators", "data"];
    const view = known.includes(id) ? id : "overview";
    document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== view));
    document.querySelectorAll("nav a").forEach((a) =>
      a.setAttribute("aria-current", a.getAttribute("href") === `#${view}` ? "page" : "false"));
    tip.hidden = true;
  }

  fetch("data/site.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => {
      $("#loading").remove();
      overview(d); collectionsView(d); outlook(d); vintages(d); agencies(d); districtsView(d); legislators(d); dataView(d);
      window.addEventListener("hashchange", route);
      route();
      moneyFlow(d);
      stamps(d);
    })
    .catch((e) => { $("#loading").textContent = `Couldn't load the data (${e.message}).`; });
})();
