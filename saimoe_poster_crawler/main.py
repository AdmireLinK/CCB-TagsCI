"""
Main execution script for ISML Poster Crawler & JSON Updater.
Runs the complete workflow:
1. Crawls https://internationalsaimoe.moe/gallery for winner poster image links starting with https://cdn.isml.app/
2. Removes all https://static.wikitide.net links from server/data/character_images.json
3. Maps extracted poster links to winner characters and updates character_images.json
"""

import os
import sys
from crawler import crawl_isml_posters
from updater import update_character_images

# Ensure UTF-8 output encoding for Windows CLI
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    saimoe_posters_json = os.path.join(script_dir, "saimoe_posters.json")

    print("==================================================")
    print("Step 1: Crawling ISML Gallery Posters...")
    print("==================================================")
    crawl_data = crawl_isml_posters(output_path=saimoe_posters_json)

    print("\n==================================================")
    print("Step 2: Updating character_images.json...")
    print("==================================================")
    update_result = update_character_images(crawl_data)

    print("\n==================================================")
    print("Workflow Completed Successfully!")
    print(f"Total winners crawled: {crawl_data['total_posters']}")
    print(f"Unique winner entities: {crawl_data['total_unique_entities']}")
    print(f"Removed wikitide.net links: {update_result['wikitide_removed']}")
    print(f"Added cdn.isml.app poster links: {update_result['posters_added']}")
    print("==================================================")


if __name__ == "__main__":
    main()
