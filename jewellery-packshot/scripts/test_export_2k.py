"""Tests for export_2k.py and build_review.py.

Run from the skill folder:
  uv run --with pillow --with psd-tools python scripts/test_export_2k.py
(pytest also collects the test_* functions.)
"""
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageCms, ImageDraw
from psd_tools import PSDImage

HERE = Path(__file__).parent
EXPORT = HERE / "export_2k.py"
REVIEW = HERE / "build_review.py"
MIDDLE_DOT = chr(0xB7)


def is_srgb(image):
    """ICC bytes carry a creation timestamp, so compare the profile description."""
    profile = ImageCms.ImageCmsProfile(io.BytesIO(image.info["icc_profile"]))
    return "sRGB" in ImageCms.getProfileDescription(profile)


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True)


def make_inputs(root):
    Image.new("RGB", (8, 10), "white").save(root / "before.png")
    after = Image.new("RGB", (20, 20), "white")
    draw = ImageDraw.Draw(after)
    draw.ellipse((2, 2, 7, 7), fill=(245, 230, 210))  # pearl
    draw.rectangle((15, 8, 17, 10), fill=(220, 170, 30))  # gold pin
    after.save(root / "after.png")
    mask = Image.new("L", (20, 20), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((1, 1, 18, 18), fill=255)
    draw.ellipse((7, 7, 12, 12), fill=0)  # real interior opening
    mask.save(root / "mask.png")


def export(root, out, mask="mask.png", *extra):
    return run(EXPORT, "--before", root / "before.png", "--after", root / "after.png",
               "--mask", root / mask, "--output-dir", out, "--stem", "item", *extra)


def test_export():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        make_inputs(root)
        out = root / "OUTPUT"
        result = export(root, out, "mask.png", "--split-formats", "--qc-dir", root / "work" / "qc")
        assert result.returncode == 0, result.stderr
        assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == [
            "PNG/item-after-2k.png", "PNG/item-transparent-2k.png", "PSD/item-after-2k.psd"]
        assert (root / "work" / "qc" / "item-qc-panels.png").exists()
        checks = json.loads(next(l for l in result.stdout.splitlines() if l.startswith("CHECKS "))[7:])
        assert {k: checks[k] for k in ("size", "srgb", "layers", "after_visible", "pixels", "mask_alpha",
                                       "upscaled", "halo_check")} == {
            "size": "2048x2048", "srgb": True, "layers": True, "after_visible": True,
            "pixels": True, "mask_alpha": True, "upscaled": True, "halo_check": None}
        assert checks["decontaminated_px"] > 0 and 0 < checks["soft_alpha_ratio"] < 1
        white = Image.open(out / "PNG/item-after-2k.png")
        cutout = Image.open(out / "PNG/item-transparent-2k.png")
        assert white.size == cutout.size == (2048, 2048)
        assert is_srgb(white) and is_srgb(cutout)
        assert cutout.mode == "RGBA"
        opaque = [(x, y) for x in range(0, 2048, 64) for y in range(0, 2048, 64) if cutout.getpixel((x, y))[3] == 255]
        assert opaque and all(cutout.getpixel(p)[:3] == white.getpixel(p) for p in opaque)
        assert cutout.getpixel((460, 460))[3] == 255  # pearl opaque
        assert cutout.getpixel((1689, 972))[3] == 255  # gold pin opaque
        assert cutout.getpixel((1024, 1024))[3] == 0  # opening stays transparent
        assert cutout.getpixel((5, 5))[3] == 0  # background transparent
        psd = PSDImage.open(out / "PSD/item-after-2k.psd")
        assert [layer.name for layer in psd] == ["Original", "After", "Cutout_Transparent"]
        assert psd[1].visible and not psd[2].visible
        assert psd[2].topil().convert("RGB").tobytes() == cutout.convert("RGB").tobytes()
        assert psd[1].topil().convert("RGB").tobytes() == white.convert("RGB").tobytes()
        # edge decontamination: a 50% gold-over-white pixel at alpha 128 un-mixes back to gold
        gold = (220, 170, 30)
        mixed = Image.new("RGB", (4, 4), "white")
        mixed.putpixel((1, 1), tuple(round((g + 255) / 2) for g in gold))
        soft = Image.new("L", (4, 4), 0)
        soft.putpixel((1, 1), 128)
        soft.putpixel((2, 2), 255)
        sys.path.insert(0, str(HERE))
        from export_2k import decontaminate
        rgba, count = decontaminate(mixed, soft)
        assert count == 1 and all(abs(a - b) <= 2 for a, b in zip(rgba.getpixel((1, 1))[:3], gold))
        assert rgba.getpixel((2, 2)) == (255, 255, 255, 255)
        assert psd[2].has_mask()
        assert psd[2].mask.topil(layer_sized=True).convert("L").tobytes() == cutout.getchannel("A").tobytes()

        # flat layout without --split-formats
        flat = export(root, root / "flat")
        assert flat.returncode == 0, flat.stderr
        assert (root / "flat" / "item-transparent-2k.png").exists()

        # rejections: collision, wrong size, opaque, empty, no full range, RGB mask, qc inside output
        assert export(root, out, "mask.png", "--split-formats").returncode != 0
        Image.new("L", (19, 20), 0).save(root / "bad-size.png")
        Image.new("L", (20, 20), 255).save(root / "opaque.png")
        Image.new("L", (20, 20), 0).save(root / "empty.png")
        Image.new("L", (20, 20), 128).save(root / "flat-gray.png")
        Image.new("RGB", (20, 20), "white").save(root / "rgb.png")
        for name in ("bad-size.png", "opaque.png", "empty.png", "flat-gray.png", "rgb.png"):
            assert export(root, root / name.replace(".png", ""), name).returncode != 0, name
        assert export(root, root / "q", "mask.png", "--qc-dir", root / "q" / "qc").returncode != 0



def test_default_without_transparency():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        make_inputs(root)
        out = root / 'default'
        result = run(EXPORT, '--before', root / 'before.png', '--after', root / 'after.png',
                     '--output-dir', out, '--stem', 'item', '--split-formats',
                     '--qc-dir', root / 'qc')
        assert result.returncode == 0, result.stderr
        assert sorted(p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()) == [
            'PNG/item-after-2k.png', 'PSD/item-after-2k.psd']
        checks = json.loads(next(l[7:] for l in result.stdout.splitlines() if l.startswith('CHECKS ')))
        assert checks['transparent_requested'] is False
        assert 'halo_check' not in checks and 'mask_alpha' not in checks
        white = Image.open(out / 'PNG/item-after-2k.png')
        psd = PSDImage.open(out / 'PSD/item-after-2k.psd')
        assert white.mode == 'RGB' and is_srgb(white)
        assert [l.name for l in psd] == ['Original', 'After']
        assert psd[1].visible
        assert psd[1].topil().convert('RGB').tobytes() == white.tobytes()
        assert (root / 'qc/item-qc-panels.png').exists()
        # Rerun is a collision, never a silent replacement.
        collision = run(EXPORT, '--before', root / 'before.png', '--after', root / 'after.png',
                        '--output-dir', out, '--stem', 'item', '--split-formats')
        assert collision.returncode != 0
        traversal = run(EXPORT, '--before', root / 'before.png', '--after', root / 'after.png',
                        '--output-dir', root / 'unsafe', '--stem', '../escape')
        assert traversal.returncode != 0 and not (root / 'unsafe').exists()


if __name__ == '__main__':
    test_default_without_transparency()
    print('PASS default: white PNG, two-layer PSD, pixel equality, no transparent artifacts, collisions')
    test_export()
    print('PASS optional cutout: mask opt-in, three layers, alpha registration, edge un-mixing, rejections')
