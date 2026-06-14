# UK49 Lunchtime AI Prediction Bot - Deployment Guide

This guide walks you through deploying your UK49 Lunchtime Prediction Bot to the cloud for free.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Local Setup & Testing](#local-setup--testing)
3. [Cloud Deployment (Render.com - FREE)](#cloud-deployment-rendercom---free)
4. [Telegram Bot Setup](#telegram-bot-setup)
5. [API Keys Setup](#api-keys-setup)
6. [Environment Variables](#environment-variables)
7. [Monitoring & Logs](#monitoring--logs)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before you start, you'll need:
- A GitHub account (free)
- A Render.com account (free tier)
- A Telegram account
- API keys (see below)

---

## Local Setup & Testing

### Step 1: Clone and Setup

```bash
# Clone your repository (or create it)
git clone <your-repo-url>
cd uk49-bot

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your API keys (see section below)
```

### Step 3: Run Initial Scrape

```bash
python -c "from src.database import init_db; init_db()"
python -c "from src.scraper import run_full_scrape; run_full_scrape()"
```

### Step 4: Test the Bot Locally

```bash
python run.py
```

You should see:
- Database initialization message
- Historical scrape results
- Scheduler starting
- "Starting Telegram bot..." message

---

## Cloud Deployment (Render.com - FREE)

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit: UK49 Lunchtime Bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/uk49-bot.git
git push -u origin main
```

### Step 2: Create Render Account

1. Go to https://render.com
2. Sign up with GitHub
3. Click "New +" → "Web Service"
4. Connect your GitHub repository

### Step 3: Configure Render Service

**Settings:**
- **Name:** uk49-lunchtime-bot
- **Region:** Frankfurt (EU) or closest to you
- **Branch:** main
- **Runtime:** Python 3
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python run.py`
- **Plan:** Free

**Environment Variables:**
Click "Environment" tab and add:

```
TELEGRAM_BOT_TOKEN=your_token_here
GROQ_API_KEY=your_groq_key_here
CUSTOM_LLM_API_KEY=your_qwen_key_here  # Optional - your own Qwen API
CUSTOM_LLM_BASE_URL=https://your-api-url.com/v1  # Optional
RAPIDAPI_KEY=your_rapidapi_key_here  # Optional
DATABASE_URL=data/uk49_lunchtime.db
LLM_MODEL=qwen/qwen3-32b
LOG_LEVEL=INFO
```

### Step 4: Deploy

Click "Create Web Service"
Render will:
1. Build the Docker image
2. Install dependencies
3. Start the bot

**Note:** Free tier spins down after 15 minutes of inactivity. The scheduler keeps it alive during the day.

### Step 5: Keep Alive (IMPORTANT)

Free web services sleep after 15 min. To keep your bot alive 24/7:

**Option A: Use UptimeRobot (FREE)**
1. Go to https://uptimerobot.com
2. Add monitor → HTTP(s)
3. URL: `https://your-render-url.onrender.com/health`
4. Interval: 5 minutes
5. This pings your service to keep it awake

**Option B: Use Cron-Job.org (FREE)**
1. Go to https://cron-job.org
2. Create job to ping your Render URL every 10 minutes

---

## Telegram Bot Setup

### Step 1: Create Bot with BotFather

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Name your bot (e.g., "UK49 Predictor")
4. Choose username (e.g., `uk49_lunchtime_bot`)
5. **Copy the token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Configure

Paste the token in your `.env` file:
```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

### Step 3: Find Your User ID (for Admin)

1. Search for **@userinfobot** in Telegram
2. Start the bot
3. It will reply with your user ID (e.g., `123456789`)
4. Add to `.env`:
```
ADMIN_IDS=123456789
```

---

## API Keys Setup

### Option 1: Groq API (FREE - Recommended)

1. Go to https://console.groq.com
2. Sign up with email/GitHub
3. Go to "API Keys"
4. Create new key
5. **Copy the key**
6. Paste in `.env`:
```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Groq Free Tier Limits:**
- 300,000 tokens per minute
- 1,000 requests per minute
- More than enough for this bot

### Option 2: Your Own Qwen API (if you have one)

If you have a Qwen API key from DashScope/Alibaba:

```bash
CUSTOM_LLM_API_KEY=your-qwen-api-key-here
CUSTOM_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-turbo  # or qwen-plus, qwen-max
```

### Option 3: RapidAPI (Optional - for live results)

1. Go to https://rapidapi.com
2. Sign up for free
3. Search for "UK Lottery" or "49s"
4. Subscribe to a free plan
5. Copy your API key from dashboard
6. Paste in `.env`:
```
RAPIDAPI_KEY=your-rapidapi-key-here
```

**Note:** The bot can work without RapidAPI by scraping bet49s.com directly.

---

## Environment Variables

Complete list of all environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | **YES** | Your Telegram bot token from @BotFather |
| `GROQ_API_KEY` | *Optional* | Free Groq API key for Qwen AI |
| `CUSTOM_LLM_API_KEY` | *Optional* | Your own Qwen/DashScope API key |
| `CUSTOM_LLM_BASE_URL` | *Optional* | Base URL for custom LLM API |
| `RAPIDAPI_KEY` | *Optional* | RapidAPI key for live results |
| `DATABASE_URL` | No | SQLite path (default: `data/uk49_lunchtime.db`) |
| `LLM_MODEL` | No | Model ID (default: `qwen/qwen3-32b`) |
| `ADMIN_IDS` | No | Comma-separated Telegram user IDs |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

---

## Monitoring & Logs

### View Logs on Render

1. Go to your service on Render dashboard
2. Click "Logs" tab
3. See real-time bot activity

### Common Log Messages

```
✅ "Database initialized successfully"
✅ "Scraped X new Lunchtime draws"
✅ "Prediction X saved for YYYY-MM-DD"
✅ "Accuracy updated for prediction X: Y/3 (Z%)"
```

### Health Check

Add this endpoint to `src/bot.py` if using a web service with health checks:

```python
from flask import Flask
app = Flask(__name__)

@app.route('/health')
def health():
    return {'status': 'ok', 'draws': get_draw_count()}
```

---

## Troubleshooting

### Bot Not Responding in Telegram

**Problem:** Bot doesn't reply to commands
**Solution:**
1. Check Render logs for errors
2. Verify `TELEGRAM_BOT_TOKEN` is correct
3. Make sure you sent `/start` first
4. Check if bot is blocked

### "No LLM API configured" Error

**Problem:** Predictions fail
**Solution:**
1. Get free Groq API key: https://console.groq.com
2. Add `GROQ_API_KEY` to environment variables
3. Redeploy

### "No data in database" Error

**Problem:** /predict or /stats shows no data
**Solution:**
1. Run `/scrape` command (admin only)
2. Or wait for scheduler to run at 12:55 UK time
3. Check Render logs for scraper errors

### Service Goes to Sleep

**Problem:** Bot stops responding after 15 minutes
**Solution:**
1. Set up UptimeRobot: https://uptimerobot.com
2. Ping your Render URL every 5 minutes
3. Or upgrade to Render paid plan ($7/month)

### Scraping Errors

**Problem:** bet49s.com blocks scraping
**Solution:**
1. The bot uses realistic User-Agent headers
2. If blocked, increase delay between requests
3. Consider using a proxy service

---

## Security Best Practices

1. ✅ **Never commit `.env` file** - It's in `.gitignore`
2. ✅ **Never share API keys** - Keep them in environment variables only
3. ✅ **Use Render Secret Files** - For production, use Render's secret file feature
4. ✅ **Restrict Admin Commands** - Only your Telegram user ID can run /scrape
5. ✅ **Enable Render Private Services** - If you don't need public URL

---

## Updating the Bot

To update after code changes:

```bash
# Make changes locally
git add .
git commit -m "Update: description"
git push origin main

# Render will auto-deploy!
```

---

## Commands Reference

| Command | Description | Who Can Use |
|---------|-------------|-------------|
| `/start` | Welcome message | Everyone |
| `/help` | Show commands | Everyone |
| `/predict` | Get 10 AI predictions | Everyone |
| `/stats` | View analytics | Everyone |
| `/history` | Prediction accuracy | Everyone |
| `/last` | Latest draw result | Everyone |
| `/scrape` | Manual result fetch | Admin only |
| `/admin` | System stats | Admin only |

---

## Support

If you encounter issues:
1. Check Render logs first
2. Verify all API keys are correct
3. Make sure `.env` variables are set
4. Check that database initialized properly

**Good luck with your predictions! 🎱**
