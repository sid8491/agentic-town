"""
viewer_edit.py — helper for editing viewer.html, the self-contained bundled web viewer.

File structure:
    Lines 1–168     HTML shell + JS bootloader that decodes the bundle at runtime
    <script type="__bundler/manifest">       JSON dict of UUID -> {data:base64, mime, compressed}
                                              Holds dependencies only (fonts, React, ReactDOM,
                                              Babel-standalone, agent portraits). Almost never
                                              touched.
    <script type="__bundler/ext_resources">  JSON list of {id, uuid} pairs (usually empty)
    <script type="__bundler/template">       JSON-encoded string of the actual HTML+CSS+JS.
                                              This is where the UI code lives.

Usage:
    from scripts.viewer_edit import ViewerBundle

    b = ViewerBundle.read("viewer.html")
    b.template = b.template.replace('id="root"', 'id="root" data-v=2')
    b.write("viewer.html")

The template is exposed as a decoded HTML/JS/CSS string. Asset references inside it
use UUIDs (e.g. src="def6a65e-1f25-4048-9cf0-aca305b97c2c") that the runtime
bootloader rewrites to blob: URLs — leave those UUIDs alone unless you also edit
the manifest.

Roundtrip guarantee: read() then write() with no mutations produces a
byte-identical file.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

_BLOCK_RE = re.compile(
    r'(?P<open><script type="__bundler/(?P<kind>manifest|ext_resources|template)">\n)'
    r'(?P<content>.*?)'
    r'(?P<close>\n {2}</script>)',
    re.DOTALL,
)


class ViewerBundle:
    def __init__(
        self,
        raw: str,
        manifest: dict[str, Any],
        ext_resources: list[Any],
        template: str,
        original_blocks: dict[str, str],
        original_objects: dict[str, Any],
    ) -> None:
        self._raw = raw
        self._original_blocks = original_blocks
        self._original_objects = original_objects
        self.manifest = manifest
        self.ext_resources = ext_resources
        self.template = template

    @classmethod
    def read(cls, path: str | Path) -> "ViewerBundle":
        raw = Path(path).read_text(encoding="utf-8")
        original_blocks: dict[str, str] = {}
        for m in _BLOCK_RE.finditer(raw):
            original_blocks[m.group("kind")] = m.group("content")
        missing = {"manifest", "ext_resources", "template"} - set(original_blocks)
        if missing:
            raise ValueError(f"viewer.html is missing bundler tags: {sorted(missing)}")
        manifest = json.loads(original_blocks["manifest"])
        ext_resources = json.loads(original_blocks["ext_resources"])
        template = json.loads(original_blocks["template"])
        original_objects = {
            "manifest": copy.deepcopy(manifest),
            "ext_resources": copy.deepcopy(ext_resources),
            "template": template,  # str is immutable
        }
        return cls(
            raw=raw,
            manifest=manifest,
            ext_resources=ext_resources,
            template=template,
            original_blocks=original_blocks,
            original_objects=original_objects,
        )

    def _block_for(self, kind: str) -> str:
        current = {
            "manifest": self.manifest,
            "ext_resources": self.ext_resources,
            "template": self.template,
        }[kind]
        if current == self._original_objects[kind]:
            return self._original_blocks[kind]
        if kind == "template":
            return json.dumps(current)
        return json.dumps(current, separators=(",", ":"))

    def to_html(self) -> str:
        def replace(m: re.Match) -> str:
            return m.group("open") + self._block_for(m.group("kind")) + m.group("close")
        return _BLOCK_RE.sub(replace, self._raw)

    def write(self, path: str | Path) -> None:
        target = Path(path)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(self.to_html(), encoding="utf-8")
        tmp.replace(target)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python scripts/viewer_edit.py <viewer.html>")
        print("Reads the file and prints sizes; useful as a sanity check.")
        sys.exit(1)
    b = ViewerBundle.read(sys.argv[1])
    print(f"manifest: {len(b.manifest)} assets")
    print(f"ext_resources: {len(b.ext_resources)} entries")
    print(f"template: {len(b.template):,} chars of HTML/JS/CSS")
    roundtrip = b.to_html() == Path(sys.argv[1]).read_text(encoding="utf-8")
    print(f"roundtrip identity: {'OK' if roundtrip else 'DIFFERS'}")
