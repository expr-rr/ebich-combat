import psycopg2
import os
import json
import uvicorn
import hashlib
import time
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

DB_URI = "postgresql://neondb_owner:npg_bYj1tnSH8XBg@ep-billowing-pine-ahbzqlq1-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

def get_hash(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# Раздача статики
current_dir = os.path.dirname(os.path.realpath(__file__))
if os.path.exists(os.path.join(current_dir, "images")):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
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
        cursor.execute('INSERT INTO users (username, password_hash, last_active) VALUES (%s, %s, %s)', 
                       (name, pw, int(time.time())))
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "message": "Готово!"}
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
        last_active = row[8] if row[8] is not None else now
        diff = now - last_active
        actual_seconds = min(diff, 36000)
        tap_val = row[2] * row[3]
        afk_coins = (tap_val * actual_seconds) / 5
        cursor.execute('UPDATE users SET last_active = %s WHERE username = %s', (now, name))
        conn.commit()
        cursor.close()
        conn.close()
        return {
            "status": "success",
            "afk": {"coins": afk_coins, "seconds": actual_seconds},
            "data": {
                "username": row[0], "coins": row[1] + afk_coins, "tapPower": row[2],
                "multiplier": row[3], "prestige": row[4], "grand": row[5],
                "c_prest_current": row[6], "shop": json.loads(row[7] if row[7] else "[]")
            }
        }
    return {"status": "error", "message": "Ошибка"}

@app.post("/api/save")
async def save_game(request: Request):
    data = await request.json()
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET coins = %s, tap_power = %s, multiplier = %s, prestige = %s, grand = %s, 
        c_prest_current = %s, shop_data = %s, last_active = %s WHERE username = %s
    ''', (data['coins'], data['tapPower'], data['multiplier'], data['prestige'], data['grand'], 
          data['c_prest_current'], json.dumps(data['shop']), int(time.time()), data['username']))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}

# --- АДМИНСКАЯ ЛОГИКА ---
@app.post("/api/admin/edit_balance")
async def admin_edit_balance(request: Request):
    data = await request.json()
    admin_user = data.get('admin_username')
    target_user = data.get('target_username')
    amount = float(data.get('amount', 0))
    action = data.get('action') # 'add' или 'remove'

    if admin_user != 'admin':
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    
    if action == 'add':
        cursor.execute('UPDATE users SET coins = coins + %s WHERE username = %s', (amount, target_user))
    elif action == 'remove':
        cursor.execute('UPDATE users SET coins = GREATEST(0, coins - %s) WHERE username = %s', (amount, target_user))
    
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}

@app.get("/api/leaderboard")
async def leaderboard():
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    # Исключаем 'admin' из списка
    cursor.execute('''
        SELECT username, coins, grand, prestige, tap_power, multiplier 
        FROM users 
        WHERE username != 'admin' 
        ORDER BY coins DESC LIMIT 10
    ''')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{"name": r[0], "balance": int(r[1]), "grand": r[2], "prestige": r[3], "click": r[4]*r[5]} for r in rows]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
