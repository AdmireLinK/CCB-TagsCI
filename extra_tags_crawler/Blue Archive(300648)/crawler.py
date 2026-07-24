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

from character_tags_crawler.utils.network import safe_get, safe_soup
from character_tags_crawler.utils.file import save_json_pretty

# 全局配置
BA_ID = "300648"

TAGSCI_WORKSPACE = project_root
GUESSER_WORKSPACE = project_root.parent / "anime-character-guessr"

OUTPUT_JSON_DIR = TAGSCI_WORKSPACE / "outputs" / "extra_tags"
OUTPUT_ASSETS_DIR = TAGSCI_WORKSPACE / "outputs" / "assets" / "extra_tags"

CACHE_FILE = Path(__file__).resolve().parent / "crawler_cache.json"

def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"警告: 无法加载缓存文件: {e}")
    return {}

def save_cache(cache_data):
    try:
        CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[碧蓝档案] 已将 {len(cache_data)} 条页面详情写入缓存。")
    except Exception as e:
        print(f"警告: 无法保存缓存文件: {e}")

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

def fetch_student_detail(romaji, cache):
    if romaji in cache:
        return cache[romaji]
        
    url = f"https://wiki.biligame.com/ba/{urllib.parse.quote(romaji)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/ba/Students"
    }
    
    print(f"[碧蓝档案] 正在获取学生详情: {romaji}...")
    try:
        soup = safe_soup(url, headers=headers, cooldown=0.5)
        star_div = soup.find(class_="romajiStar")
        stars = 3
        if star_div:
            stars_str = star_div.get_text(strip=True)
            stars = len(stars_str) if stars_str else 3
            
        weapon_div = soup.find(class_="weaponType")
        weapon = weapon_div.get_text(strip=True).upper() if weapon_div else "AR"
        
        position = "中排"
        for row in soup.find_all(class_="propertyRow"):
            txt = row.get_text(strip=True).upper()
            if txt == "FRONT":
                position = "前排"
                break
            elif txt == "MIDDLE":
                position = "中排"
                break
            elif txt == "BACK":
                position = "后排"
                break
                
        details = {"stars": stars, "weapon": weapon, "position": position}
        cache[romaji] = details
        return details
    except Exception as e:
        print(f"警告: 无法获取学生 {romaji} 的详情页 ({e})，使用默认值降级处理")
        return {"stars": 3, "weapon": "AR", "position": "中排"}

def clean_base_name(name_str):
    return re.sub(r'[\(（].*?[\)）]', '', name_str).strip()

def process_bluearchive():
    bgm_characters = crawl_bangumi_characters(BA_ID)
    cache = load_cache()
    
    print("[碧蓝档案] 正在抓取 Bwiki 学生列表 JSON 数据库...")
    bwiki_url = "https://wiki.biligame.com/ba/index.php?title=MediaWiki:StudentList.jp.json&action=raw"
    headers = {"User-Agent": "Mozilla/5.0"}
    bwiki_cache_file = Path(__file__).resolve().parent / "student_list_cache.json"
    try:
        r = safe_get(bwiki_url, headers=headers, cooldown=1)
        bwiki_data = r.json()
        bwiki_cache_file.write_text(json.dumps(bwiki_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"警告: 无法获取 Bwiki 学生列表 JSON: {e}。将尝试从本地缓存加载...")
        if bwiki_cache_file.exists():
            try:
                bwiki_data = json.loads(bwiki_cache_file.read_text(encoding="utf-8"))
                print("[碧蓝档案] 成功从本地缓存加载 Bwiki 学生列表。")
            except Exception as ex:
                print(f"错误: 无法加载本地 Bwiki 缓存: {ex}")
                return
        else:
            print("错误: 未找到本地 Bwiki 缓存。")
            return

    SCHOOL_MAP = {
        "SRT": "SRT特殊学院", "千年": "千年科学学园", "圣三一": "三一综合学园",
        "山海经": "山海经高级中学", "格黑娜": "格黑娜学园", "瓦尔基里": "瓦尔基里警察学校",
        "百鬼夜行": "百鬼夜行联合学院", "红冬": "赤冬联邦学园", "阿拜多斯": "阿拜多斯高中",
        "阿里乌斯": "阿里乌斯分校", "海兰德": "海兰德铁道学园",
    }
    
    ROLE_MAP = {
        "支援手": "辅助", "攻击手": "输出", "坦克": "坦克",
        "治疗手": "治疗", "战术支援": "载具支援",
    }
    
    ATTACK_MAP = {
        "爆炸": ("爆发", "#920008"), "爆发": ("爆发", "#920008"),
        "贯通": ("贯通", "#BD8901"), "神秘": ("神秘", "#226F9B"), "振动": ("振动", "#794394"),
    }
    
    DEFENSE_MAP = {
        "轻装": ("轻装甲", "#920008"), "轻装甲": ("轻装甲", "#920008"),
        "重装": ("重装甲", "#BD8901"), "重装甲": ("重装甲", "#BD8901"),
        "特殊": ("特殊装甲", "#226F9B"), "特殊装甲": ("特殊装甲", "#226F9B"),
        "弹力": ("弹力装甲", "#794394"), "弹力装甲": ("弹力装甲", "#794394"),
    }
    
    ALIAS_MAP = {
        "阿露": "爱露", "尼禄": "妮露", "切里诺": "洁莉诺", "淳子": "纯子",
        "花绘": "花江", "爱莉": "爱理", "遥香": "春香", "枫香": "风香",
        "小鸟": "亚都梨", "朱音": "茜", "叶渚": "康娜", "佳代": "卡娅",
        "明里": "明莉", "阳奈": "希奈", "真纪": "真姬",
    }

    # 1. 整理 Bwiki 每种形态的数据
    bwiki_forms = {}
    for romaji, info in bwiki_data.items():
        raw_name = info.get("name", "")
        base_name = clean_base_name(raw_name)
        details = fetch_student_detail(romaji, cache)
        
        school_name = SCHOOL_MAP.get(info.get("school"), "其它")
        role_name = ROLE_MAP.get(info.get("role"), "输出")
        squad = info.get("squad", "STRIKER")
        
        atk_type, atk_color = ATTACK_MAP.get(info.get("attackType"), (info.get("attackType"), "#ffffff"))
        def_type, def_color = DEFENSE_MAP.get(info.get("defenseType"), (info.get("defenseType"), "#ffffff"))
        
        bwiki_forms[raw_name] = {
            "name": raw_name,
            "base_name": base_name,
            "stars": details["stars"],
            "weapon": details["weapon"].upper(),
            "school": school_name,
            "squad": squad,
            "role": role_name,
            "attackType": (atk_type, atk_color),
            "defenseType": (def_type, def_color),
            "position": details["position"]
        }

    save_cache(cache)

    ba_assets_dir = OUTPUT_ASSETS_DIR / BA_ID
    ba_assets_dir.mkdir(parents=True, exist_ok=True)
    
    referenced_icons = set()
    for student in bwiki_forms.values():
        referenced_icons.add(f"{student['stars']}星.png")
        referenced_icons.add(f"{student['weapon']}.png")
        referenced_icons.add(f"{student['role']}.png")
        referenced_icons.add(f"{student['school']}.png")
        referenced_icons.add(f"{student['squad']}.png")
        referenced_icons.add(f"{student['attackType'][0]}.png")
        referenced_icons.add(f"{student['defenseType'][0]}.png")
        referenced_icons.add(f"{student['position']}.png")
            
    missing_assets = {}
    for icon_name in referenced_icons:
        name = icon_name.rsplit(".", 1)[0]
        missing_assets[icon_name] = [
            f"File:图标-{name}.png", f"File:Logo-{name}.png",
            f"File:Logo-阵营图标-{name}.png", f"File:{name}.png",
            f"File:角色稀有度{name}.png", f"File:{name}级.png",
            f"File:{name}star.png", f"File:{name}星.png",
            f"File:学校-{name}.png", f"File:武器-{name}.png"
        ]
        
    from character_tags_crawler.utils.network import download_bwiki_missing_assets
    api_url = "https://wiki.biligame.com/ba/api.php"
    download_bwiki_missing_assets(api_url, missing_assets, ba_assets_dir, {"User-Agent": "Mozilla/5.0", "Referer": "https://wiki.biligame.com/ba/"})

    def get_rarity_html(star_str):
        if (ba_assets_dir / f"{star_str}.png").exists():
            return f"<img src='/assets/extra_tags/{BA_ID}/{star_str}.png' alt='{star_str}' />"
        return star_str

    def get_weapon_html(w):
        if (ba_assets_dir / f"{w}.png").exists():
            return f"<img src='/assets/extra_tags/{BA_ID}/{w}.png'/>{w}"
        return w

    def get_role_html(ro):
        if (ba_assets_dir / f"{ro}.png").exists():
            return f"<img src='/assets/extra_tags/{BA_ID}/{ro}.png'/>{ro}"
        return ro

    def get_school_html(school):
        if school == "其它": return school
        if (ba_assets_dir / f"{school}.png").exists():
            return f"<img src='/assets/extra_tags/{BA_ID}/{school}.png'/>{school}"
        return school

    # 2. 映射形态到 Bangumi 角色
    # 如果异格角色在 Bangumi 有独立条目才拆分；若无独立条目则写入主形态！
    bgm_form_mapping = {cid: [] for cid in bgm_characters}

    for form_name, form_data in bwiki_forms.items():
        base_name = form_data["base_name"]
        
        # 尝试寻找该形态在 Bangumi 上的专属独立条目
        exact_cid = None
        for cid, info in bgm_characters.items():
            cands = [info["chinese_name"], info["name"]]
            for cand in cands:
                if not cand: continue
                # 如果这个 Bangumi 角色名称包含了形态全名 (如 专属的 丹恒·饮月 或 包含括号的特定角色)
                if cand == form_name or cand.endswith(form_name):
                    exact_cid = cid
                    break
            if exact_cid:
                break
                
        if exact_cid:
            # 存在独立 Bangumi 条目：归属独立条目
            bgm_form_mapping[exact_cid].append(form_data)
        else:
            # 无独立 Bangumi 条目：归属主形态 (base_name) 条目进行合并！
            base_cid = None
            for cid, info in bgm_characters.items():
                cands = [info["chinese_name"], info["name"]]
                for cand in cands:
                    if not cand: continue
                    mapped_base = ALIAS_MAP.get(base_name, base_name)
                    if cand == base_name or cand.endswith(base_name) or cand == mapped_base or cand.endswith(mapped_base):
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
        
        # 聚合该 Bangumi ID 接收到的所有形态属性 (主形态 + 未拆分的异格形态)
        stars_set = {f["stars"] for f in forms}
        weapon_set = {f["weapon"] for f in forms}
        school_set = {f["school"] for f in forms}
        squad_set = {f["squad"] for f in forms}
        role_set = {f["role"] for f in forms}
        position_set = {f["position"] for f in forms}
        attack_types = {f["attackType"] for f in forms}
        defense_types = {f["defenseType"] for f in forms}

        rarity_dict = {f"{star}星": get_rarity_html(f"{star}星") for star in sorted(stars_set)}
        weapon_dict = {w: get_weapon_html(w) for w in sorted(weapon_set)}
        
        tags_dict = {}
        for t_name, t_col in sorted(attack_types):
            tags_dict[t_name] = f"<span style='color: {t_col};'>{t_name}</span>"
        for t_name, t_col in sorted(defense_types):
            tags_dict[t_name] = f"<span style='color: {t_col};'>{t_name}</span>"
        for sq in sorted(squad_set):
            tags_dict[sq] = f"<span style='font-style: italic; font-weight: bold;'>{sq}</span>"
        for ro in sorted(role_set):
            tags_dict[ro] = get_role_html(ro)
        for pos in sorted(position_set):
            tags_dict[pos] = pos
        
        school_dict = {}
        for sch in sorted(school_set):
            school_dict[sch] = get_school_html(sch)
            
        extra_tags[cid] = {
            "稀有度": rarity_dict,
            "武器类型": weapon_dict,
            "标签": tags_dict,
            "所属": school_dict
        }

    print(f"[碧蓝档案] 成功匹配了 {matched_count} 个 Bangumi 角色条目 (含异格自动拆分/合并处理)。")

    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{BA_ID}.json"
    save_json_pretty(extra_tags, str(out_json_file))
    
    guesser_dest = GUESSER_WORKSPACE / "client" / "public" / "data" / "extra_tags" / f"{BA_ID}.json"
    guesser_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out_json_file, guesser_dest)
    print(f"[碧蓝档案] 已保存并同步 {len(extra_tags)} 个角色的 Extra Tags 至 {guesser_dest}")

def main():
    print("=== 碧蓝档案 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_bluearchive()
    except Exception as e:
        print(f"执行碧蓝档案爬取时发生错误: {e}")
        raise
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
