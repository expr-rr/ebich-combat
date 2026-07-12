import psycopg2
import os
import json
import uvicorn
import hashlib
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# УБЕДИСЬ, ЧТО ЭТО ССЫЛКА POOLER (ПОРТ 6543)
DB_URI = "postgresql://postgres.rraadyircdxqizpbdihv:4FXrzTNyMn2gBAoL@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require"

def get_hash(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

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
        if not name: return {"status": "error", "message": "Введите ник"}
        pw = get_hash(data['password'])
        
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        
        # Пытаемся вставить данные
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s)', (name, pw))
        conn.commit()
        cursor.close()
        return {"status": "success", "message": "Аккаунт создан! Теперь жми ВОЙТИ"}
    except psycopg2.errors.UniqueViolation:
        return {"status": "error", "message": "Этот ник уже занят. Нажми ВОЙТИ"}
    except Exception as e:
        print(f"!!! REAL REGISTER ERROR: {e}") # ЭТО ПОЯВИТСЯ В ЛОГАХ RENDER
        return {"status": "error", "message": f"Ошибка базы: {str(e)}"}
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
        cursor.execute('SELECT username, coins, tap_power, multiplier, prestige, grand, c_prest_current, shop_data FROM users WHERE username = %s AND password_hash = %s', (name, pw))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            return {
                "status": "success",
                "data": {
                    "username": row[0], "coins": row[1], "tapPower": row[2],
                    "multiplier": row[3], "prestige": row[4], "grand": row[5],
                    "c_prest_current": row[6], "shop": json.loads(row[7] if row[7] else "[]")
                }
            }
        return {"status": "error", "message": "Неверный ник или пароль"}
    except Exception as e:
        print(f"!!! LOGIN ERROR: {e}")
        return {"status": "error", "message": "Ошибка сервера"}
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
                prestige = %s, grand = %s, c_prest_current = %s, shop_data = %s
            WHERE username = %s
        ''', (data['coins'], data['tapPower'], data['multiplier'], 
              data['prestige'], data['grand'], data['c_prest_current'], 
              json.dumps(data['shop']), data['username']))
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"!!! SAVE ERROR: {e}")
    finally:
        if conn: conn.close()
    return {"status": "ok"}

@app.get("/api/leaderboard")
async def leaderboard():
    conn = None
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('SELECT username, coins, grand FROM users ORDER BY coins DESC LIMIT 10')
        rows = cursor.fetchall()
        cursor.close()
        return [{"name": r[0], "balance": int(r[1]), "grand": r[2]} for r in rows]
    except:
        return []
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
