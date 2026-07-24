import os
import sys
import re
import shutil
import json
from pathlib import Path

# 将项目根目录添加到 sys.path 中，以便能够导入项目中的通用模块
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from character_tags_crawler.utils.network import safe_soup
from character_tags_crawler.utils.file import save_json_pretty

# 全局配置
HSR_ID = "360097"

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
    name = re.sub(r'[\(（].*?[\)）]', '', name)
    name = name.replace("•", "·").strip()
    return name

def clean_base_name(name):
    clean_n = clean_wiki_name(name)
    for sep in ["·", "•"]:
        if sep in clean_n:
            return clean_n.split(sep)[0].strip()
    return clean_n

def process_hsr():
    bgm_characters = crawl_bangumi_characters(HSR_ID)

    print("[星穹铁道] 正在抓取星穹铁道 Bwiki 角色筛选页...")
    bwiki_url = "https://wiki.biligame.com/sr/%E8%A7%92%E8%89%B2%E7%AD%9B%E9%80%89"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/sr/"
    }
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)

    bwiki_forms = {}
    table = soup.find("table", class_="CardSelect")
    if not table:
        print("[星穹铁道] 未找到 CardSelect 表格！")
        return

    rows = table.find_all("tr")
    for row in rows:
        attrs = {k: v for k, v in row.attrs.items() if k.startswith("data-param")}
        if not attrs or "data-param1" not in attrs:
            continue
        
        tds = row.find_all("td")
        if len(tds) < 2:
            continue
            
        raw_name = tds[1].get_text(strip=True)
        name = clean_wiki_name(raw_name)
        base_name = clean_base_name(raw_name)
        
        rarity = attrs.get("data-param1", "").strip()
        path_name = attrs.get("data-param2", "").strip()
        element = attrs.get("data-param3", "").strip()
        faction = attrs.get("data-param7", "").strip()

        bwiki_forms[name] = {
            "form_name": name,
            "base_name": base_name,
            "rarity": rarity,
            "path": path_name,
            "element": element,
            "faction": faction
        }

    print(f"[星穹铁道] Bwiki 解析得到 {len(bwiki_forms)} 个特定形态。")

    # 全面别名映射关系表
    ALIAS_MAP = {
        "星": ["开拓者", "星"],
        "穹": ["开拓者", "穹"],
        "开拓者": ["星", "穹", "开拓者"],
        "大黑塔": ["「大」黑塔"]
    }

    def normalize_name(n):
        if not n: return ""
        n = n.replace("•", "·").replace("·", "")
        return re.sub(r'[^\w\u4e00-\u9fa5]', '', n)

    def name_matches(name1, name2):
        if not name1 or not name2: return False
        if name1 == name2 or normalize_name(name1) == normalize_name(name2):
            return True
        aliases1 = ALIAS_MAP.get(name1, [name1]) if isinstance(ALIAS_MAP.get(name1), list) else [ALIAS_MAP.get(name1, name1)]
        aliases2 = ALIAS_MAP.get(name2, [name2]) if isinstance(ALIAS_MAP.get(name2), list) else [ALIAS_MAP.get(name2, name2)]
        for a1 in aliases1:
            for a2 in aliases2:
                if a1 == a2 or normalize_name(a1) == normalize_name(a2):
                    return True
        return False

    # 资产检查与自动下载
    from character_tags_crawler.utils.network import download_bwiki_missing_assets
    api_url = "https://wiki.biligame.com/sr/api.php"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/sr/"
    }
    hsr_assets_dir = OUTPUT_ASSETS_DIR / HSR_ID
    hsr_assets_dir.mkdir(parents=True, exist_ok=True)
    
    referenced_icons = set()
    for char in bwiki_forms.values():
        if char["rarity"]: referenced_icons.add(f"{char['rarity']}.png")
        if char["path"]: referenced_icons.add(f"{char['path']}.png")
        if char["element"]: referenced_icons.add(f"{char['element']}.png")
        if char["faction"]: referenced_icons.add(f"{char['faction']}.png")
            
    missing_assets = {}
    for icon_name in referenced_icons:
        name = icon_name.rsplit(".", 1)[0]
        query_names = [name]
        if "星" in name:
            star_num = name.replace("星", "")
            query_names.extend([f"星级_{star_num}", f"星级-{star_num}", f"星级{star_num}", f"{star_num}星", f"{star_num}star"])
        
        candidates = []
        for qn in query_names:
            candidates.extend([
                f"File:命途_{qn}.png", f"File:命途-{qn}.png",
                f"File:属性_{qn}.png", f"File:属性-{qn}.png",
                f"File:星级_{qn}.png", f"File:星级-{qn}.png",
                f"File:图标_{qn}.png", f"File:Logo_{qn}.png",
                f"File:{qn}.png", f"File:{qn}.svg"
            ])
        missing_assets[icon_name] = candidates

    download_bwiki_missing_assets(api_url, missing_assets, hsr_assets_dir, headers)

    def get_rarity_html(r):
        if (hsr_assets_dir / f"{r}.png").exists():
            return f"<img src='/assets/extra_tags/{HSR_ID}/{r}.png' alt='{r}' />"
        elif (hsr_assets_dir / f"{r}.svg").exists():
            return f"<img src='/assets/extra_tags/{HSR_ID}/{r}.svg' alt='{r}' />"
        return r

    def get_tag_html(tag_name):
        if not tag_name: return ""
        if (hsr_assets_dir / f"{tag_name}.png").exists():
            return f"<img src='/assets/extra_tags/{HSR_ID}/{tag_name}.png'/>{tag_name}"
        elif (hsr_assets_dir / f"{tag_name}.svg").exists():
            return f"<img src='/assets/extra_tags/{HSR_ID}/{tag_name}.svg'/>{tag_name}"
        return tag_name

    # 智能分流映射 (支持星/穹以及所有异格/主形态归属)
    bgm_form_mapping = {cid: [] for cid in bgm_characters}

    for form_name, form_data in bwiki_forms.items():
        base_name = form_data["base_name"]
        
        # 1. 寻求专属 Bangumi 独立条目 (如 丹恒·饮月)
        exact_cids = []
        for cid, info in bgm_characters.items():
            cands = [info["chinese_name"], info["name"]]
            for cand in cands:
                if cand and name_matches(cand, form_name):
                    exact_cids.append(cid)
                    break
                
        if exact_cids:
            for cid in exact_cids:
                bgm_form_mapping[cid].append(form_data)
        else:
            # 2. 无专属独立条目，寻求主形态合并 (如 把 开拓者·毁灭/存护/同谐 合并写入 Bangumi 的 星(124795) 和 穹(124794))
            base_cids = []
            for cid, info in bgm_characters.items():
                cands = [info["chinese_name"], info["name"]]
                for cand in cands:
                    if cand and name_matches(cand, base_name):
                        base_cids.append(cid)
                        break
            for cid in base_cids:
                bgm_form_mapping[cid].append(form_data)

    extra_tags = {}
    matched_count = 0

    for cid, forms in bgm_form_mapping.items():
        if not forms:
            continue
            
        matched_count += 1
        rarities_set = {f["rarity"] for f in forms if f["rarity"]}
        paths_set = {f["path"] for f in forms if f["path"]}
        elements_set = {f["element"] for f in forms if f["element"]}
        factions_set = {f["faction"] for f in forms if f["faction"]}

        rarity_dict = {r: get_rarity_html(r) for r in sorted(rarities_set)}
        tags_dict = {}
        for p in sorted(paths_set):
            tags_dict[p] = get_tag_html(p)
        for e in sorted(elements_set):
            tags_dict[e] = get_tag_html(e)

        faction_dict = {f: get_tag_html(f) for f in sorted(factions_set) if f}

        extra_tags[cid] = {
            "稀有度": rarity_dict,
            "标签": tags_dict,
            "阵营": faction_dict
        }

    print(f"[星穹铁道] 成功精准匹配了 {matched_count} 个 Bangumi 角色条目 (覆盖星、穹及所有角色)。")

    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{HSR_ID}.json"
    save_json_pretty(extra_tags, str(out_json_file))
    
    guesser_dest = GUESSER_WORKSPACE / "client" / "public" / "data" / "extra_tags" / f"{HSR_ID}.json"
    guesser_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out_json_file, guesser_dest)
    print(f"[星穹铁道] 已全量刷新并同步 {len(extra_tags)} 个干净且精确的 Extra Tags 至 {guesser_dest}")

def main():
    print("=== 星穹铁道 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_hsr()
    except Exception as e:
        print(f"执行星穹铁道爬取时发生错误: {e}")
        raise
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
