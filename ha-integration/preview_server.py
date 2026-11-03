"""Local-only editor preview with fictional entities. It never calls a live HA instance."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from kindle_model import load  # noqa: E402
import demo  # noqa: E402

protocol, _, render = load()
LAYOUT = protocol.normalize_layout(deepcopy(demo.LAYOUT))
REVISION = 1
DEVICES = {
    "demo-bedroom": {"id": "demo-bedroom", "name": "卧室 Kindle", "width": 758, "height": 1024, "battery": 82,
                     "charging": True, "revision": 1, "plugin_version": protocol.VERSION},
    "demo-study": {"id": "demo-study", "name": "书房 Kindle", "width": 758, "height": 1024, "battery": 41,
                   "charging": False, "revision": 0, "plugin_version": "0.3.0"},
}
AREAS = {"living": {"area_id": "living", "name": "客厅"}, "bedroom": {"area_id": "bedroom", "name": "卧室"},
         "study": {"area_id": "study", "name": "书房"}}
ENTITY_AREAS = {"living": ("light.living_main", "switch.floor_lamp", "sensor.living_humidity",
                           "sensor.living_temperature", "light.living_strip"),
                "bedroom": ("climate.bedroom", "light.bedside", "fan.bedroom"),
                "study": ("climate.study", "light.study_desk", "switch.monitor", "cover.study_curtain")}


def admin(layout, device_id=None):
    DEVICES["demo-bedroom"]["last_seen"] = time.time() - 12
    DEVICES["demo-study"]["last_seen"] = time.time() - 2 * 86400
    screen = DEVICES.get(device_id) or next(iter(DEVICES.values()), {"width": 758, "height": 1024})
    states = {key: {**value, "precision": None} for key, value in demo.STATES.items()}
    frame, views = render.snapshot(layout, REVISION, states, "°C", screen["width"], screen["height"])
    return {"layout": layout, "revision": REVISION, "frame": frame, "views": views, "devices": list(DEVICES.values()),
            "system_unit": "°C", "suggested_url": "http://192.168.1.20:8123", "icons": list(protocol.ICONS),
            "version": protocol.VERSION, "now": time.time()}


PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kindle 面板 · 本地预览</title><style>html,body{margin:0;height:100%}kindle-panel-editor{height:100vh}
body.dark{--primary-background-color:#111315;--card-background-color:#1b1e21;--secondary-background-color:#202428;
--divider-color:#2d3237;--primary-text-color:#e6e9ec;--secondary-text-color:#a5aeb7;--disabled-text-color:#737d87;
--primary-color:#3da3f5;--app-header-background-color:#1b1e21;background:#111315}</style>
<body><kindle-panel-editor preview></kindle-panel-editor><script type="module">
import '/editor.js';
const params = new URLSearchParams(location.search);
if (params.has('dark')) document.body.classList.add('dark');
const panel = document.querySelector('kindle-panel-editor');
const entities = {}, areas = %AREAS%;
for (const [area, ids] of Object.entries(%ENTITY_AREAS%)) for (const id of ids) entities[id] = {entity_id: id, area_id: area};
panel.narrow = params.has('narrow') || innerWidth < 870;
panel.hass = {states: %STATES%, entities, areas, devices: {}, callWS: async message => {
  const response = await fetch('/demo/manage', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(message)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  return data;
}};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, data, content_type="application/json", status=200):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        elif isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/editor.js":
            return self.send((ROOT / "custom_components/kindle_panel/frontend/editor.js").read_bytes(), "text/javascript")
        if path != "/":
            return self.send({"error": "not found"}, status=404)
        page = (PAGE.replace("%STATES%", json.dumps(demo.STATES, ensure_ascii=False))
                .replace("%AREAS%", json.dumps(AREAS, ensure_ascii=False))
                .replace("%ENTITY_AREAS%", json.dumps(ENTITY_AREAS)))
        self.send(page, "text/html")

    def do_POST(self):
        global LAYOUT, REVISION
        if self.path != "/demo/manage":
            return self.send({"error": "not found"}, status=404)
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 262144)))
            action, device_id = body.get("action"), body.get("device_id")
            if action == "load":
                return self.send(admin(LAYOUT, device_id))
            if action == "preview":
                return self.send(admin(protocol.normalize_layout(body.get("layout")), device_id))
            if action == "save":
                if body.get("revision") != REVISION:
                    raise protocol.ProtocolError("布局已改变，请重新加载")
                layout = protocol.normalize_layout(body.get("layout"))
                missing = [t["title"] for t in protocol.iter_tiles(layout) if t["entity_id"] not in demo.STATES]
                if missing:
                    raise protocol.ProtocolError(f"这些卡片的实体不存在：{'、'.join(missing[:3])}")
                LAYOUT, REVISION = layout, REVISION + 1
                return self.send(admin(LAYOUT, device_id))
            if action == "revoke":
                DEVICES.pop(device_id, None)
                return self.send(admin(LAYOUT))
            return self.send({"error": "本地预览不执行配对或设备操作"}, status=400)
        except (ValueError, TypeError) as err:
            return self.send({"error": str(err)}, status=400)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Kindle editor preview: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
