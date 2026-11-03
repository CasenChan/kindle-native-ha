import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from kindle_model import load  # noqa: E402
import demo  # noqa: E402

p, d, r = load()
ICONS = set(json.loads((Path(__file__).parents[1] / "frontend/icons.json").read_text(encoding="utf-8")))


def render(layout=None, states=None, width=758, height=1024, system_unit="°C"):
    layout = p.normalize_layout(layout or demo.LAYOUT)
    return r.snapshot(layout, 7, demo.STATES if states is None else states, system_unit, width, height)


def inside(box, width, height):
    return box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["w"] <= width and box["y"] + box["h"] <= height


class RenderTests(unittest.TestCase):
    def test_every_op_is_well_formed_and_on_screen(self):
        for width, height in ((758, 1024), (1072, 1448), (600, 800)):
            snap, _ = render(width=width, height=height)
            for page in snap["pages"]:
                for op in page["ops"]:
                    self.assertIn(op["t"], "rxi")
                    self.assertTrue(all(isinstance(op[key], int) for key in ("x", "y")), op)
                    if op["t"] == "r":
                        self.assertTrue(inside(op, width, height), op)
                    if op["t"] == "i":
                        self.assertIn(op["n"], ICONS)
                        self.assertIn(op["c"], ("k", "w", "g"))
                for box in page["cards"] + page["hits"]:
                    self.assertTrue(inside(box, width, height), box)

    def test_cards_do_not_overlap_and_stay_out_of_chrome(self):
        snap, _ = render()
        for page in snap["pages"]:
            cards = page["cards"]
            for card in cards:
                self.assertGreaterEqual(card["y"], 128)
                self.assertLessEqual(card["y"] + card["h"], 1024 - 72)
            for i, a in enumerate(cards):
                for b in cards[i + 1:]:
                    self.assertTrue(a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                                    or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"], (a, b))

    def test_hits_only_target_saved_tiles_with_allowed_actions(self):
        snap, _ = render()
        tiles = {tile["id"]: tile for tile in p.iter_tiles(p.normalize_layout(demo.LAYOUT))}
        for page in snap["pages"]:
            for hit in page["hits"]:
                if "tile" in hit:
                    self.assertIn(hit["tile"], tiles)
                    self.assertIn(hit["action"], ("power", "activate", "temperature", "mode", "brightness",
                                                  "cover", "media", "lock"))
                else:
                    self.assertIn(hit["local"], ("refresh", "backlight", "menu", "page"))

    def test_unavailable_tiles_have_no_controls(self):
        snap, views = render()
        offline = [tile_id for tile_id, view in views.items() if not view["available"]]
        self.assertTrue(offline)
        for page in snap["pages"]:
            self.assertFalse([hit for hit in page["hits"] if hit.get("tile") in offline])

    def test_climate_controls_follow_state(self):
        snap, _ = render()
        hits = [hit for hit in snap["pages"][0]["hits"] if hit.get("tile") == "t6"]
        actions = {(hit["action"], hit.get("value")) for hit in hits}
        self.assertIn(("temperature", 23), actions)
        self.assertIn(("temperature", 25), actions)
        self.assertIn(("mode", "heat"), actions)
        self.assertNotIn(("mode", "cool"), actions)
        off = [hit for hit in snap["pages"][1]["hits"] if hit.get("tile") == "t11"]
        self.assertFalse([hit for hit in off if hit["action"] == "temperature"])

    def test_snapshot_exposes_only_minimal_state(self):
        snap, _ = render()
        self.assertEqual(set(snap["states"]["t1"]), {"available", "state"})
        self.assertNotIn("friendly_name", json.dumps(snap, ensure_ascii=False))

    def test_dense_grids_render(self):
        tiles = [{"id": f"t{i}", "entity_id": "light.living_main", "title": f"灯{i}"} for i in range(32)]
        layout = {"pages": [{"id": "p", "title": "密集", "columns": 4,
                             "sections": [{"id": "s", "title": "全部", "rows": 8, "tiles": tiles}]}]}
        snap, _ = render(layout)
        self.assertEqual(len(snap["pages"][0]["cards"]), 32)
        self.assertGreater(min(card["h"] for card in snap["pages"][0]["cards"]), 70)

    def test_new_controls_are_rendered(self):
        snap, views = render()
        hits = {(hit.get("tile"), hit.get("action"), hit.get("value")) for page in snap["pages"] for hit in page["hits"]}
        self.assertIn(("t1", "brightness", 1), hits)
        self.assertEqual(views["t1"]["brightness"], 60)
        self.assertIn(("t22", "media", "next"), hits)
        self.assertIn(("t23", "cover", "stop"), hits)
        unlock = [hit for page in snap["pages"] for hit in page["hits"] if hit.get("tile") == "t10"]
        self.assertEqual(unlock[0]["value"], False)
        self.assertTrue(unlock[0]["confirm"])

    def test_locks_without_permission_cannot_be_unlocked_from_the_kindle(self):
        layout = p.normalize_layout(demo.LAYOUT)
        p.find_tile(layout, "t10")["allow_unlock"] = False
        snap, _ = r.snapshot(layout, 1, demo.STATES, "°C", 758, 1024)
        self.assertFalse([hit for page in snap["pages"] for hit in page["hits"] if hit.get("tile") == "t10"])

    def test_hash_changes_only_with_content(self):
        first, _ = render()
        again, _ = render()
        self.assertEqual(first["hash"], again["hash"])
        states = {**demo.STATES, "light.bedside": {**demo.STATES["light.bedside"], "state": "off"}}
        changed, _ = render(states=states)
        self.assertNotEqual(first["hash"], changed["hash"])

    def test_every_kind_and_size_lays_out_cleanly(self):
        """Every card kind at every w×h on 1–4 columns and 2–8 rows: shapes stay inside the card, texts do not
        overlap each other or icons, fonts stay readable and tap targets stay finger-sized."""
        modes = ["off", "cool", "heat", "dry", "fan_only", "auto"]
        kinds = {
            "toggle": ("switch.x", "on", {}), "dimmer": ("light.x", "on", {"brightness": 128, "supported_color_modes": ["hs"]}),
            "number": ("sensor.x", "1234.56", {"unit_of_measurement": "kWh"}), "text": ("sensor.y", "Partly cloudy with rain", {}),
            "action": ("scene.x", "unknown", {}), "lock": ("lock.x", "locked", {}), "offline": ("switch.x", "unavailable", {}),
            "climate": ("climate.x", "cool", {"temperature": 24, "current_temperature": 26.3, "min_temp": 16, "max_temp": 30, "hvac_modes": modes}),
            "cover": ("cover.x", "open", {"current_position": 60}), "media": ("media_player.x", "playing", {"media_title": "很长的歌曲名字 - Artist"}),
        }

        def box(op):
            if op["t"] != "x":
                return op["x"], op["y"], op.get("w", op.get("s")), op.get("h", op.get("s"))
            width = r.text_width(op["v"], op["s"]) + (r.text_width(op["u"], op["s"] * .5) + op["s"] * .12 if op.get("u") else 0)
            width = min(width, op.get("w", width))
            left = {"r": op["x"] - width, "c": op["x"] - width / 2}.get(op.get("a"), op["x"])
            return left, op["y"], width, op["s"] * 1.25

        def overlap(a, b, slack):
            return a[0] < b[0] + b[2] - slack and b[0] < a[0] + a[2] - slack and a[1] < b[1] + b[3] - slack and b[1] < a[1] + a[3] - slack

        for name, (entity_id, state, attributes) in kinds.items():
            for columns in (1, 2, 3, 4):
                for rows in (2, 3, 4, 6, 8):
                    for w in range(1, columns + 1):
                        for h in range(1, min(rows, 4) + 1):
                            layout = p.normalize_layout({"pages": [{"id": "p", "title": "测试", "columns": columns, "sections": [
                                {"id": "s", "title": "房间", "rows": rows,
                                 "tiles": [{"id": "t", "entity_id": entity_id, "title": "客厅主灯开关", "w": w, "h": h}]}]}]})
                            snap, _ = r.snapshot(layout, 1, {entity_id: {"state": state, "attributes": attributes}}, "°C", 758, 1024)
                            page, label = snap["pages"][0], f"{name} {columns}col {rows}rows {w}x{h}"
                            card = page["cards"][0]
                            mine = [op for op in page["ops"] if card["x"] - 2 <= op["x"] <= card["x"] + card["w"]
                                    and card["y"] - 2 <= op["y"] <= card["y"] + card["h"]]
                            texts = [box(op) for op in mine if op["t"] == "x"]
                            for op in mine:
                                left, top, width, height = box(op)
                                self.assertLessEqual(left + width, card["x"] + card["w"] + 1, label)
                                self.assertLessEqual(top + height, card["y"] + card["h"] + 2, label)
                                if op["t"] == "x":
                                    self.assertGreaterEqual(op["s"], 14, label)
                            for i, a in enumerate(texts):
                                for b in texts[i + 1:]:
                                    self.assertFalse(overlap(a, b, 4), label)
                                for icon in (box(op) for op in mine if op["t"] == "i"):
                                    self.assertFalse(overlap(a, icon, 2), label)
                            for hit in page["hits"]:
                                if "tile" in hit:
                                    self.assertGreaterEqual(min(hit["w"], hit["h"]), 30, label)

    def test_payload_stays_small(self):
        snap, _ = render()
        self.assertLess(len(json.dumps(snap, ensure_ascii=False).encode()), 200_000)


if __name__ == "__main__":
    unittest.main()
