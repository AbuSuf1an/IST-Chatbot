#!/usr/bin/env python3
"""
Process scraped website content and add to database
"""

from update_db import DatabaseUpdater
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    try:
        updater = DatabaseUpdater()
        
        # Clear old web content
        updater.clear_web_scraped_data()
        
        # Process new scraped content
        updater.process_scraped_content()
        
        logger.info("✅ Web content processing completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Web content processing failed: {str(e)}")

if __name__ == "__main__":
    main()