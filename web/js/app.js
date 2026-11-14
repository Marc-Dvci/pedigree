import { Graph, check, tree } from "./pedigree.js";

// Registry stamp colours by licence family. Red is kept for terms that differ.
const STAMP = [
  [/^llama/, "#1d4ed8"],
  [/^gemma/, "#0f766e"],
  [/^qwen/, "#6d28d9"],
  [/^(mrl|mnpl)$/, "#c2410c"],
  [/^deepseek/, "#3730a3"],
  [/openrail/, "#a16207"],
  [/^cc-by-nc/, "#9d174d"],
];
// Licences the Hub tags with their own id; the others are published under `other` with a name in the card.
const HUB_TAGGED = new Set(["llama3", "llama3.1", "llama3.2", "llama3.3", "gemma", "cc-by-nc-4.0", "creativeml-openrail-m"]);
const KIND = {
  attribution: "Attribution",
  naming: "Name",
  notice: "Copy and notice",
  use_policy: "Use policy",
  user_threshold: "User threshold",
  non_commercial: "Non-commercial",
  no_other_llm: "Other models",
};
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const colour = (lic) => (lic ? (STAMP.find(([re]) => re.test(lic)) || [null, "#4b5563"])[1] : "#9ca3af");
const state = { graph: null };

// --- the chart: the model on the left, ancestors branching right in brackets ----------------------------------------

function layout(root) {
  const nodes = [];
  let leaf = 0;
  const place = (n, depth) => {
    const kids = n.parents.map((p) => ({ ...place(p.node, depth + 1), relation: p.relation }));
    const y = kids.length ? (kids[0].y + kids[kids.length - 1].y) / 2 : leaf++;
    const item = { n, depth, y, kids };
    nodes.push(item);
    return item;
  };
  const top = place(root, 0);
  return { top, nodes, leaves: Math.max(leaf, 1) };
}

function stamp(x, y, lic) {
  const text = lic ? lic.toUpperCase() : "NO LICENCE TAG";
  const w = 10 + text.length * 7.2;
  const c = colour(lic);
  const dash = lic ? "" : ' stroke-dasharray="3 3"';
  return `<g class="stamp"><rect x="${x}" y="${y}" width="${w}" height="20" rx="3" fill="none" stroke="${c}" stroke-width="1.6"${dash}/>
    <text x="${x + w / 2}" y="${y + 14}" text-anchor="middle" fill="${c}">${esc(text)}</text></g>`;
}

function drawChart(root, differs) {
  const { nodes, leaves } = layout(root);
  const colW = 300;
  const rowH = 78;
  const maxDepth = Math.max(...nodes.map((n) => n.depth));
  const width = 30 + maxDepth * colW + 300;
  const height = 40 + leaves * rowH;
  const X = (d) => 16 + d * colW;
  const Y = (y) => 40 + y * rowH;
  const parts = [];
  for (const item of nodes) {
    const x = X(item.depth);
    const y = Y(item.y);
    if (item.kids.length) {
      const ys = item.kids.map((k) => Y(k.y));
      const bx = x + 234;
      parts.push(`<line x1="${x + 222}" y1="${y}" x2="${bx}" y2="${y}" class="rule"/>`);
      parts.push(`<line x1="${bx}" y1="${Math.min(y, ...ys)}" x2="${bx}" y2="${Math.max(y, ...ys)}" class="rule"/>`);
      for (const k of item.kids) {
        const kx = X(k.depth);
        parts.push(`<line x1="${bx}" y1="${Y(k.y)}" x2="${kx - 8}" y2="${Y(k.y)}" class="rule"/>`);
        parts.push(`<text x="${kx - 12}" y="${Y(k.y) - 6}" class="rel" text-anchor="end">${esc(k.relation)}</text>`);
      }
    }
    const [author, name] = item.n.id.includes("/") ? item.n.id.split("/", 2) : ["", item.n.id];
    const isRoot = item.depth === 0;
    const shown = name.length > 26 ? name.slice(0, 25) + "…" : name;
    parts.push(`<text x="${x}" y="${y - 18}" class="author">${esc(author)}</text>`);
    parts.push(`<text x="${x}" y="${y}" class="name${isRoot ? " root" : ""}"><title>${esc(item.n.id)}</title>${esc(shown)}</text>`);
    parts.push(stamp(x, y + 8, item.n.licence));
    if (isRoot && differs) parts.push(`<text x="${x}" y="${y + 46}" class="differs">declared terms differ from upstream terms</text>`);
    if (item.n.more) {
      parts.push(`<line x1="${x + 222}" y1="${y}" x2="${x + 240}" y2="${y}" class="rule"/>`);
      parts.push(`<text x="${x + 244}" y="${y + 4}" class="more">+${item.n.more}</text>`);
    }
  }
  const svg = $("#chart");
  svg.setAttribute("viewBox", `0 0 ${width} ${height + 24}`);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height + 24));
  svg.style.aspectRatio = `${width} / ${height + 24}`;
  svg.innerHTML = parts.join("");
}

// --- the terms ------------------------------------------------------------------------------------------------------

function drawTerms(r) {
  const groups = {};
  for (const item of r.inherited) (groups[item.licence] ||= []).push(item);
  const sections = Object.entries(groups).map(([lic, items]) => {
    const near = items[0].nearest;
    const same = lic === r.declared;
    const rows = items
      .map((i) => {
        const fail = r.naming.find((n) => n.licence === lic && i.kind === "naming");
        const differ = r.differs.some((d) => d.licence === lic && d.kind === i.kind);
        const note = fail ? `the name does not begin with “${esc(fail.prefix)}”` : differ ? "the declared licence words this differently, or not at all" : "";
        return `<li><span class="kind">${esc(KIND[i.kind] || i.kind)}</span> <span class="clause">§${esc(i.nearest.clause)}</span>
          <q>${esc(i.nearest.text)}</q>${note ? ` <span class="flag">${note}</span>` : ""}</li>`;
      })
      .join("");
    return `<section class="licence">
      <h3><span class="dot" style="background:${colour(lic)}"></span>${esc(lic)} <span class="from">from ${esc(near.ancestor)}${same ? "" : ' · <span class="flag">not the declared licence</span>'}</span></h3>
      <p class="path">${near.chain.map(esc).join(" → ")}</p>
      <ul>${rows}</ul>
      <p class="src"><a href="${esc(near.source)}">Licence text</a></p></section>`;
  });
  $("#terms").innerHTML = sections.length
    ? sections.join("")
    : "<p>No ancestor in this graph declares a licence with obligations.</p>";
}

function show(id) {
  const r = check(state.graph, id.trim());
  if (!r) {
    $("#verdict").innerHTML = `<p>${esc(id)} is not in this page's slice of the graph. The command line and the MCP server cover every model in the snapshot.</p>`;
    $("#chart").innerHTML = "";
    $("#terms").innerHTML = "";
    return;
  }
  const params = new URLSearchParams(location.search);
  params.set("model", r.model);
  history.replaceState(null, "", `${location.pathname}?${params}`);
  const differs = r.differs.length > 0;
  const kinds = [...new Set(r.differs.map((d) => KIND[d.kind] || d.kind))];
  $("#verdict").innerHTML = `<h2>${esc(r.model)}</h2>
    <p>Declares <b>${esc(r.declared_unresolved ? "a licence named in its card (Hub id other)" : r.declared || "no licence tag")}</b>. Inherits terms from ${r.upstream_licences.length ? r.upstream_licences.map((l) => `<b>${esc(l)}</b>`).join(", ") : "no licence with obligations"}.
    ${differs ? `<span class="flag">Upstream terms the declared licence does not carry: ${kinds.map(esc).join(", ")}.</span>` : ""}</p>`;
  drawChart(tree(state.graph, r.model), differs);
  drawTerms(r);
}

// --- the population -------------------------------------------------------------------------------------------------

async function drawStats() {
  const stats = await fetch("data/stats.json").then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (!stats) return;
  const rows = Object.entries(stats.licences)
    .filter(([, s]) => s.inheritors)
    .sort((a, b) => b[1].inheritors - a[1].inheritors)
    .map(([lic, s]) => {
      const total = s.inheritors;
      const head = `<h3><span class="dot" style="background:${colour(lic)}"></span>${esc(lic)}: ${total.toLocaleString()} models inherit its terms</h3>`;
      if (!HUB_TAGGED.has(lic)) {
        return `<div class="pop">${head}<p class="small">Published under the Hub's <code>other</code> licence id, with its name in the model card.</p></div>`;
      }
      const same = (s.declared || []).find((d) => d.declared === lic)?.models || 0;
      const none = (s.declared || []).find((d) => d.declared === "none")?.models || 0;
      const other = total - same - none;
      const seg = (n, c, label) => (n ? `<span style="width:${(100 * n) / total}%;background:${c}" title="${label}: ${n}"></span>` : "");
      const bars = seg(same, colour(lic), lic) + seg(other, "#b91c1c", "another licence") + seg(none, "#d1d5db", "none");
      const naming = s.naming ? `<p class="small">${s.naming.prefixed.toLocaleString()} of ${s.naming.trained.toLocaleString()} fine-tunes, adapters and merges begin with “${esc(s.naming.prefix)}”.</p>` : "";
      return `<div class="pop">${head}<div class="bar">${bars}</div>
        <p class="small">${same.toLocaleString()} declare ${esc(lic)}, ${other.toLocaleString()} declare another licence, ${none.toLocaleString()} declare none.</p>${naming}</div>`;
    });
  $("#stats").innerHTML = rows.join("");
}

async function start() {
  try {
    state.graph = await Graph.load();
  } catch (err) {
    $("#status").textContent = `Relate could not start in this browser: ${err.message}`;
    return;
  }
  const g = state.graph;
  const n = g.rows("MATCH (m:Model) RETURN count(m) AS n")[0].n;
  const snap = g.rows("MATCH (s:Snapshot) RETURN s.revision AS r, s.rows AS rows")[0] || {};
  $("#status").textContent = `Relate 1.0.1 running in this tab (WebAssembly): ${n.toLocaleString()} models loaded in ${g.loadMs} ms, from a snapshot of ${Number(snap.rows || 0).toLocaleString()} Hub model cards (revision ${String(snap.r || "").slice(0, 7)}).`;
  const ids = g.rows("MATCH (m:Model) WHERE m.downloads > 0 RETURN m.id AS id ORDER BY m.downloads DESC LIMIT 400").map((r) => r.id);
  $("#models").innerHTML = ids.map((i) => `<option value="${esc(i)}">`).join("");
  const examples = await fetch("data/examples.json").then((r) => (r.ok ? r.json() : [])).catch(() => []);
  $("#examples").innerHTML = examples.map((e) => `<button type="button">${esc(e)}</button>`).join("");
  $("#examples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => ((($("#model").value = b.textContent), show(b.textContent)))));
  $("#form").addEventListener("submit", (e) => (e.preventDefault(), show($("#model").value)));
  const first = new URLSearchParams(location.search).get("model") || examples[0] || ids[0];
  if (first) {
    $("#model").value = first;
    show(first);
  }
  drawStats();
  document.body.classList.add("ready");
}

start();
