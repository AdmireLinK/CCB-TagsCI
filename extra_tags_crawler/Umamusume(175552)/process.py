import json
import requests
from pathlib import Path

def get_bangumi_data(subject_id):
    url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_wiki_data(wiki_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(wiki_url, headers=headers)
    response.raise_for_status()
    return response.text

def process_umamusume():
    subject_id = 175552
    
    bangumi_data = get_bangumi_data(subject_id)
    
    wiki_url = "https://wiki.biligame.com/umamusume/赛马娘图鉴"
    wiki_content = get_wiki_data(wiki_url)
    
    tags = {
        "subject_id": subject_id,
        "name": bangumi_data.get("name", ""),
        "name_cn": bangumi_data.get("name_cn", ""),
        "characters": []
    }
    
    output_path = Path("../../outputs/extra_tags/175552.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    output_path.write_text(json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"Generated {output_path}")

if __name__ == "__main__":
    process_umamusume()