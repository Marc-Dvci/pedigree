// The browser code gives the command line's answers: run web/js/pedigree.js on Relate's WebAssembly build (from npm)
// with the page's slice, and compare with web/test/parity.json, which tests/test_web_parity.py proves matches Python.
//   cd web && npm ci && node test/parity.mjs
import fs from "node:fs";
import { createRequire } from "node:module";
import { initSync, RelateDb } from "@relate/relate-wasm";
import { Graph, check } from "../js/pedigree.js";

const here = new URL(".", import.meta.url);
const require = createRequire(import.meta.url);
initSync({ module: fs.readFileSync(require.resolve("@relate/relate-wasm/relate_bg.wasm")) });

const graph = new Graph(new RelateDb());
graph.queries = JSON.parse(fs.readFileSync(new URL("../data/queries.json", here), "utf8"));
graph.runScript(fs.readFileSync(new URL("../data/slice.cypher", here), "utf8"));
const expected = JSON.parse(fs.readFileSync(new URL("parity.json", here), "utf8"));

let failures = 0;
for (const want of expected) {
  const r = check(graph, want.model);
  const got = r && {
    model: want.model,
    declared: r.declared,
    upstream_licences: r.upstream_licences,
    inherited: r.inherited.map((i) => [i.licence, i.kind, i.nearest.ancestor, i.nearest.chain]).sort(),
    differs: r.differs.map((d) => [d.licence, d.kind]).sort(),
    naming: r.naming.map((n) => [n.licence, n.prefix]).sort(),
  };
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    failures += 1;
    console.error(`${want.model}\n  js:     ${JSON.stringify(got)}\n  python: ${JSON.stringify(want)}`);
  }
}
console.log(`${expected.length - failures} of ${expected.length} models give the same pedigree in the browser code and the Python code`);
process.exit(failures ? 1 : 0);
