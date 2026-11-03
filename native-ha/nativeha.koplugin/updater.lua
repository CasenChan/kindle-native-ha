-- Optional over-the-air plugin update from the paired HA, started only from the Kindle menu.
-- Every file must be listed in HA's manifest, match an allowlisted target and its SHA-256 before anything is
-- written; previous files are backed up first so the menu can roll back. This protects against corrupt or
-- partial downloads, not against an active attacker on the LAN (the transport is plain HTTP).
local Updater = {}

local MAX_FILES, MAX_BYTES = 300, 512 * 1024

-- Map a manifest path to an absolute target, or nil when it is not an allowed file.
function Updater.target(path, dirs)
    if type(path) ~= 'string' then return nil end
    local name = path:match('^plugin/([a-z_]+%.lua)$')
    if name then return dirs.plugin .. name end
    name = path:match('^icons/([a-z%-]+%.svg)$')
    if name then return dirs.icons .. name end
    if path == 'default-snapshot.json' then return dirs.root .. path end
end

function Updater.validate(manifest, dirs)
    if type(manifest) ~= 'table' or type(manifest.version) ~= 'string' or not manifest.version:match('^%d+[%d%.]*$')
        or type(manifest.files) ~= 'table' or #manifest.files < 1 or #manifest.files > MAX_FILES then
        return nil, '更新清单格式有误'
    end
    local has_main, seen = false, {}
    for _, file in ipairs(manifest.files) do
        if type(file) ~= 'table' or not Updater.target(file.path, dirs) or seen[file.path]
            or type(file.sha256) ~= 'string' or not file.sha256:match('^%x+$') or #file.sha256 ~= 64
            or type(file.bytes) ~= 'number' or file.bytes < 0 or file.bytes > MAX_BYTES then
            return nil, '更新清单包含不允许的文件'
        end
        seen[file.path] = true
        if file.path == 'plugin/main.lua' then has_main = true end
    end
    if not has_main then return nil, '更新清单缺少插件主程序' end
    return true
end

-- fs = { read(path) -> string|nil, write(path, data) -> bool, mkdir(path) }; sha256(data) -> lowercase hex.
function Updater.run(request, sha256, fs, dirs)
    local manifest, err = request('POST', '/api/kindle_panel/device/update/manifest', {})
    if not manifest then return nil, err or '无法读取更新清单' end
    local ok, invalid = Updater.validate(manifest, dirs)
    if not ok then return nil, invalid end
    local staged = {}
    for _, file in ipairs(manifest.files) do
        local result, file_err = request('POST', '/api/kindle_panel/device/update/file', { path = file.path })
        if not result or type(result.content) ~= 'string' then return nil, file_err or '下载更新文件失败' end
        if #result.content ~= file.bytes or sha256(result.content):lower() ~= file.sha256:lower() then
            return nil, '更新文件校验失败：' .. file.path
        end
        staged[#staged + 1] = { target = Updater.target(file.path, dirs), content = result.content, path = file.path }
    end
    -- All files verified in memory; back up what they replace, then write.
    fs.mkdir(dirs.backup)
    local backed = {}
    for _, file in ipairs(staged) do
        local previous = fs.read(file.target)
        if previous then
            local name = file.path:gsub('/', '__')
            if not fs.write(dirs.backup .. name, previous) then return nil, '无法备份旧版本，未做任何修改' end
            backed[#backed + 1] = { name = name, target = file.target }
        end
    end
    local index = {}
    for _, item in ipairs(backed) do index[#index + 1] = item.name .. '\t' .. item.target end
    if not fs.write(dirs.backup .. 'index.txt', table.concat(index, '\n')) then
        return nil, '无法备份旧版本，未做任何修改'
    end
    for _, file in ipairs(staged) do
        if not fs.write(file.target, file.content) then
            Updater.rollback(fs, dirs)
            return nil, '写入失败，已恢复旧版本'
        end
    end
    return manifest.version
end

function Updater.hasBackup(fs, dirs)
    return fs.read(dirs.backup .. 'index.txt') ~= nil
end

function Updater.rollback(fs, dirs)
    local index = fs.read(dirs.backup .. 'index.txt')
    if not index then return nil, '没有可恢复的旧版本' end
    for line in index:gmatch('[^\n]+') do
        local name, target = line:match('^([^\t]+)\t(.+)$')
        local data = name and fs.read(dirs.backup .. name)
        if not data or not fs.write(target, data) then return nil, '恢复失败：' .. tostring(name) end
    end
    return true
end

return Updater
