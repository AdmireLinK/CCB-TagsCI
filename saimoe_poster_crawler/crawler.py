"""
ISML Poster Crawler
Fetches all winner posters and recipient character details from https://internationalsaimoe.moe/gallery.
"""

import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup

# Ensure UTF-8 output encoding for Windows CLI
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

BASE_URL = "https://internationalsaimoe.moe/gallery"


def fetch_gallery_html(lang: str) -> str:
    """Fetch raw HTML string for gallery page with specific language parameter."""
    url = f"{BASE_URL}?lang={lang}"
    print(f"[Crawler] Fetching ISML gallery page ({lang})...")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.encoding = 'utf-8'
    return resp.text


def parse_poster_boxes(html_text: str):
    """Parse winner poster boxes from gallery HTML."""
    soup = BeautifulSoup(html_text, 'html.parser')
    boxes = soup.find_all('div', class_='winner_poster_box')
    return boxes


def extract_box_data(box):
    """Extract information from a winner poster box."""
    # Find year header from parent full-section
    parent_section = box.find_parent('div', class_='full-section')
    year = ""
    if parent_section:
        h1 = parent_section.find('h1')
        if h1:
            year = h1.get_text(strip=True)

    # Poster image link
    img_tag = box.find('img')
    img_url = img_tag['src'] if img_tag and 'src' in img_tag.attrs else ""
    a_tag = box.find('a')
    a_url = a_tag['href'] if a_tag and 'href' in a_tag.attrs else ""

    # Ensure link starts with https://cdn.isml.app/
    final_img_url = ""
    if img_url.startswith("https://cdn.isml.app/"):
        final_img_url = img_url
    elif a_url.startswith("https://cdn.isml.app/"):
        final_img_url = a_url

    # Text fields
    text_boxes = box.find_all('div', class_='winner_text_box')
    award = text_boxes[0].get_text(strip=True) if len(text_boxes) > 0 else ""

    name = ""
    for t in text_boxes:
        if 'winner_name' in t.get('class', []):
            name = t.get_text(strip=True)

    series = text_boxes[2].get_text(strip=True) if len(text_boxes) > 2 else ""

    return {
        "year": year,
        "award": award,
        "name": name,
        "series": series,
        "img_url": final_img_url
    }


def crawl_isml_posters(output_path: str = None) -> list:
    """Crawl ISML gallery in JA, ZH, and EN to compile complete winner poster records."""
    html_ja = fetch_gallery_html("ja")
    html_zh = fetch_gallery_html("zh_hans")
    html_en = fetch_gallery_html("en")

    boxes_ja = parse_poster_boxes(html_ja)
    boxes_zh = parse_poster_boxes(html_zh)
    boxes_en = parse_poster_boxes(html_en)

    total_boxes = len(boxes_ja)
    print(f"[Crawler] Found {total_boxes} winner poster boxes.")

    posters_list = []
    isml_characters = {}

    for b_ja, b_zh, b_en in zip(boxes_ja, boxes_zh, boxes_en):
        data_ja = extract_box_data(b_ja)
        data_zh = extract_box_data(b_zh)
        data_en = extract_box_data(b_en)

        img_url = data_ja["img_url"] or data_zh["img_url"] or data_en["img_url"]
        if not img_url.startswith("https://cdn.isml.app/"):
            continue

        item = {
            "year": data_ja["year"] or data_zh["year"] or data_en["year"],
            "award_ja": data_ja["award"],
            "award_zh": data_zh["award"],
            "award_en": data_en["award"],
            "name_ja": data_ja["name"],
            "name_zh": data_zh["name"],
            "name_en": data_en["name"],
            "series_ja": data_ja["series"],
            "series_zh": data_zh["series"],
            "series_en": data_en["series"],
            "img_url": img_url
        }
        posters_list.append(item)

        # Extract ISML character ID from filename (e.g. 2025-heavenly_tiara-2093.png)
        m = re.search(r"-(\d+(?:_\d+)*)\.(?:png|jpg|jpeg|gif)$", img_url, re.IGNORECASE)
        char_id_key = m.group(1) if m else img_url

        if char_id_key not in isml_characters:
            isml_characters[char_id_key] = {
                "isml_id": char_id_key,
                "name_ja": data_ja["name"],
                "name_zh": data_zh["name"],
                "name_en": data_en["name"],
                "posters": []
            }
        if img_url not in isml_characters[char_id_key]["posters"]:
            isml_characters[char_id_key]["posters"].append(img_url)

    result = {
        "total_posters": len(posters_list),
        "total_unique_entities": len(isml_characters),
        "posters": posters_list,
        "characters": isml_characters
    }

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[Crawler] Successfully saved crawl results to {output_path}")

    return result


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_json = os.path.join(script_dir, "saimoe_posters.json")
    crawl_isml_posters(output_path=output_json)
