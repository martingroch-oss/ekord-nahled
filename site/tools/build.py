"""Sestaví index.html: vloží SVG výkresy do src.html, texty z redakčního systému (content/uvod.json) a stránky katalogu.

Běží doma (docs/web/proto) i na GitHubu v repozitáři webu (CAT_H = kořen webu, CAT_JSON = content/domy.json)."""
import os, re, html as _html
T = os.path.dirname(os.path.abspath(__file__))
H = os.environ.get("CAT_H") or os.path.dirname(T)
import sys
SRC, OUT = (sys.argv[1:3] + ["src.html", "index.html"][len(sys.argv[1:3]):])
s = open(os.path.join(H, SRC)).read()


def nbsp(t):
    """česká typografie: jednopísmenné předložky a spojky nezůstanou na konci řádku"""
    return re.sub(r"(^|\s)([ksvzouaiKSVZOUAI])\s+", lambda m: m.group(1) + m.group(2) + "&nbsp;", t)


def cms_texts(s, texts):
    """upravitelné texty úvodní stránky: v každé <section> nadpisy a odstavce, které obsahují jen text (bez značek).
    Klíč = id sekce (nebo její aria-label) + značka + pořadí. Vrátí stránku s texty z redakce a seznam polí pro redakci."""
    fields = []
    def sec(m):
        a = m.group(1)
        sid = (re.search(r'\bid="([^"]+)"', a) or re.search(r'aria-label="([^"]+)"', a)).group(1)
        label = (re.search(r'aria-label="([^"]+)"', a) or [None, sid])[1]
        cnt = {}
        def el(e):
            tag, attrs, inner = e.group(1), e.group(2) or "", e.group(3)
            if "<" in inner or "{{" in inner or not inner.strip():
                return e.group(0)
            cnt[tag] = cnt.get(tag, 0) + 1
            key = "%s.%s%d" % (sid, tag, cnt[tag])
            default = re.sub(r"\s+", " ", _html.unescape(inner).replace("\xa0", " ")).strip()
            fields.append(dict(key=key, section=label, tag=tag, default=default))
            v = texts.get(key)
            if v is None or not str(v).strip():
                return e.group(0)
            return "<%s%s>%s</%s>" % (tag, attrs, nbsp(_html.escape(str(v).strip(), quote=False)), tag)
        body = re.sub(r"<(h[1-3]|p)(\s[^>]*)?>(.*?)</\1>", el, m.group(2), flags=re.S)
        return "<section%s>%s</section>" % (a, body)
    s = re.sub(r"<section(\s[^>]*)>(.*?)</section>", sec, s, flags=re.S)
    return s, fields


import json as _j
_u = os.path.join(H, "content/uvod.json")
s, _fields = cms_texts(s, _j.load(open(_u)) if os.path.exists(_u) else {})
if os.path.isdir(os.path.join(H, "content")) and SRC.endswith("src.html"):
    _j.dump(_fields, open(os.path.join(H, "content/uvod_pole.json"), "w"), ensure_ascii=False, indent=1)
strip = lambda t: re.sub(r"<\?xml[^>]*>", "", t)
s = s.replace("{{ROOF}}", strip(open(os.path.join(H, "img/182j47_strecha.svg")).read()))
s = s.replace("{{SIT}}", strip(open(os.path.join(H, "img/182j47_situace.svg")).read()))
s = s.replace("{{PLAN}}", strip(open(os.path.join(H, "img/182j47_pudorys.svg")).read()))
# F126: rejstřík odkazuje na stránky domů v katalogu (tools/catalog.py, domy.json); výběr typických domů + odkaz na všechny řady
sys.path.insert(0, T)
import catalog as _cat
CAT = _j.load(open(_cat.CAT))
_cat.pages(CAT)                                             # skryté domy vynechá a smaže jejich stránku
CAT = [h for h in CAT if not h.get("hidden")]
PICK = ["168j45", "174g54", "184jz3", "190h314", "286j46-187", "319j46-200"]
li = [_cat.tile(h) for k in PICK for h in CAT if h["slug"] == k]
s = s.replace("{{INDEX}}", "\n".join(li))
s = s.replace("{{INDEX_N}}", str(len(CAT))).replace("{{INDEX_SERIES}}", "".join(
    '<a href="domy.html#%s">%s</a>' % (x[0], x[2]) for x in _cat.SERIES))
# F120: video v úvodu a průlet, jakmile jsou vyrenderované; jinak obrázek a krátký průlet
ex = lambda f: os.path.exists(os.path.join(H, f))
s = s.replace("{{HERO_VIDEO}}", '<video muted loop playsinline autoplay preload="auto" poster="img/terasa_zlata.jpg" src="3d/hero.mp4" aria-hidden="true"></video>' if ex("3d/hero.mp4") else "")
tour = ex("3d/182j47_okruh.mp4")
s = s.replace("{{FLY_SRC}}", "3d/182j47_okruh.mp4" if tour else "3d/182j47_terasa_zlata_prulet.mp4")
s = s.replace("{{FLY_POSTER}}", "img/okruh_poster.jpg" if tour else "img/prulet_poster.jpg")
s = s.replace("{{FLY_HELP}}", "Okruh kolem domu od zahrady ke vstupu, renderovaný ze stejného modelu." if tour else "Průlet nad terasou, renderovaný ze stejného modelu.")
# řez se sluncem: rozměry z modelu domu (ekord_scene.py) a přesah střechy před okny do zahrady
import json, math
_sc = os.path.join(H, "../../../04_3d/ekord_scene.py")
_const = os.path.join(H, "site/const.json")              # na GitHubu model domu není: rozměry uložené při nasazení
if not os.path.exists(_sc) and os.path.exists(_const):
    k = json.load(open(_const)); over, soffit, head = k["over"], k["soffit"], k["head"]
else:
  sc = open(_sc).read()
  m = re.search(r"EAVE, SOFFIT, HEAD, CEIL = ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+)", sc)
  wt = float(re.search(r"WALL_T, TRUSS_K = ([\d.]+)", sc).group(1))
  soffit, head = float(m.group(2)), float(m.group(3))
  try:
    from shapely.geometry import Polygon
    g = json.load(open(os.path.join(H, "../../../04_3d/geo/182j47_geo.json")))
    F, Ev = Polygon(g["footprint"]), Polygon(g["eave"])
    ds = sorted(Ev.exterior.distance(F.exterior.interpolate(t / 200, normalized=True)) for t in range(200))
    over = ds[len(ds) // 2] + wt / 2                               # typický přesah + sklo v polovině zdi
  except Exception:
    over = 0.84 + wt / 2
  if os.environ.get("SITE_CONST"):
    json.dump(dict(over=round(over, 2), soffit=soffit, head=head), open(os.environ["SITE_CONST"], "w"))
s = s.replace("{{SUN_OVER}}", "%.2f" % over).replace("{{SUN_SOFFIT}}", "%.2f" % soffit).replace("{{SUN_HEAD}}", "%.2f" % head)
open(os.path.join(H, OUT), "w").write(s)
print(OUT, len(s))
