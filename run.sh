#!/bin/bash

# Crypto Parser - Простой скрипт запуска
# Запускает парсинг новых монет, получение ID и обновление OHLC

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Настройки БД
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-crypto_db}"
export DB_USER="${DB_USER:-crypto_user}"
export DB_PASSWORD="${DB_PASSWORD:-crypto_password}"
export PARSER_MODE="${PARSER_MODE:-safe}"

# Директории
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/crypto_$(date +%Y%m%d_%H%M%S).log"

# Создание директории для логов
mkdir -p "$LOG_DIR"

# Функция логирования
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

# Начало работы
log "${GREEN}🚀 Crypto Parser - $(date)${NC}"
log "================================"

# Проверка Docker
if ! command -v docker &> /dev/null; then
    log "${RED}❌ Docker не установлен${NC}"
    exit 1
fi

# Проверка БД
if ! docker ps | grep -q crypto_db; then
    log "${YELLOW}⚠️  БД не запущена. Пытаемся запустить...${NC}"
    docker-compose up -d
    sleep 5
fi

# Проверка подключения к БД
if docker exec crypto_db pg_isready -U crypto_user > /dev/null 2>&1; then
    log "${GREEN}✅ БД работает${NC}"
else
    log "${RED}❌ БД недоступна${NC}"
    exit 1
fi

# Проверка Python и зависимостей
if ! python3 -c "import psycopg2" 2>/dev/null; then
    log "${YELLOW}⚠️  psycopg2 не установлен. Установите: sudo apt-get install python3-psycopg2${NC}"
    exit 1
fi

# ЭТАП 1: Парсинг новых монет
log ""
log "${GREEN}📊 Этап 1: Парсинг новых монет...${NC}"
log "--------------------------------"

if [ -f "$SCRIPT_DIR/parser.py" ]; then
    python3 "$SCRIPT_DIR/parser.py" >> "$LOG_FILE" 2>&1
    parser_exit_code=$?
    if [ $parser_exit_code -eq 0 ]; then
        log "${GREEN}✅ Парсинг завершен${NC}"
    else
        log "${RED}❌ Ошибка парсинга (код: $parser_exit_code)${NC}"
    fi
else
    log "${RED}❌ Файл parser.py не найден${NC}"
    parser_exit_code=1
fi

# Пауза между этапами
sleep 5

# ЭТАП 2: Получение ID монет
log ""
log "${BLUE}🔍 Этап 2: Получение ID монет с CoinGecko...${NC}"
log "--------------------------------------------"

if [ -f "$SCRIPT_DIR/parser_id.py" ]; then
    python3 "$SCRIPT_DIR/parser_id.py" >> "$LOG_FILE" 2>&1
    id_parser_exit_code=$?
    if [ $id_parser_exit_code -eq 0 ]; then
        log "${GREEN}✅ Получение ID завершено${NC}"
    else
        log "${RED}❌ Ошибка получения ID (код: $id_parser_exit_code)${NC}"
    fi
else
    log "${RED}❌ Файл parser_id.py не найден${NC}"
    id_parser_exit_code=1
fi

# Пауза между этапами
sleep 10

# ЭТАП 3: Обновление OHLC
log ""
log "${GREEN}🔄 Этап 3: Обновление OHLC данных...${NC}"
log "-----------------------------------"

if [ -f "$SCRIPT_DIR/updater.py" ]; then
    python3 "$SCRIPT_DIR/updater.py" >> "$LOG_FILE" 2>&1
    updater_exit_code=$?
    if [ $updater_exit_code -eq 0 ]; then
        log "${GREEN}✅ Обновление OHLC завершено${NC}"
    else
        log "${RED}❌ Ошибка обновления OHLC (код: $updater_exit_code)${NC}"
    fi
else
    log "${RED}❌ Файл updater.py не найден${NC}"
    updater_exit_code=1
fi

# Краткая статистика
log ""
log "${GREEN}📈 Статистика:${NC}"
log "-------------"

docker exec crypto_db psql -U crypto_user -d crypto_db -t -c "
SELECT
    'Всего монет: ' || COUNT(*)
FROM cryptocurrencies
UNION ALL
SELECT
    'Монет с символами: ' || COUNT(*)
FROM cryptocurrencies
WHERE symbol IS NOT NULL AND symbol != ''
UNION ALL
SELECT
    'Монет с CoinGecko ID: ' || COUNT(*)
FROM cryptocurrencies
WHERE coin_gecko_id IS NOT NULL
UNION ALL
SELECT
    'Монет с OHLC: ' || COUNT(*)
FROM cryptocurrencies
WHERE ohlc_table_name IS NOT NULL
UNION ALL
SELECT
    'Добавлено сегодня: ' || COUNT(*)
FROM cryptocurrencies
WHERE added_date = CURRENT_DATE;
" | while read line; do
    log "$line"
done

# Сводка по этапам
log ""
log "${GREEN}📋 Сводка выполнения:${NC}"
log "--------------------"

if [ $parser_exit_code -eq 0 ]; then
    log "${GREEN}✅ Этап 1 (Парсинг): УСПЕШНО${NC}"
else
    log "${RED}❌ Этап 1 (Парсинг): ОШИБКА${NC}"
fi

if [ $id_parser_exit_code -eq 0 ]; then
    log "${GREEN}✅ Этап 2 (Получение ID): УСПЕШНО${NC}"
else
    log "${RED}❌ Этап 2 (Получение ID): ОШИБКА${NC}"
fi

if [ $updater_exit_code -eq 0 ]; then
    log "${GREEN}✅ Этап 3 (Обновление OHLC): УСПЕШНО${NC}"
else
    log "${RED}❌ Этап 3 (Обновление OHLC): ОШИБКА${NC}"
fi

log ""
log "${GREEN}✅ Готово!${NC}"
log "Лог сохранен: $LOG_FILE"
log "================================"

# Показать последние ошибки если есть
if grep -q "ERROR\|ОШИБКА\|Error" "$LOG_FILE"; then
    log ""
    log "${YELLOW}⚠️  Обнаружены ошибки в логе:${NC}"
    grep -E "ERROR|ОШИБКА|Error" "$LOG_FILE" | tail -5
fi

# Общий код возврата
overall_exit_code=0
if [ $parser_exit_code -ne 0 ] || [ $id_parser_exit_code -ne 0 ] || [ $updater_exit_code -ne 0 ]; then
    overall_exit_code=1
fi

exit $overall_exit_code