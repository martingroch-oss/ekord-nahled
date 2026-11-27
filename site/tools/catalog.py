"""F126: katalog všech domů EKORD (všechny řady z původního webu) a stránka každého domu.

python catalog.py assets   – výkresy, fotky a PDF do img/domy, img/domy/foto, pdf; zapíše domy.json
python catalog.py renders  – rendery exteriéru z _render/out/f135/set do img/domy/render (F136)
python catalog.py pages    – domy.html a dum/<slug>.html z domy.json (volá i build.py)

Seznam domů, řady, popisy a fotky jsou z uloženého původního webu (01_web_mirror, stránky řad v galerii).
Půdorys domu: vektorová kresba ze čtečky (zdi z řezu FreeCAD řešiče, nábytek ze čtečky) jen když projde kontrolou
kvality (`vector_ok`); jinak původní výkres převedený do šedi (raster z webu nebo vykreslené PDF). Nic se nevymýšlí:
dům bez výkresu ukáže fotku nebo vizualizaci.
"""
import re, html, os, json, sys, shutil, subprocess, csv, unicodedata

H = os.environ.get("CAT_H") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # docs/web/proto (CMS: kořen webu)
ROOT = os.path.abspath(os.path.join(H, "../../.."))                         # EKORD
M = os.path.join(ROOT, "01_web_mirror")
G = os.path.join(M, "galerie/architektonicka-reseni")
REG = os.environ.get("CAT_REG") or os.path.join(ROOT, "work/regress")
PY = os.path.join(ROOT, ".venv/bin/python")
CAT = os.environ.get("CAT_JSON") or os.path.join(H, "domy.json")

GROUPS = [("typicke", "Typické domy EKORD", "Přízemní domy s valbovou střechou a lomeným průčelím do zahrady. Řady podle počtu pokojů."),
          ("ostatni", "Ostatní domy EKORD", "Menší domy, domy se sedlovou střechou, domy z buněk a zelené domy pod vrstvou zeminy.")]
SERIES = [  # (slug, stránka původního webu, název, skupina, popis)
    ("3-1", "typicke-domy-ekord/31", "3+1", "typicke", "Domy pro malou rodinu, pro tři až čtyři osoby."),
    ("4-1", "typicke-domy-ekord/41", "4+1", "typicke", "Domy pro pět až šest osob, často třígenerační."),
    ("5-1", "typicke-domy-ekord/51", "5+1", "typicke", "Velké domy pro šest až osm osob, některé s garáží."),
    ("6-1", "typicke-domy-ekord/61-a-vice", "6+1 a více", "typicke", "Třígenerační dům s garáží."),
    ("mini", "ostatni-domy-ekord/ekord-mini", "EKORD mini", "ostatni", "Malé domy pro dvě až pět osob."),
    ("z", "ostatni-domy-ekord/ekord-z-zelene-domy", "EKORD Z (zelené domy)", "ostatni",
     "Střecha a často i stěny jsou chráněné vrstvou zeminy a vegetací. Patří sem i domy z buněk TEKAZ."),
    ("s", "ostatni-domy-ekord/ekord-s", "EKORD S (sedlová střecha)", "ostatni", "Přízemní domy se sedlovou střechou."),
    ("b", "ostatni-domy-ekord/ekord-b", "EKORD B (z buněk)", "ostatni", "Domy skládané z buněk, od rekreačního bydlení po rodinný dům."),
    ("e", "ostatni-domy-ekord/ekord-e", "EKORD E (easy)", "ostatni", "Jednoduché domy pro dva a více obyvatel."),
    ("jine", "ostatni-domy-ekord/jine-prizemni-domy", "Jiné přízemní domy", "ostatni", "Přízemní domy mimo typové řady."),
]


def slugify(t):
    t = re.sub(r"^Ekord\s+", "", t.strip(), flags=re.I)
    t = re.sub(r"-TOPd.*$", "", t)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9-]+", "", t.replace(" ", ""))


def scrape():
    """domy z uložených stránek řad: název, popis, řady, výkresy (jpg/gif/pdf) a fotky 800 px"""
    houses = {}
    for sl, page, name, grp, _ in SERIES:
        s = open(os.path.join(G, page, "index.html"), encoding="utf-8", errors="ignore").read()
        for it in s.split('<div class="houses-item">')[1:]:
            title = re.sub(r"\s+", " ", html.unescape(re.search(r"<h2>(.*?)</h2>", it, re.S).group(1))).strip()
            desc = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", re.search(r'class="description">(.*?)</div>', it, re.S).group(1)))).strip()
            k = slugify(title)
            h = houses.setdefault(k, dict(slug=k, title=re.sub(r"^Ekord\s+", "", title).replace("-TOPdům2011", ""), desc=desc,
                                          series=[], plans=[], pdfs=[], photos=[], top2011="TOPdům2011" in title))
            if sl not in h["series"]:
                h["series"].append(sl)
            for f in re.findall(r'href="(media/[^"]+)"', it):
                p = os.path.join(M, f)
                if not os.path.exists(p):
                    continue
                if f.lower().endswith(".pdf"):
                    # odkaz z webu na PDF jiného domu (S 211gZY -> s186.pdf) se nebere: číslo plochy musí sedět
                    num = re.search(r"\d+", h["title"].split()[-1]).group(0)
                    if num in os.path.basename(f) and p not in h["pdfs"]:
                        h["pdfs"].append(p)
                elif p not in h["plans"]:
                    h["plans"].append(p)
            for f in re.findall(r'href="(assets/cache/images/[^"]*800x800[^"]+)"', it):
                p = os.path.join(M, f)
                if os.path.exists(p) and p not in h["photos"]:
                    h["photos"].append(p)
    for h in houses.values():
        h["m2"] = int(re.search(r"\d+", h["title"].split()[-1]).group(0))
        h["persons"] = (re.search(r"(?:až )?pro [^-,(]*?osob[ay]?(?: \([^)]*\)[^-]*)?", h["desc"]) or [None])[0] if re.search(r"pro .*osob", h["desc"]) else None
        h["notes"] = [x.strip() for x in re.split(r"\s+-\s+", h["desc"])[1:] if "osob" not in x and x.strip()]
    return houses


def summary():
    rows = {}
    p = os.path.join(REG, "summary.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            rows[r["id"]] = r
    return rows


def vector_ok(rid, info, summ):
    """kresba ze čtečky se ukáže jen, když odpovídá výkresu: zdi z řešiče, rozumný podíl zdí, příčky, kuchyň, nábytek, plocha"""
    raw = json.load(open(os.path.join(REG, rid, "raw_geo.json")))
    fc = json.load(open(os.path.join(REG, rid, "fc_solved.json")))
    ty = [f.get("type") for f in raw.get("furniture", [])]
    s = summ.get(rid, {})
    try:
        dev = abs(float(s.get("area_dev_pct") or 0))
    except ValueError:
        dev = 99
    why = []
    if not info.get("walls_fc"): why.append("bez zdí z řešiče")
    if not 0.06 < info.get("wall_ratio", 0) < 0.32: why.append("zdi %.2f plochy" % info.get("wall_ratio", 0))
    if (fc.get("partitions") or 0) < 4 and not raw.get("drawing"): why.append("málo příček")   # F134: pieces of the author's drawing merge
    if "hob" not in ty: why.append("bez kuchyně")
    if len(ty) < 25: why.append("málo vybavení")
    if dev > 25: why.append("plocha mimo o %.0f %%" % dev)
    # F129: partitions per floor area (FreeCAD section): EKORD plans have 1.6-2.8 m of partition per 10 m2; much less
    # means the reader missed partitions and rooms run into each other (133j94)
    from shapely.geometry import Polygon as _P
    from shapely.ops import unary_union as _U
    pu = _U([_P(p_).buffer(0) for p_ in fc.get("section_partitions_1_5m") or [] if len(p_) >= 3])
    dens = (pu.length / 2 if not pu.is_empty else 0.0) / max(_P(raw["footprint"]).buffer(0).area, 1.0) * 10
    if dens < 1.4: why.append("příček %.1f m na 10 m²" % dens)
    return not why, why


def open_pdf(src):
    """PDF z webu mají často poškozený strom stránek; pdfvec._open je přestaví (jako čtečka)"""
    sys.path.insert(0, os.path.join(ROOT, "_tools"))
    import pdfvec
    return pdfvec._open(src)


def raster(src, dst, maxw=1600, page=0):
    """původní výkres do šedi: světlé (mřížka, papír) na bílou, ořez na kresbu"""
    from PIL import Image, ImageOps
    if src.lower().endswith(".pdf"):
        import pymupdf
        d = open_pdf(src); pg = d[page]
        z = 2600 / max(pg.rect.width, pg.rect.height)
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, alpha=False)
        im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    else:
        im = Image.open(src).convert("L")
    im = ImageOps.autocontrast(im, cutoff=0.5)
    im = im.point(lambda v: 255 if v > 212 else int(v * 0.92))
    bb = ImageOps.invert(im).point(lambda v: 255 if v > 40 else 0).getbbox()
    if bb:
        m = 12
        im = im.crop((max(0, bb[0] - m), max(0, bb[1] - m), min(im.width, bb[2] + m), min(im.height, bb[3] + m)))
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    im.save(dst, quality=84, optimize=True, progressive=True)
    return im.size


def assets():
    houses = scrape(); summ = summary()
    out = os.path.join(H, "img/domy"); fo = os.path.join(out, "foto"); pd = os.path.join(H, "pdf")
    for d in (out, fo, pd):
        os.makedirs(d, exist_ok=True)
    tool = os.path.join(H, "tools/svg_plan.py")
    for k, h in sorted(houses.items()):
        h["plan"] = None; h["why"] = []
        rid = None
        for p in h["pdfs"]:
            c = os.path.splitext(os.path.basename(p))[0].lower()
            if os.path.exists(os.path.join(REG, c, "fc_solved.json")):
                rid = c; break
        h["reader"] = rid
        if rid:
            r = os.path.join(REG, rid, "raw_geo.json")
            env = dict(os.environ, PXM="24"); env.pop("NOVIEWS", None)
            subprocess.run([PY, tool, r, r, out, k], env=env, capture_output=True)
            os.replace(os.path.join(out, k + "_pudorys.svg"), os.path.join(out, k + "_nahled.svg"))
            env = dict(os.environ, NOVIEWS="1", INFO="1"); env.pop("PXM", None)
            subprocess.run([PY, tool, r, r, out, k], env=env, capture_output=True)
            info = json.load(open(os.path.join(out, k + "_info.json")))
            ok, why = vector_ok(rid, info, summ)
            h["why"] = why
            if ok:
                h["plan"] = dict(kind="svg", thumb="img/domy/%s_nahled.svg" % k, big="img/domy/%s_pudorys.svg" % k,
                                 roof="img/domy/%s_strecha.svg" % k, rooms=info["rooms"], beds=info["beds"])
        if not h["plan"]:
            for f in ("_nahled.svg", "_pudorys.svg", "_strecha.svg", "_info.json"):
                if os.path.exists(os.path.join(out, k + f)):
                    os.remove(os.path.join(out, k + f))
            src = (h["plans"] or h["pdfs"] or [None])[0]
            if src:
                w, hh = raster(src, os.path.join(out, k + "_vykres.jpg"))
                h["plan"] = dict(kind="img", thumb="img/domy/%s_vykres.jpg" % k, big="img/domy/%s_vykres.jpg" % k, w=w, h=hh)
        h["photo_files"] = []
        for i, p in enumerate(h["photos"]):
            dst = "img/domy/foto/%s_%d.jpg" % (k, i + 1)
            shutil.copyfile(p, os.path.join(H, dst)); h["photo_files"].append(dst)
        if h["pdfs"]:
            open_pdf(h["pdfs"][0]).save(os.path.join(pd, k + ".pdf"), garbage=3, deflate=True)   # opravený strom stránek: otevře se v každém prohlížeči
            h["pdf"] = "pdf/%s.pdf" % k
        print("%-12s %-5s %-24s %s" % (k, (h["plan"] or {}).get("kind"), rid or "-", "; ".join(h["why"])))
    keep = ("slug", "title", "desc", "text", "hidden", "series", "m2", "persons", "notes", "plan", "photo_files", "pdf", "reader", "why", "top2011")
    json.dump([{k_: h.get(k_) for k_ in keep} for h in sorted(houses.values(), key=lambda h: (h["m2"], h["slug"]))],
              open(CAT, "w"), ensure_ascii=False, indent=1)
    print("domy:", len(houses))


# ---------------------------------------------------------------- vizualizace exteriéru (F136)
RSET = os.environ.get("CAT_RENDERS") or os.path.join(ROOT, "_render/out/f135/set")
RVIEWS = ("terasa_zlata", "terasa_den")
FACADE_CZ = {"cihla": "cihlový obklad", "omitka": "omítka", "drevo_modrin": "modřínové lamely",
             "drevo_sede": "šedé dřevěné obložení", "drevo_opalene": "opálené dřevo"}


def renders():
    """rendery exteriéru z modelu domu (04_3d/ekord_scene.py, FreeCAD skořepina) -> img/domy/render/<slug>_<pohled>.jpg
    a <slug>.json s receptem fasády ze záznamu renderu. Dům bez renderu nic nedostane, nic se nevymýšlí."""
    from PIL import Image
    out = os.path.join(H, "img/domy/render"); os.makedirs(out, exist_ok=True)
    n = 0
    for h in json.load(open(CAT)):
        rid = h.get("reader")
        if not rid or h["slug"] == "182j47" or not os.path.isdir(os.path.join(RSET, rid)):
            continue
        views = []
        for v in RVIEWS:
            src = [f for f in os.listdir(os.path.join(RSET, rid)) if f.endswith("_%s.png" % v)]
            if not src:
                continue
            im = Image.open(os.path.join(RSET, rid, src[0])).convert("RGB")
            im.thumbnail((1600, 1600))
            im.save(os.path.join(out, "%s_%s.jpg" % (h["slug"], v)), quality=84, optimize=True, progressive=True)
            views.append(v)
        if not views:
            continue
        log = os.path.join(os.path.dirname(RSET), "set_%s.log" % rid)
        m = re.search(r"exterior recipe (\S+) (\S+)", open(log, errors="ignore").read()) if os.path.exists(log) else None
        rec, roof = (m.group(1), m.group(2)) if m else (None, None)
        json.dump(dict(views=views, recipe=rec, metal=roof == "metal"), open(os.path.join(out, h["slug"] + ".json"), "w"))
        n += 1; print("%-12s %-14s %s" % (h["slug"], rec, roof))
    print("rendery:", n)


def render_of(h):
    """rendery domu na disku (krok renders): (seznam cest, popis materiálu) nebo None"""
    j = os.path.join(H, "img/domy/render", h["slug"] + ".json")
    if not os.path.exists(j):
        return None
    r = json.load(open(j))
    rec = r.get("recipe") or ""
    fac = FACADE_CZ.get(rec) or FACADE_CZ.get(rec.split("_")[0], "")
    mat = ("fasáda %s, " % fac if fac else "") + ("plechová střecha na stojatou drážku" if r.get("metal") else "tašková střecha")
    return ["img/domy/render/%s_%s.jpg" % (h["slug"], v) for v in r["views"]], mat


# ---------------------------------------------------------------- stránky
CSS = """
:root{--bg:#FFFFFF;--bg-2:#F3F3F1;--ink:#111111;--ink-2:#4A4A4A;--mute:#737373;--line:#E2E2DF;
  --sans:"Inter Variable",Inter,"Helvetica Neue",Helvetica,Arial,sans-serif;--m:clamp(20px,5vw,88px);--max:1440px;--ease:cubic-bezier(.2,.7,.2,1)}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{font:400 17px/1.6 var(--sans);color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased;font-feature-settings:"ss01","cv11"}
img,svg{display:block;max-width:100%}
a{color:inherit}
:focus-visible{outline:1.5px solid currentColor;outline-offset:3px}
.wrap{padding-inline:var(--m);max-width:var(--max);margin-inline:auto}
h1,h2,h3{font-weight:300}
h1{font-size:clamp(40px,6vw,96px);line-height:.98;letter-spacing:-.04em}
h2{font-size:clamp(28px,3.4vw,52px);line-height:1.05;letter-spacing:-.035em}
h3{font-size:clamp(20px,1.7vw,25px);line-height:1.25;letter-spacing:-.015em;font-weight:400}
p{max-width:62ch;text-wrap:pretty}
.eyebrow{font-size:14px;line-height:1.2;color:var(--mute)}
.eyebrow a{text-decoration:none}.eyebrow a:hover{text-decoration:underline}
.lead{font-size:clamp(18px,1.4vw,21px);color:var(--ink-2)}
.btn{display:inline-flex;align-items:center;gap:14px;min-height:50px;padding:0 24px;font:500 15px/1 var(--sans);text-decoration:none;background:var(--ink);color:#fff}
.btn:hover{background:#333}
.btn.ghost{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 1px currentColor}.btn.ghost:hover{background:var(--bg-2)}
.top{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.92);backdrop-filter:saturate(1.2) blur(14px);-webkit-backdrop-filter:saturate(1.2) blur(14px);box-shadow:0 1px 0 var(--line)}
.top .wrap{display:flex;align-items:center;justify-content:space-between;height:72px;gap:24px}
.brand{display:flex;align-items:center;gap:12px;text-decoration:none}
.brand img{width:40px;filter:grayscale(1) contrast(1.1)}
.brand b{font:500 17px/1 var(--sans);letter-spacing:.12em}
.nav{display:flex;align-items:center;gap:clamp(14px,2.4vw,34px)}
.nav a{white-space:nowrap}.nav a:not(.btn){text-decoration:none;font-size:15px}
.nav a:not(.btn):hover,.nav a.on{text-decoration:underline;text-underline-offset:6px;text-decoration-thickness:1px}
.nav .btn{min-height:40px;padding:0 18px;font-size:14px}
.intro{padding-block:clamp(56px,8vw,120px) clamp(32px,4vw,56px)}
.intro .lead{margin-top:22px}
.chips{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:34px;font-size:15px}
.chips a{text-decoration:none;color:var(--ink-2);padding-bottom:3px;border-bottom:1px solid var(--line)}
.chips a:hover{color:var(--ink);border-color:var(--ink)}
.group{padding-top:clamp(40px,5vw,72px)}
.group>.ghead{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px;align-items:end;padding-bottom:20px;border-bottom:1px solid var(--ink)}
.series{padding-top:clamp(36px,4vw,56px);scroll-margin-top:90px}
.series .shead{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 24px;align-items:baseline;margin-bottom:18px}
.series .shead p{color:var(--mute);font-size:15px}
.grid{list-style:none;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-top:1px solid var(--line);border-left:1px solid var(--line)}
.grid li{background:#fff;transition:background .3s;border-right:1px solid var(--line);border-bottom:1px solid var(--line)}
.grid li:hover{background:var(--bg-2)}
.grid a{display:block;padding:18px;text-decoration:none;height:100%}
.grid .pl{aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;margin-bottom:14px;overflow:hidden}
.grid .pl img{max-height:100%;object-fit:contain}
.grid .pl img.raster{mix-blend-mode:multiply}
.grid .pl img.photo{width:100%;height:100%;object-fit:cover;filter:grayscale(1) contrast(1.05)}
.grid b{display:block;font-size:19px;font-weight:400;letter-spacing:-.01em}
.grid span{display:block;font-size:13px;color:var(--mute);line-height:1.45;margin-top:2px}
.foot{margin-top:clamp(80px,10vw,150px);padding-block:48px;border-top:1px solid var(--line);font-size:14px;color:var(--mute);display:flex;flex-wrap:wrap;gap:12px 32px;justify-content:space-between}
.foot a{color:var(--ink)}
/* dům */
.house .meta{display:flex;flex-wrap:wrap;gap:10px 40px;margin-top:30px;font-size:15px}
.house .meta div{display:flex;flex-direction:column}
.house .meta small{font-size:13px;color:var(--mute)}
.house .meta b{font-weight:400;font-size:21px;letter-spacing:-.01em}
.plan{margin-top:clamp(36px,5vw,72px);background:var(--bg-2);padding:clamp(16px,4vw,56px)}
.plan svg,.plan img{width:100%;height:auto;max-height:82vh;margin-inline:auto}
.plan img{mix-blend-mode:multiply;object-fit:contain}
.plan svg text{font-family:var(--sans)}
.plan figcaption{font-size:13px;color:var(--mute);margin-top:14px}
.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:clamp(24px,5vw,80px);margin-top:clamp(48px,6vw,96px)}
.rooms{list-style:none;border-top:1px solid var(--ink)}
.rooms li{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--line);font-size:16px}
.rooms li span{color:var(--mute)}
.roof svg{width:100%;height:auto}
.photos{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:clamp(48px,6vw,96px)}
.photos img{width:100%;aspect-ratio:16/10;object-fit:cover}
.photos figure:only-child{grid-column:1/-1}
.cta{margin-top:clamp(56px,7vw,110px);background:var(--ink);color:#fff;padding:clamp(28px,5vw,72px);display:flex;flex-wrap:wrap;gap:24px 48px;align-items:center;justify-content:space-between}
.cta h2{color:#fff;max-width:18ch}
.cta .btn{background:#fff;color:var(--ink)}.cta .btn:hover{background:var(--bg-2)}
.pager{display:flex;justify-content:space-between;gap:16px;margin-top:40px;font-size:15px}
.pager a{text-decoration:none}.pager a:hover{text-decoration:underline}
.links{display:flex;flex-wrap:wrap;gap:10px;margin-top:28px}
.about{margin-top:clamp(28px,4vw,48px);display:grid;gap:14px;font-size:18px}
.render{margin-top:clamp(36px,5vw,72px)}
.render img{width:100%;height:auto;aspect-ratio:16/9;object-fit:cover}
.render figcaption{font-size:13px;color:var(--mute);margin-top:14px;max-width:80ch}
@media (max-width:1100px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:760px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.grid a{padding:12px}.grid b{font-size:16px}
  .group>.ghead,.two{grid-template-columns:1fr}.photos{grid-template-columns:1fr}.nav .hide-m{display:none}}
"""

HEAD = """<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
<meta name="description" content="%s">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#111111">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource-variable/inter@5.0.16/index.css">
<link rel="icon" href="%simg/znak.svg">
<style>%s</style>
</head>
<body>
<header class="top"><div class="wrap">
  <a class="brand" href="%sindex.html" aria-label="EKORD, úvod"><img src="%simg/znak.svg" alt=""><b>EKORD</b></a>
  <nav class="nav"><a href="%sindex.html" class="hide-m">Dům 182j47</a><a href="%sdomy.html"%s>Všechny domy</a><a class="btn" href="%sindex.html#kontakt">Napsat</a></nav>
</div></header>
<main>
"""
FOOT = """</main>
<footer class="wrap"><div class="foot"><span>Ing. Marian Groch, autor domů EKORD</span><span>Výkresy a fotky z původního webu ekord.cz. Kresby půdorysů jsou přečtené z výkresů.</span><a href="%sindex.html#kontakt">Napsat architektovi</a></div></footer>
</body>
</html>
"""


def nbsp(t):
    """česká typografie: jednopísmenné předložky a spojky nezůstanou na konci řádku"""
    return re.sub(r"(^|\s)([ksvzouaiKSVZOUAI])[ \t]+", lambda m: m.group(1) + m.group(2) + "&nbsp;", t)


def esc(t):
    return html.escape(t or "", quote=True)


def tile(h, pre=""):
    p = h.get("plan")
    sub = "%d m²" % h["m2"] + (" · " + h["persons"] if h.get("persons") else "")
    if p and p["kind"] == "svg":
        im = '<img src="%s%s" alt="Půdorys domu %s" loading="lazy">' % (pre, p["thumb"], esc(h["title"]))
    elif p:
        im = '<img class="raster" src="%s%s" alt="Původní výkres domu %s" loading="lazy">' % (pre, p["thumb"], esc(h["title"]))
    elif h.get("photo_files"):
        im = '<img class="photo" src="%s%s" alt="Dům %s" loading="lazy">' % (pre, h["photo_files"][0], esc(h["title"]))
    else:
        im = ""
    return ('<li><a href="%sdum/%s.html"><div class="pl">%s</div><b>%s</b><span>%s</span></a></li>'
            % (pre, h["slug"], im, esc(h["title"]), esc(sub)))


def pages(cat=None):
    cat = cat or json.load(open(CAT))
    for h in cat:                                           # CMS: skrytý dům na webu není, ani jeho stránka
        if h.get("hidden") and os.path.exists(os.path.join(H, "dum", h["slug"] + ".html")):
            os.remove(os.path.join(H, "dum", h["slug"] + ".html"))
    cat = [h for h in cat if not h.get("hidden")]
    by = {h["slug"]: h for h in cat}
    sname = {s[0]: s[2] for s in SERIES}
    # katalog
    o = [HEAD % ("Všechny domy EKORD", "Katalog přízemních domů EKORD: %d domů v %d řadách." % (len(cat), len(SERIES)),
                 "", CSS, "", "", "", "", ' class="on"', "")]
    o.append('<section class="wrap intro"><p class="eyebrow">Katalog</p><h1 style="margin-top:16px">Všechny domy EKORD</h1>'
             '<p class="lead">%d přízemních domů v&nbsp;%d řadách. Každý je výchozí bod: architekt ho upraví pro konkrétní pozemek, '
             'světové strany a&nbsp;rodinu.</p><nav class="chips" aria-label="Řady">%s</nav></section>'
             % (len(cat), len(SERIES), "".join('<a href="#%s">%s</a>' % (s[0], esc(s[2])) for s in SERIES)))
    for gk, gname, gdesc in GROUPS:
        o.append('<section class="wrap group"><div class="ghead"><h2>%s</h2><p class="lead">%s</p></div>' % (gname, gdesc))
        for sl, _, name, grp, desc in SERIES:
            if grp != gk:
                continue
            hs = sorted([h for h in cat if sl in h["series"]], key=lambda h: (h["m2"], h["slug"]))
            o.append('<div class="series" id="%s"><div class="shead"><h3>%s</h3><p>%s %s</p></div><ul class="grid">%s</ul></div>'
                     % (sl, esc(name), esc(desc), "%d %s." % (len(hs), "dům" if len(hs) == 1 else "domy" if len(hs) < 5 else "domů"),
                        "".join(tile(h) for h in hs)))
        o.append('</section>')
    o.append(FOOT % "")
    open(os.path.join(H, "domy.html"), "w").write("\n".join(o))
    # domy
    os.makedirs(os.path.join(H, "dum"), exist_ok=True)
    for h in cat:
        s0 = h["series"][0]
        sib = sorted([x for x in cat if s0 in x["series"]], key=lambda x: (x["m2"], x["slug"]))
        i = [x["slug"] for x in sib].index(h["slug"])
        prev_, next_ = sib[i - 1] if i > 0 else None, sib[i + 1] if i + 1 < len(sib) else None
        o = [HEAD % ("Dům EKORD %s" % h["title"], esc(h["desc"]), "../", CSS, "../", "../", "../", "../", "", "../")]
        series_links = " · ".join('<a href="../domy.html#%s">%s</a>' % (s, esc(sname[s])) for s in h["series"])
        o.append('<section class="wrap intro house"><p class="eyebrow"><a href="../domy.html">Všechny domy</a> / %s</p>'
                 '<h1 style="margin-top:16px">Dům %s</h1><p class="lead">%s</p>' % (series_links, esc(h["title"]), esc(h["desc"])))
        meta = [("Plocha podle názvu", "%d m²" % h["m2"])]
        if h.get("persons"):
            meta.append(("Obyvatelé", h["persons"][0].upper() + h["persons"][1:]))
        p = h.get("plan") or {}
        if p.get("kind") == "svg":
            if p.get("beds"):
                meta.append(("Postele v půdorysu", str(p["beds"])))
            if p.get("rooms"):
                meta.append(("Místnosti", str(len(p["rooms"]))))
        o.append('<div class="meta">%s</div>' % "".join('<div><small>%s</small><b>%s</b></div>' % (a, esc(b)) for a, b in meta))
        links = []
        if h["slug"] == "182j47":
            links.append('<a class="btn" href="../index.html#prohlidka">Projít dům ve 3D <span class="ar">→</span></a>')
            links.append('<a class="btn ghost" href="../index.html#den">Celý příběh domu</a>')
        if h.get("pdf"):
            links.append('<a class="btn ghost" href="../%s" target="_blank" rel="noopener">Původní výkres (PDF)</a>' % h["pdf"])
        if links:
            o.append('<div class="links">%s</div>' % "".join(links))
        if (h.get("text") or "").strip():                 # delší popis domu z redakčního systému, odstavce po prázdném řádku
            o.append('<div class="about">%s</div>' % "".join("<p>%s</p>" % nbsp(esc(t.strip())).replace("\n", "<br>")
                                                         for t in re.split(r"\n\s*\n", h["text"]) if t.strip()))
        rr = render_of(h)
        if rr:
            o.append('<figure class="render"><img src="../%s" alt="Vizualizace domu %s od zahrady" width="1600" height="900">'
                     '<figcaption>Vizualizace z&nbsp;3D modelu postaveného podle výkresu: %s. Materiály jsou ilustrační, '
                     'fasádu a&nbsp;krytinu vybíráte s&nbsp;architektem.</figcaption></figure>' % (rr[0][0], esc(h["title"]), rr[1]))
        if p.get("kind") == "svg":
            svg = re.sub(r"<\?xml[^>]*>", "", open(os.path.join(H, p["big"])).read())
            o.append('<figure class="plan">%s<figcaption>Půdorys se zařízením, nakreslený z&nbsp;původního výkresu. '
                     'Plochy místností jsou z&nbsp;kót výkresu.</figcaption></figure>' % svg)
        elif p.get("kind") == "img":
            o.append('<figure class="plan"><img src="../%s" alt="Původní výkres domu %s" width="%d" height="%d">'
                     '<figcaption>Původní výkres domu.</figcaption></figure>' % (p["big"], esc(h["title"]), p["w"], p["h"]))
        if p.get("kind") == "svg" and (p.get("rooms") or os.path.exists(os.path.join(H, p["roof"]))):
            rooms = "".join('<li>%s<span>%s m²</span></li>' % (esc(r["name"][0].upper() + r["name"][1:]), ("%.1f" % r["area"]).replace(".", ","))
                            for r in sorted(p.get("rooms") or [], key=lambda r: -r["area"]))
            roof = re.sub(r"<\?xml[^>]*>", "", open(os.path.join(H, p["roof"])).read()) if os.path.exists(os.path.join(H, p["roof"])) else ""
            roof = re.sub(r'<g class="rays".*?</g>', "", roof, flags=re.S)
            o.append('<div class="two"><div><h3 style="margin-bottom:18px">Místnosti</h3><ul class="rooms">%s</ul></div>'
                     '<div class="roof"><h3 style="margin-bottom:18px">Střecha</h3>%s</div></div>' % (rooms, roof))
        extra = [(f, "Vizualizace domu %s ve dne" % h["title"]) for f in (rr[0][1:] if rr else [])]
        pics = extra + [(f, "Dům %s, foto nebo vizualizace %d" % (h["title"], k + 1)) for k, f in enumerate(h.get("photo_files") or [])]
        if pics:
            o.append('<div class="photos">%s</div>' % "".join(
                '<figure><img src="../%s" alt="%s" loading="lazy"></figure>' % (f, esc(a)) for f, a in pics))
        o.append('<div class="cta"><h2>Tento dům upravíme pro váš pozemek</h2><a class="btn" href="../index.html#kontakt">Napsat architektovi <span class="ar">→</span></a></div>')
        o.append('<nav class="pager" aria-label="Další domy řady">%s%s</nav></section>' % (
            '<a href="%s.html">← %s</a>' % (prev_["slug"], esc(prev_["title"])) if prev_ else "<span></span>",
            '<a href="%s.html">%s →</a>' % (next_["slug"], esc(next_["title"])) if next_ else "<span></span>"))
        o.append(FOOT % "../")
        open(os.path.join(H, "dum", h["slug"] + ".html"), "w").write("\n".join(o))
    print("stránky:", len(cat) + 1)


if __name__ == "__main__":
    if "assets" in sys.argv:
        assets()
    if "renders" in sys.argv:
        renders()
    if "pages" in sys.argv:
        pages()
