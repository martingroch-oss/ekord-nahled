// Redakční systém webu EKORD: přihlášení jménem a heslem a uložení změn do repozitáře webu na GitHubu.
// Cloudflare Worker (zdarma). Tajné hodnoty se nastaví v Cloudflare, nikdy nejsou v kódu ani v repozitáři:
//   GH_TOKEN        jemně omezený GitHub token jen pro repozitář webu (Contents: read & write)
//   USERS           "jmeno:heslo" pro každého editora, oddělené čárkou nebo novým řádkem
//   SESSION_SECRET  dlouhý náhodný řetězec pro podpis přihlášení
// Proměnné (wrangler.toml): GH_REPO = "vlastnik/repozitar", GH_BRANCH = "main", ALLOW_ORIGIN = adresa webu.
//
// API (vše JSON):
//   POST /login   {user, pass}                       -> {token, user}       (platí 12 hodin)
//   GET  /file?path=content/domy.json                -> {text, sha}
//   POST /commit  {message, files:[{path, text|b64|delete, base_sha?}]}  -> {commit}
//                 base_sha: soubor se od načtení nezměnil, jinak 409 (někdo upravil současně)
//   GET  /status                                     -> poslední běh sestavení webu
// Zapisovat lze jen do content/*.json, img/domy/foto/*.jpg a pdf/*.pdf.

const ALLOWED = [/^content\/[a-z0-9_-]+\.json$/, /^img\/domy\/foto\/[a-z0-9_-]+\.jpg$/, /^pdf\/[a-z0-9_-]+\.pdf$/];
const MAX_FILE = 8 * 1024 * 1024;
const TTL = 12 * 3600;

const enc = new TextEncoder();
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const fromB64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

async function hmac(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64u(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}

function same(a, b) {            // porovnání v konstantním čase
  const x = enc.encode(a), y = enc.encode(b);
  let d = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) d |= (x[i] || 0) ^ (y[i] || 0);
  return d === 0;
}

function users(env) {
  const out = {};
  for (const line of (env.USERS || "").split(/[,\n]/)) {
    const i = line.indexOf(":");
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}

async function makeToken(env, user) {
  const body = b64u(enc.encode(JSON.stringify({ u: user, e: Math.floor(Date.now() / 1000) + TTL })));
  return body + "." + (await hmac(env.SESSION_SECRET, body));
}

async function checkToken(env, req) {
  const t = (req.headers.get("Authorization") || "").replace(/^Bearer\s+/, "");
  const [body, sig] = t.split(".");
  if (!body || !sig || !same(sig, await hmac(env.SESSION_SECRET, body))) return null;
  const p = JSON.parse(new TextDecoder().decode(fromB64u(body)));
  if (p.e < Date.now() / 1000 || !(p.u in users(env))) return null;
  return p.u;
}

function gh(env, path, init = {}) {
  return fetch("https://api.github.com/repos/" + env.GH_REPO + path, {
    ...init,
    headers: { Authorization: "Bearer " + env.GH_TOKEN, Accept: "application/vnd.github+json", "User-Agent": "ekord-cms",
               "X-GitHub-Api-Version": "2022-11-28", ...(init.body ? { "Content-Type": "application/json" } : {}) },
  });
}

async function ghJson(env, path, init) {
  const r = await gh(env, path, init);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error("GitHub " + r.status + ": " + (j.message || "")), { status: r.status });
  return j;
}

const utf8b64 = (s) => { let b = ""; for (const c of enc.encode(s)) b += String.fromCharCode(c); return btoa(b); };

async function readFile(env, path) {
  const branch = env.GH_BRANCH || "main";
  const j = await ghJson(env, "/contents/" + path + "?ref=" + branch);
  let text;
  if (j.content) text = new TextDecoder().decode(Uint8Array.from(atob(j.content.replace(/\n/g, "")), (c) => c.charCodeAt(0)));
  else {                                                     // soubor nad 1 MB: obsah přes blob
    const b = await ghJson(env, "/git/blobs/" + j.sha);
    text = new TextDecoder().decode(Uint8Array.from(atob(b.content.replace(/\n/g, "")), (c) => c.charCodeAt(0)));
  }
  return { text, sha: j.sha };
}

async function commit(env, user, message, files) {
  const branch = env.GH_BRANCH || "main";
  if (!Array.isArray(files) || !files.length || files.length > 40) throw Object.assign(new Error("špatný seznam souborů"), { status: 400 });
  for (const f of files) {
    if (!ALLOWED.some((re) => re.test(f.path || ""))) throw Object.assign(new Error("sem se zapisovat nesmí: " + f.path), { status: 403 });
    const size = f.text != null ? f.text.length : f.b64 ? f.b64.length * 0.75 : 0;
    if (size > MAX_FILE) throw Object.assign(new Error("soubor je moc velký: " + f.path), { status: 413 });
  }
  const ref = await ghJson(env, "/git/ref/heads/" + branch);
  const head = await ghJson(env, "/git/commits/" + ref.object.sha);
  const tree = [];
  for (const f of files) {
    if (f.base_sha) {                                        // současná úprava jiným editorem: neprepisovat
      const cur = await gh(env, "/contents/" + f.path + "?ref=" + ref.object.sha);
      const cj = cur.ok ? await cur.json() : null;
      if (cj && cj.sha !== f.base_sha) throw Object.assign(new Error("Soubor " + f.path + " mezitím změnil někdo jiný. Načtěte stránku znovu."), { status: 409 });
    }
    if (f.delete) { tree.push({ path: f.path, mode: "100644", type: "blob", sha: null }); continue; }
    const blob = await ghJson(env, "/git/blobs", { method: "POST", body: JSON.stringify({ content: f.b64 || utf8b64(f.text), encoding: "base64" }) });
    tree.push({ path: f.path, mode: "100644", type: "blob", sha: blob.sha });
  }
  const t = await ghJson(env, "/git/trees", { method: "POST", body: JSON.stringify({ base_tree: head.tree.sha, tree }) });
  const c = await ghJson(env, "/git/commits", { method: "POST", body: JSON.stringify({
    message: (message || "Úprava obsahu").slice(0, 200) + "\n\nRedakční systém, editor: " + user, tree: t.sha, parents: [ref.object.sha] }) });
  await ghJson(env, "/git/refs/heads/" + branch, { method: "PATCH", body: JSON.stringify({ sha: c.sha }) });
  return c.sha;
}

export default {
  async fetch(req, env) {
    const origin = req.headers.get("Origin") || "";
    const allow = (env.ALLOW_ORIGIN || "").split(",").map((s) => s.trim()).filter(Boolean);
    const cors = { "Access-Control-Allow-Origin": allow.includes(origin) ? origin : allow[0] || "",
                   "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                   "Vary": "Origin" };
    const out = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { ...cors, "Content-Type": "application/json; charset=utf-8" } });
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    const url = new URL(req.url);
    try {
      if (url.pathname === "/login" && req.method === "POST") {
        const { user, pass } = await req.json();
        const u = users(env);
        if (!user || !pass || !(user in u) || !same(pass, u[user])) {
          await new Promise((r) => setTimeout(r, 1200));     // zpomalí hádání hesla
          return out({ error: "Špatné jméno nebo heslo." }, 401);
        }
        return out({ token: await makeToken(env, user), user });
      }
      const user = await checkToken(env, req);
      if (!user) return out({ error: "Přihlášení vypršelo. Přihlaste se znovu." }, 401);
      if (url.pathname === "/file" && req.method === "GET") {
        const path = url.searchParams.get("path") || "";
        if (!/^content\/[a-z0-9_-]+\.json$/.test(path)) return out({ error: "tento soubor číst nelze" }, 403);
        return out(await readFile(env, path));
      }
      if (url.pathname === "/commit" && req.method === "POST") {
        const { message, files } = await req.json();
        return out({ commit: await commit(env, user, message, files) });
      }
      if (url.pathname === "/status" && req.method === "GET") {
        const j = await ghJson(env, "/actions/runs?per_page=1&branch=" + (env.GH_BRANCH || "main"));
        const r = (j.workflow_runs || [])[0];
        return out(r ? { status: r.status, conclusion: r.conclusion, title: r.display_title, updated: r.updated_at } : {});
      }
      return out({ error: "neznámá adresa" }, 404);
    } catch (e) {
      return out({ error: e.message }, e.status && e.status < 600 ? (e.status >= 500 ? 502 : e.status) : 500);
    }
  },
};
