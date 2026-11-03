from copy import deepcopy
import hashlib

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.kindle_panel.protocol import DOMAIN, VERSION

LAYOUT = {
    "pages": [{"id": "home", "title": "家", "columns": 2, "sections": [
        {"id": "living", "title": "客厅", "rows": 3, "tiles": [
            {"id": "lamp", "entity_id": "light.lamp", "title": "台灯"},
            {"id": "ac", "entity_id": "climate.ac", "title": "空调", "w": 2},
            {"id": "door", "entity_id": "lock.door", "title": "门锁"},
        ]}]}],
}


async def setup(hass, hass_ws_client):
    await async_setup_component(hass, "http", {})
    hass.states.async_set("light.lamp", "off", {"friendly_name": "台灯", "supported_color_modes": ["brightness"]})
    hass.states.async_set("climate.ac", "cool", {"temperature": 75, "current_temperature": 78, "min_temp": 61,
                                                 "max_temp": 86, "target_temp_step": 1, "hvac_modes": ["off", "cool"]})
    hass.states.async_set("lock.door", "locked", {})
    entry = MockConfigEntry(domain=DOMAIN, title="Kindle")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ws = await hass_ws_client(hass)
    return entry, ws


async def manage(ws, action, **values):
    await ws.send_json({"id": manage.counter, "type": "kindle_panel/manage", "action": action, **values})
    manage.counter += 1
    return await ws.receive_json()
manage.counter = 1


async def pair(hass, ws, client):
    code = (await manage(ws, "pair"))["result"]["code"]
    response = await client.post("/api/kindle_panel/pair", json={"code": code, "name": "测试 Kindle", "width": 758, "height": 1024})
    assert response.status == 200
    return (await response.json())["device_key"]


async def test_full_device_flow(hass, hass_ws_client, hass_client_no_auth):
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry, ws = await setup(hass, hass_ws_client)
    loaded = await manage(ws, "load")
    assert loaded["success"] and loaded["result"]["frame"]["protocol"] == 2
    saved = await manage(ws, "save", layout={**LAYOUT, "temperature_unit": "°C"}, revision=loaded["result"]["revision"])
    assert saved["success"], saved
    revision = saved["result"]["revision"]

    client = await hass_client_no_auth()
    key = await pair(hass, ws, client)
    headers = {"X-Kindle-Key": key}
    frame = await (await client.post("/api/kindle_panel/device/snapshot", headers=headers,
                                     json={"battery": 80, "charging": True, "plugin_version": "0.3.0"})).json()
    assert frame["revision"] == revision and frame["temperature_unit"] == "°C"
    assert frame["plugin"] == {"version": VERSION, "update": False, "allowed": False}
    assert "friendly_name" not in str(frame)
    hits = {(h.get("tile"), h.get("action"), h.get("value")) for page in frame["pages"] for h in page["hits"]}
    assert ("lamp", "power", True) in hits and ("ac", "temperature", 24.5) in hits
    assert not [h for h in hits if h[0] == "door"], "unlock must be opt-in"

    turn_on = async_mock_service(hass, "light", "turn_on")
    set_temperature = async_mock_service(hass, "climate", "set_temperature")
    for body in ({"tile_id": "lamp", "action": "power", "value": True},
                 {"tile_id": "ac", "action": "temperature", "value": 24.5}):
        response = await client.post("/api/kindle_panel/device/action", headers=headers, json={"revision": revision, **body})
        assert response.status == 200, await response.text()
    assert turn_on[0].data == {"entity_id": "light.lamp"}
    assert set_temperature[0].data["temperature"] == 76

    rejected = await client.post("/api/kindle_panel/device/action", headers=headers,
                                 json={"revision": revision, "tile_id": "door", "action": "lock", "value": False})
    assert rejected.status == 400
    stale = await client.post("/api/kindle_panel/device/action", headers=headers,
                              json={"revision": revision - 1, "tile_id": "lamp", "action": "power", "value": True})
    assert stale.status == 409
    assert (await client.post("/api/kindle_panel/device/snapshot", json={})).status == 401

    devices = (await manage(ws, "load"))["result"]["devices"]
    assert devices[0]["battery"] == 80 and devices[0]["plugin_version"] == "0.3.0"
    registry = dr.async_get(hass)
    assert registry.async_get_device(identifiers={(DOMAIN, devices[0]["id"])})
    revoked = await manage(ws, "revoke", device_id=devices[0]["id"])
    assert revoked["success"] and revoked["result"]["devices"] == []
    assert registry.async_get_device(identifiers={(DOMAIN, devices[0]["id"])}) is None
    assert (await client.post("/api/kindle_panel/device/snapshot", headers=headers, json={})).status == 401


async def test_backlight_entity_round_trip(hass, hass_ws_client, hass_client_no_auth):
    entry, ws = await setup(hass, hass_ws_client)
    client = await hass_client_no_auth()
    key = await pair(hass, ws, client)
    headers = {"X-Kindle-Key": key}
    await hass.async_block_till_done()
    device_id = (await manage(ws, "load"))["result"]["devices"][0]["id"]
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{device_id}_backlight")
    assert entity_id, "pairing creates the backlight entity"

    frame = await (await client.post("/api/kindle_panel/device/snapshot", headers=headers, json={"backlight": 30})).json()
    await hass.async_block_till_done()
    assert frame["backlight_target"] is None
    assert hass.states.get(entity_id).state == "30"

    await hass.services.async_call("number", "set_value", {"entity_id": entity_id, "value": 65}, blocking=True)
    assert hass.states.get(entity_id).state == "65"
    assert hass.states.get(entity_id).attributes["pending"] is True
    frame = await (await client.post("/api/kindle_panel/device/snapshot", headers=headers, json={"backlight": 30})).json()
    target = frame["backlight_target"]
    assert target["level"] == 65
    # The Kindle applies it and acknowledges the id; the command is cleared and the real level shown.
    frame = await (await client.post("/api/kindle_panel/device/snapshot", headers=headers,
                                     json={"backlight": 63, "backlight_ack": target["id"]})).json()
    await hass.async_block_till_done()
    assert frame["backlight_target"] is None
    assert hass.states.get(entity_id).state == "63"
    assert hass.states.get(entity_id).attributes["pending"] is False

    await manage(ws, "revoke", device_id=device_id)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get(entity_id) is None
    assert hass.states.get(entity_id) is None


async def test_plugin_update_requires_opt_in(hass, hass_ws_client, hass_client_no_auth):
    entry, ws = await setup(hass, hass_ws_client)
    client = await hass_client_no_auth()
    key = await pair(hass, ws, client)
    headers = {"X-Kindle-Key": key}
    assert (await client.post("/api/kindle_panel/device/update/manifest", headers=headers, json={})).status == 403
    revision = (await manage(ws, "load"))["result"]["revision"]
    assert (await manage(ws, "save", layout={**LAYOUT, "allow_update": True}, revision=revision))["success"]
    frame = await (await client.post("/api/kindle_panel/device/snapshot", headers=headers,
                                     json={"plugin_version": "0.3.0"})).json()
    assert frame["plugin"]["update"] is True
    manifest = await (await client.post("/api/kindle_panel/device/update/manifest", headers=headers, json={})).json()
    assert manifest["version"] == VERSION
    entry = next(item for item in manifest["files"] if item["path"] == "plugin/main.lua")
    served = await (await client.post("/api/kindle_panel/device/update/file", headers=headers, json={"path": entry["path"]})).json()
    assert hashlib.sha256(served["content"].encode()).hexdigest() == entry["sha256"]
    for path in ("../__init__.py", "manifest.json", "/etc/passwd", "plugin/../../__init__.py"):
        assert (await client.post("/api/kindle_panel/device/update/file", headers=headers, json={"path": path})).status == 404
    assert (await client.post("/api/kindle_panel/device/update/manifest", json={})).status == 401


async def test_editor_validation_and_v1_migration(hass, hass_ws_client, hass_storage):
    hass_storage[DOMAIN] = {"version": 1, "key": DOMAIN, "data": {"revision": 4, "devices": {}, "layout": {
        "title": "旧布局", "columns": 2, "rows": 3, "refresh_seconds": 60,
        "tiles": [{"id": "a", "entity_id": "light.lamp", "title": "台灯", "icon": "bulb", "span": 1}]}}}
    entry, ws = await setup(hass, hass_ws_client)
    loaded = (await manage(ws, "load"))["result"]
    assert loaded["revision"] == 4 and loaded["layout"]["pages"][0]["title"] == "旧布局"
    assert loaded["layout"]["refresh_seconds"] == 60
    bad = deepcopy(LAYOUT)
    bad["pages"][0]["sections"][0]["tiles"][0]["entity_id"] = "light.missing"
    result = await manage(ws, "save", layout=bad, revision=4)
    assert not result["success"] and "不存在" in result["error"]["message"]
    conflict = await manage(ws, "save", layout=LAYOUT, revision=3)
    assert not conflict["success"]
    preview = await manage(ws, "preview", layout={**LAYOUT, "temperature_unit": "°F"})
    assert preview["success"] and preview["result"]["frame"]["temperature_unit"] == "°F"


async def test_unload_and_remove(hass, hass_ws_client, hass_storage, no_frontend):
    entry, ws = await setup(hass, hass_ws_client)
    assert no_frontend.call_args.kwargs["frontend_url_path"] == "kindle-panel"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN not in hass_storage or not hass_storage[DOMAIN]
