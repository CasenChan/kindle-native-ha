"""Turn raw HA states into the short Chinese text shown on cards (HA-independent)."""
from __future__ import annotations

from .protocol import climate_view, convert_temperature, kind_for_entity, optional_number

MODE_NAMES = {"off": "关机", "cool": "制冷", "heat": "制热", "heat_cool": "自动", "auto": "自动",
              "dry": "除湿", "fan_only": "送风"}
MODE_ORDER = ("off", "cool", "heat", "heat_cool", "auto", "dry", "fan_only")
ON_OFF = {"on": "开启", "off": "关闭"}
BINARY_CLASSES = {
    "door": ("已打开", "已关闭"), "garage_door": ("已打开", "已关闭"), "opening": ("已打开", "已关闭"),
    "window": ("已打开", "已关闭"), "lock": ("未上锁", "已上锁"), "motion": ("有人", "无人"),
    "occupancy": ("有人", "无人"), "presence": ("在家", "离开"), "moisture": ("漏水", "正常"),
    "smoke": ("报警", "正常"), "gas": ("报警", "正常"), "carbon_monoxide": ("报警", "正常"),
    "battery": ("电量低", "正常"), "connectivity": ("已连接", "已断开"), "plug": ("通电", "断电"),
    "power": ("通电", "断电"), "problem": ("异常", "正常"), "vibration": ("震动", "静止"),
    "light": ("有光", "无光"), "running": ("运行中", "已停止"), "sound": ("有声音", "安静"),
}
DOMAIN_STATES = {
    "lock": {"locked": "已上锁", "unlocked": "未上锁", "locking": "上锁中", "unlocking": "开锁中",
             "jammed": "卡住", "open": "已打开", "opening": "打开中"},
    "cover": {"open": "已打开", "closed": "已关闭", "opening": "打开中", "closing": "关闭中"},
    "media_player": {"playing": "播放中", "paused": "已暂停", "idle": "空闲", "off": "关闭", "on": "开启",
                     "standby": "待机", "buffering": "缓冲中"},
    "person": {"home": "在家", "not_home": "外出"}, "device_tracker": {"home": "在家", "not_home": "外出"},
    "vacuum": {"cleaning": "清扫中", "docked": "已回充", "returning": "回充中", "idle": "空闲",
               "paused": "已暂停", "error": "故障"},
    "alarm_control_panel": {"disarmed": "已撤防", "armed_home": "在家布防", "armed_away": "离家布防",
                            "armed_night": "夜间布防", "arming": "布防中", "pending": "等待中", "triggered": "报警中"},
    "sun": {"above_horizon": "白天", "below_horizon": "夜晚"},
    "update": {"on": "有更新", "off": "已最新"},
}


def number_text(value: float, precision: int | None = None) -> str:
    if precision is not None and 0 <= precision <= 6:
        text = f"{value:.{precision}f}"
    else:
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "-0.0") else text


def tile_view(tile: dict, state: dict | None, system_unit: str, unit: str) -> dict:
    """Everything a card needs to draw itself; never exposes other attributes."""
    kind = kind_for_entity(tile["entity_id"])
    domain = tile["entity_id"].partition(".")[0]
    raw = str(state.get("state", "unknown")) if state else "unavailable"
    attributes = (state or {}).get("attributes") or {}
    available = raw != "unavailable" and (raw != "unknown" or kind == "action")
    view = {"kind": kind, "state": raw, "available": available, "on": False, "text": "离线", "unit": ""}
    if not available:
        view["text"] = "离线" if raw == "unavailable" else "—"
        return view
    if kind == "toggle":
        view.update(on=raw == "on", text=ON_OFF.get(raw, raw))
    elif kind == "action":
        view["text"] = "轻触执行"
    elif kind == "climate":
        climate = climate_view(attributes, system_unit, unit)
        modes = [mode for mode in attributes.get("hvac_modes") or [] if isinstance(mode, str)]
        climate.update(mode=raw, modes=sorted(modes, key=lambda mode: MODE_ORDER.index(mode)
                                              if mode in MODE_ORDER else len(MODE_ORDER)))
        view.update(on=raw != "off", text=MODE_NAMES.get(raw, raw), climate=climate)
    else:
        view.update(sensor_text(domain, raw, attributes, state.get("precision"), unit))
    return view


def sensor_text(domain: str, raw: str, attributes: dict, precision, unit: str) -> dict:
    measured = attributes.get("unit_of_measurement")
    measured = measured if isinstance(measured, str) else ""
    try:
        value = float(raw)
    except ValueError:
        value = None
    if value is not None and value == value and abs(value) != float("inf"):
        if measured in ("°C", "°F") and measured != unit:
            value = convert_temperature(value, measured, unit)
            measured, precision = unit, 1 if precision is None else precision
        return {"text": number_text(value, precision), "unit": measured[:12]}
    if domain == "binary_sensor" and raw in ("on", "off"):
        on_text, off_text = BINARY_CLASSES.get(attributes.get("device_class"), ("开启", "关闭"))
        return {"text": on_text if raw == "on" else off_text, "on": raw == "on"}
    text = DOMAIN_STATES.get(domain, {}).get(raw) or ON_OFF.get(raw) or raw
    return {"text": text[:40], "unit": measured[:12] if measured and text == raw else ""}


def section_summary(section: dict, views: dict) -> str:
    """A one-line overview, e.g. "2 盏灯开着 · 25.8°C"."""
    parts, lights, lit, temperature, locks = [], 0, 0, None, []
    for tile in section["tiles"]:
        view = views.get(tile["id"]) or {}
        if not view.get("available"):
            continue
        domain = tile["entity_id"].partition(".")[0]
        if view["kind"] == "climate" and view["on"] and not parts:
            parts.append(f"空调{view['text']}中")
        elif domain == "light" or (view["kind"] == "toggle" and tile["icon"] == "bulb"):
            lights += 1
            lit += view["on"]
        elif temperature is None and view.get("unit") in ("°C", "°F"):
            temperature = view["text"] + view["unit"]
        elif domain == "lock" or tile["icon"] == "lock":
            locks.append(view["text"] == "已上锁")
    if lit:
        parts.append(f"{lit} 盏灯开着")
    elif lights:
        parts.append("灯已全关")
    if temperature:
        parts.append(temperature)
    if locks:
        parts.append("门已锁" if all(locks) else "门未锁")
    return " · ".join(parts[:2])
