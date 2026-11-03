# 安装

本流程面向已越狱、已安装 Hotfix、KUAL 与 KOReader 的 Paperwhite 1。固件和越狱过程不包含在本仓库中。实测环境为 PW1 / 5.6.1.1、KOReader 2026.07.1、HA Core 2026.9.2。

## 1. 安装 HA 集成

在仓库根目录执行：

```sh
python ha-integration/build.py
python ha-integration/package.py
```

解压 `ha-integration/dist/kindle-panel-0.3.0.zip`，将其中 `custom_components/kindle_panel` 复制到 HA 配置目录的 `custom_components/kindle_panel`。可使用 HA 官方 File editor；配置目录在不同安装中可能显示为 `/config` 或 `/homeassistant`。

检查 HA 配置并重启，在“设置 → 设备与服务 → 添加集成”搜索 **Kindle Panel**。完成后打开侧边栏 **Kindle 面板**。

将默认示例卡片替换成真实存在的实体，然后保存。编辑器左栏按「页面 → 房间分组 → 卡片」组织：可新建页面和分组、搜索添加实体、改名和换图标；在中间预览里拖动卡片换位置，拖右下角改大小。「面板设置」里可选温度单位（跟随 HA / °C / °F）、刷新间隔和常驻方式。

从 0.2 升级时，已保存的布局会自动迁移；Kindle 插件也必须同时更新（见下一节），否则 Kindle 会提示布局数据有误。

## 2. 部署原生客户端

用 USB 连接 Kindle，确定挂载目录。Windows 示例：

```sh
python native-ha/deploy_usb.py --device H:/
```

Linux 示例：

```sh
python native-ha/deploy_usb.py --device /media/Kindle
```

脚本会检查 Kindle 版本文件及 KOReader 入口，将被覆盖的文件备份到电脑 `backups/`，逐个复制并读回验证。已有 `nativeha/config.json` 会保留；首次部署使用不含凭据的示例配置。测试依赖与 Node.js 不复制到设备。

安全弹出、拔线，打开 **KUAL → Home Assistant**，确认卡片、图标、右上角菜单和退出均正常。

## 3. 配对

1. 退出面板，USB 连接 Kindle。
2. 在 HA 编辑器的 **设备** 标签确认「Kindle 连接 HA 的地址」是局域网 `http://` 地址（如 `http://192.168.1.20:8123`），点击 **下载配对文件**，把 `kindle-pairing.json` 放到设备 `nativeha/`。
3. 十分钟内安全弹出拔线，Kindle 连接家中 Wi-Fi，打开原生面板。
4. 配对成功后检查真实状态，验证一个可恢复的控制操作，再退出并接回 USB。

配对文件会自动移除。密钥保存在 Kindle 系统分区的私有数据目录；无需管理员 Token。客户端只连接局域网 HTTP 地址；如果你通过 https 或外网地址打开 HA，请在设备页手动填写内网地址。最多配对 5 台，不用的设备可在设备页撤销。

## 4. 安装开机启动

先完成上一节的配对、控制和退出验证。在电脑执行：

```sh
python native-ha/prepare_startup_usb.py --device H:/
```

此步骤只准备文件，并不在电脑上修改 Kindle 系统。脚本保留已配对的服务器地址，备份旧 RUNME，写入一次性安装入口。

安全弹出拔线，在 Kindle 主屏搜索英文半角 `;log runme` 并执行，等待约十秒，再通过设置菜单正常重启。无需打开 KUAL，应自动进入 HA。

安装器写入 `/etc/upstart/nativeha.conf` 与 `/var/local/nativeha/autostart.sh`，随后恢复根文件系统只读。任务等待 Kindle 主界面就绪及用户分区可用，无崩溃重启循环；未配对时不会自动启动。

验证接电、拔线休眠及唤醒后，从菜单退出，再通过 USB 保存诊断日志。确认安装成功后，可将 USB 根目录的 `RUNME.sh` 移到电脑备份，防止重复执行。

## 日常使用

默认接电每 30 秒更新；电池可按 KOReader 的无操作超时休眠，短按电源也可休眠。墨水屏保留 HA 画面，唤醒后刷新。网页改变布局后，客户端下一轮读取会同步。

右上角房屋图标或屏幕长按打开维护菜单。手动退出后，用 KUAL 重新进入，或重启自动进入。电脑可以关闭，运行只需要 Kindle 与 HA 在同一可达网络。

顶部太阳按钮打开背光面板：两侧按钮逐级调暗/调亮，中间亮度条可直接点选，下方为关闭、低、中、高四档；点面板外关闭。底部页签切换页面，也可左右滑动。点击状态已过期的卡片会先刷新再执行，一次点击即可。

## 夜间背光与自动回首页

在编辑器「面板设置」中可开启夜间背光：进入时段时 Kindle 记住当前亮度并调到设定值，结束时恢复；时段内手动调节会保留到下一次切换。时间按 Kindle 自身时钟计算。「自动回到首页」会在无人操作达到设定时间后回到第一页。

## 在 HA 中调节背光

配对后，HA「设置 → 设备与服务 → Kindle Panel」下每台 Kindle 都有「背光」实体（0–100%），可在仪表盘或自动化中设置，例如日落后调到 10%。Kindle 会在下一次刷新时执行（休眠中则唤醒后执行），并把实际亮度同步回 HA。

## 在线更新插件（可选）

1. 先按常规流程更新 HA 集成（新版集成内置配套的 Kindle 插件）。
2. 在编辑器「面板设置 → 插件在线更新」中开启。
3. Kindle 刷新后，状态行显示「插件可更新」，在右上角菜单选择「更新插件」并确认。全部文件校验通过后才写入，旧文件备份在 `nativeha/plugin-backup/`，面板随后自动重启。
4. 如有问题，在菜单中选择「恢复上一版本插件」，或照常用 USB 部署。更新完成后可在 HA 中关闭在线更新。

在线更新只适合可信的家庭网络，原因见[架构说明](architecture.md#插件在线更新)。
