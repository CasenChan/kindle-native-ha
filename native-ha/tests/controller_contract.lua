-- Exercises controller logic (remote backlight, night schedule, return-home, quiet refresh) with KOReader stand-ins.
local checks=0
local function check(value,message)assert(value,message);checks=checks+1 end
local scheduled,files,clock={},{},{hour=12,min=0}
local light={on=true,level=12,max=24}
local function class()
    local base={}
    base.__index=base
    function base:extend(fields)fields=fields or {};fields.__index=fields;return setmetatable(fields,{__index=self})end
    return base
end
local powerd={fl_min=0,fl_max=24,
    isFrontlightOn=function()return light.on end,frontlightIntensity=function()return light.level end,
    setIntensity=function(_,v)light.level=v end,turnOnFrontlight=function()light.on=true end,
    turnOffFrontlight=function()light.on=false end,getCapacity=function()return 80 end,
    isCharging=function()return true end,isCharged=function()return false end}
package.preload['device']=function()return {hasFrontlight=function()return true end,getPowerDevice=function()return powerd end,
    screen={getWidth=function()return 758 end,getHeight=function()return 1024 end}}end
package.preload['ui/uimanager']=function()return {scheduleIn=function(_,t,f)scheduled[#scheduled+1]={t=t,f=f}end,
    unschedule=function()end,forceRePaint=function()end,show=function()end,nextTick=function()end}end
package.preload['ui/widget/buttondialog']=function()return class()end
package.preload['ui/widget/infomessage']=function()local c=class();function c:new(f)return f end;return c end
package.preload['ui/widget/container/widgetcontainer']=function()return class()end
package.preload['pluginshare']=function()return {}end
package.preload['json']=function()return {encode=function()return '{}'end,decode=function()return {}end}end
local real_open,real_date=io.open,os.date
io.open=function(path,mode)
    if not path:match('^/mnt/us/')then return real_open(path,mode)end
    if mode=='w' then return {write=function(_,v)files[path]=v;return true end,close=function()end}end
    if not files[path] then return nil end
    return {read=function()return files[path]end,close=function()end}
end
os.date=function(fmt)if fmt=='*t' then return {hour=clock.hour,min=clock.min,month=11,day=3,wday=2}end return real_date(fmt)end

local NativeHA=dofile('nativeha.koplugin/main.lua')
local renders={}
local ha=setmetatable({path='nativeha.koplugin',active=true,night={},
    panel={page=0,update=function(_,_,_,_,mode,status_only)renders[#renders+1]=status_only and 'status' or (mode or 'ui')end,
        queuePopover=function(_,state)renders[#renders+1]='queued:'..state.level end,
        updatePopover=function(_,state,mode)renders[#renders+1]=mode..':'..state.level end,
        goPage=function(self,index)self.page=index;renders[#renders+1]='page:'..index end,
        currentPage=function()return {cards={{id='lamp',x=20,y=128,w=351,h=268}}}end,
        cardBox=function(_,id)if id=='lamp' then return {x=14,y=122,w=363,h=280}end end},
    client={snapshot={},online=true}},{__index=NativeHA})

-- remote backlight from the HA number entity
ha.client.snapshot={backlight_target={id=1,level=50}}
check(ha:applyRemoteBacklight(),'Apply a queued HA backlight level')
check(light.level==12 and light.on,'50% of a 0-24 range is level 12')
ha.client.snapshot={backlight_target={id=2,level=25}};ha:applyRemoteBacklight()
check(light.level==6,'25% maps to level 6')
light.level=20
check(not ha:applyRemoteBacklight() and light.level==20,'An acknowledged command is never re-applied over a manual change')
check(ha:deviceInfo().backlight_ack==2 and ha:deviceInfo().backlight==83,'Report the applied id and the real level')
ha.client.snapshot={backlight_target={id=3,level=0}};ha:applyRemoteBacklight()
check(not light.on,'0% turns the frontlight off')
light.on,light.level=true,18

-- night schedule across midnight
ha.client.snapshot={night_light={enabled=true,start='22:00',['end']='07:00',level=10}}
clock.hour=21;ha:applyNightLight();check(light.level==18,'Nothing happens before the window')
clock.hour=23;ha:applyNightLight();check(light.level==2 and ha.night.active,'Dim to 10% when the window starts')
light.level=5;ha:applyNightLight();check(light.level==5,'A manual change at night is kept')
check(files['/mnt/us/nativeha/night-light.json'],'Night state survives restarts')
clock.hour=7;ha:applyNightLight();check(light.level==18 and not ha.night.active,'Restore the daytime level in the morning')
ha.client.snapshot={night_light={enabled=false,start='22:00',['end']='07:00',level=10}}
clock.hour=23;ha:applyNightLight();check(light.level==18,'Disabled schedule never dims')

-- return to the first page after inactivity
ha.client.snapshot={home_timeout=3};ha.panel.page=2
ha.last_interaction=os.time()-60;ha:returnHome();check(ha.panel.page==2,'Stay while the user was recently active')
ha.last_interaction=os.time()-200;ha:returnHome();check(ha.panel.page==0,'Return home after the timeout')
check(renders[#renders]=='page:0','Returning home is a normal page turn')
ha.client.snapshot={home_timeout=0};ha.panel.page=1;ha.last_interaction=0;ha:returnHome()
check(ha.panel.page==1,'Timeout 0 disables returning home')
-- touch-to-light
scheduled={};light.on,light.level=true,16
ha.client.snapshot={touch_light={enabled=true,timeout=30}}
ha:syncTouchLight()
check(scheduled[#scheduled].t==30,'Enabling touch-to-light starts the idle timer')
ha:goDark()
check(not light.on and ha.auto_dark,'The light goes off after the idle time')
check(ha:deviceInfo().backlight==67,'HA keeps seeing the level a touch restores, not 0')
ha.client.snapshot.backlight_target={id=9,level=25};ha:applyRemoteBacklight()
check(not light.on and ha.wake_level==6,'An HA command while dark changes the wake level without lighting up')
ha.client.snapshot.backlight_target=nil
check(ha:noteInteraction()==true and light.on and light.level==6,'A touch wakes the light at the wake level and is swallowed')
check(ha:noteInteraction()==false,'Later touches act normally')
ha.panel.popover={};ha:goDark()
check(light.on,'The light stays on while the backlight popover is open');ha.panel.popover=nil
ha:goDark();ha.client.snapshot={touch_light={enabled=false,timeout=30}};ha:syncTouchLight()
check(light.on and light.level==6 and not ha.auto_dark,'Turning the feature off restores the light')

-- dragging the backlight bar: light follows every step, picture is only queued
light.on,light.level=true,10
ha:setBacklight(14,'fast');check(light.level==14 and renders[#renders]=='queued:14','A drag step changes the light at once and only queues a repaint')
ha:setBacklight(15,'fast');check(light.level==15 and renders[#renders]=='queued:15','Every step reaches the hardware')
ha:setBacklight(15,'ui');check(renders[#renders]=='ui:15','Release repaints the popover cleanly')

-- which regions a refresh repaints
local function frame(rev,hashes,id)
    local regions={}
    for i,h in ipairs(hashes)do regions[i]={x=0,y=i*100,w=700,h=90,hash=h}end
    return {revision=rev,pages={{id=id or 'home',regions=regions}}}
end
ha.panel.page=0
local changed=ha:changedRegions(frame(1,{'a','b','c'}),frame(1,{'a','B','c'}))
check(#changed==1 and changed[1].y==200,'Only the region whose fingerprint changed is repainted')
check(#ha:changedRegions(frame(1,{'a','b'}),frame(1,{'a','b'}))==0,'An unchanged page repaints nothing but the status strip')
check(ha:changedRegions(frame(1,{'a'}),frame(2,{'a'}))==nil,'A new layout revision repaints the whole page')
check(ha:changedRegions(frame(1,{'a'}),frame(1,{'a','b'}))==nil,'A changed region list repaints the whole page')
check(ha:changedRegions(frame(1,{'a'},'home'),frame(1,{'a'},'other'))==nil,'A different page repaints the whole page')
local with_pressed=ha:changedRegions(frame(1,{'a'}),frame(1,{'a'}),'lamp')
check(#with_pressed==1 and with_pressed[1].x==14,'The pressed outline is cleared by repainting just that card')
local many={};local more={}
for i=1,10 do many[i]='x'..i;more[i]='y'..i end
check(ha:changedRegions(frame(1,many),frame(1,more))==nil,'When most of the page changed, repaint it once')

-- plugin update explanations
local shown
package.loaded['ui/uimanager'].show=function(_,widget)shown=widget.text end
ha.version='0.5.0';ha.client.online=true
ha.client.snapshot={plugin={version='0.5.0',update=false,allowed=false}};ha:explainUpdate()
check(shown:find('尚未开启'),'Explain that HA has updates switched off')
ha.client.snapshot={plugin={version='0.5.0',update=false,allowed=true}};ha:explainUpdate()
check(shown:find('已是最新'),'Explain that the plugin is current')
ha.client.snapshot={};ha:explainUpdate()
check(shown:find('过旧'),'Explain that the HA integration is too old')
print('Controller contract: '..checks..' checks passed')
io.open,os.date=real_open,real_date
