import re
import json
from pathlib import Path
from bs4 import BeautifulSoup

def make_tag_img(value):
    return f"<img src='/assets/tag/ys/{value}.png' alt='{value}' />"

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
        name = anchor.get_text(strip=True)
        id_name_mapping[character_id] = name

    return id_name_mapping

def parse_bwiki_mapping():
    script_dir = Path(__file__).parent
    bwiki_html = (script_dir / "bwiki.txt").read_text(encoding="utf-8")
    soup = BeautifulSoup(bwiki_html, "html.parser")

    mapping = {
        '空': {
            "稀有度": '5星',
            "武器类型": '单手剑',
            "属性": [],
            "所属国家": '其它'
        },
        '荧': {
            "稀有度": '5星',
            "武器类型": '单手剑',
            "属性": [],
            "所属国家": '其它'
        }
    }

    for card in soup.select("#CardSelectTr div.divsort"):
        name_block = card.find("div", class_="L")
        if not name_block:
            continue

        name = name_block.get_text(strip=True)
        rarity = card.get("data-param1", "").strip()
        element = card.get("data-param2", "").strip()
        weapon = card.get("data-param3", "").strip()
        nation = card.get("data-param4", "").strip()

        if not name or not rarity:
            continue

        if nation == '其他':
            nation = '其它'

        if '旅行者' in name:
            if element in ('', '无', '与旅行者相同'):
                continue
            for traveler in ('空', '荧'):
                if element not in mapping[traveler]["属性"]:
                    mapping[traveler]["属性"].append(element)
            continue

        mapping[name] = {
            "稀有度": rarity,
            "武器类型": weapon,
            "属性": element,
            "所属国家": nation
        }

    return mapping

def process_genshin_impact():
    id_name_mapping = parse_bangumi_mapping()
    mapping = parse_bwiki_mapping()

    id_info = {}
    unmatched_names = []

    for id_, name in id_name_mapping.items():
        if name in mapping:
            id_info[id_] = mapping[name]
        else:
            unmatched_names.append(name)

    id_info['80855'] = mapping['埃洛伊']

    extra_tags = {}

    for id_, info in id_info.items():
        rarity = info['稀有度']
        weapon = info['武器类型']
        element = info['属性']
        nation = info['所属国家']

        if isinstance(element, list):
            element_dict = {e: make_tag_img(e)+e for e in element}
        else:
            element_dict = {element: make_tag_img(element)+element}

        extra_tags[id_] = {
            "_name": id_name_mapping[id_],
            "稀有度": {rarity: make_tag_img(rarity)},
            "属性": element_dict,
            "武器类型": {weapon: make_tag_img(weapon)+weapon},
            "所属": {nation: make_tag_img(nation)+nation if (nation != '其它' and nation != '至冬') else nation}
        }

    script_dir = Path(__file__).parent
    output_path = script_dir.parent.parent / "outputs" / "extra_tags" / "284157.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(extra_tags, f, ensure_ascii=False, indent=2)

    print(f"Generated {output_path}")

if __name__ == "__main__":
    process_genshin_impact()