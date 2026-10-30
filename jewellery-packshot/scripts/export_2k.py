"""Export a selected white retouch as a 2K PNG and two-layer PSD.

Original and After are editable raster layers. Only explicit --mask adds a transparent
PNG and hidden Cutout_Transparent layer. This packager never retouches or approves
an image. It refuses existing files and reopens every output for format checks.
"""
import argparse
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageOps
from psd_tools import PSDImage
from psd_tools.constants import Resource
from psd_tools.psd.image_resources import ImageResource

LAYERS = ["Original", "After"]
SOFT_ALPHA_WARN = 0.08  # hint only: a soft shadow left in the mask shows up as a wide semi-transparent band


def load_rgb(path):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        profile = source.info.get("icc_profile")
        if profile:
            image = ImageCms.profileToProfile(
                image, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                ImageCms.createProfile("sRGB"), outputMode="RGB",
            )
        return image.convert("RGB")


def load_mask(path):
    with Image.open(path) as source:
        if source.mode != "L":
            raise SystemExit("--mask must be an 8-bit grayscale (L) image")
        return ImageOps.exif_transpose(source).copy()


def decontaminate(after, mask):
    """Cutout RGBA: opaque pixels keep After RGB; edge pixels (0<alpha<255) are un-mixed
    from the white background, C = (I - (1 - a) * 255) / a, so no light halo shows on black."""
    rgb = np.asarray(after, dtype=np.float32)
    a = np.asarray(mask, dtype=np.float32)[..., None] / 255.0
    edge = (a > 0) & (a < 1)
    unmixed = np.clip((rgb - (1.0 - a) * 255.0) / np.maximum(a, 1e-3), 0, 255)
    out = np.where(edge, np.rint(unmixed), rgb).astype(np.uint8)
    rgba = np.dstack([out, np.asarray(mask, dtype=np.uint8)])
    return Image.fromarray(rgba, "RGBA"), int(edge[..., 0].sum())


def check(condition, message):
    if not condition:
        raise SystemExit(f"VERIFY FAILED: {message}")


def qc_panels(before, after, cutout):
    """Internal inspection sheet: original, After, cutout on black, gray and white."""
    panels = [before, after] + ([
        Image.alpha_composite(Image.new("RGBA", after.size, bg), cutout).convert("RGB")
        for bg in ("black", "#808080", "white")
    ] if cutout is not None else [])
    labels = ["ORIGINAL (fitted, not registered)", "AFTER", "CUTOUT black", "CUTOUT gray", "CUTOUT white"]
    sheet = Image.new("RGB", (after.width * len(panels), after.height + 28), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, panel) in enumerate(zip(labels, panels)):
        sheet.paste(panel, (index * after.width, 28))
        draw.text((index * after.width + 4, 6), label, fill="black")
    return sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path, help="original camera photo")
    parser.add_argument("--after", required=True, type=Path, help="selected white-background result")
    parser.add_argument("--mask", type=Path,
                        help="explicit opt-in to transparent PNG and masked third PSD layer; reviewed L mask")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--stem", required=True)
    parser.add_argument("--split-formats", action="store_true",
                        help="write PNGs to OUTPUT/PNG/ and the PSD to OUTPUT/PSD/")
    parser.add_argument("--portrait-3x4", action="store_true",
                        help="normalize a near-3:4 portrait input to exactly 1536x2048")
    parser.add_argument("--qc-dir", type=Path,
                        help="optional internal panel sheet (black/gray/white); must be outside --output-dir")
    args = parser.parse_args()
    if not args.stem or Path(args.stem).name != args.stem or args.stem in (".", ".."):
        parser.error("stem must be a filename, not a path")

    png_dir = args.output_dir / "PNG" if args.split_formats else args.output_dir
    psd_dir = args.output_dir / "PSD" if args.split_formats else args.output_dir
    after_png = png_dir / f"{args.stem}-after-2k.png"
    transparent_png = png_dir / f"{args.stem}-transparent-2k.png"
    psd_path = psd_dir / f"{args.stem}-after-2k.psd"
    outputs = [after_png, psd_path]
    if args.mask:
        outputs.append(transparent_png)
    layers = LAYERS + (["Cutout_Transparent"] if args.mask else [])
    qc_png = None
    if args.qc_dir:
        out_root = args.output_dir.resolve()
        qc_root = args.qc_dir.resolve()
        if qc_root == out_root or out_root in qc_root.parents:
            parser.error("--qc-dir must be outside --output-dir")
        qc_png = args.qc_dir / f"{args.stem}-qc-panels.png"
        outputs.append(qc_png)
    for path in outputs:
        if path.exists():
            raise FileExistsError(path)

    after = load_rgb(args.after)
    mask = load_mask(args.mask) if args.mask else None
    source_size = after.size
    if mask is not None and mask.size != source_size:
        parser.error("--mask dimensions must match the EXIF-oriented --after dimensions")
    if mask is not None and mask.getextrema() != (0, 255):
        parser.error("--mask must contain fully transparent (0) and fully opaque (255) pixels")
    if args.portrait_3x4:
        if abs(after.width / after.height - 3 / 4) > 0.02:
            parser.error("--portrait-3x4 requires a near-3:4 portrait input")
        size = (1536, 2048)
        after = ImageOps.fit(after, size, Image.Resampling.LANCZOS)
        if mask is not None:
            mask = ImageOps.fit(mask, size, Image.Resampling.BILINEAR)
    else:
        size = tuple(max(1, round(n * 2048 / max(source_size))) for n in source_size)
        after = after.resize(size, Image.Resampling.LANCZOS)
        # Bilinear keeps transparent openings free of Lanczos ringing; geometry matches After.
        if mask is not None:
            mask = mask.resize(size, Image.Resampling.BILINEAR)
    cutout, decontaminated = decontaminate(after, mask) if mask is not None else (None, 0)
    original = ImageOps.contain(load_rgb(args.before), size, Image.Resampling.LANCZOS)
    before = Image.new("RGB", size, "white")
    before.paste(original, ((size[0] - original.width) // 2, (size[1] - original.height) // 2))

    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    psd = PSDImage.new("RGB", size, color=(255, 255, 255))
    psd.create_pixel_layer(before, name=LAYERS[0])
    psd.create_pixel_layer(after, name=LAYERS[1])
    if cutout is not None:
        cutout_rgb = cutout.convert("RGB")
        cutout_layer = psd.create_pixel_layer(cutout_rgb, name=layers[2])
        cutout_layer.create_mask(mask)
        cutout_layer.visible = False
    psd.image_resources[Resource.ICC_PROFILE] = ImageResource(key=Resource.ICC_PROFILE, data=profile)

    png_dir.mkdir(parents=True, exist_ok=True)
    psd_dir.mkdir(parents=True, exist_ok=True)
    with after_png.open("xb") as output:
        after.save(output, format="PNG", icc_profile=profile)
    if cutout is not None:
        with transparent_png.open("xb") as output:
            cutout.save(output, format="PNG", icc_profile=profile)
    with psd_path.open("xb") as output:
        psd.save(output)
    if qc_png:
        qc_png.parent.mkdir(parents=True, exist_ok=True)
        with qc_png.open("xb") as output:
            qc_panels(before, after, cutout).save(output, format="PNG")

    reopened = PSDImage.open(psd_path)
    check(reopened.size == size, f"PSD size {reopened.size} != {size}")
    check(max(size) == 2048, f"long edge {max(size)} != 2048")
    check(reopened.image_resources.get_data(Resource.ICC_PROFILE) == profile, "PSD lacks sRGB profile")
    check([layer.name for layer in reopened] == layers, f"PSD layers {[l.name for l in reopened]}")
    check(reopened[0].visible and reopened[1].visible, "Original and After must be visible")
    check(reopened[0].topil().convert("RGB").tobytes() == before.tobytes(), "Original layer pixels")
    check(reopened[1].topil().convert("RGB").tobytes() == after.tobytes(), "After layer pixels")
    if cutout is not None:
        check(not reopened[2].visible, "Cutout_Transparent must be hidden")
        check(reopened[2].topil().convert("RGB").tobytes() == cutout_rgb.tobytes(), "Cutout layer RGB")
        check(reopened[2].has_mask(), "Cutout_Transparent has no raster mask")
        psd_mask = reopened[2].mask.topil(layer_sized=True).convert("L")
    with Image.open(after_png) as exported:
        check(exported.size == size, "white PNG size")
        check(exported.info.get("icc_profile") == profile, "white PNG lacks sRGB profile")
        check(exported.convert("RGB").tobytes() == after.tobytes(), "white PNG != PSD After")
    soft_ratio = None
    if cutout is not None:
        with Image.open(transparent_png) as exported:
            check(exported.mode == "RGBA" and exported.size == size, "transparent PNG mode/size")
            check(exported.info.get("icc_profile") == profile, "transparent PNG lacks sRGB profile")
            reopened_rgba = np.asarray(exported.convert("RGBA"))
            check(exported.getchannel("A").tobytes() == psd_mask.tobytes(), "PSD mask != transparent PNG alpha")
        opaque = reopened_rgba[..., 3] == 255
        check(np.array_equal(reopened_rgba[..., :3][opaque], np.asarray(after)[opaque]),
              "transparent PNG opaque pixels != After")
        check(np.array_equal(reopened_rgba[..., :3], np.asarray(cutout_rgb)), "transparent PNG RGB != PSD cutout")
    
        alpha = reopened_rgba[..., 3]
        soft = int(((alpha > 0) & (alpha < 255)).sum())
        soft_ratio = round(soft / max(1, int((alpha > 0).sum())), 4)
    checks = {
        "size": f"{size[0]}x{size[1]}", "srgb": True, "layers": True, "after_visible": True,
        "pixels": True, "upscaled": max(source_size) < 2048,
        "transparent_requested": mask is not None,
    }
    if cutout is not None:
        checks.update(mask_alpha=True, decontaminated_px=decontaminated,
                      soft_alpha_ratio=soft_ratio, halo_check=None)
    print(f"FORMAT-CHECKS-PASS: {source_size[0]}x{source_size[1]} -> {size[0]}x{size[1]}; files reopened and verified; "
          "visual QC is separate")
    if soft_ratio is not None and soft_ratio > SOFT_ALPHA_WARN:
        print(f"WARNING: {soft_ratio:.1%} of visible cutout pixels are semi-transparent; "
              "a soft shadow is probably inside the mask")
    print("CHECKS " + json.dumps(checks))
    for path in outputs:
        print(path)


if __name__ == "__main__":
    main()
