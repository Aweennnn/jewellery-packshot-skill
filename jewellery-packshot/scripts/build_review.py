"""Render review-manifest.json into one self-contained review.html.

Usage: python scripts/build_review.py MANIFEST.json OUTPUT/review.html [--replace]
Schema: references/review-manifest.md. Standard library only.
"""
import argparse
import html
import json
import math
import os
import sys
from pathlib import Path
from urllib.parse import quote

STATUS = {"QC-PASS": "pass", "REWORK": "rework", "BLOCKED": "blocked"}
TYPES = ("mounted", "loose")
METHODS = ("generative", "masked", "original-derived")
CHECK_KEYS = ("srgb", "layers", "after_visible", "pixels")
CUTOUT_CHECK_KEYS = ("mask_alpha", "halo_check")

# UI labels per language. Findings and region notes come from the manifest as written.
UI = {
    "zh": {
        "title": "精修质检", "inputs": "输入", "pass": "通过", "rework": "返工", "blocked": "无法处理",
        "mounted": "镶嵌首饰", "loose": "裸石",
        "generative": "生成式精修", "masked": "蒙版精修", "original-derived": "原图导出，未精修",
        "upscaled": "插值放大", "attempts": "尝试次数",
        "original": "原图", "after": "精修图", "transparent": "透明图",
        "checker": "棋盘格", "black": "黑", "white": "白",
        "review": "人工复核", "visual": "视觉检查", "nothing": "无待复核项",
        "file_checks": "文件检查", "size": "尺寸", "ok": "通过", "ko": "未通过", "unchecked": "未检查",
        "not_exported": "未导出", "files": "交付文件", "png": "PNG", "transparent_png": "透明 PNG",
        "psd": "PSD", "none": "无", "no_file": "无文件",
        "srgb": "sRGB 色彩配置", "layers": "图层 Original / After", "layers_cutout": "图层 Original / After / Cutout_Transparent",
        "after_visible": "默认显示 After", "pixels": "PNG 与 PSD 像素一致",
        "mask_alpha": "蒙版与透明通道一致", "halo_check": "透明图黑底白底无阴影无光晕",
    },
    "en": {
        "title": "Retouch QC", "inputs": "Inputs", "pass": "Pass", "rework": "Rework", "blocked": "Blocked",
        "mounted": "Mounted jewellery", "loose": "Loose stone",
        "generative": "Generative retouch", "masked": "Masked retouch",
        "original-derived": "Original export, not retouched",
        "upscaled": "Upscaled", "attempts": "Attempts",
        "original": "Original", "after": "Retouched", "transparent": "Transparent",
        "checker": "Checker", "black": "Black", "white": "White",
        "review": "Needs review", "visual": "Visual check", "nothing": "Nothing to review",
        "file_checks": "File checks", "size": "Size", "ok": "Pass", "ko": "Fail", "unchecked": "Not checked",
        "not_exported": "Not exported", "files": "Delivered files", "png": "PNG",
        "transparent_png": "Transparent PNG", "psd": "PSD", "none": "None", "no_file": "No file",
        "srgb": "sRGB profile", "layers": "Layers Original / After", "layers_cutout": "Layers Original / After / Cutout_Transparent",
        "after_visible": "After visible by default", "pixels": "PNG matches PSD pixels",
        "mask_alpha": "Mask matches PNG alpha", "halo_check": "No shadow or halo on black and white",
    },
    "fr": {
        "title": "Contrôle retouche", "inputs": "Entrées", "pass": "Validé", "rework": "À reprendre",
        "blocked": "Bloqué", "mounted": "Bijou", "loose": "Pierre non sertie",
        "generative": "Retouche générative", "masked": "Retouche par masque",
        "original-derived": "Export de l'original, non retouché",
        "upscaled": "Agrandissement interpolé", "attempts": "Tentatives",
        "original": "Original", "after": "Retouche", "transparent": "Détourage",
        "checker": "Damier", "black": "Noir", "white": "Blanc",
        "review": "À vérifier", "visual": "Contrôle visuel", "nothing": "Rien à vérifier",
        "file_checks": "Contrôle des fichiers", "size": "Dimensions", "ok": "Conforme", "ko": "Non conforme",
        "unchecked": "Non vérifié", "not_exported": "Non exporté", "files": "Fichiers livrés", "png": "PNG",
        "transparent_png": "PNG détouré", "psd": "PSD", "none": "Aucun", "no_file": "Aucun fichier",
        "srgb": "Profil sRGB", "layers": "Calques Original / After", "layers_cutout": "Calques Original / After / Cutout_Transparent",
        "after_visible": "After visible par défaut", "pixels": "PNG identique au PSD",
        "mask_alpha": "Masque identique à l'alpha du PNG", "halo_check": "Ni ombre ni halo sur noir et blanc",
    },
}


def ui_for(lang):
    """BCP-47 code -> label table; 'fr-CA' uses 'fr'; unknown languages fall back to English."""
    base = str(lang or "en").split("-")[0].lower()
    return (base if base in UI else "en"), UI.get(base, UI["en"])


CSS = """
:root{color-scheme:light dark;
--mauve-1:#fdfcfd;--mauve-2:#faf9fb;--mauve-3:#f2eff3;--mauve-4:#eae7ec;--mauve-5:#e3dfe6;--mauve-6:#dbd8e0;--mauve-7:#d0cdd7;--mauve-11:#65636d;--mauve-12:#211f26;
--grass-3:#e9f6e9;--grass-6:#b2ddb5;--grass-11:#2a7e3b;
--amber-3:#fff7c2;--amber-6:#f3d673;--amber-11:#ab6400;
--red-3:#feebec;--red-6:#fdbdbe;--red-9:#e5484d;--red-11:#ce2c31;
--white:#ffffff;--mauve-dark-1:#121113;--checker:#eae7ec;
--r-card:16px;--pad-card:8px;--r-img:8px;--r-chip:999px;
--s1:8px;--s2:16px;--s3:24px;--s4:32px;--s6:48px}
@media (prefers-color-scheme:dark){:root{
--mauve-1:#121113;--mauve-2:#1a191b;--mauve-3:#232225;--mauve-4:#2b292d;--mauve-5:#323035;--mauve-6:#3c393f;--mauve-7:#49474e;--mauve-11:#b5b2bc;--mauve-12:#eeeef0;
--grass-3:#1b2a1e;--grass-6:#2d5736;--grass-11:#71d083;
--amber-3:#302008;--amber-6:#5c3d05;--amber-11:#ffca16;
--red-3:#3b1219;--red-6:#72232d;--red-9:#e5484d;--red-11:#ff9592}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--mauve-1);color:var(--mauve-12);font:14px/1.5 -apple-system,"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC",sans-serif;-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.mono{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-size:13px;letter-spacing:-.01em}
.page{max-width:1336px;margin:0 auto;padding:var(--s6) var(--s4)}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:var(--s4);flex-wrap:wrap;padding-bottom:var(--s3);border-bottom:1px solid var(--mauve-6)}
h1{font-size:24px;line-height:32px;font-weight:600;letter-spacing:.02em}
.sub{display:flex;gap:var(--s2);color:var(--mauve-11);margin-top:var(--s1)}
.stats{display:grid;grid-template-columns:repeat(4,minmax(88px,auto));background:var(--mauve-2);border:1px solid var(--mauve-6);border-radius:var(--r-card)}
.stat{padding:var(--s2) var(--s3);display:flex;flex-direction:column;gap:4px}
.stat+.stat{border-left:1px solid var(--mauve-6)}
.stat dt{font-size:12px;line-height:16px;color:var(--mauve-11)}
.stat dd{font-size:28px;line-height:32px;font-weight:600;letter-spacing:-.02em}
.stat.pass dd{color:var(--grass-11)}.stat.rework dd{color:var(--amber-11)}.stat.blocked dd{color:var(--red-11)}
nav{display:flex;flex-wrap:wrap;gap:var(--s1);padding:var(--s3) 0}
nav a{display:inline-flex;align-items:center;gap:var(--s1);height:32px;padding:0 12px 0 10px;border:1px solid var(--mauve-6);border-radius:var(--r-chip);color:var(--mauve-12);text-decoration:none;background:var(--mauve-2)}
nav a:hover{border-color:var(--mauve-7);background:var(--mauve-3)}
.dot{width:8px;height:8px;border-radius:50%;flex:none}
.dot.pass{background:var(--grass-11)}.dot.rework{background:var(--amber-11)}.dot.blocked{background:var(--red-11)}
.items{display:flex;flex-direction:column;gap:var(--s3)}
.card{background:var(--mauve-2);border:1px solid var(--mauve-6);border-radius:var(--r-card);padding:var(--pad-card);scroll-margin-top:var(--s3)}
.card-head{display:flex;align-items:center;gap:var(--s1);padding:var(--s1) var(--s1) var(--s2);flex-wrap:wrap}
.card-head .mono{font-size:15px;font-weight:600;margin-right:var(--s1)}
.meta{margin-left:auto;display:flex;align-items:center;gap:var(--s2);color:var(--mauve-11);font-size:12px}
.meta b{color:var(--mauve-12);font-weight:600;font-size:13px;margin-left:4px}
.chip{display:inline-flex;align-items:center;height:24px;padding:0 10px;border-radius:var(--r-chip);font-size:12px;line-height:1;font-weight:500;white-space:nowrap;background:var(--mauve-3);color:var(--mauve-11);box-shadow:inset 0 0 0 1px var(--mauve-6);text-box:trim-both cap alphabetic}
.chip.pass{background:var(--grass-3);color:var(--grass-11);box-shadow:inset 0 0 0 1px var(--grass-6)}
.chip.rework{background:var(--amber-3);color:var(--amber-11);box-shadow:inset 0 0 0 1px var(--amber-6)}
.chip.blocked{background:var(--red-3);color:var(--red-11);box-shadow:inset 0 0 0 1px var(--red-6)}
.views{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--s1);align-items:stretch}
.views.with-cutout{grid-template-columns:repeat(3,minmax(0,1fr))}
figure{display:flex;flex-direction:column;gap:var(--s1)}
figcaption{display:flex;align-items:center;justify-content:space-between;height:24px;padding:0 var(--s1);font-size:12px;color:var(--mauve-11)}
.frame{position:relative;border-radius:var(--r-img);overflow:hidden;background:var(--white)}
.frame img{display:block;width:100%;height:auto}
.frame::after{content:"";position:absolute;inset:0;border-radius:inherit;box-shadow:inset 0 0 0 1px var(--mauve-6);pointer-events:none}
.frame.empty{flex:1;min-height:160px;display:grid;place-items:center;background:var(--mauve-3);color:var(--mauve-11);font-size:12px}
.frame.t-checker{background:repeating-conic-gradient(var(--checker) 0 25%,var(--white) 0 50%) 0 0/16px 16px}
.frame.t-black{background:var(--mauve-dark-1)}
.frame.t-white{background:var(--white)}
.seg{display:inline-flex;padding:2px;gap:2px;border-radius:var(--r-chip);background:var(--mauve-3);box-shadow:inset 0 0 0 1px var(--mauve-6)}
.seg button{all:unset;cursor:pointer;height:20px;padding:0 8px;border-radius:var(--r-chip);font-size:12px;line-height:20px;color:var(--mauve-11)}
.seg button[aria-pressed=true]{background:var(--mauve-1);color:var(--mauve-12);box-shadow:0 0 0 1px var(--mauve-7)}
.seg button:focus-visible{outline:2px solid var(--mauve-7);outline-offset:1px}
svg.marks{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
svg.marks ellipse,svg.marks polygon{fill:none;stroke:var(--red-9);stroke-width:2;vector-effect:non-scaling-stroke}
.pin{position:absolute;transform:translate(calc(-50% + 10px),calc(-50% - 10px));width:20px;height:20px;border-radius:50%;background:var(--red-9);color:var(--white);font-size:11px;font-weight:700;line-height:20px;text-align:center}
.notes{display:grid;grid-template-columns:2fr 1fr;gap:var(--s1);margin-top:var(--s1)}
.panel{background:var(--mauve-1);border-radius:var(--r-img);box-shadow:inset 0 0 0 1px var(--mauve-6);padding:var(--s2)}
.panel h3{font-size:12px;line-height:16px;font-weight:600;color:var(--mauve-11);margin-bottom:var(--s1);letter-spacing:.04em}
.panel h3+ol,.panel h3+ul{margin-top:0}
.panel section+section{margin-top:var(--s2);padding-top:var(--s2);border-top:1px solid var(--mauve-6)}
ol,ul{list-style:none;display:flex;flex-direction:column;gap:var(--s1)}
ol li{display:grid;grid-template-columns:20px 1fr;gap:var(--s1);align-items:start}
ol li .pin{position:static;transform:none}
ul.findings li{padding-left:var(--s2);position:relative}
ul.findings li::before{content:"";position:absolute;left:2px;top:9px;width:4px;height:4px;border-radius:50%;background:var(--mauve-11)}
dl.checks{display:grid;grid-template-columns:1fr auto;column-gap:var(--s2);row-gap:var(--s1);font-size:13px}
dl.checks dt{color:var(--mauve-11)}
dl.checks dd{text-align:right;font-weight:500}
dd.ok{color:var(--grass-11)}dd.ko{color:var(--red-11)}
.files a{color:var(--mauve-12);text-decoration:underline;text-decoration-color:var(--mauve-7);text-underline-offset:.3em;word-break:break-all}
.files a:hover{text-decoration-color:var(--mauve-12)}
.files ul{display:grid;grid-template-columns:max-content minmax(0,1fr);column-gap:var(--s2);row-gap:var(--s1);font-size:13px}
.files li{display:contents}
.files li span{color:var(--mauve-11)}
.none{color:var(--mauve-11)}
@media (max-width:900px){.views,.views.with-cutout{grid-template-columns:minmax(0,1fr)}.notes{grid-template-columns:minmax(0,1fr)}header>div,.stats{width:100%}.page{padding:var(--s4) var(--s2)}.stats{grid-template-columns:repeat(2,1fr)}.stat:nth-child(3){border-left:0}.stat:nth-child(n+3){border-top:1px solid var(--mauve-6)}.meta{margin-left:0;width:100%}}
@media print{:root{color-scheme:light}body{background:var(--white)}.page{padding:0;max-width:none}nav,.seg{display:none}.card{break-inside:avoid;page-break-inside:avoid}}
"""

JS = """
document.querySelectorAll('.seg').forEach(function(seg){
  var frame=document.getElementById(seg.dataset.target);
  seg.addEventListener('click',function(e){
    var b=e.target.closest('button'); if(!b) return;
    seg.querySelectorAll('button').forEach(function(x){x.setAttribute('aria-pressed',x===b)});
    frame.className='frame t-'+b.dataset.bg;
  });
});
"""


def fail(message):
    raise SystemExit(f"manifest error: {message}")


def unit(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        fail(f"{label} must be a number between 0 and 1, got {value!r}")
    return float(value)


def link(value, out_dir, label):
    """Return a path relative to review.html; the referenced file must exist."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must be a non-empty local file path or null")
    out_dir = Path(out_dir).resolve()
    path = Path(value)
    absolute = (path if path.is_absolute() else out_dir / path).resolve()
    if not absolute.is_file():
        fail(f"{label} not found: {absolute}")
    return Path(os.path.relpath(absolute, out_dir)).as_posix()


def validate(manifest, out_dir):
    if not isinstance(manifest, dict):
        fail("manifest must be an object")
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        fail("items must be a non-empty list")
    stems = set()
    for index, item in enumerate(items):
        where = f"items[{index}]"
        if not isinstance(item, dict):
            fail(f"{where} must be an object")
        stem = item.get("stem")
        if not isinstance(stem, str) or not stem.strip() or stem in stems:
            fail(f"{where}.stem missing or duplicated")
        stems.add(stem)
        if item.get("status") not in STATUS:
            fail(f"{where}.status must be one of {sorted(STATUS)}")
        if item.get("type", "mounted") not in TYPES:
            fail(f"{where}.type must be mounted or loose")
        if item.get("method", "generative") not in METHODS:
            fail(f"{where}.method must be one of {sorted(METHODS)}")
        for key in ("source", "after_png", "transparent_png", "psd"):
            item[key] = link(item.get(key), out_dir, f"{where}.{key}")
        if item["source"] is None:
            fail(f"{where}.source is required")
        findings = item.get("findings", [])
        if not isinstance(findings, list) or any(not isinstance(f, str) or not f.strip() for f in findings):
            fail(f"{where}.findings must be a list of non-empty strings")
        regions = item.get("regions", [])
        if not isinstance(regions, list):
            fail(f"{where}.regions must be a list")
        if regions and not item["after_png"]:
            fail(f"{where}.regions need after_png")
        for r_index, region in enumerate(regions):
            label = f"{where}.regions[{r_index}]"
            if not isinstance(region, dict):
                fail(f"{label} must be an object")
            if not isinstance(region.get("note"), str) or not region["note"].strip():
                fail(f"{label}.note is required")
            if "points" in region:
                points = region["points"]
                if not isinstance(points, list) or len(points) < 3 or any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in points):
                    fail(f"{label}.points needs at least 3 points")
                region["points"] = [(unit(x, label), unit(y, label)) for x, y in points]
                polygon = region["points"]
                area = sum(x * polygon[(n + 1) % len(polygon)][1] - y * polygon[(n + 1) % len(polygon)][0] for n, (x, y) in enumerate(polygon))
                if abs(area) < 1e-12:
                    fail(f"{label}.points must enclose a non-zero area")
            else:
                for key in ("x", "y", "rx", "ry"):
                    region[key] = unit(region.get(key), f"{label}.{key}")
                if region["rx"] <= 0 or region["ry"] <= 0:
                    fail(f"{label} ellipse radii must be positive")
        if item["status"] == "REWORK" and not regions:
            fail(f"{where}: REWORK needs at least one circled region")
        if item["status"] == "QC-PASS" and regions:
            fail(f"{where}: a circled region means human attention; QC-PASS may not carry regions")
        checks = item.get("file_checks")
        if checks is not None and not isinstance(checks, dict):
            fail(f"{where}.file_checks must be an object or null")
        if item["status"] == "QC-PASS":
            if item.get("method") == "original-derived":
                fail(f"{where}: original-derived is not a completed retouch and cannot be QC-PASS")
            for key in ("source", "after_png", "psd"):
                if not item[key]:
                    fail(f"{where}: QC-PASS needs {key}")
            required = CHECK_KEYS + (CUTOUT_CHECK_KEYS if item["transparent_png"] else ())
            for key in required:
                if not checks or checks.get(key) is not True:
                    fail(f"{where}: QC-PASS needs file_checks.{key} true")
        if item["status"] == "BLOCKED" and not findings:
            fail(f"{where}: BLOCKED needs a finding naming the missing capability")
    return items


def esc(value):
    return html.escape(str(value), quote=True)


def pin_position(region):
    if "points" in region:
        x, y = min(region["points"], key=lambda p: (p[1], -p[0]))
        return x, y
    return region["x"] + region["rx"] * 0.7071, region["y"] - region["ry"] * 0.7071


def image_frame(src, alt, t, extra="", frame_id=""):
    if not src:
        return f'<div class="frame empty">{t["no_file"]}</div>'
    ident = f' id="{frame_id}"' if frame_id else ""
    return (f'<div class="frame{extra}"{ident}><img src="{esc(quote(src, safe="/"))}" alt="{esc(alt)}">'
            "{marks}</div>")


def render_marks(regions):
    if not regions:
        return ""
    shapes, pins = [], []
    for number, region in enumerate(regions, 1):
        if "points" in region:
            points = " ".join(f"{x:.4f},{y:.4f}" for x, y in region["points"])
            shapes.append(f'<polygon points="{points}"/>')
        else:
            shapes.append(f'<ellipse cx="{region["x"]:.4f}" cy="{region["y"]:.4f}" '
                          f'rx="{region["rx"]:.4f}" ry="{region["ry"]:.4f}"/>')
        x, y = pin_position(region)
        pins.append(f'<span class="pin" style="left:{x * 100:.2f}%;top:{y * 100:.2f}%">{number}</span>')
    return ('<svg class="marks" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">'
            + "".join(shapes) + "</svg>" + "".join(pins))


def render_item(index, item, t):
    cls = STATUS[item["status"]]
    label = t[cls]
    stem = item["stem"]
    regions = item.get("regions") or []
    checks = item.get("file_checks")
    tags = [f'<span class="chip">{t[item.get("type", "mounted")]}</span>']
    method = item.get("method", "generative")
    if method != "generative":
        tags.append(f'<span class="chip{" rework" if method == "original-derived" else ""}">{t[method]}</span>')
    if checks and checks.get("upscaled"):
        tags.append(f'<span class="chip">{t["upscaled"]}</span>')
    attempts = item.get("attempts")
    meta = f'<span>{t["attempts"]}<b>{esc(attempts)}</b></span>' if attempts is not None else ""

    after = image_frame(item["after_png"], f"{stem} {t['after']}", t).replace("{marks}", render_marks(regions))
    before = image_frame(item["source"], f"{stem} {t['original']}", t).replace("{marks}", "")
    frame_id = f"t{index}"
    transparent = image_frame(item["transparent_png"], f"{stem} {t['transparent']}", t,
                              " t-checker", frame_id).replace("{marks}", "")
    seg = ""
    if item["transparent_png"]:
        seg = (f'<span class="seg" data-target="{frame_id}">'
               f'<button type="button" data-bg="checker" aria-pressed="true">{t["checker"]}</button>'
               f'<button type="button" data-bg="black" aria-pressed="false">{t["black"]}</button>'
               f'<button type="button" data-bg="white" aria-pressed="false">{t["white"]}</button></span>')

    transparent_figure = (
        f'<figure><figcaption><span>{t["transparent"]}</span>{seg}</figcaption>{transparent}</figure>'
        if item["transparent_png"] else ""
    )
    region_list = "".join(f'<li><span class="pin">{n}</span><span>{esc(r["note"])}</span></li>'
                          for n, r in enumerate(regions, 1))
    findings = "".join(f"<li>{esc(f)}</li>" for f in item.get("findings") or [])
    left = []
    if regions:
        left.append(f'<section><h3>{t["review"]} {len(regions)}</h3><ol>{region_list}</ol></section>')
    if findings:
        left.append(f'<section><h3>{t["visual"]}</h3><ul class="findings">{findings}</ul></section>')
    if not left:
        left.append(f'<section><h3>{t["visual"]}</h3><p class="none">{t["nothing"]}</p></section>')

    if checks:
        rows = [f'<dt>{t["size"]}</dt><dd class="mono">{esc(checks.get("size", ""))}</dd>']
        keys = CHECK_KEYS + (CUTOUT_CHECK_KEYS if item["transparent_png"] else ())
        for key in keys:
            value = checks.get(key)
            word = t["ok"] if value is True else t["unchecked"] if value is None else t["ko"]
            check_label = t["layers_cutout"] if key == "layers" and item["transparent_png"] else t[key]
            rows.append(f'<dt>{check_label}</dt><dd class="{"ok" if value is True else "ko"}">{word}</dd>')
        check_html = f'<dl class="checks">{"".join(rows)}</dl>'
    else:
        check_html = f'<p class="none">{t["not_exported"]}</p>'
    files = [(t[k], item[v]) for k, v in (("png", "after_png"), ("transparent_png", "transparent_png"),
                                          ("psd", "psd")) if item[v]]
    file_html = "".join(f'<li><span>{k}</span><a class="mono" href="{esc(quote(v, safe="/"))}">{esc(Path(v).name)}</a></li>'
                        for k, v in files) or f'<li class="none">{t["none"]}</li>'

    return f"""<article class="card" id="item-{index}">
<div class="card-head"><span class="mono">{esc(stem)}</span>{"".join(tags)}<span class="meta">{meta}<span class="chip {cls}">{label}</span></span></div>
<div class="views{" with-cutout" if item["transparent_png"] else ""}">
<figure><figcaption>{t["original"]}</figcaption>{before}</figure>
<figure><figcaption>{t["after"]}</figcaption>{after}</figure>
{transparent_figure}
</div>
<div class="notes">
<div class="panel">{"".join(left)}</div>
<div class="panel"><section><h3>{t["file_checks"]}</h3>{check_html}</section><section class="files"><h3>{t["files"]}</h3><ul>{file_html}</ul></section></div>
</div>
</article>"""


def render(manifest, items):
    lang, t = ui_for(manifest.get("lang"))
    counts = {key: sum(1 for i in items if i["status"] == key) for key in STATUS}
    batch = manifest.get("batch", "")
    date = manifest.get("date", "")
    stats = [("", t["inputs"], len(items))] + [(STATUS[k], t[STATUS[k]], counts[k]) for k in STATUS]
    stats_html = "".join(f'<div class="stat {c}"><dt>{l}</dt><dd>{n}</dd></div>' for c, l, n in stats)
    nav = ""
    if len(items) > 1:
        nav = "<nav>" + "".join(
            f'<a href="#item-{n}"><span class="dot {STATUS[i["status"]]}"></span>'
            f'<span class="mono">{esc(i["stem"])}</span></a>' for n, i in enumerate(items)) + "</nav>"
    cards = "\n".join(render_item(n, i, t) for n, i in enumerate(items))
    embedded = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t["title"]} {esc(batch)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
<header><div><h1>{t["title"]}</h1><div class="sub"><span class="mono">{esc(batch)}</span><span>{esc(date)}</span></div></div>
<dl class="stats">{stats_html}</dl></header>
{nav}
<main class="items">
{cards}
</main>
</div>
<script type="application/json" id="manifest">{embedded}</script>
<script>{JS}</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path, help="OUTPUT/review.html")
    parser.add_argument("--replace", action="store_true", help="replace a review.html this job created")
    args = parser.parse_args()
    if args.output.exists() and not args.replace:
        raise FileExistsError(args.output)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    out_dir = args.output.resolve().parent
    items = validate(manifest, out_dir)
    page = render(manifest, items)
    args.output.write_text(page, encoding="utf-8")
    counts = {key: sum(1 for i in items if i["status"] == key) for key in STATUS}
    print(f"PASS: {args.output} ({len(items)} items, " + ", ".join(f"{k} {v}" for k, v in counts.items())
          + f", {sum(len(i.get('regions') or []) for i in items)} regions)")


if __name__ == "__main__":
    sys.exit(main())
