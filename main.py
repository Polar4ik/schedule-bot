import logging
import requests
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue

from settings import *

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = 'subscribers.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscribers (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL UNIQUE
    );
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY,
        data TEXT NOT NULL
    );
    ''')
    
    conn.commit()
    conn.close()

def add_subscriber(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO subscribers (user_id) VALUES (?);', (user_id,))
    conn.commit()
    conn.close()

def is_subscribed(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM subscribers WHERE user_id = ?;', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_subscribers():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM subscribers;')
    subscribers = cursor.fetchall()
    conn.close()
    return [subscriber['user_id'] for subscriber in subscribers]

def get_last_schedule():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT data FROM schedule ORDER BY id DESC LIMIT 1;')
    result = cursor.fetchone()
    conn.close()
    return result['data'] if result else None

def update_schedule(new_schedule):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO schedule (data) VALUES (?);', (new_schedule,))
    conn.commit()
    conn.close()

def get_schedule():
    url = "https://nggtk.ru/api/v2/GetScheduleGroup/?vk_access_token_settings=&vk_app_id=7688110&vk_are_notifications_enabled=0&vk_is_app_user=1&vk_is_favorite=1&vk_language=ru&vk_platform=desktop_web&vk_ref=catalog_recent&vk_testing_group_id=3&vk_ts=1715447998&vk_user_id=491552018&sign=jHrws9PeP528Ijpeo8IEv5mVtqOB7j-kbnmyO_64bAo"
    params = {
        'group': '27' 
    }

    response = requests.post(url, data=params)

    if response.status_code != 200:
        logger.error(f"Ошибка при запросе расписания: {response.status_code}")
        return []

    data = response.json()

    schedule_items = []
    for item in data.get('schedule', []):
        couples = [f"{c['name']} (Кабинет: {c['office']})" for c in item.get('couples', [])]
        schedule_items.append(f"{item['name']}:\n" + "\n".join(couples))

    return "\n\n".join(schedule_items)

async def send_schedule(update, context):
    chat_id = update.message.chat_id
    schedule = get_schedule()

    if not schedule:
        await update.message.reply_text("Не удалось получить расписание. Попробуйте позже.")
        return

    await update.message.reply_text(schedule)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['Получить расписание'],  
        ['Подписаться на уведомления']  
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(
        "Привет! Нажми на кнопку ниже, чтобы получить расписание или подписаться на уведомления.",
        reply_markup=reply_markup
    )

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id 

    if is_subscribed(user_id):
        await update.message.reply_text("Вы уже подписаны на обновления расписания.")
    else:
        add_subscriber(user_id)
        await update.message.reply_text("Вы успешно подписаны на обновления расписания.")

async def check_schedule(context: ContextTypes.DEFAULT_TYPE):
    current_schedule = get_schedule()

    if not current_schedule:
        logger.error("Не удалось получить расписание при проверке.")
        return

    last_schedule = get_last_schedule()

    if current_schedule != last_schedule:
        response = "Обновление расписания:\n\n" + current_schedule

        for user_id in get_subscribers():
            try:
                await context.bot.send_message(user_id, response)
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

        update_schedule(current_schedule)

def main():
    application = Application.builder().token(TOKEN).build()

    create_tables()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex('^Получить расписание$'), send_schedule))
    application.add_handler(MessageHandler(filters.Regex('^Подписаться на уведомления$'), subscribe))

    job_queue = application.job_queue
    job_queue.run_repeating(check_schedule, interval=600, first=0)  # Проверка каждые 10 минут

    application.run_polling()

if __name__ == '__main__':
    main()

