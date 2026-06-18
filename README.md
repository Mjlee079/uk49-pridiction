# UK49 Lunchtime AI Prediction Bot

An AI-powered Telegram bot that predicts UK49 Lunchtime lottery numbers using advanced analytics and Qwen AI models.

## Features

- 🤖 AI-powered predictions using Qwen models
- 📊 Statistical analysis (frequencies, gaps, co-occurrences, trends)
- 🧠 Self-learning from historical accuracy
- 🔒 Secure API key handling
- ☁️ Cloud-ready deployment

## Quick Start

1. Clone and setup:
```bash
git clone <repo-url>
cd uk49-pridiction
pip install -r requirements.txt
cp .env.example .env
```

2. Configure `.env` with your API keys

3. Run:
```bash
python run.py
```

## Commands

- `/predict` - Get 10 AI predictions
- `/stats` - View analytics
- `/history` - Prediction accuracy
- `/last` - Latest draw result

## Deployment

See [DEPLOY.md](DEPLOY.md) for full deployment guide.

## Security

- API keys stored in environment variables only
- Never commit `.env` file
- Admin-only commands restricted by Telegram user ID
