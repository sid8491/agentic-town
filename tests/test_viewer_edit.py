"""
tests/test_viewer_edit.py — Tests for scripts/viewer_edit.py

Verifies:
  - read() parses all three bundler blocks
  - to_html() roundtrips byte-identically when nothing is mutated
  - template mutation propagates through to_html() / write()
  - write() then read() preserves the mutation
  - no-op mutation (assigning the same value) still roundtrips identically

Run with:
    .venv/Scripts/python.exe tests/test_viewer_edit.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.viewer_edit import ViewerBundle

VIEWER = os.path.join(ROOT, "viewer.html")

results = []


def run_test(name, fn):
    try:
        fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


def test_01_read_parses_all_blocks():
    b = ViewerBundle.read(VIEWER)
    assert isinstance(b.manifest, dict) and len(b.manifest) > 0
    assert isinstance(b.ext_resources, list)
    assert isinstance(b.template, str) and "<!DOCTYPE html>" in b.template


def test_02_roundtrip_identity():
    b = ViewerBundle.read(VIEWER)
    original = Path(VIEWER).read_text(encoding="utf-8")
    assert b.to_html() == original, "to_html() must match source byte-for-byte when unmodified"


def test_03_template_mutation_propagates():
    b = ViewerBundle.read(VIEWER)
    needle = "XYZ_VIEWER_EDIT_TEST_MARKER"
    assert needle not in b.template
    b.template = b.template.replace("<title>Agentic Town", "<title>" + needle + " Agentic Town")
    assert needle in b.to_html()


def test_04_write_then_read_preserves_mutation():
    b = ViewerBundle.read(VIEWER)
    needle = "XYZ_WRITE_READ_TEST_MARKER"
    b.template = b.template.replace("<title>Agentic Town", "<title>" + needle + " Agentic Town")
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "v.html"
        b.write(f)
        b2 = ViewerBundle.read(f)
        assert needle in b2.template


def test_05_no_op_mutation_keeps_byte_identity():
    """Reassigning identical values must not perturb the original encoding."""
    b = ViewerBundle.read(VIEWER)
    b.template = b.template  # identity reassignment
    b.manifest = b.manifest
    original = Path(VIEWER).read_text(encoding="utf-8")
    assert b.to_html() == original


def test_06_atomic_write():
    """write() should not leave a .tmp behind on success."""
    b = ViewerBundle.read(VIEWER)
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "v.html"
        b.write(f)
        leftovers = list(Path(td).glob("*.tmp"))
        assert leftovers == [], f"unexpected leftovers: {leftovers}"


TESTS = [
    ("1.  read() parses all bundler blocks", test_01_read_parses_all_blocks),
    ("2.  to_html() roundtrip identity (no mutations)", test_02_roundtrip_identity),
    ("3.  template mutation propagates to_html()", test_03_template_mutation_propagates),
    ("4.  write() then read() preserves mutation", test_04_write_then_read_preserves_mutation),
    ("5.  no-op reassignment keeps byte identity", test_05_no_op_mutation_keeps_byte_identity),
    ("6.  write() leaves no .tmp behind", test_06_atomic_write),
]


if __name__ == "__main__":
    print("=" * 70)
    print("scripts/viewer_edit.py — Tests")
    print("=" * 70)

    for name, fn in TESTS:
        run_test(name, fn)

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print("=" * 70)
    print(f"Results: {passed}/{len(results)} passed, {failed} failed")
    print("=" * 70)
    if failed:
        sys.exit(1)
    print("ALL TESTS PASSED")
