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

def process_mc():
    """
    鸣潮 Extra Tags 自动爬取与处理核心逻辑：
    1. 爬取 Bangumi 鸣潮角色列表
    2. 爬取鸣潮 Bwiki 角色筛选数据 (带有 Referer 头绕过 EdgeOne 567 拦截)
    3. 匹配对齐 Bangumi 角色与 Bwiki 共鸣者属性
    4. 复制本地 mc tags 资产
    5. 生成 JSON
    """
    # 1. 爬取 Bangumi 数据
    bgm_characters = crawl_bangumi_characters(MC_ID)

    # 2. 爬取鸣潮 Bwiki
    print("[鸣潮] 正在抓取鸣潮 Bwiki 共鸣者列表...")
    bwiki_url = "https://wiki.biligame.com/wutheringwaves/%E5%85%B1%E9%B8%A3%E8%80%85"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/wutheringwaves/"
    }
    soup = safe_soup(bwiki_url, headers=headers, cooldown=2)

    wiki_chars = {}
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
            
        # 从第一个 td 的最后一个 a 标签提取出角色的真实名字
        anchors = tds[0].find_all("a")
        if not anchors:
            continue
        raw_name = anchors[-1].get_text(strip=True)
        name = clean_wiki_name(raw_name)
        
        # 属性 (冷凝, 导电, 气动, 热熔, 衍射, 湮灭)
        element = attrs.get("data-param1", "").strip()
        # 稀有度星级 (5, 4) -> 5星 / 4星
        rarity_num = attrs.get("data-param2", "").strip()
        rarity = f"{rarity_num}星" if rarity_num.isdigit() else f"{rarity_num}星"
        # 武器 (佩枪, 迅刀, 臂铠, 音感仪, 长刃)
        weapon = attrs.get("data-param3", "").strip()
        # 战斗风格标签
        style_raw = attrs.get("data-param4", "").strip()
        styles = [s.strip() for s in style_raw.split(",") if s.strip()]

        wiki_chars[name] = {
            "element": element,
            "rarity": rarity,
            "rarity_num": rarity_num,
            "weapon": weapon,
            "styles": styles
        }

    print(f"[鸣潮] Bwiki 上共获取了 {len(wiki_chars)} 个角色的数据。")

    # 别名与多版本映射
    ALIAS_MAP = {
        "漂泊者·消灭": "漂泊者",
        "漂泊者·衍射": "漂泊者",
        "折枝": "折枝",
        "今汐": "今汐",
        "长离": "长离"
    }

    # 归一化名字辅助匹配
    def normalize_name(n):
        n = re.sub(r'[^\w\u4e00-\u9fa5]', '', n)
        return n

    # 3. 匹配 Bangumi 角色
    extra_tags = {}
    mc_assets_dir = OUTPUT_ASSETS_DIR / MC_ID
    mc_assets_dir.mkdir(parents=True, exist_ok=True)
    
    local_mc_tags = GUESSER_WORKSPACE / "client" / "public" / "assets" / "tag" / "mc"
    available_icons = set()
    if mc_assets_dir.exists() and any(mc_assets_dir.glob("*.png")):
        available_icons = {f.name.rsplit(".", 1)[0] for f in mc_assets_dir.glob("*.png")}
    elif local_mc_tags.exists():
        available_icons = {f.rsplit(".", 1)[0] for f in os.listdir(local_mc_tags) if f.endswith(".png")}

    # 4. 自动下载缺失的图片资产
    from character_tags_crawler.utils.network import download_bwiki_missing_assets
    api_url = "https://wiki.biligame.com/wutheringwaves/api.php"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://wiki.biligame.com/wutheringwaves/"
    }
    
    referenced_icons = set()
    for char in wiki_chars.values():
        r_num = char["rarity_num"]
        if r_num.isdigit():
            referenced_icons.add(f"{r_num}星.png")
        referenced_icons.add(f"{char['element']}.png")
        referenced_icons.add(f"{char['weapon']}.png")
                    
    missing_assets = {}
    for icon_name in referenced_icons:
        name = icon_name.rsplit(".", 1)[0]
        query_names = [name]
        
        candidates = []
        for qn in query_names:
            candidates.extend([
                f"File:图标-{qn}.png",
                f"File:Logo-{qn}.png",
                f"File:{qn}.png",
                f"File:属性-{qn}.png",
                f"File:武器-{qn}.png",
                f"File:声骸-{qn}.png",
                f"File:星级_{qn}.png",
                f"File:星级-{qn}.png",
                f"File:{qn}.svg"
            ])
        missing_assets[icon_name] = candidates

    download_bwiki_missing_assets(api_url, missing_assets, mc_assets_dir, headers)

    # Helper functions for dynamic file existence checking
    def get_rarity_html(rarity, rarity_num):
        rarity_file = f"{rarity_num}星" if rarity_num.isdigit() else rarity
        filename = f"{rarity_file}.png"
        if (mc_assets_dir / filename).exists():
            return f"<img src='/assets/extra_tags/{MC_ID}/{filename}' alt='{rarity}' />"
        return rarity

    def get_tag_html(tag_name):
        if not tag_name:
            return ""
        filename = f"{tag_name}.png"
        if (mc_assets_dir / filename).exists():
            return f"<img src='/assets/extra_tags/{MC_ID}/{filename}'/>{tag_name}"
        return tag_name

    for cid, info in bgm_characters.items():
        bgm_name = info["name"]
        bgm_zh = info["chinese_name"]
        
        matched_char = None
        for candidate in [bgm_zh, bgm_name]:
            if not candidate:
                continue
            
            # 精确匹配
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
            element = matched_char["element"]
            rarity = matched_char["rarity"]
            rarity_num = matched_char["rarity_num"]
            weapon = matched_char["weapon"]
            styles = matched_char["styles"]

            # 稀有度
            rarity_html = get_rarity_html(rarity, rarity_num)
                
            # 属性
            element_html = get_tag_html(element)
                
            # 武器
            weapon_html = get_tag_html(weapon)
                
            # 拼装属性与标签
            tags_dict = {
                element: element_html,
                weapon: weapon_html
            }
            
            # 追加战斗风格标签
            for style in styles:
                tags_dict[style] = style
                
            extra_tags[cid] = {
                "稀有度": {rarity: rarity_html},
                "标签": tags_dict
            }

    # 5. 保存 JSON 输出
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    out_json_file = OUTPUT_JSON_DIR / f"{MC_ID}.json"
    from character_tags_crawler.utils.file import merge_and_save_extra_tags
    merge_and_save_extra_tags(MC_ID, extra_tags, str(out_json_file), str(GUESSER_WORKSPACE))
    print(f"[鸣潮] 成功写入 {len(extra_tags)} 个角色属性到 {out_json_file}")

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
