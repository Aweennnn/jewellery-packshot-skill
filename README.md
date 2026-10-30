# Jewellery packshot skill for Codex

A Codex skill that turns a folder of jewellery and loose-stone photos into clean
white-background product shots. It retouches each photo with Codex's built-in image
editor, checks every result against the original, and saves:

```text
after/
├── PNG/<name>-after-2k.png   one 2K white-background PNG per photo
├── PSD/<name>-after-2k.psd   two editable layers: Original and After
└── review.html               side-by-side check page for the whole batch
```

Every result is also shown in the chat, so you can ask for small changes photo by photo.

## What it is careful about

- **The piece stays the piece.** The skill records each design's visible features
  before editing (outline, prongs, stone count, filigree, material colour) and rejects
  any result that changes them. Loose stones keep their cut, facets, colour and
  inclusions; no added fire or sparkle.
- **Shooting aids are removed.** Fixing glue, putty, wax, tape, tweezers, clips and
  stands, including at the contact points.
- **Nothing is called done that isn't.** Each photo ends as pass, rework or blocked,
  and the review page circles anything still in doubt.
- **Your language.** The review page and findings follow the language you work in.
  Labels exist for English, Chinese and French; other languages get English labels.
- **A transparent cutout is optional,** made only when you ask for it.

## Requirements

- Codex with access to local files and its built-in
  image editing tool.
- [uv](https://docs.astral.sh/uv/) to run the export script (it fetches Pillow, NumPy
  and psd-tools on the fly).

## Install

Copy the `jewellery-packshot` folder into your Codex skills folder:

```sh
git clone https://github.com/Aweennnn/jewellery-packshot-skill.git
cp -R jewellery-packshot-skill/jewellery-packshot ~/.codex/skills/
```

Or give Codex the folder path and ask: *"Install the jewellery-packshot skill from
this folder into my Codex skills directory. Don't overwrite an existing skill with
the same name."*

## Use

Put the original photos in a `before` folder, then ask Codex:

> Use the jewellery-packshot skill on `/path/to/before` and save the results in `/path/to/after`.

## Tests

```sh
cd jewellery-packshot/scripts
python3 test_review.py
uv run --with pillow --with numpy --with psd-tools python test_export_2k.py
```

## About

Made by [Ykela](https://ykela.com). For Photoshop users,
Ykela also makes Jewelry Éclat, a plugin for white-background shots, model try-on
images and scenes.

Released under the [MIT License](LICENSE).
