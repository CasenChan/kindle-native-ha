local Client = {}
Client.__index = Client

function Client.new(request, now)
    return setmetatable({ request = request, now = now or os.time, online = false }, Client)
end

function Client:accept(snapshot, fresh)
    if type(snapshot) ~= 'table' or type(snapshot.layout) ~= 'table'
        or type(snapshot.layout.tiles) ~= 'table' or #snapshot.layout.tiles < 1 or #snapshot.layout.tiles > 24
        or type(snapshot.geometry) ~= 'table' or type(snapshot.geometry.cards) ~= 'table'
        or type(snapshot.states) ~= 'table' or type(snapshot.revision) ~= 'number' then
        return nil, '布局数据有误，请在 HA 网页重新保存'
    end
    local width, height = snapshot.geometry.width, snapshot.geometry.height
    if type(width) ~= 'number' or type(height) ~= 'number'
        or width < 400 or width > 2732 or height < 400 or height > 2732 then
        return nil, '屏幕尺寸数据有误'
    end
    if type(snapshot.geometry.pages)~='number' or snapshot.geometry.pages<1 or snapshot.geometry.pages>24
        or type(snapshot.geometry.fonts)~='table' then return nil,'页面数据有误'end
    for _,key in ipairs({'header','title','value','small'})do
        local value=snapshot.geometry.fonts[key]
        if type(value)~='number' or value<8 or value>160 then return nil,'字体数据有误'end
    end
    local tiles = {}
    for _, tile in ipairs(snapshot.layout.tiles) do
        if type(tile) ~= 'table' or type(tile.id) ~= 'string' or type(tile.title) ~= 'string' then
            return nil, '卡片数据有误'
        end
        tiles[tile.id] = tile
        local state=snapshot.states[tile.id]
        if type(state)~='table' or type(state.available)~='boolean' or type(state.state)~='string' then return nil,'设备状态数据有误'end
    end
    for _, card in ipairs(snapshot.geometry.cards) do
        if not tiles[card.id] or type(card.metrics) ~= 'table' then return nil, '卡片位置数据有误' end
        for _, key in ipairs({ 'x', 'y', 'w', 'h', 'page' }) do
            if type(card[key]) ~= 'number' or card[key] ~= card[key] then return nil, '卡片位置数据有误' end
        end
        if card.x < 0 or card.y < 0 or card.w <= 0 or card.h <= 0
            or card.x + card.w > width or card.y + card.h > height then
            return nil, '卡片超出了屏幕范围'
        end
        for _,key in ipairs({'pad','icon_size','icon_y','title_y','value_y','title_font','value_font','small_font',
            'climate_title_x','mode_y','current_y','climate_value_font','label_font','control_h','control_font'})do
            local value=card.metrics[key]
            if type(value)~='number' or value~=value or value<0 or value>600 then return nil,'卡片尺寸数据有误'end
        end
    end
    self.snapshot, self.tiles = snapshot, tiles
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
    return self.online and self.tiles[tile_id] ~= nil and type(state) == 'table'
        and state.available == true and age ~= nil and age >= 0 and age <= 60 or false
end

function Client:action(tile_id, action, value)
    if not self:available(tile_id) then return nil, '状态已过期或设备离线，请刷新' end
    return self:_call('/api/kindle_panel/device/action', {
        revision = self.snapshot.revision, tile_id = tile_id, action = action, value = value,
    })
end

return Client
