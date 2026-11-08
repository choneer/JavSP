![JavSP](./image/JavSP.svg)

# Jav Scraper Package

**汇总多站点数据的AV元数据刮削器**

提取影片文件名中的番号信息，自动抓取并汇总多个站点数据的 AV 元数据，按照指定的规则分类整理影片文件，并创建供 Emby、Jellyfin、Kodi 等软件使用的元数据文件

## 本分支：Windows 本地 WebUI

此分支在上游命令行工具上增加本机浏览器界面、配置迁移和部分数据源修复；上游项目本身并不以 UI 为目标。界面监听 `127.0.0.1:8765`，支持配置预览、编辑、任务启动和日志查看。它不是远程多用户服务，请勿直接暴露到公网。整理任务可能移动视频并覆盖元数据和图片，首次使用请先用独立测试目录验证。

Windows 便携版使用及安全说明见 [Windows 使用说明](docs/WINDOWS_WEBUI.md)，已检查的数据源和限制见 [数据源检查记录](docs/SOURCE_STATUS_WINDOWS.md)。站点的可用性随网络、地区和网站验证变化；未恢复的来源不应被视为已修复。

从源码运行时使用 Python 3.10–3.12，在项目根目录安装依赖后运行：

```powershell
python -m pip install -e .
python -m javsp.server --open-browser
```

本分支新增的回归测试可用 `python -m pytest -q tests` 运行（需另外安装 pytest 和 httpx）；上游在线爬虫测试可能覆盖其测试快照，不应直接用于检查个人媒体。WebUI 运行任务时会关闭交互和自动更新检查。

旧版 INI 可通过 `python -m tools.migrate_windows <旧配置路径> <新配置路径>` 迁移；输出路径必须不存在。请核对迁移警告及命名、网络等设置，不要将个人配置、日志或密钥提交到公开仓库。

当前分支的 Windows 便携包构建工具为 `tools/build_windows_portable.py`；Docker/WebUI 部署尚未完成或验证，请勿将上游 Docker 命令当作本分支的 WebUI 部署方案。

以下为上游项目的功能说明。

**i18n**: This project currently supports only Chinese. However, if you're willing, you can [vote here](https://github.com/Yuukiy/JavSP/discussions/157) for the language you'd like to see added

![License](https://img.shields.io/github/license/Yuukiy/JavSP)
[![LICENSE](https://img.shields.io/badge/license-Anti%20996-blue.svg)](https://github.com/996icu/996.ICU/blob/master/LICENSE)
![Python 3.10](https://img.shields.io/badge/python-3.10-green.svg)
[![Crawlers test](https://img.shields.io/github/actions/workflow/status/Yuukiy/JavSP/test-web-funcs.yml?label=crawlers%20test)](https://github.com/Yuukiy/JavSP/actions/workflows/test-web-funcs.yml)
[![Latest release](https://img.shields.io/github/v/release/Yuukiy/JavSP)](https://github.com/Yuukiy/JavSP/releases/latest)
[![996.icu](https://img.shields.io/badge/link-996.icu-red.svg)](https://996.icu)
## 功能特点

下面这些是一些已实现或待实现的功能，在逐渐实现和完善，如果想到新的功能点也会加进来。

- [x] 自动识别影片番号
- [x] 支持处理影片分片
- [x] 汇总多个站点的数据生成NFO数据文件
- [x] 上游提供定期站点抓取测试（不代表本分支或各站点当前均可用）
- [x] 多线程并行抓取
- [x] 下载高清封面
- [x] 基于AI人体分析裁剪素人等非常规封面的海报
- [x] 自动检查和更新新版本
- [x] 翻译标题和剧情简介
- [ ] 匹配本地字幕
- [ ] 使用小缩略图创建文件夹封面
- [ ] 保持不同站点间 genre 分类的统一
- [ ] 不同的运行模式（抓取数据+整理，仅抓取数据）
- [ ] 可选：所有站点均抓取失败时由人工介入

## 迁移

功能修改日志：[ChangeLog](./CHANGELOG.md)

如果你之前使用的是config.ini，请重新配置JavSP，或者通过[这个脚本](./tools/config_migration.py)来将其迁移到最新的config.yml。

## [安装并运行JavSP](https://github.com/Yuukiy/JavSP/wiki/%E5%AE%89%E8%A3%85%E5%B9%B6%E8%BF%90%E8%A1%8CJavSP)

## 使用

软件开箱即用。如果想让软件更符合你的使用需求，也许你需要更改配置文件:

> 以任意文本编辑器打开 ```config.yml```，根据各个配置项的说明选择你需要的配置即可。

此外软件也支持从命令行指定运行参数（命令行参数的优先级高于配置文件）。运行 ```JavSP -h``` 查看支持的参数列表

更详细的使用说明请前往 [JavSP Wiki](https://github.com/Yuukiy/JavSP/wiki) 查看

如果使用的时候遇到问题也欢迎给我反馈😊

## 问题反馈

如果使用中遇到了 Bug，请[前往 Issue 区反馈](https://github.com/Yuukiy/JavSP/issues)（提问前请先搜索是否已有类似问题）


## 参与贡献

此项目不需要捐赠。如果你想要帮助改进这个项目，欢迎通过以下方式参与进来（并不仅局限于代码）：

- 帮助撰写和改进Wiki

- 帮助完善单元测试数据（不必非要写代码，例如如果你发现有某系列的番号识别不准确，总结一下提issue也是很好的）

- 帮助翻译 genre

- Bugfix / 新功能？欢迎发 Pull Request

- 要不考虑点个 Star ?（我会很开心的）


## 许可

此项目的所有权利与许可受 GPL-3.0 License 与 [Anti 996 License](https://github.com/996icu/996.ICU/blob/master/LICENSE_CN) 共同限制。此外，如果你使用此项目，表明你还额外接受以下条款：

- 本软件仅供学习 Python 和技术交流使用

- 请勿在微博、微信等墙内的公共社交平台上宣传此项目

- 用户在使用本软件时，请遵守当地法律法规

- 禁止将本软件用于商业用途


---

![Star History Chart](https://api.star-history.com/svg?repos=Yuukiy/JavSP&type=Date)
