local Updater=dofile('nativeha.koplugin/updater.lua')
local checks=0
local function check(value,message)assert(value,message);checks=checks+1 end
local function hash(data)return string.format('%064x',#data)end   -- stand-in digest: length, zero padded
local dirs={plugin='/kp/',icons='/icons/',root='/root/',backup='/backup/'}
local files={['plugin/main.lua']='new main',['plugin/panelwidget.lua']='new panel',['icons/sun-w.svg']='<svg/>'}
local function manifest()
    local list={}
    for path,content in pairs(files)do list[#list+1]={path=path,bytes=#content,sha256=hash(content)}end
    table.sort(list,function(a,b)return a.path<b.path end)
    return {version='0.4.1',files=list}
end
local disk,writes
local function reset()
    disk={['/kp/main.lua']='old main',['/kp/panelwidget.lua']='old panel'};writes=0
end
local fs={read=function(p)return disk[p]end,write=function(p,d)writes=writes+1;disk[p]=d;return true end,mkdir=function()end}
local served
local function request(_,path,body)
    if path:match('/manifest$')then return served end
    return {path=body.path,content=files[body.path]}
end

check(Updater.target('plugin/main.lua',dirs)=='/kp/main.lua','Map plugin files')
check(Updater.target('icons/sun-w.svg',dirs)=='/icons/sun-w.svg','Map icons')
for _,bad in ipairs({'plugin/../../etc/passwd','plugin/main.sh','icons/x.svg.lua','/etc/shadow','plugin/Main.lua','koreader.sh'})do
    check(Updater.target(bad,dirs)==nil,'Reject path '..bad)
end
reset();served=manifest()
check(Updater.run(request,hash,fs,dirs)=='0.4.1','Install a verified bundle')
check(disk['/kp/main.lua']=='new main' and disk['/icons/sun-w.svg']=='<svg/>','Write every file')
check(Updater.hasBackup(fs,dirs),'Keep a backup')
check(Updater.rollback(fs,dirs) and disk['/kp/main.lua']=='old main','Roll back to the previous files')

reset();served=manifest();served.files[1].sha256=string.rep('0',64)
local ok,err=Updater.run(request,hash,fs,dirs)
check(not ok and err:find('校验'),'Reject a corrupt file')
check(writes==0 and disk['/kp/main.lua']=='old main','Nothing is written when verification fails')

reset();served=manifest();table.insert(served.files,{path='plugin/../../x.lua',bytes=1,sha256=string.rep('a',64)})
check(not Updater.run(request,hash,fs,dirs) and writes==0,'Reject manifests with disallowed paths')
reset();served={version='1',files={{path='icons/a.svg',bytes=1,sha256=string.rep('a',64)}}}
check(not Updater.run(request,hash,fs,dirs),'Require the plugin entry point')
reset();served=nil
check(not Updater.run(function()return nil,'HA 未开启'end,hash,fs,dirs),'Respect HA refusing updates')
print('Plugin updater contract: '..checks..' checks passed')
