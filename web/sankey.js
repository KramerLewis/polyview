/* Minimal three-column Sankey for polyview. No dependencies.
   renderSankey(el, flow, {money, esc, bindTips}) draws into el.
   flow = { columns: [[names], [names], [names]], links: [{from, to, value, stage}], balance_nodes: [..] } */
(() => {
  "use strict";
  const SOURCE_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

  window.renderSankey = function renderSankey(el, flow, { money, esc, bindTips }) {
    const W = Math.max(640, el.clientWidth || 960);
    const H = 560;
    const M = { top: 8, bottom: 8, left: 250, right: 235 };
    const NODE_W = 14, PAD = 14;
    const cols = flow.columns;
    const balance = new Set(flow.balance_nodes || []);
    const colorOf = {};
    cols[0].forEach((n, i) => { colorOf[n] = balance.has(n) ? "var(--neutral-flow)" : SOURCE_COLORS[i % 4]; });

    // Node values = max(in, out) so balance holds visually.
    const val = {};
    flow.links.forEach((l) => {
      val[l.from] = val[l.from] || { in: 0, out: 0 };
      val[l.to] = val[l.to] || { in: 0, out: 0 };
      val[l.from].out += l.value; val[l.to].in += l.value;
    });
    const size = (n) => Math.max(val[n].in, val[n].out);
    const k = Math.min(...cols.map((c) =>
      (H - M.top - M.bottom - PAD * (c.length - 1)) / c.reduce((s, n) => s + size(n), 0)));
    const x = [M.left, (M.left + W - M.right - NODE_W) / 2, W - M.right - NODE_W];

    const nodes = {};
    cols.forEach((c, ci) => {
      const total = c.reduce((s, n) => s + size(n), 0) * k + PAD * (c.length - 1);
      let y = M.top + (H - M.top - M.bottom - total) / 2;
      c.forEach((n) => {
        nodes[n] = { name: n, col: ci, x: x[ci], y, h: Math.max(1, size(n) * k), outY: y, inY: y };
        y += size(n) * k + PAD;
      });
    });
    const order = (n) => cols[nodes[n].col].indexOf(n);
    const links = [...flow.links].sort((a, b) => order(a.from) - order(b.from) || order(a.to) - order(b.to));
    // Allocate link positions: outgoing sorted by target order, incoming by source order.
    const outSorted = [...links].sort((a, b) => order(a.from) - order(b.from) || order(a.to) - order(b.to));
    outSorted.forEach((l) => { l.y0 = nodes[l.from].outY; nodes[l.from].outY += l.value * k; });
    const inSorted = [...links].sort((a, b) => order(a.to) - order(b.to) || order(a.from) - order(b.from));
    inSorted.forEach((l) => { l.y1 = nodes[l.to].inY; nodes[l.to].inY += l.value * k; });

    const band = (l) => {
      const x0 = nodes[l.from].x + NODE_W, x1 = nodes[l.to].x, h = l.value * k, xm = (x0 + x1) / 2;
      return `M${x0},${l.y0}C${xm},${l.y0} ${xm},${l.y1} ${x1},${l.y1}L${x1},${l.y1 + h}`
        + `C${xm},${l.y1 + h} ${xm},${l.y0 + h} ${x0},${l.y0 + h}Z`;
    };
    const total = cols[0].reduce((s, n) => s + size(n), 0);
    const pct = (v) => `${((v / total) * 100).toFixed(1)}%`;
    const tipLink = (l) => `<b>${esc(l.from)} → ${esc(l.to)}</b><br>${money(l.value)} (${pct(l.value)})`
      + (l.stage === 2 ? '<br><span class="muted">Money mixes inside a fund, so this can\'t be traced back to a specific source.</span>' : "");
    const tipNode = (n) => `<b>${esc(n)}</b><br>In: ${money(val[n].in)}<br>Out: ${money(val[n].out)}`;

    let svg = `<svg class="sankey" viewBox="0 0 ${W} ${H}" width="100%" role="img"
      aria-label="Money flow from revenue sources through funds to areas of government; see the table below for values">`;
    svg += links.map((l, i) => `<path class="link" data-i="${i}" data-from="${esc(l.from)}" data-to="${esc(l.to)}"
      d="${band(l)}" style="fill:${l.stage === 1 ? colorOf[l.from] : "var(--neutral-flow)"}"
      tabindex="0" data-tip="${esc(tipLink(l))}"></path>`).join("");
    svg += Object.values(nodes).map((n) => {
      const fill = n.col === 0 ? colorOf[n.name] : balance.has(n.name) ? "var(--neutral-flow)" : "var(--node)";
      const left = n.col === 0;
      const tx = left ? n.x - 8 : n.x + NODE_W + 8;
      const anchor = left ? "end" : "start";
      return `<g class="node" data-name="${esc(n.name)}" tabindex="0" data-tip="${esc(tipNode(n.name))}">
        <rect x="${n.x}" y="${n.y}" width="${NODE_W}" height="${n.h}" rx="2" style="fill:${fill}"
          ${balance.has(n.name) ? 'class="balance"' : ""}></rect>
        <text x="${tx}" y="${n.y + n.h / 2}" text-anchor="${anchor}" dominant-baseline="middle">
          <tspan class="nlabel">${esc(n.name)}</tspan><tspan class="nval" dx="6">${money(size(n.name))}</tspan></text></g>`;
    }).join("");
    svg += "</svg>";
    el.innerHTML = svg;

    // Hover: highlight a link, or every link touching a node.
    const paths = [...el.querySelectorAll("path.link")];
    const focus = (pred) => paths.forEach((p) => p.classList.toggle("dim", !pred(p)));
    const clear = () => paths.forEach((p) => p.classList.remove("dim"));
    paths.forEach((p) => {
      p.addEventListener("mouseenter", () => focus((q) => q === p));
      p.addEventListener("mouseleave", clear);
      p.addEventListener("focus", () => focus((q) => q === p));
      p.addEventListener("blur", clear);
    });
    el.querySelectorAll("g.node").forEach((g) => {
      const n = g.dataset.name;
      const hit = (q) => q.dataset.from === n || q.dataset.to === n;
      g.addEventListener("mouseenter", () => focus(hit));
      g.addEventListener("mouseleave", clear);
      g.addEventListener("focus", () => focus(hit));
      g.addEventListener("blur", clear);
    });
    bindTips(el);
  };
})();
