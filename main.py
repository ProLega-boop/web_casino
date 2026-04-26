import os
import asyncio
import random
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo
from threading import Thread

# --- НАСТРОЙКИ ---
API_TOKEN = '7867459328:AAFPBnnuCebm90WZeNrQhrO-g-zkACtOCs4'
app = FastAPI()
templates = Jinja2Templates(directory="templates")
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# База данных в оперативной памяти
db = {
    "users": {}, 
    "game": {"players": {}, "timer": 40, "is_active": False, "result": None}
}

async def run_game_cycle():
    db["game"]["is_active"] = True
    db["game"]["timer"] = 40
    while db["game"]["timer"] > 0:
        await asyncio.sleep(1)
        db["game"]["timer"] -= 1
    
    players = db["game"]["players"]
    if players:
        winner_id = random.choice(list(players.keys()))
        total_bank = sum(players.values())
        prize = total_bank * 0.95 # 5% комиссия
        db["users"][winner_id]["bal"] += prize
        db["game"]["result"] = {
            "username": db["users"][winner_id]["name"],
            "prize": round(prize, 2),
            "cell": random.randint(0, 99)
        }
    
    await asyncio.sleep(7) # Время показа победителя
    db["game"]["players"] = {}
    db["game"]["is_active"] = False
    db["game"]["result"] = None

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/get_state")
async def get_state(uid: str, username: str):
    if uid not in db["users"]:
        db["users"][uid] = {"bal": 100.0, "name": username} # 100 TON при первом входе
    return {"user": db["users"][uid], "game": db["game"]}

@app.post("/api/place_bet")
async def place_bet(data: dict):
    uid, amount = str(data['uid']), float(data['amount'])
    if db["users"].get(uid) and db["users"][uid]["bal"] >= amount:
        db["users"][uid]["bal"] -= amount
        db["game"]["players"][uid] = db["game"]["players"].get(uid, 0) + amount
        if len(db["game"]["players"]) >= 2 and not db["game"]["is_active"]:
            asyncio.create_task(run_game_cycle())
        return {"status": "ok"}
    return {"status": "error"}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Ссылка формируется автоматически на основе твоего Replit
    url = f"https://{os.getenv('REPL_SLUG')}.{os.getenv('REPL_OWNER')}.repl.co"
    kb = [[types.InlineKeyboardButton(text="⚔️ ИГРАТЬ PvP", web_app=WebAppInfo(url=url))]]
    await message.answer("Добро пожаловать! Жми кнопку для входа:", 
                         reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

if __name__ == "__main__":
    # Запуск веб-сервера на порту 8080 (обязательно для Replit)
    Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8080)).start()
    asyncio.run(dp.start_polling(bot))
