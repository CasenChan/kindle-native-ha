local checks=0
local function check(condition,message)assert(condition,message);checks=checks+1 end
local status,response,throw_error=200,'fixture',false
local last_request,calls,timeout_set,timeout_reset=nil,0,0,0
package.preload['json']=function()return {
    encode=function()return '{}'end,
    decode=function(value)
        if value=='bad-json' then error('invalid json') end
        return value=='error' and {error='layout changed'} or {accepted=true}
    end,
}end
package.preload['ltn12']=function()return {source={string=function(value)return function()return value end end}}end
package.preload['socketutil']=function()return {
    set_timeout=function(_,block,total)
        check(block==3 and total==8,'Bound network timeouts');timeout_set=timeout_set+1
    end,
    reset_timeout=function()timeout_reset=timeout_reset+1 end,
}end
package.preload['socket.http']=function()return {request=function(request)
    calls=calls+1;last_request=request
    if throw_error then error('private-device-key')end
    local ok=request.sink(response)
    if not ok then return nil,'response limit'end
    request.sink(nil)
    return 1,status
end}end
local Transport=dofile('nativeha.koplugin/devicetransport.lua')
local request=Transport('http://ha.example/','test-device.test-secret')
check(request('POST','/api/kindle_panel/device/snapshot',{}),'Decode a snapshot')
check(last_request.url=='http://ha.example/api/kindle_panel/device/snapshot','Use only the configured host')
check(last_request.headers['X-Kindle-Key']=='test-device.test-secret','Send only the scoped device key')
check(last_request.headers.Authorization==nil,'Do not use an HA administrator bearer token')
check(last_request.redirect==false,'Never forward credentials through redirects')
check(last_request.headers['Content-Type']=='application/json','Send JSON')
check(tonumber(last_request.headers['Content-Length'])==#last_request.source(),'Accurate UTF-8 request length')
local before=calls
check(not request('POST','/api/services/switch/turn_on',{}),'Reject the generic HA service API')
check(calls==before,'Reject invalid paths before network access')
local unpaired=Transport('http://ha.example')
check(not unpaired('POST','/api/kindle_panel/device/snapshot',{}),'Block unpaired snapshots')
check(calls==before,'An unpaired device must not request states')
check(unpaired('POST','/api/kindle_panel/pair',{}),'Permit the one-use pairing endpoint')
check(last_request.headers['X-Kindle-Key']==nil,'Pairing needs no device credential')
status=409;response='error'
local ok,err,code=request('POST','/api/kindle_panel/device/action',{})
check(not ok and code==409 and err=='layout changed','Preserve revision-conflict errors')
status=302;response='fixture';before=calls
check(not request('POST','/api/kindle_panel/device/action',{}),'Reject redirects')
check(calls==before+1,'Never retry a write or follow a redirect')
status=401
ok,err,code=request('POST','/api/kindle_panel/device/snapshot',{})
check(not ok and code==401 and err=='需要重新配对 Kindle','Report revoked pairing')
status=200;response='bad-json'
check(not request('POST','/api/kindle_panel/device/snapshot',{}),'Reject malformed JSON')
response=string.rep('x',2*1024*1024+1)
check(not request('POST','/api/kindle_panel/device/snapshot',{}),'Bound response memory')
response='fixture';throw_error=true
ok,err=request('POST','/api/kindle_panel/device/snapshot',{})
check(not ok and not err:find('private'),'Hide credential-bearing low-level errors')
check(timeout_set==timeout_reset,'Restore shared socket timeouts after every request')
check(not pcall(Transport,'https://ha.example','key'),'Never silently downgrade HTTPS')
check(not pcall(Transport,'http://ha.example','key\r\nInjected: yes'),'Reject header injection')
print('Scoped device transport: '..checks..' checks passed')
