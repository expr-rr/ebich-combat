import psycopg2
import os
import json
import uvicorn
import hashlib
import time
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# ССЫЛКА NEON (убедись, что она твоя)
DB_URI = "postgresql://neondb_owner:npg_bYj1tnSH8XBg@ep-billowing-pine-ahbzqlq1-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

def get_hash(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            coins DOUBLE PRECISION DEFAULT 0,
            tap_power DOUBLE PRECISION DEFAULT 1,
            multiplier DOUBLE PRECISION DEFAULT 1,
            prestige INTEGER DEFAULT 0,
            grand INTEGER DEFAULT 0,
            c_prest_current DOUBLE PRECISION DEFAULT 100000,
            shop_data TEXT DEFAULT '[]',
            last_active BIGINT
        )
    ''')
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_active BIGINT")
    except:
        conn.rollback()
    conn.commit()
    cursor.close()
    conn.close()

init_db()

current_dir = os.path.dirname(os.path.realpath(__file__))
if os.path.exists(os.path.join(current_dir, "images")):
    app.mount("/images", StaticFiles(directory=os.path.join(current_dir, "images")), name="images")

@app.get("/")
async def read_index():
    return FileResponse('index.html')

@app.post("/api/register")
async def register(request: Request):
    conn = None
    try:
        data = await request.json()
        name = data['username'].strip().lower()
        pw = get_hash(data['password'])
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, password_hash, last_active) VALUES (%s, %s, %s)', 
                       (name, pw, int(time.time())))
        conn.commit()
        return {"status": "success", "message": "Готово! Жми ВОЙТИ"}
    except:
        return {"status": "error", "message": "Ник занят"}
    finally:
        if conn: conn.close()

@app.post("/api/login")
async def login(request: Request):
    conn = None
    try:
        data = await request.json()
        name = data['username'].strip().lower()
        pw = get_hash(data['password'])
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('SELECT username, coins, tap_power, multiplier, prestige, grand, c_prest_current, shop_data, last_active FROM users WHERE username = %s AND password_hash = %s', (name, pw))
        row = cursor.fetchone()
        if row:
            now = int(time.time())
            last_active = row[8] if row[8] is not None else now
            diff = now - last_active
            actual_seconds = min(diff, 36000)
            tap_value = row[2] * row[3]
            afk_coins = (tap_value * actual_seconds) / 10 if actual_seconds > 0 else 0
            cursor.execute('UPDATE users SET last_active = %s WHERE username = %s', (now, name))
            conn.commit()
            return {
                "status": "success",
                "afk": {"coins": afk_coins, "seconds": actual_seconds},
                "data": {
                    "username": row[0], "coins": row[1] + afk_coins, "tapPower": row[2],
                    "multiplier": row[3], "prestige": row[4], "grand": row[5],
                    "c_prest_current": row[6], "shop": json.loads(row[7] if row[7] else "[]")
                }
            }
        return {"status": "error", "message": "Ошибка данных"}
    except:
        return {"status": "error", "message": "Тех. ошибка"}
    finally:
        if conn: conn.close()

@app.post("/api/save")
async def save_game(request: Request):
    conn = None
    try:
        data = await request.json()
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET 
                coins = %s, tap_power = %s, multiplier = %s, 
                prestige = %s, grand = %s, c_prest_current = %s, 
                shop_data = %s, last_active = %s
            WHERE username = %s
        ''', (data['coins'], data['tapPower'], data['multiplier'], 
              data['prestige'], data['grand'], data['c_prest_current'], 
              json.dumps(data['shop']), int(time.time()), data['username']))
        conn.commit()
    except Exception as e:
        print(f"SAVE ERROR: {e}")
    finally:
        if conn: conn.close()
    return {"status": "ok"}

@app.get("/api/leaderboard")
async def leaderboard():
    conn = None
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        # Тянем больше данных: username, coins, grand, prestige, tap_power, multiplier
        cursor.execute('SELECT username, coins, grand, prestige, tap_power, multiplier FROM users ORDER BY coins DESC LIMIT 10')
        rows = cursor.fetchall()
        return [{
            "name": r[0], 
            "balance": int(r[1]), 
            "grand": r[2],
            "prestige": r[3],
            "click": r[4] * r[5] # Считаем доход за клик сразу
        } for r in rows]
    except:
        return []
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
