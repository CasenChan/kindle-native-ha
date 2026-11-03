from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from kindle_model import load  # noqa: E402

p, d, r = load()


def layout_with(*tiles, columns=2, rows=3, **section):
    return {"pages": [{"id": "p", "title": "家", "columns": columns,
                       "sections": [{"id": "s", "title": "", "rows": rows, "tiles": list(tiles), **section}]}]}


def tile(tile_id, entity_id="switch.lamp", **extra):
    return {"id": tile_id, "entity_id": entity_id, "title": tile_id, **extra}


class LayoutTests(unittest.TestCase):
    def test_default_layout_is_valid_and_placed(self):
        layout = p.default_layout()
        tiles = list(p.iter_tiles(layout))
        self.assertEqual([(t["x"], t["y"], t["w"]) for t in tiles], [(0, 0, 1), (1, 0, 1), (0, 1, 2)])

    def test_explicit_positions_are_kept_and_others_first_fit(self):
        layout = p.normalize_layout(layout_with(tile("a", x=1, y=1), tile("b", w=2), tile("c"), columns=2, rows=2))
        placed = {t["id"]: (t["x"], t["y"]) for t in p.iter_tiles(layout)}
        self.assertEqual(placed, {"a": (1, 1), "b": (0, 0), "c": (0, 1)})

    def test_overlapping_or_out_of_bounds_positions_are_repacked(self):
        layout = p.normalize_layout(layout_with(tile("a", x=0, y=0), tile("b", x=0, y=0), tile("c", x=9, y=9)))
        self.assertEqual(len({(t["x"], t["y"]) for t in p.iter_tiles(layout)}), 3)

    def test_section_overflow_is_a_clear_error(self):
        with self.assertRaisesRegex(p.ProtocolError, "放不下"):
            p.normalize_layout(layout_with(*(tile(str(i)) for i in range(5)), columns=2, rows=2))

    def test_sizes_are_clamped_to_the_grid(self):
        layout = p.normalize_layout(layout_with(tile("a", w=4, h=8), columns=2, rows=3))
        self.assertEqual((layout["pages"][0]["sections"][0]["tiles"][0]["w"],
                          layout["pages"][0]["sections"][0]["tiles"][0]["h"]), (2, 3))

    def test_invalid_layouts_are_rejected(self):
        base = p.default_layout()
        for change in ({"refresh_seconds": 1}, {"power_mode": "disable-security"}, {"temperature_unit": "K"},
                       {"pages": []}):
            with self.subTest(change=change), self.assertRaises(p.ProtocolError):
                p.normalize_layout({**deepcopy(base), **change})
        with self.assertRaises(p.ProtocolError):
            p.normalize_layout(layout_with(tile("a", entity_id="switch.foo/../../services")))
        with self.assertRaises(p.ProtocolError):
            p.normalize_layout(layout_with(tile("a"), tile("a")))
        with self.assertRaisesRegex(p.ProtocolError, "超过 8 行"):
            p.normalize_layout({"pages": [{"id": "p", "title": "家", "columns": 2, "sections": [
                {"id": "s1", "rows": 5, "tiles": [tile("a")]}, {"id": "s2", "rows": 4, "tiles": []}]}]})

    def test_v1_layouts_migrate_to_pages(self):
        old = {"title": "我的家", "columns": 2, "rows": 2, "refresh_seconds": 60, "power_mode": "always-refresh",
               "tiles": [{"id": f"t{i}", "entity_id": "switch.x", "title": "灯", "icon": "bulb", "span": 1}
                         for i in range(5)]
               + [{"id": "c", "entity_id": "climate.x", "title": "空调", "icon": "thermostat", "span": 1}]}
        layout = p.normalize_layout(old)
        self.assertEqual(len(layout["pages"]), 2)
        self.assertEqual(layout["refresh_seconds"], 60)
        self.assertEqual(layout["power_mode"], "always-refresh")
        self.assertEqual([t["id"] for t in p.iter_tiles(layout)], ["t0", "t1", "t2", "t3", "t4", "c"])
        climate = p.find_tile(layout, "c")
        self.assertEqual((climate["w"], climate["x"], climate["y"]), (2, 0, 1))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.layout = p.default_layout()
        self.switch, _, self.climate = p.iter_tiles(self.layout)

    def test_services_are_scoped_to_saved_tiles(self):
        self.assertEqual(p.service_for_action(self.switch, "power", True, {"state": "off"}),
                         ("switch", "turn_on", {"entity_id": self.switch["entity_id"]}))
        for action, value in (("power", "on"), ("unlock", True), ("temperature", 23)):
            with self.assertRaises(p.ProtocolError):
                p.service_for_action(self.switch, action, value, {"state": "on"})
        with self.assertRaises(p.ProtocolError):
            p.service_for_action(self.switch, "power", True, {"state": "unavailable"})

    def test_buttons_press_and_scenes_turn_on(self):
        button = {"entity_id": "input_button.bell"}
        self.assertEqual(p.service_for_action(button, "activate", None, {"state": "unknown"})[1], "press")
        self.assertEqual(p.service_for_action({"entity_id": "scene.x"}, "activate", None, {"state": "x"})[1], "turn_on")

    def test_temperature_enforces_live_range_and_step(self):
        state = {"state": "cool", "attributes": {"min_temp": 16, "max_temp": 30, "target_temp_step": .5}}
        self.assertEqual(p.service_for_action(self.climate, "temperature", 24.5, state)[2]["temperature"], 24.5)
        for value in (True, 31, 24.2, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(p.ProtocolError):
                p.service_for_action(self.climate, "temperature", value, state)
        with self.assertRaises(p.ProtocolError):
            p.service_for_action(self.climate, "temperature", 24, {**state, "state": "off"})

    def test_modes_must_be_supported(self):
        state = {"state": "cool", "attributes": {"hvac_modes": ["off", "cool"]}}
        self.assertEqual(p.service_for_action(self.climate, "mode", "off", state)[1:],
                         ("set_hvac_mode", {"entity_id": "climate.bedroom", "hvac_mode": "off"}))
        with self.assertRaises(p.ProtocolError):
            p.service_for_action(self.climate, "mode", "heat", state)

    def test_celsius_panel_controls_a_fahrenheit_system(self):
        state = {"state": "cool", "attributes": {"temperature": 75, "min_temp": 61, "max_temp": 86,
                                                 "target_temp_step": 1, "current_temperature": 78.4}}
        view = p.climate_view(state["attributes"], "°F", "°C")
        self.assertEqual((view["temperature"], view["step"], view["current_temperature"]), (24.0, 0.5, 25.8))
        temperatures = []
        for _ in range(4):
            target = p.service_for_action(self.climate, "temperature", view["temperature"] + view["step"],
                                          state, "°F", "°C")[2]["temperature"]
            temperatures.append(target)
            state["attributes"]["temperature"] = target
            view = p.climate_view(state["attributes"], "°F", "°C")
        self.assertEqual(temperatures, [76, 77, 78, 79])
        down = p.service_for_action(self.climate, "temperature", view["temperature"] - view["step"], state, "°F", "°C")
        self.assertEqual(down[2]["temperature"], 78)

    def test_same_unit_grid_is_anchored_at_min_temp(self):
        view = p.climate_view({"temperature": 24.5, "min_temp": 16.5, "max_temp": 30.5, "target_temp_step": 1},
                              "°C", "°C")
        self.assertEqual(view["temperature"], 24.5)


class DisplayTests(unittest.TestCase):
    def view(self, entity_id, state, unit="°C", **attributes):
        return d.tile_view({"id": "t", "entity_id": entity_id}, {"state": state, "attributes": attributes,
                                                                  "precision": attributes.pop("precision", None)},
                           "°C", unit)

    def test_states_are_translated(self):
        self.assertEqual(self.view("binary_sensor.door", "on", device_class="door")["text"], "已打开")
        self.assertEqual(self.view("binary_sensor.pir", "off", device_class="motion")["text"], "无人")
        self.assertEqual(self.view("lock.front", "locked")["text"], "已上锁")
        self.assertEqual(self.view("cover.curtain", "closed")["text"], "已关闭")
        self.assertEqual(self.view("switch.x", "on")["text"], "开启")
        self.assertEqual(self.view("switch.x", "unavailable")["text"], "离线")

    def test_numbers_respect_precision_and_temperature_unit(self):
        self.assertEqual(self.view("sensor.t", "25.84444", unit_of_measurement="°C")["text"], "25.84")
        self.assertEqual(self.view("sensor.t", "25.84444", unit_of_measurement="°C", precision=1)["text"], "25.8")
        fahrenheit = self.view("sensor.t", "25", "°F", unit_of_measurement="°C")
        self.assertEqual((fahrenheit["text"], fahrenheit["unit"]), ("77.0", "°F"))
        self.assertEqual(self.view("sensor.p", "1200", unit_of_measurement="W")["unit"], "W")

    def test_snapshot_does_not_expose_arbitrary_attributes(self):
        view = self.view("switch.x", "on", secret="not-for-the-device", latitude=1)
        self.assertNotIn("not-for-the-device", repr(view))

    def test_section_summary(self):
        section = {"tiles": [{"id": "a", "entity_id": "light.a", "icon": "bulb"},
                             {"id": "b", "entity_id": "light.b", "icon": "bulb"},
                             {"id": "t", "entity_id": "sensor.t", "icon": "temperature"}]}
        views = {"a": self.view("light.a", "on"), "b": self.view("light.b", "off"),
                 "t": self.view("sensor.t", "21.5", unit_of_measurement="°C")}
        self.assertEqual(d.section_summary(section, views), "1 盏灯开着 · 21.5°C")


class PairingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
