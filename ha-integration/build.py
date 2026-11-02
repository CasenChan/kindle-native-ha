"""Bundle the self-contained HA editor and shared native SVG assets."""
import json
import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
icons = json.loads((ROOT / "frontend/icons.json").read_text(encoding="utf-8"))
source = (ROOT / "frontend/editor-source.js").read_text(encoding="utf-8")
target = ROOT / "custom_components/kindle_panel/frontend/editor.js"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("const ICONS = " + json.dumps(icons, ensure_ascii=False) + ";\n" + source, encoding="utf-8", newline="\n")
native_icons = ROOT.parent / "native-ha/icons"
native_icons.mkdir(parents=True, exist_ok=True)
for name, body in icons.items():
    svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='#111' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'>" + body + "</svg>"
    (native_icons / f"{name}.svg").write_text(svg, encoding="utf-8", newline="\n")
print(f"Built HA editor and {len(icons)} native icons")
spec = importlib.util.spec_from_file_location("kindle_protocol", ROOT / "custom_components/kindle_panel/protocol.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
layout = model.normalize_layout(model.DEFAULT_LAYOUT)
snapshot = {"revision": 1, "layout": layout, "geometry": model.geometry(layout), "temperature_unit": "°C",
            "states": {tile["id"]: model.public_state(tile, None) for tile in layout["tiles"]}}
(ROOT.parent / "native-ha/default-snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8", newline="\n")
shutil.copyfile(ROOT.parent / "native-ha/controller-source.lua", ROOT.parent / "native-ha/nativeha.koplugin/main.lua")
