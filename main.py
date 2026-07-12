import psycopg2
import os
import json
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

# ТВОЯ ГОТОВАЯ ССЫЛКА С ПАРОЛЕМ
DB_URI = "postgresql://postgres:4FXrzTNyMn2gBAoL@db.rraadyircdxqizpbdihv.supabase.co:5432/postgres"

def init_db():
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                coins DOUBLE PRECISION,
                tap_power DOUBLE PRECISION,
                multiplier DOUBLE PRECISION,
                prestige INTEGER,
                grand INTEGER,
                c_prest_current DOUBLE PRECISION,
                shop_data TEXT
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        print("База данных Supabase успешно подключена!")
    except Exception as e:
        print(f"Ошибка подключения к базе: {e}")

# Инициализация при старте
init_db()

# Раздача картинок (убедись, что папка images лежит рядом с main.py)
current_dir = os.path.dirname(os.path.realpath(__file__))
images_path = os.path.join(current_dir, "images")
if os.path.exists(images_path):
    app.mount("/images", StaticFiles(directory=images_path), name="images")

@app.get("/")
async def read_index():
    return FileResponse('index.html')

@app.post("/api/save")
async def save_game(request: Request):
    try:
        data = await request.json()
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (id, username, coins, tap_power, multiplier, prestige, grand, c_prest_current, shop_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                username = EXCLUDED.username, coins = EXCLUDED.coins, tap_power = EXCLUDED.tap_power,
                multiplier = EXCLUDED.multiplier, prestige = EXCLUDED.prestige, 
                grand = EXCLUDED.grand, c_prest_current = EXCLUDED.c_prest_current, 
                shop_data = EXCLUDED.shop_data
        ''', (data['user_id'], data['username'], data['coins'], data['tapPower'],
              data['multiplier'], data['prestige'], data['grand'],
              data['c_prest_current'], json.dumps(data['shop'])))
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/load")
async def load_game(user_id: int):
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return {
                "coins": row[2], "tapPower": row[3], "multiplier": row[4],
                "prestige": row[5], "grand": row[6], "c_prest_current": row[7],
                "shop": json.loads(row[8])
            }
        return None
    except:
        return None

@app.get("/api/leaderboard")
async def leaderboard():
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        cursor.execute('SELECT username, coins, grand FROM users ORDER BY coins DESC LIMIT 10')
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"name": r[0], "balance": r[1], "grand": r[2]} for r in rows]
    except:
        return []

if __name__ == "__main__":
    # Настройка порта для Render
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
