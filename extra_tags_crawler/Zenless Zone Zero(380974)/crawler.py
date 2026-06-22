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

def process_zzz():
    """
    绝区零 Extra Tags 自动爬取与处理核心逻辑：
    1. 爬取 Bangumi 绝区零角色列表
    2. 爬取绝区零 Bwiki 角色筛选页面数据
    3. 将 Bwiki 角色数据与 Bangumi 进行名称匹配对齐
    4. 复制本地 zzz tags 资产
    5. 生成 JSON
    """
    # 1. 爬取 Bangumi 数据
    bgm_characters = crawl_bangumi_characters(ZZZ_ID)

    # 2. 爬取 ZZZ Bwiki
    print("[绝区零] 正在抓取绝区零 Bwiki 角色筛选页...")
    bwiki_url = "https://wiki.biligame.com/zzz/%E8%A7%92%E8%89%B2%E7%AD%9B%E9%80%89"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/zzz/"
    }
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)

    # 职业属性映射
    PROFESSION_MAP = {
        "命破": "击破"  # 将 Bwiki 数据中的 "命破" 转换为本地的 "击破"
    }

    # Bwiki 数据解析
    wiki_chars = {}
    table = soup.find("table", class_="CardSelect")
    if not table:
        print("[绝区零] 未找到 CardSelect 表格！")
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
        
        # 稀有度 S/A 等
        rarity = attrs.get("data-param1", "").strip()
        # 属性 (物理, 火, 冰, 电, 以太)
        element = attrs.get("data-param4", "").strip()
        # 特性 (强攻, 击破, 异常, 支援, 防护)
        profession_raw = attrs.get("data-param5", "").strip()
        profession = PROFESSION_MAP.get(profession_raw, profession_raw)
        # 伤害类型 (斩击, 打击, 穿透)
        dmg_type = attrs.get("data-param6", "").strip()
        # 阵营
        faction = attrs.get("data-param7", "").strip()

        wiki_chars[name] = {
            "rarity": rarity,
            "element": element,
            "profession": profession,
            "dmg_type": dmg_type,
            "faction": faction
        }

    print(f"[绝区零] Bwiki 上共获取了 {len(wiki_chars)} 个角色的数据。")

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
    extra_tags = {}
    for cid, info in bgm_characters.items():
        bgm_name = info["name"]
        bgm_zh = info["chinese_name"]
        
        matched_char = None
        for candidate in [bgm_zh, bgm_name]:
            if not candidate:
                continue
            
            # 1. 精确与别名直接匹配
            if candidate in wiki_chars:
                matched_char = wiki_chars[candidate]
                break
                
            norm_candidate = normalize_name(candidate)
            # 2. 遍历 Bwiki 匹配
            for w_name, data in wiki_chars.items():
                w_name_norm = normalize_name(w_name)
                # 检查归一化后是否相等，或者子串
                if norm_candidate == w_name_norm or w_name in candidate or candidate in w_name:
                    matched_char = data
                    break
                # 3. 检查 ALIAS_MAP 翻译映射
                alias_translated = ALIAS_MAP.get(w_name, w_name)
                alias_norm = normalize_name(alias_translated)
                if norm_candidate == alias_norm or alias_translated in candidate or candidate in alias_translated:
                    matched_char = data
                    break
            
            if matched_char:
                break

        if matched_char:
            rarity = matched_char["rarity"]
            element = matched_char["element"]
            profession = matched_char["profession"]
            dmg_type = matched_char["dmg_type"]
            faction = matched_char["faction"]

            # 图像引用拼装
            rarity_html = f"<img src='/assets/extra_tags/{ZZZ_ID}/{rarity}.png' alt='{rarity}' />"
            element_html = f"<img src='/assets/extra_tags/{ZZZ_ID}/{element}.png'/>{element}"
            prof_html = f"<img src='/assets/extra_tags/{ZZZ_ID}/{profession}.png'/>{profession}"
            
            tags_dict = {
                element: element_html,
                profession: prof_html
            }
            
            # 添加伤害类型 (纯文本)
            if dmg_type:
                # 某些角色有多个伤害类型 (如 席德 有 打击, 斩击)
                for dt in [d.strip() for d in dmg_type.split(",") if d.strip()]:
                    tags_dict[dt] = dt
                    
            # 阵营
            faction_dict = {}
            if faction:
                faction_dict[faction] = f"<img src='/assets/extra_tags/{ZZZ_ID}/{faction}.png'/>{faction}"
                
            extra_tags[cid] = {
                "稀有度": {rarity: rarity_html},
                "标签": tags_dict,
                "阵营": faction_dict
            }

    # 4. 复制本地图片资产
    zzz_assets_dir = OUTPUT_ASSETS_DIR / ZZZ_ID
    zzz_assets_dir.mkdir(parents=True, exist_ok=True)
    
    local_zzz_tags = GUESSER_WORKSPACE / "client" / "public" / "assets" / "tag" / "zzz"
    if local_zzz_tags.exists():
        for filename in os.listdir(local_zzz_tags):
            if filename.endswith(".png"):
                shutil.copy(local_zzz_tags / filename, zzz_assets_dir / filename)
        print("[绝区零] 成功复制本地绝区零图标资产。")
    else:
        print("警告: 未找到本地绝区零 tags 图标文件夹，跳过资产复制。")

    # 5. 保存 JSON 输出
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{ZZZ_ID}.json"
    from character_tags_crawler.utils.file import merge_and_save_extra_tags
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
