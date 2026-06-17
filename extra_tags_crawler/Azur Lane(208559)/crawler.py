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
AL_ID = "208559"

# 相对工作区路径的定义
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

def process_azurlane():
    """
    爬取碧蓝航线角色及标签核心逻辑：
    1. 爬取 Bangumi 的角色列表
    2. 爬取碧蓝航线 Bwiki 的舰船定位筛选页面，提取每个舰船的类型、稀有度和阵营
    3. 将 Bangumi 角色与 Bwiki 舰船进行匹配对齐 (处理带有后缀的改型名称与中外代号名称)
    4. 复制本地已有的类型和阵营图标到输出文件夹
    5. 生成最终的 JSON 文件，并将图片引用路径更改为 /assets/extra_tags/208559/...
    """
    # 1. 爬取 Bangumi 角色数据
    bgm_characters = crawl_bangumi_characters(AL_ID)
    
    # 2. 爬取碧蓝航线 BWiki
    print("[碧蓝航线] 正在抓取碧蓝航线 Bwiki 舰船定位筛选表...")
    bwiki_url = "https://wiki.biligame.com/blhx/%E8%88%B0%E8%88%B9%E5%AE%9A%E4%BD%8D%E7%AD%9B%E9%80%89"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/blhx/"
    }
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)
    
    # 解析 Bwiki 舰船数据
    wiki_ships = {}
    for row in soup.find_all("tr", class_="divsort"):
        tds = row.find_all("td")
        if len(tds) < 2:
            continue
        name_cell = tds[1]
        name = name_cell.get_text(strip=True)
        if not name:
            continue
            
        # 拆分括号内名称以获取真正中文名 (处理诸如 "赤城(凰)" 的和谐命名情况)
        base_name = name.split("(")[0].split("（")[0].strip()
        
        # 去除改型后缀 (.改 / 改)
        clean_name = base_name
        if clean_name.endswith(".改"):
            clean_name = clean_name[:-2]
        elif clean_name.endswith("改"):
            clean_name = clean_name[:-1]
            
        # 稀有度星级映射
        # 普通 -> 1星, 稀有 -> 2星, 精锐 -> 3星, 超稀有/最高方案 -> 4星, 海上传奇/决战方案 -> 5星
        rarity_raw = row.get("data-param2", "").strip()
        rarity_star = "1星"
        if rarity_raw == "普通":
            rarity_star = "1星"
        elif rarity_raw == "稀有":
            rarity_star = "2星"
        elif rarity_raw == "精锐":
            rarity_star = "3星"
        elif rarity_raw in ("超稀有", "最高方案"):
            rarity_star = "4星"
        elif rarity_raw in ("海上传奇", "决战方案"):
            rarity_star = "5星"
            
        # 舰船类型
        hull_type = row.get("data-param1", "").split(",")[0].strip()
        
        # 阵营
        faction = row.get("data-param3", "").strip()
        
        ship_info = {
            "name": base_name,
            "rarity_star": rarity_star,
            "rarity_name": rarity_raw,
            "type": hull_type,
            "faction": faction
        }
        
        # 多改型行覆盖时，保留最高稀有度
        for key in [clean_name, base_name, name]:
            if key not in wiki_ships or int(rarity_star[0]) > int(wiki_ships[key]["rarity_star"][0]):
                wiki_ships[key] = ship_info

    print(f"[碧蓝航线] Bwiki 上抓取并记录了 {len(wiki_ships)} 个定位行数据。")

    # 3. 匹配 Bangumi ID 并生成规范的字典
    extra_tags = {}
    
    # 匹配角色并分配
    for cid, info in bgm_characters.items():
        name = info["name"]
        zh_name = info["chinese_name"]
        
        # 查找匹配的 Bwiki 舰船
        matched_ship = None
        for candidate in [zh_name, name]:
            if not candidate:
                continue
            if candidate in wiki_ships:
                matched_ship = wiki_ships[candidate]
                break
                
        # μ兵装等别名兜底匹配 (如 "赤城(μ兵装)" / "赤城(μ兵装)(凰(μ兵装))")
        if not matched_ship and zh_name:
            if "·" in zh_name: # 去除缩写符号匹配
                clean_zh = zh_name.replace("·", "")
                if clean_zh in wiki_ships:
                    matched_ship = wiki_ships[clean_zh]

        if matched_ship:
            r_star = matched_ship["rarity_star"]
            r_name = matched_ship["rarity_name"]
            h_type = matched_ship["type"]
            faction = matched_ship["faction"]
            
            # 拼装对应 HTML 标签字符串
            type_img = f"<img src='/assets/extra_tags/{AL_ID}/{h_type}.png'/>{h_type}"
            faction_img = f"<img src='/assets/extra_tags/{AL_ID}/{faction}.png'/>{faction}"
            
            extra_tags[cid] = {
                "稀有度": {r_star: r_name},
                "类型": {h_type: type_img},
                "阵营": {faction: faction_img}
            }

    # 4. 复制本地图片资产
    al_assets_dir = OUTPUT_ASSETS_DIR / AL_ID
    al_assets_dir.mkdir(parents=True, exist_ok=True)
    
    local_al_tags = GUESSER_WORKSPACE / "client" / "public" / "assets" / "tag" / "al"
    if local_al_tags.exists():
        # 复制所有 .png 图标
        for filename in os.listdir(local_al_tags):
            if filename.endswith(".png"):
                shutil.copy(local_al_tags / filename, al_assets_dir / filename)
        print("[碧蓝航线] 成功复制本地阵营与类型图标资产。")
    else:
        print("警告: 未找到本地碧蓝航线 tags 图标文件夹，跳过资产复制。")

    # 5. 生成 JSON 输出文件
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{AL_ID}.json"
    save_json_pretty(extra_tags, str(out_json_file))
    print(f"[碧蓝航线] 成功写入 {len(extra_tags)} 个角色属性到 {out_json_file}")

def main():
    print("=== 碧蓝航线 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_azurlane()
    except Exception as e:
        print(f"执行碧蓝航线爬取时发生错误: {e}")
        import traceback
        traceback.print_exc()
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
