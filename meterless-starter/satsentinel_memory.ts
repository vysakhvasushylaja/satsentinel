// SatSentinel memory bridge: its OWN H-MEM state, one JSON line on stdout.
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadHMEM } from "./src/engine.ts";

const here = path.dirname(fileURLToPath(import.meta.url));

async function main(): Promise<void> {
  const [command, ...rest] = process.argv.slice(2);
  const arg = rest.join(" ");
  if (!command || !arg) throw new Error("usage: satsentinel_memory.ts remember|ask|audit <text|id>");
  const emit = console.log;
  console.log = (...a: unknown[]) => console.error(...a); // keep stdout clean
  const { HMEM, source } = await loadHMEM();
  const hmem = new HMEM({ persistDir: process.env.SATSENTINEL_MEMORY_DIR || path.join(here, ".satsentinel-memory") });
  let out: unknown;
  if (command === "remember") {
    const r = hmem.add({ content: arg, type: "general", source: "analyst" });
    out = { id: r.id, layer: r.layer, content: r.content };
  } else if (command === "ask") {
    const res = hmem.query(arg, { threshold: 0.1 });
    out = {
      engine_source: source,
      memories: res.memories.map((m: any) => ({
        id: m.memory.id, content: m.memory.content, relevance: m.relevance, layer: m.memory.layer,
      })),
    };
  } else if (command === "audit") {
    out = {
      id: arg,
      history: hmem.ledger.history(arg).map((e: any) => ({
        action: e.action, actor: e.actor, timestamp: new Date(e.timestamp).toISOString(),
      })),
    };
  } else {
    throw new Error("unknown command " + command);
  }
  emit(JSON.stringify(out));
}

main().catch((e) => { console.error(String(e)); process.exit(1); });
