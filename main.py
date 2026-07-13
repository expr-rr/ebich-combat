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

DB_URI = "ТВОЯ_ССЫЛКА_ОТ_NEON_ИЛИ_SUPABASE"

def get_hash(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# Раздача статики
current_dir = os.path.dirname(os.path.realpath(__file__))
if os.path.exists(os.path.join(current_dir, "images")):
    app.mount("/images", StaticFiles(directory=os.path.join(current_dir, "images")), name="images")

@app.get("/")
async def read_index():
    return FileResponse('index.html')

@app.post("/api/register")
async def register(request: Request):
    try:
        data = await request.json()
        name = data['username'].strip().lower()
        pw = get_hash(data['password'])
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        # При регистрации записываем текущее время как last_active
        cursor.execute('INSERT INTO users (username, password_hash, last_active) VALUES (%s, %s, %s)', 
                       (name, pw, int(time.time())))
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "message": "Аккаунт создан!"}
    except:
        return {"status": "error", "message": "Ник занят"}

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    name = data['username'].strip().lower()
    pw = get_hash(data['password'])
    
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    cursor.execute('SELECT username, coins, tap_power, multiplier, prestige, grand, c_prest_current, shop_data, last_active FROM users WHERE username = %s AND password_hash = %s', (name, pw))
    row = cursor.fetchone()
    
    if row:
        now = int(time.time())
        last_active = row[8] if row[8] else now
        
        # --- ЛОГИКА АФК ДОХОДА ---
        seconds_offline = now - last_active
        if seconds_offline > 36000: seconds_offline = 36000 # Ограничение 10 часов
        
        # Формула: (Клик * Множитель) * Секунды / 2
        tap_value = row[2] * row[3]
        afk_coins = (tap_value * seconds_offline) / 2
        
        # Сразу обновляем время в базе, чтобы не начислить дважды
        cursor.execute('UPDATE users SET last_active = %s WHERE username = %s', (now, name))
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "status": "success",
            "afk": {"coins": afk_coins, "seconds": seconds_offline},
            "data": {
                "username": row[0], "coins": row[1] + afk_coins, "tapPower": row[2],
                "multiplier": row[3], "prestige": row[4], "grand": row[5],
                "c_prest_current": row[6], "shop": json.loads(row[7] if row[7] else "[]")
            }
        }
    return {"status": "error", "message": "Неверные данные"}

@app.post("/api/save")
async def save_game(request: Request):
    data = await request.json()
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    # При сохранении обновляем last_active
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
    cursor.close()
    conn.close()
    return {"status": "ok"}

@app.get("/api/leaderboard")
async def leaderboard():
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    cursor.execute('SELECT username, coins, grand FROM users ORDER BY coins DESC LIMIT 10')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{"name": r[0], "balance": int(r[1]), "grand": r[2]} for r in rows]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
