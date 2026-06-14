import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Get bot info
token = os.getenv('TELEGRAM_BOT_TOKEN')

if token:
    url = f'https://api.telegram.org/bot{token}/getMe'
    try:
        response = requests.get(url, timeout=10)
        bot_data = response.json()
        
        if bot_data.get('ok'):
            bot = bot_data['result']
            username = bot['username']
            name = bot['first_name']
            bot_id = bot['id']
            
            print('Bot username: @' + username)
            print('Bot name: ' + name)
            print('Bot ID: ' + str(bot_id))
            print()
            print('Bot is RUNNING and polling for messages!')
            print()
            print('Please send /start to @' + username)
            print('If you already did, wait 10 seconds and try again')
            print()
            print('If still not working:')
            print('1. Restart Telegram app')
            print('2. Delete chat and start new one')
            print('3. Check if bot is blocked')
        else:
            print('Bot error:', bot_data.get('description'))
    except Exception as e:
        print('Error:', e)
