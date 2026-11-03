local ButtonDialog = require('ui/widget/buttondialog')
local Device = require('device')
local InfoMessage = require('ui/widget/infomessage')
local JSON = require('json')
local PluginShare = require('pluginshare')
local UIManager = require('ui/uimanager')
local WidgetContainer = require('ui/widget/container/widgetcontainer')

local NativeHA = WidgetContainer:extend{ name='nativeha', is_doc_only=false }
local ROOT = '/mnt/us/nativeha/'
local PRIVATE = '/var/local/nativeha/'
local WEEKDAYS = { '日', '一', '二', '三', '四', '五', '六' }

local function readFile(path)
    local file=io.open(path,'r');if not file then return nil end
    local value=file:read('*a');file:close();return value
end
local function readJSON(path)
    local value=readFile(path);if not value then return nil end
    local ok,result=pcall(JSON.decode,value)
    return ok and type(result)=='table' and result or nil
end
local function writeFile(path,value)
    local file=io.open(path,'w');if not file then return false end
    local ok=file:write(value);file:close();return ok~=nil
end
local function writeJSON(path,value)
    local ok,encoded=pcall(JSON.encode,value)
    return ok and writeFile(path,encoded) or false
end
local function updatedText()
    local now=os.date('*t')
    return string.format('%d月%d日 周%s · %02d:%02d 已更新',now.month,now.day,WEEKDAYS[now.wday],now.hour,now.min)
end

function NativeHA:init()
    self.ui.menu:registerToMainMenu(self)
    self.refresh_task=function()if self.active and not self.suspended then self:refresh()end end
    self.capture_task=function()
        if self.active and not self.captured and not self.popup and not self.suspended then
            UIManager:forceRePaint()
            self.captured=pcall(Device.screen.shot,Device.screen,ROOT..'diagnostics/last-screen.png')
        end
    end
    if os.getenv('KINDLE_NATIVE_HA')=='1' then UIManager:nextTick(function()self:startPanel()end) end
end

function NativeHA:addToMainMenu(items)
    items.nativeha={text='Home Assistant',sorting_hint='more_tools',callback=function()self:startPanel()end}
end

function NativeHA:deviceInfo()
    local power=Device:getPowerDevice()
    return {width=Device.screen:getWidth(),height=Device.screen:getHeight(),battery=power:getCapacity(),
        charging=power:isCharging() or power:isCharged()}
end

function NativeHA:makeClient()
    local key=readFile(PRIVATE..'device-key')
    if key then key=key:gsub('^%s+',''):gsub('%s+$','') end
    local ok,request=pcall(self.Transport,self.config.base_url,key)
    if not ok then request=function()return nil,'连接设置有误，请重新配对'end end
    return self.Client.new(request)
end

function NativeHA:startPanel()
    if self.active then return end
    self.config=readJSON(ROOT..'config.json') or {}
    self.config.base_url=self.config.base_url or 'http://homeassistant.local'
    self.Client=dofile(self.path..'/deviceapi.lua')
    self.Transport=dofile(self.path..'/devicetransport.lua')
    self.Panel=dofile(self.path..'/panelwidget.lua')
    self.client=self:makeClient()
    local screen=self:deviceInfo()
    local cached=readJSON(ROOT..'snapshot-cache.json')
    if not self.client:accept(cached,false) or cached.screen.width~=screen.width or cached.screen.height~=screen.height then
        cached=readJSON(ROOT..'default-snapshot.json')
        if not self.client:accept(cached,false) then
            UIManager:show(InfoMessage:new{text='面板资源不完整，请重新安装。'});return
        end
    end
    self.previous_settings={}
    for _,key in ipairs({'screensaver_type','screensaver_show_message','auto_restore_wifi','auto_disable_wifi'})do
        self.previous_settings[key]={value=G_reader_settings:readSetting(key)}
    end
    G_reader_settings:saveSetting('screensaver_type','disable')
    G_reader_settings:makeFalse('screensaver_show_message')
    G_reader_settings:makeTrue('auto_restore_wifi')
    G_reader_settings:makeFalse('auto_disable_wifi')
    self.old_keepalive,self.old_pause=PluginShare.keepalive,PluginShare.pause_auto_suspend
    self.active,self.busy,self.suspended=true,false,false
    self.status,self.status_error='正在连接…',false
    self.panel=self.Panel:new{
        on_refresh=function()self:refresh()end,
        on_menu=function()self:showMenu()end,
        on_action=function(hit,pos)self:perform(hit,pos)end,
        on_backlight_open=function()self:toggleBacklight()end,
        on_backlight=function(level)self:setBacklight(level)end,
    }
    self:render('full')
    UIManager:show(self.panel)
    self:updatePower()
    writeFile('/tmp/nativeha_ui_ready','ready')
    UIManager:nextTick(self.refresh_task)
end

function NativeHA:updatePower()
    if not self.active then return end
    local info=self:deviceInfo()
    local awake=self.client.snapshot.power_mode=='always-refresh' or info.charging
    if awake~=self.keep_awake then
        self.keep_awake=awake
        PluginShare.keepalive=awake or self.old_keepalive
        PluginShare.pause_auto_suspend=awake or self.old_pause
        os.execute('lipc-set-prop com.lab126.powerd preventScreenSaver '..(awake and '1' or '0'))
    end
end

function NativeHA:tokens()
    local info=self:deviceInfo()
    return {status=self.status,status_error=self.status_error,offline=not self.client.online,
        battery=tostring(info.battery)..'%'..(info.charging and '+' or '')}
end

function NativeHA:render(mode)
    if self.active then self.panel:update(self.client.snapshot,self:tokens(),self.busy,mode)end
end

-- ------------------------------------------------------------------ backlight

function NativeHA:backlightState()
    if not Device:hasFrontlight() then return nil end
    local powerd=Device:getPowerDevice()
    local level=powerd:isFrontlightOn() and powerd:frontlightIntensity() or 0
    return {level=level,min=powerd.fl_min or 0,max=powerd.fl_max or 24}
end

function NativeHA:toggleBacklight()
    if self.panel.popover then
        self.panel.popover=nil;self:render('flashui');return
    end
    local state=self:backlightState()
    if not state then UIManager:show(InfoMessage:new{text='这台 Kindle 没有可调节的背光。',timeout=3});return end
    self.panel.popover=state;self:render('ui')
end

function NativeHA:setBacklight(level)
    local powerd=Device:getPowerDevice()
    local state=self:backlightState()
    if not state then return end
    level=math.max(0,math.min(state.max,level))
    if level<=0 then
        powerd:turnOffFrontlight()
    else
        powerd:setIntensity(math.max(state.min,level))
        if not powerd:isFrontlightOn() then powerd:turnOnFrontlight() end
    end
    self.panel.popover=self:backlightState();self:render('ui')
end

-- ------------------------------------------------------------------ data

function NativeHA:pairIfPresent()
    local pairing=readJSON(ROOT..'kindle-pairing.json')
    if not pairing or type(pairing.code)~='string' then return true end
    if self.failed_pair_code==pairing.code then return nil,'配对码已失效，请在 HA 下载新的配对文件'end
    local ok,request=pcall(self.Transport,pairing.server_url)
    if not ok then return nil,'配对文件中的地址不受支持，请填写 http:// 局域网地址'end
    local info=self:deviceInfo()
    local result,err,code=request('POST','/api/kindle_panel/pair',{
        code=pairing.code,name=pairing.name or 'Kindle 控制屏',width=info.width,height=info.height,
    })
    if not result then
        if code==400 or code==401 then self.failed_pair_code=pairing.code end
        return nil,err
    end
    local key=result.device_key
    if type(key)~='string' or not key:match('^[a-f0-9]+%.[a-zA-Z0-9_-]+$') then return nil,'配对响应有误'end
    os.execute('mkdir -p /var/local/nativeha && chmod 700 /var/local/nativeha')
    if not writeFile(PRIVATE..'device-key.new',key..'\n') then return nil,'无法保存设备配对信息'end
    if not os.rename(PRIVATE..'device-key.new',PRIVATE..'device-key') then return nil,'无法保存设备配对信息'end
    os.execute('chmod 600 /var/local/nativeha/device-key')
    self.config.base_url=pairing.server_url
    writeJSON(ROOT..'config.json',self.config)
    os.remove(ROOT..'kindle-pairing.json')
    local old=self.client.snapshot
    self.client=self:makeClient();self.client:accept(old,false)
    return true
end

function NativeHA:refresh()
    if not self.active or self.busy or self.suspended then return end
    UIManager:unschedule(self.refresh_task)
    self.busy,self.status,self.status_error=true,'正在读取设备…',false;self:render();UIManager:forceRePaint()
    local paired,pair_error=self:pairIfPresent()
    local result,err
    if paired then result,err=self.client:refresh(self:deviceInfo())else err=pair_error end
    self.busy=false
    self.panel.pressed=nil
    if result then
        self.status,self.status_error=updatedText(),false
        writeJSON(ROOT..'snapshot-cache.json',result)
    else
        self.status,self.status_error=(err or '连接失败')..' · 轻触重试',true
    end
    self:updatePower()
    self:render()
    if not self.captured then UIManager:unschedule(self.capture_task);UIManager:scheduleIn(1,self.capture_task)end
    UIManager:scheduleIn(math.max(15,self.client.snapshot.refresh_seconds or 30),self.refresh_task)
    return result
end

-- A tap on stale state first refreshes, then re-reads the tap position on the fresh frame, so one tap is enough
-- and the command is always computed from current state (e.g. toggle direction, next temperature).
function NativeHA:perform(hit,pos)
    if not self.active or self.busy then return end
    if not self.client:available(hit.tile) then
        if not self:refresh() then return end
        hit=self.panel:hitAt(pos)
        if not hit or not hit.tile or not self.client:available(hit.tile) then return end
        self.panel.pressed=hit.tile
    end
    self.busy,self.status,self.status_error=true,'正在发送指令…',false;self:render('fast');UIManager:forceRePaint()
    local result,err,code=self.client:action(hit.tile,hit.action,hit.value)
    self.busy=false
    if result then self.status,self.status_error='指令已发送，等待设备状态…',false
    else self.status,self.status_error=(err or '指令未完成')..' · 轻触重试',true;self.panel.pressed=nil end
    self:render()
    UIManager:unschedule(self.refresh_task)
    UIManager:scheduleIn(result and 1.5 or code==409 and .1 or 15,self.refresh_task)
end

function NativeHA:showMenu()
    if self.popup then return end
    local dialog
    local function close()UIManager:close(dialog);self.popup=nil end
    dialog=ButtonDialog:new{
        title='Kindle 控制面板',
        modal=true,
        buttons={
            {{text='刷新设备状态',callback=function()close();self:refresh()end}},
            {{text='屏幕背光',callback=function()close();self:toggleBacklight()end}},
            {{text='连接说明',callback=function()
                close();UIManager:show(InfoMessage:new{text='在 HA 网页的“Kindle 面板”里编辑页面、房间分组和卡片。\n\n首次使用请在“设备”里下载配对文件，放到 Kindle 的 nativeha 文件夹，再打开本面板。'})
            end}},
            {{text='退出到 Kindle',callback=function()
                close();writeFile('/tmp/nativeha_manual_exit','manual');self:stopPanel();UIManager:quit()
            end}},
            {{text='返回控制页',callback=close}},
        },
        tap_close_callback=function()self.popup=nil end,
    }
    self.popup=dialog;UIManager:show(dialog)
end

function NativeHA:stopPanel()
    if not self.active then return end
    self.active=false
    UIManager:unschedule(self.refresh_task);UIManager:unschedule(self.capture_task)
    if self.popup then UIManager:close(self.popup);self.popup=nil end
    if self.panel then UIManager:close(self.panel);self.panel=nil end
    PluginShare.keepalive,PluginShare.pause_auto_suspend=self.old_keepalive,self.old_pause
    os.execute('lipc-set-prop com.lab126.powerd preventScreenSaver '..(self.old_keepalive and '1' or '0'))
    for key,entry in pairs(self.previous_settings or {})do
        if entry.value==nil then G_reader_settings:delSetting(key)else G_reader_settings:saveSetting(key,entry.value)end
    end
end
function NativeHA:onSuspend()self.suspended=true;UIManager:unschedule(self.refresh_task);UIManager:unschedule(self.capture_task)end
function NativeHA:onResume()if self.active then self.suspended=false;self:updatePower();UIManager:scheduleIn(1,self.refresh_task)end end
function NativeHA:onCharging()if self.active then self:updatePower()end end
function NativeHA:onNotCharging()if self.active then self:updatePower()end end
function NativeHA:onNetworkConnected()if self.active and not self.suspended then UIManager:scheduleIn(1,self.refresh_task)end end
function NativeHA:onCloseWidget()self:stopPanel()end
return NativeHA
