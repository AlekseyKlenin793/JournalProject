import logging
from collections import Counter
from sqlalchemy import or_

from models import Journal, Direction
from state import user_search_history, user_journal_data, user_journal_base

# === СППР ===
from spp.criteria.weights import DEFAULT_CRITERIA
from spp.semantic.semantic_search import get_semantic_scores
from spp.decision.decision_engine import rank_journals
from spp.decision.explanation import explain_journal_score
from spp.scoring.normalization import collect_statistics

HISTORY_KEYWORDS_LIMIT = 10
MAX_RECOMMENDATIONS = 10
MAX_DEBUG_JOURNALS = 5

# === ВРЕМЕННЫЙ ФЛАГ ДИАГНОСТИКИ СППР ===
DEBUG_SPP = True   # <<< ПОСЛЕ ТЕСТИРОВАНИЯ ПОСТАВИТЬ False ИЛИ УДАЛИТЬ


def extract_keywords(history):
    if not history:
        return []

    words = []
    for query in history[-HISTORY_KEYWORDS_LIMIT:]:
        words.extend([w.lower() for w in query.strip().split() if len(w) > 2])

    counter = Counter(words)
    return [k for k, _ in counter.most_common(HISTORY_KEYWORDS_LIMIT)]


def recommend_journals(bot, message, session):
    user_id = message.from_user.id
    history = user_search_history.get(user_id, [])

    if not history:
        bot.reply_to(
            message,
            "🗂 У вас ещё нет истории поиска. Для начала попробуйте поискать журналы."
        )
        return

    keywords = extract_keywords(history)
    if not keywords:
        bot.reply_to(message, "ℹ️ Недостаточно данных для рекомендаций.")
        return

    try:
        # ---------- 1. ПРЕДВАРИТЕЛЬНЫЙ ОТБОР (candidate set) ----------
        journal_filter = or_(
            *[Journal.journal_name.ilike(f"%{kw}%") for kw in keywords]
        )
        direction_filter = or_(
            *[Direction.scientific_direction.ilike(f"%{kw}%") for kw in keywords]
        )

        journals = (
            session.query(Journal)
            .join(Direction, isouter=True)
            .filter(journal_filter | direction_filter)
            .distinct()
            .all()
        )

        if not journals:
            bot.reply_to(
                message,
                "❌ Не удалось найти журналы для формирования рекомендаций."
            )
            return

        # ---------- 2. СППР: РАНЖИРОВАНИЕ ----------
        query_text = "Пользователь ищет научный журнал по теме: " + ", ".join(history)

        ranked = rank_journals(
            journals=journals,
            criteria=DEFAULT_CRITERIA,
            query=query_text,
            alpha=0.4,
            top_n=MAX_RECOMMENDATIONS
        )

        if not ranked:
            bot.reply_to(message, "❌ СППР не смогла сформировать рекомендации.")
            return

        # ---------- 3. ПОДГОТОВКА СТАТИСТИКИ ДЛЯ ОБЪЯСНЕНИЙ ----------
        stats = collect_statistics(journals, DEFAULT_CRITERIA)

        # ---------- 4. ПРЕОБРАЗОВАНИЕ ДЛЯ render.py ----------
        recommendations = []
        explanations = {}

        for journal, score in ranked:
            row = (
                journal.journal_name,
                journal.issn,
                journal.publication_price,
                journal.publication_currency,
                journal.final_category
            )
            recommendations.append(row)

            # подробное объяснение (для диагностики)
            if DEBUG_SPP:
                semantic_scores = get_semantic_scores(journals, query_text)

                explanations[journal.issn] = explain_journal_score(
                    journal=journal,
                    criteria=DEFAULT_CRITERIA,
                    stats=stats,
                    semantic_score=semantic_scores.get(journal.id, 0.0),
                    alpha=0.4
                )

        # ---------- 5. СОХРАНЕНИЕ СОСТОЯНИЯ ----------
        user_journal_base[user_id] = recommendations
        user_journal_data[user_id] = list(recommendations)

        # ---------- 6. ВЫВОД ПОЛЬЗОВАТЕЛЮ ----------
        bot.send_message(
            message.chat.id,
            "🧠 *Рекомендации журналов (СППР на основе вашей истории):*",
            parse_mode="Markdown"
        )

        from render import send_journals_page
        send_journals_page(bot, message.chat.id, user_id, 0)

        # ---------- 7. ДИАГНОСТИЧЕСКИЙ ВЫВОД СППР ----------
        if DEBUG_SPP:
            try:
                debug_text = "🧪 *Диагностика СППР (временно):*\n\n"

                for i, (journal, score) in enumerate(ranked[:MAX_DEBUG_JOURNALS], start=1):
                    expl = explanations.get(journal.issn, {})
                    debug_text += (
                        f"{i}. *{journal.journal_name}*\n"
                        f"   Итоговый балл: {score}\n"
                    )

                    for cname, cdata in expl.get("criteria", {}).items():
                        debug_text += (
                            f"   • {cname}: "
                            f"raw={cdata['raw_value']} | "
                            f"norm={cdata['normalized_value']} | "
                            f"w={cdata['weight']} | "
                            f"contrib={cdata['weighted_score']}\n"
                        )
                    debug_text += "\n"

                bot.send_message(
                    message.chat.id,
                    debug_text,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.warning(f"DEBUG_SPP сообщение не отправлено: {e}")

    except Exception as e:
        logging.exception("Ошибка при формировании рекомендаций СППР")
        bot.reply_to(message, "❌ Ошибка при формировании рекомендаций.")
