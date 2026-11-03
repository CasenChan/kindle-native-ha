# 原生 Kindle 客户端

KOReader Lua 插件，通过 Kindle Panel 的受限 API 获取服务端渲染的绘制指令，使用原生控件绘制并处理触摸、翻页和背光。

- `controller-source.lua`：控制器规范源，修改后运行 `python ha-integration/build.py`。
- `nativeha.koplugin/`：可部署插件，包含控制器、绘制、状态客户端和传输。
- `icons/`（黑、白、浅灰三套）、`default-snapshot.json`：由 HA 构建脚本生成。
- `extensions/nativeha/`：KUAL 启动器。
- `startup/`：PW1 开机任务、USB 挂载守卫和安装器。
- `deploy_usb.py --device <挂载目录>`：复制当前客户端，备份并读回验证；已有配置会保留。
- `prepare_startup_usb.py --device <挂载目录>`：为已配对且已验证的 PW1 准备一次性开机安装器。

安装与运行步骤见[完整安装说明](../docs/install.md)，维护入口见[恢复说明](../docs/recovery.md)。

`npm test` 执行设备 API、受限传输和面板绘制/触摸合约检查；`npm run check` 检查全部已部署 Lua 文件的语法。Fengari 是电脑端测试工具，不会复制到 Kindle。字体、触摸、网络和休眠仍需实机验证。
