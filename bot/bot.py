import re
import os
import telebot
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# настройка логирования
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
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} начал взаимодействие с ботом.")
    welcome_text = (
        "👋 *Добро пожаловать!* Я бот для поиска информации о научных журналах и направлениях.\n\n"
        "📌 *Введите один из следующих запросов:*\n"
        " - ISSN (например, 1234-5678)\n"
        " - Код направления (например, 5.3.3 или 12.00.01)\n"
        " - Название журнала или направления (например, Материаловедение)"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")


@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "ℹ️ *Справка и помощь*\n\n"
        "Я бот для поиска информации о научных журналах и направлениях. "
        "Вот список доступных команд:\n\n"
        "📌 *Основные команды:*\n"
        "  - `/start` — Начать работу с ботом и получить приветственное сообщение.\n"
        "  - `/help` — Получить справку о командах и примеры использования.\n\n"
        "📚 *Поиск информации:*\n"
        "  - `ISSN` (например, `1234-5678`) — Найти журнал по ISSN.\n"
        "  - Код направления (например, `5.3.3` или `12.00.01`) — Показать журналы по указанному коду.\n"
        "  - Название (например, `Физическая культура`) — Поиск по названию журнала или научного направления.\n\n"
        "🎯 *Дополнительные команды:*\n"
        "  - `/show_top N` — Показать только первые N журналов из последнего запроса (например, `/show_top 5`).\n\n"
        "🛠️ *Примеры использования:*\n"
        "  1️⃣ Отправьте `5.3.3` — я покажу журналы по этому направлению.\n"
        "  2️⃣ Отправьте часть названия журнала или направления, например, `Физическая культура`, чтобы увидеть совпадения.\n"
        "  3️⃣ Используйте `/show_top 10`, чтобы посмотреть топ-10 из найденного списка.\n\n"
        "❓ Если у вас есть вопросы или предложения, напишите администратору."
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")


# обработка всех текстовых запросов
@bot.message_handler(func=lambda message: True)
def handle_query(message):
    query = message.text.strip()
    user_id = message.from_user.id
    logging.info(f"PID {os.getpid()} — Получен запрос от пользователя {message.from_user.id}: {message.text}")

    if query.startswith("/show_top"):
        try:
            n = int(query.split()[1])
            show_top_journals(message, user_id, n)
        except (IndexError, ValueError):
            bot.reply_to(message, "❌ Введите число после команды, например: /show_top 5")
        return

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


# отправка информации о наличии направления в разных журналах
def send_journals_list(message, rows):
    user_id = message.from_user.id

    # список журналов для пользователя
    user_journal_data[user_id] = rows

    response = "📚 *Список найденных журналов:*\n\n"
    for i, row in enumerate(rows, 1):
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

        # прерываем, если длина ответа близка к лимиту телеги
        if len(response) > 3500:  # оставляем запас для дополнительного текста
            response += "⚠️ Список слишком длинный, отображены только первые журналы.\n"
            break

    # подсказываем команду /show_top
    response += (
        "\n💡 Если хотите увидеть только определённое количество журналов, введите `/show_top N`, "
        "где N — число журналов, которые нужно отобразить."
    )

    # разделяем текст на части и отправляем
    send_long_message(message, response)


# экранирование спецсимволов Markdown для корректного отображения текста. Если текст пустой или None, возвращает пустую строку.
def escape_markdown(text):
    if not text:
        return ""
    # Telegram Markdown v2 требует экранирования следующих символов
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f"([{escape_chars}])", r'\\\1', text)


# разбивка длинных сообщений на части, учитывая ограничение Telegram в 4096 байт.
def send_long_message(message, text, parse_mode="Markdown"):
    max_length = 4096
    while len(text) > max_length:
        split_index = text[:max_length].rfind("\n")
        if split_index == -1:
            split_index = max_length
        part = text[:split_index]
        text = text[split_index:].strip()

        bot.reply_to(message, part, parse_mode=parse_mode)
    if text:
        bot.reply_to(message, text, parse_mode=parse_mode)


def show_top_journals(message, user_id, n):
    if user_id not in user_journal_data:
        bot.reply_to(message, "❌ Вы ещё не запрашивали список журналов. Сначала выполните поиск.")
        return

    journals = user_journal_data[user_id]
    if n > len(journals):
        bot.reply_to(message, f"⚠️ В вашем списке всего {len(journals)} журналов.")
        n = len(journals)

    response = f"📚 *Топ {n} журналов:*\n\n"
    for i, row in enumerate(journals[:n], 1):
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

        # если текст уже близок к максимальной длине, отправляем его и начинаем новый блок
        if len(response) > 3500:  # с запасом оставляем пространство для Telegram Markdown
            send_long_message(message, response)
            response = ""  # очищаем текущий блок

    # отправляем оставшийся текст
    if response:
        send_long_message(message, response)


if __name__ == "__main__":
    logging.info("Бот запущен и готов к работе.")
    print("Бот запущен...")
    bot.polling()