import logging
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Инициализация бота
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Состояния FSM
class AddExpenseState(StatesGroup):
    waiting_for_amount_and_category = State()

# Форматирование чисел
def format_number(number):
    return "{:,.0f}".format(number).replace(",", ".")

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("finance.db")
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE IF NOT EXISTS expenses (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER,
                        amount REAL,
                        category TEXT,
                        date TEXT)""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS action_history (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER,
                        details TEXT,
                        date TEXT)""")

    conn.commit()
    conn.close()

# Функции работы с БД
def add_expense(user_id, amount, category, date):
    conn = sqlite3.connect("finance.db")
    cursor = conn.cursor()
    
    cursor.execute("INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)", 
                   (user_id, amount, category, date))
    
    cursor.execute("INSERT INTO action_history (user_id, details, date) VALUES (?, ?, ?)",
                   (user_id, f"Добавлен расход: {amount} сум в категорию {category}", date))
    
    cursor.execute("DELETE FROM action_history WHERE id NOT IN (SELECT id FROM action_history WHERE user_id = ? ORDER BY date DESC LIMIT 5)", (user_id,))
    
    conn.commit()
    conn.close()

def get_today_expenses(user_id):
    conn = sqlite3.connect("finance.db")
    cursor = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date LIKE ?", (user_id, f"{today}%"))
    total_amount = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT category, SUM(amount) FROM expenses WHERE user_id = ? AND date LIKE ? GROUP BY category", 
                  (user_id, f"{today}%"))
    details = cursor.fetchall()
    
    conn.close()
    return total_amount, details

def get_stats(user_id):
    conn = sqlite3.connect("finance.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT category, SUM(amount) FROM expenses WHERE user_id = ? GROUP BY category", (user_id,))
    stats = cursor.fetchall()
    
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ?", (user_id,))
    total_amount = cursor.fetchone()[0] or 0
    
    cursor.execute("""
        SELECT strftime('%Y-%m', date) AS month, SUM(amount)
        FROM expenses
        WHERE user_id = ?
        GROUP BY month
        ORDER BY month DESC
    """, (user_id,))
    monthly_stats = cursor.fetchall()
    
    conn.close()
    return stats, total_amount, monthly_stats

def delete_last_expense(user_id):
    conn = sqlite3.connect("finance.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, amount, category FROM expenses WHERE user_id = ? ORDER BY date DESC LIMIT 1", (user_id,))
    last_expense = cursor.fetchone()
    
    if last_expense:
        expense_id, amount, category = last_expense
        cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        cursor.execute("INSERT INTO action_history (user_id, details, date) VALUES (?, ?, ?)",
                      (user_id, f"Удалён расход: {amount} сум из категории {category}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        cursor.execute("DELETE FROM action_history WHERE id NOT IN (SELECT id FROM action_history WHERE user_id = ? ORDER BY date DESC LIMIT 5)", (user_id,))
        conn.commit()
        conn.close()
        return amount, category
    
    conn.close()
    return None, None

def get_all_users():
    conn = sqlite3.connect("finance.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT user_id FROM expenses")
    users = [user[0] for user in cursor.fetchall()]
    
    conn.close()
    return users

# Инициализация базы данных
init_db()

# Клавиатура
def create_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/stats"), KeyboardButton(text="/today")],
            [KeyboardButton(text="/delete_last"), KeyboardButton(text="/help")]
        ],
        resize_keyboard=True
    )

# Обработчики команд
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я финансовый ассистент. Помогу тебе управлять расходами 💰\n\n"
        "Просто напиши сумму и категорию расхода, например: 15000 продукты\n\n"
        "Используй кнопки ниже для быстрого доступа к командам.",
        reply_markup=create_main_keyboard()
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = [
        "📌 <b>Как пользоваться ботом:</b>",
        "",
        "1. <b>Быстрый ввод</b> (без команд):",
        "Просто напиши: <code>СУММА КАТЕГОРИЯ</code>",
        "Пример: <code>15000 продукты</code>",
        "",
        "2. <b>Основные команды:</b>",
        "/stats - общая статистика расходов",
        "/today - расходы за сегодня",
        "/delete_last - удалить последний расход",
        "/help - эта справка"
    ]
    await message.answer("\n".join(help_text), parse_mode="HTML")

@dp.message(Command("today"))
async def today_expenses(message: types.Message):
    try:
        total, details = get_today_expenses(message.from_user.id)
        today_date = datetime.now().strftime("%d.%m.%Y")
        
        if total > 0:
            response = [f"💰 <b>Расходы на {today_date}:</b>"]
            for category, amount in details:
                response.append(f"- {category}: {format_number(amount)} сум")
            response.append(f"\n<b>Итого:</b> {format_number(total)} сум")
        else:
            response = [f"💰 <b>Расходы на {today_date}:</b> нет расходов"]
            
        await message.answer("\n".join(response), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при получении расходов за сегодня: {e}")
        await message.answer("❌ Ошибка при получении данных")

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    try:
        stats, total, monthly = get_stats(message.from_user.id)
        response = ["📊 <b>Ваши расходы:</b>"]
        
        if stats:
            response.extend(f"- {cat}: {format_number(amt)} сум" for cat, amt in stats)
            response.append(f"\n💸 <b>Всего:</b> {format_number(total)} сум")
            response.append("\n📅 <b>По месяцам:</b>")
            response.extend(f"- {month}: {format_number(amt)} сум" for month, amt in monthly)
        else:
            response.append("Пока нет данных о расходах")
            
        await message.answer("\n".join(response), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer("❌ Ошибка при получении статистики")

@dp.message(Command("delete_last"))
async def delete_last_expense_handler(message: types.Message):
    try:
        amount, category = delete_last_expense(message.from_user.id)
        if amount:
            await message.answer(f"🗑️ Удалено: {format_number(amount)} сум (категория: {category})")
        else:
            await message.answer("ℹ️ Нет расходов для удаления")
    except Exception as e:
        logger.error(f"Ошибка при удалении расхода: {e}")
        await message.answer("❌ Ошибка при удалении расхода")

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_expense_input(message: types.Message):
    try:
        parts = message.text.split(maxsplit=1)
        amount = float(parts[0].replace(',', '.'))
        category = parts[1].lower() if len(parts) > 1 else "другое"
        
        add_expense(message.from_user.id, amount, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        await message.answer(f"✅ Добавлено: {format_number(amount)} сум в категорию «{category}»")
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите:\n<code>СУММА КАТЕГОРИЯ</code>\n"
            "Пример: <code>10000 еда</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при добавлении расхода: {e}")
        await message.answer("⚠️ Произошла ошибка при обработке вашего запроса")

# Ежедневные уведомления
async def send_daily_reports():
    while True:
        now = datetime.utcnow()
        if now.hour == 18 and now.minute == 59:  # 23:59 Tashkent time (UTC+5)
            for user_id in get_all_users():
                total, details = get_today_expenses(user_id)
                if total > 0:
                    today_date = (now + timedelta(hours=5)).strftime("%d.%m.%Y")
                    response = [f"🕒 <b>Ваши расходы за {today_date}:</b>"]
                    response.extend(f"- {cat}: {format_number(amt)} сум" for cat, amt in details)
                    response.append(f"\n<b>Итого:</b> {format_number(total)} сум")
                    try:
                        await bot.send_message(user_id, "\n".join(response), parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Ошибка отправки отчета пользователю {user_id}: {e}")
        await asyncio.sleep(60)

# Запуск бота
async def main():
    # Удаляем вебхук, если он был
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем задачу для ежедневных отчетов
    asyncio.create_task(send_daily_reports())
    
    # Запускаем polling
    logger.info("Бот запущен в режиме polling")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")