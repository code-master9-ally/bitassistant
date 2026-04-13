import requests
import json

BOT_TOKEN = "8761142925:AAHUKHO4z4HKaXwicUGAk2OG2NAsplr6ea0"
CHAT_ID = "8488759436"

# Test invoice with correct format
payload = {
    "chat_id": CHAT_ID,
    "title": "BitAssistant Monthly Plan",
    "description": "Unlock unlimited AI messages for 30 days",
    "payload": json.dumps({"plan": "monthly", "user_id": "1"}),
    "provider_token": "",  # Empty for Stars
    "currency": "XTR",     # Stars currency
    "prices": [{"label": "Monthly Subscription", "amount": 500}],
    "start_parameter": "bitassistant_sub",
    "need_name": True,
    "need_email": True
}

print("Sending test invoice...")
response = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice", json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
