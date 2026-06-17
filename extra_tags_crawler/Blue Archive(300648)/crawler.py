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

# 相对工作区路径的定义
TAGSCI_WORKSPACE = project_root
GUESSER_WORKSPACE = project_root.parent / "anime-character-guessr"

OUTPUT_JSON_DIR = TAGSCI_WORKSPACE / "outputs" / "extra_tags"
OUTPUT_ASSETS_DIR = TAGSCI_WORKSPACE / "outputs" / "assets" / "extra_tags"

# 缓存文件路径
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

def fetch_student_detail(romaji, cache):
    """
    获取学生详情页的数据，如果缓存中已存在则直接读取。
    支持优雅的抓取与错误降级处理。
    """
    if romaji in cache:
        return cache[romaji]
        
    url = f"https://wiki.biligame.com/ba/{urllib.parse.quote(romaji)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/ba/Students"
    }
    
    print(f"[碧蓝档案] 正在获取学生详情: {romaji}...")
    try:
        # 使用 0.5s 基础冷却时间，防止触发防爬机制 (567 Error)
        soup = safe_soup(url, headers=headers, cooldown=0.5)
        
        # 1. 稀有度
        star_div = soup.find(class_="romajiStar")
        stars = 3
        if star_div:
            stars_str = star_div.get_text(strip=True)
            stars = len(stars_str) if stars_str else 3
            
        # 2. 武器类型
        weapon_div = soup.find(class_="weaponType")
        weapon = weapon_div.get_text(strip=True) if weapon_div else "AR"
        
        # 3. 战场站位
        position = "中排"
        for row in soup.find_all(class_="propertyRow"):
            txt = row.get_text(strip=True)
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
        # 降级容错
        return {"stars": 3, "weapon": "AR", "position": "中排"}

def process_bluearchive():
    """
    爬取碧蓝档案角色及标签核心逻辑：
    1. 爬取 Bangumi 的角色列表
    2. 爬取碧蓝档案 Bwiki 的学生列表 JSON 接口
    3. 获取每个学生的星级、武器类型和战斗位置 (合并正月、泳装等多形态属性)
    4. 将 Bangumi 角色与 Bwiki 学生进行匹配对齐 (支持拼音代号及译名差异匹配)
    5. 复制本地已有的学校、职业、属性图标到输出文件夹
    6. 生成最终的 JSON 文件，并将图片引用路径更改为 /assets/extra_tags/300648/...
    """
    # 1. 爬取 Bangumi 角色数据
    bgm_characters = crawl_bangumi_characters(BA_ID)
    
    # 加载本地缓存
    cache = load_cache()
    
    # 2. 爬取碧蓝档案 Bwiki 学生列表 JSON
    print("[碧蓝档案] 正在抓取 Bwiki 学生列表 JSON 数据库...")
    bwiki_url = "https://wiki.biligame.com/ba/index.php?title=MediaWiki:StudentList.jp.json&action=raw"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = safe_get(bwiki_url, headers=headers, cooldown=1)
        bwiki_data = r.json()
    except Exception as e:
        print(f"错误: 无法获取 Bwiki 学生列表 JSON: {e}")
        return

    # 3. 学校、战斗职业、属性的名称映射字典
    SCHOOL_MAP = {
        "SRT": "SRT特殊学院",
        "千年": "千年科学学园",
        "圣三一": "三一综合学园",
        "山海经": "山海经高级中学",
        "格黑娜": "格黑娜学园",
        "瓦尔基里": "瓦尔基里警察学校",
        "百鬼夜行": "百鬼夜行联合学院",
        "红冬": "赤冬联邦学园",
        "阿拜多斯": "阿拜多斯高中",
        "阿里乌斯": "阿里乌斯分校",
        "海兰德": "海兰德铁道学园",
    }
    
    ROLE_MAP = {
        "支援手": "辅助",
        "攻击手": "输出",
        "坦克": "坦克",
        "治疗手": "治疗",
        "战术支援": "载具支援",
    }
    
    ATTACK_MAP = {
        "爆炸": ("爆发", "#920008"),
        "爆发": ("爆发", "#920008"),
        "贯通": ("贯通", "#BD8901"),
        "神秘": ("神秘", "#226F9B"),
        "振动": ("振动", "#794394"),
    }
    
    DEFENSE_MAP = {
        "轻装": ("轻装甲", "#920008"),
        "轻装甲": ("轻装甲", "#920008"),
        "重装": ("重装甲", "#BD8901"),
        "重装甲": ("重装甲", "#BD8901"),
        "特殊": ("特殊装甲", "#226F9B"),
        "特殊装甲": ("特殊装甲", "#226F9B"),
        "弹力": ("弹力装甲", "#794394"),
        "弹力装甲": ("弹力装甲", "#794394"),
    }
    
    # 中文姓名译名别名对照字典 (Bwiki 与 Bangumi 差异)
    ALIAS_MAP = {
        "阿露": "爱露",
        "尼禄": "妮露",
        "切里诺": "洁莉诺",
        "淳子": "纯子",
        "花绘": "花江",
        "爱莉": "爱理",
        "遥香": "春香",
        "枫香": "风香",
        "小鸟": "亚都梨",
        "朱音": "茜",
        "叶渚": "康娜",
        "佳代": "卡娅",
        "明里": "明莉",
    }

    def clean_wiki_name(name_str):
        # 移除类似 "阿露(正月)" -> "阿露" 后缀括号
        return re.sub(r'[\(（].*?[\)）]', '', name_str).strip()

    # 处理每个学生的基本数据和详情页
    wiki_students = {}
    for romaji, info in bwiki_data.items():
        raw_name = info.get("name", "")
        base_name = clean_wiki_name(raw_name)
        
        # 抓取或载入详情
        details = fetch_student_detail(romaji, cache)
        
        # 转换并规范属性
        school_name = SCHOOL_MAP.get(info.get("school"), "其它")
        role_name = ROLE_MAP.get(info.get("role"), "输出")
        squad = info.get("squad", "STRIKER")
        
        # 攻击与装甲类型
        atk_type, atk_color = ATTACK_MAP.get(info.get("attackType"), (info.get("attackType"), "#ffffff"))
        def_type, def_color = DEFENSE_MAP.get(info.get("defenseType"), (info.get("defenseType"), "#ffffff"))
        
        student_info = {
            "name": base_name,
            "stars": [details["stars"]],
            "weapon": details["weapon"],
            "school": school_name,
            "squad": squad,
            "role": role_name,
            "attackType": (atk_type, atk_color),
            "defenseType": (def_type, def_color),
            "position": details["position"]
        }
        
        # 合并不同形态学生的属性 (多版本角色星级及某些属性可能存在交集)
        if base_name not in wiki_students:
            wiki_students[base_name] = student_info
        else:
            existing = wiki_students[base_name]
            if details["stars"] not in existing["stars"]:
                existing["stars"].append(details["stars"])
            # 攻击装甲形态可能有多种
            if isinstance(existing["attackType"], list):
                if (atk_type, atk_color) not in existing["attackType"]:
                    existing["attackType"].append((atk_type, atk_color))
            elif existing["attackType"] != (atk_type, atk_color):
                existing["attackType"] = [existing["attackType"], (atk_type, atk_color)]
                
            if isinstance(existing["defenseType"], list):
                if (def_type, def_color) not in existing["defenseType"]:
                    existing["defenseType"].append((def_type, def_color))
            elif existing["defenseType"] != (def_type, def_color):
                existing["defenseType"] = [existing["defenseType"], (def_type, def_color)]

    # 保存抓取缓存以利于后续快速执行
    save_cache(cache)

    # 4. 匹配 Bangumi 角色 ID
    extra_tags = {}
    for cid, info in bgm_characters.items():
        name = info["name"]
        zh_name = info["chinese_name"]
        
        # 查找匹配的 Bwiki 学生
        matched_student = None
        for candidate in [zh_name, name]:
            if not candidate:
                continue
            
            # 直接匹配
            for wiki_name, s_info in wiki_students.items():
                if candidate.endswith(wiki_name):
                    matched_student = s_info
                    break
            if matched_student:
                break
                
            # 别名匹配
            for wiki_name, s_info in wiki_students.items():
                mapped_wiki = ALIAS_MAP.get(wiki_name, wiki_name)
                if candidate.endswith(mapped_wiki):
                    matched_student = s_info
                    break
            if matched_student:
                break

        if matched_student:
            stars = matched_student["stars"]
            weapon = matched_student["weapon"]
            school = matched_student["school"]
            squad = matched_student["squad"]
            role = matched_student["role"]
            position = matched_student["position"]
            
            # 稀有度星级标签字典
            rarity_dict = {}
            for star in sorted(stars):
                star_str = f"{star}星"
                rarity_dict[star_str] = f"<img src='/assets/extra_tags/{BA_ID}/{star_str}.png' alt='{star_str}' />"
                
            # 武器类型
            weapon_dict = {
                weapon: f"<img src='/assets/extra_tags/{BA_ID}/{weapon}.png'/>{weapon}"
            }
            
            # 标签拼装
            tags_dict = {}
            
            # 攻击与装甲着色样式
            def add_color_tag(types_data):
                if isinstance(types_data, list):
                    for t_name, t_col in types_data:
                        tags_dict[t_name] = f"<span style='color: {t_col};'>{t_name}</span>"
                else:
                    t_name, t_col = types_data
                    tags_dict[t_name] = f"<span style='color: {t_col};'>{t_name}</span>"
            
            add_color_tag(matched_student["attackType"])
            add_color_tag(matched_student["defenseType"])
            
            # Squad 战术类型
            tags_dict[squad] = f"<span style='font-style: italic; font-weight: bold;'>{squad}</span>"
            
            # 战斗职业
            tags_dict[role] = f"<img src='/assets/extra_tags/{BA_ID}/{role}.png'/>{role}"
            
            # 站位 (纯文本形式)
            tags_dict[position] = position
            
            # 学校所属
            school_dict = {}
            if school != "其它":
                school_dict[school] = f"<img src='/assets/extra_tags/{BA_ID}/{school}.png'/>{school}"
            else:
                school_dict[school] = school
                
            extra_tags[cid] = {
                "稀有度": rarity_dict,
                "武器类型": weapon_dict,
                "标签": tags_dict,
                "所属": school_dict
            }

    # 5. 复制本地图片资产
    ba_assets_dir = OUTPUT_ASSETS_DIR / BA_ID
    ba_assets_dir.mkdir(parents=True, exist_ok=True)
    
    local_ba_tags = GUESSER_WORKSPACE / "client" / "public" / "assets" / "tag" / "ba"
    if local_ba_tags.exists():
        for filename in os.listdir(local_ba_tags):
            if filename.endswith(".png"):
                shutil.copy(local_ba_tags / filename, ba_assets_dir / filename)
        print("[碧蓝档案] 成功复制本地学校与武器职业图标资产。")
    else:
        print("警告: 未找到本地碧蓝档案 tags 图标文件夹，跳过资产复制。")

    # 6. 生成 JSON 输出文件
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{BA_ID}.json"
    save_json_pretty(extra_tags, str(out_json_file))
    print(f"[碧蓝档案] 成功写入 {len(extra_tags)} 个角色属性到 {out_json_file}")

def main():
    print("=== 碧蓝档案 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_bluearchive()
    except Exception as e:
        print(f"执行碧蓝档案爬取时发生错误: {e}")
        import traceback
        traceback.print_exc()
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
