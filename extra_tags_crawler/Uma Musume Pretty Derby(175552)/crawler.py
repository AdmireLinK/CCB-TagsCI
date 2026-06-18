import os
import sys
import re
import shutil
import json
from pathlib import Path
from bs4 import BeautifulSoup

# 将项目根目录添加到 sys.path 中，以便能够导入项目中的通用模块
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from character_tags_crawler.utils.network import safe_get, safe_soup
from character_tags_crawler.utils.file import save_json_pretty

# 全局配置
UMAMUSUME_ID = "175552"

# 相对工作区路径的定义
TAGSCI_WORKSPACE = project_root
GUESSER_WORKSPACE = project_root.parent / "anime-character-guessr"

OUTPUT_JSON_DIR = TAGSCI_WORKSPACE / "outputs" / "extra_tags"
OUTPUT_ASSETS_DIR = TAGSCI_WORKSPACE / "outputs" / "assets" / "extra_tags"

def crawl_bangumi_characters(subject_id: str):
    """
    爬取 Bangumi 上的角色列表，返回角色 ID 与中日文名字之间的映射关系。
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

def process_umamusume():
    """
    爬取赛马娘角色及标签核心逻辑：
    1. 爬取 Bangumi 的角色列表并记录中日双语映射。
    2. 爬取赛马娘 Bwiki 的图鉴页面，提取每个角色的草地/泥地适应性、距离适应性、跑法适应性与稀有度。
    3. 将 Bangumi 角色与 Bwiki 角色进行匹配。
    4. 复制本地已有的稀有度组合图标（1star.png, 2star.png, 3star.png）到输出文件夹。
    5. 生成最终的 JSON 文件，并将图片引用路径更改为 /assets/extra_tags/175552/...
    """
    # 1. 爬取 Bangumi 角色数据
    bgm_characters = crawl_bangumi_characters(UMAMUSUME_ID)
    id_name_mapping = {
        cid: {
            "ja": info["name"],
            "zh": info["chinese_name"]
        }
        for cid, info in bgm_characters.items()
    }
    
    # 2. 爬取赛马娘 BWiki 页面
    print("[赛马娘] 正在抓取赛马娘 Bwiki 角色数据库...")
    bwiki_url = "https://wiki.biligame.com/umamusume/%E8%B5%9B%E9%A9%AC%E5%A8%98%E5%9B%BE%E9%89%B4"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)
    
    columns = [
        "稀有度",
        "草地",
        "泥地",
        "短距离",
        "英里",
        "中距离",
        "长距离",
        "领跑",
        "跟前",
        "居中",
        "后追",
    ]
    
    # 构建日文名到 Bangumi ID 的映射，便于匹配
    ja_to_ids = {}
    for cid, names in id_name_mapping.items():
        ja_to_ids.setdefault(names["ja"], []).append(cid)

    def make_stat_dict():
        return {column: [] for column in columns}

    character_stats = {}
    grade_letter_pattern = re.compile(r"[SABCDEFUG]")

    def extract_grade(cell):
        """从单元格中提取适应性评级字符（如 A, B, C 等）"""
        hidden = cell.find("div")
        if hidden:
            hidden_text = hidden.get_text(strip=True)
            if hidden_text:
                return hidden_text

        for img in cell.find_all("img", alt=True):
            match = grade_letter_pattern.search(img["alt"])
            if match:
                return match.group(0)

        text = cell.get_text(separator=" ", strip=True)
        match = grade_letter_pattern.search(text)
        if match:
            return match.group(0)

        return None

    def extract_initial_stars(cell):
        """从单元格中提取初始星级数量"""
        star_imgs = cell.find_all("img")
        if star_imgs:
            return len(star_imgs)

        digits = re.findall(r"\d+", cell.get_text())
        return int(digits[0]) if digits else None

    # 各个属性在 Bwiki 表格行中的对应列位置
    column_indices = {
        "稀有度": 2,
        "草地": 8,
        "泥地": 9,
        "短距离": 10,
        "英里": 11,
        "中距离": 12,
        "长距离": 13,
        "领跑": 14,
        "跟前": 15,
        "居中": 16,
        "后追": 17,
    }

    # 遍历 Bwiki 图鉴表格行并进行数据抓取
    for row in soup.select("table#CardSelectTr tbody tr"):
        cells = row.find_all("td")
        if len(cells) <= max(column_indices.values()):
            continue

        name_cell = cells[1]
        ja_name = None
        # 优先提取标注了 lang="ja" 的日文名称标签（排除名称前缀的称号，如 【...】）
        for span in name_cell.find_all("span", attrs={"lang": "ja"}):
            text = span.get_text(strip=True)
            if not text:
                continue
            if text.startswith("【") and text.endswith("】"):
                continue
            ja_name = text
            break

        # 后备提取超链接链接文本
        if not ja_name:
            anchors = name_cell.find_all("a")
            for anchor in anchors:
                text = anchor.get_text(strip=True)
                if text:
                    ja_name = text
                    break

        if not ja_name:
            continue

        target_ids = ja_to_ids.get(ja_name)
        if not target_ids:
            continue

        # 解析各列的属性适应性与稀有度
        for column, index in column_indices.items():
            value = (
                extract_initial_stars(cells[index])
                if column == "稀有度"
                else extract_grade(cells[index])
            )
            if value is None or value == "":
                continue

            for cid in target_ids:
                if cid not in character_stats:
                    character_stats[cid] = make_stat_dict()
                current_values = character_stats[cid][column]
                if value not in current_values:
                    current_values.append(value)

    # 3. 处理星级资产图标（从本地猜角色静态资源中复制组合星级图标）
    umamusume_assets_dir = OUTPUT_ASSETS_DIR / UMAMUSUME_ID
    umamusume_assets_dir.mkdir(parents=True, exist_ok=True)
    
    local_uma_tags = GUESSER_WORKSPACE / "client" / "public" / "assets" / "tag" / "umamusume"
    if local_uma_tags.exists():
        for rarity in range(1, 4):
            src_path = local_uma_tags / f"{rarity}star.png"
            dest_path = umamusume_assets_dir / f"{rarity}star.png"
            if src_path.exists():
                print(f"[赛马娘] 发现本地星级资源，正在复制 {rarity}star.png")
                shutil.copy(src_path, dest_path)

    # 4. 生成规范的 JSON 数据格式
    terrain_columns = ["草地", "泥地"]
    distance_columns = ["短距离", "英里", "中距离", "长距离"]
    running_style_columns = ["领跑", "跟前", "居中", "后追"]

    def should_add_tag(values):
        # 只要该适应性在初始或觉醒中达到 A 或 B，即作为该角色的可选检索标签
        return any(value in {"A", "B"} for value in values)

    tags = {}
    for cid in sorted(character_stats.keys(), key=int):
        stats = character_stats[cid]
        entry = {}
        entry["_name"] = id_name_mapping[cid]["zh"] or id_name_mapping[cid]["ja"]

        rarity_values = sorted({value for value in stats["稀有度"] if isinstance(value, int)})
        if rarity_values:
            entry["稀有度"] = {
                f"{rarity}星": f"<img src='/assets/extra_tags/{UMAMUSUME_ID}/{rarity}star.png' alt='{rarity}星' />"
                for rarity in rarity_values
            }

        terrain_tags = {
            column: column
            for column in terrain_columns
            if should_add_tag(stats[column])
        }
        if terrain_tags:
            entry["场地"] = terrain_tags

        distance_tags = {
            column: column
            for column in distance_columns
            if should_add_tag(stats[column])
        }
        if distance_tags:
            entry["距离"] = distance_tags

        running_tags = {
            column: column
            for column in running_style_columns
            if should_add_tag(stats[column])
        }
        if running_tags:
            entry["跑法"] = running_tags

        if entry:
            tags[cid] = entry

    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{UMAMUSUME_ID}.json"
    from character_tags_crawler.utils.file import merge_and_save_extra_tags
    merge_and_save_extra_tags(UMAMUSUME_ID, tags, str(out_json_file), str(GUESSER_WORKSPACE))
    print(f"[赛马娘] 成功写入 {len(tags)} 个角色属性到 {out_json_file}")

def main():
    print("=== 赛马娘 Extra Tags 自动爬取与处理程序 ===")
    try:
        process_umamusume()
    except Exception as e:
        print(f"执行赛马娘爬取时发生错误: {e}")
        import traceback
        traceback.print_exc()
    print("=== 执行完毕 ===")

if __name__ == "__main__":
    main()
