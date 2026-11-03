local Client=dofile('nativeha.koplugin/deviceapi.lua')
local checks=0
local function check(value,message)assert(value,message);checks=checks+1 end
local function snapshot()
    return {protocol=2,revision=3,refresh_seconds=30,power_mode='external-refresh',
        screen={width=758,height=1024,scale=1},
        pages={{id='home',title='家',
            ops={{t='r',x=20,y=128,w=351,h=268,f=255,b=2,c=0,r=18},{t='x',x=48,y=300,s=24,v='Lamp'},
                {t='i',x=48,y=150,s=38,n='bulb',c='k'},{t='x',x=28,y=84,s=19,v='',k='status'}},
            hits={{x=20,y=128,w=351,h=268,tile='left',action='power',value=false},{x=0,y=0,w=600,h=128,['local']='refresh'}},
            cards={{id='left',x=20,y=128,w=351,h=268,r=18}}}},
        states={left={state='on',available=true}}}
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
local bad=snapshot();bad.protocol=1
check(not client:accept(bad,true),'Reject frames from an older HA integration')
bad=snapshot();bad.pages[1].ops[1].w=9000
check(not client:accept(bad,true),'Reject out-of-screen drawing')
bad=snapshot();bad.pages[1].hits[1].tile='ghost'
check(not client:accept(bad,true),'Reject hits for tiles without state')
bad=snapshot();bad.pages[1].ops[3].n='../../etc/passwd'
check(not client:accept(bad,true),'Reject icon names that could escape the icon directory')
bad=snapshot();bad.pages[1].ops[2].s=99999
check(not client:accept(bad,true),'Reject unreasonable text sizes')
bad=snapshot();bad.states.left.available='yes'
check(not client:accept(bad,true),'Reject malformed state')
bad=snapshot();bad.pages={}
check(not client:accept(bad,true),'Reject frames without pages')
print('Scoped device API contract: '..checks..' checks passed')
