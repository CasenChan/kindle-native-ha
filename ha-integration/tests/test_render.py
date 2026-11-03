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
                    self.assertIn(hit["action"], ("power", "activate", "temperature", "mode"))
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

    def test_payload_stays_small(self):
        snap, _ = render()
        self.assertLess(len(json.dumps(snap, ensure_ascii=False).encode()), 200_000)


if __name__ == "__main__":
    unittest.main()
