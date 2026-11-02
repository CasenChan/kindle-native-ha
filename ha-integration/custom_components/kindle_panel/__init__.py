"""Native Kindle control panels with an HA-hosted visual editor."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import time

from aiohttp import web
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import KEY_HASS, HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store

from .protocol import (
    DEFAULT_LAYOUT, DOMAIN, Pairing, ProtocolError, authenticate, geometry,
    normalize_layout, public_state, service_for_action,
)

# Use the validator actually used by HA's WebSocket layer across its migration.
vol = getattr(websocket_api.decorators, "vol", None) or websocket_api.decorators.probatio

PANEL_PATH = "kindle-panel"
API_PATH = "/api/kindle_panel"


class Runtime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass, self.entry = hass, entry
        self.store = Store(hass, 1, DOMAIN)
        self.layout = normalize_layout(deepcopy(DEFAULT_LAYOUT))
        self.revision = 1
        self.devices: dict[str, dict] = {}
        self.pairing = Pairing()
        self.lock = asyncio.Lock()

    async def load(self):
        if data := await self.store.async_load():
            self.layout = normalize_layout(data.get("layout", self.layout))
            self.revision = max(1, int(data.get("revision", 1)))
            self.devices = data.get("devices", {})

    def stored(self):
        return {"layout": self.layout, "revision": self.revision, "devices": self.devices}

    async def save(self):
        await self.store.async_save(self.stored())

    @staticmethod
    def device_public(device):
        return {key: device.get(key) for key in ("id", "name", "width", "height", "last_seen", "battery", "charging")}

    def state_for(self, entity_id):
        state = self.hass.states.get(entity_id)
        return {"state": state.state, "attributes": dict(state.attributes)} if state else None

    def states_for(self, owner, layout=None):
        result = {}
        for tile in (layout or self.layout)["tiles"]:
            allowed = owner.permissions.check_entity(tile["entity_id"], POLICY_READ)
            result[tile["id"]] = public_state(tile, self.state_for(tile["entity_id"]) if allowed else None)
        return result

    def admin_data(self, owner):
        devices = [self.device_public(item) for item in self.devices.values()]
        screen = devices[0] if devices else {"width": 758, "height": 1024}
        return {"layout": self.layout, "revision": self.revision, "devices": devices,
                "geometry": geometry(self.layout, screen["width"], screen["height"]),
                "states": self.states_for(owner), "temperature_unit": str(self.hass.config.units.temperature_unit)}

    async def auth_device(self, key):
        device = authenticate(self.devices, key)
        if device is None:
            raise web.HTTPUnauthorized(text='{"error":"not_paired"}', content_type="application/json")
        owner = await self.hass.auth.async_get_user(device["owner_id"])
        if owner is None or not owner.is_active:
            raise web.HTTPUnauthorized(text='{"error":"owner_unavailable"}', content_type="application/json")
        return device, owner


def runtime(hass):
    instance = hass.data.get(DOMAIN)
    if not isinstance(instance, Runtime):
        raise web.HTTPServiceUnavailable(text="Kindle Panel is not configured")
    return instance


async def read_json(request):
    # StreamReader.read(n) may return a partial TCP chunk, not the full body.
    chunks, size = [], 0
    while True:
        chunk = await request.content.read(4097 - size)
        if not chunk:
            break
        size += len(chunk)
        if size > 4096:
            raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=size)
        chunks.append(chunk)
    data = b"".join(chunks)
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError) as err:
        raise web.HTTPBadRequest(text="Invalid JSON") from err
    if not isinstance(value, dict):
        raise web.HTTPBadRequest(text="JSON object required")
    return value


class PairView(HomeAssistantView):
    url = API_PATH + "/pair"
    name = "api:kindle_panel:pair"
    requires_auth = False

    async def post(self, request):
        manager = runtime(request.app[KEY_HASS])
        body = await read_json(request)
        async with manager.lock:
            if len(manager.devices) >= 5:
                return web.json_response({"error": "请先移除不用的设备"}, status=400)
            try:
                device, key = manager.pairing.consume(body.get("code"), body.get("name", "Kindle"),
                                                       body.get("width", 758), body.get("height", 1024))
            except (ProtocolError, TypeError) as err:
                return web.json_response({"error": str(err)}, status=400)
            owner = await manager.hass.auth.async_get_user(device["owner_id"])
            if owner is None or not owner.is_active:
                return web.json_response({"error": "配对用户不可用"}, status=403)
            manager.devices[device["id"]] = device
            await manager.save()
            dr.async_get(manager.hass).async_get_or_create(
                config_entry_id=manager.entry.entry_id, identifiers={(DOMAIN, device["id"])},
                name=device["name"], manufacturer="Amazon", model="Kindle native panel",
                configuration_url="homeassistant://kindle-panel",
            )
        return web.json_response({"device_key": key, "device_id": device["id"]})


class SnapshotView(HomeAssistantView):
    url = API_PATH + "/device/snapshot"
    name = "api:kindle_panel:snapshot"
    requires_auth = False

    async def post(self, request):
        manager = runtime(request.app[KEY_HASS])
        device, owner = await manager.auth_device(request.headers.get("X-Kindle-Key"))
        body = await read_json(request)
        device["last_seen"] = time.time()
        battery = body.get("battery")
        if type(battery) in {int, float} and 0 <= battery <= 100:
            device["battery"] = battery
        if type(body.get("charging")) is bool:
            device["charging"] = body["charging"]
        width, height = body.get("width"), body.get("height")
        if type(width) is int and type(height) is int and 400 <= width <= 2732 and 400 <= height <= 2732:
            device["width"], device["height"] = width, height
        manager.store.async_delay_save(manager.stored, 30)
        return web.json_response({"revision": manager.revision, "layout": manager.layout,
                                  "geometry": geometry(manager.layout, device["width"], device["height"]),
                                  "states": manager.states_for(owner), "device": manager.device_public(device),
                                  "temperature_unit": str(manager.hass.config.units.temperature_unit)})


class ActionView(HomeAssistantView):
    url = API_PATH + "/device/action"
    name = "api:kindle_panel:action"
    requires_auth = False

    async def post(self, request):
        manager = runtime(request.app[KEY_HASS])
        device, owner = await manager.auth_device(request.headers.get("X-Kindle-Key"))
        body = await read_json(request)
        if body.get("revision") != manager.revision:
            return web.json_response({"error": "布局已更新，请刷新后操作"}, status=409)
        tile = next((tile for tile in manager.layout["tiles"] if tile["id"] == body.get("tile_id")), None)
        if tile is None:
            return web.json_response({"error": "卡片不存在"}, status=404)
        if not owner.permissions.check_entity(tile["entity_id"], POLICY_CONTROL):
            return web.json_response({"error": "没有控制该设备的权限"}, status=403)
        try:
            domain, service, fields = service_for_action(tile, body.get("action"), body.get("value"),
                                                        manager.state_for(tile["entity_id"]))
            await manager.hass.services.async_call(domain, service, fields, blocking=True,
                                                    context=Context(user_id=owner.id))
        except (ProtocolError, HomeAssistantError, ValueError, TypeError):
            return web.json_response({"error": "设备未能执行，请刷新状态后重试"}, status=400)
        device["last_seen"] = time.time()
        return web.json_response({"accepted": True})


@websocket_api.websocket_command({
    "type": "kindle_panel/manage", vol.Required("action"): vol.In(["load", "preview", "save", "pair", "revoke"]),
    vol.Optional("layout"): dict, vol.Optional("revision"): int, vol.Optional("device_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_manage(hass, connection, msg):
    manager = runtime(hass)
    try:
        async with manager.lock:
            action = msg["action"]
            if action == "preview":
                layout = normalize_layout(msg.get("layout"))
                device = manager.devices.get(msg.get("device_id"), {"width": 758, "height": 1024})
                connection.send_result(msg["id"], {
                    "layout": layout, "states": manager.states_for(connection.user, layout),
                    "geometry": geometry(layout, device["width"], device["height"]),
                    "temperature_unit": str(hass.config.units.temperature_unit),
                })
                return
            if action == "save":
                if msg.get("revision") != manager.revision:
                    raise ProtocolError("布局已被更新，请重新加载后再保存")
                layout = normalize_layout(msg.get("layout"))
                if any(hass.states.get(tile["entity_id"]) is None for tile in layout["tiles"]):
                    raise ProtocolError("布局中有不存在的实体，请重新选择")
                manager.layout = layout
                manager.revision += 1
                await manager.save()
            elif action == "pair":
                connection.send_result(msg["id"], manager.pairing.create(connection.user.id))
                return
            elif action == "revoke":
                manager.devices.pop(msg.get("device_id"), None)
                await manager.save()
            connection.send_result(msg["id"], manager.admin_data(connection.user))
    except ProtocolError as err:
        connection.send_error(msg["id"], "invalid_layout", str(err))


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await hass.http.async_register_static_paths([
        StaticPathConfig("/kindle_panel_static", str(Path(__file__).parent / "frontend"), cache_headers=True)
    ])
    for view in (PairView(), SnapshotView(), ActionView()):
        hass.http.register_view(view)
    websocket_api.async_register_command(hass, websocket_manage)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = Runtime(hass, entry)
    await manager.load()
    hass.data[DOMAIN] = manager
    await panel_custom.async_register_panel(
        hass, frontend_url_path=PANEL_PATH, webcomponent_name="kindle-panel-editor",
        sidebar_title="Kindle 面板", sidebar_icon="mdi:tablet-dashboard",
        module_url="/kindle_panel_static/editor.js?v=0.2.0", require_admin=True,
        config_panel_domain=DOMAIN,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = hass.data.pop(DOMAIN, None)
    if isinstance(manager, Runtime):
        await manager.save()
    frontend.async_remove_panel(hass, PANEL_PATH)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Removing the integration also revokes its paired-device keys."""
    await Store(hass, 1, DOMAIN).async_remove()
