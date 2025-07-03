#!/usr/bin/env python3
"""
Парсер ID монет через CoinGecko API List
Загружает полный список монет, ищет совпадения по имени и обновляет ID в БД
"""
import aiohttp
import asyncio
import re
import os
import psycopg2
from psycopg2.pool import SimpleConnectionPool
import logging
import time
import sys

# Настройка логирования
log_level = logging.DEBUG if os.environ.get('DEBUG', '').lower() == 'true' else logging.INFO
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки
API_URL = "https://api.coingecko.com/api/v3/coins/list"

# База данных
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432'),
    'database': os.environ.get('DB_NAME', 'crypto_db'),
    'user': os.environ.get('DB_USER', 'crypto_user'),
    'password': os.environ.get('DB_PASSWORD', 'crypto_password')
}

# Глобальный пул соединений
db_pool = None


def init_db_pool():
    """Инициализация пула соединений к БД"""
    global db_pool
    try:
        db_pool = SimpleConnectionPool(1, 5, **DB_CONFIG)
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка создания пула БД: {e}")
        return False


def get_db_connection():
    """Получение соединения из пула"""
    if db_pool:
        return db_pool.getconn()
    return None


def put_db_connection(conn):
    """Возврат соединения в пул"""
    if db_pool and conn:
        db_pool.putconn(conn)


def close_db_pool():
    """Закрытие пула соединений"""
    global db_pool
    if db_pool:
        db_pool.closeall()
        db_pool = None


def get_coins_without_id():
    """Получает монеты без coin_gecko_id из БД"""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, symbol
            FROM cryptocurrencies 
            WHERE coin_gecko_id IS NULL 
            AND name IS NOT NULL 
            AND name != ''
            AND name != 'Unknown'
            ORDER BY added_date DESC
        """)

        coins = cursor.fetchall()
        cursor.close()

        return [{'db_id': coin[0], 'name': coin[1], 'symbol': coin[2]} for coin in coins]

    except Exception as e:
        logger.error(f"❌ Ошибка получения монет из БД: {e}")
        return []
    finally:
        put_db_connection(conn)


def update_coin_id(db_id, coin_gecko_id):
    """Обновляет coin_gecko_id в БД"""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE cryptocurrencies 
            SET coin_gecko_id = %s 
            WHERE id = %s
        """, (coin_gecko_id, db_id))

        conn.commit()
        cursor.close()
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка обновления БД: {e}")
        return False
    finally:
        put_db_connection(conn)


async def fetch_coins_list():
    """Загружает полный список монет с CoinGecko API"""
    logger.info("📥 Загрузка полного списка монет с CoinGecko API...")

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9'
    }

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(API_URL, headers=headers, ssl=False) as response:
                if response.status == 200:
                    coins_list = await response.json()
                    logger.info(f"✅ Загружено {len(coins_list)} монет")
                    return coins_list
                else:
                    logger.error(f"❌ Ошибка загрузки: HTTP {response.status}")
                    return None

    except Exception as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        return None


def normalize_text(text):
    """Нормализует текст для сравнения"""
    if not text:
        return ""

    # Приводим к нижнему регистру
    text = text.lower().strip()

    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text)

    # Убираем специальные символы для более гибкого сравнения
    text_clean = re.sub(r'[^\w\s]', '', text)

    return text, text_clean


def find_coin_by_name_and_symbol(coins_list, db_coin):
    """Ищет монету в списке по имени и символу с различными стратегиями"""

    db_name = db_coin['name']
    db_symbol = db_coin['symbol']

    # Нормализуем данные из БД
    db_name_norm, db_name_clean = normalize_text(db_name)
    db_symbol_norm = db_symbol.lower().strip() if db_symbol else ""

    logger.debug(f"  🔍 Поиск: '{db_name}' ({db_symbol})")

    # Стратегия 1: Точное совпадение имени и символа
    for coin in coins_list:
        api_name_norm, api_name_clean = normalize_text(coin.get('name', ''))
        api_symbol_norm = coin.get('symbol', '').lower().strip()

        if (db_name_norm == api_name_norm and
                db_symbol_norm == api_symbol_norm and
                db_symbol_norm):
            logger.debug(f"    ✅ Точное совпадение имени и символа: {coin['id']}")
            return coin['id'], "exact_name_symbol"

    # Стратегия 2: Точное совпадение только по символу (если символ достаточно уникален)
    if db_symbol and len(db_symbol) >= 3:
        for coin in coins_list:
            api_symbol_norm = coin.get('symbol', '').lower().strip()
            if db_symbol_norm == api_symbol_norm:
                logger.debug(f"    ✅ Точное совпадение символа: {coin['id']}")
                return coin['id'], "exact_symbol"

    # Стратегия 3: Точное совпадение имени (без символа)
    for coin in coins_list:
        api_name_norm, api_name_clean = normalize_text(coin.get('name', ''))
        if db_name_norm == api_name_norm:
            logger.debug(f"    ✅ Точное совпадение имени: {coin['id']}")
            return coin['id'], "exact_name"

    # Стратегия 4: Совпадение очищенного имени (без спецсимволов)
    if db_name_clean and len(db_name_clean) >= 3:
        for coin in coins_list:
            api_name_norm, api_name_clean = normalize_text(coin.get('name', ''))
            if db_name_clean == api_name_clean and api_name_clean:
                logger.debug(f"    ⚠️ Совпадение очищенного имени: {coin['id']}")
                return coin['id'], "clean_name"

    # Стратегия 5: Частичное совпадение имен (осторожно)
    if len(db_name_norm) >= 5:  # Минимум 5 символов для частичного поиска
        for coin in coins_list:
            api_name_norm, api_name_clean = normalize_text(coin.get('name', ''))

            # Проверяем содержание одного в другом
            if (db_name_norm in api_name_norm or api_name_norm in db_name_norm) and len(api_name_norm) >= 3:
                # Дополнительная проверка по символу если есть
                if db_symbol:
                    api_symbol_norm = coin.get('symbol', '').lower().strip()
                    if db_symbol_norm == api_symbol_norm:
                        logger.debug(f"    ⚠️ Частичное совпадение имени + символ: {coin['id']}")
                        return coin['id'], "partial_name_symbol"
                else:
                    # Без символа - только если совпадение достаточно точное
                    if len(api_name_norm) <= len(db_name_norm) * 1.5:  # Не слишком длинное имя
                        logger.debug(f"    ⚠️ Частичное совпадение имени: {coin['id']}")
                        return coin['id'], "partial_name"

    return None, "not_found"


def process_coins_matching(coins_list, db_coins):
    """Обрабатывает поиск совпадений и обновление БД"""

    logger.info(f"🔍 Поиск совпадений для {len(db_coins)} монет...")

    results = {
        'exact_name_symbol': 0,
        'exact_symbol': 0,
        'exact_name': 0,
        'clean_name': 0,
        'partial_name_symbol': 0,
        'partial_name': 0,
        'not_found': 0,
        'db_errors': 0
    }

    updated_coins = []

    for i, db_coin in enumerate(db_coins):
        logger.info(f"[{i + 1}/{len(db_coins)}] {db_coin['name']} ({db_coin['symbol']})")

        coin_id, match_type = find_coin_by_name_and_symbol(coins_list, db_coin)

        if coin_id:
            # Обновляем в БД
            if update_coin_id(db_coin['db_id'], coin_id):
                updated_coins.append({
                    'name': db_coin['name'],
                    'symbol': db_coin['symbol'],
                    'id': coin_id,
                    'match_type': match_type
                })
                logger.info(f"  ✅ Обновлен: {coin_id} (тип: {match_type})")
                results[match_type] += 1
            else:
                logger.error(f"  ❌ Ошибка обновления БД")
                results['db_errors'] += 1
        else:
            logger.warning(f"  ❌ Не найден")
            results['not_found'] += 1

    return results, updated_coins


async def main():
    """Главная асинхронная функция"""
    print("=" * 70)
    print("🔍 ПАРСЕР ID МОНЕТ ЧЕРЕЗ COINGECKO API LIST")
    print(f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API URL: {API_URL}")
    print("=" * 70)

    # Инициализация БД
    if not init_db_pool():
        sys.exit(1)

    # Получаем монеты без ID из БД
    db_coins = get_coins_without_id()
    if not db_coins:
        logger.info("✅ Все монеты уже имеют coin_gecko_id")
        close_db_pool()
        return

    logger.info(f"📊 Найдено монет без ID в БД: {len(db_coins)}")

    # Загружаем список монет с API
    coins_list = await fetch_coins_list()
    if not coins_list:
        logger.error("❌ Не удалось загрузить список монет")
        close_db_pool()
        return

    try:
        # Обрабатываем совпадения
        results, updated_coins = process_coins_matching(coins_list, db_coins)

        # Выводим статистику
        logger.info(f"\n📊 Результаты обработки:")
        logger.info(f"  ✅ Точное совпадение (имя + символ): {results['exact_name_symbol']}")
        logger.info(f"  ✅ Точное совпадение (только символ): {results['exact_symbol']}")
        logger.info(f"  ✅ Точное совпадение (только имя): {results['exact_name']}")
        logger.info(f"  ⚠️ Совпадение очищенного имени: {results['clean_name']}")
        logger.info(f"  ⚠️ Частичное совпадение (имя + символ): {results['partial_name_symbol']}")
        logger.info(f"  ⚠️ Частичное совпадение (только имя): {results['partial_name']}")
        logger.info(f"  ❌ Не найдено: {results['not_found']}")
        logger.info(f"  ❌ Ошибки БД: {results['db_errors']}")

        total_updated = sum(results[key] for key in results if key not in ['not_found', 'db_errors'])
        total_processed = len(db_coins)

        if total_processed > 0:
            success_rate = (total_updated / total_processed) * 100
            logger.info(f"\n📈 Общая успешность: {success_rate:.1f}% ({total_updated}/{total_processed})")

        # Показываем примеры обновленных монет
        if updated_coins:
            logger.info(f"\n💾 Примеры обновленных монет:")
            for coin in updated_coins[:10]:  # Показываем первые 10
                logger.info(f"  • {coin['name']} ({coin['symbol']}) -> {coin['id']} [{coin['match_type']}]")

            if len(updated_coins) > 10:
                logger.info(f"  ... и еще {len(updated_coins) - 10} монет")

    finally:
        # Очищаем список из памяти
        logger.info(f"\n🗑️ Удаление списка монет из памяти...")
        coins_list.clear()
        del coins_list
        logger.info(f"✅ Список удален")

    # Закрываем пул БД
    close_db_pool()

    print("\n✅ Парсер ID завершил работу")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())