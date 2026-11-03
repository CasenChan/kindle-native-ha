-- Exercises panelwidget.lua against minimal KOReader stand-ins and the real default frame.
local checks=0
local function check(value,message)assert(value,message);checks=checks+1 end
local painted,dirty,widgets={},{},0
local function class(base)
    base=base or {}
    base.__index=base
    function base:extend(fields)fields=fields or {};fields.__index=fields;return setmetatable(fields,{__index=self})end
    function base:new(fields)fields=fields or {};setmetatable(fields,{__index=self});if fields.init then fields:init()end;return fields end
    return base
end
package.preload['ffi/blitbuffer']=function()return {Color8=function(v)return {gray=v}end,COLOR_WHITE={gray=255},COLOR_BLACK={gray=0}}end
package.preload['device']=function()return {screen={getWidth=function()return 758 end,getHeight=function()return 1024 end,
    scaleBySize=function(_,v)return v end}}end
package.preload['ui/font']=function()return {getFace=function(_,name,size)return {name=name,size=size}end}end
package.preload['ui/geometry']=function()return class({})end
package.preload['ui/gesturerange']=function()return class({})end
local regions={}
package.preload['ui/uimanager']=function()return {setDirty=function(_,widget,mode,region)dirty[#dirty+1]=mode;regions[#dirty]=region end}end
local Text=class({})
function Text:getSize()local n=0;for _ in tostring(self.text):gmatch('[%z\1-\127\194-\244][\128-\191]*')do n=n+1 end;return {w=n*self.face.size,h=math.floor(self.face.size*1.3)}end
function Text:paintTo(_,x,y)painted[#painted+1]={kind='text',text=self.text,x=x,y=y}end
function Text:free()widgets=widgets-1 end
local OriginalNew=Text.new
function Text:new(fields)widgets=widgets+1;return OriginalNew(self,fields)end
package.preload['ui/widget/textwidget']=function()return Text end
local Icon=class({})
function Icon:paintTo(_,x,y)painted[#painted+1]={kind='icon',file=self.file,x=x,y=y}end
package.preload['ui/widget/iconwidget']=function()return Icon end
package.preload['ui/widget/container/inputcontainer']=function()return class({})end

-- tiny JSON decoder is unnecessary: the default frame is loaded through fengari's host JSON-free path
local Panel=dofile('nativeha.koplugin/panelwidget.lua')
local frame={protocol=2,revision=1,screen={width=758,height=1024,scale=1},refresh_seconds=30,
    states={lamp={available=true,state='off'},ac={available=true,state='cool'},door={available=false,state='unavailable'},
        lock={available=true,state='locked'}},
    pages={
        {id='home',title='家',
         ops={{t='r',x=20,y=128,w=351,h=268,f=255,b=2,c=0,r=18},{t='x',x=28,y=84,s=19,v='',c=110,k='status'},
              {t='x',x=48,y=300,s=46,v='关闭',b=true},{t='x',x=700,y=300,s=46,v='24',a='r',w=300,u='°C'},
              {t='r',x=680,y=28,w=52,h=52,f=255,b=2,r=26,k='backlight'},{t='i',x=693,y=41,s=26,n='sun',c='k',k='backlight'},
              {t='i',x=48,y=150,s=38,n='../evil',c='k'}},
         hits={{x=0,y=0,w=600,h=128,['local']='refresh'},{x=670,y=18,w=67,h=76,['local']='backlight'},
               {x=20,y=128,w=351,h=268,tile='lamp',action='power',value=true},
               {x=20,y=400,w=72,h=72,tile='ac',action='temperature',value=23},
               {x=200,y=960,w=120,h=60,['local']='page',value=1},
               {x=400,y=700,w=300,h=200,tile='lock',action='lock',value=false,confirm='再次轻触以开锁'}},
         cards={{id='lamp',x=20,y=128,w=351,h=268,r=18},{id='ac',x=20,y=400,w=718,h=268,r=18},{id='door',x=20,y=700,w=351,h=200,r=14}}},
        {id='two',title='二',ops={{t='x',x=28,y=30,s=38,v='二',b=true}},hits={},cards={}},
    }}
local events={}
local panel=Panel:new{
    on_refresh=function()events[#events+1]='refresh'end,
    on_menu=function()events[#events+1]='menu'end,
    on_action=function(hit,pos)events[#events+1]=hit.tile..':'..hit.action..':'..tostring(hit.value)end,
    on_backlight_open=function()events[#events+1]='backlight'end,
    on_backlight=function(level)events[#events+1]='level:'..level end,
    on_confirm=function(hit)events[#events+1]='confirm:'..hit.tile end,
    on_interaction=function()interactions=(interactions or 0)+1;return swallow end,
}
panel:update(frame,{status='11月3日 已更新',battery='82%'},false)
check(dirty[#dirty]=='ui','Normal updates use a partial refresh')
panel:paintTo({paintRect=function()end,paintRoundedRect=function()end,paintBorder=function()end},0,0)
local texts,icons={},{}
for _,item in ipairs(painted)do
    if item.kind=='text' then texts[#texts+1]=item.text else icons[#icons+1]=item.file end
end
local joined=table.concat(texts,'|')
check(joined:find('11月3日 已更新',1,true),'Fill the status token')
check(joined:find('°C',1,true),'Draw units next to values')
check(icons[2]:find('sensor.svg',1,true),'Unsafe icon names fall back to a bundled icon')
local unit_x,value_x
for _,item in ipairs(painted)do if item.text=='24' then value_x=item.x elseif item.text=='°C' then unit_x=item.x end end
check(unit_x and value_x and unit_x>value_x and unit_x<700,'Right-aligned value and unit end at the anchor')
local function tap(x,y)panel:onTap(nil,{pos={x=x,y=y}})end
tap(100,200);check(events[#events]=='lamp:power:true','Card taps send the hit action')
check(panel.pressed=='lamp','Pressed card gets feedback')
tap(40,420);check(events[#events]=='ac:temperature:23','Topmost hit wins inside a card')
tap(100,800);check(events[#events]=='refresh','Tapping an offline card refreshes')
tap(100,50);check(events[#events]=='refresh','Header tap refreshes')
panel.busy=true;local count=#events;tap(100,200)
check(#events==count,'Ignore control taps while busy');panel.busy=false
tap(700,40);check(events[#events]=='backlight','Sun button opens the backlight popover')
panel.popover={level=12,min=0,max=24}
panel:update(frame,{},false)
tap(420,290);check(events[#events]:match('^level:'),'Popover presets set a level')
local slider=panel.slider
check(slider and slider.w>200,'The popover exposes a draggable bar')
local levels={}
panel.on_backlight=function(level,mode)levels[#levels+1]={level,mode};panel.popover.level=level end
panel:onPan(nil,{pos={x=slider.x+slider.w*0.25,y=slider.y+slider.h/2}})
panel:onPan(nil,{pos={x=slider.x+slider.w*0.5,y=slider.y+slider.h/2}})
check(#levels==2 and levels[1][1]==6 and levels[2][1]==12 and levels[2][2]=='fast','Dragging adjusts live with fast refresh')
panel:onPan(nil,{pos={x=slider.x+slider.w*0.5+1,y=slider.y+slider.h/2}})
check(#levels==2,'No refresh while the level does not change')
panel:onPanRelease(nil,{pos={x=slider.x+slider.w+80,y=slider.y}})
check(levels[#levels][1]==24 and levels[#levels][2]=='ui','Release settles with a clean refresh, clamped to the maximum')
panel:onSwipe(nil,{direction='west',distance=slider.w,pos={x=slider.x+slider.w-1,y=slider.y+slider.h/2}})
check(levels[#levels][1]==0 and panel.page==0,'A flick along the bar sets the level instead of turning the page')
check(not panel:onPan(nil,{pos={x=10,y=900}}),'Drags outside the bar are ignored')
tap(10,900);check(panel.popover==nil,'Tapping outside closes the popover')
panel:onPan(nil,{pos={x=slider.x+10,y=slider.y+10}})
check(#levels==4,'No slider without the popover')
tap(250,980);check(panel.page==1,'Footer tab switches page')
check(dirty[#dirty]=='flashui','Page changes flash to clear ghosting')
panel:onSwipe(nil,{direction='west'});check(panel.page==0,'Swipe wraps around pages')
panel.page=0;panel:update(frame,{},false)
tap(500,800);check(events[#events]=='confirm:lock','Unlocking first asks for confirmation')
tap(500,800);check(events[#events]=='lock:lock:false','A second tap within five seconds unlocks')
tap(500,800);check(events[#events]=='confirm:lock','Confirmation is needed again for the next unlock')
check((interactions or 0)>=10,'Taps and swipes report user interaction')
local counted=panel.updates
panel:update(frame,{status='14:33 已更新'},false,nil,true)
check(panel.updates==counted,'Status-only refreshes do not count towards the full refresh')
check(regions[#dirty] and regions[#dirty].y<=84 and regions[#dirty].y>=60 and regions[#dirty].h<80,'Status-only refreshes repaint just the header strip')
local fulls=0
for _=1,12 do panel:update(frame,{},false);if dirty[#dirty]=='full' then fulls=fulls+1 end end
check(fulls==1,'Every 12 content updates trigger exactly one full refresh')
swallow=true;count=#events;tap(100,200)
check(#events==count,'The tap that wakes the backlight does nothing else');swallow=false
local before=widgets;panel:update(frame,{},false);panel:onCloseWidget()
check(widgets<=before,'Text widgets are freed')
print('Native panel contract: '..checks..' checks passed')
