-- Удаляем все существующие представления перед пересозданием
DROP VIEW IF EXISTS tokenomics_detailed CASCADE;
DROP VIEW IF EXISTS tokenomics_summary CASCADE;
DROP VIEW IF EXISTS crypto_issues CASCADE;
DROP VIEW IF EXISTS crypto_without_social CASCADE;
DROP VIEW IF EXISTS active_telegram_channels CASCADE;
DROP VIEW IF EXISTS telegram_stats CASCADE;
DROP VIEW IF EXISTS crypto_social_links CASCADE;
DROP VIEW IF EXISTS upcoming_soon CASCADE;
DROP VIEW IF EXISTS upcoming_projects_stats CASCADE;
DROP VIEW IF EXISTS crypto_stats CASCADE;

-- Пересоздаем все представления
-- Представление: общая статистика криптовалют
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
    c.telegram_table_name,
    c.telegram_message_count,
    c.telegram_last_parsed,
    array_length(c.telegram_channels, 1) as telegram_channels_count,
    array_length(c.twitter_accounts, 1) as twitter_accounts_count,
    array_length(c.official_websites, 1) as websites_count,
    c.social_links_updated,
    c.last_updated_at,
    CASE
        WHEN c.ohlc_table_name IS NOT NULL THEN
            (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = c.ohlc_table_name)
        ELSE 0
    END as ohlc_table_exists,
    CASE
        WHEN c.telegram_table_name IS NOT NULL THEN
            (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = c.telegram_table_name)
        ELSE 0
    END as telegram_table_exists
FROM cryptocurrencies c
ORDER BY c.first_seen_at DESC;

-- Представление: статистика upcoming проектов
CREATE OR REPLACE VIEW upcoming_projects_stats AS
SELECT
    project_name,
    project_symbol,
    project_type,
    initial_cap,
    ido_raise,
    launch_date,
    launch_date_original,
    moni_score,
    parsed_at,
    updated_at,
    CASE
        WHEN launch_date IS NOT NULL THEN EXTRACT(EPOCH FROM (launch_date::timestamp - CURRENT_TIMESTAMP))/86400
        ELSE NULL
    END as days_until_launch,
    CASE
        WHEN launch_date < CURRENT_DATE THEN 'Прошедший'
        WHEN launch_date = CURRENT_DATE THEN 'Сегодня'
        WHEN launch_date <= CURRENT_DATE + INTERVAL '7 days' THEN 'На этой неделе'
        WHEN launch_date <= CURRENT_DATE + INTERVAL '30 days' THEN 'В этом месяце'
        ELSE 'Будущий'
    END as launch_status
FROM cryptorank_upcoming
WHERE is_active = TRUE
ORDER BY launch_date ASC NULLS LAST;

-- Представление: ближайшие запуски
CREATE OR REPLACE VIEW upcoming_soon AS
SELECT
    project_name,
    project_symbol,
    project_type,
    initial_cap,
    ido_raise,
    launch_date,
    moni_score,
    EXTRACT(EPOCH FROM (launch_date::timestamp - CURRENT_TIMESTAMP))/86400 as days_until_launch
FROM cryptorank_upcoming
WHERE is_active = TRUE
  AND launch_date IS NOT NULL
  AND launch_date >= CURRENT_DATE
  AND launch_date <= CURRENT_DATE + INTERVAL '30 days'
ORDER BY launch_date ASC;

-- Представление: социальные ссылки
CREATE OR REPLACE VIEW crypto_social_links AS
SELECT
    c.id,
    c.symbol,
    c.name,
    c.telegram_channels,
    c.twitter_accounts,
    c.discord_links,
    c.reddit_communities,
    c.github_links,
    c.official_websites,
    c.instagram_accounts,
    c.social_links_updated,
    (
        COALESCE(array_length(c.telegram_channels, 1), 0) +
        COALESCE(array_length(c.twitter_accounts, 1), 0) +
        COALESCE(array_length(c.discord_links, 1), 0) +
        COALESCE(array_length(c.reddit_communities, 1), 0) +
        COALESCE(array_length(c.github_links, 1), 0) +
        COALESCE(array_length(c.official_websites, 1), 0) +
        COALESCE(array_length(c.instagram_accounts, 1), 0)
    ) as total_social_links,
    CASE
        WHEN c.social_links_updated IS NOT NULL THEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - c.social_links_updated))/3600
        ELSE NULL
    END as hours_since_updated
FROM cryptocurrencies c
WHERE
    c.telegram_channels IS NOT NULL OR
    c.twitter_accounts IS NOT NULL OR
    c.discord_links IS NOT NULL OR
    c.reddit_communities IS NOT NULL OR
    c.github_links IS NOT NULL OR
    c.official_websites IS NOT NULL OR
    c.instagram_accounts IS NOT NULL
ORDER BY total_social_links DESC;

-- Представление: мониторинг Telegram
CREATE OR REPLACE VIEW telegram_stats AS
SELECT
    c.symbol,
    c.name,
    c.telegram_table_name,
    c.telegram_message_count,
    c.telegram_channels,
    c.telegram_last_parsed,
    CASE
        WHEN c.telegram_last_parsed IS NOT NULL THEN EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - c.telegram_last_parsed))/3600
        ELSE NULL
    END as hours_since_parsed,
    CASE
        WHEN c.telegram_table_name IS NOT NULL AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = c.telegram_table_name) THEN 'Active'
        WHEN c.telegram_table_name IS NOT NULL THEN 'Table Missing'
        ELSE 'Not Parsed'
    END as status
FROM cryptocurrencies c
WHERE c.telegram_table_name IS NOT NULL OR c.telegram_channels IS NOT NULL
ORDER BY c.telegram_last_parsed DESC NULLS LAST;

-- Представление: активные Telegram каналы
CREATE OR REPLACE VIEW active_telegram_channels AS
SELECT DISTINCT
    c.symbol,
    c.name,
    unnest(c.telegram_channels) as channel_name,
    c.telegram_message_count,
    c.telegram_last_parsed
FROM cryptocurrencies c
WHERE c.telegram_channels IS NOT NULL AND array_length(c.telegram_channels, 1) > 0
ORDER BY c.telegram_message_count DESC;

-- Представление: криптовалюты без социальных ссылок
CREATE OR REPLACE VIEW crypto_without_social AS
SELECT
    c.id,
    c.symbol,
    c.name,
    c.coin_gecko_id,
    c.added_date,
    c.market_cap
FROM cryptocurrencies c
WHERE
    c.coin_gecko_id IS NOT NULL AND
    (c.telegram_channels IS NULL OR array_length(c.telegram_channels, 1) = 0) AND
    (c.twitter_accounts IS NULL OR array_length(c.twitter_accounts, 1) = 0) AND
    (c.official_websites IS NULL OR array_length(c.official_websites, 1) = 0)
ORDER BY c.market_cap DESC NULLS LAST;

-- Представление: проблемы в данных
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
        WHEN telegram_channels IS NULL OR array_length(telegram_channels, 1) = 0 THEN 'Нет Telegram каналов'
        WHEN telegram_table_name IS NULL AND telegram_channels IS NOT NULL THEN 'Нет таблицы сообщений'
        WHEN telegram_message_count = 0 AND telegram_table_name IS NOT NULL THEN 'Нет сообщений'
        WHEN social_links_updated IS NULL AND coin_gecko_id IS NOT NULL THEN 'Социальные ссылки не обновлены'
        ELSE 'OK'
    END as issue
FROM cryptocurrencies
WHERE name = 'Unknown'
   OR coin_gecko_id IS NULL
   OR (ohlc_table_name IS NULL AND coin_gecko_id IS NOT NULL)
   OR (telegram_channels IS NULL OR array_length(telegram_channels, 1) = 0)
   OR (telegram_table_name IS NULL AND telegram_channels IS NOT NULL)
   OR (telegram_message_count = 0 AND telegram_table_name IS NOT NULL)
   OR (social_links_updated IS NULL AND coin_gecko_id IS NOT NULL)
ORDER BY added_date DESC;

-- Представление: tokenomics_summary
CREATE OR REPLACE VIEW tokenomics_summary AS
SELECT
    t.id,
    t.project_name,
    t.tokenomics,
    t.parsed_at,
    t.updated_at,
    t.tokenomics->'distribution' as distribution,
    t.tokenomics->'initial_values' as initial_values,
    t.tokenomics->'token_allocation' as token_allocation,
    t.tokenomics->'source' as source,
    t.tokenomics->'scraped_at' as scraped_at,
    -- Извлекаем конкретные значения из distribution
    (SELECT COUNT(*) FROM jsonb_object_keys(t.tokenomics->'distribution')) as distribution_categories_count,
    -- Проверяем наличие ключевых данных
    CASE
        WHEN t.tokenomics->'distribution' IS NOT NULL AND jsonb_typeof(t.tokenomics->'distribution') = 'object' THEN true
        ELSE false
    END as has_distribution,
    CASE
        WHEN t.tokenomics->'initial_values' IS NOT NULL AND jsonb_typeof(t.tokenomics->'initial_values') = 'object' THEN true
        ELSE false
    END as has_initial_values,
    CASE
        WHEN t.tokenomics->'token_allocation' IS NOT NULL AND jsonb_typeof(t.tokenomics->'token_allocation') = 'object' THEN true
        ELSE false
    END as has_token_allocation
FROM cryptorank_tokenomics t
ORDER BY t.parsed_at DESC;

-- Новое представление: детализированный анализ токеномики
CREATE OR REPLACE VIEW tokenomics_detailed AS
SELECT
    t.project_name,
    t.parsed_at,

    -- Распределение токенов
    t.tokenomics->'distribution' as distribution_data,

    -- Начальные значения
    t.tokenomics->'initial_values'->>'Total supply' as total_supply,
    t.tokenomics->'initial_values'->>'Circulating supply' as circulating_supply,
    t.tokenomics->'initial_values'->>'Max supply' as max_supply,
    t.tokenomics->'initial_values'->>'Initial price' as initial_price,
    t.tokenomics->'initial_values'->>'Market cap' as market_cap,

    -- Аллокация токенов
    t.tokenomics->'token_allocation' as allocation_data,

    -- Статистика
    (SELECT COUNT(*) FROM jsonb_object_keys(COALESCE(t.tokenomics->'distribution', '{}'::jsonb))) as categories_count,

    -- Проверки качества данных
    CASE
        WHEN (SELECT COUNT(*) FROM jsonb_object_keys(COALESCE(t.tokenomics->'distribution', '{}'::jsonb))) > 0 THEN 'Complete'
        WHEN t.tokenomics->'initial_values' IS NOT NULL THEN 'Partial'
        ELSE 'Minimal'
    END as data_quality

FROM cryptorank_tokenomics t
ORDER BY t.parsed_at DESC;

-- Выводим информацию о созданных представлениях
SELECT 'Views recreated successfully!' as status;