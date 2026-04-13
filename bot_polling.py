#!/usr/bin/env python3
"""
Telegram Bot Polling - Captures user chat IDs and handles payments
"""

import requests
import time
import json
import sqlite3
from datetime import datetime

BOT_TOKEN = "8761142925:AAHUKHO4z4HKaXwicUGAk2OG2NAsplr6ea0"
LAST_UPDATE = 0

# Database to store user chat IDs
DB_PATH = '/data/data/com.termux/files/home/bitassistant/users.db'

def init_chat_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS telegram_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            chat_id TEXT,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Telegram users table initialized")

def save_chat_id(user_id, chat_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO telegram_users (user_id, chat_id, username, first_name)
        VALUES (?, ?, ?, ?)
    ''', (user_id, chat_id, username, first_name))
    conn.commit()
    conn.close()
    print(f"✅ Saved chat_id {chat_id} for user {user_id}")

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending message: {e}")

def send_invoice(chat_id, plan, stars):
    """Send payment invoice to user"""
    title = f"BitAssistant {plan.capitalize()} Plan"
    description = f"Unlock unlimited messages and premium features for {plan}"
    payload = json.dumps({"plan": plan})
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice"
    data = {
        "chat_id": chat_id,
        "title": title,
        "description": description,
        "payload": payload,
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": f"{plan.capitalize()} Subscription", "amount": stars}],
        "start_parameter": f"bitassistant_{plan}",
        "need_email": True,
        "need_name": True
    }
    
    try:
        response = requests.post(url, json=data)
        result = response.json()
        if result.get("ok"):
            send_message(chat_id, f"✅ Payment invoice sent! Please complete the payment.")
            return True
        else:
            send_message(chat_id, f"❌ Failed to create invoice: {result.get('description', 'Unknown error')}")
            return False
    except Exception as e:
        send_message(chat_id, f"❌ Error: {e}")
        return False

def handle_pre_checkout_query(pre_checkout_query_id):
    """Confirm payment is valid"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery"
    data = {
        "pre_checkout_query_id": pre_checkout_query_id,
        "ok": True
    }
    requests.post(url, json=data)

def handle_successful_payment(chat_id, payload, telegram_payment_charge_id):
    """Handle successful payment"""
    try:
        payment_data = json.loads(payload)
        plan = payment_data.get("plan")
        
        # Update user's plan in database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get user by chat_id
        c.execute("SELECT user_id FROM telegram_users WHERE chat_id = ?", (chat_id,))
        result = c.fetchone()
        
        if result:
            user_id = result[0]
            # Update user plan (you'll need to link this to your users table)
            # For now, just confirm
            send_message(chat_id, f"✅ Payment successful! Your {plan} plan is now active. Thank you for upgrading!")
        else:
            send_message(chat_id, f"✅ Payment received for {plan} plan! Please login to activate your premium features.")
            
        conn.close()
        
    except Exception as e:
        print(f"Payment handling error: {e}")
        send_message(chat_id, "❌ Payment processing error. Please contact support.")

def check_updates():
    global LAST_UPDATE
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        params = {"offset": LAST_UPDATE + 1, "timeout": 25}
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        
        if data.get("ok") and data.get("result"):
            for update in data["result"]:
                LAST_UPDATE = update["update_id"]
                
                # Handle message updates
                if "message" in update:
                    msg = update["message"]
                    chat_id = msg.get("chat", {}).get("id")
                    user_id = msg.get("from", {}).get("id")
                    username = msg.get("from", {}).get("username", "")
                    first_name = msg.get("from", {}).get("first_name", "")
                    text = msg.get("text", "")
                    
                    # Save user info
                    save_chat_id(str(user_id), str(chat_id), username, first_name)
                    
                    # Handle commands
                    if text == "/start":
                        send_message(chat_id, 
                            "🤖 *BitAssistant Bot*\n\n"
                            "Welcome! I'll help you manage your subscription.\n\n"
                            "📋 *Commands:*\n"
                            "/start - Show this menu\n"
                            "/plan - View your current plan\n"
                            "/upgrade - Upgrade to premium\n"
                            "/help - Get help\n\n"
                            "💡 Your chat ID has been saved. You can now upgrade from the web dashboard!",
                            parse_mode="Markdown"
                        )
                    
                    elif text == "/plan":
                        send_message(chat_id, "📊 *Your Plan: Free*\n\n50 messages/day\nUpgrade for unlimited access!", parse_mode="Markdown")
                    
                    elif text == "/upgrade":
                        send_message(chat_id, "🔗 Please visit our web dashboard to upgrade: https://bitassistant.com/upgrade")
                    
                    elif text == "/help":
                        send_message(chat_id, "Need help? Contact support at support@bitassistant.com")
                
                # Handle pre-checkout query (payment confirmation)
                if "pre_checkout_query" in update:
                    query = update["pre_checkout_query"]
                    handle_pre_checkout_query(query["id"])
                
                # Handle successful payment
                if "message" in update and "successful_payment" in update["message"]:
                    msg = update["message"]
                    chat_id = msg["chat"]["id"]
                    payment = msg["successful_payment"]
                    handle_successful_payment(chat_id, payment["invoice_payload"], payment["telegram_payment_charge_id"])
                    
    except Exception as e:
        print(f"Error: {e}")

def main():
    print("=" * 50)
    print("🤖 BitAssistant Bot Polling Service")
    print("=" * 50)
    print(f"Bot Token: {BOT_TOKEN[:15]}...")
    print("=" * 50)
    
    init_chat_db()
    
    print("\n✅ Bot polling started! Send /start to @MyVA1550_bot")
    print("💡 Press Ctrl+C to stop\n")
    
    while True:
        try:
            check_updates()
        except KeyboardInterrupt:
            print("\n👋 Stopping...")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
        time.sleep(1)

if __name__ == "__main__":
    main()
