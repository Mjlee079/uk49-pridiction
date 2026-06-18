import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('CUSTOM_LLM_API_KEY')
base_url = os.getenv('CUSTOM_LLM_BASE_URL')
endpoint = base_url + '/messages'

headers = {
    'x-api-key': api_key,
    'Content-Type': 'application/json'
}

data = {
    'model': 'qwen3.7-plus',
    'max_tokens': 100,
    'messages': [{'role': 'user', 'content': 'Say hello'}]
}

response = requests.post(endpoint, headers=headers, json=data, timeout=10)
result = response.json()

print('Number of content items:', len(result['content']))
for i, item in enumerate(result['content']):
    print('Item', i)
    print('  type:', item.get('type', 'unknown'))
    print('  keys:', list(item.keys()))
    if 'text' in item:
        print('  text:', item['text'][:100])
    if 'thinking' in item:
        print('  thinking:', item['thinking'][:100])
