-- Crypto Parser Database Schema
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
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)  -- ИЗМЕНЕНО: уникальность только по символу
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_crypto_symbol ON cryptocurrencies(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_added_date ON cryptocurrencies(added_date);
CREATE INDEX IF NOT EXISTS idx_crypto_gecko_id ON cryptocurrencies(coin_gecko_id);
CREATE INDEX IF NOT EXISTS idx_crypto_ohlc_table ON cryptocurrencies(ohlc_table_name);
CREATE INDEX IF NOT EXISTS idx_crypto_chain ON cryptocurrencies(chain);  -- ДОБАВЛЕНО: индекс для chain

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

-- УДАЛЯЕМ ВСЕ ФУНКЦИИ И ТРИГГЕРЫ СОЗДАНИЯ ТАБЛИЦ
-- Таблицы будут создаваться через updater.py

-- Представление для удобного просмотра
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
    c.last_updated_at,
    CASE
        WHEN c.ohlc_table_name IS NOT NULL THEN
            (SELECT COUNT(*)
             FROM information_schema.tables
             WHERE table_name = c.ohlc_table_name)
        ELSE 0
    END as table_exists,
    CASE
        WHEN c.ohlc_table_name IS NOT NULL AND
             EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = c.ohlc_table_name) THEN
            (SELECT COUNT(*)
             FROM information_schema.columns
             WHERE table_name = c.ohlc_table_name)
        ELSE 0
    END as column_count
FROM cryptocurrencies c
ORDER BY c.first_seen_at DESC;

-- Представление для мониторинга обновлений
CREATE OR REPLACE VIEW crypto_update_status AS
SELECT
    symbol,
    name,
    chain,
    coin_gecko_id IS NOT NULL as has_gecko_id,
    ohlc_table_name IS NOT NULL as has_ohlc_table,
    added_date,
    first_seen_at,
    last_updated_at,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_updated_at))/3600 as hours_since_update
FROM cryptocurrencies
ORDER BY last_updated_at DESC;

-- Представление для поиска проблемных записей
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
        ELSE 'OK'
    END as issue
FROM cryptocurrencies
WHERE name = 'Unknown'
   OR coin_gecko_id IS NULL
   OR (ohlc_table_name IS NULL AND coin_gecko_id IS NOT NULL)
ORDER BY added_date DESC;