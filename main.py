import psycopg2
import os
import json
import uvicorn
import hashlib
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

DB_URI = "postgresql://neondb_owner:npg_bYj1tnSH8XBg@ep-billowing-pine-ahbzqlq1-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

def get_hash(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
            coins DOUBLE PRECISION DEFAULT 0, tap_power DOUBLE PRECISION DEFAULT 1,
            multiplier DOUBLE PRECISION DEFAULT 1, prestige INTEGER DEFAULT 0,
            grand INTEGER DEFAULT 0, c_prest_current DOUBLE PRECISION DEFAULT 100000,
            shop_data TEXT DEFAULT '[]', last_active BIGINT,
            pending_coins DOUBLE PRECISION DEFAULT 0
        )
    ''')
    try: cursor.execute("ALTER TABLE users ADD COLUMN pending_coins DOUBLE PRECISION DEFAULT 0")
    except: conn.rollback()
    conn.commit()
    cursor.close()
    conn.close()

init_db()

current_dir = os.path.dirname(os.path.realpath(__file__))
if os.path.exists(os.path.join(current_dir, "images")):
    app.mount("/images", StaticFiles(directory=os.path.join(current_dir, "images")), name="images")

@app.get("/")
async def read_index(): return FileResponse('index.html')

@app.post("/api/register")
async def register(request: Request):
    try:
        data = await request.json()
        name = data['username'].strip().lower()
        pw = get_hash(data['password'])
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, password_hash, last_active) VALUES (%s, %s, %s)', (name, pw, int(time.time())))
        conn.commit()
        return {"status": "success"}
    except: return {"status": "error", "message": "Ник занят"}

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    name = data['username'].strip().lower()
    pw = get_hash(data['password'])
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    cursor.execute('SELECT username, coins, tap_power, multiplier, prestige, grand, c_prest_current, shop_data, last_active, pending_coins FROM users WHERE username = %s AND password_hash = %s', (name, pw))
    row = cursor.fetchone()
    if row:
        now = int(time.time())
        # При входе суммируем основной баланс + АФК + то, что выдал админ
        pending = row[9] if row[9] else 0
        afk = ((row[2] * row[3] * min(now - (row[8] or now), 36000)) / 5)
        total_coins = row[1] + afk + pending
        
        # Обнуляем pending после зачисления
        cursor.execute('UPDATE users SET last_active = %s, pending_coins = 0, coins = %s WHERE username = %s', (now, total_coins, name))
        conn.commit()
        return {
            "status": "success",
            "afk": {"coins": afk + pending, "seconds": min(now - (row[8] or now), 36000)},
            "data": { "username": row[0], "coins": total_coins, "tapPower": row[2], "multiplier": row[3], "prestige": row[4], "grand": row[5], "c_prest_current": row[6], "shop": json.loads(row[7]) }
        }
    return {"status": "error", "message": "Ошибка"}

@app.post("/api/save")
async def save_game(request: Request):
    data = await request.json()
    name = data['username']
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    
    # 1. Проверяем, нет ли "подарков" от админа в pending_coins
    cursor.execute('SELECT pending_coins FROM users WHERE username = %s', (name,))
    row = cursor.fetchone()
    pending = row[0] if row and row[0] else 0
    
    # 2. Суммируем то, что прислал клиент + то, что выдал админ
    new_balance = float(data['coins']) + pending
    
    # 3. Сохраняем и обнуляем pending
    cursor.execute('''
        UPDATE users SET coins = %s, tap_power = %s, multiplier = %s, prestige = %s, grand = %s, 
        c_prest_current = %s, shop_data = %s, last_active = %s, pending_coins = 0 WHERE username = %s
    ''', (new_balance, data['tapPower'], data['multiplier'], data['prestige'], data['grand'], 
          data['c_prest_current'], json.dumps(data['shop']), int(time.time()), name))
    conn.commit()
    cursor.close()
    conn.close()
    
    # Возвращаем новый баланс клиенту (включая админские монеты)
    return {"status": "ok", "new_balance": new_balance}

@app.post("/api/admin/edit_balance")
async def admin_edit_balance(request: Request):
    data = await request.json()
    if data.get('admin_username') != 'admin': raise HTTPException(status_code=403)
    
    target = data.get('target_username')
    amount = float(data.get('amount', 0))
    action = data.get('action')
    val = amount if action == 'add' else -amount

    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    # Добавляем в pending_coins (сработает и для онлайн, и для офлайн игроков)
    cursor.execute('UPDATE users SET pending_coins = pending_coins + %s WHERE username = %s', (val, target))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}

@app.get("/api/leaderboard")
async def leaderboard():
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    cursor.execute("SELECT username, coins, grand, prestige, tap_power, multiplier FROM users WHERE username != 'admin' ORDER BY coins DESC LIMIT 10")
    rows = cursor.fetchall()
    return [{"name": r[0], "balance": int(r[1]), "grand": r[2], "prestige": r[3], "click": r[4]*r[5]} for r in rows]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
