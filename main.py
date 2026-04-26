import os
import asyncio
import random
import json
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo
from threading import Thread
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
# ТОКЕН ИЗ ЧАТА (Проверь его актуальность!)
API_TOKEN = '7867459328:AAFPBnnuCebm90WZeNrQhrO-g-zkACtOCs4'
DB_FILE = "user_db.json"
REPL_URL = "https://9c9ba178-af50-412c-bef0-3d6790704005-00-2zmyvzx318f4t.picard.replit.dev/" # ВСТАВЬ СЮДА СВОЮ АКТУАЛЬНУЮ ССЫЛКУ ИЗ REPLIT!

app = FastAPI()
templates = Jinja2Templates(directory="templates")
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Цвета для игроков (до 5 участников в раунде)
PLAYER_COLORS = ["#007aff", "#ff3b30", "#4cd964", "#ff9500", "#5856d6"]

# --- ПАМЯТЬ БОТА (JSON БАЗА ДАННЫХ) ---
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"users": {}, "history": []}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Глобальное состояние
state = load_db()
current_game = {"players": {}, "timer": 20, "is_active": False, "result": None, "colors": {}}

# --- ЛОГИКА ИГРЫ ---
async def run_game_cycle():
    global state
    current_game["is_active"] = True
    current_game["timer"] = 20
    
    # 1. Фаза ставок (Таймер)
    while current_game["timer"] > 0:
        await asyncio.sleep(1)
        current_game["timer"] -= 1
    
    # 2. Фаза определения победителя
    players = current_game["players"]
    if players:
        total_bank = sum(players.values())
        
        # Расчет шансов для выбора победителя
        choices = []
        for uid, amount in players.items():
            chance = (amount / total_bank) * 100
            choices.append((uid, chance))
            
        # Выбор победителя на основе шансов
        winner_id = random.choices([c[0] for c in choices], weights=[c[1] for c in choices], k=1)[0]
        
        # Расчет выигрыша (5% комиссия проекта)
        commission = total_bank * 0.05
        prize = total_bank - commission
        
        # Начисление выигрыша
        state["users"][winner_id]["bal"] += prize
        winner_name = state["users"][winner_id]["name"]
        
        # Сохранение результата раунда
        result_data = {
            "time": datetime.now().strftime("%H:%M"),
            "username": winner_name,
            "prize": round(prize, 2),
            "chance": round((players[winner_id] / total_bank) * 100, 1),
            "cell": random.randint(0, 99) # Случайная клетка "взрыва"
        }
        
        current_game["result"] = result_data
        state["history"].insert(0, result_data) # Добавляем в начало истории
        state["history"] = state["history"][:5] # Храним только последние 5 игр
        
        # --- Реферальная комиссия (расчет от комиссии проекта) ---
        referrer_id = state["users"][winner_id].get("referred_by")
        if referrer_id and referrer_id in state["users"]:
            # Например, 10% от комиссии проекта идет рефералу
            ref_bonus = commission * 0.10
            state["users"][referrer_id]["bal"] += ref_bonus
            state["users"][referrer_id]["ref_earned"] += ref_bonus

        save_db(state) # Сохраняем данные после начисления

    # 3. Фаза показа победителя (~5 секунд)
    await asyncio.sleep(5)
    
    # 4. Фаза автоматического сброса поля
    current_game["players"] = {}
    current_game["is_active"] = False
    current_game["result"] = None
    current_game["colors"] = {}
    await asyncio.sleep(2) # Пауза перед новым раундом

# --- API ЭНДПОИНТЫ ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/get_state")
async def get_state(uid: str, username: str, referred_by: str = None):
    global state
    uid = str(uid)
    
    # Создание или обновление пользователя
    if uid not in state["users"]:
        state["users"][uid] = {
            "bal": 50.0, # Тестовый баланс
            "name": username,
            "referred_by": referred_by if referred_by != uid else None,
            "ref_count": 0,
            "ref_earned": 0.0,
            "promo_used": False
        }
        # Если есть реферал, обновляем его счетчик
        if referred_by and referred_by in state["users"] and referred_by != uid:
            state["users"][referred_by]["ref_count"] += 1
        save_db(state)
    else:
        # Обновляем имя, если оно изменилось в ТГ
        if state["users"][uid]["name"] != username:
            state["users"][uid]["name"] = username
            save_db(state)

    return JSONResponse(content={
        "user": state["users"][uid],
        "game": current_game,
        "last_win": state["history"][0] if state["history"] else None,
        "replit_url": REPL_URL
    })

@app.post("/api/place_bet")
async def place_bet(data: dict):
    global current_game, state
    uid, amount = str(data['uid']), float(data['amount'])
    
    if uid in state["users"] and state["users"][uid]["bal"] >= amount:
        # Списываем баланс
        state["users"][uid]["bal"] -= amount
        
        # Назначаем цвет игроку, если его нет
        if uid not in current_game["colors"]:
            color_index = len(current_game["colors"]) % len(PLAYER_COLORS)
            current_game["colors"][uid] = PLAYER_COLORS[color_index]
            
        # Добавляем ставку
        current_game["players"][uid] = current_game["players"].get(uid, 0) + amount
        
        save_db(state)
        
        # Запуск таймера при 2+ игроках
        if len(current_game["players"]) >= 2 and not current_game["is_active"]:
            asyncio.create_task(run_game_cycle())
            
        return {"status": "ok"}
    return {"status": "error"}

@app.post("/api/use_promo")
async def use_promo(data: dict):
    global state
    uid, promo = str(data['uid']), data['promo'].strip().upper()
    
    if uid in state["users"] and not state["users"][uid]["promo_used"]:
        if promo == "STARTBONUS": # Пример промокода
            state["users"][uid]["bal"] += 10.0 # Бонус 10 TON
            state["users"][uid]["promo_used"] = True
            save_db(state)
            return {"status": "ok", "message": "Промокод активирован! +10 TON"}
        return {"status": "error", "message": "Неверный промокод"}
    return {"status": "error", "message": "Промокод уже использован или ошибка"}

# --- TELEGRAM БОТ ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Логика реферальной ссылки: /start ID
    args = message.text.split()
    referred_by = args[1] if len(args) > 1 else None
    
    # Формируем URL для Web App, передавая ID реферала
    webapp_url = REPL_URL
    if referred_by:
        webapp_url += f"?startapp={referred_by}"
        
    kb = [[types.InlineKeyboardButton(text="⚔️ ИГРАТЬ PvP", web_app=WebAppInfo(url=webapp_url))]]
    await message.answer("Добро пожаловать в обновленную PvP Рулетку!", 
                         reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

if __name__ == "__main__":
    # Запуск сервера на порту 8080 (для Replit)
    Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8080)).start()
    asyncio.run(dp.start_polling(bot))
