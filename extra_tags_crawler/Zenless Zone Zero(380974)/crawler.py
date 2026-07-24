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
from character_tags_crawler.utils.file import save_json_pretty

# 全局配置
ZZZ_ID = "380974"

TAGSCI_WORKSPACE = project_root
GUESSER_WORKSPACE = project_root.parent / "anime-character-guessr"

OUTPUT_JSON_DIR = TAGSCI_WORKSPACE / "outputs" / "extra_tags"
OUTPUT_ASSETS_DIR = TAGSCI_WORKSPACE / "outputs" / "assets" / "extra_tags"

def crawl_bangumi_characters(subject_id: str):
    print(f"[{subject_id}] 正在爬取 Bangumi 角色列表...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    id_name_mapping = {}
    
    page = 1
    while True:
        url = f"https://bgm.tv/subject/{subject_id}/characters?page={page}"
        try:
            soup = safe_soup(url, headers=headers, cooldown=1.5)
        except Exception as e:
            if page == 1:
                print(f"警告: 无法获取角色子页面列表，正在尝试从主页面进行解析。错误信息: {e}")
                main_url = f"https://bgm.tv/subject/{subject_id}"
                soup = safe_soup(main_url, headers=headers, cooldown=1.5)
            else:
                break

        subtitles = soup.select("div.item h2.subtitle")
        if not subtitles:
            break

        found_in_page = 0
        for subtitle in subtitles:
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
            found_in_page += 1

        print(f"  第 {page} 页抓取到 {found_in_page} 个角色。")
        next_link = soup.select_one("a.p[href*='page=']")
        if not next_link or found_in_page == 0:
            break
        page += 1

    print(f"[{subject_id}] 在 Bangumi 上共找到了 {len(id_name_mapping)} 个角色。")
    return id_name_mapping

def clean_wiki_name(name):
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
    all_titles = []
    for titles in missing_assets.values():
        all_titles.extend(titles)
    all_titles = list(set(all_titles))
    
    resolved = resolve_image_url(all_titles, headers)
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
    bgm_characters = crawl_bangumi_characters(ZZZ_ID)

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

    PROFESSION_MAP = {}
    ALIAS_MAP = {
        "猫又": "猫宫又奈", "比利": "比利·奇德", "安比": "安比·德玛拉",
        "妮可": "妮可·德玛拉", "苍角": "苍角", "露西": "露西雅娜·德·蒙特夫",
        "派派": "派派·温贝鲁", "简": "简·杜", "塞斯": "塞斯·洛威尔",
        "凯撒": "凯撒·金", "可琳": "可琳·威克斯", "本": "本·比格",
        "珂蕾妲": "珂蕾妲·贝洛伯格", "安东": "安东·伊万诺夫", "格莉丝": "格莉丝·巴雷特",
        "艾莲": "艾莲·乔", "莱卡恩": "冯·莱卡恩"
    }

    def normalize_name(n):
        if not n: return ""
        return re.sub(r'[^\w\u4e00-\u9fa5]', '', n)

    # 1. 解析 Bwiki 所有形态
    bwiki_forms = {}
    for char_name, char_data in bwiki_data.items():
        base_name = clean_wiki_name(char_name)
        matched_char = char_data["printouts"]
        
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

        bwiki_forms[char_name] = {
            "form_name": char_name,
            "base_name": base_name,
            "rarity": rarity,
            "element": element,
            "profession": profession,
            "dmg_types": dmg_type_list,
            "faction": faction
        }

    matched_assets = {
        "rarities": {f["rarity"] for f in bwiki_forms.values() if f["rarity"]},
        "elements": {f["element"] for f in bwiki_forms.values() if f["element"]},
        "professions": {f["profession"] for f in bwiki_forms.values() if f["profession"]},
        "factions": {f["faction"] for f in bwiki_forms.values() if f["faction"]}
    }

    missing_assets = {}
    for r in matched_assets["rarities"]:
        missing_assets[f"{r}.png"] = [f"File:角色稀有度{r}.png", f"File:{r}.png"]
    for e in matched_assets["elements"]:
        missing_assets[f"{e}.png"] = [f"File:图标-{e}.png", f"File:{e}.png"]
    for p in matched_assets["professions"]:
        missing_assets[f"{p}.png"] = [f"File:图标-{p}.png", f"File:{p}.png"]
    for f in matched_assets["factions"]:
        missing_assets[f"{f}.png"] = [f"File:Logo-阵营图标-{f}.png", f"File:{f}.png"]

    download_missing_assets(missing_assets, headers)

    zzz_assets_dir = OUTPUT_ASSETS_DIR / ZZZ_ID
    def get_rarity_html(r):
        if not r: return ""
        if (zzz_assets_dir / f"{r}.png").exists():
            return f"<img src='/assets/extra_tags/{ZZZ_ID}/{r}.png' alt='{r}' />"
        return r

    def get_tag_html(tag_name):
        if not tag_name: return ""
        if (zzz_assets_dir / f"{tag_name}.png").exists():
            return f"<img src='/assets/extra_tags/{ZZZ_ID}/{tag_name}.png'/>{tag_name}"
        return tag_name

    # 智能分流逻辑：独立 Bangumi 条目拆分，非独立条目合并到主形态
    bgm_form_mapping = {cid: [] for cid in bgm_characters}

    for form_name, form_data in bwiki_forms.items():
        base_name = form_data["base_name"]
        
        # 专属独立条目比对
        exact_cid = None
        for cid, info in bgm_characters.items():
            cands = [info["chinese_name"], info["name"]]
            for cand in cands:
                if not cand: continue
                norm_cand = normalize_name(cand)
                norm_form = normalize_name(form_name)
                alias_trans = ALIAS_MAP.get(form_name)
                norm_alias = normalize_name(alias_trans) if alias_trans else ""
                
                if norm_cand == norm_form or (norm_alias and norm_cand == norm_alias):
                    exact_cid = cid
                    break
            if exact_cid:
                break
                
        if exact_cid:
            bgm_form_mapping[exact_cid].append(form_data)
        else:
            # 寻求主形态条目合并
            base_cid = None
            for cid, info in bgm_characters.items():
                cands = [info["chinese_name"], info["name"]]
                for cand in cands:
                    if not cand: continue
                    norm_cand = normalize_name(cand)
                    norm_base = normalize_name(base_name)
                    alias_base = ALIAS_MAP.get(base_name)
                    norm_alias_base = normalize_name(alias_base) if alias_base else ""
                    
                    if norm_cand == norm_base or (norm_alias_base and norm_cand == norm_alias_base):
                        base_cid = cid
                        break
                if base_cid:
                    break
            if base_cid:
                bgm_form_mapping[base_cid].append(form_data)

    extra_tags = {}
    matched_count = 0

    for cid, forms in bgm_form_mapping.items():
        if not forms:
            continue
            
        matched_count += 1
        rarities_set = {f["rarity"] for f in forms if f["rarity"]}
        elements_set = {f["element"] for f in forms if f["element"]}
        professions_set = {f["profession"] for f in forms if f["profession"]}
        factions_set = {f["faction"] for f in forms if f["faction"]}
        dmg_types_set = set()
        for f in forms:
            dmg_types_set.update(f["dmg_types"])

        rarity = sorted(rarities_set)[0] if rarities_set else ""
        rarity_html = get_rarity_html(rarity)

        tags_dict = {}
        for e in sorted(elements_set):
            tags_dict[e] = get_tag_html(e)
        for p in sorted(professions_set):
            tags_dict[p] = get_tag_html(p)
        for dt in sorted(dmg_types_set):
            tags_dict[dt] = dt

        faction_dict = {}
        for fac in sorted(factions_set):
            faction_dict[fac] = get_tag_html(fac)

        extra_tags[cid] = {
            "标签": tags_dict,
            "阵营": faction_dict
        }
        if rarity:
            extra_tags[cid]["稀有度"] = {rarity: rarity_html}

    print(f"[绝区零] 成功匹配了 {matched_count} 个 Bangumi 角色条目 (独立条目拆分/共用条目合并)。")

    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{ZZZ_ID}.json"
    save_json_pretty(extra_tags, str(out_json_file))
    
    guesser_dest = GUESSER_WORKSPACE / "client" / "public" / "data" / "extra_tags" / f"{ZZZ_ID}.json"
    guesser_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out_json_file, guesser_dest)
    print(f"[绝区零] 已保存并同步 {len(extra_tags)} 个角色的 Extra Tags 至 {guesser_dest}")

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
