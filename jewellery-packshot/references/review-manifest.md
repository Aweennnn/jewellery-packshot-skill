# Review manifest

The final images must be shown in the conversation with their status and any
unresolved problem. `review.html` is a supplementary comparison and inspection
page, not a substitute for showing the selected results.

Write `WORK/review-manifest.json`, then run:

```bash
python scripts/build_review.py WORK/review-manifest.json OUTPUT/review.html
```

The builder checks the manifest and file references, embeds a compact copy inside
`review.html`, and refuses an existing page unless `--replace` is given. Use
`--replace` only for a page this job created. Keep the manifest in the temporary
work directory and clear it with the rest of temporary work after verified delivery.

## Default: white PNG and two-layer PSD

A transparent PNG is optional and is produced only when the user requests it.
Omit `transparent_png` or set it to `null` for the normal white-background delivery.
The page then shows only Original and After, and the file-check panel describes
`Original / After` layers. There is no empty transparent panel or irrelevant halo
or alpha-mask check.

```json
{
  "lang": "en",
  "batch": "before",
  "date": "2026-10-29",
  "items": [
    {
      "stem": "1257",
      "type": "mounted",
      "source": "/Users/me/Jewellery/before/1257.jpg",
      "after_png": "PNG/1257-after-2k.png",
      "psd": "PSD/1257-after-2k.psd",
      "status": "QC-PASS",
      "method": "generative",
      "attempts": 1,
      "findings": ["Outline, settings and side-stone count checked against the original; no change in material or structure."],
      "regions": [],
      "file_checks": {
        "size": "1536x2048",
        "srgb": true,
        "layers": true,
        "after_visible": true,
        "pixels": true,
        "upscaled": false
      }
    }
  ]
}
```

## Fields and status rules

| Field | Rule |
| --- | --- |
| `lang` | User's language as a BCP-47 code; default `en`. Labels are provided for `zh`, `en`, and `fr`; region subtags use the base language and other languages fall back to English. Write findings and region notes in the user's language. |
| `batch`, `date` | Input folder name and date in `YYYY-MM-DD` format. |
| `stem` | Original filename stem, non-empty and unique within the batch. |
| `type` | `mounted` for jewellery, `loose` for a loose stone or parcel. |
| `source` | Original photo, required. Absolute or relative to `review.html`; emitted links are relative and URL-encoded for offline use. |
| `after_png`, `psd` | Selected white PNG and PSD, relative to `review.html` or absolute paths. Required for QC-PASS; `null` when not exported. Every listed path must point to a file. |
| `transparent_png` | Optional requested transparent cutout; omit or use `null` by default. Every listed file must exist. When present, the page adds the transparent panel, its background controls, and cutout checks. |
| `status` | Exactly `QC-PASS`, `REWORK`, or `BLOCKED`. |
| `method` | `generative`, `masked` for a pixel-preserving fallback, or `original-derived` for an unretouched original-based export. `original-derived` cannot be QC-PASS. |
| `attempts` | Cumulative total of generative edits and targeted fallback passes for this item. Never reset it on a follow-up. |
| `attempt_history` | Optional audit trail, e.g. `[{"scope":"initial","request":"white-background retouch","generative":1,"fallback":0}]`. Add a descriptive scope for a new user-requested adjustment; keep earlier entries. An unresolved repeated defect retains its earlier retry count. `attempts` stays the cumulative total across scopes. |
| `findings` | List of concrete, non-empty strings. BLOCKED requires an explanation naming the missing capability. |
| `regions` | List of localized zones needing attention on After. REWORK requires at least one. QC-PASS must have none. |
| `file_checks` | Copy the exporter's `CHECKS {...}` result, or `null` when not exported. QC-PASS requires a check object with `srgb`, `layers`, `after_visible`, and `pixels` all exactly `true`. File checks alone do not certify visual fidelity. |

QC-PASS means the selected delivery passed the agent's original-photo comparison
and the required file checks. It does not mean pixel identity, measured stone
size, owner approval, or Photoshop compatibility. State whether Photoshop itself
was used. REWORK means a specific visual defect remains; export the best available
selected image and locate each unresolved defect. BLOCKED means a required
capability is unavailable; explain it and continue unaffected items.

## Optional requested transparent cutout

When `transparent_png` is present, add the exporter's `mask_alpha`,
`decontaminated_px`, and `soft_alpha_ratio` results. After viewing the transparent
PNG at 100% on black and white, set `halo_check` to `true` only when no shadow or
halo remains; otherwise set it to `false`. Use `null` only before inspection.
For an item with a transparent PNG, QC-PASS additionally requires `mask_alpha` and
`halo_check` both exactly `true`. The PSD layer label then includes the third
`Cutout_Transparent` layer.

A failed requested cutout makes the item REWORK, even when the white PNG is usable.
Identify which output has the defect in its note. When no cutout was requested,
there is no cutout work or halo gate to pass.

## Localized review regions

Coordinates are normalized to After, from 0 to 1, with origin at top left. Use an
ellipse (`x`, `y`, positive `rx`, positive `ry`) or a polygon (`points`, at least
three non-collinear pairs). Numbers must be finite and cannot be booleans. Each
region needs a concrete non-empty `note` naming what differs. Place tight marks on
the actual suspect area; a whole-image warning does not locate a defect.

```json
{
  "status": "REWORK",
  "regions": [
    {"x": 0.23, "y": 0.53, "rx": 0.04, "ry": 0.03,
     "note": "Left pearl outline is rounder than in the original"},
    {"points": [[0.50, 0.57], [0.59, 0.55], [0.61, 0.64], [0.52, 0.68]],
     "note": "Lower-right openwork filigree runs differently from the original"}
  ]
}
```

Open the built page to confirm every mark lands on the named area. Use plain,
precise language for a jeweller or retoucher. Keep filenames and format names
unchanged; describe stones by photographed colour and cut rather than species.
