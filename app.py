#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import sqlite3
import bcrypt
import secrets
from datetime import datetime, timedelta
import re
import requests
import threading
import time
from pathlib import Path

app = Flask(__name__, static_folder='.')
app.secret_key = secrets.token_hex(32)
app.config['JWT_SECRET_KEY'] = secrets.token_hex(32)
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

CORS(app, supports_credentials=True)
jwt = JWTManager(app)

MASTER_EMAIL = "danielxox052@gmail.com"
BOT_TOKEN = "8761142925:AAHUKHO4z4HKaXwicUGAk2OG2NAsplr6ea0"

env_path = Path.home() / "ai_assistant" / ".env"
keys = {}
if env_path.exists():
    with open(env_path, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                keys[k] = v
GROQ_API_KEY = keys.get("GROQ_API_KEY")

DB_PATH = '/data/data/com.termux/files/home/bitassistant/users.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, email TEXT UNIQUE, password TEXT,
        plan TEXT DEFAULT 'free', daily_limit INTEGER DEFAULT 50,
        usage_count INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, role TEXT, content TEXT, image_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, date DATE DEFAULT CURRENT_DATE, requests INTEGER DEFAULT 0,
        UNIQUE(user_id, date)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS telegram_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, chat_id TEXT,
        username TEXT, first_name TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    print("✅ Database ready")

init_db()

def hash_password(pw): return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
def verify_password(pw, h): return bcrypt.checkpw(pw.encode(), h.encode())
def get_user_by_email(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name, email, password, plan, daily_limit, usage_count FROM users WHERE email = ?', (email.lower(),))
    user = c.fetchone()
    conn.close()
    return user

def get_user_by_id(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name, email, plan, daily_limit, usage_count FROM users WHERE id = ?', (uid,))
    user = c.fetchone()
    conn.close()
    return user

def update_usage(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO daily_usage (user_id, date, requests) VALUES (?, CURRENT_DATE, 1) ON CONFLICT(user_id, date) DO UPDATE SET requests = requests + 1', (uid,))
    c.execute('UPDATE users SET usage_count = usage_count + 1 WHERE id = ?', (uid,))
    conn.commit()
    conn.close()

def save_conversation(uid, role, content, image_url=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO conversations (user_id, role, content, image_url) VALUES (?, ?, ?, ?)', (uid, role, content, image_url))
    conn.commit()
    conn.close()

def get_chat_history(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT role, content, image_url FROM conversations WHERE user_id = ? ORDER BY created_at ASC LIMIT 50', (uid,))
    history = c.fetchall()
    conn.close()
    return history

def clear_chat_history(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM conversations WHERE user_id = ?', (uid,))
    conn.commit()
    conn.close()

def generate_image(prompt):
    """Generate image using Pollinations.ai"""
    try:
        encoded = requests.utils.quote(prompt[:100])
        return f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&nologo=true"
    except:
        return None

def get_time(): return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

def call_groq(user_msg, is_master=False):
    if not GROQ_API_KEY:
        return "⚠️ API key missing"
    
    # IMAGE GENERATION - detect "generate"
    if "generate" in user_msg.lower():
        prompt = re.sub(r'^(generate|generate an|generate a|generate image of|create|make|draw)\s+', '', user_msg.lower()).strip()
        if not prompt or len(prompt) < 2:
            prompt = "beautiful scenery"
        img_url = generate_image(prompt)
        if img_url:
            return f"IMAGE:{img_url}"
        return "Sorry, couldn't generate that image."
    
    if "time" in user_msg.lower():
        return get_time()
    
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": user_msg}],
        "max_tokens": 150
    }
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return "Error"
    except:
        return "Error"

# ============ API ============
@app.route('/')
def index(): return send_from_directory('.', 'index.html')
@app.route('/<path:path>')
def serve(path): return send_from_directory('.', path)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name, email, password = data.get('name'), data.get('email', '').lower(), data.get('password')
    if not name or not email or not password or len(password) < 6:
        return jsonify({'error': 'Invalid data'}), 400
    if get_user_by_email(email):
        return jsonify({'error': 'Email exists'}), 400
    hashed = hash_password(password)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, hashed))
    uid = c.lastrowid
    conn.commit()
    conn.close()
    token = create_access_token(identity=str(uid))
    return jsonify({'success': True, 'access_token': token, 'user': {'id': uid, 'name': name, 'email': email, 'plan': 'free'}})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email, password = data.get('email', '').lower(), data.get('password')
    user = get_user_by_email(email)
    if not user or not verify_password(password, user[3]):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = create_access_token(identity=str(user[0]))
    return jsonify({'success': True, 'access_token': token, 'user': {'id': user[0], 'name': user[1], 'email': user[2], 'plan': user[4]}})

@app.route('/api/profile', methods=['GET'])
@jwt_required()
def profile():
    uid = get_jwt_identity()
    user = get_user_by_id(uid)
    if not user:
        return jsonify({'error': 'Not found'}), 404
    is_master = (user[2] == MASTER_EMAIL)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT requests FROM daily_usage WHERE user_id = ? AND date = CURRENT_DATE', (uid,))
    daily = c.fetchone()
    conn.close()
    return jsonify({'user': {
        'id': user[0], 'name': user[1], 'email': user[2],
        'plan': 'master' if is_master else user[3],
        'daily_limit': 999999 if is_master else user[4],
        'total_usage': user[5] or 0,
        'daily_usage': daily[0] if daily else 0,
        'is_master': is_master
    }})

@app.route('/api/history', methods=['GET'])
@jwt_required()
def history():
    uid = get_jwt_identity()
    history = get_chat_history(uid)
    return jsonify({'history': [{'role': h[0], 'content': h[1], 'image_url': h[2]} for h in history]})

@app.route('/api/clear_history', methods=['POST'])
@jwt_required()
def clear_hist():
    uid = get_jwt_identity()
    clear_chat_history(uid)
    return jsonify({'success': True})

@app.route('/api/chat', methods=['POST'])
@jwt_required()
def chat():
    uid = get_jwt_identity()
    data = request.json
    msg = data.get('message', '')
    if not msg:
        return jsonify({'error': 'Message required'}), 400
    
    user = get_user_by_id(uid)
    is_master = (user[2] == MASTER_EMAIL)
    
    if not is_master:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT requests FROM daily_usage WHERE user_id = ? AND date = CURRENT_DATE', (uid,))
        daily = c.fetchone()
        conn.close()
        if daily and daily[0] >= 50:
            return jsonify({'response': '⚠️ Daily limit reached (50). Upgrade to Pro!'})
    
    save_conversation(uid, 'user', msg)
    resp = call_groq(msg, is_master)
    
    img_url = None
    if resp.startswith('IMAGE:'):
        img_url = resp.replace('IMAGE:', '')
        resp = "🎨 Here's your generated image:"
    
    save_conversation(uid, 'assistant', resp, img_url)
    
    if not is_master:
        update_usage(uid)
    
    if img_url:
        return jsonify({'response': resp, 'image_url': img_url})
    return jsonify({'response': resp})

@app.route('/api/create_invoice', methods=['POST'])
@jwt_required()
def invoice():
    uid = get_jwt_identity()
    plan = request.json.get('plan')
    stars = {'monthly': 500, 'yearly': 5000, 'lifetime': 10000}.get(plan, 500)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT chat_id FROM telegram_users WHERE user_id = ?', (uid,))
    res = c.fetchone()
    conn.close()
    if not res:
        return jsonify({'error': 'Message @MyVA1550_bot first'}), 400
    payload = {
        "chat_id": res[0],
        "title": f"BitAssistant {plan.capitalize()}",
        "description": "Unlimited messages + images + web search",
        "payload": f'{{"plan":"{plan}","user_id":"{uid}"}}',
        "currency": "XTR",
        "prices": [{"label": f"{plan.capitalize()} Subscription", "amount": stars}],
        "start_parameter": f"bitassistant_{plan}"
    }
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice", json=payload)
        if r.json().get('ok'):
            return jsonify({'success': True, 'message': 'Invoice sent!'})
        return jsonify({'error': 'Failed'}), 400
    except:
        return jsonify({'error': 'Error'}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 BitAssistant Server")
    print("=" * 50)
    print(f"📍 http://127.0.0.1:5000")
    print("👑 Master: danielxox052@gmail.com (unlimited)")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
