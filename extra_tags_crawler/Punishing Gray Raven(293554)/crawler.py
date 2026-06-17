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
PNS_ID = "293554"

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

def process_pns():
    """
    战双帕弥什 Extra Tags 自动爬取与处理核心逻辑：
    1. 爬取 Bangumi 战双角色列表
    2. 爬取战双 Bwiki 机体图鉴页面 (使用 Referer 绕过 EdgeOne 567 拦截)
    3. 提取机体的属性、武器、品质、类型，并以“基础名字”(如 露西亚) 进行多机体形态的属性合并
    4. 匹配对齐 Bangumi 角色并分配 tags
    5. 复制本地 pns tags 资产
    6. 生成 JSON
    """
    # 1. 爬取 Bangumi 数据
    bgm_characters = crawl_bangumi_characters(PNS_ID)

    # 2. 爬取战双 Bwiki
    print("[战双帕弥什] 正在抓取战双 Bwiki 机体图鉴...")
    bwiki_url = "https://wiki.biligame.com/zspms/%E6%9C%BA%E4%BD%93%E5%9B%BE%E9%89%B4"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/zspms/"
    }
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)

    # 属性映射
    PROFESSION_MAP = {
        "破甲型": "装甲型"  # Bwiki 中可能写作 "破甲型"，对应本地的 "装甲型"
    }

    # Bwiki 数据解析与合并
    wiki_chars = {}
    table = soup.find("table", class_="CardSelect")
    if not table:
        print("[战双帕弥什] 未找到 CardSelect 表格！")
        return

    rows = table.find_all("tr")
    for row in rows:
        attrs = {k: v for k, v in row.attrs.items() if k.startswith("data-param")}
        if not attrs or "data-param1" not in attrs:
            continue
        
        tds = row.find_all("td")
        if len(tds) < 1:
            continue
            
        # 提取名字
        anchors = tds[0].find_all("a")
        if not anchors:
            continue
        raw_name = anchors[-1].get_text(strip=True)
        name = clean_wiki_name(raw_name)
        
        # 初始品质 (S, A, B)
        rarity = attrs.get("data-param2", "").strip()
        # 机体类型/职业 (进攻型, 装甲型, 辅助型, 增幅型, 先锋型, 观测者, 湮灭型)
        prof_raw = attrs.get("data-param3", "").strip()
        profession = PROFESSION_MAP.get(prof_raw, prof_raw)
        # 武器
        weapon = attrs.get("data-param4", "").strip()
        # 元素能量 (物理, 火, 冰, 雷, 暗, 空)
        element = attrs.get("data-param5", "").strip()
        # 团队阵营
        faction = attrs.get("data-param6", "").strip()
        # 效应/标签 (焚烧, 电束, 紊乱, 真意斩, 黯衍, 覆冰等)
        tags_raw = attrs.get("data-param8", "").strip()
        effect_tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        # 提取基础角色名字（例如 “露西亚·逆冕” -> “露西亚”）
        parts = name.split("·")
        base_name = parts[0].strip()

        # 对同一个基础角色的多版本进行属性合并
        if base_name not in wiki_chars:
            wiki_chars[base_name] = {
                "rarities": {rarity},
                "professions": {profession},
                "weapons": {weapon} if weapon else set(),
                "elements": {element} if element else set(),
                "factions": {faction} if faction else set(),
                "effect_tags": set(effect_tags)
            }
        else:
            existing = wiki_chars[base_name]
            existing["rarities"].add(rarity)
            existing["professions"].add(profession)
            if weapon:
                existing["weapons"].add(weapon)
            if element:
                existing["elements"].add(element)
            if faction:
                existing["factions"].add(faction)
            existing["effect_tags"].update(effect_tags)

    print(f"[战双帕弥什] Bwiki 上共获取并合并了 {len(wiki_chars)} 个角色的数据。")

    # 别名映射词典
    ALIAS_MAP = {
        "2B": "YoRHa 2B",
        "9S": "YoRHa 9S",
        "A2": "YoRHa A2"
    }

    # 归一化名字辅助匹配
    def normalize_name(n):
        n = re.sub(r'[^\w\u4e00-\u9fa5]', '', n)
        return n

    # 3. 匹配 Bangumi 角色
    extra_tags = {}
    pns_assets_dir = OUTPUT_ASSETS_DIR / PNS_ID
    pns_assets_dir.mkdir(parents=True, exist_ok=True)
    
    local_pns_tags = GUESSER_WORKSPACE / "client" / "public" / "assets" / "tag" / "pns"
    available_icons = set()
    if pns_assets_dir.exists() and any(pns_assets_dir.glob("*.png")):
        available_icons = {f.name.rsplit(".", 1)[0] for f in pns_assets_dir.glob("*.png")}
    elif local_pns_tags.exists():
        available_icons = {f.rsplit(".", 1)[0] for f in os.listdir(local_pns_tags) if f.endswith(".png")}

    for cid, info in bgm_characters.items():
        bgm_name = info["name"]
        bgm_zh = info["chinese_name"]
        
        matched_char = None
        for candidate in [bgm_zh, bgm_name]:
            if not candidate:
                continue
            
            # 直接匹配
            if candidate in wiki_chars:
                matched_char = wiki_chars[candidate]
                break
                
            norm_candidate = normalize_name(candidate)
            # 遍历 Bwiki
            for w_name, data in wiki_chars.items():
                w_name_norm = normalize_name(w_name)
                # 检查归一化后是否相等，或者子串
                if norm_candidate == w_name_norm or w_name in candidate or candidate in w_name:
                    matched_char = data
                    break
                # 别名映射
                alias_translated = ALIAS_MAP.get(w_name, w_name)
                alias_norm = normalize_name(alias_translated)
                if norm_candidate == alias_norm or alias_translated in candidate or candidate in alias_translated:
                    matched_char = data
                    break
            
            if matched_char:
                break

        if matched_char:
            rarities = matched_char["rarities"]
            professions = matched_char["professions"]
            weapons = matched_char["weapons"]
            elements = matched_char["elements"]
            factions = matched_char["factions"]
            effect_tags = matched_char["effect_tags"]

            # 1. 稀有度
            rarity_dict = {}
            for r in sorted(rarities):
                if r in available_icons:
                    rarity_dict[r] = f"<img src='/assets/extra_tags/{PNS_ID}/{r}.png' alt='{r}' />"
                else:
                    rarity_dict[r] = r

            # 2. 标签：机体类型、能量参数、效应标签
            tags_dict = {}
            for p in professions:
                if p in available_icons:
                    tags_dict[p] = f"<img src='/assets/extra_tags/{PNS_ID}/{p}.png'/>{p}"
                else:
                    tags_dict[p] = p
                    
            for e in elements:
                if e in available_icons:
                    tags_dict[e] = f"<img src='/assets/extra_tags/{PNS_ID}/{e}.png'/>{e}"
                else:
                    tags_dict[e] = e
                    
            for t in effect_tags:
                if t in available_icons:
                    tags_dict[t] = f"<img src='/assets/extra_tags/{PNS_ID}/{t}.png'/>{t}"
                else:
                    tags_dict[t] = t

            # 3. 武器
            weapon_dict = {}
            for w in weapons:
                # 武器种类很多，有图标的用图标，无图标的用纯文本
                if w in available_icons:
                    weapon_dict[w] = f"<img src='/assets/extra_tags/{PNS_ID}/{w}.png'/>{w}"
                else:
                    weapon_dict[w] = w

            # 4. 所属/阵营
            faction_dict = {}
            for f in factions:
                if f in available_icons:
                    faction_dict[f] = f"<img src='/assets/extra_tags/{PNS_ID}/{f}.png'/>{f}"
                else:
                    faction_dict[f] = f

            extra_tags[cid] = {
                "稀有度": rarity_dict,
                "武器类型": weapon_dict,
                "标签": tags_dict,
                "阵营": faction_dict
            }

    # 4. 复制本地图片资产
    if local_pns_tags.exists():
        for filename in os.listdir(local_pns_tags):
            if filename.endswith(".png"):
                shutil.copy(local_pns_tags / filename, pns_assets_dir / filename)
        print("[战双帕弥什] 成功复制本地战双图标资产。")
    else:
        print("警告: 未找到本地战双 tags 图标文件夹，跳过资产复制。")

    # 5. 保存 JSON 输出
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{PNS_ID}.json"
    save_json_pretty(extra_tags, str(out_json_file))
    print(f"[战双帕弥什] 成功写入 {len(extra_tags)} 个角色属性到 {out_json_file}")

def main():
    print("=== 战双帕弥什 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_pns()
    except Exception as e:
        print(f"执行战双爬取时发生错误: {e}")
        import traceback
        traceback.print_exc()
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
