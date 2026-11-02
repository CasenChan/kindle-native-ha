local Client=dofile('nativeha.koplugin/deviceapi.lua')
local checks=0
local function check(value,message)assert(value,message);checks=checks+1 end
local function snapshot()
    local metrics={pad=28,icon_size=64,icon_y=40,title_y=118,value_y=157,title_font=25,value_font=38,small_font=19,
        climate_title_x=112,mode_y=63,current_y=110,climate_value_font=45,label_font=17,control_h=60,control_font=28}
    return {revision=3,layout={tiles={{id='left',title='Lamp',kind='toggle'}}},
        geometry={width=758,height=1024,pages=1,fonts={header=34,title=25,value=38,small=20},
            cards={{id='left',x=20,y=108,w=351,h=268,page=0,metrics=metrics}}},
        states={left={state='on',available=true,attributes={}}}}
end
local calls,now,failure={},1000,false
local client=Client.new(function(method,path,body)
    calls[#calls+1]={method=method,path=path,body=body}
    if failure then return nil,'changed',409 end
    return path:match('/snapshot$') and snapshot() or {accepted=true}
end,function()return now end)
check(#calls==0,'Constructor must not send commands')
check(client:accept(snapshot(),false),'Accept a cached frame')
check(not client:available('left'),'Cached state must remain read only')
check(not client:action('left','power',false),'No commands before a fresh authenticated read')
check(#calls==0,'No outgoing request for blocked action')
check(client:refresh({battery=90,charging=true}),'Read scoped snapshot')
check(calls[1].path=='/api/kindle_panel/device/snapshot','Use only the device API')
check(calls[1].body.battery==90,'Send only relevant device telemetry')
check(client:action('left','power',false),'Send explicit desired state')
local request=calls[#calls]
check(request.body.tile_id=='left' and request.body.value==false,'Preserve explicit off')
check(request.body.entity_id==nil,'Never select arbitrary HA entities in a device request')
check(request.body.revision==3,'Bind actions to the current layout revision')
local count=#calls
check(not client:action('unconfigured','power',true),'Reject an unknown card')
check(#calls==count,'Unknown card must not reach the network')
now=1061
check(not client:action('left','power',false),'Block stale state')
now=1001;check(client:refresh({}),'Recover by reading state')
failure=true;count=#calls
local ok,err,code=client:action('left','power',false)
check(not ok and code==409,'Recognize a changed layout')
check(#calls==count+1,'Never retry an action automatically')
check(not client:available('left'),'Disable controls after a failed request')
local bad=snapshot();bad.geometry.cards[1].w=9000
check(not client:accept(bad,true),'Reject out-of-screen geometry')
bad=snapshot();bad.states.left=nil
check(not client:accept(bad,true),'Reject missing card state')
bad=snapshot();bad.geometry.cards[1].metrics.icon_size=99999
check(not client:accept(bad,true),'Reject unreasonable native icon dimensions')
print('Scoped device API contract: '..checks..' checks passed')
