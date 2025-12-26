from pathlib import Path
import re
import json
from collections import defaultdict

from bs4 import BeautifulSoup


def parse_bangumi_mapping():
    script_dir = Path(__file__).parent
    bangumi_html = (script_dir / "bangumi.txt").read_text(encoding="utf-8")
    soup = BeautifulSoup(bangumi_html, "html.parser")

    id_name_mapping = {}
    for subtitle in soup.select("div.item h2.subtitle"):
        anchor = subtitle.find("a", href=re.compile(r"^/character/\d+"))
        if not anchor:
            continue

        match = re.search(r"/character/(\d+)", anchor["href"])
        if not match:
            continue

        character_id = match.group(1)
        japanese_name = anchor.get_text(strip=True)

        chinese_span = subtitle.find("span", class_="tip")
        chinese_name = chinese_span.get_text(strip=True) if chinese_span else ""

        id_name_mapping[character_id] = {
            "ja": japanese_name,
            "zh": chinese_name,
        }

    return id_name_mapping


def parse_bwiki_stats(id_name_mapping):
    script_dir = Path(__file__).parent
    bwiki_html = (script_dir / "bwiki.txt").read_text(encoding="utf-8")
    bwiki_soup = BeautifulSoup(bwiki_html, "html.parser")

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

    ja_to_ids = defaultdict(list)
    for character_id, names in id_name_mapping.items():
        ja_to_ids[names["ja"]].append(character_id)

    def make_stat_dict():
        return {column: [] for column in columns}

    character_stats = defaultdict(make_stat_dict)

    grade_letter_pattern = re.compile(r"[SABCDEFUG]")

    def extract_grade(cell):
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
        star_imgs = cell.find_all("img")
        if star_imgs:
            return len(star_imgs)

        digits = re.findall(r"\d+", cell.get_text())
        return int(digits[0]) if digits else None

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

    for row in bwiki_soup.select("table#CardSelectTr tbody tr"):
        cells = row.find_all("td")
        if len(cells) <= max(column_indices.values()):
            continue

        name_cell = cells[1]
        ja_name = None
        for span in name_cell.find_all("span", attrs={"lang": "ja"}):
            text = span.get_text(strip=True)
            if not text:
                continue
            if text.startswith("【") and text.endswith("】"):
                continue
            ja_name = text
            break

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

        for column, index in column_indices.items():
            value = (
                extract_initial_stars(cells[index])
                if column == "稀有度"
                else extract_grade(cells[index])
            )
            if value is None or value == "":
                continue

            for character_id in target_ids:
                current_values = character_stats[character_id][column]
                if value not in current_values:
                    current_values.append(value)

    return character_stats


def process_umamusume():
    id_name_mapping = parse_bangumi_mapping()
    character_stats = parse_bwiki_stats(id_name_mapping)

    terrain_columns = ["草地", "泥地"]
    distance_columns = ["短距离", "英里", "中距离", "长距离"]
    running_style_columns = ["领跑", "跟前", "居中", "后追"]

    def should_add_tag(values):
        return any(value in {"A", "B"} for value in values)

    tags = {}
    for character_id in sorted(character_stats.keys(), key=int):
        stats = character_stats[character_id]
        entry = {}
        entry["_name"] = id_name_mapping[character_id]["zh"]

        rarity_values = sorted({value for value in stats["稀有度"] if isinstance(value, int)})
        if rarity_values:
            entry["稀有度"] = {
                f"{rarity}星": f"<img src='/assets/tag/umamusume/{rarity}star.png' alt='{rarity}星' />"
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
            tags[character_id] = entry

    script_dir = Path(__file__).parent
    output_path = script_dir.parent.parent / "outputs" / "extra_tags" / "175552.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)

    print(f"Generated {output_path}")
    print(f"Wrote {len(tags)} entries")


if __name__ == "__main__":
    process_umamusume()
