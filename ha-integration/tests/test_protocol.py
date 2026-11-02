from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).parents[1] / "custom_components/kindle_panel/protocol.py"
spec = importlib.util.spec_from_file_location("kindle_protocol", path)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.layout = p.normalize_layout(deepcopy(p.DEFAULT_LAYOUT))

    def test_geometry_matches_device_and_has_no_overlaps(self):
        g = p.geometry(self.layout)
        self.assertEqual((g["width"], g["height"], g["pages"]), (758, 1024, 1))
        for card in g["cards"]:
            self.assertGreaterEqual(card["x"], 0)
            self.assertGreaterEqual(card["y"], g["header"])
            self.assertLessEqual(card["x"] + card["w"], 758)
            self.assertLessEqual(card["y"] + card["h"], 1024 - g["footer"])
        self.assertEqual(g["cards"][0]["y"], g["cards"][1]["y"])
        self.assertGreater(g["cards"][2]["y"], g["cards"][0]["y"])
        self.assertGreater(g["cards"][2]["w"], g["cards"][0]["w"])

    def test_pages_pack_wide_climate_without_crossing_bounds(self):
        data = deepcopy(p.DEFAULT_LAYOUT)
        data["tiles"] *= 4
        for i, tile in enumerate(data["tiles"]):
            data["tiles"][i] = {**tile, "id": str(i)}
        layout = p.normalize_layout(data)
        g = p.geometry(layout)
        self.assertGreater(g["pages"], 1)
        self.assertEqual(len(g["cards"]), 12)

    def test_invalid_layouts_are_rejected(self):
        for change in ({"columns": True}, {"rows": 0}, {"refresh_seconds": 1}, {"tiles": []}, {"power_mode": "disable-security"}):
            with self.subTest(change=change), self.assertRaises(p.ProtocolError):
                p.normalize_layout({**deepcopy(p.DEFAULT_LAYOUT), **change})
        data = deepcopy(p.DEFAULT_LAYOUT)
        data["tiles"][0]["entity_id"] = "switch.foo/../../services"
        with self.assertRaises(p.ProtocolError):
            p.normalize_layout(data)

    def test_pairing_is_one_use_and_key_is_not_stored(self):
        clock = [1000]
        pairs = p.Pairing(lambda: clock[0])
        code = pairs.create("owner")["code"]
        device, key = pairs.consume(code, "卧室 Kindle", 758, 1024)
        self.assertNotIn(key, repr(device))
        self.assertIs(p.authenticate({device["id"]: device}, key), device)
        self.assertIsNone(p.authenticate({device["id"]: device}, key + "x"))
        self.assertIsNone(p.authenticate({}, key))
        with self.assertRaises(p.ProtocolError):
            pairs.consume(code, "again", 758, 1024)
        code = pairs.create("owner")["code"]
        clock[0] += 601
        with self.assertRaises(p.ProtocolError):
            pairs.consume(code, "expired", 758, 1024)

    def test_services_are_scoped_to_saved_tiles(self):
        tile = self.layout["tiles"][0]
        result = p.service_for_action(tile, "power", True, {"state": "off"})
        self.assertEqual(result, ("switch", "turn_on", {"entity_id": tile["entity_id"]}))
        for action, value in (("power", "on"), ("unlock", True), ("temperature", 23)):
            with self.assertRaises(p.ProtocolError):
                p.service_for_action(tile, action, value, {"state": "on"})

    def test_temperature_enforces_live_range_and_step(self):
        tile = self.layout["tiles"][2]
        state = {"state": "cool", "attributes": {"min_temp": 16, "max_temp": 30, "target_temp_step": .5}}
        self.assertEqual(p.service_for_action(tile, "temperature", 24.5, state)[2]["temperature"], 24.5)
        for value in (True, 31, 24.2, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(p.ProtocolError):
                p.service_for_action(tile, "temperature", value, state)
        with self.assertRaises(p.ProtocolError):
            p.service_for_action(tile, "temperature", 24, {**state, "state": "off"})

    def test_snapshot_does_not_expose_arbitrary_entity_attributes(self):
        state = {"state": "on", "attributes": {"unit_of_measurement": "%", "secret": "not-for-the-device", "latitude": 1}}
        result = p.public_state(self.layout["tiles"][0], state)
        self.assertEqual(result["attributes"], {"unit_of_measurement": "%"})
        self.assertFalse(p.public_state(self.layout["tiles"][0], None)["available"])


if __name__ == "__main__":
    unittest.main()
