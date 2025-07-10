-- Crypto Parser Database Schema with Telegram Support
-- БЕЗ ДАТ В ИМЕНАХ ТАБЛИЦ

-- Основная таблица криптовалют
CREATE TABLE IF NOT EXISTS cryptocurrencies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    chain VARCHAR(100),
    price VARCHAR(100),
    change_24h VARCHAR(50),
    market_cap VARCHAR(100),
    fdv VARCHAR(100),
    added_date DATE,
    added_raw VARCHAR(100),
    coin_gecko_id VARCHAR(255),
    ohlc_table_name VARCHAR(100),
    telegram_table_name VARCHAR(100),  -- ДОБАВЛЕНО: имя таблицы с Telegram данными
    telegram_message_count INTEGER DEFAULT 0,  -- ДОБАВЛЕНО: количество сообщений
    telegram_channels TEXT[],  -- ДОБАВЛЕНО: список найденных каналов
    telegram_last_parsed TIMESTAMP,  -- ДОБАВЛЕНО: последний парсинг
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_crypto_symbol ON cryptocurrencies(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_added_date ON cryptocurrencies(added_date);
CREATE INDEX IF NOT EXISTS idx_crypto_gecko_id ON cryptocurrencies(coin_gecko_id);
CREATE INDEX IF NOT EXISTS idx_crypto_ohlc_table ON cryptocurrencies(ohlc_table_name);
CREATE INDEX IF NOT EXISTS idx_crypto_chain ON cryptocurrencies(chain);
CREATE INDEX IF NOT EXISTS idx_crypto_telegram_table ON cryptocurrencies(telegram_table_name);  -- ДОБАВЛЕНО

-- Функция для обновления last_updated_at
CREATE OR REPLACE FUNCTION update_last_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер обновления времени
DROP TRIGGER IF EXISTS update_crypto_last_updated ON cryptocurrencies;
CREATE TRIGGER update_crypto_last_updated
    BEFORE UPDATE ON cryptocurrencies
    FOR EACH ROW
    EXECUTE FUNCTION update_last_updated_at();

-- Шаблон таблицы для Telegram сообщений (создается динамически для каждой монеты)
-- Пример: telegram_raco, telegram_btc, и т.д.
/*
CREATE TABLE IF NOT EXISTS telegram_SYMBOL (
    id SERIAL PRIMARY KEY,
    crypto_id INTEGER REFERENCES cryptocurrencies(id),
    message_id VARCHAR(100),
    message_text TEXT,
    message_date TIMESTAMP,
    views INTEGER DEFAULT 0,
    has_media BOOLEAN DEFAULT FALSE,
    has_photo BOOLEAN DEFAULT FALSE,
    has_video BOOLEAN DEFAULT FALSE,
    links TEXT[],
    message_url VARCHAR(500),
    channel_name VARCHAR(255),
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Анализ сообщений
    sentiment VARCHAR(20),  -- positive, negative, neutral
    mentions_price BOOLEAN DEFAULT FALSE,
    mentions_buy BOOLEAN DEFAULT FALSE,
    mentions_sell BOOLEAN DEFAULT FALSE,
    extracted_price NUMERIC,
    extracted_percentage NUMERIC,

    UNIQUE(message_id, channel_name)
);
*/

-- Представление для удобного просмотра с Telegram данными
CREATE OR REPLACE VIEW crypto_stats AS
SELECT
    c.id,
    c.name,
    c.symbol,
    c.chain,
    c.added_date,
    c.first_seen_at::date as first_seen_date,
    CURRENT_DATE - c.added_date as age_days,
    CURRENT_DATE - c.first_seen_at::date as days_in_db,
    c.coin_gecko_id,
    c.ohlc_table_name,
    c.telegram_table_name,  -- ДОБАВЛЕНО
    c.telegram_message_count,  -- ДОБАВЛЕНО
    c.telegram_last_parsed,  -- ДОБАВЛЕНО
    c.last_updated_at,
    CASE
        WHEN c.ohlc_table_name IS NOT NULL THEN
            (SELECT COUNT(*)
             FROM information_schema.tables
             WHERE table_name = c.ohlc_table_name)
        ELSE 0
    END as ohlc_table_exists,
    CASE
        WHEN c.telegram_table_name IS NOT NULL THEN
            (SELECT COUNT(*)
             FROM information_schema.tables
             WHERE table_name = c.telegram_table_name)
        ELSE 0
    END as telegram_table_exists  -- ДОБАВЛЕНО
FROM cryptocurrencies c
ORDER BY c.first_seen_at DESC;

-- Представление для мониторинга Telegram данных
CREATE OR REPLACE VIEW telegram_stats AS
SELECT
    c.symbol,
    c.name,
    c.telegram_table_name,
    c.telegram_message_count,
    c.telegram_channels,
    c.telegram_last_parsed,
    CASE
        WHEN c.telegram_last_parsed IS NOT NULL THEN
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - c.telegram_last_parsed))/3600
        ELSE NULL
    END as hours_since_parsed,
    CASE
        WHEN c.telegram_table_name IS NOT NULL AND
             EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = c.telegram_table_name) THEN
            'Active'
        WHEN c.telegram_table_name IS NOT NULL THEN
            'Table Missing'
        ELSE
            'Not Parsed'
    END as status
FROM cryptocurrencies c
WHERE c.telegram_table_name IS NOT NULL
   OR c.telegram_channels IS NOT NULL
ORDER BY c.telegram_last_parsed DESC NULLS LAST;

-- Представление для поиска активных Telegram каналов
CREATE OR REPLACE VIEW active_telegram_channels AS
SELECT DISTINCT
    c.symbol,
    c.name,
    unnest(c.telegram_channels) as channel_name,
    c.telegram_message_count,
    c.telegram_last_parsed
FROM cryptocurrencies c
WHERE c.telegram_channels IS NOT NULL
  AND array_length(c.telegram_channels, 1) > 0
ORDER BY c.telegram_message_count DESC;

-- Функция для анализа сообщений
CREATE OR REPLACE FUNCTION analyze_telegram_message(message_text TEXT)
RETURNS TABLE(
    sentiment VARCHAR(20),
    mentions_price BOOLEAN,
    mentions_buy BOOLEAN,
    mentions_sell BOOLEAN,
    extracted_price NUMERIC,
    extracted_percentage NUMERIC
) AS $$
DECLARE
    text_lower TEXT;
    price_match TEXT;
    percentage_match TEXT;
BEGIN
    text_lower := lower(message_text);

    -- Определение настроения
    IF text_lower ~ '(moon|bullish|buy|pump|gem|profit|🚀|📈|💎)' THEN
        sentiment := 'positive';
    ELSIF text_lower ~ '(dump|sell|bearish|crash|scam|rug|📉|🔴)' THEN
        sentiment := 'negative';
    ELSE
        sentiment := 'neutral';
    END IF;

    -- Проверка упоминаний
    mentions_price := text_lower ~ '(price|цена|\$|usd|usdt)';
    mentions_buy := text_lower ~ '(buy|купить|покупка|long)';
    mentions_sell := text_lower ~ '(sell|продать|продажа|short)';

    -- Извлечение цены
    price_match := substring(message_text from '\$?\d+\.?\d*');
    IF price_match IS NOT NULL THEN
        extracted_price := regexp_replace(price_match, '[^0-9.]', '', 'g')::NUMERIC;
    END IF;

    -- Извлечение процентов
    percentage_match := substring(message_text from '\d+\.?\d*%');
    IF percentage_match IS NOT NULL THEN
        extracted_percentage := regexp_replace(percentage_match, '[^0-9.]', '', 'g')::NUMERIC;
    END IF;

    RETURN QUERY SELECT sentiment, mentions_price, mentions_buy, mentions_sell, extracted_price, extracted_percentage;
END;
$$ LANGUAGE plpgsql;

-- Представление для анализа настроений по монетам
CREATE OR REPLACE VIEW telegram_sentiment_analysis AS
WITH sentiment_data AS (
    SELECT
        c.symbol,
        c.name,
        c.telegram_table_name,
        'positive' as sentiment,
        0 as count
    FROM cryptocurrencies c
    WHERE c.telegram_table_name IS NOT NULL
)
SELECT
    symbol,
    name,
    telegram_table_name,
    'Analysis pending' as sentiment_summary,
    0 as total_messages,
    0 as positive_percent,
    0 as negative_percent,
    0 as neutral_percent
FROM sentiment_data
GROUP BY symbol, name, telegram_table_name;

-- Функция для получения последних сообщений монеты
CREATE OR REPLACE FUNCTION get_latest_telegram_messages(
    p_symbol VARCHAR,
    p_limit INTEGER DEFAULT 10
)
RETURNS TABLE(
    message_text TEXT,
    message_date TIMESTAMP,
    views INTEGER,
    channel_name VARCHAR,
    message_url VARCHAR
) AS $$
DECLARE
    table_name VARCHAR;
    query TEXT;
BEGIN
    -- Получаем имя таблицы
    SELECT telegram_table_name INTO table_name
    FROM cryptocurrencies
    WHERE symbol = p_symbol;

    IF table_name IS NULL THEN
        RETURN;
    END IF;

    -- Динамический запрос
    query := format('
        SELECT message_text, message_date, views, channel_name, message_url
        FROM %I
        ORDER BY message_date DESC
        LIMIT %s
    ', table_name, p_limit);

    RETURN QUERY EXECUTE query;
END;
$$ LANGUAGE plpgsql;

-- Представление для поиска проблемных записей (обновлено)
CREATE OR REPLACE VIEW crypto_issues AS
SELECT
    id,
    symbol,
    name,
    chain,
    added_date,
    CASE
        WHEN name = 'Unknown' THEN 'Неизвестное имя'
        WHEN coin_gecko_id IS NULL THEN 'Нет CoinGecko ID'
        WHEN ohlc_table_name IS NULL AND coin_gecko_id IS NOT NULL THEN 'Нет OHLC таблицы'
        WHEN telegram_table_name IS NULL THEN 'Нет Telegram данных'
        WHEN telegram_message_count = 0 AND telegram_table_name IS NOT NULL THEN 'Нет сообщений'
        ELSE 'OK'
    END as issue
FROM cryptocurrencies
WHERE name = 'Unknown'
   OR coin_gecko_id IS NULL
   OR (ohlc_table_name IS NULL AND coin_gecko_id IS NOT NULL)
   OR telegram_table_name IS NULL
   OR (telegram_message_count = 0 AND telegram_table_name IS NOT NULL)
ORDER BY added_date DESC;