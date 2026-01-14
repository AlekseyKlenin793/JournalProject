# recommend.py

import logging
from collections import Counter
from sqlalchemy import or_
from models import Journal, Direction
from state import user_search_history, user_journal_data, user_journal_base

HISTORY_KEYWORDS_LIMIT = 10   # Макс ключевых слов из истории
MAX_RECOMMENDATIONS = 10      # Количество журналов в рекомендациях


def extract_keywords(history):
    """
    Простое извлечение ключевых слов из истории поиска.
    """
    if not history:
        return []

    words = []
    for query in history[-HISTORY_KEYWORDS_LIMIT:]:
        words.extend([w.lower() for w in query.strip().split() if len(w) > 2])

    counter = Counter(words)
    return [k for k, _ in counter.most_common(HISTORY_KEYWORDS_LIMIT)]


def recommend_journals(bot, message, session):
    """
    Генерирует рекомендации журналов для пользователя на основе его истории поиска.
    """
    user_id = message.from_user.id
    history = user_search_history.get(user_id, [])

    if not history:
        bot.reply_to(message, "ℹ️ У вас ещё нет истории поиска. Сначала попробуйте поискать журналы.")
        return

    keywords = extract_keywords(history)
    if not keywords:
        bot.reply_to(message, "ℹ️ Недостаточно данных для рекомендаций.")
        return

    try:
        # формируем фильтр для поиска в названии журналов
        journal_filter = or_(*[Journal.journal_name.ilike(f"%{kw}%") for kw in keywords])
        # фильтр для поиска по научным направлениям
        direction_filter = or_(*[Direction.scientific_direction.ilike(f"%{kw}%") for kw in keywords])

        results = (
            session.query(
                Journal.journal_name,
                Journal.issn,
                Journal.publication_price,
                Journal.publication_currency,
                Journal.final_category
            )
            .join(Direction, isouter=True)
            .filter(journal_filter | direction_filter)
            .all()
        )

        if not results:
            bot.reply_to(message, "❌ Не удалось найти рекомендации на основе вашей истории.")
            return

        # убираем дубликаты по ISSN
        unique = {r[1]: r for r in results}
        recommendations = list(unique.values())[:MAX_RECOMMENDATIONS]

        # сохраняем в state
        user_journal_base[user_id] = recommendations
        user_journal_data[user_id] = list(recommendations)

        bot.send_message(
            message.chat.id,
            "📝 *Рекомендации журналов на основе вашей истории поиска:*",
            parse_mode="Markdown"
        )

        # выводим через стандартную функцию пагинации
        from bot import send_journals_page
        send_journals_page(bot, message.chat.id, user_id, 0)

    except Exception as e:
        logging.error(f"Ошибка при генерации рекомендаций: {e}")
        bot.reply_to(message, "❌ Ошибка при формировании рекомендаций.")
