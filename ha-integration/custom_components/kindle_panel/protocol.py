"""Validated, HA-independent layout model, device protocol and pairing."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import math
import re
import secrets
import time

DOMAIN = "kindle_panel"
VERSION = "0.5.2"
LAYOUT_VERSION = 2
ICONS = ("bulb", "thermostat", "temperature", "humidity", "power", "fan", "home", "scene", "plug", "sensor",
         "door", "window", "lock", "curtain", "tv", "motion", "battery", "bolt", "music")
TEMPERATURE_UNITS = ("auto", "°C", "°F")
POWER_MODES = ("external-refresh", "always-refresh")
MAX_PAGES, MAX_SECTIONS, MAX_COLUMNS, MAX_PAGE_ROWS, MAX_SECTION_TILES, MAX_TILES = 8, 6, 4, 8, 32, 60

TOGGLE_DOMAINS = {"switch", "light", "fan", "input_boolean", "humidifier"}
ACTION_DOMAINS = {"scene", "script", "button", "input_button"}
COVER_ACTIONS = {"open": "open_cover", "close": "close_cover", "stop": "stop_cover"}
MEDIA_ACTIONS = {"play_pause": "media_play_pause", "next": "media_next_track", "previous": "media_previous_track"}
HOME_TIMEOUTS = (0, 1, 3, 5, 10, 30)
TIME_PATTERN = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
DEFAULT_NIGHT = {"enabled": False, "start": "22:00", "end": "07:00", "level": 10}
TOUCH_TIMEOUTS = (10, 15, 30, 60, 120, 300)
DEFAULT_TOUCH = {"enabled": False, "timeout": 30}
DEFAULT_LAYOUT = {
    "version": LAYOUT_VERSION, "refresh_seconds": 30, "power_mode": "external-refresh", "temperature_unit": "auto",
    "pages": [{"id": "home", "title": "我的家", "columns": 2, "sections": [
        {"id": "living", "title": "", "rows": 3, "summary": True, "tiles": [
            {"id": "light-left", "entity_id": "switch.room_light_left", "title": "房间灯左键", "icon": "bulb"},
            {"id": "light-right", "entity_id": "switch.room_light_right", "title": "房间灯右键", "icon": "bulb"},
            {"id": "climate", "entity_id": "climate.bedroom", "title": "卧室空调", "icon": "thermostat", "w": 2},
        ]},
    ]}],
}
ID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{1,48}")
ENTITY_PATTERN = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+")


class ProtocolError(ValueError):
    """User-visible validation failure."""


def kind_for_entity(entity_id: str) -> str:
    domain = entity_id.partition(".")[0]
    if domain in TOGGLE_DOMAINS:
        return "toggle"
    if domain == "climate":
        return "climate"
    if domain in ACTION_DOMAINS:
        return "action"
    return {"cover": "cover", "media_player": "media", "lock": "lock"}.get(domain, "sensor")


def integer(value, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ProtocolError(f"{name}超出支持范围")
    return value


def label(value, default: str, limit: int = 40, allow_empty: bool = False) -> str:
    if value is None:
        value = default
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise ProtocolError("名称格式有误")
    value = value.strip()
    if len(value) > limit or (not value and not allow_empty):
        raise ProtocolError("名称过长或为空")
    return value


def identifier(value, seen: set, name: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value) or value in seen:
        raise ProtocolError(f"{name}编号重复或无效")
    seen.add(value)
    return value


# ---------------------------------------------------------------- layout model

def migrate_v1(data: dict) -> dict:
    """Convert the 0.2 flat grid (columns/rows/tiles with span) into pages of one untitled section."""
    columns = data.get("columns", 2) if data.get("columns") in (1, 2) else 2
    rows = data.get("rows", 3) if data.get("rows") in (2, 3, 4) else 3
    tiles = data.get("tiles") if isinstance(data.get("tiles"), list) else []
    pages, current, row, column = [], [], 0, 0
    for item in tiles:
        if not isinstance(item, dict):
            raise ProtocolError("卡片格式有误")
        entity_id = item.get("entity_id", "")
        span = columns if kind_for_entity(str(entity_id)) == "climate" else min(columns, item.get("span", 1) if item.get("span") in (1, 2) else 1)
        if column + span > columns:
            row, column = row + 1, 0
        if row >= rows:
            pages.append(current)
            current, row, column = [], 0, 0
        current.append({key: item[key] for key in ("id", "entity_id", "title", "icon") if key in item}
                       | {"w": span, "h": 1, "x": column, "y": row})
        column += span
        if column >= columns:
            row, column = row + 1, 0
    pages.append(current)
    title = data.get("title") if isinstance(data.get("title"), str) and data.get("title").strip() else "我的家"
    return {
        "version": LAYOUT_VERSION, "refresh_seconds": data.get("refresh_seconds", 30),
        "power_mode": data.get("power_mode", "external-refresh"), "temperature_unit": "auto",
        "pages": [{"id": f"page-{index + 1}", "title": title if len(pages) == 1 else f"{title[:12]} {index + 1}",
                   "columns": columns,
                   "sections": [{"id": f"section-{index + 1}", "title": "", "rows": rows, "summary": True,
                                 "tiles": page_tiles}]}
                  for index, page_tiles in enumerate(pages)],
    }


def place_tiles(tiles: list[dict], columns: int, rows: int, section_name: str) -> list[dict]:
    """Keep valid explicit positions, first-fit the rest, return tiles in reading order."""
    used = [[False] * columns for _ in range(rows)]

    def free(x, y, w, h):
        return 0 <= x and 0 <= y and x + w <= columns and y + h <= rows and not any(
            used[row][col] for row in range(y, y + h) for col in range(x, x + w))

    def occupy(tile, x, y):
        for row in range(y, y + tile["h"]):
            for col in range(x, x + tile["w"]):
                used[row][col] = True
        tile["x"], tile["y"] = x, y

    pending = []
    for tile in tiles:
        x, y = tile.get("x"), tile.get("y")
        if type(x) is int and type(y) is int and free(x, y, tile["w"], tile["h"]):
            occupy(tile, x, y)
        else:
            pending.append(tile)
    for tile in pending:
        spot = next(((x, y) for y in range(rows) for x in range(columns) if free(x, y, tile["w"], tile["h"])), None)
        if spot is None:
            raise ProtocolError(f"「{section_name}」放不下所有卡片，请增加行数或缩小卡片")
        occupy(tile, *spot)
    return sorted(tiles, key=lambda tile: (tile["y"], tile["x"]))


def normalize_tile(item, seen: set, columns: int, rows: int) -> dict:
    if not isinstance(item, dict):
        raise ProtocolError("卡片格式有误")
    tile_id = identifier(item.get("id"), seen, "卡片")
    entity_id = item.get("entity_id")
    if not isinstance(entity_id, str) or not ENTITY_PATTERN.fullmatch(entity_id):
        raise ProtocolError("实体编号有误")
    kind = kind_for_entity(entity_id)
    icon = item.get("icon") or default_icon(entity_id)
    if icon not in ICONS:
        raise ProtocolError("请选择支持的图标")
    width = integer(item.get("w", 1), 1, MAX_COLUMNS, "卡片宽度")
    height = integer(item.get("h", 1), 1, MAX_PAGE_ROWS, "卡片高度")
    tile = {"id": tile_id, "entity_id": entity_id, "title": label(item.get("title"), entity_id),
            "icon": icon, "kind": kind, "w": min(width, columns), "h": min(height, rows)}
    for key in ("x", "y"):
        if type(item.get(key)) is int:
            tile[key] = item[key]
    if kind == "lock":
        tile["allow_unlock"] = item.get("allow_unlock") is True
    return tile


def normalize_touch(value) -> dict:
    if value is None:
        return dict(DEFAULT_TOUCH)
    if not isinstance(value, dict):
        raise ProtocolError("触摸点亮设置有误")
    touch = {**DEFAULT_TOUCH, **{key: value[key] for key in DEFAULT_TOUCH if key in value}}
    if type(touch["enabled"]) is not bool or type(touch["timeout"]) is not int or touch["timeout"] not in TOUCH_TIMEOUTS:
        raise ProtocolError("触摸点亮的熄灭时间有误")
    return touch


def normalize_night(value) -> dict:
    if value is None:
        return dict(DEFAULT_NIGHT)
    if not isinstance(value, dict):
        raise ProtocolError("夜间背光设置有误")
    night = {**DEFAULT_NIGHT, **{key: value[key] for key in DEFAULT_NIGHT if key in value}}
    if type(night["enabled"]) is not bool or not all(
            isinstance(night[key], str) and TIME_PATTERN.fullmatch(night[key]) for key in ("start", "end")):
        raise ProtocolError("夜间背光时间格式应为 HH:MM")
    if night["start"] == night["end"]:
        raise ProtocolError("夜间背光的开始和结束时间不能相同")
    integer(night["level"], 0, 100, "夜间亮度")
    return night


def normalize_layout(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ProtocolError("布局格式有误")
    if "pages" not in data and "tiles" in data:
        data = migrate_v1(data)
    interval = integer(data.get("refresh_seconds", 30), 15, 300, "刷新间隔")
    power_mode = data.get("power_mode", "external-refresh")
    if power_mode not in POWER_MODES:
        raise ProtocolError("常驻方式有误")
    unit = data.get("temperature_unit", "auto")
    if unit not in TEMPERATURE_UNITS:
        raise ProtocolError("温度单位有误")
    home_timeout = data.get("home_timeout", 0)
    if home_timeout not in HOME_TIMEOUTS or type(home_timeout) is not int:
        raise ProtocolError("自动回到首页的时间有误")
    night = normalize_night(data.get("night_light"))
    touch = normalize_touch(data.get("touch_light"))
    allow_update = data.get("allow_update", False)
    if type(allow_update) is not bool:
        raise ProtocolError("在线更新设置有误")
    source_pages = data.get("pages")
    if not isinstance(source_pages, list) or not 1 <= len(source_pages) <= MAX_PAGES:
        raise ProtocolError(f"请保留 1 至 {MAX_PAGES} 个页面")
    page_ids, section_ids, tile_ids, pages, total = set(), set(), set(), [], 0
    for page_index, page in enumerate(source_pages, 1):
        if not isinstance(page, dict):
            raise ProtocolError("页面格式有误")
        columns = integer(page.get("columns", 2), 1, MAX_COLUMNS, "列数")
        source_sections = page.get("sections")
        if not isinstance(source_sections, list) or not 1 <= len(source_sections) <= MAX_SECTIONS:
            raise ProtocolError(f"每页需要 1 至 {MAX_SECTIONS} 个分组")
        page_title = label(page.get("title"), f"第 {page_index} 页", 16)
        sections, page_rows = [], 0
        for section_index, section in enumerate(source_sections, 1):
            if not isinstance(section, dict):
                raise ProtocolError("分组格式有误")
            rows = integer(section.get("rows", 2), 1, MAX_PAGE_ROWS, "分组行数")
            page_rows += rows
            title = label(section.get("title"), "", 16, allow_empty=True)
            source_tiles = section.get("tiles", [])
            if not isinstance(source_tiles, list) or len(source_tiles) > MAX_SECTION_TILES:
                raise ProtocolError(f"每个分组最多 {MAX_SECTION_TILES} 张卡片")
            tiles = [normalize_tile(item, tile_ids, columns, rows) for item in source_tiles]
            total += len(tiles)
            name = title or f"{page_title} · 第 {section_index} 组"
            sections.append({"id": identifier(section.get("id"), section_ids, "分组"), "title": title,
                             "rows": rows, "summary": section.get("summary", True) is not False,
                             "tiles": place_tiles(tiles, columns, rows, name)})
        if page_rows > MAX_PAGE_ROWS:
            raise ProtocolError(f"「{page_title}」的分组合计超过 {MAX_PAGE_ROWS} 行，请减少行数或拆分页面")
        pages.append({"id": identifier(page.get("id"), page_ids, "页面"), "title": page_title,
                      "columns": columns, "sections": sections})
    if total < 1 or total > MAX_TILES:
        raise ProtocolError(f"请选择 1 至 {MAX_TILES} 张卡片")
    return {"version": LAYOUT_VERSION, "refresh_seconds": interval, "power_mode": power_mode,
            "temperature_unit": unit, "home_timeout": home_timeout, "night_light": night, "touch_light": touch,
            "allow_update": allow_update, "pages": pages}


def iter_tiles(layout: dict):
    for page in layout["pages"]:
        for section in page["sections"]:
            yield from section["tiles"]


def find_tile(layout: dict, tile_id) -> dict | None:
    return next((tile for tile in iter_tiles(layout) if tile["id"] == tile_id), None)


def default_icon(entity_id: str, device_class: str | None = None) -> str:
    domain = entity_id.partition(".")[0]
    by_class = {"temperature": "temperature", "humidity": "humidity", "door": "door", "garage_door": "door",
                "window": "window", "opening": "door", "lock": "lock", "motion": "motion", "occupancy": "motion",
                "presence": "motion", "battery": "battery", "power": "bolt", "energy": "bolt",
                "curtain": "curtain", "blind": "curtain", "shade": "curtain", "tv": "tv", "outlet": "plug"}
    by_domain = {"light": "bulb", "switch": "plug", "fan": "fan", "climate": "thermostat", "scene": "scene",
                 "script": "scene", "button": "power", "input_button": "power", "lock": "lock", "cover": "curtain",
                 "media_player": "music", "humidifier": "humidity", "input_boolean": "power", "person": "home"}
    return by_class.get(device_class or "") or by_domain.get(domain, "sensor")


# ---------------------------------------------------------------- temperature

def convert_temperature(value: float, source: str, target: str) -> float:
    if source == target or source not in ("°C", "°F") or target not in ("°C", "°F"):
        return value
    return value * 9 / 5 + 32 if target == "°F" else (value - 32) * 5 / 9


def display_unit(layout: dict, system_unit: str) -> str:
    return system_unit if layout.get("temperature_unit", "auto") == "auto" else layout["temperature_unit"]


def finite_number(value):
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ProtocolError("数值无效")
    return value


def optional_number(value):
    try:
        return finite_number(value)
    except ProtocolError:
        return None


def snap(value: float, step: float) -> float:
    return round(round(value / step) * step, 4)


def climate_view(attributes: dict, system_unit: str, unit: str) -> dict:
    """Current/target/range in the panel's display unit; target snapped to the display step."""
    step = optional_number(attributes.get("target_temp_step")) or 1
    if unit != system_unit:
        step = 0.5 if unit == "°C" else 1
    result = {"step": step, "unit": unit}
    for key in ("current_temperature", "temperature", "min_temp", "max_temp"):
        value = optional_number(attributes.get(key))
        result[key] = None if value is None else convert_temperature(value, system_unit, unit)
    if result["temperature"] is not None:
        # Same unit: keep HA's grid (anchored at min_temp) so ±step stays valid for set_temperature.
        base = result["min_temp"] if unit == system_unit and result["min_temp"] is not None else 0
        result["temperature"] = round(base + snap(result["temperature"] - base, step), 4)
    if result["current_temperature"] is not None:
        result["current_temperature"] = round(result["current_temperature"], 1)
    return result


def target_temperature(value, state: dict, system_unit: str, unit: str) -> float:
    """Translate a requested display-unit target into a valid system-unit target."""
    attributes = state.get("attributes") or {}
    target = finite_number(value)
    low, high = finite_number(attributes.get("min_temp")), finite_number(attributes.get("max_temp"))
    step = finite_number(attributes.get("target_temp_step", 1))
    if step <= 0 or state.get("state") == "off":
        raise ProtocolError("温度超出范围，或空调已关机")
    if unit == system_unit:
        if not low <= target <= high or abs((target - low) / step - round((target - low) / step)) > 0.00001:
            raise ProtocolError("温度超出范围或步长不受支持")
        return target
    view = climate_view(attributes, system_unit, unit)
    if not view["min_temp"] - view["step"] <= target <= view["max_temp"] + view["step"]:
        raise ProtocolError("温度超出范围")
    wanted = convert_temperature(target, unit, system_unit)
    result = low + round((wanted - low) / step) * step
    current = optional_number(attributes.get("temperature"))
    if current is not None and view["temperature"] is not None and abs(result - current) < step / 2 \
            and target != view["temperature"]:
        result = current + (step if target > view["temperature"] else -step)
    return round(min(high, max(low, result)), 4)


# ---------------------------------------------------------------- device actions

def service_for_action(tile: dict, action: str, value, state: dict | None,
                       system_unit: str = "°C", unit: str | None = None) -> tuple[str, str, dict]:
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
        attributes = state.get("attributes") or {}
        if action == "power" and type(value) is bool:
            return "climate", "turn_on" if value else "turn_off", fields
        if action == "temperature":
            temperature = target_temperature(value, state, system_unit, unit or system_unit)
            return "climate", "set_temperature", {**fields, "temperature": temperature}
        if action == "mode" and isinstance(value, str) and value in (attributes.get("hvac_modes") or []):
            return "climate", "set_hvac_mode", {**fields, "hvac_mode": value}
    if kind == "toggle" and domain == "light" and action == "brightness" and value in (-1, 1) \
            and type(value) is int and state.get("state") == "on":
        return "light", "turn_on", {**fields, "brightness_step_pct": 10 * value}
    if kind == "action" and action == "activate" and value is None:
        return domain, "press" if domain in {"button", "input_button"} else "turn_on", fields
    if kind == "cover" and action == "cover" and value in COVER_ACTIONS:
        return "cover", COVER_ACTIONS[value], fields
    if kind == "media" and action == "media" and value in MEDIA_ACTIONS:
        return "media_player", MEDIA_ACTIONS[value], fields
    if kind == "lock" and action == "lock" and type(value) is bool:
        if not value and not tile.get("allow_unlock"):
            raise ProtocolError("这张卡片未允许在 Kindle 上开锁")
        return "lock", "lock" if value else "unlock", fields
    raise ProtocolError("此卡片不支持该操作")


# ---------------------------------------------------------------- pairing

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
                  "battery": None, "charging": False, "revision": None}
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


def default_layout() -> dict:
    return normalize_layout(deepcopy(DEFAULT_LAYOUT))
