import psycopg2
from sentence_transformers import SentenceTransformer
import numpy as np
from tqdm import tqdm

# =========================
# НАСТРОЙКИ
# =========================

DB_CONFIG = {
    "host": "db",
    "dbname": "JournalProjectDB",
    "user": "postgres",
    "password": "804793"
}

MODEL_NAME = "intfloat/multilingual-e5-base"
BATCH_SIZE = 64


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def clean_text(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("\n", " ").strip()


def build_text(name, url, category):
    """
    Формируем НОРМАЛЬНЫЙ текст для эмбеддинга
    """
    parts = [
        "Научный журнал",
        clean_text(name),
        f"категория {clean_text(category)}" if category else "",
        f"сайт {clean_text(url)}" if url else ""
    ]

     oin([p for p in parts if p])


# =========================
# ОСНОВНОЙ СКРИПТ
# =========================

def main():
    print("🚀 Подключение к БД...")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("📥 Загрузка модели...")
    model = SentenceTransformer(MODEL_NAME)

    print("📊 Чтение журналов...")
    cur.execute("SELECT id, journal_name, url, final_category FROM journals")
    journals = cur.fetchall()

    print(f"Найдено журналов: {len(journals)}")

    # =========================
    # ПОДГОТОВКА ДАННЫХ
    # =========================

    ids = []
    texts = []

    for journal in journals:
        journal_id, name, url, category = journal

        text = build_text(name, url, category)

        ids.append(journal_id)
        texts.append(text)

    # =========================
    # ГЕНЕРАЦИЯ ЭМБЕДДИНГОВ
    # =========================

    print("🧠 Генерация эмбеддингов...")

    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True
    )

    # =========================
    # ЗАПИСЬ В БД
    # =========================

    print("💾 Сохранение в БД...")

    for i in tqdm(range(len(ids))):
        cur.execute(
            "UPDATE journals SET embedding=%s WHERE id=%s",
            (embeddings[i].tolist(), ids[i])
        )

    conn.commit()

    cur.close()
    conn.close()

    print("✅ Эмбеддинги успешно обновлены!")


if __name__ == "__main__":
    main()