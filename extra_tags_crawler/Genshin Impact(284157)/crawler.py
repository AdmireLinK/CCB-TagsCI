import os
import sys
import re
import shutil
import json
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup

# 将项目根目录添加到 sys.path 中，以便能够导入项目中的通用模块
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from character_tags_crawler.utils.network import safe_get, safe_download, safe_soup
from character_tags_crawler.utils.file import save_json_pretty

# 全局配置
GENSHIN_ID = "284157"

# 相对工作区路径的定义
TAGSCI_WORKSPACE = project_root
GUESSER_WORKSPACE = project_root.parent / "anime-character-guessr"

OUTPUT_JSON_DIR = TAGSCI_WORKSPACE / "outputs" / "extra_tags"
OUTPUT_ASSETS_DIR = TAGSCI_WORKSPACE / "outputs" / "assets" / "extra_tags"

def clean_mediawiki_url(url: str) -> str:
    """
    将 MediaWiki 缩略图 URL 转换为其高分辨率的原始图片 URL。
    
    例如缩略图 URL:
    https://patchwiki.biligame.com/images/ys/thumb/c/c6/1t9ir39whxf8j3svmde4ekbcjj45dpp.png/20px-...png
    转换为原图 URL:
    https://patchwiki.biligame.com/images/ys/c/c6/1t9ir39whxf8j3svmde4ekbcjj45dpp.png
    """
    if "/thumb/" in url:
        url = url.replace("/thumb/", "/")
        parts = url.split("/")
        # 如果最后一个部分包含尺寸前缀 (如 20px-...)，或者只是一些渲染尺寸标识后缀，我们需要去掉
        if len(parts) > 1 and ("px-" in parts[-1] or parts[-1].endswith(".png") or parts[-1].endswith(".jpg")):
            # 如果倒数第二个部分本身已经是实际的文件名(以常见图片格式结尾)，直接丢弃最后一个部分即可
            if parts[-2].lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                url = "/".join(parts[:-1])
    return url

def crawl_bangumi_characters(subject_id: str):
    """
    爬取 Bangumi 上的角色列表，返回角色 ID 与名字之间的映射关系。
    如果获取角色专属子页面失败，将尝试从主页面爬取作为后备逻辑。
    """
    print(f"[{subject_id}] 正在爬取 Bangumi 角色列表...")
    url = f"https://bgm.tv/subject/{subject_id}/characters"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        soup = safe_soup(url, headers=headers, cooldown=2)
    except Exception as e:
        print(f"警告: 无法获取角色子页面列表，正在尝试从主页面进行解析。错误信息: {e}")
        main_url = f"https://bgm.tv/subject/{subject_id}"
        soup = safe_soup(main_url, headers=headers, cooldown=2)

    id_name_mapping = {}
    for subtitle in soup.select("div.item h2.subtitle"):
        anchor = subtitle.find("a", href=re.compile(r"^/character/\d+"))
        if not anchor:
            continue

        match = re.search(r"/character/(\d+)", anchor["href"])
        if not match:
            continue

        character_id = match.group(1)
        name = anchor.get_text(strip=True)
        
        chinese_span = subtitle.find("span", class_="tip")
        chinese_name = chinese_span.get_text(strip=True) if chinese_span else ""
        
        id_name_mapping[character_id] = {
            "name": name,
            "chinese_name": chinese_name
        }
    
    print(f"[{subject_id}] 在 Bangumi 上找到了 {len(id_name_mapping)} 个角色。")
    return id_name_mapping

def process_genshin():
    """
    爬取原神角色及标签核心逻辑：
    1. 爬取 Bangumi 的角色列表
    2. 爬取原神 Bwiki 的角色筛选页面，提取每个角色的稀有度、武器、属性和所属国家
    3. 将 Bangumi 角色与 Bwiki 角色属性进行匹配对齐 (处理特例，例如旅行者、埃洛伊等)
    4. 从 Bwiki 的页面抓取对应标签 learnings 并下载保存
    5. 生成最终的 JSON 文件，并将图片引用路径更改为 /assets/extra_tags/284157/...
    """
    # 1. 爬取 Bangumi 角色数据
    bgm_characters = crawl_bangumi_characters(GENSHIN_ID)
    id_name_mapping = {cid: info["name"] for cid, info in bgm_characters.items()}
    
    # 2. 爬取原神 BWiki
    print("[原神] 正在抓取原神 Bwiki 角色筛选数据库...")
    bwiki_url = "https://wiki.biligame.com/ys/%E8%A7%92%E8%89%B2%E7%AD%9B%E9%80%89"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)
    
    # 初始化特例角色的手动映射
    mapping = {
        '空': {
            "稀有度": '5星',
            "武器类型": '单手剑',
            "属性": [],
            "所属国家": '其它'
        },
        '荧': {
            "稀有度": '5星',
            "武器类型": '单手剑',
            "属性": [],
            "所属国家": '其它'
        }
    }
    
    # 提取标签数据。通过 tr[data-param1] 选择器选中所有角色属性行
    for row in soup.select("#CardSelectTr tr[data-param1]"):
        tds = row.find_all("td")
        if len(tds) < 2:
            continue
            
        name_anchor = tds[1].find("a")
        if not name_anchor:
            continue
        name = name_anchor.get_text(strip=True)
        
        rarity = row.get("data-param1", "").strip()
        weapon = row.get("data-param2", "").strip()
        element = row.get("data-param3", "").strip()
        nation = row.get("data-param5", "").strip()

        if not name or not rarity:
            continue

        if nation == '其他':
            nation = '其它'

        # 旅行者特例处理：旅行者拥有多种属性
        if '旅行者' in name:
            if element in ('', '无', '与旅行者相同'):
                continue
            for traveler in ('空', '荧'):
                if element not in mapping[traveler]["属性"]:
                    mapping[traveler]["属性"].append(element)
            continue

        mapping[name] = {
            "稀有度": rarity,
            "武器类型": weapon,
            "属性": element,
            "所属国家": nation
        }

    # 匹配 Bangumi ID
    id_info = {}
    for cid, name in id_name_mapping.items():
        if name in mapping:
            id_info[cid] = mapping[name]
            
    # 埃洛伊的硬编码特例处理
    if '80855' in id_name_mapping and '埃洛伊' in mapping:
        id_info['80855'] = mapping['埃洛伊']

    # 3. 确定需要下载的标签图标
    tags_to_download = set()
    for info in id_info.values():
        tags_to_download.add(info["稀有度"])
        tags_to_download.add(info["武器类型"])
        if isinstance(info["属性"], list):
            tags_to_download.update(info["属性"])
        else:
            tags_to_download.add(info["属性"])
        if info["所属国家"] not in ('其它', '至冬'):
            tags_to_download.add(info["所属国家"])
            
    # 移除空值标签
    tags_to_download = {t for t in tags_to_download if t and t not in ('', '无')}

    # 扫描页面上的所有 img 标签以匹配所需的图标 URL
    image_urls = {}
    for img in soup.find_all('img'):
        src = img.get('src', '')
        alt = img.get('alt', '')
        if not src:
            continue
        decoded_src = urllib.parse.unquote(src)
        decoded_alt = urllib.parse.unquote(alt)
        
        # 匹配标签图标 (支持多模式，如 "卡牌UI-元素-火.png" 或 "蒙德.png")
        for tag in tags_to_download:
            if tag in decoded_alt or f"-{tag}." in decoded_src or f"_{tag}." in decoded_src or decoded_src.split('/')[-1].startswith(f"20px-{tag}") or decoded_src.split('/')[-1].endswith(f"-{tag}.png"):
                if tag not in image_urls:
                    image_urls[tag] = clean_mediawiki_url(src)

    # 稀有度星星需要从各自的文件描述页单独爬取 (避免抓取到小图尺寸)
    for rarity in ['4星', '5星']:
        if rarity not in image_urls:
            try:
                print(f"[原神] 正在从文件描述页获取稀有度图标: {rarity}...")
                file_url = f"https://wiki.biligame.com/ys/%E6%96%87%E4%BB%B6:{urllib.parse.quote(rarity)}.png"
                file_soup = safe_soup(file_url, headers=headers, cooldown=1)
                file_img = file_soup.find('div', id='file').find('img')
                image_urls[rarity] = clean_mediawiki_url(file_img['src'])
            except Exception as e:
                print(f"警告: 无法从文件页面获取 {rarity} 的原图 URL. 错误信息: {e}")

    # 确定输出文件夹并创建
    genshin_assets_dir = OUTPUT_ASSETS_DIR / GENSHIN_ID
    genshin_assets_dir.mkdir(parents=True, exist_ok=True)

    # 下载匹配到的图片
    for tag, img_url in image_urls.items():
        dest_path = genshin_assets_dir / f"{tag}.png"
        try:
            safe_download(img_url, str(dest_path), headers=headers, cooldown=1)
        except Exception as e:
            print(f"下载标签 {tag} 图标失败: {e}")

    # 本地兜底逻辑：若本地猜角色仓库中存在对应图标而下载失败，则复制本地资源
    local_ys_tags = GUESSER_WORKSPACE / "client" / "public" / "assets" / "tag" / "ys"
    if local_ys_tags.exists():
        for tag in tags_to_download:
            dest_path = genshin_assets_dir / f"{tag}.png"
            if not dest_path.exists():
                src_path = local_ys_tags / f"{tag}.png"
                if src_path.exists():
                    print(f"[原神] 检测到本地兜底图片，正在复制 {tag}.png")
                    shutil.copy(src_path, dest_path)

    # 4. 生成规范的 JSON 输出
    def make_tag_img(value):
        return f"<img src='/assets/extra_tags/{GENSHIN_ID}/{value}.png' alt='{value}' />"

    extra_tags = {}
    for cid, info in id_info.items():
        rarity = info['稀有度']
        weapon = info['武器类型']
        element = info['属性']
        nation = info['所属国家']

        if isinstance(element, list):
            element_dict = {e: make_tag_img(e)+e for e in element}
        else:
            element_dict = {element: make_tag_img(element)+element}

        extra_tags[cid] = {
            "_name": id_name_mapping[cid],
            "稀有度": {rarity: make_tag_img(rarity)},
            "属性": element_dict,
            "武器类型": {weapon: make_tag_img(weapon)+weapon},
            "所属": {nation: make_tag_img(nation)+nation if (nation != '其它' and nation != '至冬') else nation}
        }

    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{GENSHIN_ID}.json"
    from character_tags_crawler.utils.file import merge_and_save_extra_tags
    merge_and_save_extra_tags(GENSHIN_ID, extra_tags, str(out_json_file), str(GUESSER_WORKSPACE))
    print(f"[原神] 成功写入 {len(extra_tags)} 个角色属性到 {out_json_file}")

def main():
    print("=== 原神 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_genshin()
    except Exception as e:
        print(f"执行原神爬取时发生错误: {e}")
        raise
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
