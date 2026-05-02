"""One-shot patch: make plot-thread clicks also enable Director Mode."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.viewer_edit import ViewerBundle

OLD = (
    "if (e.target.classList.contains('tclose')) return;\n"
    "      const first = card.dataset.first;\n"
    "      if (first) _setProtagonist(first, true);"
)
NEW = (
    "if (e.target.classList.contains('tclose')) return;\n"
    "      const first = card.dataset.first;\n"
    "      if (first) {\n"
    "        if (!directorMode) {\n"
    "          directorMode = true;\n"
    "          const btn = document.getElementById('director-toggle');\n"
    "          if (btn) btn.classList.add('active');\n"
    "        }\n"
    "        _setProtagonist(first, true);\n"
    "      }"
)

b = ViewerBundle.read(ROOT / "viewer.html")
if OLD not in b.template:
    raise SystemExit("anchor not found — already patched or template changed")
b.template = b.template.replace(OLD, NEW)
b.write(ROOT / "viewer.html")
print("patched.")
