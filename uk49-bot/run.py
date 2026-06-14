import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup logging to both file and console
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"bot_{datetime.now().strftime('%Y%m%d')}.log")

# Create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# File handler
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)

# Setup root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Mask httpx logging to prevent token exposure
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the UK49 Lunchtime Bot."""
    logger.info("=" * 50)
    logger.info("UK49 Lunchtime AI Prediction Bot Starting...")
    logger.info("=" * 50)

    # Add src to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from src.database import init_db
    from src.scraper import run_full_scrape
    from src.scheduler import start_scheduler
    from src.bot import start_bot

    # Initialize database
    logger.info("Initializing database...")
    init_db()

    # Check if we need to run initial scrape
    from src.database import get_draw_count
    from src.database import get_all_draws
    lunch_count = get_draw_count()
    brunch_count = len(get_all_draws('BRUNCHTIME'))
    total_count = lunch_count + brunch_count
    
    if total_count == 0:
        logger.info("No data found. Running initial historical scrape...")
        count = run_full_scrape()
        logger.info(f"Initial scrape complete: {count} draws")
    else:
        logger.info(f"Database has {brunch_count} Brunchtime + {lunch_count} Lunchtime = {total_count} total draws")
        
        # If we have Brunchtime but not Lunchtime, or vice versa, scrape missing data
        if brunch_count == 0 or lunch_count == 0:
            logger.info("Missing draw data. Running scrape to complete dataset...")
            count = run_full_scrape()
            logger.info(f"Scraped {count} additional draws")

    # Start scheduler in background
    logger.info("Starting background scheduler...")
    scheduler = start_scheduler()

    # Start Telegram bot (this blocks)
    logger.info("Starting Telegram bot...")
    try:
        start_bot()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduler.shutdown()
        logger.info("Goodbye!")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        scheduler.shutdown()
        raise


if __name__ == "__main__":
    main()
