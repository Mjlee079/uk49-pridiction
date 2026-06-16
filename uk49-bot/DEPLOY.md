# UK49 Lunchtime AI Prediction Bot — Render Deployment Guide

This guide covers deploying the bot to **Render.com free tier** with **PostgreSQL** (persistent storage) and **Telegram webhook mode**.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Variables](#environment-variables)
3. [Step 1: Push Code to GitHub](#step-1-push-code-to-github)
4. [Step 2: Create PostgreSQL on Render](#step-2-create-postgresql-on-render)
5. [Step 3: Create Web Service](#step-3-create-web-service)
6. [Step 4: Set Environment Variables](#step-4-set-environment-variables)
7. [Step 5: Deploy](#step-5-deploy)
8. [Step 6: Migrate Data (Optional)](#step-6-migrate-data-optional)
9. [Step 7: Set Telegram Webhook](#step-7-set-telegram-webhook)
10. [Step 8: Set Up Better Stack Monitoring](#step-8-set-up-better-stack-monitoring)
11. [Commands Reference](#commands-reference)
12. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- A **GitHub** account
- A **Render.com** account (free tier)
- A **Telegram** account
- API keys (see below)
- A **Better Stack** account (free tier) — for monitoring/keep-alive

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | **Auto** | Render auto-generates when you link PostgreSQL |
| `TELEGRAM_BOT_TOKEN` | **Yes** | Your Telegram bot token from @BotFather |
| `WEBHOOK_URL` | **Yes** | Your Render app URL (e.g., `https://uk49-bot.onrender.com`) |
| `GROQ_API_KEY` | **Yes** | Free from https://console.groq.com |
| `LLM_MODEL` | No | Default: `qwen/qwen3-32b` |
| `ADMIN_IDS` | No | Your Telegram user ID (comma-separated) |
| `DRAW_TIMEZONE` | No | Default: `Europe/London` |
| `DRAW_TIME` | No | Default: `12:49` |
| `PORT` | **Auto** | Render provides this (Flask binds to it) |

---

## Step 1: Push Code to GitHub

```bash
# Make sure your code is committed
git add .
git commit -m "chore: production-ready for Render (PostgreSQL, webhook, monitoring)"
git push origin main
```

---

## Step 2: Create PostgreSQL on Render

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"PostgreSQL"**
3. **Name:** `uk49-db`
4. **Plan:** Free
5. Click **"Create Database"**
6. Wait for it to be ready (green status)

---

## Step 3: Create Web Service

1. Click **"New +"** → **"Web Service"**
2. Connect your **GitHub repository**
3. **Settings:**
   - **Name:** `uk49-lunchtime-bot` (or your choice)
   - **Region:** Pick closest to your users
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python run.py`
   - **Plan:** Free
4. Click **"Create Web Service"**

**Important:** Before the first deploy completes, link the PostgreSQL:
- Go to your Web Service → **"Settings"**
- Under **"Database"**, click **"Connect Database"**
- Select the `uk49-db` you created
- This auto-populates `DATABASE_URL`

---

## Step 4: Set Environment Variables

Go to your Web Service → **"Environment"** tab and add:

```
TELEGRAM_BOT_TOKEN=your_token_here
WEBHOOK_URL=https://your-app-name.onrender.com
GROQ_API_KEY=your_groq_key_here
LLM_MODEL=qwen/qwen3-32b
ADMIN_IDS=your_telegram_user_id
```

**Note:** Replace `your-app-name` with your actual Render app name. You can get this after the first deploy.

If you need to update `WEBHOOK_URL` after the first deploy:
1. Deploy once (it will fail webhook setup, that's OK)
2. Get the URL from the Render dashboard
3. Set `WEBHOOK_URL` to that URL
4. Redeploy

---

## Step 5: Deploy

Render will auto-deploy after you set env vars. Check the **Logs** tab for:

```
✅ Database initialized successfully (PostgreSQL)
✅ Starting Flask server on port 10000...
✅ Webhook set successfully
```

If you see `WEBHOOK_URL not set`, set it and redeploy.

---

## Step 6: Migrate Data (Optional)

If you have existing SQLite data locally and want to migrate it:

### Option A: Run from Render Shell
1. Go to your Web Service → **"Shell"** tab
2. Upload your `data/uk49_lunchtime.db` and `data/state.json` files (use the shell's upload feature or `scp`)
3. Run:
```bash
python migrate_to_postgres.py
```

### Option B: Run Locally
1. Set your Render `DATABASE_URL` locally:
```bash
export DATABASE_URL=postgresql://user:pass@host:5432/dbname
```
2. Run the migration script:
```bash
python migrate_to_postgres.py
```

---

## Step 7: Set Telegram Webhook

The app auto-sets the webhook on startup if `WEBHOOK_URL` is set.

**To verify:**
- Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo`
- You should see your Render URL in the `url` field

**To manually set (if needed):**
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-app-name.onrender.com/webhook"}'
```

---

## Step 8: Set Up Better Stack Monitoring

**Better Stack** (free tier) keeps your Render service alive and alerts you if it goes down.

1. Go to https://betterstack.com
2. Sign up for a free account
3. Go to **"Monitors"** → **"Create Monitor"**
4. **Settings:**
   - **Name:** UK49 Bot Health
   - **URL:** `https://your-app-name.onrender.com/health`
   - **Check Interval:** 10 minutes
   - **Expected Status Code:** 200
5. Click **"Create Monitor"**

This pings your `/health` endpoint every 10 minutes, keeping the Render service awake.

---

## Commands Reference

| Command | Description | Who Can Use |
|---------|-------------|-------------|
| `/start` | Welcome message | Everyone |
| `/help` | Show commands | Everyone |
| `/predict` | Get 10 AI predictions | Everyone |
| `/stats` | View hot/cold numbers | Everyone |
| `/history` | Prediction accuracy | Everyone |
| `/last` | Latest draw result | Everyone |
| `/scrape` | Manual result fetch | Admin only |
| `/admin` | System stats | Admin only |

---

## Troubleshooting

### "Database not initialized"
- Check Render logs for PostgreSQL connection errors
- Verify `DATABASE_URL` is set correctly
- Ensure the PostgreSQL instance is linked to the Web Service

### "Webhook not set"
- Check that `WEBHOOK_URL` is set to your exact Render app URL
- Redeploy after setting the env var
- Verify with `getWebhookInfo` (see Step 7)

### Bot not responding
- Check Render logs for errors
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Test `/health` in browser: `https://your-app.onrender.com/health`

### Service goes to sleep
- Ensure Better Stack monitor is active (Step 8)
- Check monitor logs in Better Stack dashboard
- Render free tier sleeps after 15 min idle — pings prevent this

### "No data in database"
- The bot auto-scrapes on startup if empty
- Or run `/scrape` (admin command) after the first deploy
- Or migrate existing SQLite data (Step 6)

---

## Security

- ✅ **Never commit `.env`** — it's in `.gitignore`
- ✅ **Never share API keys** — keep them in Render env vars only
- ✅ **Restrict admin commands** — only your Telegram ID can run `/scrape`
- ✅ **Use Render Secret Files** — for additional sensitive data if needed

---

## Updating the Bot

```bash
# Make changes locally
git add .
git commit -m "Update: description"
git push origin main

# Render auto-deploys!
```

---

## Support

If issues persist:
1. Check Render logs
2. Verify all env vars are set
3. Test `/health` endpoint in browser
4. Check Better Stack monitor status

**Good luck with your predictions!**
