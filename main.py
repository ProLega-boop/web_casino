import os, asyncio, random, json, uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo
from threading import Thread

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '7867459328:AAFPBnnuCebm90WZeNrQhrO-g-zkACtOCs4'
DB_FILE = "user_db.json"
REPL_URL = "https://9c9ba178-af50-412c-bef0-3d6790704005-00-2zmyvzx318f4t.picard.replit.dev/"

app = FastAPI()
templates = Jinja2Templates(directory="templates")
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {"users": {}, "history": [], "top_game": 0.0, "promos": {"START": 10.0}}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: 
        json.dump(data, f, ensure_ascii=False, indent=4)

state = load_db()
current_game = {"players": {}, "timer": 15, "is_active": False, "result": None}

async def run_game_cycle():
    global state
    current_game["is_active"] = True
    current_game["timer"] = 15
    while current_game["timer"] > 0:
        await asyncio.sleep(1)
        current_game["timer"] -= 1
    
    if current_game["players"]:
        p_items = list(current_game["players"].items())
        total_bank = sum(p[1] for p in p_items)
        # Выбор победителя с учетом веса (суммы ставки)
        winner_id = random.choices([p[0] for p in p_items], weights=[p[1] for p in p_items], k=1)[0]
        
        commission = total_bank * 0.05
        prize = total_bank - commission
        state["users"][winner_id]["bal"] += prize
        
        if total_bank > state.get("top_game", 0): state["top_game"] = total_bank

        res = {"username": state["users"][winner_id]["name"], "prize": round(prize, 2), "total": total_bank}
        current_game["result"] = res
        state["history"].insert(0, res)
        state["history"] = state["history"][:5]
        save_db(state)

    await asyncio.sleep(7)
    current_game.update({"players": {}, "is_active": False, "result": None})

@app.get("/api/get_state")
async def get_state(uid: str, username: str):
    global state
    uid = str(uid)
    if uid not in state["users"]:
        state["users"][uid] = {"bal": 100.0, "name": username, "used_promos": []}
        save_db(state)
    
    bets = [{"uid": pid, "name": state["users"].get(pid, {}).get("name", "Gamer"), "amount": amt} 
            for pid, amt in current_game["players"].items()]
    
    return {
        "user": state["users"][uid],
        "game": current_game,
        "bets": bets,
        "top_game": state.get("top_game", 0),
        "last_game": state["history"][0]["total"] if state["history"] else 0
    }

@app.post("/api/place_bet")
async def place_bet(data: dict):
    uid = str(data['uid'])
    try:
        amt = float(data['amount'])
    except: return {"status": "error", "message": "Invalid amount"}

    if amt < 0.1: return {"status": "error", "message": "Min 0.1 TON"}

    if state["users"].get(uid, {}).get("bal", 0) >= amt:
        state["users"][uid]["bal"] -= amt
        current_game["players"][uid] = current_game["players"].get(uid, 0) + amt
        save_db(state)
        if len(current_game["players"]) >= 2 and not current_game["is_active"]:
            asyncio.create_task(run_game_cycle())
        return {"status": "ok"}
    return {"status": "error", "message": "Low balance"}

@app.post("/api/use_promo")
async def use_promo(data: dict):
    uid, code = str(data['uid']), data['code'].upper()
    if code in state.get("promos", {}) and code not in state["users"][uid].get("used_promos", []):
        bonus = state["promos"][code]
        state["users"][uid]["bal"] += bonus
        state["users"][uid].setdefault("used_promos", []).append(code)
        save_db(state)
        return {"status": "ok", "bonus": bonus}
    return {"status": "error"}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [[types.InlineKeyboardButton(text="⚔️ ИГРАТЬ PvP", web_app=WebAppInfo(url=REPL_URL))]]
    await message.answer("Добро пожаловать в битву!", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

if __name__ == "__main__":
    Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=5000)).start()
    asyncio.run(dp.start_polling(bot))
