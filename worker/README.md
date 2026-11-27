# Redakční systém webu EKORD – nastavení (jednou, asi 20 minut)

Jak to funguje:
- Táta otevře `https://martingroch-oss.github.io/ekord-nahled/admin/` a přihlásí se jménem a heslem.
- Redakce pošle změnu malému serveru na Cloudflare (Worker, zdarma). Ten ověří heslo a uloží změnu do repozitáře webu.
- GitHub Action stránky do dvou minut přegeneruje.
- Heslo ani GitHub token nikdy nejsou na webu ani v repozitáři, jsou jen v Cloudflare.

## 1. GitHub token (jen pro repozitář webu)
1. github.com → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Nastav:
   - Název: `ekord-redakce`
   - Expiration: 1 rok (pak ho obnov)
   - Repository access: **Only select repositories** → `ekord-nahled`
   - Permissions → Repository:
     - **Contents: Read and write**
     - **Actions: Read-only** (ukazuje stav sestavení)
3. Token zkopíruj. Uvidíš ho jen jednou.

## 2. Cloudflare Worker (přes web, nic se neinstaluje)
1. Založ účet na dash.cloudflare.com (zdarma).
2. Compute (Workers) → **Create** → Worker → název `ekord-redakce` → Deploy.
3. **Edit code**, smaž ukázku, vlož celý obsah `worker/worker.js` z repozitáře webu → Deploy.
4. Settings → **Variables and Secrets** přidej:

   | Název | Typ | Hodnota |
   |---|---|---|
   | `GH_REPO` | Text | `martingroch-oss/ekord-nahled` |
   | `GH_BRANCH` | Text | `main` |
   | `ALLOW_ORIGIN` | Text | `https://martingroch-oss.github.io` |
   | `GH_TOKEN` | **Secret** | token z kroku 1 |
   | `USERS` | **Secret** | např. `tata:dlouhe-heslo-pro-tatu, martin:jine-heslo` |
   | `SESSION_SECRET` | **Secret** | náhodný řetězec, např. výstup `openssl rand -base64 32` |

5. Adresu Workeru (`https://ekord-redakce.<něco>.workers.dev`) mi pošli. Zapíšu ji do `admin/config.json` a redakce se připojí.

Pokud raději terminál: ve složce `worker/` spusť `npx wrangler deploy` a pak `npx wrangler secret put GH_TOKEN` (a stejně `USERS` a `SESSION_SECRET`).

## Údržba
- Heslo změníš nebo editora přidáš úpravou secretu `USERS`. Odebraný editor je hned odhlášen.
- Když token vyprší, redakce při ukládání hlásí chybu GitHubu 401. Vytvoř nový token a vlož ho do `GH_TOKEN`.
- Každá úprava je commit „Redakční systém, editor: …“. Starou verzi lze vrátit přes historii repozitáře.
- Domácí nasazení (`python tools/deploy.py` v docs/web/proto) si nejdřív stáhne tátovy úpravy a zachová je. Půdorysy a rendery dál vznikají doma.
- Zkouška bez internetu: `python cms/mock_server.py <kopie webu>`, přihlášení zkouska / zkouska.
