// Static dev server for the Wellness Beyond #LLJC site.
// Run with: bun run dev
//
// Defaults come from the mywheel hub registry for this spoke:
//   hostname (short url) = wbl.local   ·   primary port = 3150  (block 3150-3159)
// A Caddy reverse proxy on :80 maps http://wbl.local/ -> 127.0.0.1:3150.
// Override with HOST / PORT env vars.

const HOST = process.env.HOST ?? "wbl.local";
const PORT = Number(process.env.PORT ?? 3150);
const ROOT = import.meta.dir;

// --- Pre-flight: this port is dedicated to this spoke, so anything LISTENing on
// it is a stale dev server from a previous run. Find it via `ss` (which, unlike
// `lsof -i :PORT`, reports only the listening socket — not Caddy's proxied
// connection to the same port) and kill it so `bun run dev` always starts clean.
function listenerPids(port: number): number[] {
  try {
    const res = Bun.spawnSync(["ss", "-ltnpH", `sport = :${port}`]);
    const out = res.stdout?.toString() ?? "";
    const pids = new Set<number>();
    for (const m of out.matchAll(/pid=(\d+)/g)) {
      const pid = Number(m[1]);
      if (pid && pid !== process.pid) pids.add(pid);
    }
    return [...pids];
  } catch {
    return [];
  }
}

function freePort(port: number): void {
  const pids = listenerPids(port);
  if (pids.length === 0) return;
  console.warn(`  Port ${port} already in use by pid ${pids.join(", ")} — killing stale dev server.`);
  for (const pid of pids) {
    try { process.kill(pid, "SIGKILL"); } catch { /* already gone / not ours */ }
  }
  // Wait (briefly) for the socket to be released before we bind.
  const deadline = Date.now() + 2000;
  while (Date.now() < deadline && listenerPids(port).length > 0) Bun.sleepSync(50);
}

function handler(req: Request): Promise<Response> | Response {
  const url = new URL(req.url);
  let pathname = decodeURIComponent(url.pathname);

  if (pathname === "/") pathname = "/index.html";
  if (pathname.includes("..")) return new Response("Forbidden", { status: 403 });

  return (async () => {
    let file = Bun.file(ROOT + pathname);
    if (!(await file.exists()) && !pathname.includes(".")) {
      file = Bun.file(ROOT + pathname + ".html"); // pretty "/page" -> "/page.html"
    }
    if (await file.exists()) return new Response(file);
    return new Response("404 — Not Found", { status: 404, headers: { "Content-Type": "text/plain" } });
  })();
}

freePort(PORT);

let server;
try {
  server = Bun.serve({ hostname: HOST, port: PORT, fetch: handler });
} catch (err) {
  if (String(err).includes("EADDRINUSE")) {
    console.error(`  Port ${PORT} is still in use after the kill attempt — aborting.`);
    process.exit(1);
  }
  // Not a port conflict: HOST likely doesn't resolve here. Bind all interfaces, keep the short URL.
  console.warn(`  (hostname ${HOST} not bindable; falling back to 0.0.0.0)`);
  server = Bun.serve({ hostname: "0.0.0.0", port: PORT, fetch: handler });
}

console.log(`\n  Wellness Beyond #LLJC — dev server`);
console.log(`  ➜  Short URL:  http://${HOST}/            (Caddy proxy → :${PORT})`);
console.log(`  ➜  Direct:     http://localhost:${server.port}/\n`);
