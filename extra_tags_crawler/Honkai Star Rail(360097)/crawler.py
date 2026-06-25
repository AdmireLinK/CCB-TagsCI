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
    对 Bwiki 的名称进行清洗，统一圆点格式
    """
    name = re.sub(r'[\(（].*?[\)）]', '', name)
    name = name.replace("•", "·").replace("·", "·").strip()
    return name

def process_hsr():
    """
    崩坏：星穹铁道 Extra Tags 自动爬取与处理核心逻辑：
    1. 爬取 Bangumi 星穹铁道角色列表
    2. 爬取星穹铁道 Bwiki 角色筛选数据 (带有 Referer 头绕过 EdgeOne 567 拦截)
    3. 提取角色的属性、命途、星级和阵营，以“基础名字”(如 开拓者, 三月七) 进行多机体/多命途形态的属性合并
    4. 匹配对齐 Bangumi 角色并分配 tags
    5. 复制本地 hsr tags 资产
    6. 生成 JSON
    """
    # 1. 爬取 Bangumi 数据
    bgm_characters = crawl_bangumi_characters(HSR_ID)

    # 2. 爬取星穹铁道 Bwiki
    print("[星穹铁道] 正在抓取星穹铁道 Bwiki 角色筛选页...")
    bwiki_url = "https://wiki.biligame.com/sr/%E8%A7%92%E8%89%B2%E7%AD%9B%E9%80%89"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/sr/"
    }
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)

    # Bwiki 数据解析与合并
    wiki_chars = {}
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
        
        # 稀有度 (5星, 4星)
        rarity = attrs.get("data-param1", "").strip()
        # 命途 (毁灭, 巡猎, 智识, 同谐, 虚无, 存护, 丰饶, 记忆, 欢愉等)
        path_name = attrs.get("data-param2", "").strip()
        # 战斗属性 (物理, 火, 冰, 雷, 风, 量子, 虚数)
        element = attrs.get("data-param3", "").strip()
        # 阵营
        faction = attrs.get("data-param7", "").strip()

        # 提取基础名字（如 “开拓者·同谐” -> “开拓者”，“三月七·巡猎” -> “三月七”）
        base_name = name
        for sep in ["·", "•"]:
            if sep in name:
                base_name = name.split(sep)[0].strip()
                break

        # 对同一个基础角色的多版本进行属性合并
        for key in [name, base_name]:
            if key not in wiki_chars:
                wiki_chars[key] = {
                    "rarities": {rarity},
                    "paths": {path_name},
                    "elements": {element} if element else set(),
                    "factions": {faction} if faction else set()
                }
            else:
                existing = wiki_chars[key]
                existing["rarities"].add(rarity)
                existing["paths"].add(path_name)
                if element:
                    existing["elements"].add(element)
                if faction:
                    existing["factions"].add(faction)

    print(f"[星穹铁道] Bwiki 上共获取并合并了 {len(wiki_chars)} 个角色的数据。")

    # 别名映射词典
    ALIAS_MAP = {
        "三月七": "三月七",
        "开拓者": "开拓者",
        "丹恒": "丹恒",
        "饮月": "丹恒·饮月"
    }

    # 归一化名字辅助匹配
    def normalize_name(n):
        n = n.replace("•", "·").replace("·", "·")
        n = re.sub(r'[^\w\u4e00-\u9fa5]', '', n)
        return n

    # 4. 自动下载缺失的图片资产
    from character_tags_crawler.utils.network import download_bwiki_missing_assets
    api_url = "https://wiki.biligame.com/sr/api.php"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/sr/"
    }
    hsr_assets_dir = OUTPUT_ASSETS_DIR / HSR_ID
    hsr_assets_dir.mkdir(parents=True, exist_ok=True)
    
    referenced_icons = set()
    for char in wiki_chars.values():
        for r in char["rarities"]:
            referenced_icons.add(f"{r}.png")
        for p in char["paths"]:
            referenced_icons.add(f"{p}.png")
        for e in char["elements"]:
            referenced_icons.add(f"{e}.png")
        for f in char["factions"]:
            referenced_icons.add(f"{f}.png")
            
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
                f"File:命途_{qn}.png",
                f"File:命途-{qn}.png",
                f"File:属性_{qn}.png",
                f"File:属性-{qn}.png",
                f"File:星级_{qn}.png",
                f"File:星级-{qn}.png",
                f"File:图标_{qn}.png",
                f"File:Logo_{qn}.png",
                f"File:{qn}.png",
                f"File:{qn}.svg"
            ])
        missing_assets[icon_name] = candidates

    download_bwiki_missing_assets(api_url, missing_assets, hsr_assets_dir, headers)

    # Helper functions for dynamic file existence checking
    def get_rarity_html(r):
        if (hsr_assets_dir / f"{r}.png").exists():
            return f"<img src='/assets/extra_tags/{HSR_ID}/{r}.png' alt='{r}' />"
        elif (hsr_assets_dir / f"{r}.svg").exists():
            return f"<img src='/assets/extra_tags/{HSR_ID}/{r}.svg' alt='{r}' />"
        return r

    def get_tag_html(tag_name):
        if not tag_name:
            return ""
        if (hsr_assets_dir / f"{tag_name}.png").exists():
            return f"<img src='/assets/extra_tags/{HSR_ID}/{tag_name}.png'/>{tag_name}"
        elif (hsr_assets_dir / f"{tag_name}.svg").exists():
            return f"<img src='/assets/extra_tags/{HSR_ID}/{tag_name}.svg'/>{tag_name}"
        return tag_name

    # 3. 匹配 Bangumi 角色
    extra_tags = {}
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
            # 遍历 Bwiki 匹配
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
            paths = matched_char["paths"]
            elements = matched_char["elements"]
            factions = matched_char["factions"]

            # 1. 稀有度
            rarity_dict = {}
            for r in sorted(rarities):
                rarity_dict[r] = get_rarity_html(r)

            # 2. 标签：命途类型、战斗属性
            tags_dict = {}
            for p in paths:
                tags_dict[p] = get_tag_html(p)
                    
            for e in elements:
                tags_dict[e] = get_tag_html(e)

            # 3. 阵营 / 所属
            faction_dict = {}
            for f in factions:
                faction_dict[f] = get_tag_html(f)

            extra_tags[cid] = {
                "稀有度": rarity_dict,
                "标签": tags_dict,
                "阵营": faction_dict
            }

    # 5. 保存 JSON 输出
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{HSR_ID}.json"
    from character_tags_crawler.utils.file import merge_and_save_extra_tags
    merge_and_save_extra_tags(HSR_ID, extra_tags, str(out_json_file), str(GUESSER_WORKSPACE))
    print(f"[星穹铁道] 成功写入 {len(extra_tags)} 个角色属性到 {out_json_file}")

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
