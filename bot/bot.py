import re
import os
import io
import telebot
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Настройка логирования
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Получение чувствительных данных из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# для сохранения запрошенного пользователем списка журналов
user_journal_data = {}

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)
bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_first_name = message.from_user.first_name or "Пользователь"
    logging.info(f"Пользователь {message.from_user.id} начал взаимодействие с ботом.")
    
    welcome_text = (
        f"👋 Привет, <b>{user_first_name}</b>!\n\n"
        "Этот бот помогает находить <b>научные журналы</b> и <b>направления</b> из базы данных.\n"
        "Вы можете искать по <b>ISSN</b>, <b>коду направления</b> или <b>названию</b>.\n\n"
        "<b>Примеры использования:</b>\n"
        "- Отправьте <code>1234-5678</code>, чтобы найти журнал по ISSN.\n"
        "- Отправьте <code>5.3.3</code>, чтобы получить список журналов по коду направления.\n"
        "- Отправьте <code>Физика</code>, чтобы найти журналы или направления по названию."
    )
    
    bot.reply_to(message, welcome_text, parse_mode="HTML")

# обработка всех текстовых запросов
@bot.message_handler(func=lambda message: True)
def handle_query(message):
    query = message.text.strip()
    user_id = message.from_user.id
    logging.info(f"PID {os.getpid()} — Получен запрос от пользователя {message.from_user.id}: {message.text}")

    # определяем тип запроса
    issn_pattern = r"^\d{4}-\d{3}[0-9X]$"  # ISSN ?
    direction_code_pattern = r"^\d+\.\d+\.\d+$"  # код направления ?

    if re.match(issn_pattern, query):
        search_by_issn(message, query)  # поиск по ISSN
    elif re.match(direction_code_pattern, query):
        search_by_direction_code(message, query)  # поиск по коду направления
    else:
        search_by_name(message, query)  # поиск по названию журнала или направления


# поиск по ISSN
def search_by_issn(message, query):
    try:
        with engine.connect() as connection:
            sql_query = text("""
                SELECT journal_name, issn, direction_number, scientific_directions, inclusion_date,
                       h_index, citation_index, publication_time, publication_price, white_list_level,
                       url, final_category
                FROM directions
                WHERE issn = :query
            """)
            result = connection.execute(sql_query, {"query": query})
            rows = result.fetchall()
            if rows:
                send_journal_info(message, rows)
            else:
                bot.reply_to(message, "❌ Журнал с таким ISSN не найден.")
    except SQLAlchemyError as e:
        logging.error(f"Ошибка поиска по ISSN: {e}")
        bot.reply_to(message, "❌ Ошибка при выполнении запроса.")


# поиск по коду направления
def search_by_direction_code(message, query):
    try:
        with engine.connect() as connection:
            sql_query = text("""
                SELECT journal_name, issn, publication_price, final_category
                FROM directions
                WHERE direction_number = :query
            """)
            result = connection.execute(sql_query, {"query": query})
            rows = result.fetchall()
            if rows:
                send_journals_list(message, rows)
            else:
                bot.reply_to(message, "❌ Журналы с таким кодом направления не найдены.")
    except SQLAlchemyError as e:
        logging.error(f"Ошибка поиска по коду направления: {e}")
        bot.reply_to(message, "❌ Ошибка при выполнении запроса.")


# поиск по названию журнала или направлению
def search_by_name(message, query):
    """
    Поиск журналов по названию и направлениям.
    """
    try:
        with engine.connect() as connection:
            journal_query = text("""
                SELECT journal_name, issn, direction_number, scientific_directions, inclusion_date,
                       h_index, citation_index, publication_time, publication_price, white_list_level,
                       url, final_category
                FROM directions
                WHERE journal_name ILIKE :query
            """)
            result_journal = connection.execute(journal_query, {"query": query})
            journal_rows = result_journal.fetchall()

            if journal_rows:
                send_journal_info(message, journal_rows)
                return

            direction_query = text("""
                SELECT journal_name, issn, publication_price, final_category
                FROM directions
                WHERE scientific_directions ILIKE :query
            """)
            result_direction = connection.execute(direction_query, {"query": f"%{query}%"})
            direction_rows = result_direction.fetchall()

            if direction_rows:
                send_journals_list(message, direction_rows)
            else:
                bot.reply_to(message, "❌ Ничего не найдено по вашему запросу.")
    except SQLAlchemyError as e:
        logging.error(f"Ошибка поиска по названию: {e}")
        bot.reply_to(message, "❌ Ошибка при выполнении запроса.")
    except Exception as e:
        logging.error(f"Непредвиденная ошибка: {e}")
        bot.reply_to(message, "❌ Произошла ошибка. Попробуйте позже.")


# отправка информации о конкретном журнале
def send_journal_info(message, rows):
    journal_info = {}
    for row in rows:
        journal_name = row[0]
        if journal_name not in journal_info:
            journal_info[journal_name] = {
                "issn": row[1],
                "directions": [],
                "inclusion_date": row[4],
                "h_index": row[5] or 0,
                "citation_index": row[6] or 0,
                "publication_time": row[7] or "Не указано",
                "publication_price": row[8] or 0,
                "white_list_level": row[9] or "Не указано",
                "url": row[10],
                "final_category": row[11] or "Не указано",
            }
        direction = f"• {row[2] or 'Не указано'} — {row[3] or 'Не указано'}"
        journal_info[journal_name]["directions"].append(direction)

    for journal_name, info in journal_info.items():
        directions_formatted = "\n".join(info["directions"])
        response = (
            f"📚 *Название журнала:* {journal_name}\n"
            f"🔢 *ISSN:* {info['issn']}\n"
            f"📖 *Направления:*\n{directions_formatted}\n"
            f"📅 *Дата включения:* {info['inclusion_date']}\n"
            f"📈 *Индекс Хирша:* {info['h_index']}\n"
            f"🔗 *Индекс цитирования:* {info['citation_index']}\n"
            f"⏳ *Время публикации:* {info['publication_time']}\n"
            f"💰 *Цена публикации:* {info['publication_price']}\n"
            f"🏅 *Уровень в «Белом списке»:* {info['white_list_level']}\n"
            f"🔖 *Итоговая категория:* {info['final_category']}\n"
            f"🌐 *Ссылка:* {info['url']}"
        )
        bot.reply_to(message, response, parse_mode="Markdown")


def send_journals_list(message, rows):
    user_id = message.from_user.id
    user_journal_data[user_id] = rows  # сохраняем список журналов

    # отправляем первую страницу
    send_journals_page(message.chat.id, user_id, 0)

def send_journals_page(chat_id, user_id, page, message_id=None):
    journals = user_journal_data.get(user_id, [])
    if not journals:
        bot.send_message(chat_id, "❌ Нет сохранённых данных. Сначала выполните поиск.")
        return

    per_page = 5
    total_pages = (len(journals) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))  # защита от выхода за пределы

    start = page * per_page
    end = start + per_page
    current_page_items = journals[start:end]

    response = f"📚 *Список найденных журналов (стр. {page+1}/{total_pages}):*\n\n"
    for i, row in enumerate(current_page_items, start+1):
        journal_name = escape_markdown(row[0]) or "Название не указано"
        issn = escape_markdown(row[1]) or "Не указано"
        price = f"{row[2]}" if row[2] else "0"
        category = escape_markdown(row[3]) if row[3] else "-"

        response += (
            f"{i}. 📰 *{journal_name}*\n"
            f"   🔢 *ISSN:* {issn}\n"
            f"   💰 *Цена:* {price}\n"
            f"   🏷️ *Категория:* {category}\n\n"
        )

    markup = InlineKeyboardMarkup()
    buttons = []

    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page-1}"))
    buttons.append(InlineKeyboardButton(f" {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"page_{page+1}"))

    markup.row(*buttons)

    markup.add(InlineKeyboardButton("📄 Экспорт в TXT", callback_data="export_txt"))

    if message_id: 
        bot.edit_message_text(
            response,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    else:
        bot.send_message(chat_id, response, parse_mode="Markdown", reply_markup=markup)

# экранирование спецсимволов Markdown для корректного отображения текста. Если текст пустой или None, возвращает пустую строку.
def escape_markdown(text):
    if not text:
        return ""
    # Telegram Markdown v2 требует экранирования следующих символов
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f"([{escape_chars}])", r'\\\1', text)


@bot.callback_query_handler(func=lambda call: call.data.startswith("page_") or call.data == "noop")
def callback_page(call: CallbackQuery):
    user_id = call.from_user.id

    if call.data == "noop":
        bot.answer_callback_query(call.id)
        return

    page = int(call.data.split("_")[1])
    send_journals_page(call.message.chat.id, user_id, page, call.message.message_id)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "export_txt")
def callback_export(call: CallbackQuery):
    user_id = call.from_user.id
    journals = user_journal_data.get(user_id, [])

    if not journals:
        bot.answer_callback_query(call.id, "❌ Нет данных для экспорта.")
        return

    export_text = "Результаты поиска журналов:\n\n"
    for i, row in enumerate(journals, start=1):
        journal_name = row[0] or "Название не указано"
        issn = row[1] or "Не указано"
        price = f"{row[2]}" if row[2] else "0"
        category = row[3] if row[3] else "-"

        export_text += (
            f"{i}. {journal_name}\n"
            f"   ISSN: {issn}\n"
            f"   Цена: {price}\n"
            f"   Категория: {category}\n\n"
        )

    file_buffer = io.BytesIO(export_text.encode("utf-8"))
    file_buffer.name = "results.txt"

    bot.send_document(call.message.chat.id, file_buffer)

    bot.answer_callback_query(call.id, "✅ Файл сформирован и отправлен.")


if __name__ == "__main__":
    logging.info("Бот запущен и готов к работе.")
    print("Бот запущен...")
    bot.polling()
