import os
import sqlite3
import bcrypt
import secrets
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity

app = Flask(__name__, static_folder='.')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', secrets.token_hex(32))
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

CORS(app, supports_credentials=True)
jwt = JWTManager(app)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
BOT_TOKEN = os.environ.get('BOT_TOKEN', "8761142925:AAHUKHO4z4HKaXwicUGAk2OG2NAsplr6ea0")
MASTER_EMAIL = os.environ.get('MASTER_EMAIL', "danielxox052@gmail.com")

DB_PATH = '/tmp/users.db'

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
    conn.commit()
    conn.close()

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
    try:
        encoded = requests.utils.quote(prompt[:100])
        return f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&nologo=true"
    except:
        return None

def call_groq(msg):
    if not GROQ_API_KEY:
        return "⚠️ API key missing"
    if "generate" in msg.lower():
        prompt = msg.lower().replace("generate", "").replace("an", "").replace("a", "").strip()
        img = generate_image(prompt)
        if img:
            return f"IMAGE:{img}"
        return "Sorry, couldn't generate that."
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": msg}], "max_tokens": 150}
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return "Error"
    except:
        return "Error"

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
    return jsonify({'user': {'id': user[0], 'name': user[1], 'email': user[2], 'plan': 'master' if is_master else user[3], 'daily_limit': 999999 if is_master else user[4], 'total_usage': user[5] or 0, 'is_master': is_master}})

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
    msg = request.json.get('message', '')
    if not msg:
        return jsonify({'error': 'Message required'}), 400
    save_conversation(uid, 'user', msg)
    resp = call_groq(msg)
    img = None
    if resp.startswith('IMAGE:'):
        img = resp.replace('IMAGE:', '')
        resp = "🎨 Here's your generated image:"
    save_conversation(uid, 'assistant', resp, img)
    if img:
        return jsonify({'response': resp, 'image_url': img})
    return jsonify({'response': resp})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
