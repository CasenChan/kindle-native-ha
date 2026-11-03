# 开发说明

在仓库根目录运行 README 中的构建和检查命令。Python 测试验证布局模型与迁移、放置、温度换算、状态文案、渲染指令（不越界、不重叠、触控只指向已保存卡片）、配对和服务约束；Lua 测试验证画面校验、显式动作、过期状态、受限路径、凭据头、超时、重定向，以及面板绘制、点击、背光面板和翻页。

规范源：

- 修改 `ha-integration/frontend/src/*.js` 和 `icons.json`，通过 `build.py` 更新前端 bundle 和三色 SVG。
- 卡片版式只改 `render.py`：Kindle 与网页预览都按其输出绘制，不要在 Lua 或 JS 中另写版式。
- 修改 `native-ha/controller-source.lua`，通过同一构建步骤更新插件 `main.lua`。
- 提交生成的 JS、SVG、默认快照和 Lua 控制器，以便直接部署；不提交 dist ZIP、依赖目录或设备状态。

每次修改两端布局或协议后，检查离线预览及实机显示。Fengari 只用于语法和逻辑验证，不能替代实际 KOReader/LuaJIT、字体、触摸和休眠测试。

本地 `setup/`、`backups/`、`diagnostics/`、`downloads/`、`secrets/` 和旧 `compatibility-test/` 均为忽略目录。配对文件、设备密钥、私人 HA 配置和缓存不得提交。示例使用虚构实体；不要将个人设备标识写回默认布局。
