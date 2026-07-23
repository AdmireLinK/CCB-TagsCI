import os
import sys
import re
import shutil
import json
import requests
from pathlib import Path

# 将项目根目录添加到 sys.path 中，以便能够导入项目中的通用模块
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from character_tags_crawler.utils.network import safe_soup, safe_download
from character_tags_crawler.utils.file import merge_and_save_extra_tags

# 全局配置
ZZZ_ID = "380974"

TAGSCI_WORKSPACE = project_root
GUESSER_WORKSPACE = project_root.parent / "anime-character-guessr"

OUTPUT_JSON_DIR = TAGSCI_WORKSPACE / "outputs" / "extra_tags"
OUTPUT_ASSETS_DIR = TAGSCI_WORKSPACE / "outputs" / "assets" / "extra_tags"

def crawl_bangumi_characters(subject_id: str):
    """
    爬取 Bangumi 上的角色列表，返回角色 ID 与名字之间的映射关系。
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

def clean_wiki_name(name):
    """
    对 Bwiki 的名称进行清洗，移除不必要的符号或括号
    """
    return re.sub(r'[\(（].*?[\)）]', '', name).strip()

def clean_title(title):
    return re.sub(r'^(File|文件|Image|图像):', '', title, flags=re.IGNORECASE).strip()

def resolve_image_url(titles, headers=None):
    if not titles:
        return {}
    url = "https://wiki.biligame.com/zzz/api.php"
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://wiki.biligame.com/zzz/"
        }
    
    from urllib3 import Retry
    from requests.adapters import HTTPAdapter
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries))
    s.mount('http://', HTTPAdapter(max_retries=retries))
    
    resolved = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i+50]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json"
        }
        try:
            r = s.get(url, params=params, headers=headers, timeout=10)
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            for pid, pinfo in pages.items():
                title = pinfo.get("title")
                ii = pinfo.get("imageinfo")
                if ii:
                    resolved[clean_title(title)] = ii[0]["url"]
        except Exception as e:
            print(f"警告: 批量查询图片 URL 失败: {e}")
    return resolved

def download_missing_assets(missing_assets, headers=None):
    if not missing_assets:
        return
        
    print(f"[绝区零] 发现 {len(missing_assets)} 个可能需要下载的素材。")
    
    # Collect all titles
    all_titles = []
    for titles in missing_assets.values():
        all_titles.extend(titles)
    all_titles = list(set(all_titles))
    
    # Resolve URLs
    resolved = resolve_image_url(all_titles, headers)
    
    # Download
    zzz_assets_dir = OUTPUT_ASSETS_DIR / ZZZ_ID
    zzz_assets_dir.mkdir(parents=True, exist_ok=True)
    
    for filename, titles in missing_assets.items():
        dest_path = zzz_assets_dir / filename
        if dest_path.exists():
            continue
            
        downloaded = False
        for title in titles:
            img_url = resolved.get(clean_title(title))
            if img_url:
                try:
                    print(f"[绝区零] 正在下载 {filename} (自 {title})...")
                    safe_download(img_url, str(dest_path), headers=headers, cooldown=0.5, verbose=True)
                    downloaded = True
                    break
                except Exception as e:
                    print(f"警告: 从 {title} 下载 {filename} 失败: {e}")
        if not downloaded:
            print(f"错误: 无法下载 {filename} (尝试过的标题: {titles})")

def process_zzz():
    # 1. 爬取 Bangumi 数据
    bgm_characters = crawl_bangumi_characters(ZZZ_ID)

    # 2. 从 Bwiki API 获取角色数据 (使用 SMW ask)
    print("[绝区零] 正在通过 Bwiki API 获取角色数据...")
    url_bwiki = "https://wiki.biligame.com/zzz/api.php"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/zzz/"
    }
    params_ask = {
        "action": "ask",
        "query": "[[Category:角色]]|?稀有度|?属性|?特性|?阵营|?伤害类型|limit=100",
        "format": "json"
    }
    
    # Setup retry session for SMW ask
    from urllib3 import Retry
    from requests.adapters import HTTPAdapter
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retries))
    s.mount('http://', HTTPAdapter(max_retries=retries))
    
    try:
        r = s.get(url_bwiki, params=params_ask, headers=headers, timeout=10)
        bwiki_data = r.json().get("query", {}).get("results", {})
    except Exception as e:
        print(f"错误: 无法从 Bwiki API 获取数据: {e}")
        return

    print(f"[绝区零] Bwiki 上共获取了 {len(bwiki_data)} 个角色的数据。")

    # 职业属性映射
    PROFESSION_MAP = {}

    # 别名映射词典
    ALIAS_MAP = {
        "猫又": "猫宫又奈",
        "比利": "比利·奇德",
        "安比": "安比·德玛拉",
        "妮可": "妮可·德玛拉",
        "苍角": "苍角",
        "露西": "露西雅娜·德·蒙特夫",
        "派派": "派派·温贝鲁",
        "简": "简·杜",
        "塞斯": "塞斯·洛威尔",
        "凯撒": "凯撒·金",
        "可琳": "可琳·威克斯",
        "本": "本·比格",
        "珂蕾妲": "珂蕾妲·贝洛伯格",
        "安东": "安东·伊万诺夫",
        "格莉丝": "格莉丝·巴雷特",
        "艾莲": "艾莲·乔",
        "莱卡恩": "冯·莱卡恩"
    }

    # 归一化名字辅助匹配
    def normalize_name(n):
        n = re.sub(r'[^\w\u4e00-\u9fa5]', '', n)
        return n

    # 3. 匹配 Bangumi 角色
    matched_assets = {
        "rarities": set(),
        "elements": set(),
        "professions": set(),
        "factions": set()
    }
    for char_name, char_data in bwiki_data.items():
        matched_char = char_data["printouts"]
        rarities_raw = matched_char.get("稀有度", [])
        if rarities_raw:
            matched_assets["rarities"].add(rarities_raw[0])
        elements_raw = matched_char.get("属性", [])
        if elements_raw:
            matched_assets["elements"].add(elements_raw[0])
        professions_raw = matched_char.get("特性", [])
        if professions_raw:
            p_raw = professions_raw[0]
            matched_assets["professions"].add(PROFESSION_MAP.get(p_raw, p_raw))
        factions_raw = matched_char.get("阵营", [])
        if factions_raw:
            matched_assets["factions"].add(factions_raw[0])

    # 4. 自动下载缺失的图片资产
    missing_assets = {}
    for r in matched_assets["rarities"]:
        filename = f"{r}.png"
        missing_assets[filename] = [f"File:角色稀有度{r}.png", f"File:{r}.png"]
    for e in matched_assets["elements"]:
        filename = f"{e}.png"
        missing_assets[filename] = [f"File:图标-{e}.png", f"File:{e}.png"]
    for p in matched_assets["professions"]:
        filename = f"{p}.png"
        missing_assets[filename] = [f"File:图标-{p}.png", f"File:{p}.png"]
    for f in matched_assets["factions"]:
        filename = f"{f}.png"
        missing_assets[filename] = [f"File:Logo-阵营图标-{f}.png", f"File:{f}.png"]

    download_missing_assets(missing_assets, headers)

    # Helper functions for dynamic file existence checking
    zzz_assets_dir = OUTPUT_ASSETS_DIR / ZZZ_ID
    def get_rarity_html(r):
        if not r:
            return ""
        if (zzz_assets_dir / f"{r}.png").exists():
            return f"<img src='/assets/extra_tags/{ZZZ_ID}/{r}.png' alt='{r}' />"
        return r

    def get_tag_html(tag_name):
        if not tag_name:
            return ""
        if (zzz_assets_dir / f"{tag_name}.png").exists():
            return f"<img src='/assets/extra_tags/{ZZZ_ID}/{tag_name}.png'/>{tag_name}"
        return tag_name

    extra_tags = {}
    for cid, info in bgm_characters.items():
        bgm_name = info["name"]
        bgm_zh = info["chinese_name"]
        
        matched_char = None
        for candidate in [bgm_zh, bgm_name]:
            if not candidate:
                continue
            
            # 1. 精确与别名直接匹配
            if candidate in bwiki_data:
                matched_char = bwiki_data[candidate]["printouts"]
                break
                
            norm_candidate = normalize_name(candidate)
            # 2. 遍历 Bwiki 匹配
            for w_name, data in bwiki_data.items():
                w_name_norm = normalize_name(w_name)
                if norm_candidate == w_name_norm or w_name in candidate or candidate in w_name:
                    matched_char = data["printouts"]
                    break
                
                alias_translated = ALIAS_MAP.get(w_name, w_name)
                alias_norm = normalize_name(alias_translated)
                if norm_candidate == alias_norm or alias_translated in candidate or candidate in alias_translated:
                    matched_char = data["printouts"]
                    break
            
            if matched_char:
                break

        if matched_char:
            rarities_raw = matched_char.get("稀有度", [])
            rarity = rarities_raw[0] if rarities_raw else ""
            
            elements_raw = matched_char.get("属性", [])
            element = elements_raw[0] if elements_raw else ""
            
            professions_raw = matched_char.get("特性", [])
            profession_raw = professions_raw[0] if professions_raw else ""
            profession = PROFESSION_MAP.get(profession_raw, profession_raw)
            
            dmg_type_list = matched_char.get("伤害类型", [])
            
            factions_raw = matched_char.get("阵营", [])
            faction = factions_raw[0] if factions_raw else ""

            # 图像引用拼装
            rarity_html = get_rarity_html(rarity)
            element_html = get_tag_html(element)
            prof_html = get_tag_html(profession)
            
            tags_dict = {}
            if element:
                tags_dict[element] = element_html
            if profession:
                tags_dict[profession] = prof_html
            
            # 添加伤害类型 (纯文本)
            if dmg_type_list:
                for dt in dmg_type_list:
                    tags_dict[dt] = dt
                    
            # 阵营
            faction_dict = {}
            if faction:
                faction_dict[faction] = get_tag_html(faction)
                
            extra_tags[cid] = {
                "标签": tags_dict,
                "阵营": faction_dict
            }
            if rarity:
                extra_tags[cid]["稀有度"] = {rarity: rarity_html}

    # 5. 保存 JSON 输出
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{ZZZ_ID}.json"
    merge_and_save_extra_tags(ZZZ_ID, extra_tags, str(out_json_file), str(GUESSER_WORKSPACE))
    print(f"[绝区零] 成功写入 {len(extra_tags)} 个角色属性到 {out_json_file}")

def main():
    print("=== 绝区零 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_zzz()
    except Exception as e:
        print(f"执行绝区零爬取时发生错误: {e}")
        raise
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
