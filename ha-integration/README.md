# Kindle Panel 0.2.0

自定义 Home Assistant 集成，提供侧边栏可视化编辑器、共享屏幕几何、持久布局、一次性配对和受限设备 API。

## 构建

```sh
python ha-integration/build.py
python -m unittest discover -s ha-integration/tests -q
python ha-integration/package.py
```

`dist/kindle-panel-0.2.0.zip` 包含 `custom_components/kindle_panel/`，旁边的 `manifest.json` 记录各文件 SHA-256。固定归档顺序、时间戳和权限使相同源文件在同一 Python/zlib 环境中可重复打包。

## 安装与使用

将集成复制到 HA 配置目录，重启 HA，进入“设置 → 设备与服务 → 添加集成 → Kindle Panel”。随后打开侧边栏“Kindle 面板”。

默认卡片是示例实体。先选择自己的实体、名称、图标与布局，再点击“保存并同步”。点击模拟屏卡片只用于编辑，不会调用设备服务。

“配对 Kindle”下载一次性文件，十分钟内放入设备的 `nativeha/` 目录。详细步骤见[安装说明](../docs/install.md)。

## 源文件

`protocol.py`：布局、几何、状态过滤、服务白名单及配对密钥逻辑。\
`__init__.py`：HA HTTP、WebSocket、存储与侧边栏适配。\
`frontend/editor-source.js` 和 `frontend/icons.json`：编辑器和图标源。\
`custom_components/kindle_panel/frontend/editor.js`：构建输出。

本地演示运行 `python ha-integration/preview_server.py`，访问 `http://127.0.0.1:8765`。演示不连接实际 HA。[接口与权限设计](../docs/architecture.md)。
