-- Paints the server-rendered display list (rect / text / icon ops) and maps taps to hit regions.
-- Only device-local things are drawn here: header tokens, pressed feedback and the backlight popover.
local Blitbuffer = require('ffi/blitbuffer')
local Device = require('device')
local Font = require('ui/font')
local Geom = require('ui/geometry')
local GestureRange = require('ui/gesturerange')
local IconWidget = require('ui/widget/iconwidget')
local InputContainer = require('ui/widget/container/inputcontainer')
local TextWidget = require('ui/widget/textwidget')
local UIManager = require('ui/uimanager')

local ICON_DIR = '/mnt/us/nativeha/icons/'
local ICON_SUFFIX = { k='', w='-w', g='-g' }
local LIGHT_STEPS = 12
local CONFIRM_SECONDS = 5
local FULL_REFRESH_EVERY = 12

local Panel = InputContainer:extend{ covers_fullscreen = true }

local function gray(value)
    if type(value) ~= 'number' then return nil end
    return Blitbuffer.Color8(math.max(0, math.min(255, math.floor(value))))
end

local function pixelFace(size)
    -- Ops use physical pixels; undo KOReader's UI-size scaling.
    return Font:getFace('cfont', size * 1000 / Device.screen:scaleBySize(1000))
end

function Panel:init()
    self.page, self.items, self.popover = 0, {}, nil
    self.dimen = Geom:new{ x=0, y=0, w=Device.screen:getWidth(), h=Device.screen:getHeight() }
    self.ges_events = {
        Tap = { GestureRange:new{ ges='tap', range=self.dimen } },
        Swipe = { GestureRange:new{ ges='swipe', range=self.dimen } },
        Hold = { GestureRange:new{ ges='hold', range=self.dimen } },
        Pan = { GestureRange:new{ ges='pan', range=self.dimen } },
        PanRelease = { GestureRange:new{ ges='pan_release', range=self.dimen } },
    }
end

function Panel:getSize() return self.dimen end

function Panel:freeItems()
    for _, item in ipairs(self.items) do
        if item.widget and item.widget.free then item.widget:free() end
    end
    self.items = {}
end

function Panel:addWidget(widget, x, y)
    self.items[#self.items + 1] = { widget=widget, x=math.floor(x), y=math.floor(y) }
end

function Panel:addRect(x, y, w, h, fill, border, color, radius)
    self.items[#self.items + 1] = { rect=true, x=math.floor(x), y=math.floor(y), w=math.floor(w), h=math.floor(h),
        fill=gray(fill), border=border or 0, color=gray(color) or Blitbuffer.COLOR_BLACK, radius=radius or 0 }
end

function Panel:addIcon(name, x, y, size, color)
    if type(name) ~= 'string' or not name:match('^[a-z%-]+$') then name = 'sensor' end
    local widget = IconWidget:new{ file=ICON_DIR .. name .. (ICON_SUFFIX[color] or '') .. '.svg',
        width=math.floor(size), height=math.floor(size), alpha=true }
    self:addWidget(widget, x, y)
end

-- Text with optional half-size unit, aligned at x (left / right edge / centre of a box of width w).
function Panel:addText(value, x, y, size, opts)
    opts = opts or {}
    local color = gray(opts.color) or Blitbuffer.COLOR_BLACK
    local unit = type(opts.unit) == 'string' and opts.unit ~= '' and opts.unit or nil
    local unit_widget, unit_w, gap = nil, 0, 0
    if unit then
        unit_widget = TextWidget:new{ text=unit, face=pixelFace(math.max(10, math.floor(size * 0.5))),
            padding=0, fgcolor=color }
        gap = math.max(3, math.floor(size * 0.12))
        unit_w = unit_widget:getSize().w + gap
    end
    local main = TextWidget:new{ text=tostring(value or ''), face=pixelFace(math.max(10, math.min(160, size))),
        bold=opts.bold or false, padding=0, fgcolor=color,
        max_width=opts.width and math.max(10, opts.width - unit_w) or nil }
    local main_size = main:getSize()
    local total = main_size.w + unit_w
    local left = x
    if opts.align == 'r' then left = x - total
    elseif opts.align == 'c' then left = x - total / 2 end
    self:addWidget(main, left, y)
    if unit_widget then
        local unit_size = unit_widget:getSize()
        self:addWidget(unit_widget, left + main_size.w + gap, y + main_size.h - unit_size.h)
    end
end

function Panel:currentPage()
    local pages = self.snapshot.pages
    self.page = math.max(0, math.min(self.page, #pages - 1))
    return pages[self.page + 1]
end

-- mode: KOReader refresh type. status_only: only the header status/battery text changed, so refresh just that
-- strip and do not count it towards the periodic full refresh.
function Panel:update(snapshot, tokens, busy, mode, status_only)
    self.snapshot, self.tokens, self.busy = snapshot, tokens or {}, busy
    self:freeItems()
    local page, t = self:currentPage(), self.tokens
    for _, op in ipairs(page.ops) do
        if op.t == 'r' then
            local fill = op.f
            if op.k == 'backlight' and self.popover then fill = 0 end
            self:addRect(op.x, op.y, op.w, op.h, fill, op.b, op.c, op.r)
        elseif op.t == 'x' then
            local value, color, bold = op.v, op.c, op.b
            if op.k then value = t[op.k] or '' end
            if op.k == 'status' and t.status_error then color, bold = 0, true end
            self:addText(value, op.x, op.y, op.s, { color=color, bold=bold, align=op.a, width=op.w, unit=op.u })
        elseif op.t == 'i' then
            local color = op.c
            if op.k == 'backlight' and self.popover then color = 'w' end
            if op.k == 'wifi' and t.offline then color = 'g' end
            self:addIcon(op.n, op.x, op.y, op.s, color)
        end
    end
    if self.pressed then
        for _, card in ipairs(page.cards) do
            if card.id == self.pressed then self:addRect(card.x, card.y, card.w, card.h, nil, 5, 0, card.r) end
        end
    end
    if self.popover then self:buildPopover() end
    if status_only and not self.popover then
        local region = self:statusRegion(page)
        if region then UIManager:setDirty(self, 'ui', region);return end
    end
    self.updates = (self.updates or 0) + 1
    if self.updates >= FULL_REFRESH_EVERY then mode, self.updates = 'full', 0 end  -- clears e-ink ghosting
    UIManager:setDirty(self, mode or 'ui')
end

-- Bounding box of the header strip holding the device-filled status and battery texts.
function Panel:statusRegion(page)
    local top, bottom = nil, nil
    for _, op in ipairs(page.ops) do
        if op.t == 'x' and (op.k == 'status' or op.k == 'battery') then
            top = math.min(top or op.y, op.y)
            bottom = math.max(bottom or 0, op.y + math.ceil(op.s * 1.5))
        end
    end
    if not top then return nil end
    return Geom:new{ x=0, y=math.max(0, top - 4), w=self.dimen.w, h=bottom - top + 8 }
end

function Panel:paintTo(bb, x, y)
    self.dimen.x, self.dimen.y = x, y
    bb:paintRect(x, y, self.dimen.w, self.dimen.h, Blitbuffer.COLOR_WHITE)
    for _, item in ipairs(self.items) do
        if item.rect then
            local r = math.min(item.radius, math.floor(item.w / 2), math.floor(item.h / 2))
            if item.fill then
                if r > 0 then bb:paintRoundedRect(x + item.x, y + item.y, item.w, item.h, item.fill, r)
                else bb:paintRect(x + item.x, y + item.y, item.w, item.h, item.fill) end
            end
            if item.border > 0 then
                bb:paintBorder(x + item.x, y + item.y, item.w, item.h, item.border, item.color, r, true)
            end
        else
            item.widget:paintTo(bb, x + item.x, y + item.y)
        end
    end
end

-- ------------------------------------------------------------------ backlight popover

function Panel:popoverGeometry()
    local s, width = self.snapshot.screen.scale, self.snapshot.screen.width
    local x = math.floor(150 * s)
    return { s=s, x=x, y=math.floor(96 * s), w=width - math.floor(28 * s) - x, h=math.floor(252 * s) }
end

function Panel:buildPopover()
    local p, light = self:popoverGeometry(), self.popover
    local s, x, y, w = p.s, p.x, p.y, p.w
    self.popover_hits = {}
    local function hit(hx, hy, hw, hh, level) self.popover_hits[#self.popover_hits + 1] = { x=hx, y=hy, w=hw, h=hh, level=level } end
    self:addRect(x - 4, y - 4, w + 8, p.h + 8, 255, 0, 0, 24 * s)
    self:addRect(x, y, w, p.h, 255, math.max(2, math.floor(3 * s)), 0, 20 * s)
    self:addText('屏幕背光', x + 28 * s, y + 26 * s, 26 * s, { bold=true })
    self:addText(string.format('%d / %d', light.level, light.max), x + w - 28 * s, y + 30 * s, 22 * s, { color=110, align='r' })
    local step = math.max(1, math.floor(light.max / LIGHT_STEPS + 0.5))
    local by, bs = y + 76 * s, 72 * s
    local line = math.max(2, math.floor(2 * s))
    self:addRect(x + 24 * s, by, bs, bs, 255, line, 0, bs / 2)
    self:addIcon('sun-low', x + 42 * s, by + 18 * s, 36 * s, 'k')
    hit(x + 24 * s, by, bs, bs, math.max(light.min, light.level - step))
    self:addRect(x + w - 24 * s - bs, by, bs, bs, 255, line, 0, bs / 2)
    self:addIcon('sun', x + w - 24 * s - bs + 18 * s, by + 18 * s, 36 * s, 'k')
    hit(x + w - 24 * s - bs, by, bs, bs, math.min(light.max, light.level + step))
    local sx = x + 24 * s + bs + 18 * s
    local sw = w - 2 * (24 * s + bs + 18 * s)
    -- Dragging or flicking anywhere on this row sets the level from the finger position.
    self.slider = { x=sx, y=by - 10 * s, w=sw, h=bs + 20 * s, max=light.max }
    local gap = 6 * s
    local seg = (sw - gap * (LIGHT_STEPS - 1)) / LIGHT_STEPS
    local filled = math.floor(light.level / light.max * LIGHT_STEPS + 0.5)
    for i = 0, LIGHT_STEPS - 1 do
        self:addRect(sx + i * (seg + gap), by + 18 * s, seg, 36 * s, i < filled and 0 or 255, line, 0, 6 * s)
        hit(sx + i * (seg + gap), by, seg + gap, bs, math.floor((i + 1) / LIGHT_STEPS * light.max + 0.5))
    end
    local presets = { { '关闭', 0 }, { '低', math.floor(light.max * 0.15 + 0.5) }, { '中', math.floor(light.max / 2 + 0.5) }, { '高', light.max } }
    local py, ph = y + 172 * s, 56 * s
    local pw = (w - 48 * s - 36 * s) / 4
    for i, preset in ipairs(presets) do
        local px, on = x + 24 * s + (i - 1) * (pw + 12 * s), preset[2] == light.level
        self:addRect(px, py, pw, ph, on and 0 or 255, on and 0 or line, 0, 14 * s)
        self:addText(preset[1], px + pw / 2, py + 17 * s, 22 * s, { color=on and 255 or 0, bold=on, align='c', width=pw })
        hit(px, py, pw, ph, preset[2])
    end
end

-- ------------------------------------------------------------------ gestures

local function inside(box, pos)
    return pos.x >= box.x and pos.x < box.x + box.w and pos.y >= box.y and pos.y < box.y + box.h
end

function Panel:hitAt(pos)
    local hits = self:currentPage().hits
    for i = #hits, 1, -1 do
        if inside(hits[i], pos) then return hits[i] end
    end
end

function Panel:cardAt(pos)
    for _, card in ipairs(self:currentPage().cards) do
        if inside(card, pos) then return card end
    end
end

function Panel:goPage(index)
    local count = #self.snapshot.pages
    if count < 2 then return end
    self.page = index % count
    self.pressed = nil
    self:update(self.snapshot, self.tokens, self.busy, 'flashui')
end

function Panel:onTap(_, gesture)
    if not self.snapshot then return true end
    -- With touch-to-light, the tap that wakes a dark screen only turns the light on.
    if self.on_interaction and self.on_interaction() then return true end
    local pos = gesture.pos
    if self.popover then
        local p = self:popoverGeometry()
        if inside(p, pos) then
            for _, region in ipairs(self.popover_hits or {}) do
                if inside(region, pos) then self.on_backlight(region.level);break end
            end
        else
            self.popover = nil
            self:update(self.snapshot, self.tokens, self.busy, 'flashui')
        end
        return true
    end
    local target = self:hitAt(pos)
    if target and target['local'] then
        local kind = target['local']
        if kind == 'menu' then self.on_menu()
        elseif kind == 'backlight' then self.on_backlight_open()
        elseif kind == 'page' then self:goPage(target.value)
        else self.on_refresh() end
        return true
    end
    if self.busy then return true end
    if target and target.tile and target.confirm then
        local armed, now = self.armed, os.time()
        if not (armed and armed.tile == target.tile and armed.action == target.action and armed.value == target.value
            and now - armed.time <= CONFIRM_SECONDS) then
            self.armed = { tile=target.tile, action=target.action, value=target.value, time=now }
            self.on_confirm(target)
            return true
        end
    end
    self.armed = nil
    if target and target.tile then
        local card = self:cardAt(pos)
        self.pressed = card and card.id
        self:update(self.snapshot, self.tokens, self.busy, 'fast')
        self.on_action(target, pos)
    elseif self:cardAt(pos) then
        local card = self:cardAt(pos)
        local state = self.snapshot.states[card.id]
        if not state or not state.available then self.on_refresh() end
    end
    return true
end

function Panel:sliderLevel(x)
    local slider = self.slider
    local fraction = math.max(0, math.min(1, (x - slider.x) / slider.w))
    return math.floor(fraction * slider.max + 0.5)
end

-- Live drag on the backlight bar: apply on every step change with a fast (A2) refresh, settle on release.
function Panel:onPan(_, gesture)
    if not (self.popover and self.slider) then return false end
    local pos = gesture.pos
    if not self.sliding then
        if not inside(self.slider, pos) then return false end
        self.sliding = true
    end
    local level = self:sliderLevel(pos.x)
    if level ~= self.popover.level then self.on_backlight(level, 'fast') end
    return true
end

function Panel:onPanRelease(_, gesture)
    if not self.sliding then return false end
    self.sliding = false
    self.on_backlight(self:sliderLevel(gesture.pos.x), 'ui')
    return true
end

function Panel:onSwipe(_, gesture)
    if self.popover and self.slider and inside(self.slider, gesture.pos) then
        -- A quick flick along the bar ends where the finger left the screen.
        local finish = gesture.end_pos and gesture.end_pos.x
            or gesture.pos.x + (gesture.direction == 'east' and 1 or gesture.direction == 'west' and -1 or 0) * (gesture.distance or 0)
        self.on_backlight(self:sliderLevel(finish), 'ui')
        return true
    end
    if self.popover or not self.snapshot then return true end
    if self.on_interaction and self.on_interaction() then return true end
    if gesture.direction == 'west' then self:goPage(self.page + 1)
    elseif gesture.direction == 'east' then self:goPage(self.page - 1) end
    return true
end

function Panel:onHold() self.on_menu();return true end
function Panel:onCloseWidget() self:freeItems() end

return Panel
