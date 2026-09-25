"""Behavior checks for the source-site validator (stdlib only)."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.check_site import validate_site


PAGE = "---\nlayout: default\ntitle: Status\nlang: en\nlast_updated: 2026-09-24\n---\nStatus.\n"
ROOT = Path(__file__).resolve().parents[1]


class SiteChecks(unittest.TestCase):
    def test_commented_document_flag_and_null_metadata_cannot_bypass_checks(self):
        files = {"_config.yml": "languages: [en]\n", "index.md": PAGE.replace(
            "title: Status", "title: 'Status #1' # title\ndocument: true # legal document")}
        self.assertIn("index.md: missing front matter field 'version'", validate_site(files))
        for value in ("null", "~", "# date required"):
            with self.subTest(value=value):
                files["index.md"] = PAGE.replace("last_updated: 2026-09-24", "last_updated: " + value)
                self.assertIn("index.md: missing front matter field 'last_updated'", validate_site(files))
        files["index.md"] = PAGE.replace("2026-09-24", "'2026-09-24' # updated")
        self.assertEqual(validate_site(files), [])

    def test_cli_checks_fixture_trees_and_returns_one_line_per_error(self):
        cases = {"good": "OK", "broken_link": "broken internal link '/absent/'",
                 "missing_front_matter": "missing front matter",
                 "missing_translation": "missing translation 'es/index.md'",
                 "wrong_lang": "lang must be 'es'", "script_tag": "script tag is forbidden"}
        for fixture, message in cases.items():
            with self.subTest(fixture=fixture):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/check_site.py"), str(ROOT / "tests/fixtures" / fixture)],
                    capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0 if fixture == "good" else 1)
                self.assertIn(message, result.stdout)
                self.assertEqual(len(result.stdout.splitlines()), 1)
                self.assertEqual(result.stderr, "")

    def test_cli_ignores_nonpublished_files_and_reports_missing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "_config.yml").write_text("languages: [en]\nexclude:\n  - notes\n")
            (root / "index.md").write_text(PAGE)
            for name in ("README.md", "tests/bad.md", "scripts/bad.md", "notes/bad.md", ".harness/bad.md", "_site/bad.md"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Not a page.")
            command = [sys.executable, str(ROOT / "scripts/check_site.py"), directory]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout)
            (root / "_config.yml").unlink()
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("_config.yml", result.stdout)
            self.assertEqual(result.stderr, "")

    def test_forbidden_active_content_and_remote_styles_are_rejected(self):
        cases = (
            ("index.md", '<ScRiPt src="/app.js"></ScRiPt>', "script tag is forbidden"),
            ("index.md", "[insecure](http://example.org/)", "http:// links are forbidden"),
            ("_layouts/default.html", '<link rel="stylesheet" href="https://example.org/style">', "external stylesheet/font is forbidden"),
            ("_layouts/default.html", '<link href="//example.org/style.css" rel="stylesheet">', "external stylesheet/font is forbidden"),
            ("assets/style.css", '@import "https://example.org/font.css";', "external stylesheet/font is forbidden"),
            ("assets/style.css", '@font-face { src: url(//example.org/font.woff2); }', "external stylesheet/font is forbidden"),
            ("index.md", '<style>@import url("https://example.org/font.css");</style>', "external stylesheet/font is forbidden"),
        )
        for path, content, message in cases:
            with self.subTest(content=content):
                files = {"_config.yml": "languages: [en]\n", "index.md": PAGE}
                files[path] = (PAGE if path.endswith(".md") else "") + content
                self.assertIn(f"{path}: {message}", validate_site(files))

    def test_links_resolve_source_files_in_pages_and_layouts(self):
        files = {"_config.yml": "languages: [en]\n", "index.md": PAGE,
                 "a/b.md": PAGE, "c/d/index.md": PAGE, "e/f/index.html": PAGE,
                 "assets/style.css": "body {}", "asset.svg": "<svg></svg>"}
        links = ["/a/b/", "/c/d/", "/e/f/", "/assets/style.css", "/asset.svg",
                 "https://example.org/", "mailto:", "#main", "/a/b/?print=1#main",
                 "{{ '/a/b/' | relative_url }}", '{{ "/c/d/" | relative_url }}',
                 "{{ page.url | relative_url }}"]
        files["index.md"] += "\n".join(f"[link]({link})" for link in links)
        files["_layouts/default.html"] = '\n'.join(
            f'<a href="{link}">Link</a>' for link in links if '"' not in link)
        files["a/b.md"] += '\n[relative](../../c/d/)\n<img src="/asset.svg">'
        self.assertEqual(validate_site(files), [])
        for source, link in (("index.md", "[broken](/missing/)"),
                             ("_layouts/default.html", '<a href="{{ \'/missing/\' | relative_url }}">Missing</a>'),
                             ("a/b.md", '<img src="/missing/">')):
            with self.subTest(source=source):
                broken = dict(files)
                broken[source] += '\n' + link
                self.assertIn(f"{source}: broken internal link '/missing/'", validate_site(broken))

    def test_translations_and_document_metadata_follow_configured_languages(self):
        for config in ("languages: [en, es, fr] # locales\n", "languages:\n  - en\n  - 'es'\n  - fr\n"):
            files = {"_config.yml": config, "sxnts/privacy.md": PAGE,
                     "es/sxnts/privacy.md": PAGE.replace("lang: en", "lang: es")}
            self.assertIn("sxnts/privacy.md: missing translation 'fr/sxnts/privacy.md'", validate_site(files))
            files["fr/sxnts/privacy.md"] = PAGE.replace("lang: en", "lang: fr")
            self.assertEqual(validate_site(files), [])
            files["es/sxnts/privacy.md"] = PAGE
            self.assertIn("es/sxnts/privacy.md: lang must be 'es'", validate_site(files))
        files = {"_config.yml": "languages: [es, en]\n",
                 "index.md": PAGE.replace("lang: en", "lang: es"), "en/index.md": PAGE}
        self.assertEqual(validate_site(files), [])
        files = {"_config.yml": "languages: [en]\n", "sxnts/privacy.md": PAGE.replace(
            "title: Status", "title: Status\ndocument: true")}
        for field in ("version", "effective_date"):
            self.assertIn(f"sxnts/privacy.md: missing front matter field '{field}'", validate_site(files))
        files["sxnts/privacy.md"] = files["sxnts/privacy.md"].replace(
            "document: true", "document: true\nversion: 1\neffective_date: 2026-09-24")
        self.assertEqual(validate_site(files), [])
        files["sxnts/privacy.md"] = files["sxnts/privacy.md"].replace("effective_date: 2026-09-24", "effective_date: yesterday")
        self.assertIn("sxnts/privacy.md: effective_date must be an ISO date (YYYY-MM-DD)", validate_site(files))

    def test_page_metadata_is_required_and_dates_are_real_iso_dates(self):
        files = {"_config.yml": "languages: [en]\n", "index.md": PAGE}
        self.assertEqual(validate_site(files), [])
        for field in ("layout", "title", "lang", "last_updated"):
            with self.subTest(field=field):
                broken = dict(files)
                broken["index.md"] = "\n".join(
                    line for line in PAGE.splitlines() if not line.startswith(field + ":")
                )
                self.assertIn(f"index.md: missing front matter field '{field}'", validate_site(broken))
        files["index.md"] = "No metadata."
        self.assertIn("index.md: missing front matter", validate_site(files))
        files["index.md"] = PAGE.replace("2026-09-24", "2026-02-30")
        self.assertIn("index.md: last_updated must be an ISO date (YYYY-MM-DD)", validate_site(files))


if __name__ == "__main__":
    unittest.main()
