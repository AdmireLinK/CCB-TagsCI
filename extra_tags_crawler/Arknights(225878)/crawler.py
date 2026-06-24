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

from character_tags_crawler.utils.network import safe_soup
from character_tags_crawler.utils.file import save_json_pretty

# 全局配置
ARKNIGHTS_ID = "225878"

# 相对工作区路径 of defined workspaces
TAGSCI_WORKSPACE = project_root
GUESSER_WORKSPACE = project_root.parent / "anime-character-guessr"

OUTPUT_JSON_DIR = TAGSCI_WORKSPACE / "outputs" / "extra_tags"
OUTPUT_ASSETS_DIR = TAGSCI_WORKSPACE / "outputs" / "assets" / "extra_tags"

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

def process_arknights():
    """
    爬取明日方舟角色及标签核心逻辑：
    1. 爬取 Bangumi 的角色列表
    2. 爬取明日方舟 Bwiki 的干员数据表，提取每个干员的稀有度、职业、标签、阵营和感染状态
    3. 将 Bangumi 角色与 Bwiki 干员属性进行匹配对齐 (处理多职业形态的阿米娅，合并其属性)
    4. 复制本地已有的稀有度星星和职业图标到输出文件夹
    5. 生成最终的 JSON 文件，并将图片引用路径更改为 /assets/extra_tags/225878/...
    """
    # 1. 爬取 Bangumi 角色数据
    bgm_characters = crawl_bangumi_characters(ARKNIGHTS_ID)
    
    # 2. 爬取明日方舟 BWiki
    print("[明日方舟] 正在抓取明日方舟 Bwiki 干员数据表...")
    bwiki_url = "https://wiki.biligame.com/arknights/%E5%B9%B2%E5%91%98%E6%95%B0%E6%8D%AE%E8%A1%A8"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/arknights/"
    }
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)
    
    # 解析 Bwiki 干员数据
    wiki_ops = {}
    for row in soup.find_all("tr", class_="divsort"):
        name_cell = row.find("td")
        if not name_cell:
            continue
        op_name = name_cell.get_text(strip=True)
        if not op_name:
            continue
            
        # 稀有度星级 (如 "5")
        rarity_str = row.get("data-param2", "").split(",")[0].strip()
        if not rarity_str.isdigit():
            continue
        rarity = f"{rarity_str}星"
        
        # 职业 (如 "术师")
        occupation = row.get("data-param1", "").strip()
        
        # 标签 (如 "远程位, 输出, 支援")
        tags_raw = row.get("data-param5", "").split(",")
        tags = [t.strip() for t in tags_raw if t.strip()]
        
        # 阵营 (如 "罗德岛")
        factions_raw = row.get("data-param4", "").split(",")
        factions = [f.strip() for f in factions_raw if f.strip()]
        
        # 是否感染 (如 "是" / "否")
        infected = row.get("data-param7", "").strip()
        
        # 保存或合并数据 (阿米娅有多个职业形态行)
        if op_name not in wiki_ops:
            wiki_ops[op_name] = {
                "稀有度": rarity,
                "职业": [occupation],
                "标签": set(tags),
                "阵营": set(factions),
                "是否感染": infected
            }
        else:
            # 合并阿米娅的不同形态属性
            if occupation not in wiki_ops[op_name]["职业"]:
                wiki_ops[op_name]["职业"].append(occupation)
            wiki_ops[op_name]["标签"].update(tags)
            wiki_ops[op_name]["阵营"].update(factions)
            if infected == "是":
                wiki_ops[op_name]["是否感染"] = "是"

    print(f"[明日方舟] Bwiki 上抓取并合并了 {len(wiki_ops)} 个干员的数据。")

    # 3. 匹配 Bangumi ID 并生成规范的字典
    extra_tags = {}
    
    # 匹配角色并分配
    for cid, info in bgm_characters.items():
        name = info["name"]
        zh_name = info["chinese_name"]
        
        # 查找匹配的 Bwiki 干员
        matched_op = None
        for candidate in [name, zh_name]:
            if not candidate:
                continue
            if candidate in wiki_ops:
                matched_op = wiki_ops[candidate]
                break
                
        # 协作活动干员兜底映射 (如 霜华、战车、闪击)
        if not matched_op:
            if name == "Frost" and "霜华" in wiki_ops:
                matched_op = wiki_ops["霜华"]
            elif name == "Tachanka" and "战车" in wiki_ops:
                matched_op = wiki_ops["战车"]
            elif name == "Blitz" and "闪击" in wiki_ops:
                matched_op = wiki_ops["闪击"]
            elif name == "Ash" and "灰烬" in wiki_ops:
                matched_op = wiki_ops["灰烬"]

        if matched_op:
            rarity = matched_op["稀有度"]
            rarity_num = rarity.replace("星", "")
            rarity_img = f"<img src='/assets/extra_tags/{ARKNIGHTS_ID}/{rarity_num}star.png' alt='{rarity}' />"
            
            occs_dict = {}
            for occ in matched_op["职业"]:
                occs_dict[occ] = f"<img src='/assets/extra_tags/{ARKNIGHTS_ID}/{occ}.png' alt='{occ}' /> {occ}"
                
            tags_dict = {t: t for t in matched_op["标签"]}
            factions_dict = {f: f for f in matched_op["阵营"]}
            infected_dict = {matched_op["是否感染"]: matched_op["是否感染"]}
            
            extra_tags[cid] = {
                "_name": name,
                "稀有度": {rarity: rarity_img},
                "职业": occs_dict,
                "标签": tags_dict,
                "阵营": factions_dict,
                "是否感染": infected_dict
            }

    # 4. 自动下载缺失的图片资产
    from character_tags_crawler.utils.network import download_bwiki_missing_assets
    api_url = "https://wiki.biligame.com/arknights/api.php"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/arknights/"
    }
    arknights_assets_dir = OUTPUT_ASSETS_DIR / ARKNIGHTS_ID
    
    referenced_stars = set()
    referenced_professions = set()
    referenced_factions = set()
    for char in extra_tags.values():
        for r in char.get("稀有度", {}).keys():
            star_num = re.sub(r'\D', '', r)
            if star_num:
                referenced_stars.add(f"{star_num}star.png")
        for o in char.get("职业", {}).keys():
            referenced_professions.add(f"{o}.png")
        for f in char.get("阵营", {}).keys():
            referenced_factions.add(f"{f}.png")
            
    # 4.1 下载星级与职业图标 (自 Bwiki)
    missing_bwiki = {}
    for icon_name in referenced_stars | referenced_professions:
        name = icon_name.rsplit(".", 1)[0]
        query_names = [name]
        if name.endswith("star"):
            star_num = name[:-4]
            query_names.extend([f"Akn星级{star_num}", f"明日方舟星级{star_num}", f"{star_num}星", f"星级-{star_num}", f"{star_num}star"])
        
        candidates = []
        for qn in query_names:
            candidates.extend([
                f"File:图标-{qn}.png",
                f"File:Logo-{qn}.png",
                f"File:{qn}.png",
                f"File:{qn}star.png",
                f"File:{qn}星.png",
                f"File:职业-{qn}.png"
            ])
        missing_bwiki[icon_name] = candidates
        
    download_bwiki_missing_assets(api_url, missing_bwiki, arknights_assets_dir, headers)

    # 4.2 下载阵营图标 (自 PRTS Wiki)
    prts_api_url = "https://prts.wiki/api.php"
    prts_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://prts.wiki/"
    }
    
    missing_prts = {}
    for icon_name in referenced_factions:
        name = icon_name.rsplit(".", 1)[0]
        candidates = [
            f"File:Logo_{name}.png",
            f"File:Logo_{name}.PNG",
            f"File:{name}.png",
            f"File:{name}.PNG"
        ]
        missing_prts[icon_name] = candidates
        
    download_bwiki_missing_assets(prts_api_url, missing_prts, arknights_assets_dir, prts_headers)

    # 5. 生成 JSON 输出文件
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{ARKNIGHTS_ID}.json"
    from character_tags_crawler.utils.file import merge_and_save_extra_tags
    merge_and_save_extra_tags(ARKNIGHTS_ID, extra_tags, str(out_json_file), str(GUESSER_WORKSPACE))
    print(f"[明日方舟] 成功写入 {len(extra_tags)} 个角色属性到 {out_json_file}")

def main():
    print("=== 明日方舟 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_arknights()
    except Exception as e:
        print(f"执行明日方舟爬取时发生错误: {e}")
        raise
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
