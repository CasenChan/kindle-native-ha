"""Native Kindle control panels with an HA-hosted visual editor."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import logging
from pathlib import Path
import re
import time

from aiohttp import web
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import KEY_HASS, HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.storage import Store

from .protocol import (
    DOMAIN, ICONS, VERSION, Pairing, ProtocolError, authenticate, default_layout, display_unit, find_tile,
    iter_tiles, normalize_layout, service_for_action,
)
from .number import SIGNAL_NEW_DEVICE, signal_device_updated
from .render import snapshot

_LOGGER = logging.getLogger(__name__)
# Use the validator actually used by HA's WebSocket layer across its migration.
vol = getattr(websocket_api.decorators, "vol", None) or websocket_api.decorators.probatio

PANEL_PATH = "kindle-panel"
NATIVE_DIR = Path(__file__).parent / "native"
PLUGIN_VERSION = re.compile(r"\d+(\.\d+){1,3}")
API_PATH = "/api/kindle_panel"
DEFAULT_SCREEN = {"width": 758, "height": 1024}
MAX_DEVICES = 5
PLATFORMS = ["number"]


class Runtime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass, self.entry = hass, entry
        self.store = Store(hass, 1, DOMAIN)
        self.layout = default_layout()
        self.revision = 1
        self.devices: dict[str, dict] = {}
        self.pairing = Pairing()
        self.lock = asyncio.Lock()

    async def load(self):
        if data := await self.store.async_load():
            self.revision = max(1, int(data.get("revision", 1)))
            self.devices = data.get("devices", {})
            try:
                self.layout = normalize_layout(data.get("layout", self.layout))
            except ProtocolError as err:
                _LOGGER.warning("Stored Kindle layout is invalid (%s); using the example layout", err)

    def stored(self):
        return {"layout": self.layout, "revision": self.revision, "devices": self.devices}

    async def save(self):
        await self.store.async_save(self.stored())

    @property
    def system_unit(self) -> str:
        return str(self.hass.config.units.temperature_unit)

    @staticmethod
    def device_public(device):
        return {key: device.get(key) for key in
                ("id", "name", "width", "height", "last_seen", "battery", "charging", "revision",
                 "plugin_version", "backlight")}

    def state_for(self, entity_id):
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        precision = None
        if entry := er.async_get(self.hass).async_get(entity_id):
            options = entry.options.get("sensor") or {}
            value = options.get("display_precision", options.get("suggested_display_precision"))
            precision = value if type(value) is int else None
        return {"state": state.state, "attributes": dict(state.attributes), "precision": precision}

    def states_for(self, owner, layout):
        """Raw states of the layout's entities that the pairing owner may read; others look unavailable."""
        return {tile["entity_id"]: self.state_for(tile["entity_id"])
                for tile in iter_tiles(layout) if owner.permissions.check_entity(tile["entity_id"], POLICY_READ)}

    def frame(self, owner, layout, screen):
        return snapshot(layout, self.revision, self.states_for(owner, layout), self.system_unit,
                        screen["width"], screen["height"])

    def suggested_url(self):
        """The LAN URL a Kindle can reach; the device client only speaks plain HTTP."""
        try:
            url = get_url(self.hass, allow_external=False, allow_cloud=False, prefer_external=False)
        except NoURLAvailableError:
            return None
        return url if url.startswith("http://") else None

    def admin_data(self, owner, layout=None, device_id=None):
        layout = layout or self.layout
        screen = self.devices.get(device_id) or next(iter(self.devices.values()), DEFAULT_SCREEN)
        frame, views = self.frame(owner, layout, screen)
        return {"layout": layout, "revision": self.revision, "frame": frame, "views": views,
                "devices": [self.device_public(item) for item in self.devices.values()],
                "system_unit": self.system_unit, "suggested_url": self.suggested_url(),
                "icons": list(ICONS), "version": VERSION, "now": time.time()}

    async def set_backlight(self, device_id, level):
        """Queue a backlight command; the Kindle applies it on its next snapshot and acknowledges the id."""
        device = self.devices.get(device_id)
        if device is None:
            return
        # Small per-device sequence numbers survive any JSON number encoding on the Kindle side.
        device["backlight_seq"] = device.get("backlight_seq", 0) + 1
        device["backlight_target"] = {"id": device["backlight_seq"], "level": max(0, min(100, int(level)))}
        await self.save()
        async_dispatcher_send(self.hass, signal_device_updated(device_id))

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
            if len(manager.devices) >= MAX_DEVICES:
                return web.json_response({"error": "已配对 5 台设备，请先在 HA 网页撤销不用的设备"}, status=400)
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
            async_dispatcher_send(manager.hass, SIGNAL_NEW_DEVICE, device["id"])
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
        backlight, ack, target = body.get("backlight"), body.get("backlight_ack"), device.get("backlight_target")
        if type(backlight) in {int, float} and 0 <= backlight <= 100:
            device["backlight"] = round(backlight)
        if target and type(ack) in {int, float} and ack >= target["id"]:
            device.pop("backlight_target")
        async_dispatcher_send(manager.hass, signal_device_updated(device["id"]))
        plugin = body.get("plugin_version")
        if isinstance(plugin, str) and PLUGIN_VERSION.fullmatch(plugin):
            device["plugin_version"] = plugin
        device["revision"] = manager.revision
        manager.store.async_delay_save(manager.stored, 30)
        frame, _ = manager.frame(owner, manager.layout, device)
        update = manager.layout["allow_update"] and device.get("plugin_version") not in (None, VERSION)
        return web.json_response({**frame, "device": manager.device_public(device),
                                  "plugin": {"version": VERSION, "update": bool(update),
                                             "allowed": manager.layout["allow_update"]},
                                  "backlight_target": device.get("backlight_target")})


def native_manifest():
    """The plugin bundle shipped inside this integration (written by build.py)."""
    return json.loads((NATIVE_DIR / "manifest.json").read_text(encoding="utf-8"))


class UpdateManifestView(HomeAssistantView):
    url = API_PATH + "/device/update/manifest"
    name = "api:kindle_panel:update_manifest"
    requires_auth = False

    async def post(self, request):
        manager = runtime(request.app[KEY_HASS])
        await manager.auth_device(request.headers.get("X-Kindle-Key"))
        if not manager.layout["allow_update"]:
            return web.json_response({"error": "HA 未开启 Kindle 插件在线更新"}, status=403)
        manifest = await manager.hass.async_add_executor_job(native_manifest)
        return web.json_response(manifest)


class UpdateFileView(HomeAssistantView):
    url = API_PATH + "/device/update/file"
    name = "api:kindle_panel:update_file"
    requires_auth = False

    async def post(self, request):
        manager = runtime(request.app[KEY_HASS])
        await manager.auth_device(request.headers.get("X-Kindle-Key"))
        if not manager.layout["allow_update"]:
            return web.json_response({"error": "HA 未开启 Kindle 插件在线更新"}, status=403)
        body = await read_json(request)
        manifest = await manager.hass.async_add_executor_job(native_manifest)
        # Only files listed in the bundled manifest are served; the path never reaches the filesystem otherwise.
        entry = next((item for item in manifest["files"] if item["path"] == body.get("path")), None)
        if entry is None:
            return web.json_response({"error": "文件不在更新清单中"}, status=404)
        content = await manager.hass.async_add_executor_job(
            (NATIVE_DIR / entry["path"]).read_text, "utf-8")
        return web.json_response({"path": entry["path"], "content": content})


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
        tile = find_tile(manager.layout, body.get("tile_id"))
        if tile is None:
            return web.json_response({"error": "卡片不存在"}, status=404)
        if not owner.permissions.check_entity(tile["entity_id"], POLICY_CONTROL):
            return web.json_response({"error": "没有控制该设备的权限"}, status=403)
        try:
            domain, service, fields = service_for_action(
                tile, body.get("action"), body.get("value"), manager.state_for(tile["entity_id"]),
                manager.system_unit, display_unit(manager.layout, manager.system_unit))
            await manager.hass.services.async_call(domain, service, fields, blocking=True,
                                                    context=Context(user_id=owner.id))
        except (ProtocolError, HomeAssistantError, ValueError, TypeError):
            return web.json_response({"error": "设备未能执行，请刷新状态后重试"}, status=400)
        device["last_seen"] = time.time()
        return web.json_response({"accepted": True})


@websocket_api.websocket_command({
    "type": "kindle_panel/manage",
    vol.Required("action"): vol.In(["load", "preview", "save", "pair", "revoke"]),
    vol.Optional("layout"): dict, vol.Optional("revision"): int, vol.Optional("device_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_manage(hass, connection, msg):
    manager = runtime(hass)
    action, device_id = msg["action"], msg.get("device_id")
    try:
        async with manager.lock:
            if action == "preview":
                layout = normalize_layout(deepcopy(msg.get("layout")))
                connection.send_result(msg["id"], manager.admin_data(connection.user, layout, device_id))
                return
            if action == "pair":
                connection.send_result(msg["id"], manager.pairing.create(connection.user.id))
                return
            if action == "save":
                if msg.get("revision") != manager.revision:
                    raise ProtocolError("布局已被其他页面更新，请重新加载后再保存")
                layout = normalize_layout(deepcopy(msg.get("layout")))
                missing = [tile["title"] for tile in iter_tiles(layout) if hass.states.get(tile["entity_id"]) is None]
                if missing:
                    raise ProtocolError(f"这些卡片的实体不存在：{'、'.join(missing[:3])}")
                manager.layout = layout
                manager.revision += 1
                await manager.save()
            elif action == "revoke":
                if manager.devices.pop(device_id, None) is not None:
                    await manager.save()
                    registry = dr.async_get(hass)
                    if entry := registry.async_get_device(identifiers={(DOMAIN, device_id)}):
                        registry.async_remove_device(entry.id)
            connection.send_result(msg["id"], manager.admin_data(connection.user, device_id=device_id))
    except ProtocolError as err:
        connection.send_error(msg["id"], "invalid_layout", str(err))


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await hass.http.async_register_static_paths([
        StaticPathConfig("/kindle_panel_static", str(Path(__file__).parent / "frontend"), cache_headers=True)
    ])
    for view in (PairView(), SnapshotView(), ActionView(), UpdateManifestView(), UpdateFileView()):
        hass.http.register_view(view)
    websocket_api.async_register_command(hass, websocket_manage)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = Runtime(hass, entry)
    await manager.load()
    hass.data[DOMAIN] = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await panel_custom.async_register_panel(
        hass, frontend_url_path=PANEL_PATH, webcomponent_name="kindle-panel-editor",
        sidebar_title="Kindle 面板", sidebar_icon="mdi:tablet-dashboard",
        module_url=f"/kindle_panel_static/editor.js?v={VERSION}", require_admin=True,
        config_panel_domain=DOMAIN,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    manager = hass.data.pop(DOMAIN, None)
    if isinstance(manager, Runtime):
        await manager.save()
    frontend.async_remove_panel(hass, PANEL_PATH)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Removing the integration also revokes its paired-device keys."""
    await Store(hass, 1, DOMAIN).async_remove()
