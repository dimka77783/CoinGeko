#!/bin/bash
# Wrapper для запуска crypto parser из cron
# Обеспечивает правильное окружение

# Базовые настройки
PROJECT_DIR="/home/odinokov/PycharmProjects/parsercoin"
LOG_DIR="$PROJECT_DIR/logs"
BACKUP_DIR="$PROJECT_DIR/backups"

# Переход в рабочую директорию
cd "$PROJECT_DIR" || exit 1

# Настройка окружения
export PATH="/usr/local/bin:/usr/bin:/bin"
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_NAME="crypto_db"
export DB_USER="crypto_user"
export DB_PASSWORD="crypto_password"

# Создание необходимых директорий
mkdir -p "$LOG_DIR" "$BACKUP_DIR"

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Функция для записи в отдельный лог-файл
log_to_file() {
    local logfile="$LOG_DIR/$1_$(date +%Y%m%d).log"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$logfile"
}

# Проверка Docker
if ! docker ps >/dev/null 2>&1; then
    log "ERROR: Docker is not running or accessible"
    exit 1
fi

# Проверка контейнера БД
if ! docker ps | grep -q crypto_db; then
    log "WARNING: Database container not running, starting..."
    docker-compose up -d
    sleep 10
fi

# Выполнение команды переданной как аргумент
case "$1" in
    "parser")
        log_to_file "parser" "Starting parser.py"
        /usr/bin/python3 parser.py 2>&1 | tee -a "$LOG_DIR/parser_$(date +%Y%m%d).log"
        PARSER_EXIT_CODE=${PIPESTATUS[0]}

        if [ $PARSER_EXIT_CODE -eq 0 ]; then
            log_to_file "parser" "parser.py completed successfully"

            # Автоматический запуск parser_coingecko_social.py
            log_to_file "coingecko" "Starting parser_coingecko_social.py after parser.py"
            sleep 5  # Небольшая пауза
            /usr/bin/python3 parser_coingecko_social.py 2>&1 | tee -a "$LOG_DIR/coingecko_$(date +%Y%m%d).log"
            COINGECKO_EXIT_CODE=${PIPESTATUS[0]}

            if [ $COINGECKO_EXIT_CODE -eq 0 ]; then
                log_to_file "coingecko" "parser_coingecko_social.py completed successfully"
            else
                log_to_file "coingecko" "ERROR: parser_coingecko_social.py failed with exit code $COINGECKO_EXIT_CODE"
                exit $COINGECKO_EXIT_CODE
            fi
        else
            log_to_file "parser" "ERROR: parser.py failed with exit code $PARSER_EXIT_CODE"
            exit $PARSER_EXIT_CODE
        fi
        ;;

    "parser_id")
        log_to_file "parser_id" "Starting parser_id.py"
        /usr/bin/python3 parser_id.py 2>&1 | tee -a "$LOG_DIR/parser_id_$(date +%Y%m%d).log"
        ;;

    "updater")
        log_to_file "updater" "Starting updater.py"
        /usr/bin/python3 updater.py 2>&1 | tee -a "$LOG_DIR/updater_$(date +%Y%m%d).log"
        ;;

    "social-only")
        # Запуск только парсера социальных ссылок
        log_to_file "coingecko" "Starting parser_coingecko_social.py (standalone)"
        shift  # Удаляем первый аргумент (команду)
        /usr/bin/python3 parser_coingecko_social.py "$@" 2>&1 | tee -a "$LOG_DIR/coingecko_$(date +%Y%m%d).log"
        ;;

    "fresh_updater")
        log_to_file "fresh_updater" "Starting fresh_updater.py"
        /usr/bin/python3 fresh_updater.py 2>&1 | tee -a "$LOG_DIR/fresh_updater_$(date +%Y%m%d).log"
        ;;

    "cleanup_ohlc")
        log_to_file "cleanup" "Starting cleanup_ohlc.py"
        shift  # Удаляем первый аргумент
        /usr/bin/python3 cleanup_ohlc.py "$@" 2>&1 | tee -a "$LOG_DIR/cleanup_$(date +%Y%m%d).log"
        ;;

    "daily_report")
        log_to_file "daily_report" "Starting daily_report.py"
        /usr/bin/python3 daily_report.py 2>&1 | tee -a "$LOG_DIR/daily_report_$(date +%Y%m%d).log"
        ;;

    "full")
        log_to_file "full" "Starting full update (run.sh)"
        ./run.sh 2>&1 | tee -a "$LOG_DIR/full_$(date +%Y%m%d).log"
        ;;

    "backup")
        log "Starting database backup"
        BACKUP_FILE="$BACKUP_DIR/crypto_db_$(date +%Y%m%d_%H%M%S).sql.gz"
        docker exec crypto_db pg_dump -U crypto_user crypto_db | gzip > "$BACKUP_FILE"
        if [ $? -eq 0 ]; then
            log "Backup saved to: $BACKUP_FILE"
            # Удаление старых бэкапов (старше 7 дней)
            find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete
        else
            log "ERROR: Backup failed"
            exit 1
        fi
        ;;

    "stats")
        log "Getting database statistics"
        docker exec crypto_db psql -U crypto_user -d crypto_db -t -c "
            SELECT '===== Database Statistics ====='
            UNION ALL
            SELECT 'Timestamp: ' || NOW()::timestamp(0)
            UNION ALL
            SELECT 'Database size: ' || pg_size_pretty(pg_database_size('crypto_db'))
            UNION ALL
            SELECT 'Total coins: ' || COUNT(*) FROM cryptocurrencies
            UNION ALL
            SELECT 'Coins with OHLC: ' || COUNT(*) FROM cryptocurrencies WHERE ohlc_table_name IS NOT NULL
            UNION ALL
            SELECT 'Coins with CoinGecko ID: ' || COUNT(*) FROM cryptocurrencies WHERE coin_gecko_id IS NOT NULL
            UNION ALL
            SELECT 'Coins with social links: ' || COUNT(*) FROM cryptocurrencies WHERE telegram_channels IS NOT NULL OR twitter_accounts IS NOT NULL
            UNION ALL
            SELECT 'Updated today: ' || COUNT(*) FROM cryptocurrencies WHERE DATE(last_updated_at) = CURRENT_DATE
            UNION ALL
            SELECT 'Social links updated today: ' || COUNT(*) FROM cryptocurrencies WHERE DATE(social_links_updated) = CURRENT_DATE
            UNION ALL
            SELECT 'New today: ' || COUNT(*) FROM cryptocurrencies WHERE DATE(first_seen_at) = CURRENT_DATE;"
        ;;

    "health_check")
        # Проверка здоровья системы
        log "Performing health check"

        # Проверка Docker контейнера
        if docker ps | grep -q crypto_db; then
            echo "✅ Database container: Running"
        else
            echo "❌ Database container: Not running"
            exit 1
        fi

        # Проверка подключения к БД
        if docker exec crypto_db psql -U crypto_user -d crypto_db -c "SELECT 1;" > /dev/null 2>&1; then
            echo "✅ Database connection: OK"
        else
            echo "❌ Database connection: Failed"
            exit 1
        fi

        # Проверка места на диске
        DISK_USAGE=$(df -h "$PROJECT_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
        if [ "$DISK_USAGE" -lt 90 ]; then
            echo "✅ Disk usage: ${DISK_USAGE}%"
        else
            echo "⚠️  Disk usage: ${DISK_USAGE}% (High)"
        fi
        ;;

    "cleanup-logs")
        # Удаление старых логов
        log "Cleaning up old logs"
        find "$LOG_DIR" -name "*.log" -mtime +30 -delete
        log "Old logs removed"
        ;;

    *)
        log "ERROR: Unknown command: $1"
        echo "Usage: $0 {parser|parser_id|updater|social-only|fresh_updater|cleanup_ohlc|daily_report|full|backup|stats|health_check|cleanup-logs}"
        echo ""
        echo "Commands:"
        echo "  parser           - Run parser.py and then parser_coingecko_social.py"
        echo "  parser_id        - Run parser_id.py to get CoinGecko IDs"
        echo "  updater          - Run updater.py for OHLC data"
        echo "  social-only [args] - Run only parser_coingecko_social.py"
        echo "  fresh_updater    - Update recently added coins"
        echo "  cleanup_ohlc [args] - Clean up old OHLC tables"
        echo "  daily_report     - Generate daily report"
        echo "  full             - Run full update (run.sh)"
        echo "  backup           - Create database backup"
        echo "  stats            - Show database statistics"
        echo "  health_check     - Check system health"
        echo "  cleanup-logs     - Remove logs older than 30 days"
        exit 1
        ;;
esac

# Финальная проверка на ошибки
if [ $? -eq 0 ]; then
    log "Task completed successfully"
else
    log "ERROR: Task failed"
fi