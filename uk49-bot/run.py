import os
import sys
import logging
import threading
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Load environment variables from .env file
load_dotenv()

# Setup logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"bot_{datetime.now().strftime('%Y%m%d')}.log")

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize Flask app
app = Flask(__name__)

# Global PTB application (for webhook processing)
_ptb_application = None


@app.route("/")
def index():
    """Root status page."""
    from src.database import get_draw_count
    count = get_draw_count()
    return jsonify({
        "status": "ok",
        "service": "uk49-lunchtime-bot",
        "draws": count,
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.route("/health")
def health():
    """Health check endpoint — used by Render and Better Stack."""
    from src.database import get_draw_count
    count = get_draw_count()
    return jsonify({
        "status": "ok",
        "draws": count,
        "timestamp": datetime.utcnow().isoformat(),
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive Telegram webhook updates."""
    global _ptb_application
    if _ptb_application is None:
        logger.error("Webhook received but PTB application not initialized")
        return jsonify({"status": "error", "message": "Bot not ready"}), 503

    try:
        update = request.get_json(force=True)
        asyncio.run_coroutine_threadsafe(
            _ptb_application.update_queue.put(update),
            _ptb_application._event_loop,
        )
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def _run_ptb_in_thread():
    """Run the Telegram bot (PTB application) in a background thread."""
    global _ptb_application
    from src.bot import create_application
    from src.security import get_key
    import telegram

    logger.info("Starting Telegram PTB application in background thread...")
    _ptb_application = create_application()

    # Start the application (creates event loop)
    _ptb_application._event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ptb_application._event_loop)

    _ptb_application._event_loop.run_until_complete(_ptb_application.initialize())
    _ptb_application._event_loop.run_until_complete(_ptb_application.start())

    # Set webhook on Telegram servers
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        bot_url = f"{webhook_url}/webhook"
        logger.info(f"Setting webhook to: {bot_url}")
        _ptb_application._event_loop.run_until_complete(
            telegram.Bot(get_key("TELEGRAM_BOT_TOKEN")).set_webhook(url=bot_url)
        )
        logger.info("Webhook set successfully")
    else:
        logger.warning("WEBHOOK_URL not set — webhook will not be registered on Telegram")

    logger.info("Telegram bot ready (webhook mode)")
    _ptb_application._event_loop.run_forever()


def main():
    """Main entry point for the UK49 Lunchtime Bot on Render."""
    logger.info("=" * 50)
    logger.info("UK49 Lunchtime AI Prediction Bot Starting (Render Mode)...")
    logger.info("=" * 50)

    from src.database import init_db
    from src.scraper import run_full_scrape
    from src.scheduler import start_scheduler

    # Initialize database
    logger.info("Initializing database...")
    init_db()

    # Check if we need to run initial scrape
    from src.database import get_draw_count, get_all_draws
    lunch_count = get_draw_count()
    brunch_count = len(get_all_draws('BRUNCHTIME'))
    total_count = lunch_count + brunch_count

    if total_count == 0:
        logger.info("No data found. Running initial historical scrape...")
        count = run_full_scrape()
        logger.info(f"Initial scrape complete: {count} draws")
    else:
        logger.info(f"Database has {brunch_count} Brunchtime + {lunch_count} Lunchtime = {total_count} total draws")
        if brunch_count == 0 or lunch_count == 0:
            logger.info("Missing draw data. Running scrape to complete dataset...")
            count = run_full_scrape()
            logger.info(f"Scraped {count} additional draws")

    # Start scheduler in background
    logger.info("Starting background scheduler...")
    scheduler = start_scheduler()

    # Start Telegram bot in background thread (webhook mode)
    ptb_thread = threading.Thread(target=_run_ptb_in_thread, daemon=True)
    ptb_thread.start()

    # Start Flask in main thread (for Render)
    port = int(os.getenv("PORT", 10000))
    logger.info(f"Starting Flask server on port {port}...")
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
