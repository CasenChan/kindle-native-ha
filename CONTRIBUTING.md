# 开发说明

在仓库根目录运行 README 中的构建和检查命令。Python 测试验证布局、分页、配对、服务约束和状态过滤；Lua 测试验证缓存、显式动作、过期状态、受限路径、凭据头、超时、重定向及错误处理。

规范源：

- 修改 `ha-integration/frontend/editor-source.js` 和 `icons.json`，通过 `build.py` 更新前端 bundle 和 SVG。
- 修改 `native-ha/controller-source.lua`，通过同一构建步骤更新插件 `main.lua`。
- 提交生成的 JS、SVG、默认快照和 Lua 控制器，以便直接部署；不提交 dist ZIP、依赖目录或设备状态。

每次修改两端布局或协议后，检查离线预览及实机显示。Fengari 只用于语法和逻辑验证，不能替代实际 KOReader/LuaJIT、字体、触摸和休眠测试。

本地 `setup/`、`backups/`、`diagnostics/`、`downloads/`、`secrets/` 和旧 `compatibility-test/` 均为忽略目录。配对文件、设备密钥、私人 HA 配置和缓存不得提交。示例使用虚构实体；不要将个人设备标识写回默认布局。
