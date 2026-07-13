import psycopg2, os, json, uvicorn, hashlib, time
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()
DB_URI = "postgresql://neondb_owner:npg_bYj1tnSH8XBg@ep-billowing-pine-ahbzqlq1-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

def get_hash(password: str): return hashlib.sha256(password.encode()).hexdigest()

# Инициализация с проверкой всех колонок
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
        cursor.close()
        conn.close()
        return {"status": "success", "message": "Аккаунт создан!"}
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
        pending = row[9] if row[9] else 0
        diff = now - (row[8] or now)
        afk = (row[2] * row[3] * min(diff, 36000)) / 5
        total = row[1] + afk + pending
        cursor.execute('UPDATE users SET last_active = %s, pending_coins = 0, coins = %s WHERE username = %s', (now, total, name))
        conn.commit()
        cursor.close()
        conn.close()
        return {
            "status": "success", "afk": {"coins": afk + pending, "seconds": min(diff, 36000)},
            "data": { "username": row[0], "coins": total, "tapPower": row[2], "multiplier": row[3], "prestige": row[4], "grand": row[5], "c_prest_current": row[6], "shop": json.loads(row[7]) }
        }
    return {"status": "error", "message": "Ошибка"}

@app.post("/api/save")
async def save_game(request: Request):
    data = await request.json()
    name = data['username']
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    
    # 1. Забираем только дельту от админа
    cursor.execute('SELECT pending_coins FROM users WHERE username = %s', (name,))
    p_row = cursor.fetchone()
    admin_delta = p_row[0] if p_row and p_row[0] else 0
    
    # 2. Сохраняем баланс клиента + дельту
    new_balance = max(0, float(data['coins']) + admin_delta)
    cursor.execute('''
        UPDATE users SET coins = %s, tap_power = %s, multiplier = %s, prestige = %s, grand = %s, 
        c_prest_current = %s, shop_data = %s, last_active = %s, pending_coins = 0 WHERE username = %s
    ''', (new_balance, data['tapPower'], data['multiplier'], data['prestige'], data['grand'], 
          data['c_prest_current'], json.dumps(data['shop']), int(time.time()), name))
    conn.commit()
    cursor.close()
    conn.close()
    
    # Возвращаем дельту, чтобы клиент прибавил её к своему ТЕКУЩЕМУ значению
    return {"status": "ok", "admin_delta": admin_delta}

@app.post("/api/admin/edit_balance")
async def admin_edit_balance(request: Request):
    data = await request.json()
    if data.get('admin_username') != 'admin': raise HTTPException(status_code=403)
    val = float(data.get('amount', 0)) if data.get('action') == 'add' else -float(data.get('amount', 0))
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET pending_coins = pending_coins + %s WHERE username = %s', (val, data.get('target_username')))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "ok"}

@app.get("/api/leaderboard")
async def leaderboard():
    conn = psycopg2.connect(DB_URI)
    cursor = conn.cursor()
    # Тянем last_active для статуса онлайн
    cursor.execute("SELECT username, coins, grand, prestige, tap_power, multiplier, last_active FROM users WHERE username != 'admin' ORDER BY coins DESC LIMIT 10")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{"name": r[0], "balance": int(r[1]), "grand": r[2], "prestige": r[3], "click": r[4]*r[5], "last_active": r[6]} for r in rows]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
