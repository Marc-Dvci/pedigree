// A model's pedigree in the browser: the same Cypher and rules as pedigree/checks.py, on Relate's WebAssembly build.

export const RELATE_VERSION = "1.2.0";
const RELATE_URL = `https://cdn.jsdelivr.net/npm/@relate/relate-wasm@${RELATE_VERSION}/relate.js`;
const TRAINED = ["finetune", "adapter", "merge"];

export class Graph {
  constructor(db) {
    this.db = db;
  }

  static async load(dataUrl = "data/") {
    const started = performance.now();
    const [{ default: init, RelateDb }, script, queries] = await Promise.all([
      import(RELATE_URL),
      fetch(dataUrl + "slice.cypher").then((r) => r.text()),
      fetch(dataUrl + "queries.json").then((r) => r.json()),
    ]);
    await init();
    const graph = new Graph(new RelateDb());
    graph.queries = queries;
    graph.runScript(script);
    graph.loadMs = Math.round(performance.now() - started);
    return graph;
  }

  runScript(script) {
    for (const envelope of this.db.executeScript(script, null).map((e) => JSON.parse(e))) {
      if (envelope.error) throw new Error(envelope.error);
    }
  }

  rows(query, params = null) {
    const result = JSON.parse(this.db.execute(query, params ? JSON.stringify(params) : null));
    if (result.error) throw new Error(result.error);
    return result.rows;
  }
}

const HUB_URL = /^(?:https?:\/\/)?(?:www\.)?(?:huggingface\.co|hf\.co)\//i;

// The graph's id for a model id as a person types it: a Hub URL works, and the Hub ignores case in ids.
export function resolve(graph, text) {
  const id = text.trim().replace(HUB_URL, "").replace(/^\/+|\/+$/g, "");
  if (graph.rows("MATCH (m:Model {id: $id}) RETURN m.id AS id", { id }).length) return id;
  const found = graph.rows("MATCH (m:Model) WHERE toLower(m.id) = $id RETURN m.id AS id", { id: id.toLowerCase() });
  return found.length === 1 ? found[0].id : null;
}

export function model(graph, text) {
  const id = resolve(graph, text);
  if (id === null) return null;
  const found = graph.rows(
    "MATCH (m:Model {id: $id}) OPTIONAL MATCH (m)-[d:DERIVED_FROM]->(p:Model) " +
      "RETURN m.id AS id, m.name AS name, m.licence AS licence, m.downloads AS downloads, " +
      "collect({parent: p.id, relation: d.relation}) AS parents",
    { id },
  );
  const row = found[0];
  row.parents = row.parents.filter((p) => p.parent !== null);
  return row;
}

function prefixOf(text) {
  const m = /"([^"]+)" at the beginning/.exec(text);
  return m ? m[1] : null;
}

export function startsWith(name, prefix) {
  const norm = (s) => s.toLowerCase().replace(/[-_\s.]+/g, " ").trim();
  return norm(name).startsWith(norm(prefix));
}

export function check(graph, text) {
  const found = model(graph, text);
  if (!found) return null;
  const id = found.id;
  const upstream = graph.rows(graph.queries.inherited, { id });
  const declared = found.licence;
  // `other`: a licence named only in the card, possibly the upstream one; no difference is claimed.
  const unresolved = declared === "other";
  // An upstream term differs when the declared licence has no term of the same kind in the same words.
  const carried = new Set(graph.rows(graph.queries.own, { id }).map((o) => JSON.stringify([o.kind, o.text])));
  const differs = unresolved ? [] : upstream.filter((u) => !carried.has(JSON.stringify([u.kind, u.nearest.text])));
  const naming = [];
  const own = new Set(found.parents.map((p) => p.relation));
  if (TRAINED.some((r) => own.has(r))) {
    for (const u of upstream) {
      const prefix = u.kind === "naming" ? prefixOf(u.nearest.text) : null;
      if (prefix && !startsWith(found.name, prefix)) naming.push({ licence: u.licence, prefix, clause: u.nearest.clause });
    }
  }
  return {
    model: found.id,
    declared,
    declared_unresolved: unresolved,
    parents: found.parents,
    inherited: upstream,
    differs,
    naming,
    non_commercial: upstream.filter((u) => u.kind === "non_commercial"),
    upstream_licences: [...new Set(upstream.map((u) => u.licence))].sort(),
  };
}

// The ancestors as a tree for the chart: each node lists its parents, to a fixed depth.
// A node at the depth limit keeps the count of its own parents in `more`, so the chart can show the line goes on.
export function tree(graph, id, depth = 3) {
  const node = (mid, level, seen) => {
    const m = model(graph, mid);
    const out = { id: mid, licence: m ? m.licence : null, downloads: m ? m.downloads : 0, parents: [], more: 0 };
    if (m && level >= depth) out.more = m.parents.length;
    if (!m || level >= depth || seen.has(mid)) return out;
    const next = new Set(seen).add(mid);
    out.parents = m.parents.map((p) => ({ relation: p.relation, node: node(p.parent, level + 1, next) }));
    return out;
  };
  return node(id, 0, new Set());
}
