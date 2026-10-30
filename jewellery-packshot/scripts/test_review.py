"""Focused review-contract tests; standard library, no image generation or network."""
import base64
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import build_review as review

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lxoAAAAASUVORK5CYII=')


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'delivery'
        self.out.mkdir()
        self.source = Path(self.temp.name) / 'original #1.png'
        self.source.write_bytes(PNG)
        for name in ('after.png', 'transparent.png'):
            (self.out / name).write_bytes(PNG)
        # The builder checks file references and exporter evidence, not PSD decoding.
        (self.out / 'after.psd').write_bytes(b'PSD fixture; exporter tested separately')
        self.item = dict(stem='photo', source=str(self.source), after_png='after.png',
                         psd='after.psd', status='QC-PASS', method='masked',
                         findings=['Compared against original.'], regions=[],
                         file_checks=dict(size='1x1', srgb=True, layers=True,
                                          after_visible=True, pixels=True))

    def manifest(self, item=None, **kwargs):
        return dict(lang='en', batch='A · B', items=[copy.deepcopy(item or self.item)], **kwargs)

    def page(self, manifest):
        items = review.validate(manifest, self.out)
        return review.render(manifest, items)

    def rejects(self, item):
        with self.assertRaises(SystemExit):
            review.validate(self.manifest(item), self.out)

    def test_default_pass_has_two_views_and_no_cutout_checks(self):
        page = self.page(self.manifest())
        self.assertEqual(page.count('<figure>'), 2)
        self.assertIn('<div class="views">', page)
        self.assertNotIn('<div class="views with-cutout">', page)
        self.assertNotIn('Mask matches PNG alpha', page)
        self.assertNotIn('No shadow or halo on black and white', page)
        self.assertNotIn('Layers Original / After / Cutout_Transparent', page)
        self.assertIn('Layers Original / After', page)
        self.assertNotIn('>Transparent PNG<', page)
        self.assertNotIn('class="frame empty"', page)
        self.assertIn('../original%20%231.png', page)
        self.assertIn('A · B', page)

    def test_cutout_needs_mask_and_halo_evidence(self):
        for key in ('mask_alpha', 'halo_check'):
            for value in (None, False, 'true', 1):
                item = copy.deepcopy(self.item)
                item['transparent_png'] = 'transparent.png'
                item['file_checks'].update(mask_alpha=True, halo_check=True)
                item['file_checks'][key] = value
                with self.subTest(key=key, value=value):
                    self.rejects(item)
        item = copy.deepcopy(self.item)
        item['transparent_png'] = 'transparent.png'
        item['file_checks'].update(mask_alpha=True, halo_check=True)
        page = self.page(self.manifest(item))
        self.assertEqual(page.count('<figure>'), 3)
        self.assertIn('<div class="views with-cutout">', page)
        self.assertIn('Layers Original / After / Cutout_Transparent', page)
        self.assertIn('No shadow or halo on black and white', page)
        self.assertIn('data-bg="black"', page)

    def test_pass_requires_all_exporter_checks_and_files(self):
        for key in review.CHECK_KEYS:
            for value in (None, False, 1):
                item = copy.deepcopy(self.item)
                item['file_checks'][key] = value
                with self.subTest(key=key, value=value):
                    self.rejects(item)
        for key in ('source', 'after_png', 'psd', 'file_checks'):
            item = copy.deepcopy(self.item)
            item[key] = None
            with self.subTest(key=key):
                self.rejects(item)
        item = copy.deepcopy(self.item)
        item['method'] = 'original-derived'
        self.rejects(item)

    def test_blocked_explains_missing_capability_without_exports(self):
        item = dict(self.item, status='BLOCKED', after_png=None, psd=None,
                    file_checks=None, findings=['Image decoder unavailable.'])
        page = self.page(self.manifest(item))
        self.assertIn('Image decoder unavailable.', page)
        self.assertNotIn('>Transparent<', page)
        for bad in ([], [' '], 'Decoder unavailable'):
            self.rejects(dict(item, findings=bad))

    def test_rework_requires_a_real_annotated_region(self):
        item = dict(self.item, status='REWORK')
        self.rejects(item)
        region = dict(x=.3, y=.4, rx=.05, ry=.1, note='Original prong is clipped.')
        item['regions'] = [region]
        page = self.page(self.manifest(item))
        self.assertIn('<ellipse cx="0.3000"', page)
        self.assertIn('Original prong is clipped.', page)
        self.rejects(dict(item, status='QC-PASS'))

    def test_invalid_status_geometry_and_links_are_rejected(self):
        self.rejects(dict(self.item, status='PASS'))
        region = dict(x=.3, y=.4, rx=.05, ry=.1, note='Edge defect.')
        for changed in ({'x': True}, {'x': float('nan')}, {'y': -1}, {'rx': 0}, {'ry': 2}, {'note': ''}):
            with self.subTest(changed=changed):
                self.rejects(dict(self.item, status='REWORK', regions=[dict(region, **changed)]))
        for points in ([], [[0, 0], [1, 1]], [[0, 0], [0, .5], [0, 1]], [[0, 0], [1, 0], [1]], 'bad'):
            with self.subTest(points=points):
                self.rejects(dict(self.item, status='REWORK', regions=[dict(points=points, note='Defect.')]))
        for value in ('missing.png', '.', '', False, 'https://example.com/photo.png'):
            with self.subTest(path=value):
                self.rejects(dict(self.item, after_png=value))

    def test_localization_embedded_manifest_and_overwrite_guard(self):
        manifest = self.manifest()
        manifest['lang'] = 'fr-CA'
        manifest['items'][0]['findings'] = ['Texte </script> avec caractères.']
        page = self.page(manifest)
        self.assertIn('<html lang="fr">', page)
        embedded = page.split('<script type="application/json" id="manifest">')[1].split('</script>')[0]
        self.assertEqual(json.loads(embedded)['items'][0]['findings'], manifest['items'][0]['findings'])
        self.assertIn('<\\/script>', embedded)
        path = Path(self.temp.name) / 'manifest.json'
        path.write_text(json.dumps(manifest))
        target = self.out / 'review.html'
        cmd = [sys.executable, str(Path(review.__file__)), str(path), str(target)]
        first = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        target.write_text('owner content')
        refused = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(target.read_text(), 'owner content')
        replaced = subprocess.run(cmd + ['--replace'], capture_output=True, text=True)
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertIn('<!doctype html>', target.read_text())


if __name__ == '__main__':
    unittest.main()
