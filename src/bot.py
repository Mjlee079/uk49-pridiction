import os
import logging
from typing import Dict
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.database import init_db, get_draw_count, get_latest_draw
from src.analytics import generate_analytics_report, get_combined_stats
from src.predictor_new import generate_predictions_pipeline
from src.memory import (
    get_performance_summary,
    format_prediction_history,
    check_and_update_accuracy,
    self_correct,
)
from src.diagnostic import run_diagnostic
from src.state import load_state
from src.scraper import scrape_latest_results
from src.security import get_key, get_key_masked, has_key, mask_sensitive_data
from src.audit import log_prediction, log_scrape, log_security_event
from src.rate_limiter import check_rate_limit, get_rate_limit_status

logger = logging.getLogger(__name__)

# Load from secure key manager
TELEGRAM_BOT_TOKEN = get_key("TELEGRAM_BOT_TOKEN")
ADMIN_IDS_STR = get_key("ADMIN_IDS") or ""
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set! Bot cannot start.")
else:
    logger.info(f"Telegram bot token loaded (masked): {get_key_masked('TELEGRAM_BOT_TOKEN')}")


def _is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in ADMIN_IDS


# ========== COMMAND HANDLERS ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"User {user.username or user.id} started the bot")

    welcome_text = """
🎱 Welcome to the <b>UK49 Lunchtime AI Predictor Bot!</b>

I use advanced analytics, AI (Qwen model), and pattern recognition to predict UK49 Lunchtime lottery numbers.

<b>Available Commands:</b>
📊 <b>/predict</b> - Get AI predictions for next draw (10 rows)
📈 <b>/stats</b> - View hot/cold numbers and analytics
📋 <b>/history</b> - See prediction accuracy history
🎯 <b>/last</b> - Show the latest draw result
🔄 <b>/scrape</b> - Manually fetch latest result (admin)
❓ <b>/help</b> - Show this help message

<b>How it works:</b>
1. I scrape historical UK49 Lunchtime results
2. I analyze frequencies, gaps, co-occurrences, and trends
3. I use AI (Qwen model) to identify patterns
4. I generate 5 rows of top-2 predictions with confidence scores
5. I learn from each draw to improve future predictions

<i>Note: Lottery is random. Predictions are based on statistical patterns, not guarantees.</i>
"""
    await update.message.reply_html(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await start_command(update, context)


async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /predict command - generate AI predictions via new pipeline."""
    user = update.effective_user
    user_id = str(user.id)
    user_name = user.username or str(user.id)

    logger.info(f"Prediction requested by {user_name} (ID: {user_id})")

    # Check rate limit
    allowed, reason = check_rate_limit(user_id, "predict")
    if not allowed:
        logger.warning(f"Rate limit hit for user {user_id}")
        await update.message.reply_text(f"⏳ {reason}")
        return

    # Send "thinking" message
    thinking_msg = await update.message.reply_text(
        "🧠 Running 5-signal parallel pipeline...\n"
        "Signals: Frequency/Gap • Markov • Co-occurrence • Positional • LSTM\n"
        "This may take 15-30 seconds."
    )

    try:
        # Check if we have data
        draw_count = get_draw_count()
        if draw_count == 0:
            await thinking_msg.edit_text(
                "⚠️ No data in database yet!\n"
                "Run the scraper first: /scrape\n"
                "Or wait for the scheduler to populate data."
            )
            return

        # Generate predictions via new pipeline
        predictions, telegram_text, reasoning, metadata = generate_predictions_pipeline(
            draw_type="LUNCHTIME",
            user_id=user_id,
            user_name=user_name,
        )

        if not predictions:
            await thinking_msg.edit_text(
                "❌ Failed to generate predictions.\n"
                "Please check if the LLM API is configured correctly."
            )
            return

        # Format response (Prompt 7 style + lightweight header)
        response = (
            f"🎯 <b>UK49 Lunchtime AI Predictions</b>\n"
            f"📊 Based on {draw_count} historical draws\n"
            f"🤖 Pipeline: 5-signal ensemble v2\n"
            f"═" * 30 + "\n\n"
        )

        # Append clean rows (Prompt 7 format)
        response += telegram_text + "\n\n"
        response += "═" * 30 + "\n"
        response += "<i>Use /stats to see the analytics behind these predictions.</i>"

        await thinking_msg.edit_text(response, parse_mode="HTML")

    except Exception as e:
        error_msg = mask_sensitive_data(str(e))
        logger.error(f"Prediction error: {error_msg}")
        await thinking_msg.edit_text(
            f"❌ Error generating predictions:\n<code>{error_msg}</code>",
            parse_mode="HTML",
        )


async def diagnostic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: Run diagnostic prompt on last 20 draws."""
    user = update.effective_user
    if not _is_admin(user.id):
        await update.message.reply_text("⛔ Admin only command.")
        return

    thinking_msg = await update.message.reply_text("🔍 Running diagnostic on last 20 draws...")

    try:
        result = run_diagnostic(draw_type="LUNCHTIME")

        text = (
            f"🔍 <b>Diagnostic Report</b>\n\n"
            f"📊 Avg Hit Rate: {result.get('avg_hit_rate', 0):.2f}\n"
            f"🎯 Weak Range: {result.get('weak_range', 'N/A')}\n"
            f"⚠️ Biggest Flaw: {result.get('biggest_flaw', 'N/A')}\n"
            f"🔥 Over-indexing: {result.get('over_indexing_issue', 'N/A')}\n"
            f"📍 Missed Positional: {result.get('missed_positional_pattern', 'N/A')}\n\n"
            f"<b>Recommended Starting Weights:</b>\n"
        )
        weights = result.get("recommended_weight_start", {})
        for k, v in weights.items():
            text += f"  • {k}: {v}\n"

        await thinking_msg.edit_text(text, parse_mode="HTML")

    except Exception as e:
        error_msg = mask_sensitive_data(str(e))
        logger.error(f"Diagnostic error: {error_msg}")
        await thinking_msg.edit_text(f"❌ Error: {error_msg}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command - show analytics."""
    user = update.effective_user
    user_id = str(user.id)
    logger.info(f"Stats requested by {user.username or user_id}")

    # Check rate limit
    allowed, reason = check_rate_limit(user_id, "stats")
    if not allowed:
        await update.message.reply_text(f"⏳ {reason}")
        return

    thinking_msg = await update.message.reply_text("📊 Analyzing statistics...")

    try:
        draws = get_combined_stats().get("total_draws", 0)
        if draws == 0:
            await thinking_msg.edit_text(
                "⚠️ No data available. Run /scrape first."
            )
            return

        report = generate_analytics_report(get_combined_stats().get("draws", []))

        # Format for Telegram (HTML)
        report = report.replace("📊", "<b>📊</b>")
        report = report.replace("🔥", "<b>🔥</b>")
        report = report.replace("❄️", "<b>❄️</b>")
        report = report.replace("📈", "<b>📈</b>")
        report = report.replace("🔗", "<b>🔗</b>")

        await thinking_msg.edit_text(report, parse_mode="HTML")

    except Exception as e:
        error_msg = mask_sensitive_data(str(e))
        logger.error(f"Stats error: {error_msg}")
        await thinking_msg.edit_text(f"❌ Error: {error_msg}")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history command - show prediction history."""
    user = update.effective_user
    user_id = str(user.id)
    logger.info(f"History requested by {user.username or user_id}")

    # Show performance summary
    summary = get_performance_summary()

    # Show recent predictions
    recent = format_prediction_history(limit=5)

    text = summary + "\n" + recent
    await update.message.reply_text(text)


async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /last command - show latest draw."""
    latest = get_latest_draw()

    if not latest:
        await update.message.reply_text(
            "⚠️ No draws in database. Run /scrape first."
        )
        return

    numbers = [latest[f"ball{i}"] for i in range(1, 7)]
    bonus = latest["bonus"]
    date = latest["draw_date"]
    time = latest["draw_time"]

    text = (
        f"🎯 <b>Latest UK49 Lunchtime Draw</b>\n\n"
        f"📅 Date: {date}\n"
        f"🕐 Time: {time}\n\n"
        f"🎱 Main Numbers:\n"
        f"   <b>{numbers[0]:02d} - {numbers[1]:02d} - {numbers[2]:02d} - "
        f"{numbers[3]:02d} - {numbers[4]:02d} - {numbers[5]:02d}</b>\n\n"
        f"⭐ Bonus: <b>{bonus:02d}</b>"
    )

    await update.message.reply_html(text)


async def scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scrape command - manually fetch latest result."""
    user = update.effective_user
    user_id = str(user.id)
    user_name = user.username or str(user.id)

    # Check if admin
    if not _is_admin(user.id):
        logger.warning(f"Unauthorized scrape attempt by {user_name} (ID: {user_id})")
        log_security_event(
            event="UNAUTHORIZED_SCRAPE_ATTEMPT",
            user_id=user_id,
            details=f"User {user_name} attempted to use /scrape without admin rights",
        )
        await update.message.reply_text("⛔ Admin only command.")
        return

    # Check rate limit
    allowed, reason = check_rate_limit(user_id, "scrape")
    if not allowed:
        await update.message.reply_text(f"⏳ {reason}")
        return

    thinking_msg = await update.message.reply_text("🔄 Scraping latest result...")

    try:
        result = scrape_latest_results()

        if result:
            numbers = result["numbers"]
            bonus = result["bonus"]
            date = result["draw_date"]

            text = (
                f"✅ <b>Latest Result Scraped!</b>\n\n"
                f"📅 {date}\n"
                f"🎱 Numbers: {numbers[0]:02d} - {numbers[1]:02d} - {numbers[2]:02d} - "
                f"{numbers[3]:02d} - {numbers[4]:02d} - {numbers[5]:02d}\n"
                f"⭐ Bonus: {bonus:02d}\n\n"
                f"Database updated. Total draws: {get_draw_count()}"
            )

            await thinking_msg.edit_text(text, parse_mode="HTML")

            # Log successful scrape
            log_scrape(
                user_id=user_id,
                user_name=user_name,
                success=True,
            )

            # Check accuracy against recent predictions
            check_and_update_accuracy()

        else:
            error_text = (
                "⚠️ <b>Scrape Failed</b>\n\n"
                "Possible reasons:\n"
                "• Website is temporarily down\n"
                "• Website structure changed\n"
                "• Network connection issue\n"
                "• No new results available yet\n\n"
                "Check Render logs for details or try again in a few minutes."
            )
            await thinking_msg.edit_text(error_text, parse_mode="HTML")

    except Exception as e:
        error_msg = mask_sensitive_data(str(e))
        logger.error(f"Scrape error: {error_msg}", exc_info=True)

        # Log failed scrape
        log_scrape(
            user_id=user_id,
            user_name=user_name,
            success=False,
            error=error_msg,
        )

        # Show more helpful error message
        error_text = (
            f"❌ <b>Scrape Error</b>\n\n"
            f"<code>{error_msg}</code>\n\n"
            f"Check Render logs for full details."
        )
        await thinking_msg.edit_text(error_text, parse_mode="HTML")


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to show system stats."""
    user = update.effective_user
    if not _is_admin(user.id):
        return

    draw_count = get_draw_count()
    latest = get_latest_draw()

    # Get key status (masked)
    from src.security import get_key_status
    key_status = get_key_status()

    text = (
        f"🔧 <b>System Stats</b>\n\n"
        f"📊 Total draws: {draw_count}\n"
        f"📅 Latest draw: {latest['draw_date'] if latest else 'None'}\n"
        f"🤖 Model: {key_status.get('LLM_MODEL', 'Not set')}\n"
        f"🔑 Telegram Token: {key_status.get('TELEGRAM_BOT_TOKEN', 'Not set')}\n"
        f"🔑 LLM API: {key_status.get('CUSTOM_LLM_API_KEY', 'Not set')}\n"
        f"👤 Admin IDs: {key_status.get('ADMIN_IDS', 'Not set')}\n"
    )

    await update.message.reply_html(text)


async def audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to show audit logs."""
    user = update.effective_user
    if not _is_admin(user.id):
        return

    from src.audit import get_audit_logger
    logger = get_audit_logger()
    stats = logger.get_stats()
    recent = logger.get_recent_logs(limit=10)

    text = (
        f"📋 <b>Audit Log</b>\n\n"
        f"📊 Total actions: {stats.get('total_actions', 0)}\n"
        f"✅ Successful: {stats.get('successful', 0)}\n"
        f"❌ Failed: {stats.get('failed', 0)}\n"
        f"👤 Unique users: {stats.get('unique_users', 0)}\n\n"
        f"<i>Recent activity logged in database</i>"
    )

    await update.message.reply_html(text)


# ========== ERROR HANDLER ==========

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors with sensitive data masking."""
    error_msg = str(context.error) if context.error else "Unknown error"
    masked_error = mask_sensitive_data(error_msg)

    logger.error(f"Update caused error: {masked_error}")

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ An error occurred. Please try again later."
        )


# ========== BOT SETUP ==========

def create_application() -> Application:
    """Create and configure the Telegram bot application."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    # Initialize database
    init_db()

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("predict", predict_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("last", last_command))
    application.add_handler(CommandHandler("scrape", scrape_command))
    application.add_handler(CommandHandler("admin", admin_stats_command))
    application.add_handler(CommandHandler("audit", audit_command))
    application.add_handler(CommandHandler("diagnostic", diagnostic_command))

    # Error handler
    application.add_error_handler(error_handler)

    return application


def start_bot():
    """Start the bot (polling mode) — for local development only.
    For production, use webhook mode via run.py.
    """
    logger.info("Starting Telegram bot with security measures...")
    application = create_application()
    application.run_polling(drop_pending_updates=True)
