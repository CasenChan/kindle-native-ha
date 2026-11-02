local Blitbuffer = require('ffi/blitbuffer')
local Device = require('device')
local Font = require('ui/font')
local Geom = require('ui/geometry')
local GestureRange = require('ui/gesturerange')
local IconWidget = require('ui/widget/iconwidget')
local InputContainer = require('ui/widget/container/inputcontainer')
local TextWidget = require('ui/widget/textwidget')
local UIManager = require('ui/uimanager')

local Panel = InputContainer:extend{ covers_fullscreen = true }
local icons = { bulb=true, thermostat=true, temperature=true, humidity=true, power=true,
    fan=true, home=true, scene=true, plug=true, sensor=true }
local mode_names = { cool='制冷', heat='制热', auto='自动', heat_cool='自动', dry='除湿', fan_only='送风', off='关机' }
local function number(value)
    if type(value) == 'string' or type(value) == 'number' then return tonumber(value) end
end
local function text(value)
    return (type(value) == 'string' or type(value) == 'number') and tostring(value) or ''
end
local function numeric(value)
    local n = number(value)
    return n and tostring(n):gsub('%.0$', '') or '—'
end
local function pixelFace(size)
    -- Geometry already uses physical pixels. Undo KOReader's UI-size scaling.
    return Font:getFace('cfont', size * 1000 / Device.screen:scaleBySize(1000))
end

function Panel:init()
    self.page, self.widgets = 0, {}
    self.dimen = Geom:new{ x=0, y=0, w=Device.screen:getWidth(), h=Device.screen:getHeight() }
    self.ges_events = {
        Tap = { GestureRange:new{ ges='tap', range=self.dimen } },
        Swipe = { GestureRange:new{ ges='swipe', range=self.dimen } },
        Hold = { GestureRange:new{ ges='hold', range=self.dimen } },
    }
end

function Panel:getSize() return self.dimen end

function Panel:clearWidgets()
    for _, item in ipairs(self.widgets or {}) do
        if item.widget.free then item.widget:free() end
    end
    self.widgets = {}
end

function Panel:addText(value, x, y, size, bold, max_width, color)
    local widget = TextWidget:new{
        text=text(value), face=pixelFace(math.max(10, math.min(72, size))),
        bold=bold or false, padding=0, max_width=max_width,
        fgcolor=color or Blitbuffer.COLOR_BLACK,
    }
    self.widgets[#self.widgets + 1] = { widget=widget, x=math.floor(x), y=math.floor(y) }
    return widget
end

function Panel:addIcon(name, x, y, size)
    if not icons[name] then name='sensor' end
    local widget = IconWidget:new{ file='/mnt/us/nativeha/icons/' .. name .. '.svg', width=size, height=size, alpha=true }
    self.widgets[#self.widgets + 1] = { widget=widget, x=math.floor(x), y=math.floor(y) }
end

function Panel:value(value, unit, x, y, size, max_width, right_aligned)
    local main = TextWidget:new{ text=text(value), face=pixelFace(size), bold=true, padding=0, max_width=max_width }
    local small = TextWidget:new{ text=text(unit), face=pixelFace(math.max(10, math.floor(size*.52))), padding=0 }
    local main_size, small_size = main:getSize(), small:getSize()
    local gap = text(unit) ~= '' and 5 or 0
    local left = right_aligned and x-main_size.w-small_size.w-gap or x
    self.widgets[#self.widgets + 1] = { widget=main, x=math.floor(left), y=math.floor(y) }
    self.widgets[#self.widgets + 1] = { widget=small, x=math.floor(left+main_size.w+gap), y=math.floor(y+main_size.h-small_size.h) }
    return main_size.h
end

function Panel:update(snapshot, status, busy)
    self.snapshot, self.status, self.busy = snapshot, status, busy
    self:clearWidgets()
    local g = snapshot.geometry
    self.page = math.max(0, math.min(self.page, g.pages-1))
    local f, gray = g.fonts, Blitbuffer.Color8(112)
    self:addText(snapshot.layout.title, g.margin, 26, f.header, true, g.width-g.margin*2-65)
    self:addIcon('home', g.width-g.margin-38, 30, 32)
    self.tile_by_id = {}
    for _, tile in ipairs(snapshot.layout.tiles) do self.tile_by_id[tile.id] = tile end
    for _, card in ipairs(g.cards) do
        if card.page == self.page then
            local tile, state = self.tile_by_id[card.id], snapshot.states[card.id] or {}
            local attr = type(state.attributes) == 'table' and state.attributes or {}
            local m, x, y = card.metrics, card.x, card.y
            local available = state.available == true
            local title_x = tile.kind == 'climate' and m.climate_title_x or m.pad
            local title_y = tile.kind == 'climate' and m.pad or m.title_y
            self:addIcon(tile.icon, x+m.pad, y+(tile.kind=='climate' and m.pad or m.icon_y), tile.kind=='climate' and (m.climate_icon_size or m.icon_size) or m.icon_size)
            self:addText(tile.title, x+title_x, y+title_y, m.title_font, false, card.w-title_x-m.pad)
            if tile.kind == 'climate' then
                self:addText(mode_names[state.state] or (available and text(state.state) or '未连接'),
                    x+m.climate_title_x, y+m.mode_y, m.small_font, false, card.w-m.climate_title_x-m.pad, gray)
                local unit = snapshot.temperature_unit or '°C'
                local label_y = y+m.current_y
                local left_label = self:addText('当前温度', x+m.pad, label_y, m.label_font, false, nil, gray)
                local right_label = TextWidget:new{ text='目标温度', face=pixelFace(m.label_font), padding=0, fgcolor=gray }
                self.widgets[#self.widgets+1] = {widget=right_label,x=x+card.w-m.pad-right_label:getSize().w,y=label_y}
                local value_y = label_y+left_label:getSize().h+3
                self:value(numeric(attr.current_temperature), unit, x+m.pad, value_y, m.climate_value_font, card.w/2-m.pad*2)
                self:value(numeric(attr.temperature), unit, x+card.w-m.pad, value_y, m.climate_value_font, card.w/2-m.pad*2, true)
                local cy = y+card.h-m.control_h
                local minus = self:addText('−', 0, 0, m.control_font, false)
                local minus_entry = self.widgets[#self.widgets];minus_entry.x=x+card.w/6-minus:getSize().w/2;minus_entry.y=cy+(m.control_h-minus:getSize().h)/2
                self:addIcon('power', x+card.w/2-14, cy+(m.control_h-28)/2, 28)
                local plus = self:addText('＋', 0, 0, m.control_font, false)
                local plus_entry = self.widgets[#self.widgets];plus_entry.x=x+card.w*5/6-plus:getSize().w/2;plus_entry.y=cy+(m.control_h-plus:getSize().h)/2
            else
                local value = not available and '未连接' or tile.kind=='toggle' and (state.state=='on' and '开启' or '关闭')
                    or tile.kind=='action' and '轻触执行' or text(state.state)
                self:value(value, tile.kind=='sensor' and text(attr.unit_of_measurement) or '', x+m.pad, y+m.value_y,
                    m.value_font, card.w-m.pad*2)
            end
        end
    end
    self:addText(status or '', g.margin, g.height-g.footer+14, f.small, false, g.width-g.margin*2-140, gray)
    self:addText(string.format('‹  %d/%d  ›', self.page+1, g.pages), g.width-g.margin-118, g.height-g.footer+14,
        f.small, false, 118, gray)
    UIManager:setDirty(self, 'ui')
end

function Panel:paintTo(bb, x, y)
    self.dimen.x, self.dimen.y = x, y
    bb:paintRect(x,y,self.dimen.w,self.dimen.h,Blitbuffer.Color8(250))
    if not self.snapshot then return end
    for _, card in ipairs(self.snapshot.geometry.cards) do
        if card.page == self.page then
            local tile, state = self.tile_by_id[card.id], self.snapshot.states[card.id] or {}
            local active = state.available and (state.state=='on' or tile.kind=='climate' and state.state~='off')
            local background = active and Blitbuffer.Color8(238) or Blitbuffer.COLOR_WHITE
            bb:paintRoundedRect(x+card.x,y+card.y,card.w,card.h,background,15)
            bb:paintBorder(x+card.x,y+card.y,card.w,card.h,1,Blitbuffer.Color8(196),15,true)
            if tile.kind == 'climate' then
                local cy=y+card.y+card.h-card.metrics.control_h
                bb:paintRect(x+card.x,cy,card.w,1,Blitbuffer.Color8(210))
                for _,part in ipairs({1,2}) do bb:paintRect(x+card.x+math.floor(card.w*part/3),cy,1,card.metrics.control_h,Blitbuffer.Color8(210)) end
            end
        end
    end
    for _, item in ipairs(self.widgets) do item.widget:paintTo(bb,x+math.floor(item.x),y+math.floor(item.y)) end
end

function Panel:onTap(_, gesture)
    local pos, g = gesture.pos, self.snapshot.geometry
    if pos.y < g.header then
        if pos.x > g.width-90 then self.on_menu() else self.on_refresh() end
        return true
    end
    if pos.y >= g.height-g.footer then
        if pos.x > g.width-150 and g.pages>1 then
            self.page = (self.page+(pos.x>g.width-70 and 1 or g.pages-1)) % g.pages
            self:update(self.snapshot,self.status,self.busy)
        else self.on_refresh() end
        return true
    end
    if self.busy then return true end
    for _, card in ipairs(g.cards) do
        if card.page==self.page and pos.x>=card.x and pos.x<card.x+card.w and pos.y>=card.y and pos.y<card.y+card.h then
            local tile, state = self.tile_by_id[card.id], self.snapshot.states[card.id] or {}
            if not state.available then self.on_refresh();return true end
            if tile.kind=='toggle' then self.on_action(tile.id,'power',state.state~='on')
            elseif tile.kind=='action' then self.on_action(tile.id,'activate')
            elseif tile.kind=='climate' and pos.y>=card.y+card.h-card.metrics.control_h then
                local part=math.min(2,math.floor((pos.x-card.x)/(card.w/3)))
                if part==1 then self.on_action(tile.id,'power',state.state=='off')
                elseif state.state~='off' then
                    local attr=state.attributes or {};local target,step=number(attr.temperature),number(attr.target_temp_step) or 1
                    if target then self.on_action(tile.id,'temperature',target+(part==0 and -step or step)) end
                end
            end
            return true
        end
    end
    return true
end

function Panel:onSwipe(_, gesture)
    local pages=self.snapshot.geometry.pages
    if gesture.direction=='west' then self.page=(self.page+1)%pages
    elseif gesture.direction=='east' then self.page=(self.page+pages-1)%pages end
    self:update(self.snapshot,self.status,self.busy)
    return true
end

function Panel:onHold() self.on_menu();return true end
function Panel:onCloseWidget() self:clearWidgets() end
return Panel
