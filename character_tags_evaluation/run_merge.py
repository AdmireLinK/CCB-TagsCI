import os
import sys
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add directories to sys.path
file_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(file_dir)
sys.path.insert(0, file_dir)

# Load environment variables from guesser repo's server/.env file
guesser_env_path = os.path.normpath(os.path.join(project_root, '..', 'anime-character-guessr', 'server', '.env'))
if not os.path.exists(guesser_env_path):
    fallback_env_path = os.path.normpath(os.path.join(project_root, 'anime-character-guessr', 'server', '.env'))
    if os.path.exists(fallback_env_path):
        guesser_env_path = fallback_env_path

if os.path.exists(guesser_env_path):
    logger.info(f"Loading environment variables from {guesser_env_path}")
    load_dotenv(dotenv_path=guesser_env_path)
else:
    logger.warning(f"Guesser .env file not found at: {guesser_env_path}")

from user_tag_processor import UserTagProcessor

def main():
    processor = UserTagProcessor()
    
    # Path configuration
    base_tags_path = os.path.normpath(os.path.join(
        project_root, 'outputs', 'id_tags.json'
    ))
    
    # Check if base tags exist
    if not os.path.exists(base_tags_path):
        # Try fallback path inside crawler
        base_tags_path_fallback = os.path.normpath(os.path.join(
            project_root, 'character_tags_crawler', 'bangumi', 'anime_character_guessr', 'id_tags.json'
        ))
        if os.path.exists(base_tags_path_fallback):
            base_tags_path = base_tags_path_fallback
        else:
            logger.error("Base tags file 'id_tags.json' not found in outputs/ or crawler directory.")
            logger.error("Please run the crawler mapper first.")
            sys.exit(1)
            
    logger.info(f"Using base tags from: {base_tags_path}")

    # Fallback directory for local json files
    local_fallback_dir = os.path.normpath(os.path.join(
        project_root, 'character_tags_crawler', 'bangumi', 'anime_character_guessr'
    ))
    
    # Load user contribution feedback and new tag proposals
    character_tags, new_tags = processor.load_feedback_data(local_fallback_dir=local_fallback_dir)
    
    output_js_path = os.path.normpath(os.path.join(project_root, 'outputs', 'id_tags.js'))
    existing_js_path = os.path.normpath(os.path.join(
        project_root, '..', 'anime-character-guessr', 'client', 'src', 'data', 'id_tags.js'
    ))
    if not os.path.exists(existing_js_path):
        fallback_js_path = os.path.normpath(os.path.join(
            project_root, 'anime-character-guessr', 'client', 'src', 'data', 'id_tags.js'
        ))
        if os.path.exists(fallback_js_path):
            existing_js_path = fallback_js_path
    
    # Merge and optimize tags
    processor.merge_and_save(
        base_tags_path=base_tags_path,
        character_tags=character_tags,
        new_tags=new_tags,
        output_js_path=output_js_path,
        existing_js_path=existing_js_path
    )
    
    logger.info("Evaluation merge process completed.")

if __name__ == '__main__':
    main()
