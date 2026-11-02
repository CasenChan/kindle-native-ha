"""Local-only editor preview. It never calls the live HA instance."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("kindle_protocol", ROOT / "custom_components/kindle_panel/protocol.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
LAYOUT = model.normalize_layout(deepcopy(model.DEFAULT_LAYOUT))
REVISION = 1
STATES = {
    "switch.room_light_left": {"entity_id": "switch.room_light_left", "state": "on", "attributes": {"friendly_name": "房间灯左键"}},
    "switch.room_light_right": {"entity_id": "switch.room_light_right", "state": "off", "attributes": {"friendly_name": "房间灯右键"}},
    "climate.bedroom": {"entity_id": "climate.bedroom", "state": "cool", "attributes": {"friendly_name": "卧室空调", "temperature": 24, "current_temperature": 24.7, "min_temp": 16, "max_temp": 30, "target_temp_step": 1}},
}


def result(layout):
    return {"layout": layout, "revision": REVISION, "devices": [], "geometry": model.geometry(layout),
            "temperature_unit": "°C", "states": {tile["id"]: model.public_state(tile, STATES.get(tile["entity_id"])) for tile in layout["tiles"]}}


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
        if self.path == "/editor.js":
            return self.send((ROOT / "custom_components/kindle_panel/frontend/editor.js").read_bytes(), "text/javascript")
        if self.path != "/":
            return self.send({"error": "not found"}, status=404)
        states_json = json.dumps(STATES, ensure_ascii=False)
        self.send("""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kindle 面板 · 本地预览</title><style>html,body{margin:0;background:#f3f5f7;min-height:100%;font-family:Arial,sans-serif}kindle-panel-editor{min-height:100vh}</style><kindle-panel-editor preview></kindle-panel-editor><script type="module">import '/editor.js';document.querySelector('kindle-panel-editor').hass={states:""" + states_json + """,callWS:async message=>{const response=await fetch('/demo/manage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(message)});const data=await response.json();if(!response.ok)throw new Error(data.error);return data;}};</script></html>""", "text/html")

    def do_POST(self):
        global LAYOUT, REVISION
        if self.path != "/demo/manage":
            return self.send({"error": "not found"}, status=404)
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 32768)))
            action = body.get("action")
            if action == "load":
                return self.send(result(LAYOUT))
            if action == "preview":
                return self.send(result(model.normalize_layout(body.get("layout"))))
            if action == "save":
                if body.get("revision") != REVISION:
                    raise model.ProtocolError("布局已改变，请重新加载")
                LAYOUT = model.normalize_layout(body.get("layout"))
                REVISION += 1
                output = ROOT.parent / "diagnostics/preview-layout.json"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(LAYOUT, ensure_ascii=False, indent=2), encoding="utf-8")
                return self.send(result(LAYOUT))
            return self.send({"error": "本地预览不执行配对或设备操作"}, status=400)
        except (ValueError, TypeError) as err:
            return self.send({"error": str(err)}, status=400)


if __name__ == "__main__":
    print("Kindle editor preview: http://127.0.0.1:8765", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
