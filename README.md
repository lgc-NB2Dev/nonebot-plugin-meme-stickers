<!-- markdownlint-disable MD031 MD033 MD036 MD041 -->

<div align="center">

<a href="https://v2.nonebot.dev/store">
  <img src="https://raw.githubusercontent.com/A-kirami/nonebot-plugin-template/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo">
</a>

<p>
  <img src="https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/template/plugin.svg" alt="NoneBotPluginText">
</p>

# NoneBot-Plugin-Meme-Stickers

_✨ 一站式制作 PJSK 样式表情包 ✨_

<img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="python">
<a href="https://pdm.fming.dev">
  <img src="https://img.shields.io/badge/pdm-managed-blueviolet" alt="pdm-managed">
</a>
<a href="https://wakatime.com/badge/user/b61b0f9a-f40b-4c82-bc51-0a75c67bfccf/project/be33a081-a5da-46f6-86f2-2f2b3e3b8ba5">
  <img src="https://wakatime.com/badge/user/b61b0f9a-f40b-4c82-bc51-0a75c67bfccf/project/be33a081-a5da-46f6-86f2-2f2b3e3b8ba5.svg" alt="wakatime">
</a>

<br />

<a href="https://pydantic.dev">
  <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/template/pyd-v1-or-v2.json" alt="Pydantic Version 1 Or 2" >
</a>
<a href="./LICENSE">
  <img src="https://img.shields.io/github/license/lgc-NB2Dev/nonebot-plugin-meme-stickers.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-meme-stickers">
  <img src="https://img.shields.io/pypi/v/nonebot-plugin-meme-stickers.svg" alt="pypi">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-meme-stickers">
  <img src="https://img.shields.io/pypi/dm/nonebot-plugin-meme-stickers" alt="pypi download">
</a>

<br />

<a href="https://registry.nonebot.dev/plugin/nonebot-plugin-meme-stickers:nonebot_plugin_meme_stickers">
  <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fnbbdg.lgc2333.top%2Fplugin%2Fnonebot-plugin-meme-stickers" alt="NoneBot Registry">
</a>
<a href="https://registry.nonebot.dev/plugin/nonebot-plugin-meme-stickers:nonebot_plugin_meme_stickers">
  <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fnbbdg.lgc2333.top%2Fplugin-adapters%2Fnonebot-plugin-meme-stickers" alt="Supported Adapters">
</a>

</div>

## 📖 介绍

### 贴纸包

<details>

<summary>示例图（点击展开）</summary>

![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/QQ20250224-005554.png)  
![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/QQ20250224-005814.png)

</details>

### 生成贴纸（交互模式与短指令）

<details>

<summary>示例图（点击展开）</summary>

![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/QQ20250224-005959.png)
![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/QQ20250224-010006.png)
![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/QQ20250224-010034.png)

</details>

### 生成贴纸（命令形式）

<details>

<summary>示例图（点击展开）</summary>

![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/QQ20250224-010206.png)

</details>

### 启用、禁用贴纸包

<details>

<summary>示例图（点击展开）</summary>

![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/QQ20250224-010418.png)
![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/QQ20250224-010559.png)

</details>

## 💿 安装

以下提到的方法 任选**其一** 即可

<details open>
<summary>[推荐] 使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

```bash
nb plugin install nonebot-plugin-meme-stickers
```

</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details>
<summary>pip</summary>

```bash
pip install nonebot-plugin-meme-stickers
```

</details>
<details>
<summary>pdm</summary>

```bash
pdm add nonebot-plugin-meme-stickers
```

</details>
<details>
<summary>poetry</summary>

```bash
poetry add nonebot-plugin-meme-stickers
```

</details>
<details>
<summary>conda</summary>

```bash
conda install nonebot-plugin-meme-stickers
```

</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分的 `plugins` 项里追加写入

```toml
[tool.nonebot]
plugins = [
    # ...
    "nonebot_plugin_meme_stickers"
]
```

</details>

## ⚙️ 配置

在 nonebot2 项目的 `.env` 文件中添加下表中的必填配置

|                    配置项                    | 必填 |                                                           默认值                                                           |                                                                                            说明                                                                                             |
| :------------------------------------------: | :--: | :------------------------------------------------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------: |
|                   `PROXY`                    |  否  |                                                             无                                                             |                                                                                 插件网络请求使用的代理地址                                                                                  |
|     `MEME_STICKERS_GITHUB_URL_TEMPLATE`      |  否  | [`...`](https://github.com/lgc-NB2Dev/nonebot-plugin-meme-stickers/blob/master/nonebot_plugin_meme_stickers/config.py#L67) | 插件请求 GitHub 源时使用的链接模板，可用变量参考 [这里](https://github.com/lgc-NB2Dev/nonebot-plugin-meme-stickers/blob/master/nonebot_plugin_meme_stickers/utils/file_source.py#L115-L125) |
|         `MEME_STICKERS_RETRY_TIMES`          |  否  |                                                            `3`                                                             |                                                                                 插件每个网络请求的重试次数                                                                                  |
|       `MEME_STICKERS_REQ_CONCURRENCY`        |  否  |                                                            `8`                                                             |                                                                             插件进行批量网络请求时每批的并行数                                                                              |
|         `MEME_STICKERS_REQ_TIMEOUT`          |  否  |                                                            `5`                                                             |                                                                                   插件网络请求超时（秒）                                                                                    |
|         `MEME_STICKERS_AUTO_UPDATE`          |  否  |                                                           `True`                                                           |                                                                               是否在启动时自动更新一遍贴纸包                                                                                |
|         `MEME_STICKERS_FORCE_UPDATE`         |  否  |                                                          `False`                                                           |                                                                    在启用自动更新贴纸包时，控制自动更新是否执行强制更新                                                                     |
|        `MEME_STICKERS_PROMPT_RETRIES`        |  否  |                                                            `3`                                                             |                                                                        交互模式时输入非法后连续询问的最高次数（秒）                                                                         |
|        `MEME_STICKERS_PROMPT_TIMEOUT`        |  否  |                                                            `30`                                                            |                                                                             交互模式时每次询问的超时时间（秒）                                                                              |
|  `MEME_STICKERS_DEFAULT_STICKER_BACKGROUND`  |  否  |                                                          `FFFFFF`                                                          |                                                                           当图片格式为 `jpeg` 时，默认的背景底色                                                                            |
| `MEME_STICKERS_DEFAULT_STICKER_IMAGE_FORMAT` |  否  |                                                           `png`                                                            |                                                                                生成贴纸时默认使用的图片格式                                                                                 |

## 🎉 使用

发送 `meme-stickers` 指令获取使用帮助吧！

<details>

<summary>指令帮助（点击展开）</summary>

> [!NOTE]
> 以下内容仅供参考，实际内容请以 `meme-stickers` 输出为准

![help](https://raw.githubusercontent.com/lgc-NB2Dev/readme/main/meme-stickers/help.jpg)

</details>

## 🏆 贡献

如果你想制作自定义贴纸包，请参考 [meme-stickers-hub](https://github.com/lgc-NB2Dev/meme-stickers-hub)  
也欢迎把你的贴纸包贡献给我们~

## 📞 联系

QQ：3076823485  
Telegram：[@lgc2333](https://t.me/lgc2333)  
吹水群：[1105946125](https://jq.qq.com/?_wv=1027&k=Z3n1MpEp)  
邮箱：<lgc2333@126.com>

## 💡 鸣谢

### [MeetWq](https://github.com/MeetWq)

- 从 [pil-utils](https://github.com/MemeCrafters/pil-utils) 抄过来的 skia 文本绘制

## 💰 赞助

**[赞助我](https://blog.lgc2333.top/donate)**

感谢大家的赞助！你们的赞助将是我继续创作的动力！

## 📝 更新日志

### 0.2.6

- 将 `meme-stickers list` 命令放开给普通用户使用（使用其他选项仍需超级管理员权限）

### 0.2.5

- 修复上个版本中的潜在 bug
- 贴纸包在真正更新文件之前其仍处于可用状态

### 0.2.4

- 贴纸包的更新中状态会从开始下载文件持续到文件更新完成了，而不是仅从文件更新阶段持续到结束

### 0.2.3

- 修复一处失误造成的 Bug ([#3](https://github.com/lgc-NB2Dev/nonebot-plugin-meme-stickers/issues/3))

### 0.2.2

- 修复不兼容 Pydantic 1 的问题

### 0.2.1

- 继续刚 `localstore`

### 0.2.0

- 小幅代码重构，修复了一些潜在 Bug
- 修复贴纸包列表卡片宽度不正确的问题
- 贴纸包现在支持使用与更新不在贴纸包文件夹内的文件了，  
  此功能设计初衷是如果各贴纸包有共享资源，可以将资源放在贴纸包文件夹外，以减少重复资源占用的空间，  
  缺点是如果有被贴纸包弃用的资源不会被自动删除，
  请各位合理使用此特性

### 0.1.2

- 兼容 `localstore` 插件，当 Bot 工作目录下不存在 `data` 文件夹且 `localstore` 插件可用时使用 `localstore` 获取插件数据存储路径

### 0.1.1

- 向 `nb-cli` 添加 `stickers-gen-checksum` 脚本，用于在数据目录的所有贴纸包下生成 `checksum.json`
