for _, name in ipairs({ '_meta', 'deviceapi', 'devicetransport', 'panelwidget', 'main' }) do
    local path = 'nativeha.koplugin/' .. name .. '.lua'
    local chunk, err = loadfile(path)
    assert(chunk, err)
end
print('Native HA Lua source: syntax checks passed')
