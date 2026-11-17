# 项目结构

本项目是 AstrBot 插件。根目录保留插件识别、安装和加载所需的文件，各部分代码按职责放在子目录中。

```text
astrbot_plugin_anime/
  main.py              插件入口、命令注册与消息发送
  __init__.py          插件公开入口，按需加载主类
  metadata.yaml        名称、简介、版本、作者和命令说明
  _conf_schema.json    AstrBot 插件配置项
  requirements.txt     Python 依赖
  .astrbot-plugin/     插件语言包和页面说明
  core/                数据模型、存储、时间换算、来源合并与日志
  rendering/           消息模板、文字格式、提醒卡片与番组表绘制
  services/            番组刷新、封面缓存、提醒与每日/每周推送调度
  web/                 AstrBot 内嵌接口与独立 WebUI 服务
  sources/             Bangumi、bgmlist 和 YUC 数据解析
  views/               管理页、登录页及其脚本和样式
  tests/               Python 与 Node.js 回归测试
  docs/                设计与实现记录，供维护时参考
```

## 修改位置

- 命令入口在 `main.py`，默认回复和帮助文本在 `rendering/templates.py`。中英文入口共用原有业务处理，主命令不会重复执行已注册的子命令。
- 提醒文字的格式在 `rendering/formatters.py`。
- 单部动画卡片在 `rendering/card_layouts.py`，每日/每周番组表在 `rendering/swimlane.py`，共用绘图方法在 `rendering/card_canvas.py`，封面缓存位于 `services/covers.py`。
- 订阅状态检查在 `core/subscriptions.py`，未订阅、未选作品等提示在 `rendering/templates.py`。
- 管理页设置的存储与校验分别在 `core/store.py`、`web/api.py`。
- 各来源的请求和解析在 `sources/`，刷新与旧数据保留逻辑在 `services/refresh.py`。
- 每日、每周番组表的定时发送在 `services/table_scheduler.py`。

## 测试

在插件根目录执行 Python 测试：

```sh
PYTHONPATH=.. python -m unittest discover -s tests -v
```

Windows PowerShell 中先设置 `$env:PYTHONPATH = ".."`，再运行同一条 Python 命令。

管理页和登录逻辑测试：

```sh
node --test tests/test_login.mjs tests/test_management.mjs
```

安装了 Playwright 时，还可以运行真实浏览器布局与交互检查：

```sh
node tests/test_catalog_layout.cjs
```

通过 `ANIME_BROWSER_EXECUTABLE` 指定已有的 Chromium 浏览器，通过 `ANIME_LAYOUT_OUTPUT` 设置截图和测量结果的保存位置。
