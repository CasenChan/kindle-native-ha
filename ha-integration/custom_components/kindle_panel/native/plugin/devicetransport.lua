local JSON = require('json')
local http = require('socket.http')
local ltn12 = require('ltn12')
local socketutil = require('socketutil')
-- LuaJSON otherwise preserves JSON null as a function sentinel, which fails
-- optional-field validation (for example when HA has no backlight command).
local decode_options = { others = { null = false } }

return function(base_url, device_key)
    base_url = base_url:gsub('/+$', '')
    assert(base_url:match('^http://[%w%.%-]+:?%d*$'), 'Unsupported server URL')
    assert(not device_key or not device_key:find('[\r\n]'), 'Invalid device key')
    return function(method, path, body)
        if not path:match('^/api/kindle_panel/') then return nil, '接口路径有误' end
        if not device_key and path ~= '/api/kindle_panel/pair' then return nil, '请先在 HA 网页配对 Kindle', 401 end
        local chunks, length = {}, 0
        local encoded = JSON.encode(body or {})
        local request = {
            url = base_url .. path, method = method, redirect = false,
            headers = { ['Content-Type'] = 'application/json', ['Content-Length'] = tostring(#encoded), Accept = 'application/json' },
            source = ltn12.source.string(encoded),
            sink = function(chunk)
                if chunk then
                    length = length + #chunk
                    if length > 2 * 1024 * 1024 then return nil, 'Response too large' end
                    chunks[#chunks + 1] = chunk
                end
                return 1
            end,
        }
        if device_key then request.headers['X-Kindle-Key'] = device_key end
        socketutil:set_timeout(3, 8)
        local ok, result, code = pcall(http.request, request)
        socketutil:reset_timeout()
        if not ok or not result then return nil, '连接失败，请检查 Wi-Fi' end
        code = tonumber(code)
        if code == 401 or code == 403 then return nil, '需要重新配对 Kindle', code end
        local decoded, value = pcall(JSON.decode, table.concat(chunks), decode_options)
        if not code or code < 200 or code >= 300 then
            local message = decoded and type(value) == 'table' and type(value.error) == 'string' and value.error:sub(1,160)
            return nil, message or 'HA 暂时无法处理请求', code
        end
        if not decoded or type(value) ~= 'table' then return nil, 'HA 返回的数据格式有误' end
        return value
    end
end
