"""Render layout pages into display lists shared by the Kindle client and the editor preview.

Every page becomes a list of primitive draw ops (rect / text / icon) plus tap regions, in physical
pixels of the target screen. Both the KOReader plugin and the browser preview only paint these ops,
so the Kindle screen and its preview cannot drift apart. Colors are 8-bit gray levels; icon colors
are "k" (black), "w" (white) and "g" (light gray), matching the generated SVG variants.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

from .display import MODE_NAMES, number_text, section_summary, tile_view
from .protocol import LAYOUT_VERSION, display_unit, iter_tiles

BASE_W, BASE_H = 758, 1024
INK, DARK, MID, LIGHT, WHITE = 0, 51, 110, 180, 255
PROTOCOL = 2


def text_width(text: str, size: float) -> float:
    """Rough advance width (CJK = 1em, Latin ≈ 0.56em) for spacing and fitting decisions."""
    return sum(size if ord(char) > 0x2E7F else size * 0.56 for char in text)


def wrap_text(text: str, size: float, width: float, lines: int) -> list[str]:
    """Greedy line breaking on estimated widths; Latin words stay whole, CJK breaks anywhere.
    The last line keeps any overflow and is ellipsised by the client."""
    out, current = [], ""
    for token in re.findall(r"[A-Za-z0-9.,%°'\-]+|\s+|.", text):
        if current.strip() and text_width((current + token).strip(), size) > width and len(out) < lines - 1:
            out.append(current.strip())
            current = token.lstrip()
        else:
            current += token
    out.append(current.strip())
    return [line for line in out if line]


def fit_size(text: str, unit: str, size: float, room: float, minimum: float = 14) -> float:
    """Shrink a value (plus its half-size unit) until it fits the available width."""
    width = text_width(text, size) + (text_width(unit, size * 0.5) + size * 0.12 if unit else 0)
    return max(minimum, size * min(1, room / width)) if width else size


class Canvas:
    def __init__(self, scale: float):
        self.s, self.ops, self.hits = scale, [], []
        self.line = max(2, round(2 * scale))

    def rect(self, x, y, w, h, fill=None, border=0, color=INK, radius=0, key=None):
        op = {"t": "r", "x": round(x), "y": round(y), "w": max(1, round(w)), "h": max(1, round(h))}
        if fill is not None:
            op["f"] = fill
        if border:
            op["b"], op["c"] = border, color
        if radius:
            op["r"] = round(min(radius, w / 2, h / 2))
        if key:
            op["k"] = key
        self.ops.append(op)

    def text(self, value, x, y, size, color=INK, bold=False, align="l", width=None, unit=None, key=None):
        op = {"t": "x", "x": round(x), "y": round(y), "s": max(10, round(size)), "v": str(value)}
        if color != INK:
            op["c"] = color
        if bold:
            op["b"] = True
        if align != "l":
            op["a"] = align
        if width:
            op["w"] = max(1, round(width))
        if unit:
            op["u"] = unit
        if key:
            op["k"] = key
        self.ops.append(op)

    def icon(self, name, x, y, size, color="k", key=None):
        op = {"t": "i", "n": name, "x": round(x), "y": round(y), "s": max(8, round(size)), "c": color}
        if key:
            op["k"] = key
        self.ops.append(op)

    def hit(self, x, y, w, h, **target):
        self.hits.append({"x": round(x), "y": round(y), "w": round(w), "h": round(h), **target})

    def circle_button(self, x, y, size, icon, enabled=True, sw_icon=0.5):
        color = INK if enabled else LIGHT
        self.rect(x, y, size, size, fill=WHITE, border=self.line, color=color, radius=size / 2)
        inner = size * sw_icon
        self.icon(icon, x + (size - inner) / 2, y + (size - inner) / 2, inner, "k" if enabled else "g")

    def badge(self, x, y, size, icon, filled, offline=False):
        if filled:
            self.rect(x, y, size, size, fill=INK, radius=size / 4)
        else:
            self.rect(x, y, size, size, fill=WHITE, border=self.line, color=LIGHT if offline else INK, radius=size / 4)
        inner = size * 0.6
        self.icon(icon, x + (size - inner) / 2, y + (size - inner) / 2, inner,
                  "w" if filled else "g" if offline else "k")

    def pill(self, x, y, w, h, on):
        if on:
            self.rect(x, y, w, h, fill=INK, radius=h / 2)
        else:
            self.rect(x, y, w, h, fill=WHITE, border=self.line, radius=h / 2)
        margin = h * 0.13
        knob = h - 2 * margin
        self.rect(x + w - knob - margin if on else x + margin, y + margin, knob, knob,
                  fill=WHITE if on else INK, radius=knob / 2)


# ---------------------------------------------------------------- cards

def tile_card(cv: Canvas, card: dict, tile: dict, view: dict):
    s, x, y, w, h = cv.s, card["x"], card["y"], card["w"], card["h"]
    offline = not view["available"]
    kind = view["kind"]
    filled = view.get("on", False) and not offline
    toggle = kind == "toggle" and not offline
    action = kind == "action" and not offline
    extra, button = [], 0
    cv.rect(x, y, w, h, fill=WHITE, border=cv.line, color=LIGHT if offline else INK, radius=card["r"])
    value_color, title_color = (LIGHT, LIGHT) if offline else (INK, DARK)
    if (w > h * 2.1 and h < 200 * s) or h < 118 * s:
        pad = (14 if h >= 90 * s else 10) * s
        size = min(52 * s, h - 2 * pad)
        cv.badge(x + pad, y + (h - size) / 2, size, tile["icon"], filled, offline)
        dim = toggle and view.get("dimmable") and view["on"] and w >= 300 * s
        show_pill = toggle and w >= 260 * s and not dim
        button = min(40 * s, h - 2 * pad)
        right = 80 * s if show_pill else 2 * button + 18 * s if dim else 52 * s if action and w >= 260 * s else 0
        left = x + pad + size + 12 * s
        room = x + w - pad - right - left
        title_size, value_size = min(18 * s, h * 0.2), min(28 * s, h * 0.3)
        cv.text(tile["title"], left, y + h / 2 - title_size - 6 * s, title_size, title_color, width=room)
        unit = f"{view['brightness']}%" if dim and view.get("brightness") else view["unit"]
        value_size = fit_size(view["text"], unit, value_size, room)
        cv.text(view["text"], left, y + h / 2 + 2 * s, value_size, value_color, True, width=room, unit=unit)
        if dim:
            button_y = y + (h - button) / 2
            plus_x = x + w - pad - button
            minus_x = plus_x - button - 8 * s
            cv.circle_button(minus_x, button_y, button, "minus", view.get("brightness", 100) > 10)
            cv.circle_button(plus_x, button_y, button, "plus", view.get("brightness", 0) < 100)
            extra = [(minus_x, button_y, -1), (plus_x, button_y, 1)]
        elif show_pill:
            cv.pill(x + w - pad - 64 * s, y + (h - 36 * s) / 2, 64 * s, 36 * s, view["on"])
        elif right:
            size = 38 * s
            cv.circle_button(x + w - pad - size, y + (h - size) / 2, size, "arrow", sw_icon=0.58)
    else:
        big, mid = h >= 200 * s and w >= 300 * s, h >= 150 * s
        pad, size = (24 * s, 64 * s) if big else (18 * s, 48 * s) if mid else (14 * s, 40 * s)
        cv.badge(x + pad, y + pad, size, tile["icon"], filled, offline)
        if toggle and w >= 150 * s:
            pill_w = (84 if big else 64 if mid else 52) * s
            pill_h = pill_w * 0.55
            cv.pill(x + w - pad - pill_w, y + pad + (size - pill_h) / 2, pill_w, pill_h, view["on"])
        elif action and w >= 150 * s:
            button = (52 if big else 36) * s
            cv.circle_button(x + w - pad - button, y + pad + (size - button) / 2, button, "arrow", sw_icon=0.56)
        unit = view["unit"]
        dim = toggle and view.get("dimmable") and view["on"] and w >= 240 * s and mid
        if dim:
            unit = f"{view['brightness']}%" if view.get("brightness") else ""
        if big:
            value_size, title_size, spacing = (54 if unit else 46) * s, 24 * s, 14 * s
        elif mid:
            value_size, title_size, spacing = (40 if unit else 34) * s, 20 * s, 8 * s
        else:
            value_size, title_size, spacing = (30 if unit else 24) * s, 17 * s, 8 * s
        button = (48 if big else 40) * s
        room = w - 2 * pad - (2 * button + 22 * s if dim else 0)
        lines = [view["text"]]
        fitted = fit_size(view["text"], unit, value_size, room)
        if not unit and fitted < value_size * 0.75:
            # Long words (e.g. weather text): wrap onto two lines when the card is tall enough.
            smaller = max(16 * s, value_size * 0.7)
            for count in (2, 3):
                wrapped = wrap_text(view["text"], smaller, room, count)
                needed = pad + size + 8 * s + title_size + spacing + (1.2 * count - 0.2) * smaller + pad
                if needed > h:
                    break
                lines, fitted = wrapped, smaller
                if text_width(wrapped[-1], smaller) <= room:
                    break
        value_size = fitted
        value_y = y + h - pad - value_size - (len(lines) - 1) * value_size * 1.2
        cv.text(tile["title"], x + pad, value_y - spacing - title_size, title_size, title_color, width=w - 2 * pad)
        for index, line in enumerate(lines):
            cv.text(line, x + pad, value_y + index * value_size * 1.2, value_size, value_color, True, width=room,
                    unit=unit if index == len(lines) - 1 else None)
        if dim:
            button_y = y + h - pad - button
            plus_x = x + w - pad - button
            minus_x = plus_x - button - 10 * s
            cv.circle_button(minus_x, button_y, button, "minus", view.get("brightness", 100) > 10)
            cv.circle_button(plus_x, button_y, button, "plus", view.get("brightness", 0) < 100)
            extra = [(minus_x, button_y, -1), (plus_x, button_y, 1)]
    if toggle:
        cv.hit(x, y, w, h, tile=tile["id"], action="power", value=not view["on"])
        for left, top, step in extra:
            cv.hit(left - 4, top - 4, button + 8, button + 8, tile=tile["id"], action="brightness", value=step)
    elif action:
        cv.hit(x, y, w, h, tile=tile["id"], action="activate")
    elif offline:
        return
    elif kind == "cover":
        cv.hit(x, y, w, h, tile=tile["id"], action="cover", value="close" if view["on"] else "open")
    elif kind == "media":
        cv.hit(x, y, w, h, tile=tile["id"], action="media", value="play_pause")
    elif kind == "lock":
        if not view["on"]:
            cv.hit(x, y, w, h, tile=tile["id"], action="lock", value=True)
        elif tile.get("allow_unlock"):
            cv.hit(x, y, w, h, tile=tile["id"], action="lock", value=False, confirm="再次轻触以开锁")


COVER_SEGMENTS = (("open", "打开", None), ("stop", "暂停", None), ("close", "关闭", None))
MEDIA_SEGMENTS = (("previous", None, "prev"), ("play_pause", None, "playpause"), ("next", None, "next"))


def bar_card(cv: Canvas, card: dict, tile: dict, view: dict):
    """Covers and media players: status on top, a three-button control bar at the bottom."""
    s, x, y, w, h = cv.s, card["x"], card["y"], card["w"], card["h"]
    segments = COVER_SEGMENTS if view["kind"] == "cover" else MEDIA_SEGMENTS
    if view["available"] and h < 150 * s and w >= 520 * s:
        # Short, wide card (list layouts): status on the left, three round buttons on the right.
        k = min(s, h / 110)
        pad = 12 * k
        badge = min(56 * s, h - 2 * pad)
        cv.rect(x, y, w, h, fill=WHITE, border=cv.line, radius=card["r"])
        cv.badge(x + pad, y + (h - badge) / 2, badge, tile["icon"], view["on"])
        button = min(h - 2 * pad, 56 * s)
        gap = 10 * k
        first = x + w - pad - 3 * button - 2 * gap
        text_x = x + pad + badge + 12 * k
        room = first - text_x - 10 * k
        status = view["text"] + (f" · {view['unit']}" if view.get("unit") else "")
        cv.text(tile["title"], text_x, y + h / 2 - 24 * k, max(15, 18 * k), DARK, width=room)
        cv.text(status, text_x, y + h / 2 + 2 * k, max(16, 24 * k), INK, True, width=room)
        for index, (value, label, icon) in enumerate(segments):
            left = first + index * (button + gap)
            top = y + (h - button) / 2
            cv.rect(left, top, button, button, fill=WHITE, border=cv.line, radius=button / 2)
            icon = icon or {"open": "up", "stop": "stop", "close": "down"}[value]
            cv.icon(icon, left + button * 0.24, top + button * 0.24, button * 0.52)
            cv.hit(left - gap / 2, y, button + gap, h, tile=tile["id"], action=view["kind"], value=value)
        return
    if not view["available"] or h < 150 * s or w < 230 * s:
        return tile_card(cv, card, tile, view)
    k = min(s, h / 220, w / 330)
    pad, badge = 20 * k + 2, 56 * k
    cv.rect(x, y, w, h, fill=WHITE, border=cv.line, radius=card["r"])
    cv.badge(x + pad, y + pad, badge, tile["icon"], view["on"])
    text_x = x + pad + badge + 14 * k
    room = x + w - pad - text_x
    cv.text(tile["title"], text_x, y + pad + 2 * k, 20 * k, DARK, width=room)
    status = view["text"] + (f" · {view['unit']}" if view.get("unit") else "")
    cv.text(status, text_x, y + pad + 28 * k, 28 * k, INK, True, width=room)
    if view.get("detail"):
        cv.text(view["detail"], x + pad, y + pad + badge + 12 * k, 18 * k, MID, width=w - 2 * pad)
    bar_h = 56 * k
    bar_x, bar_y, bar_w = x + pad, y + h - pad - bar_h, w - 2 * pad
    cv.rect(bar_x, bar_y, bar_w, bar_h, fill=WHITE, border=cv.line, radius=14 * k)
    segment = bar_w / len(segments)
    for index, (value, label, icon) in enumerate(segments):
        left = bar_x + index * segment
        if index:
            cv.rect(left, bar_y + 14 * k, 2, bar_h - 28 * k, fill=LIGHT)
        if icon:
            size = 30 * k
            cv.icon(icon, left + (segment - size) / 2, bar_y + (bar_h - size) / 2, size)
        else:
            cv.text(label, left + segment / 2, bar_y + (bar_h - 22 * k) / 2, 22 * k, INK, align="c", width=segment - 8)
        cv.hit(left, bar_y, segment, bar_h, tile=tile["id"], action=view["kind"], value=value)


def visible_modes(modes: list, current: str, limit: int) -> list:
    if len(modes) <= limit:
        return modes
    keep = [mode for mode in modes if mode in ("off", current)]
    for mode in modes:
        if len(keep) >= limit:
            break
        if mode not in keep:
            keep.append(mode)
    return sorted(keep[:limit], key=modes.index)


def climate_card(cv: Canvas, card: dict, tile: dict, view: dict):
    s, x, y, w, h = cv.s, card["x"], card["y"], card["w"], card["h"]
    offline = not view["available"]
    cv.rect(x, y, w, h, fill=WHITE, border=cv.line, color=LIGHT if offline else INK, radius=card["r"])
    if offline:
        pad = min(24 * s, h * 0.12)
        size = min(60 * s, h - 2 * pad)
        cv.badge(x + pad, y + pad, size, tile["icon"], False, True)
        cv.text(tile["title"], x + pad + size + 14 * s, y + pad + 4 * s, min(24 * s, h * 0.2), LIGHT, True,
                width=w - 3 * pad - size)
        cv.text("离线", x + pad + size + 14 * s, y + pad + min(36 * s, h * 0.4), min(20 * s, h * 0.18), LIGHT)
        return
    climate = view["climate"]
    on, unit = view["on"], climate["unit"]
    target, step = climate["temperature"], climate["step"]
    low, high = climate["min_temp"], climate["max_temp"]
    can_down = on and target is not None and (low is None or target - step >= low - 1e-6)
    can_up = on and target is not None and (high is None or target + step <= high + 1e-6)
    target_text = number_text(target) if on and target is not None else "—"
    current = climate["current_temperature"]
    current_text = number_text(current) if current is not None else "—"
    status = view["text"] + "中" if on else "已关机"

    def temperature_hits(minus_x, minus_y, plus_x, plus_y, size):
        if can_down:
            cv.hit(minus_x, minus_y, size, size, tile=tile["id"], action="temperature", value=round(target - step, 4))
        if can_up:
            cv.hit(plus_x, plus_y, size, size, tile=tile["id"], action="temperature", value=round(target + step, 4))

    k = min(s, h / 268, w / 420)
    if k >= 0.75 * s:
        pad, badge = 24 * k + 2, 60 * k
        cv.badge(x + pad, y + pad, badge, tile["icon"], on)
        cv.hit(x + pad - 6, y + pad - 6, badge + 12, badge + 12, tile=tile["id"], action="power", value=not on)
        text_x = x + pad + badge + 14 * k
        cv.text(tile["title"], text_x, y + pad + 4 * k, 24 * k, INK, True, width=w - 2 * pad - badge - 120 * k)
        cv.text(status, text_x, y + pad + 34 * k, 18 * k, MID, width=w - 2 * pad - badge - 120 * k)
        cv.text("室内", x + w - pad, y + pad + 2 * k, 17 * k, MID, align="r", width=110 * k)
        cv.text(current_text, x + w - pad, y + pad + 24 * k, 28 * k, INK, True, align="r", width=110 * k, unit=unit)
        button, button_y = 72 * k, y + pad + badge + 14 * k
        cv.circle_button(x + pad, button_y, button, "minus", can_down)
        cv.circle_button(x + w - pad - button, button_y, button, "plus", can_up)
        target_size = fit_size(target_text, unit, 62 * k, w - 2 * pad - 2 * button - 16 * k)
        cv.text(target_text, x + w / 2, button_y + (button - target_size) / 2, target_size, INK if on else LIGHT, True,
                align="c", width=w - 2 * pad - 2 * button, unit=unit if on and target is not None else None)
        temperature_hits(x + pad, button_y, x + w - pad - button, button_y, button)
        modes = climate["modes"]
        if modes:
            bar_h = 54 * k
            bar_x, bar_y, bar_w = x + pad, y + h - pad - bar_h, w - 2 * pad
            shown = visible_modes(modes, climate["mode"], max(2, math.floor(bar_w / (60 * k))))
            segment = bar_w / len(shown)
            cv.rect(bar_x, bar_y, bar_w, bar_h, fill=WHITE, border=cv.line, radius=14 * k)
            for index, mode in enumerate(shown):
                current_mode = mode == climate["mode"]
                left = bar_x + index * segment
                if current_mode:
                    cv.rect(left + 4, bar_y + 4, segment - 8, bar_h - 8, fill=INK, radius=10 * k)
                elif index and shown[index - 1] != climate["mode"]:
                    cv.rect(left, bar_y + 14 * k, 2, bar_h - 28 * k, fill=LIGHT)
                cv.text(MODE_NAMES.get(mode, mode)[:3], left + segment / 2, bar_y + (bar_h - 21 * k) / 2, 21 * k,
                        WHITE if current_mode else INK, current_mode, align="c", width=segment - 8)
                if not current_mode:
                    cv.hit(left, bar_y, segment, bar_h, tile=tile["id"], action="mode", value=mode)
    elif h >= 150 * s and w >= 230 * s:
        # Stacked compact: status row on top, a full-width  −  target  +  row below (no mode bar).
        k = min(s, h / 190, w / 330)
        pad = 16 * k + 2
        badge = 48 * k
        cv.badge(x + pad, y + pad, badge, tile["icon"], on)
        cv.hit(x + pad - 6, y + pad - 6, badge + 12, badge + 12, tile=tile["id"], action="power", value=not on)
        text_x = x + pad + badge + 12 * k
        room = x + w - pad - text_x
        cv.text(tile["title"], text_x, y + pad, max(15, 21 * k), INK, True, width=room)
        cv.text(f"{status} · 室内 {current_text}{unit}", text_x, y + pad + 28 * k, max(14, 16 * k), MID, width=room)
        button = min(64 * k, h - (badge + 3 * pad + 8 * k))
        button_y = y + h - pad - button
        cv.circle_button(x + pad, button_y, button, "minus", can_down)
        cv.circle_button(x + w - pad - button, button_y, button, "plus", can_up)
        zone = w - 2 * pad - 2 * button - 16 * k
        size = fit_size(target_text, unit, min(48 * k, button * 0.85), zone)
        cv.text(target_text, x + w / 2, button_y + (button - size) / 2, size, INK if on else LIGHT, True,
                align="c", width=zone, unit=unit if on and target is not None else None)
        temperature_hits(x + pad, button_y, x + w - pad - button, button_y, button)
    elif w >= 520 * s:
        # Inline compact for short, wide cards: badge · title/status · − target +
        k = min(s, h / 110)
        pad = 12 * k
        badge = min(56 * s, h - 2 * pad)
        cv.badge(x + pad, y + (h - badge) / 2, badge, tile["icon"], on)
        cv.hit(x, y, pad + badge + 6 * k, h, tile=tile["id"], action="power", value=not on)
        button = min(h - 2 * pad, 60 * s)
        plus_x = x + w - pad - button
        zone = 104 * k
        minus_x = plus_x - zone - button
        button_y = y + (h - button) / 2
        cv.circle_button(minus_x, button_y, button, "minus", can_down)
        cv.circle_button(plus_x, button_y, button, "plus", can_up)
        cv.text(target_text, minus_x + button + zone / 2, y + h / 2 - 18 * k, 36 * k, INK if on else LIGHT, True,
                align="c", width=zone, unit=unit if on and target is not None else None)
        temperature_hits(minus_x, button_y, plus_x, button_y, button)
        text_x = x + pad + badge + 12 * k
        room = minus_x - text_x - 8 * k
        cv.text(tile["title"], text_x, y + h / 2 - 24 * k, max(15, 20 * k), INK, True, width=room)
        cv.text(f"{status} · 室内 {current_text}{unit}", text_x, y + h / 2 + 4 * k, max(14, 16 * k), MID, width=room)
    else:
        tile_card(cv, card, tile, {**view, "kind": "climate-tiny", "text": target_text if on else "关机",
                                    "unit": unit if on and target is not None else ""})
        cv.hit(x, y, w, h, tile=tile["id"], action="power", value=not on)


# ---------------------------------------------------------------- pages

def header(cv: Canvas, title: str, width: int):
    s = cv.s
    cv.hit(0, 0, width - 160 * s, 128 * s, local="refresh")
    cv.text(title, 28 * s, 30 * s, 38 * s, INK, True, width=width - 340 * s)
    cv.text("", 28 * s, 84 * s, 19 * s, MID, width=width - 200 * s, key="status")
    cv.icon("wifi", width - 276 * s, 41 * s, 26 * s, "k", key="wifi")
    cv.text("", width - 192 * s, 45 * s, 20 * s, DARK, align="r", width=80 * s, key="battery")
    cv.icon("battery", width - 186 * s, 39 * s, 32 * s)
    button = 52 * s
    light_x, menu_x = width - 28 * s - 2 * button - 14 * s, width - 28 * s - button
    cv.rect(light_x, 28 * s, button, button, fill=WHITE, border=cv.line, radius=button / 2, key="backlight")
    cv.icon("sun", light_x + 13 * s, 41 * s, 26 * s, "k", key="backlight")
    cv.rect(menu_x, 28 * s, button, button, fill=WHITE, border=cv.line, radius=button / 2)
    cv.icon("menu", menu_x + 13 * s, 41 * s, 26 * s)
    cv.hit(light_x - 8 * s, 18 * s, button + 15 * s, button + 24 * s, local="backlight")
    cv.hit(menu_x - 7 * s, 18 * s, button + 22 * s, button + 24 * s, local="menu")


def tabs(cv: Canvas, pages: list, current: int, width: int, height: int):
    s = cv.s
    top = height - 72 * s
    cv.rect(28 * s, top, width - 56 * s, 1, fill=LIGHT)
    gap = 10 * s
    tab_w = (width - 56 * s - gap * (len(pages) - 1)) / len(pages)
    size = 21 * s if tab_w > 110 * s else 18 * s
    for index, page in enumerate(pages):
        left, active = 28 * s + index * (tab_w + gap), index == current
        cv.rect(left, top + 14 * s, tab_w, 46 * s, fill=INK if active else WHITE,
                border=0 if active else cv.line, color=LIGHT, radius=23 * s)
        cv.text(page["title"], left + tab_w / 2, top + 14 * s + (46 * s - size) / 2, size,
                WHITE if active else DARK, active, align="c", width=tab_w - 12 * s)
        cv.hit(left, top + 6 * s, tab_w, 62 * s, local="page", value=index)


def render_page(layout: dict, index: int, views: dict, width: int, height: int) -> dict:
    page = layout["pages"][index]
    s = min(width / BASE_W, height / BASE_H)
    cv = Canvas(s)
    header(cv, page["title"], width)
    multi = len(layout["pages"]) > 1
    margin, top = 28 * s, 128 * s
    bottom = height - (80 if multi else 24) * s
    sections = page["sections"]
    columns = page["columns"]
    gap = (14 if columns <= 2 else 12) * s
    heads = [44 * s if section["title"] else 0 for section in sections]
    rows = sum(section["rows"] for section in sections)
    section_gap = 10 * s
    cell_h = (bottom - top - sum(heads) - section_gap * (len(sections) - 1)
              - gap * (rows - len(sections))) / rows
    cell_w = (width - 2 * margin - gap * (columns - 1)) / columns
    radius = (18 if cell_h >= 150 * s and cell_w >= 200 * s else 14) * s
    cards, section_boxes, cursor = [], [], top
    for section, head in zip(sections, heads):
        if head:
            title_size = 24 * s
            cv.text(section["title"], margin, cursor + 8 * s, title_size, INK, True, width=width / 2)
            summary = section_summary(section, views) if section["summary"] else ""
            line_left = margin + text_width(section["title"], title_size) + 16 * s
            line_right = width - margin - (text_width(summary, 17 * s) + 16 * s if summary else 0)
            if line_right - line_left > 24 * s:
                cv.rect(line_left, cursor + 20 * s, line_right - line_left, cv.line, fill=INK)
            if summary:
                cv.text(summary, width - margin, cursor + 12 * s, 17 * s, MID, align="r", width=width / 2)
        grid_y = cursor + head
        section_boxes.append({"id": section["id"], "y": round(cursor), "head": round(head),
                              "grid": {"x": round(margin), "y": round(grid_y), "cw": round(cell_w, 2),
                                       "ch": round(cell_h, 2), "gap": round(gap, 2),
                                       "columns": columns, "rows": section["rows"]}})
        for tile in section["tiles"]:
            card = {"id": tile["id"], "x": round(margin + tile["x"] * (cell_w + gap)),
                    "y": round(grid_y + tile["y"] * (cell_h + gap)),
                    "w": round(tile["w"] * cell_w + (tile["w"] - 1) * gap),
                    "h": round(tile["h"] * cell_h + (tile["h"] - 1) * gap), "r": round(radius)}
            cards.append(card)
            view = views[tile["id"]]
            {"climate": climate_card, "cover": bar_card, "media": bar_card}.get(tile["kind"], tile_card)(cv, card, tile, view)
        cursor = grid_y + section["rows"] * cell_h + (section["rows"] - 1) * gap + section_gap
    if multi:
        tabs(cv, layout["pages"], index, width, height)
    return {"id": page["id"], "title": page["title"], "ops": cv.ops, "hits": cv.hits,
            "cards": cards, "sections": section_boxes}


def build_views(layout: dict, states: dict, system_unit: str) -> dict:
    unit = display_unit(layout, system_unit)
    return {tile["id"]: tile_view(tile, states.get(tile["entity_id"]), system_unit, unit)
            for tile in iter_tiles(layout)}


def snapshot(layout: dict, revision: int, states: dict, system_unit: str, width: int, height: int) -> dict:
    """The complete, self-contained frame the Kindle paints (also used by the editor preview)."""
    views = build_views(layout, states, system_unit)
    pages = [render_page(layout, index, views, width, height) for index in range(len(layout["pages"]))]
    fingerprint = hashlib.sha1(json.dumps(pages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return {
        "protocol": PROTOCOL, "layout_version": LAYOUT_VERSION, "revision": revision,
        "refresh_seconds": layout["refresh_seconds"], "power_mode": layout["power_mode"],
        "temperature_unit": display_unit(layout, system_unit),
        "screen": {"width": width, "height": height, "scale": round(min(width / BASE_W, height / BASE_H), 4)},
        "home_timeout": layout["home_timeout"], "night_light": layout["night_light"],
        "touch_light": layout["touch_light"],
        "hash": fingerprint, "pages": pages,
        "states": {tile_id: {"available": view["available"], "state": view["state"]}
                   for tile_id, view in views.items()},
    }, views
