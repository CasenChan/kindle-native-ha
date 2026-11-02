"""Validated, HA-independent layout and device protocol."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import math
import re
import secrets
import time

DOMAIN = "kindle_panel"
ICONS = ("bulb", "thermostat", "temperature", "humidity", "power", "fan", "home", "scene", "plug", "sensor")
DEFAULT_LAYOUT = {
    "title": "我的家", "columns": 2, "rows": 3, "refresh_seconds": 30,
    "power_mode": "external-refresh",
    "tiles": [
        {"id": "light-left", "entity_id": "switch.room_light_left", "title": "房间灯左键", "icon": "bulb", "span": 1},
        {"id": "light-right", "entity_id": "switch.room_light_right", "title": "房间灯右键", "icon": "bulb", "span": 1},
        {"id": "climate", "entity_id": "climate.bedroom", "title": "卧室空调", "icon": "thermostat", "span": 2},
    ],
}


class ProtocolError(ValueError):
    """User-visible validation failure."""


def kind_for_entity(entity_id: str) -> str:
    domain = entity_id.partition(".")[0]
    if domain in {"switch", "light", "fan"}:
        return "toggle"
    if domain == "climate":
        return "climate"
    if domain in {"scene", "script", "button"}:
        return "action"
    return "sensor"


def integer(value, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ProtocolError(f"{name}超出支持范围")
    return value


def label(value, default: str, limit: int = 40) -> str:
    if value is None:
        value = default
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise ProtocolError("名称格式有误")
    value = value.strip()
    if not value or len(value) > limit:
        raise ProtocolError("名称过长或为空")
    return value


def normalize_layout(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ProtocolError("布局格式有误")
    columns = integer(data.get("columns", 2), 1, 2, "列数")
    rows = integer(data.get("rows", 3), 2, 4, "行数")
    interval = integer(data.get("refresh_seconds", 30), 15, 300, "刷新间隔")
    power_mode = data.get("power_mode", "external-refresh")
    if power_mode not in {"external-refresh", "always-refresh"}:
        raise ProtocolError("常驻方式有误")
    source = data.get("tiles")
    if not isinstance(source, list) or not 1 <= len(source) <= 24:
        raise ProtocolError("请选择 1 至 24 张卡片")
    seen, tiles = set(), []
    for item in source:
        if not isinstance(item, dict):
            raise ProtocolError("卡片格式有误")
        tile_id, entity_id = item.get("id"), item.get("entity_id")
        if not isinstance(tile_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", tile_id) or tile_id in seen:
            raise ProtocolError("卡片编号重复或无效")
        if not isinstance(entity_id, str) or not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", entity_id):
            raise ProtocolError("实体编号有误")
        icon = item.get("icon", "sensor")
        if icon not in ICONS:
            raise ProtocolError("请选择支持的图标")
        kind = kind_for_entity(entity_id)
        span = min(columns, integer(item.get("span", 1), 1, 2, "卡片宽度"))
        if kind == "climate":
            span = columns
        seen.add(tile_id)
        tiles.append({"id": tile_id, "entity_id": entity_id, "title": label(item.get("title"), entity_id),
                      "icon": icon, "kind": kind, "span": span})
    return {"title": label(data.get("title"), "我的家", 24), "columns": columns, "rows": rows,
            "refresh_seconds": interval, "power_mode": power_mode, "tiles": tiles}


def geometry(layout: dict, width: int = 758, height: int = 1024) -> dict:
    integer(width, 400, 2732, "屏幕宽度")
    integer(height, 400, 2732, "屏幕高度")
    scale = min(width / 758, height / 1024)
    margin, gap = round(20 * scale), round(16 * scale)
    header, footer = round(108 * scale), round(60 * scale)
    columns, rows = layout["columns"], layout["rows"]
    cell_w = (width - margin * 2 - gap * (columns - 1)) // columns
    cell_h = (height - header - footer - margin - gap * (rows - 1)) // rows
    page = row = column = 0
    cards = []
    for tile in layout["tiles"]:
        span = tile["span"]
        if column + span > columns:
            row, column = row + 1, 0
        if row >= rows:
            page, row, column = page + 1, 0, 0
        factor = scale * min(1, cell_h / (250 * scale))
        icon_size, title_font, value_font = round(64 * factor), round(25 * factor), round(38 * factor)
        content_height = icon_size + title_font + value_font + round(28 * factor)
        icon_y = max(round(14 * factor), (cell_h - content_height) // 2)
        pad, control_h = round(28 * factor), round(60 * factor)
        metrics = {"pad": pad, "icon_size": icon_size, "icon_y": icon_y,
                   "title_y": icon_y + icon_size + round(14 * factor),
                   "value_y": icon_y + icon_size + title_font + round(28 * factor),
                   "title_font": title_font, "value_font": value_font, "small_font": round(19 * factor),
                   "climate_icon_size": round(48 * factor),
                   "climate_title_x": pad + round(68 * factor),
                   "mode_y": pad + title_font + round(3 * factor),
                   "current_y": cell_h - control_h - round(104 * factor),
                   "climate_value_font": round(45 * factor), "label_font": round(17 * factor),
                   "control_h": control_h, "control_font": round(28 * factor)}
        cards.append({"id": tile["id"], "page": page, "x": margin + column * (cell_w + gap),
                      "y": header + row * (cell_h + gap), "w": span * cell_w + (span - 1) * gap, "h": cell_h,
                      "metrics": metrics})
        column += span
        if column >= columns:
            row, column = row + 1, 0
    return {"width": width, "height": height, "pages": page + 1, "cards": cards,
            "margin": margin, "header": header, "footer": footer,
            "fonts": {"header": round(34 * scale), "title": round(25 * scale),
                      "value": round(38 * scale), "small": round(20 * scale)}, "icon_size": round(64 * scale)}


def finite_number(value):
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ProtocolError("数值无效")
    return value


def service_for_action(tile: dict, action: str, value, state: dict | None) -> tuple[str, str, dict]:
    """Return only an allowlisted service for the stored tile, never client-supplied IDs."""
    entity_id = tile["entity_id"]
    domain = entity_id.partition(".")[0]
    kind = kind_for_entity(entity_id)
    if not state or state.get("state") == "unavailable" or (state.get("state") == "unknown" and kind != "action"):
        raise ProtocolError("设备暂不可用")
    fields = {"entity_id": entity_id}
    if kind == "toggle" and action == "power" and type(value) is bool:
        return domain, "turn_on" if value else "turn_off", fields
    if kind == "climate":
        attr = state.get("attributes") or {}
        if action == "power" and type(value) is bool:
            return "climate", "turn_on" if value else "turn_off", fields
        if action == "temperature":
            target = finite_number(value)
            low, high = finite_number(attr.get("min_temp")), finite_number(attr.get("max_temp"))
            step = finite_number(attr.get("target_temp_step", 1))
            if step <= 0 or not low <= target <= high or state["state"] == "off":
                raise ProtocolError("温度超出范围，或空调已关机")
            steps = (target - low) / step
            if abs(steps - round(steps)) > 0.00001:
                raise ProtocolError("温度步长不受支持")
            return "climate", "set_temperature", {**fields, "temperature": target}
        if action == "mode" and isinstance(value, str) and value in (attr.get("hvac_modes") or []):
            return "climate", "set_hvac_mode", {**fields, "hvac_mode": value}
    if kind == "action" and action == "activate" and value is None:
        return domain, "press" if domain == "button" else "turn_on", fields
    raise ProtocolError("此卡片不支持该操作")


def public_state(tile: dict, state: dict | None) -> dict:
    if state is None:
        return {"state": "unavailable", "available": False, "attributes": {}}
    attributes = state.get("attributes") or {}
    allowed = ("unit_of_measurement",)
    if tile["kind"] == "climate":
        allowed += ("temperature", "current_temperature", "min_temp", "max_temp", "target_temp_step",
                    "hvac_modes", "fan_mode", "swing_mode")
    return {"state": str(state.get("state", "unknown")),
            "available": state.get("state") != "unavailable" and (state.get("state") != "unknown" or tile["kind"] == "action"),
            "attributes": {key: deepcopy(attributes[key]) for key in allowed if key in attributes}}


def token_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class Pairing:
    """One-use pairing codes; only device-key hashes are persisted."""
    def __init__(self, now=time.time):
        self.now = now
        self.pending: dict | None = None

    def create(self, owner_id: str) -> dict:
        self.pending = {"code": secrets.token_urlsafe(18), "owner_id": owner_id, "expires": self.now() + 600}
        return {"code": self.pending["code"], "expires": self.pending["expires"]}

    def consume(self, code: str, name: str, width: int, height: int) -> tuple[dict, str]:
        pending = self.pending
        if (not pending or self.now() > pending["expires"] or not isinstance(code, str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]{24}", code)
                or not hmac.compare_digest(code, pending["code"])):
            raise ProtocolError("配对码无效或已过期")
        integer(width, 400, 2732, "屏幕宽度")
        integer(height, 400, 2732, "屏幕高度")
        name = label(name, "Kindle", 40)
        device_id, secret = secrets.token_hex(12), secrets.token_urlsafe(32)
        device = {"id": device_id, "name": name, "owner_id": pending["owner_id"],
                  "key_hash": token_hash(secret), "width": width, "height": height, "last_seen": 0,
                  "battery": None, "charging": False}
        self.pending = None
        return device, device_id + "." + secret


def authenticate(devices: dict, key: str | None) -> dict | None:
    if not isinstance(key, str) or len(key) > 200:
        return None
    device_id, separator, secret = key.partition(".")
    device = devices.get(device_id)
    if not separator or not device:
        return None
    return device if hmac.compare_digest(token_hash(secret), device.get("key_hash", "")) else None
