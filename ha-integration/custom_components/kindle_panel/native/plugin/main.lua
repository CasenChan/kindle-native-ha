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
local NIGHT_STATE = ROOT..'night-light.json'
local BACKUP_DIR = ROOT..'plugin-backup/'


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

local function minutes(text)
    local hour,minute=tostring(text):match('^(%d%d):(%d%d)$')
    return hour and tonumber(hour)*60+tonumber(minute)
end

function NativeHA:init()
    self.ui.menu:registerToMainMenu(self)
    self.refresh_task=function()if self.active and not self.suspended then self:refresh(false)end end
    self.home_task=function()if self.active and not self.suspended then self:returnHome()end end
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
    local light=self.client and self:backlightState()
    return {width=Device.screen:getWidth(),height=Device.screen:getHeight(),battery=power:getCapacity(),
        charging=power:isCharging() or power:isCharged(),plugin_version=self.version,
        backlight=light and math.floor(light.level*100/math.max(1,light.max)+0.5) or nil,
        backlight_ack=self.backlight_ack}
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
    self.Updater=dofile(self.path..'/updater.lua')
    local ok,meta=pcall(dofile,self.path..'/_meta.lua')
    self.version=ok and type(meta)=='table' and meta.version or nil
    self.night=readJSON(NIGHT_STATE) or {}
    self.last_interaction=os.time()
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
        on_refresh=function()self:refresh(true)end,
        on_interaction=function()self:noteInteraction()end,
        on_confirm=function(hit)self.status,self.status_error=hit.confirm..'（5 秒内）',false;self:render(nil,true)end,
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
    local status=self.status
    if self:updateAvailable() and not self.status_error then status=status..' · 插件可更新' end
    return {status=status,status_error=self.status_error,offline=not self.client.online,
        battery=tostring(info.battery)..'%'..(info.charging and '+' or '')}
end

function NativeHA:render(mode,status_only)
    if self.active then self.panel:update(self.client.snapshot,self:tokens(),self.busy,mode,status_only)end
end

-- ------------------------------------------------------------------ return to the first page

function NativeHA:noteInteraction()
    self.last_interaction=os.time()
    local timeout=tonumber(self.client.snapshot.home_timeout) or 0
    UIManager:unschedule(self.home_task)
    if timeout>0 then UIManager:scheduleIn(timeout*60+1,self.home_task)end
end

function NativeHA:returnHome()
    local timeout=tonumber(self.client.snapshot.home_timeout) or 0
    if timeout<=0 or self.panel.page==0 or self.panel.popover or self.popup or self.busy then return end
    if os.time()-(self.last_interaction or 0)<timeout*60 then return end
    self.panel.page=0;self.panel.pressed=nil
    self:render('flashui')
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

function NativeHA:applyLevel(level)
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
end

function NativeHA:setBacklight(level)
    self:applyLevel(level)
    self.panel.popover=self:backlightState();self:render('ui')
end

-- Night schedule: entering the window saves the current level and dims; leaving it restores the saved level.
-- A manual change in between is kept until the next boundary. State survives restarts.
function NativeHA:applyNightLight()
    local night=self.client.snapshot.night_light
    local state=self:backlightState()
    if not state then return end
    local enabled=type(night)=='table' and night.enabled==true
    local start,finish=enabled and minutes(night.start),enabled and minutes(night['end'])
    local inside=false
    if start and finish then
        local now=os.date('*t');local current=now.hour*60+now.min
        if start<finish then inside=current>=start and current<finish else inside=current>=start or current<finish end
    end
    if inside and not self.night.active then
        self.night={active=true,day_level=state.level}
        self:applyLevel(math.floor((tonumber(night.level) or 0)*state.max/100+0.5))
        writeJSON(NIGHT_STATE,self.night)
    elseif not inside and self.night.active then
        self:applyLevel(tonumber(self.night.day_level) or state.level)
        self.night={active=false}
        writeJSON(NIGHT_STATE,self.night)
    end
end

-- HA's backlight entity queues {id, level%}; apply each id once, then report it back so HA clears the command.
function NativeHA:applyRemoteBacklight()
    local target=self.client.snapshot.backlight_target
    local state=self:backlightState()
    if type(target)~='table' or not state or type(target.id)~='number' or target.id==self.backlight_ack then return end
    self:applyLevel(math.floor((tonumber(target.level) or 0)*state.max/100+0.5))
    self.backlight_ack=target.id
    if self.panel.popover then self.panel.popover=self:backlightState() end
    UIManager:unschedule(self.refresh_task)
    UIManager:scheduleIn(2,self.refresh_task)   -- report the new level promptly
    return true
end

-- ------------------------------------------------------------------ plugin update

function NativeHA:updateAvailable()
    local plugin=self.client.snapshot.plugin
    return type(plugin)=='table' and plugin.update==true and type(plugin.version)=='string'
end

function NativeHA:updateDirs()
    return {plugin=self.path..'/',icons=ROOT..'icons/',root=ROOT,backup=BACKUP_DIR}
end

function NativeHA:updateFs()
    return {read=readFile,write=writeFile,mkdir=function(path)os.execute('mkdir -p "'..path..'"')end}
end

function NativeHA:restartAfter(message)
    UIManager:show(InfoMessage:new{text=message,timeout=3})
    UIManager:scheduleIn(3,function()
        if UIManager.restartKOReader then self:stopPanel();UIManager:restartKOReader()
        else UIManager:show(InfoMessage:new{text='请退出面板后重新进入以加载新版本。'})end
    end)
end

function NativeHA:runUpdate()
    local ok,sha2=pcall(require,'ffi/sha2')
    if not ok or type(sha2.sha256)~='function' then
        UIManager:show(InfoMessage:new{text='此 KOReader 缺少 SHA-256 校验组件，无法在线更新。请用 USB 更新。'});return
    end
    self.busy,self.status,self.status_error=true,'正在下载并校验插件…',false;self:render();UIManager:forceRePaint()
    local version,err=self.Updater.run(self.client.request,sha2.sha256,self:updateFs(),self:updateDirs())
    self.busy=false
    if not version then
        self.status,self.status_error=(err or '更新失败')..' · 未做任何修改',true;self:render();return
    end
    self:restartAfter('插件已更新到 '..version..'，正在重新启动面板…')
end

function NativeHA:runRollback()
    local ok,err=self.Updater.rollback(self:updateFs(),self:updateDirs())
    if not ok then UIManager:show(InfoMessage:new{text=err});return end
    self:restartAfter('已恢复上一版本插件，正在重新启动面板…')
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

-- Background refreshes repaint only what changed: an identical frame (same hash) just updates the status strip,
-- so an idle panel no longer flickers or triggers the periodic full refresh.
function NativeHA:refresh(manual)
    if not self.active or self.busy or self.suspended then return end
    UIManager:unschedule(self.refresh_task)
    local was_error=self.status_error
    if manual or was_error then
        self.busy,self.status,self.status_error=true,'正在读取设备…',false;self:render(nil,true);UIManager:forceRePaint()
    end
    self.busy=true
    local previous=self.client.snapshot.hash
    local paired,pair_error=self:pairIfPresent()
    local result,err
    if paired then result,err=self.client:refresh(self:deviceInfo())else err=pair_error end
    self.busy=false
    local pressed=self.panel.pressed~=nil
    self.panel.pressed=nil
    if result then
        self.status,self.status_error=updatedText(),false
        writeJSON(ROOT..'snapshot-cache.json',result)
    else
        self.status,self.status_error=(err or '连接失败')..' · 轻触重试',true
    end
    self:updatePower()
    self:applyNightLight()
    local remote=result and self:applyRemoteBacklight()
    local changed=pressed or (result and (result.hash==nil or result.hash~=previous))
    if result and not changed then self:render(nil,true)else self:render()end
    self:returnHome()
    if remote then return result end
    if not self.captured then UIManager:unschedule(self.capture_task);UIManager:scheduleIn(1,self.capture_task)end
    UIManager:scheduleIn(math.max(15,self.client.snapshot.refresh_seconds or 30),self.refresh_task)
    return result
end

-- A tap on stale state first refreshes, then re-reads the tap position on the fresh frame, so one tap is enough
-- and the command is always computed from current state (e.g. toggle direction, next temperature).
function NativeHA:perform(hit,pos)
    if not self.active or self.busy then return end
    if not self.client:available(hit.tile) then
        if not self:refresh(true) then return end
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
    local buttons={
        {{text='刷新设备状态',callback=function()close();self:refresh(true)end}},
        {{text='屏幕背光',callback=function()close();self:toggleBacklight()end}},
        {{text='连接说明',callback=function()
            close();UIManager:show(InfoMessage:new{text='在 HA 网页的“Kindle 面板”里编辑页面、房间分组和卡片。\n\n首次使用请在“设备”里下载配对文件，放到 Kindle 的 nativeha 文件夹，再打开本面板。'})
        end}},
    }
    if self:updateAvailable() then
        table.insert(buttons,{{text='更新插件 '..tostring(self.version)..' → '..self.client.snapshot.plugin.version,
            callback=function()close();self:confirmUpdate()end}})
    end
    if self.Updater.hasBackup(self:updateFs(),self:updateDirs()) then
        table.insert(buttons,{{text='恢复上一版本插件',callback=function()close();self:runRollback()end}})
    end
    table.insert(buttons,{{text='退出到 Kindle',callback=function()
        close();writeFile('/tmp/nativeha_manual_exit','manual');self:stopPanel();UIManager:quit()
    end}})
    table.insert(buttons,{{text='返回控制页',callback=close}})
    dialog=ButtonDialog:new{
        title='Kindle 控制面板',
        modal=true,
        buttons=buttons,
        tap_close_callback=function()self.popup=nil end,
    }
    self.popup=dialog;UIManager:show(dialog)
end

function NativeHA:confirmUpdate()
    local ConfirmBox=require('ui/widget/confirmbox')
    UIManager:show(ConfirmBox:new{
        text='从 HA 下载并安装插件 '..self.client.snapshot.plugin.version..'？\n\n所有文件校验通过后才会写入，旧版本会先备份，可在菜单中恢复。请只在可信的家庭网络中使用。',
        ok_text='更新',cancel_text='取消',
        ok_callback=function()self:runUpdate()end,
    })
end

function NativeHA:stopPanel()
    if not self.active then return end
    self.active=false
    UIManager:unschedule(self.refresh_task);UIManager:unschedule(self.capture_task);UIManager:unschedule(self.home_task)
    if self.popup then UIManager:close(self.popup);self.popup=nil end
    if self.panel then UIManager:close(self.panel);self.panel=nil end
    PluginShare.keepalive,PluginShare.pause_auto_suspend=self.old_keepalive,self.old_pause
    os.execute('lipc-set-prop com.lab126.powerd preventScreenSaver '..(self.old_keepalive and '1' or '0'))
    for key,entry in pairs(self.previous_settings or {})do
        if entry.value==nil then G_reader_settings:delSetting(key)else G_reader_settings:saveSetting(key,entry.value)end
    end
end
function NativeHA:onSuspend()self.suspended=true;UIManager:unschedule(self.refresh_task);UIManager:unschedule(self.capture_task);UIManager:unschedule(self.home_task)end
function NativeHA:onResume()if self.active then self.suspended=false;self:updatePower();UIManager:scheduleIn(1,self.refresh_task)end end
function NativeHA:onCharging()if self.active then self:updatePower()end end
function NativeHA:onNotCharging()if self.active then self:updatePower()end end
function NativeHA:onNetworkConnected()if self.active and not self.suspended then UIManager:scheduleIn(1,self.refresh_task)end end
function NativeHA:onCloseWidget()self:stopPanel()end
return NativeHA
