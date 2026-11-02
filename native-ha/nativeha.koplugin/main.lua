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
    local cached=readJSON(ROOT..'snapshot-cache.json') or readJSON(ROOT..'default-snapshot.json')
    if not self.client:accept(cached,false) then
        UIManager:show(InfoMessage:new{text='面板资源不完整，请重新安装。'});return
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
    self.status='正在连接…'
    self.panel=self.Panel:new{
        on_refresh=function()self:refresh()end,
        on_menu=function()self:showMenu()end,
        on_action=function(tile_id,action,value)self:perform(tile_id,action,value)end,
    }
    self.panel:update(cached,self.status,false)
    UIManager:show(self.panel)
    self:updatePower()
    writeFile('/tmp/nativeha_ui_ready','ready')
    UIManager:nextTick(self.refresh_task)
end

function NativeHA:updatePower()
    if not self.active then return end
    local info=self:deviceInfo()
    local layout=self.client.snapshot.layout
    local awake=layout.power_mode=='always-refresh' or info.charging
    if awake~=self.keep_awake then
        self.keep_awake=awake
        PluginShare.keepalive=awake or self.old_keepalive
        PluginShare.pause_auto_suspend=awake or self.old_pause
        os.execute('lipc-set-prop com.lab126.powerd preventScreenSaver '..(awake and '1' or '0'))
    end
end

function NativeHA:render()
    if self.active then self.panel:update(self.client.snapshot,self.status,self.busy)end
end

function NativeHA:pairIfPresent()
    local pairing=readJSON(ROOT..'kindle-pairing.json')
    if not pairing or type(pairing.code)~='string' then return true end
    if self.failed_pair_code==pairing.code then return nil,'配对码已失效，请在 HA 下载新的配对文件'end
    local ok,request=pcall(self.Transport,pairing.server_url)
    if not ok then return nil,'配对文件中的地址不受支持'end
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
    self.busy,self.status=true,'正在读取设备…';self:render();UIManager:forceRePaint()
    local paired,pair_error=self:pairIfPresent()
    local result,err,code
    if paired then result,err,code=self.client:refresh(self:deviceInfo())else err=pair_error end
    self.busy=false
    if result then
        local power=self:deviceInfo()
        self.status='已连接 · '..(power.charging and '接电' or '电池')..' '..tostring(power.battery)..'%'
        writeJSON(ROOT..'snapshot-cache.json',result)
    else self.status=err or '连接失败，请刷新' end
    self:updatePower()
    self:render()
    if not self.captured then UIManager:unschedule(self.capture_task);UIManager:scheduleIn(1,self.capture_task)end
    local interval=self.client.snapshot.layout.refresh_seconds or 30
    UIManager:scheduleIn(math.max(15,interval),self.refresh_task)
end

function NativeHA:perform(tile_id,action,value)
    if not self.active or self.busy then return end
    if not self.client:available(tile_id)then self:refresh();return end
    self.busy,self.status=true,'正在发送指令…';self:render();UIManager:forceRePaint()
    local result,err,code=self.client:action(tile_id,action,value)
    self.busy=false
    self.status=result and '指令已发送，等待设备状态' or (err or '指令未完成')
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
            {{text='连接说明',callback=function()
                close();UIManager:show(InfoMessage:new{text='在 HA 网页的“Kindle 面板”里选择实体、图标和布局。\n\n首次使用请点击“配对 Kindle”，将下载的 kindle-pairing.json 放到 Kindle 的 nativeha 文件夹，再打开本面板。'})
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
