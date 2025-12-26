import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Character Tags Crawler'))

from user_tag_processor import UserTagProcessor


def main():
    processor = UserTagProcessor()
    
    user_tags = processor.load_user_tags_from_mongo()
    print(f'Loaded {len(user_tags)} user tags from MongoDB')
    
    merged_tags = processor.merge_and_save_tags(user_tags)
    print(f'Merged tags for {len(merged_tags)} characters')
    print(f'Saved to: Outputs/id_tags.js')


if __name__ == '__main__':
    main()
