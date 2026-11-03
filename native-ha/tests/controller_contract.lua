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
package.preload['ui/widget/infomessage']=function()return class()end
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
    panel={page=0,update=function(_,_,_,_,mode,status_only)renders[#renders+1]=status_only and 'status' or (mode or 'ui')end},
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
check(renders[#renders]=='flashui','Returning home flashes to clear ghosting')
ha.client.snapshot={home_timeout=0};ha.panel.page=1;ha.last_interaction=0;ha:returnHome()
check(ha.panel.page==1,'Timeout 0 disables returning home')
print('Controller contract: '..checks..' checks passed')
io.open,os.date=real_open,real_date
