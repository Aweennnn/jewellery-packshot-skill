# Transparent cutout and QC

Use this reference only when the user explicitly requests a transparent cutout.
Read it before creating or editing that mask. The default skill delivery has no
transparent PNG or cutout mask. The white PNG keeps its contact shadow.

**The transparent cutout is product pixels only:**
- no contact shadow, no soft shadow, no white or grey fringe;
- alpha 0 on background and shadow, 255 inside the product;
- partial alpha only on the 1 to 2 px antialiased edge and on genuinely translucent
  parts (stone windows, thin chain gaps), never on a shadow;
- edges decontaminated: no light halo on black, no dark halo on white (the exporter
  un-mixes white from semi-transparent edge pixels; a mask that includes shadow still
  shows a grey band, so the mask itself must exclude it).

Never remove real dark reflections, prongs, posts, backs, clasps, girdles or culets
as "shadow".

## Source

Mask the exact selected After at its own orientation and pixel grid. RGB stays
untouched: no generative redraw, warping, recentering or idealized outline. Compare
After with the original photo first; if After already changed the piece, a good
mask cannot repair it. Mark REWORK and return to a faithful source.

Never reuse a mask from another image, version or product. A similar canvas or
layer name is not registration evidence.

## Shape

Build the mask locally from the After pixels (background-distance or colour
segmentation), then correct it by tracing the photographed boundary.

- Brightness thresholds confuse pearl and stone highlights with white background
  and keep gray or gold-tinted shadow. Separate shadow by colour as well: shadow is
  low-saturation grey, metal and coloured stones are saturated. Pearls, colourless
  stones and white metal are also low-saturation, so trace them from the source and
  never let a saturation rule cut them. Never accept a threshold-only mask without
  source comparison and correction.
- Shrink the product edge by 1 to 2 px and feather about 1 px, so no background or
  shadow colour survives in the edge.
- Keep complete pearl and stone silhouettes and their opaque highlights. Shape comes
  from the photographed edge: no imposed circles or ellipses, no sparse-point or
  straight-segment outlines.
- Check fine metal, settings, clasps, ear posts and chains on their own. Broad
  erosion shortens pins and removes metal; blurring a shadow does not remove it.
- Classify every internal opening from the photo: real filigree, ring and chain
  openings are transparent; stones and enclosed reflections stay opaque. Never
  blanket-fill holes or clear every neutral pixel inside a stone.
- Loose stones: the whole outline including girdle and culet stays opaque; a light
  or colourless stone's table and windows are not background.
- Narrow antialiasing at the boundary only. Edge colour decontamination changes RGB
  and must be reported as a retouch, not as unchanged RGB.

## Required QC

1. Compare unmasked After and cutout at identical size and position, then against the
   original photo: outline, proportions, settings, stone count and shape, posts,
   clasps. A wrong alpha changes apparent geometry even when RGB is identical.
2. Inspect the whole piece on black, medium grey and white (`export_2k.py --qc-dir`
   writes this sheet to temporary work), plus at least 200% crops of pearl rims,
   stones, fine metal, openings and former shadow contacts. After any fix, recheck
   the whole piece.
3. Halo check: open the transparent PNG at 100% on black AND on white, around the
   whole outline and every former shadow contact. Reject if any shadow, grey band,
   light halo (on black) or dark halo (on white) is visible. Record the result as
   `file_checks.halo_check` (`true` or `false`) in the manifest; the exporter leaves it
   `null`, and QC-PASS requires `true`.
4. The exporter verifies sizes, layer order, opaque-pixel RGB equality and mask equals
   PNG alpha, and reports `soft_alpha_ratio` (semi-transparent share of visible
   pixels). A high ratio warns of shadow in the mask; thin chains also raise it, so it
   is a hint, not a verdict. Passing file checks do not prove a correct contour.
5. Any changed shape, opaque real opening, missing pearl or stone edge, clipped metal,
   residual shadow or halo is REWORK: circle it in review.html.

## Lessons kept

| Case | Failure | Check |
| --- | --- | --- |
| Filigree pendant | Old mask left white background inside openings | Every real opening on black and gray |
| Pearl earrings | Threshold erased pearl rims and highlights | Opaque interiors against the source silhouette |
| Ring | Grey shadow survived; blur only softened it | Outer and contact edges on three backgrounds |
| Pendant sample (Oct 29) | Threshold mask kept the contact shadow and a pale halo on black | Saturation-aware mask, 1 px shrink, edge un-mixing, halo check |
| Pearl pendant | Hand-drawn straight contour changed pearl, metal and pin | Same-scale whole-piece comparison plus 200% edges |
