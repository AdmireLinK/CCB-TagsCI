# 世萌历年海报爬虫与数据更新工具 (ISML Poster Crawler & JSON Updater)

本工具用于从国际世萌官网（International Saimoe League）获取历年获奖得主及其以 `https://cdn.isml.app/` 开头的海报图片链接，并更新 `anime-character-guessr/server/data/character_images.json`。

## 功能说明

1. **爬虫模块 (`crawler.py`)**:
   - 爬取 `https://internationalsaimoe.moe/gallery` 页面（支持日文、简体中文、英文多语言交叉比对）。
   - 提取所有历年奖项得主（包括神圣皇冠、头环、项链、挂饰、常规赛及表演赛冠军等）及对应以 `https://cdn.isml.app/static/honor/` 开头的海报图片 URL。
   - 生成 `saimoe_posters.json` 数据文件。

2. **更新模块 (`updater.py`)**:
   - 载入 `server/data/character_images.json` 数据。
   - 移除所有以 `https://static.wikitide.net` 开头的旧版海报图片链接。
   - 利用多语言姓名规范化、繁简汉字转换及 Bangumi 别名映射 (`moegirl2bgm.json`)，将爬取的 `cdn.isml.app` 海报图片与角色进行精准匹配。
   - 将匹配成功的海报 URL 追加到角色的 `image_medium` 列表中，并保存更新后的 JSON 文件。

3. **一键运行脚本 (`main.py`)**:
   - 顺序执行爬虫与更新逻辑，输出详细的日志与统计数据。

## 文件目录说明

```
saimoe_poster_crawler/
├── crawler.py          # 爬取世萌画廊海报及得主信息
├── updater.py          # 更新 character_images.json，移除旧链接并匹配新海报
├── main.py             # 一键运行入口脚本
├── saimoe_posters.json # 爬虫提取的中间数据 (自动生成)
└── README.md           # 说明文档
```

## 使用方法

在项目根目录或 `saimoe_poster_crawler` 目录下运行：

```bash
python saimoe_poster_crawler/main.py
```

或分步运行：

```bash
# 1. 爬取海报
python saimoe_poster_crawler/crawler.py

# 2. 更新 character_images.json
python saimoe_poster_crawler/updater.py
```

## 依赖库

- Python 3.10+
- `requests`
- `beautifulsoup4`
