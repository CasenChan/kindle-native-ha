# Kindle Native HA

在 Kindle 原系统上运行的 Home Assistant 原生控制面板。使用 KOReader Lua 控件直接绘制中文、黑白卡片和 SVG 图标，HA 侧提供可视化编辑器与 Kindle 屏幕预览。

## 功能

- 在 HA 侧边栏选择实体，修改名称、图标、卡片宽度、顺序和每页布局。
- Kindle 控制灯光、开关、风扇和空调，执行场景、脚本及按钮操作；其他实体显示状态。
- 网页与 Kindle 共用布局几何，保存后按刷新周期同步；预览点击只选择编辑，不操作设备。
- 十分钟有效的一次性文件配对，独立设备密钥，服务调用仅限已保存卡片及配对用户的实体权限。
- 重启自动进入面板；默认接电持续刷新、电池休眠保留画面，唤醒后刷新。
- 支持分页、手动刷新、维护退出及 USB 禁用自动启动。

## 已验证环境

| 组件 | 版本 |
| --- | --- |
| Kindle | Paperwhite 1，固件 5.6.1.1，已越狱 |
| KOReader | Kindle 2026.07.1 |
| Home Assistant Core | 2026.9.2 |
| Kindle Panel 集成 | 0.2.0 |

实机已验证中文与图标、网页布局同步、配对、灯光控制、开机进入、接电及休眠唤醒。其他机型和固件仍需自行验证。本项目以已经安装好 KUAL、Hotfix 和 KOReader 的 Kindle 为起点。

## 快速开始

1. 按[安装说明](docs/install.md)构建并安装 HA 集成。
2. 在 HA 添加 **Kindle Panel**，打开侧边栏 **Kindle 面板**，将示例卡片改为实际存在的实体并保存。
3. 将原生插件部署到 Kindle，下载并导入一次性配对文件。
4. 验证控制与退出后，再安装开机启动。

网页地址为你的 HA 地址后加 `/kindle-panel`。Kindle 直接连接 HA，运行时无需电脑。

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

离线预览：`python ha-integration/preview_server.py`，随后访问 `http://127.0.0.1:8765`。它使用示例状态，不连接实际 HA。打包结果位于 `ha-integration/dist/`，不提交生成的 ZIP。

## 目录

| 路径 | 内容 |
| --- | --- |
| `ha-integration/custom_components/kindle_panel` | HA 配置流、存储、配对与设备 API |
| `ha-integration/frontend` | 编辑器与图标源文件 |
| `ha-integration/build.py` | 生成前端单文件、原生图标、默认快照和控制器 |
| `native-ha/nativeha.koplugin` | 原生卡片、触摸、网络与状态逻辑 |
| `native-ha/controller-source.lua` | 控制器规范源；构建时复制为插件 main.lua |
| `native-ha/startup` | 开机任务及安装器 |
| `native-ha/tests` | 当前设备 API 与传输合约检查 |
| `docs` | 安装、架构与恢复说明 |

[架构和凭据边界](docs/architecture.md) · [维护与恢复](docs/recovery.md) · [开发说明](CONTRIBUTING.md)

固件、越狱安装包、KOReader 二进制、设备备份、日志、配对文件和个人配置均不随源码发布。第三方依赖请从各自官方来源取得。
