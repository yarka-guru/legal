"""Validate the small Jekyll site's source without Jekyll or dependencies."""
from datetime import date
import argparse
from html.parser import HTMLParser
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urljoin, urlsplit


def scalar(value):
    """Read the plain/quoted scalar subset used by this site's metadata."""
    value = value.strip()
    quoted = re.fullmatch(r"(['\"])(.*?)\1\s*(?:#.*)?", value)
    if quoted:
        return quoted[2]
    value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    if value.startswith("#") or value.lower() in ("null", "~"):
        return ""
    return value


def front_matter(text):
    """Return flat metadata, or None if the front matter is absent/unclosed."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None
    result = {}
    for line in lines[1:end]:
        match = re.fullmatch(r"([\w_]+):\s*(.*)", line)
        if match:
            result[match[1]] = scalar(match[2])
    return result


def valid_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def config_list(text, key):
    """Read a top-level inline or block list; intentionally not a YAML parser."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(re.escape(key) + r":\s*(.*?)\s*(?:#.*)?", line)
        if not match:
            continue
        value = match[1]
        if value.startswith("[") and value.endswith("]"):
            return [scalar(item) for item in value[1:-1].split(",") if item.strip()]
        if value:
            raise ValueError(f"{key} must be an inline or block list")
        items = []
        for following in lines[index + 1:]:
            if not following.strip() or following.lstrip().startswith("#"):
                continue
            item = re.fullmatch(r"\s*-\s+(.+?)(?:\s+#.*)?", following)
            if item:
                items.append(scalar(item[1]))
            else:
                break
        return items
    return []


def language_path(path, languages):
    first, separator, rest = path.partition("/")
    if separator and first in languages[1:]:
        return first, rest
    return languages[0], path


class HTMLLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.remote_styles = False

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs if key in ("href", "src") and value)
        attributes = dict(attrs)
        if tag == "link" and (
            "stylesheet" in (attributes.get("rel") or "").lower().split()
            or attributes.get("as") in ("font", "style")
        ):
            href = static_link(attributes.get("href") or "")
            if href and re.match(r"(?:https?:)?//", href, re.I):
                self.remote_styles = True


def links_in(text):
    """Extract inline Markdown destinations and HTML href/src attributes."""
    parser = HTMLLinks()
    parser.feed(text)
    markdown = re.findall(r"!?\[[^\]]*\]\(\s*(\{\{.*?\}\}|<[^>]*>|[^\s)]+)(?:\s+[^)]*)?\)", text)
    return parser.links + [link.strip("<>") for link in markdown]


def static_link(link):
    literal = re.fullmatch(r"\{\{\s*(['\"])(.*?)\1\s*\|\s*relative_url\s*\}\}", link)
    if literal:
        return literal[2]
    if "{{" in link or "{%" in link:
        return None
    return link


def page_url(path):
    source = PurePosixPath(path)
    if source.name in ("index.md", "index.html"):
        return "/" + (str(source.parent).strip(".") + "/").lstrip("/")
    if source.suffix == ".md":
        return "/" + str(source.with_suffix("")) + "/"
    return "/" + path


def link_exists(link, source, files):
    parsed = urlsplit(link)
    if not link or link.startswith("#") or parsed.scheme or parsed.netloc:
        return True
    # Source Markdown links are rewritten by GitHub Pages' default relative-links plugin.
    base = "/" + source if parsed.path.endswith(".md") else page_url(source)
    target = unquote(urlsplit(urljoin(base, link)).path).lstrip("/")
    if target in files and not target.endswith("/"):
        return True
    stem = target.rstrip("/")
    prefix = stem + "/" if stem else ""
    return any(candidate in files for candidate in (
        stem + ".md", prefix + "index.md", prefix + "index.html"))


def forbidden_content(text):
    """Check source HTML/Markdown/CSS without executing any of it."""
    errors = []
    if re.search(r"<script", text, re.I):
        errors.append("script tag is forbidden")
    if re.search(r"http://", text, re.I):
        errors.append("http:// links are forbidden")
    parser = HTMLLinks()
    parser.feed(text)
    if parser.remote_styles or re.search(
        r"(?:@import\s+(?:url\(\s*)?|url\(\s*)['\"]?(?:https?:)?//", text, re.I
    ):
        errors.append("external stylesheet/font is forbidden")
    return errors


def excluded_paths(config):
    return {"README.md", "LICENSE", "scripts", "tests", "node_modules", "vendor"} | {
        item.rstrip("/") for item in config_list(config, "exclude")
    }


def included(path, excluded):
    parts = PurePosixPath(path).parts
    if any(path == item or path.startswith(item + "/") for item in excluded):
        return False
    return all(
        not part.startswith((".", "#", "_")) or (index == 0 and part == "_layouts")
        for index, part in enumerate(parts)
    ) and not path.endswith("~")


def validate_site(files):
    """Return deterministic errors for a mapping of source paths to text."""
    errors = []
    try:
        languages = config_list(files.get("_config.yml", ""), "languages")
        excluded = excluded_paths(files.get("_config.yml", ""))
    except ValueError as error:
        return [f"_config.yml: {error}"]
    if not languages or len(set(languages)) != len(languages) or any(
        not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]+)*", lang) for lang in languages
    ):
        return ["_config.yml: languages must be a nonempty list of unique language codes"]
    files = {path: text for path, text in files.items() if included(path, excluded)}
    for path, text in sorted(files.items()):
        if path.endswith((".md", ".html", ".css")):
            errors.extend(f"{path}: {error}" for error in forbidden_content(text))
        if path.endswith((".md", ".html")):
            for raw in links_in(text):
                link = static_link(raw)
                if link is not None and not link_exists(link, path, files):
                    errors.append(f"{path}: broken internal link '{link}'")
        if not path.endswith((".md", ".html")) or path.startswith("_"):
            continue
        language, canonical = language_path(path, languages)
        for target in languages:
            counterpart = canonical if target == languages[0] else f"{target}/{canonical}"
            if counterpart not in files:
                errors.append(f"{path}: missing translation '{counterpart}'")
        metadata = front_matter(text)
        if metadata is None:
            errors.append(f"{path}: missing front matter")
            continue
        required = ["layout", "title", "lang", "last_updated"]
        if metadata.get("document") == "true":
            required.extend(("version", "effective_date"))
        for field in required:
            if not metadata.get(field):
                errors.append(f"{path}: missing front matter field '{field}'")
        if metadata.get("layout") and metadata["layout"] != "default":
            errors.append(f"{path}: layout must be 'default'")
        if metadata.get("lang") and metadata["lang"] != language:
            errors.append(f"{path}: lang must be '{language}'")
        for field in ("last_updated", "effective_date"):
            if metadata.get(field) and not valid_date(metadata[field]):
                errors.append(f"{path}: {field} must be an ISO date (YYYY-MM-DD)")
    return errors


def read_site(root):
    """Read publishable sources, keeping binary assets as link targets only."""
    config = (root / "_config.yml").read_text(encoding="utf-8")
    excluded = excluded_paths(config)
    files = {"_config.yml": config}
    for directory, directories, filenames in os.walk(root):
        relative = Path(directory).relative_to(root)
        directories[:] = [name for name in directories if included((relative / name).as_posix(), excluded)]
        for name in filenames:
            path = (relative / name).as_posix()
            if included(path, excluded):
                files[path] = (root / path).read_text(encoding="utf-8") if Path(path).suffix in (
                    ".md", ".html", ".css") else ""
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        errors = validate_site(read_site(args.root))
    except (OSError, ValueError) as error:
        errors = [f"site: {error}"]
    for error in errors:
        print(" ".join(error.splitlines()))
    if not errors:
        print("OK: site source checks passed")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
