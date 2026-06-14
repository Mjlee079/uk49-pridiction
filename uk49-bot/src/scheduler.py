import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from src.scraper import scrape_latest_results
from src.api_fetcher import get_latest_from_api
from src.memory import check_and_update_accuracy, self_correct
from src.state import save_state, load_state
from src.database import init_db

logger = logging.getLogger(__name__)

# UK timezone for 12:49 draw
UK_TIMEZONE = pytz.timezone(os.getenv("DRAW_TIMEZONE", "Europe/London"))
DRAW_TIME = os.getenv("DRAW_TIME", "12:49")


def fetch_and_update_job():
    """
    Scheduled job: Fetch latest result, update accuracy, and self-correct.
    Runs daily after the Lunchtime draw (12:49 UK time).
    """
    logger.info("Running scheduled fetch job...")

    try:
        # Try API first, fallback to scraper
        result = get_latest_from_api()
        if not result:
            logger.info("API fetch failed, trying scraper...")
            result = scrape_latest_results()

        if result:
            logger.info(f"Successfully fetched result: {result}")
            # Update accuracy for any pending predictions
            check_and_update_accuracy()
            # Self-correct weights based on this draw
            self_correct(draw_type="LUNCHTIME")
            # Save state to JSON
            state = load_state()
            save_state(state)
            logger.info("Self-correction and state save complete")
        else:
            logger.info("No new result available yet")

    except Exception as e:
        logger.error(f"Scheduled job error: {e}")


def setup_scheduler() -> BackgroundScheduler:
    """Configure and return the background scheduler."""
    scheduler = BackgroundScheduler(timezone=UK_TIMEZONE)

    # Schedule: Daily at 13:00 UK time (10 minutes after 12:49 draw)
    # This gives time for results to be published
    scheduler.add_job(
        fetch_and_update_job,
        trigger=CronTrigger(hour=13, minute=0),
        id="daily_fetch",
        name="Daily Lunchtime Result Fetch",
        replace_existing=True,
    )

    # Also check at 12:55 (5 min after draw)
    scheduler.add_job(
        fetch_and_update_job,
        trigger=CronTrigger(hour=12, minute=55),
        id="quick_fetch",
        name="Quick Post-Draw Fetch",
        replace_existing=True,
    )

    # And once more at 13:15 as backup
    scheduler.add_job(
        fetch_and_update_job,
        trigger=CronTrigger(hour=13, minute=15),
        id="backup_fetch",
        name="Backup Fetch",
        replace_existing=True,
    )

    logger.info("Scheduler configured: Runs at 12:55, 13:00, and 13:15 UK time daily")
    return scheduler


def start_scheduler():
    """Start the background scheduler."""
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("Scheduler started")
    return scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    scheduler = start_scheduler()

    try:
        # Keep running
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
