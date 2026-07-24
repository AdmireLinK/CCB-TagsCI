"""
Character Images JSON Updater
Removes all static.wikitide.net poster links from character_images.json
and maps extracted cdn.isml.app poster links to corresponding winners.
"""

import json
import os
import re
import sys

# Ensure UTF-8 output encoding for Windows CLI
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Default relative paths
DEFAULT_CHAR_DB_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "anime-character-guessr",
        "server",
        "data",
        "character_images.json"
    )
)

DEFAULT_MOE2BGM_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "character_tags_crawler",
        "bangumi",
        "moegirl2bgm.json"
    )
)

# Explicit alias overrides for special name differences between ISML & Bangumi DB
EXTRA_ALIASES = {
    "高木": [41849],               # 高木さん (Takagi-san)
    "ピカチュウ": [2010],           # サトシのピカチュウ (Pikachu)
    "アーチャー": [3216],           # エミヤ (Archer / Emiya)
    "卫宫": [3216],
    "セイバー": [273],             # アルトリア・ペンドラゴン (Saber / Artoria Pendragon)
    "阿尔托莉雅·潘德拉贡": [273],
    "黒羽早雪": [15498],           # 黒雪姫 (Kuroyukihime)
    "黑羽早雪": [15498],
}

SIMP_TRAD_MAP = {
    "时": "時", "国": "國", "书": "書", "爱": "愛", "鸣": "鳴",
    "濑": "瀬", "晓": "暁", "泽": "澤", "后": "後", "藤": "藤",
    "长": "長", "崎": "崎", "优": "優", "纯": "純", "鹰": "鷹",
    "依": "依", "䌷": "紬", "凛": "凛", "柊": "柊", "绘": "絵",
    "里": "里", "亚": "亜", "织": "織", "绪": "緒", "华": "華"
}


def clean_str(s: str) -> str:
    """Normalize character name by removing whitespace, middle dots, hyphens, and converting to lowercase."""
    if not s:
        return ""
    return re.sub(r"[\s・·•\-–—&＆/,'\"()（）]+", "", s).lower()


def to_trad(s: str) -> str:
    """Convert common simplified Chinese characters to traditional / Japanese kanji equivalents."""
    return "".join([SIMP_TRAD_MAP.get(ch, ch) for ch in s])


def update_character_images(
    crawl_data: dict,
    char_db_path: str = DEFAULT_CHAR_DB_PATH,
    moe2bgm_path: str = DEFAULT_MOE2BGM_PATH
) -> dict:
    """Update character_images.json with new cdn.isml.app poster links and strip static.wikitide.net links."""

    print(f"[Updater] Loading character DB from {char_db_path}...")
    with open(char_db_path, "r", encoding="utf-8") as f:
        char_db = json.load(f)

    moe2bgm = {}
    if os.path.exists(moe2bgm_path):
        print(f"[Updater] Loading moegirl2bgm mapping from {moe2bgm_path}...")
        with open(moe2bgm_path, "r", encoding="utf-8") as f:
            moe2bgm = json.load(f)
    else:
        print("[Updater] Warning: moegirl2bgm.json not found, proceeding without extra alias map.")

    id_to_char = {c["id"]: c for c in char_db}

    # Index char_db names
    db_map = {}
    for c in char_db:
        name = c["name"]
        db_map.setdefault(clean_str(name), []).append(c)
        parts = re.split(r"[/ /]", name)
        for p in parts:
            if len(p) > 1:
                db_map.setdefault(clean_str(p), []).append(c)

    # Index moe2bgm
    moe2bgm_clean = {}
    for k, v in moe2bgm.items():
        ck = clean_str(k)
        if ck:
            moe2bgm_clean.setdefault(ck, []).append(v)

    # Map Bangumi ID -> list of ISML poster URLs
    bgm_id_to_posters = {}

    def add_poster(bgm_id, urls):
        if bgm_id in id_to_char:
            bgm_id_to_posters.setdefault(bgm_id, [])
            for url in urls:
                if url not in bgm_id_to_posters[bgm_id]:
                    bgm_id_to_posters[bgm_id].append(url)

    isml_characters = crawl_data.get("characters", {})

    for isml_id, data in isml_characters.items():
        name_ja = data.get("name_ja", "")
        name_zh = data.get("name_zh", "")
        name_en = data.get("name_en", "")
        posters = data.get("posters", [])

        # Handle couple / multi-recipient entries
        names_ja_split = [n.strip() for n in re.split(r"&|与|＆|and", name_ja)] if any(k in name_ja for k in ["&", "与", "＆", " and "]) else [name_ja]
        names_zh_split = [n.strip() for n in re.split(r"&|与|＆|and", name_zh)] if any(k in name_zh for k in ["&", "与", "＆", " and "]) else [name_zh]
        names_en_split = [n.strip() for n in re.split(r"&|与|＆|and", name_en)] if any(k in name_en for k in ["&", "与", "＆", " and "]) else [name_en]

        max_len = max(len(names_ja_split), len(names_zh_split), len(names_en_split))

        for i in range(max_len):
            nj = names_ja_split[i] if i < len(names_ja_split) else ""
            nz = names_zh_split[i] if i < len(names_zh_split) else ""
            ne = names_en_split[i] if i < len(names_en_split) else ""

            candidates = [nj, nz, ne, to_trad(nz), to_trad(nj)]
            found_ids = set()

            # 1. Check EXTRA_ALIASES
            for cand in candidates:
                cand_clean = clean_str(cand)
                if cand_clean in EXTRA_ALIASES:
                    found_ids.update(EXTRA_ALIASES[cand_clean])
                if cand in EXTRA_ALIASES:
                    found_ids.update(EXTRA_ALIASES[cand])

            # 2. Direct DB match
            if not found_ids:
                for cand in candidates:
                    c_clean = clean_str(cand)
                    if c_clean and c_clean in db_map:
                        for target in db_map[c_clean]:
                            found_ids.add(target["id"])

            # 3. Moe2bgm match
            if not found_ids:
                for cand in candidates:
                    c_clean = clean_str(cand)
                    if c_clean and c_clean in moe2bgm_clean:
                        for val in moe2bgm_clean[c_clean]:
                            val_list = val if isinstance(val, list) else [val]
                            for vid in val_list:
                                if int(vid) in id_to_char:
                                    found_ids.add(int(vid))

            for bid in found_ids:
                add_poster(bid, posters)

    print(f"[Updater] Matched {len(bgm_id_to_posters)} Bangumi characters to ISML posters.")

    # Apply changes to char_db
    modified_count = 0
    wikitide_removed = 0
    posters_added = 0

    for item in char_db:
        bgm_id = item["id"]
        mediums = item.get("image_medium", [])

        # Remove static.wikitide.net links
        new_mediums = [m for m in mediums if not m.startswith("https://static.wikitide.net")]
        wikitide_removed += (len(mediums) - len(new_mediums))

        # Add matched cdn.isml.app posters
        if bgm_id in bgm_id_to_posters:
            posters_to_add = bgm_id_to_posters[bgm_id]
            for p in posters_to_add:
                if p not in new_mediums:
                    new_mediums.append(p)
                    posters_added += 1

        if new_mediums != mediums:
            modified_count += 1
            item["image_medium"] = new_mediums

    # Save updated character_images.json
    with open(char_db_path, "w", encoding="utf-8") as f:
        json.dump(char_db, f, ensure_ascii=False, indent=2)

    print(f"[Updater] Successfully updated {char_db_path}")
    print(f"  - Modified character entries: {modified_count}")
    print(f"  - Removed static.wikitide.net links: {wikitide_removed}")
    print(f"  - Added cdn.isml.app poster links: {posters_added}")

    return {
        "modified_count": modified_count,
        "wikitide_removed": wikitide_removed,
        "posters_added": posters_added
    }


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    saimoe_posters_json = os.path.join(script_dir, "saimoe_posters.json")

    if not os.path.exists(saimoe_posters_json):
        print(f"[Updater] Error: {saimoe_posters_json} not found. Run crawler.py first.")
        sys.exit(1)

    with open(saimoe_posters_json, "r", encoding="utf-8") as f:
        crawl_data = json.load(f)

    update_character_images(crawl_data)
