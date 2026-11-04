local Client = {}
Client.__index = Client

local PROTOCOL = 2
local MAX_OPS, MAX_HITS = 6000, 800

function Client.new(request, now)
    return setmetatable({ request = request, now = now or os.time, online = false }, Client)
end

local function number(value, low, high)
    return type(value) == 'number' and value == value and value >= low and value <= high
end

local function box(item, width, height)
    return number(item.x, 0, width) and number(item.y, 0, height)
        and number(item.w, 0, width) and number(item.h, 0, height)
        and item.x + item.w <= width + 1 and item.y + item.h <= height + 1
end

local function validPage(page, width, height, states)
    if type(page) ~= 'table' or type(page.title) ~= 'string' or type(page.ops) ~= 'table'
        or type(page.hits) ~= 'table' or type(page.cards) ~= 'table'
        or #page.ops > MAX_OPS or #page.hits > MAX_HITS then
        return nil, '页面数据有误'
    end
    for _, op in ipairs(page.ops) do
        if type(op) ~= 'table' or not number(op.x, -1, width) or not number(op.y, -1, height) then
            return nil, '绘制数据有误'
        end
        if op.t == 'r' then
            if not box(op, width, height) then return nil, '绘制数据超出屏幕' end
        elseif op.t == 'x' then
            if not number(op.s, 8, 200) or (type(op.v) ~= 'string' and op.k == nil) then return nil, '文字数据有误' end
        elseif op.t == 'i' then
            if not number(op.s, 4, 600) or type(op.n) ~= 'string' or not op.n:match('^[a-z%-]+$') then
                return nil, '图标数据有误'
            end
        else
            return nil, '绘制数据有误'
        end
    end
    for _, hit in ipairs(page.hits) do
        if type(hit) ~= 'table' or not box(hit, width, height) then return nil, '触控区域有误' end
        if hit.tile ~= nil and (type(hit.tile) ~= 'string' or type(states[hit.tile]) ~= 'table'
            or type(hit.action) ~= 'string' or (hit.confirm ~= nil and type(hit.confirm) ~= 'string')) then
            return nil, '触控区域有误'
        end
    end
    if page.regions ~= nil then
        if type(page.regions) ~= 'table' or #page.regions > MAX_HITS then return nil, '刷新区域有误' end
        for _, region in ipairs(page.regions) do
            if type(region) ~= 'table' or type(region.hash) ~= 'string' or not box(region, width, height) then
                return nil, '刷新区域有误'
            end
        end
    end
    for _, card in ipairs(page.cards) do
        if type(card) ~= 'table' or type(card.id) ~= 'string' or not box(card, width, height) then
            return nil, '卡片位置数据有误'
        end
    end
    return true
end

function Client:accept(snapshot, fresh)
    if type(snapshot) ~= 'table' or snapshot.protocol ~= PROTOCOL or type(snapshot.revision) ~= 'number'
        or type(snapshot.pages) ~= 'table' or #snapshot.pages < 1 or #snapshot.pages > 8
        or type(snapshot.states) ~= 'table' or type(snapshot.screen) ~= 'table' then
        return nil, '布局数据有误，请更新 HA 集成与 Kindle 插件'
    end
    local width, height = snapshot.screen.width, snapshot.screen.height
    if not number(width, 400, 2732) or not number(height, 400, 2732) or not number(snapshot.screen.scale, 0.3, 4) then
        return nil, '屏幕尺寸数据有误'
    end
    if (snapshot.hash ~= nil and type(snapshot.hash) ~= 'string')
        or (snapshot.night_light ~= nil and type(snapshot.night_light) ~= 'table')
        or (snapshot.plugin ~= nil and type(snapshot.plugin) ~= 'table')
        or (snapshot.touch_light ~= nil and (type(snapshot.touch_light) ~= 'table'
            or (snapshot.touch_light.timeout ~= nil and not number(snapshot.touch_light.timeout, 5, 3600))))
        or (snapshot.home_timeout ~= nil and not number(snapshot.home_timeout, 0, 1440))
        or (snapshot.backlight_target ~= nil and (type(snapshot.backlight_target) ~= 'table'
            or not number(snapshot.backlight_target.id, 0, 2^52) or not number(snapshot.backlight_target.level, 0, 100))) then
        return nil, '布局设置数据有误'
    end
    for tile_id, state in pairs(snapshot.states) do
        if type(tile_id) ~= 'string' or type(state) ~= 'table' or type(state.available) ~= 'boolean' then
            return nil, '设备状态数据有误'
        end
    end
    for _, page in ipairs(snapshot.pages) do
        local ok, err = validPage(page, width, height, snapshot.states)
        if not ok then return nil, err end
    end
    self.snapshot = snapshot
    self.online = fresh == true
    self.last_read = fresh and self.now() or nil
    return snapshot
end

function Client:_call(path, body)
    local protected, result, err, code = pcall(self.request, 'POST', path, body)
    if not protected or not result then
        self.online = false
        return nil, protected and err or '连接失败，请刷新后重试', code
    end
    return result
end

function Client:refresh(info)
    local result, err, code = self:_call('/api/kindle_panel/device/snapshot', info or {})
    if not result then return nil, err, code end
    local accepted, validation_error = self:accept(result, true)
    if not accepted then self.online = false end
    return accepted, validation_error
end

function Client:available(tile_id)
    local state = self.snapshot and self.snapshot.states[tile_id]
    local age = self.last_read and self.now() - self.last_read
    return self.online and type(state) == 'table' and state.available == true
        and age ~= nil and age >= 0 and age <= 60 or false
end

function Client:action(tile_id, action, value)
    if not self:available(tile_id) then return nil, '状态已过期或设备离线，请刷新' end
    return self:_call('/api/kindle_panel/device/action', {
        revision = self.snapshot.revision, tile_id = tile_id, action = action, value = value,
    })
end

return Client
