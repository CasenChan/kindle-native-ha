# Kindle Native HA

在 Kindle 原系统上运行的 Home Assistant 原生控制面板。KOReader Lua 插件直接绘制中文黑白卡片和 SVG 图标；HA 侧提供可视化编辑器，并由服务端统一渲染屏幕，网页预览与 Kindle 画面完全一致。

## 功能

- **页面 → 房间分组 → 卡片**：最多 8 个命名页面，底部页签直接切换；一页可放多个房间分组，标题栏显示自动小结（如「2 盏灯开着 · 25.8°C」）。
- **自定义网格**：每页 1–4 列，分组合计最多 8 行（4×6、3×6 等任意组合）；每张卡片可设宽×高，在预览里拖动换位、拖右下角改大小。
- **Kindle 控制**：灯、开关、风扇、加湿器（拨钮开关，可调光的灯带亮度 −/+）；空调目标温度 −/+ 与模式切换；窗帘打开 / 暂停 / 关闭；媒体播放器上一首 / 播放暂停 / 下一首；门锁上锁（开锁需逐卡开启并二次确认）；场景、脚本、按钮执行；门窗、人体等显示中文状态。
- **温度单位**：跟随 HA，或固定摄氏 / 华氏；空调与温度传感器统一换算，Kindle 加减温度也按所选单位。
- **背光调节**：Kindle 顶部太阳按钮，12 段亮度条（可点选，也可按住拖动或快速滑动）与关闭/低/中/高档位；可开启「触摸点亮」，点一下屏幕亮起、无操作自动熄灭；可设夜间时段自动调暗并在早上恢复；每台 Kindle 在 HA 中有一个「背光」数字实体，可在自动化里调节。
- **省电少闪**：状态没变时只刷新顶部状态行，不再整屏重绘；无人操作一段时间后自动回到首页（可设）。
- **HA 编辑器**：可搜索的实体选择、19 个图标、撤销 / 重做（Ctrl+Z）、复制卡片与页面、深色主题与手机布局、设备管理（在线状态、电量、插件版本、同步状态、撤销配对）、配对地址设置。
- **插件在线更新（可选，默认关闭）**：HA 集成内置配套的 Kindle 插件；开启后可在 Kindle 菜单里手动更新，逐文件 SHA-256 校验、先备份、可一键恢复。
- **安全**：十分钟一次性文件配对，独立设备密钥；服务调用只限已保存卡片、白名单服务及配对用户的实体权限。
- 重启自动进入面板；默认接电持续刷新、电池休眠保留画面，唤醒后刷新。

## 已验证环境

| 组件 | 版本 |
| --- | --- |
| Kindle | Paperwhite 1，固件 5.6.1.1，已越狱 |
| KOReader | Kindle 2026.07.1 |
| Home Assistant Core | 2026.9.2 |
| Kindle Panel 集成 | 0.2.0 实机验证；0.3–0.5 尚待实机验证 |

0.2.0 已在实机验证中文与图标、布局同步、配对、灯光控制、开机进入、接电及休眠唤醒。0.3 / 0.4 重做了编辑器与 Kindle 绘制，HA 集成已在 Home Assistant 2026.2 测试框架中跑通完整流程，但 Kindle 上的字体、触摸、背光和刷新效果需要在实机上重新确认。本项目以已经安装好 KUAL、Hotfix 和 KOReader 的 Kindle 为起点。

## 快速开始

1. 按[安装说明](docs/install.md)构建并安装 HA 集成。
2. 在 HA 添加 **Kindle Panel**，打开侧边栏 **Kindle 面板**，把示例卡片换成实际实体并保存。
3. 将原生插件部署到 Kindle，在编辑器「设备」里下载一次性配对文件并导入。
4. 验证控制与退出后，再安装开机启动。

从 0.2 升级：HA 集成与 Kindle 插件需要**一起更新**（0.3 起屏幕数据格式不同）。0.3 → 0.4 可先更新 HA，再用 USB 或在线更新升级 Kindle。已保存的布局会自动迁移为一个页面、一个不带标题的分组，卡片顺序不变。

## 开发与检查

需要 Python 3.10+、Node.js 和 npm；Python 逻辑测试与打包仅使用标准库。

```sh
python ha-integration/build.py
python -m unittest discover -s ha-integration/tests -q
npm --prefix native-ha ci
npm --prefix native-ha test
npm --prefix native-ha run check
python ha-integration/package.py
```

可选：在装有 `pytest-homeassistant-custom-component`（Python 3.13）的环境里，于 `ha-integration/` 目录运行 `pytest`，在真实 HA 核心中测试配对、快照、控制、撤销、在线更新和迁移。

离线预览：`python ha-integration/preview_server.py`，随后访问 `http://127.0.0.1:8765`（加 `?dark` 看深色主题，`?narrow` 看手机布局）。它使用 `demo.py` 中的虚构实体，不连接实际 HA。打包结果位于 `ha-integration/dist/`，不提交生成的 ZIP。

## 目录

| 路径 | 内容 |
| --- | --- |
| `ha-integration/custom_components/kindle_panel` | HA 配置流、存储、配对与设备 API；`protocol.py` 布局模型，`display.py` 状态文案，`render.py` 屏幕渲染 |
| `ha-integration/frontend` | 编辑器源文件（`src/`）与图标 |
| `ha-integration/build.py` | 生成前端单文件、原生图标（黑/白/灰）、默认画面和控制器 |
| `native-ha/nativeha.koplugin` | 绘制指令、触摸、背光、在线更新、网络与状态逻辑 |
| `native-ha/controller-source.lua` | 控制器规范源；构建时复制为插件 main.lua |
| `native-ha/startup` | 开机任务及安装器 |
| `native-ha/tests` | 设备 API、传输、面板绘制与更新器合约检查 |
| `ha-integration/tests_ha` | 在真实 HA 核心中运行的集成测试 |
| `docs` | 安装、架构与恢复说明 |

[架构和凭据边界](docs/architecture.md) · [维护与恢复](docs/recovery.md) · [开发说明](CONTRIBUTING.md)

固件、越狱安装包、KOReader 二进制、设备备份、日志、配对文件和个人配置均不随源码发布。第三方依赖请从各自官方来源取得。
