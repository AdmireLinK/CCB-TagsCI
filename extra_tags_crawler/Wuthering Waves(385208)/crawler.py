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
MC_ID = "385208"

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

def clean_base_name(name):
    clean_n = clean_wiki_name(name)
    for sep in ["·", "•"]:
        if sep in clean_n:
            return clean_n.split(sep)[0].strip()
    return clean_n

def process_mc():
    bgm_characters = crawl_bangumi_characters(MC_ID)

    print("[鸣潮] 正在抓取鸣潮 Bwiki 共鸣者列表...")
    bwiki_url = "https://wiki.biligame.com/wutheringwaves/%E5%85%B1%E9%B8%A3%E8%80%85"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/wutheringwaves/"
    }
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)

    bwiki_forms = {}
    table = soup.find("table", class_="CardSelect")
    if not table:
        print("[鸣潮] 未找到 CardSelect 表格！")
        return

    rows = table.find_all("tr")
    for row in rows:
        attrs = {k: v for k, v in row.attrs.items() if k.startswith("data-param")}
        if not attrs or "data-param1" not in attrs:
            continue
        
        tds = row.find_all("td")
        if len(tds) < 1:
            continue
            
        anchors = tds[0].find_all("a")
        if not anchors:
            continue
        raw_name = anchors[-1].get_text(strip=True)
        form_name = raw_name
        base_name = clean_base_name(raw_name)
        
        element = attrs.get("data-param1", "").strip()
        rarity_num = attrs.get("data-param2", "").strip()
        rarity = f"{rarity_num}星" if rarity_num.isdigit() else f"{rarity_num}星"
        weapon = attrs.get("data-param3", "").strip()
        style_raw = attrs.get("data-param4", "").strip()
        styles = [s.strip() for s in style_raw.split(",") if s.strip()]

        bwiki_forms[form_name] = {
            "form_name": form_name,
            "base_name": base_name,
            "element": element,
            "rarity": rarity,
            "rarity_num": rarity_num,
            "weapon": weapon,
            "styles": styles
        }

    print(f"[鸣潮] Bwiki 上共获取了 {len(bwiki_forms)} 个形态的数据。")

    ALIAS_MAP = {
        "漂泊者·消灭": "漂泊者",
        "漂泊者·衍射": "漂泊者"
    }

    def normalize_name(n):
        if not n: return ""
        n = n.replace("•", "·").replace("·", "")
        return re.sub(r'[^\w\u4e00-\u9fa5]', '', n)

    extra_tags = {}
    mc_assets_dir = OUTPUT_ASSETS_DIR / MC_ID
    mc_assets_dir.mkdir(parents=True, exist_ok=True)

    from character_tags_crawler.utils.network import download_bwiki_missing_assets
    api_url = "https://wiki.biligame.com/wutheringwaves/api.php"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/wutheringwaves/"
    }
    
    referenced_icons = set()
    for char in bwiki_forms.values():
        r_num = char["rarity_num"]
        if r_num.isdigit():
            referenced_icons.add(f"{r_num}星.png")
        if char['element']: referenced_icons.add(f"{char['element']}.png")
        if char['weapon']: referenced_icons.add(f"{char['weapon']}.png")
                    
    missing_assets = {}
    for icon_name in referenced_icons:
        name = icon_name.rsplit(".", 1)[0]
        missing_assets[icon_name] = [
            f"File:图标-{name}.png", f"File:Logo-{name}.png",
            f"File:{name}.png", f"File:属性-{name}.png",
            f"File:武器-{name}.png", f"File:声骸-{name}.png",
            f"File:星级_{name}.png", f"File:星级-{name}.png", f"File:{name}.svg"
        ]

    download_bwiki_missing_assets(api_url, missing_assets, mc_assets_dir, headers)

    def get_rarity_html(rarity, rarity_num):
        rarity_file = f"{rarity_num}星" if rarity_num.isdigit() else rarity
        filename = f"{rarity_file}.png"
        if (mc_assets_dir / filename).exists():
            return f"<img src='/assets/extra_tags/{MC_ID}/{filename}' alt='{rarity}' />"
        return rarity

    def get_tag_html(tag_name):
        if not tag_name: return ""
        filename = f"{tag_name}.png"
        if (mc_assets_dir / filename).exists():
            return f"<img src='/assets/extra_tags/{MC_ID}/{filename}'/>{tag_name}"
        return tag_name

    # 智能拆分/合并映射
    bgm_form_mapping = {cid: [] for cid in bgm_characters}

    for form_name, form_data in bwiki_forms.items():
        base_name = form_data["base_name"]
        
        # 1. 寻求专属 Bangumi 独立条目
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
            # 2. 无专属独立条目，寻求主形态合并
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
        elements_set = {f["element"] for f in forms if f["element"]}
        rarity_num = forms[0]["rarity_num"]
        rarity = forms[0]["rarity"]
        weapons_set = {f["weapon"] for f in forms if f["weapon"]}
        styles_set = set()
        for f in forms:
            styles_set.update(f["styles"])

        rarity_html = get_rarity_html(rarity, rarity_num)
        
        tags_dict = {}
        for e in sorted(elements_set):
            tags_dict[e] = get_tag_html(e)
        for w in sorted(weapons_set):
            tags_dict[w] = get_tag_html(w)
        for st in sorted(styles_set):
            tags_dict[st] = st
            
        extra_tags[cid] = {
            "稀有度": {rarity: rarity_html},
            "标签": tags_dict
        }

    print(f"[鸣潮] 成功匹配了 {matched_count} 个 Bangumi 角色条目 (独立条目拆分/共用条目合并)。")

    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{MC_ID}.json"
    save_json_pretty(extra_tags, str(out_json_file))
    
    guesser_dest = GUESSER_WORKSPACE / "client" / "public" / "data" / "extra_tags" / f"{MC_ID}.json"
    guesser_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out_json_file, guesser_dest)
    print(f"[鸣潮] 已保存并同步 {len(extra_tags)} 个角色的 Extra Tags 至 {guesser_dest}")

def main():
    print("=== 鸣潮 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_mc()
    except Exception as e:
        print(f"执行鸣潮爬取时发生错误: {e}")
        raise
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
