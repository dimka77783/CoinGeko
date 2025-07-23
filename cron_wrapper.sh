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
        log "Starting parser.py"
        /usr/bin/python3 parser.py
        PARSER_EXIT_CODE=$?

        if [ $PARSER_EXIT_CODE -eq 0 ]; then
            log "parser.py completed successfully"

            # Автоматический запуск parser_coingecko_social.py
            log "Starting parser_coingecko_social.py"
            sleep 5  # Небольшая пауза
            /usr/bin/python3 parser_coingecko_social.py
            COINGECKO_EXIT_CODE=$?

            if [ $COINGECKO_EXIT_CODE -eq 0 ]; then
                log "parser_coingecko_social.py completed successfully"
            else
                log "ERROR: parser_coingecko_social.py failed with exit code $COINGECKO_EXIT_CODE"
                exit $COINGECKO_EXIT_CODE
            fi
        else
            log "ERROR: parser.py failed with exit code $PARSER_EXIT_CODE"
            exit $PARSER_EXIT_CODE
        fi
        ;;

    "parser_id")
        log "Starting parser_id.py"
        /usr/bin/python3 parser_id.py
        ;;

    "updater")
        log "Starting updater.py"
        /usr/bin/python3 updater.py
        ;;

    "upcoming")
        log "Starting cryptoranc_upcoin_table.py (upcoming ICO parser)"
        /usr/bin/python3 cryptoranc_upcoin_table.py
        ;;

    "social-only")
        log "Starting parser_coingecko_social.py (standalone)"
        shift  # Удаляем первый аргумент
        /usr/bin/python3 parser_coingecko_social.py "$@"
        ;;

    "full")
        log "Starting full update (run.sh)"
        ./run.sh
        ;;

    "backup")
        log "Starting database backup"
        BACKUP_FILE="$BACKUP_DIR/crypto_db_$(date +%Y%m%d_%H%M%S).sql.gz"
        docker exec crypto_db pg_dump -U crypto_user crypto_db | gzip > "$BACKUP_FILE"
        log "Backup saved to: $BACKUP_FILE"
        # Удаление старых бэкапов (старше 7 дней)
        find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete
        ;;

    "stats")
        log "Getting database statistics"
        docker exec crypto_db psql -U crypto_user -d crypto_db -t -c "
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
            SELECT 'New today: ' || COUNT(*) FROM cryptocurrencies WHERE DATE(first_seen_at) = CURRENT_DATE
            UNION ALL
            SELECT '--- UPCOMING PROJECTS ---'
            UNION ALL
            SELECT 'Total upcoming: ' || total_projects FROM get_upcoming_stats()
            UNION ALL
            SELECT 'Active upcoming: ' || active_projects FROM get_upcoming_stats()
            UNION ALL
            SELECT 'This week: ' || this_week FROM get_upcoming_stats()
            UNION ALL
            SELECT 'This month: ' || this_month FROM get_upcoming_stats();"
        ;;

    "upcoming-stats")
        log "Getting upcoming projects statistics"
        docker exec crypto_db psql -U crypto_user -d crypto_db -c "
        SELECT 'UPCOMING PROJECTS STATISTICS' as info;
        SELECT * FROM get_upcoming_stats();
        SELECT 'PROJECTS THIS WEEK:' as info;
        SELECT project_name, project_symbol, project_type, launch_date, days_until_launch
        FROM upcoming_soon
        WHERE days_until_launch <= 7
        ORDER BY launch_date;
        "
        ;;

    *)
        log "ERROR: Unknown command: $1"
        echo "Usage: $0 {parser|parser_id|updater|upcoming|social-only|full|backup|stats|upcoming-stats}"
        echo ""
        echo "Commands:"
        echo "  parser          - Run parser.py and then parser_coingecko_social.py"
        echo "  parser_id       - Run parser_id.py to get CoinGecko IDs"
        echo "  updater         - Run updater.py for OHLC data"
        echo "  upcoming        - Run cryptoranc_upcoin_table.py for upcoming ICO projects"
        echo "  social-only     - Run only parser_coingecko_social.py"
        echo "  full            - Run full update (run.sh)"
        echo "  backup          - Create database backup"
        echo "  stats           - Show database statistics (including upcoming)"
        echo "  upcoming-stats  - Show detailed upcoming projects statistics"
        exit 1
        ;;
esac

# Проверка на ошибки
if [ $? -eq 0 ]; then
    log "Task completed successfully"
else
    log "ERROR: Task failed with exit code $?"
fi