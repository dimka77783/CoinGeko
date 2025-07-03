# Crypto Parser - Руководство по развертыванию на VPS

## Содержание
1. [Требования](#требования)
2. [Подготовка сервера](#подготовка-сервера)
3. [Установка зависимостей](#установка-зависимостей)
4. [Клонирование проекта](#клонирование-проекта)
5. [Настройка базы данных](#настройка-базы-данных)
6. [Настройка приложения](#настройка-приложения)
7. [Первый запуск](#первый-запуск)
8. [Автоматизация через Cron](#автоматизация-через-cron)
9. [Мониторинг и обслуживание](#мониторинг-и-обслуживание)
10. [Решение проблем](#решение-проблем)

## Требования

### Минимальные требования к серверу:
- **ОС**: Ubuntu 20.04/22.04 или Debian 10/11
- **CPU**: 2 ядра (рекомендуется)
- **RAM**: 4 GB (рекомендуется для стабильной работы)
- **Диск**: 20 GB свободного места
- **Сеть**: Стабильное интернет-соединение

### Необходимое ПО:
- Python 3.8+
- Docker и Docker Compose
- PostgreSQL (через Docker)
- Git
- aiohttp, psycopg2 (Python библиотеки)

## Подготовка сервера

### 1. Подключение к серверу
```bash
ssh user@your-server-ip
```

### 2. Обновление системы
```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Установка базовых утилит
```bash
sudo apt install -y curl wget git nano htop unzip
```

## Установка зависимостей

### 1. Установка Python и pip
```bash
# Установка Python 3 и необходимых пакетов
sudo apt install -y python3 python3-pip python3-venv python3-dev

# Установка системных библиотек для psycopg2
sudo apt install -y libpq-dev gcc

# Проверка версии
python3 --version
```

### 2. Установка Docker
```bash
# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Добавление пользователя в группу docker
sudo usermod -aG docker $USER

# Выйти и зайти снова для применения изменений
exit
# Подключиться заново
ssh user@your-server-ip

# Проверка Docker
docker --version
```

### 3. Установка Docker Compose
```bash
# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Проверка
docker-compose --version
```

### 4. Установка PostgreSQL клиента (опционально)
```bash
sudo apt install -y postgresql-client
```

## Клонирование проекта

### 1. Создание рабочей директории
```bash
# Создание директории для проектов
mkdir -p ~/projects
cd ~/projects
```

### 2. Клонирование репозитория
```bash
# Если есть Git репозиторий
git clone https://github.com/yourusername/crypto-parser.git
cd crypto-parser

# Или создайте директорию и скопируйте файлы
mkdir crypto-parser
cd crypto-parser
```

### 3. Создание структуры проекта
```bash
# Создание необходимых директорий
mkdir -p logs backups

# Проверка структуры
ls -la
```

### 4. Копирование файлов проекта
Скопируйте следующие файлы в директорию проекта:
- `docker-compose.yml`
- `init_db.sql`
- `parser.py` - основной парсер новых монет
- `parser_id.py` - получение CoinGecko ID монет
- `updater.py` - обновление OHLC данных
- `run.sh` - скрипт полного цикла обновления
- `clean_db.py` - скрипт очистки базы данных
- `requirements.txt`

## Настройка базы данных

### 1. Проверка docker-compose.yml
```bash
nano docker-compose.yml
```

Убедитесь, что настройки корректны:
```yaml
services:
  postgres:
    image: postgres:15-alpine
    container_name: crypto_db
    environment:
      POSTGRES_DB: crypto_db
      POSTGRES_USER: crypto_user
      POSTGRES_PASSWORD: crypto_password  # Измените на безопасный пароль!
```

### 2. Запуск базы данных
```bash
# Запуск PostgreSQL в фоновом режиме
docker-compose up -d

# Проверка статуса
docker ps

# Просмотр логов
docker-compose logs -f postgres
```

### 3. Проверка подключения
```bash
# Тест подключения
docker exec -it crypto_db psql -U crypto_user -d crypto_db -c "SELECT version();"
```

## Настройка приложения

### 1. Создание виртуального окружения (рекомендуется)
```bash
# Создание venv
python3 -m venv venv

# Активация
source venv/bin/activate
```

### 2. Установка Python зависимостей
```bash
# Создание requirements.txt если его нет
cat > requirements.txt << EOF
aiohttp==3.9.1
psycopg2-binary==2.9.9
asyncio
logging
urllib3>=1.26.0
certifi
EOF

# Установка зависимостей
pip install -r requirements.txt
```

### 3. Создание файла конфигурации окружения
```bash
# Создание .env файла (опционально)
nano .env
```

Содержимое .env:
```bash
# Database settings
DB_HOST=localhost
DB_PORT=5432
DB_NAME=crypto_db
DB_USER=crypto_user
DB_PASSWORD=crypto_password

# Parser settings
MAX_COINS=30
PARSER_MODE=safe
DEBUG=false
```

### 4. Настройка прав на выполнение
```bash
# Сделать скрипты исполняемыми
chmod +x parser.py parser_id.py updater.py run.sh clean_db.py
```

## Восстановление базы данных

### Если база данных была полностью очищена или повреждена

#### 🔧 Способ 1: Через Docker (рекомендуется)
```bash
# Убедитесь, что находитесь в директории проекта
cd ~/projects/crypto-parser

# Проверьте, что контейнер БД работает
docker ps | grep crypto_db

# Если контейнер не работает, запустите его
docker-compose up -d

# Восстановление структуры БД из init_db.sql
docker exec -i crypto_db psql -U crypto_user -d crypto_db < init_db.sql
```

#### 🔧 Способ 2: Через clean_db.py (рекомендуется)
```bash
# Запустите скрипт управления БД
python3 clean_db.py

# Выберите пункт 4 (ВОССТАНОВЛЕНИЕ СТРУКТУРЫ)
# Или пункт 5 (ПЕРЕИНИЦИАЛИЗАЦИЯ) для полной очистки + восстановление
```

#### 🔧 Способ 3: Пошаговое восстановление
```bash
# 1. Проверьте подключение к БД
docker exec crypto_db pg_isready -U crypto_user

# 2. Восстановите структуру
docker exec -i crypto_db psql -U crypto_user -d crypto_db < init_db.sql

# 3. Проверьте результат
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\dt"
```

#### ✅ Проверка успешного восстановления
```bash
# Проверьте созданные таблицы
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
"

# Проверьте структуру основной таблицы
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\d cryptocurrencies"

# Проверьте функции и триггеры
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\df"
```

#### 🎯 Что восстанавливается:
- **Таблица `cryptocurrencies`** с полной структурой
- **Индексы** для оптимизации запросов  
- **Функции**:
  - `update_last_updated_at()` - обновление времени
  - `safe_table_name()` - генерация имен OHLC таблиц
  - `create_ohlc_table()` - создание OHLC таблиц
- **Триггеры**:
  - Автоматическое обновление `last_updated_at`
  - Автоматическое создание OHLC таблиц при добавлении монет
- **Представление `crypto_stats`** для удобной статистики

#### 🔄 После восстановления
```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Проверьте работу парсера
python3 parser.py

# Структура БД готова к работе!
```

## Первый запуск

### Использование clean_db.py для управления БД
```bash
# Запуск интерактивного меню
python3 clean_db.py
```

#### Доступные опции:
1. **Очистка данных** (сохранить структуру таблиц)
2. **Очистка OHLC таблиц** (удалить все OHLC таблицы)
3. **⚠️ ПОЛНОЕ УДАЛЕНИЕ ВСЕХ ТАБЛИЦ**
4. **🔧 ВОССТАНОВЛЕНИЕ СТРУКТУРЫ** (из init_db.sql) - НОВОЕ
5. **🔄 ПЕРЕИНИЦИАЛИЗАЦИЯ** (удаление + восстановление)
6. **Показать статистику**

#### Различия между восстановлением и переинициализацией:

**Пункт 4 - Восстановление структуры:**
- ✅ Восстанавливает структуру из `init_db.sql`
- ✅ **Сохраняет существующие данные**
- ✅ Создает недостающие таблицы, функции, триггеры
- ✅ **Безопасно** - не удаляет ничего
- 🎯 **Используйте когда**: структура повреждена, но данные целы

**Пункт 5 - Переинициализация:**
- ⚠️ Полностью удаляет ВСЕ таблицы и данные
- ⚠️ Затем восстанавливает структуру с нуля
- ⚠️ **НЕОБРАТИМО** - все данные будут потеряны  
- 🎯 **Используйте когда**: нужна полная очистка БД

#### Практические сценарии:

```bash
# СЦЕНАРИЙ 1: После случайного удаления таблиц (данные есть в OHLC таблицах)
python3 clean_db.py
# Выберите пункт 4 - восстановит структуру, сохранит OHLC данные

# СЦЕНАРИЙ 2: База "поломалась", но данные важны
python3 clean_db.py  
# Выберите пункт 4 - безопасное восстановление

# СЦЕНАРИЙ 3: Нужна полностью чистая БД для тестов
python3 clean_db.py
# Выберите пункт 5 - полная переинициализация

# СЦЕНАРИЙ 4: Очистить только данные, оставить структуру
python3 clean_db.py
# Выберите пункт 1 - очистка данных
```

#### Примеры использования:
```bash
# Быстрая статистика БД
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT 
    COUNT(*) as total_coins,
    COUNT(CASE WHEN coin_gecko_id IS NOT NULL THEN 1 END) as with_id,
    COUNT(CASE WHEN ohlc_table_name IS NOT NULL THEN 1 END) as with_ohlc
FROM cryptocurrencies;
"

# Просмотр через представление
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM crypto_stats LIMIT 10;
"

# Восстановление структуры (безопасно)
python3 clean_db.py  # выберите пункт 4

# Полная переинициализация (ОПАСНО)
python3 clean_db.py  # выберите пункт 5

# Ручное создание OHLC таблицы
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT create_ohlc_table('BTC', '2024-01-01');
"
```

### 1. Пошаговый тест всех компонентов

#### Этап 1: Парсинг новых монет
```bash
# Активировать venv если не активирован
source venv/bin/activate

# Запуск основного парсера
python3 parser.py
```

#### Этап 2: Получение CoinGecko ID
```bash
# Запуск парсера ID (получает ID для монет без них)
python3 parser_id.py
```

#### Этап 3: Обновление OHLC данных
```bash
# Запуск обновления OHLC
python3 updater.py
```

### 2. Проверка результатов
```bash
# Проверка общих данных в БД
docker exec -it crypto_db psql -U crypto_user -d crypto_db -c "
SELECT 
    COUNT(*) as total_coins,
    COUNT(CASE WHEN coin_gecko_id IS NOT NULL THEN 1 END) as with_id,
    COUNT(CASE WHEN ohlc_table_name IS NOT NULL THEN 1 END) as with_ohlc
FROM cryptocurrencies;
"

# Проверка последних добавленных монет
docker exec -it crypto_db psql -U crypto_user -d crypto_db -c "
SELECT name, symbol, coin_gecko_id, added_date 
FROM cryptocurrencies 
ORDER BY added_date DESC 
LIMIT 10;
"
```

### 3. Полный цикл через run.sh (опционально)
```bash
# Запуск полного цикла (все 3 этапа) - для ручного использования
./run.sh
```

## Автоматизация через Cron

### 1. Создание wrapper скрипта
```bash
nano cron_wrapper.sh
```

Содержимое:
```bash
#!/bin/bash
# Crypto Parser Cron Wrapper v2.0

PROJECT_DIR="/home/$USER/projects/crypto-parser"
cd "$PROJECT_DIR" || exit 1

# Настройка окружения
export PATH="/usr/local/bin:/usr/bin:/bin"
source "$PROJECT_DIR/venv/bin/activate"

# Настройки БД
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_NAME="crypto_db"
export DB_USER="crypto_user"
export DB_PASSWORD="crypto_password"

# Создание директорий
mkdir -p logs backups

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Запуск команды
case "$1" in
    "parser")
        log "Запуск парсера новых монет"
        python3 parser.py
        ;;
    "parser_id")
        log "Запуск получения CoinGecko ID"
        python3 parser_id.py
        ;;
    "updater")
        log "Запуск обновления OHLC"
        python3 updater.py
        ;;
    "full")
        log "Запуск полного цикла"
        ./run.sh
        ;;
    "backup")
        log "Создание резервной копии БД"
        docker exec crypto_db pg_dump -U crypto_user crypto_db | gzip > "backups/crypto_db_$(date +%Y%m%d_%H%M%S).sql.gz"
        ;;
    *)
        echo "Usage: $0 {parser|parser_id|updater|full|backup}"
        exit 1
        ;;
esac
```

### 2. Настройка прав
```bash
chmod +x cron_wrapper.sh
```

### 3. Настройка crontab
```bash
crontab -e
```

Добавьте **ОБНОВЛЕННОЕ** расписание:
```bash
# Crypto Parser Schedule v2.0
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

# Переменные
PROJECT_DIR=/home/user/projects/crypto-parser

# ЭТАП 1: Парсинг новых монет - каждый час
0 * * * * $PROJECT_DIR/cron_wrapper.sh parser >> $PROJECT_DIR/logs/parser.log 2>&1

# ЭТАП 2: Получение CoinGecko ID - каждый час (со сдвигом 30 минут)
30 * * * * $PROJECT_DIR/cron_wrapper.sh parser_id >> $PROJECT_DIR/logs/parser_id.log 2>&1

# ЭТАП 3: Обновление OHLC данных - каждые 4 часа
15 3,7,11,15,19,23 * * * $PROJECT_DIR/cron_wrapper.sh updater >> $PROJECT_DIR/logs/updater.log 2>&1

# Резервное копирование БД - ежедневно в 4:30
30 4 * * * $PROJECT_DIR/cron_wrapper.sh backup >> $PROJECT_DIR/logs/backup.log 2>&1

# Очистка старых логов - каждое воскресенье в 5:00
0 5 * * 0 find $PROJECT_DIR/logs -name "*.log" -mtime +30 -delete

# Очистка старых бэкапов - каждое воскресенье в 5:30
30 5 * * 0 find $PROJECT_DIR/backups -name "*.sql.gz" -mtime +7 -delete

# Статистика - дважды в день (утром и вечером)
0 9,21 * * * docker exec crypto_db psql -U crypto_user -d crypto_db -c "SELECT 'Time: ' || NOW()::timestamp(0), 'Total: ' || COUNT(*), 'With ID: ' || COUNT(CASE WHEN coin_gecko_id IS NOT NULL THEN 1 END), 'With OHLC: ' || COUNT(CASE WHEN ohlc_table_name IS NOT NULL THEN 1 END) FROM cryptocurrencies;" >> $PROJECT_DIR/logs/stats.log

# Проверка здоровья Docker - каждый час
0 * * * * docker ps | grep crypto_db > /dev/null || docker-compose -f $PROJECT_DIR/docker-compose.yml up -d >> $PROJECT_DIR/logs/docker_health.log 2>&1
```

### 4. Проверка cron
```bash
# Список задач
crontab -l

# Проверка логов cron
sudo tail -f /var/log/syslog | grep CRON
```

## Мониторинг и обслуживание

### 1. Просмотр логов всех компонентов
```bash
# Логи парсера новых монет
tail -f logs/parser.log

# Логи получения ID
tail -f logs/parser_id.log

# Логи обновления OHLC
tail -f logs/updater.log

# Логи полного цикла
tail -f logs/full.log

# Статистика
tail -f logs/stats.log

# Логи Docker
docker-compose logs -f

# Системные логи
journalctl -u docker -f
```

### 2. Мониторинг ресурсов и производительности
```bash
# Использование CPU и памяти
htop

# Использование диска
df -h

# Размер БД и таблиц
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT 
    pg_size_pretty(pg_database_size('crypto_db')) as db_size,
    COUNT(*) as total_tables
FROM information_schema.tables 
WHERE table_schema = 'public';
"

# Детальная статистика монет
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT 
    COUNT(*) as total_coins,
    COUNT(CASE WHEN coin_gecko_id IS NOT NULL THEN 1 END) as with_coingecko_id,
    COUNT(CASE WHEN ohlc_table_name IS NOT NULL THEN 1 END) as with_ohlc_table,
    COUNT(CASE WHEN added_date::date = CURRENT_DATE THEN 1 END) as added_today,
    COUNT(CASE WHEN added_date::date >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as added_last_week
FROM cryptocurrencies;
"

# Статистика OHLC таблиц
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT COUNT(*) as ohlc_tables_count
FROM information_schema.tables 
WHERE table_name LIKE 'ohlc_%';
"
```

### 3. Расширенное резервное копирование
```bash
# Полное резервное копирование с метаданными
docker exec crypto_db pg_dump -U crypto_user -v -F c -f /tmp/full_backup.dump crypto_db
docker cp crypto_db:/tmp/full_backup.dump backups/full_backup_$(date +%Y%m%d).dump

# Резервное копирование только схемы
docker exec crypto_db pg_dump -U crypto_user -s crypto_db | gzip > backups/schema_backup_$(date +%Y%m%d).sql.gz

# Резервное копирование только данных
docker exec crypto_db pg_dump -U crypto_user -a crypto_db | gzip > backups/data_backup_$(date +%Y%m%d).sql.gz
```

### 4. Скрипт мониторинга состояния
```bash
nano monitor.sh
```

Содержимое:
```bash
#!/bin/bash
# Crypto Parser Monitor Script

PROJECT_DIR="/home/$USER/projects/crypto-parser"
cd "$PROJECT_DIR" || exit 1

echo "=== CRYPTO PARSER STATUS ==="
echo "Время: $(date)"
echo

# Docker статус
echo "🐳 Docker контейнеры:"
docker ps --filter name=crypto_db --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo

# База данных
echo "📊 Статистика БД:"
docker exec crypto_db psql -U crypto_user -d crypto_db -t -c "
SELECT 
    'Всего монет: ' || COUNT(*) ||
    ', С ID: ' || COUNT(CASE WHEN coin_gecko_id IS NOT NULL THEN 1 END) ||
    ', С OHLC: ' || COUNT(CASE WHEN ohlc_table_name IS NOT NULL THEN 1 END) ||
    ', Добавлено сегодня: ' || COUNT(CASE WHEN added_date::date = CURRENT_DATE THEN 1 END)
FROM cryptocurrencies;
" 2>/dev/null || echo "❌ БД недоступна"
echo

# Размер БД
echo "💾 Размер БД:"
docker exec crypto_db psql -U crypto_user -d crypto_db -t -c "
SELECT pg_size_pretty(pg_database_size('crypto_db'));
" 2>/dev/null || echo "❌ Не удалось получить размер БД"
echo

# Последние логи
echo "📋 Последние события:"
if [ -f logs/stats.log ]; then
    tail -3 logs/stats.log
else
    echo "Логи статистики не найдены"
fi
echo

# Использование диска
echo "💿 Использование диска:"
df -h . | tail -1
echo

echo "=== КОНЕЦ ОТЧЕТА ==="
```

```bash
chmod +x monitor.sh
```

## Обновление приложения

### 1. Обновление кода
```bash
# Если используете Git
git pull origin main

# Обновление зависимостей
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Проверка новых файлов
ls -la *.py
```

### 2. Применение изменений БД (если есть)
```bash
# Проверка структуры БД
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\dt"

# Применение новых миграций (если необходимо)
# docker exec -i crypto_db psql -U crypto_user crypto_db < new_migration.sql
```

### 3. Перезапуск сервисов
```bash
# Перезапуск контейнеров
docker-compose restart

# Тестовый запуск компонентов
source venv/bin/activate
python3 parser.py --test
python3 parser_id.py --test
python3 updater.py --test
```

## Решение проблем

### 1. Проблемы с parser_id.py
```bash
# Ошибки Rate Limit CoinGecko
# Увеличьте задержки в parser_id.py:
# REQUEST_DELAY = 10  # до 15-20
# RETRY_DELAY = 60   # до 120

# Проблемы с поиском монет
# Проверьте логи:
tail -f logs/parser_id.log

# Ручной тест поиска ID
python3 -c "
import asyncio
from parser_id import *
asyncio.run(main())
"
```

### 2. Проблемы с updater.py (OHLC)
```bash
# Проверка API доступности
curl "https://api.coingecko.com/api/v3/coins/bitcoin/ohlc?vs_currency=usd&days=14"

# Проверка конкретной монеты
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT name, symbol, coin_gecko_id 
FROM cryptocurrencies 
WHERE coin_gecko_id IS NOT NULL 
LIMIT 1;
"

# Ручной тест обновления
python3 -c "
import asyncio
from updater import *
asyncio.run(main())
"
```

### 3. Проблемы с базой данных
```bash
# Проверка соединений
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT count(*) FROM pg_stat_activity WHERE datname='crypto_db';
"

# Если БД повреждена или очищена - безопасное восстановление
python3 clean_db.py  # выберите пункт 4 (ВОССТАНОВЛЕНИЕ СТРУКТУРЫ)

# Или через Docker напрямую
docker exec -i crypto_db psql -U crypto_user -d crypto_db < init_db.sql

# Анализ размера таблиц
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;
"

# Пересоздание индексов (если нужно)
docker exec crypto_db psql -U crypto_user -d crypto_db -c "REINDEX DATABASE crypto_db;"
```

### 4. Оптимизация производительности
```bash
# Мониторинг процессов Python
ps aux | grep python | grep -E "(parser|updater)"

# Настройка PostgreSQL для лучшей производительности
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET work_mem = '4MB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
SELECT pg_reload_conf();
"
```

## Безопасность и оптимизация

### 1. Настройка firewall
```bash
# Установка ufw
sudo apt install ufw

# Базовые правила
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 22/tcp

# Включение firewall
sudo ufw enable
```

### 2. Защита БД и оптимизация
```bash
# Изменение паролей в docker-compose.yml
# Настройка логирования PostgreSQL
# Ограничение подключений

# Создание .pgpass для безопасности
echo "localhost:5432:crypto_db:crypto_user:crypto_password" > ~/.pgpass
chmod 600 ~/.pgpass
```

### 3. Мониторинг логов и алертов
```bash
# Создание скрипта проверки ошибок
nano check_errors.sh
```

Содержимое:
```bash
#!/bin/bash
# Проверка критических ошибок

LOG_DIR="/home/$USER/projects/crypto-parser/logs"
ERRORS_FOUND=0

# Проверка критических ошибок
if grep -q "CRITICAL\|FATAL\|ERROR.*database" "$LOG_DIR"/*.log 2>/dev/null; then
    echo "🚨 Обнаружены критические ошибки!"
    ERRORS_FOUND=1
fi

# Проверка доступности БД
if ! docker exec crypto_db pg_isready -U crypto_user > /dev/null 2>&1; then
    echo "🚨 База данных недоступна!"
    ERRORS_FOUND=1
fi

# Уведомление (можно настроить email/telegram)
if [ $ERRORS_FOUND -eq 1 ]; then
    echo "Требуется внимание администратора"
    # mail -s "Crypto Parser Alert" admin@domain.com < /tmp/alert.txt
fi
```

## Полезные команды для управления

```bash
# === УПРАВЛЕНИЕ ПАРСЕРОМ ===

# Статус всех компонентов
./monitor.sh

# Принудительный запуск отдельных этапов
./cron_wrapper.sh parser     # Только парсинг новых монет
./cron_wrapper.sh parser_id  # Только получение ID
./cron_wrapper.sh updater    # Только обновление OHLC

# Ручное резервное копирование
./cron_wrapper.sh backup

# === УПРАВЛЕНИЕ ДАННЫМИ ===

# Поиск монеты в БД
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM cryptocurrencies WHERE name ILIKE '%bitcoin%' OR symbol ILIKE '%btc%';
"

# Очистка монет без ID старше 30 дней
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
DELETE FROM cryptocurrencies 
WHERE coin_gecko_id IS NULL 
AND added_date < NOW() - INTERVAL '30 days';
"

# === ДИАГНОСТИКА ===

# Проверка последней активности парсеров
ls -la logs/*.log

# Проверка активных Python процессов
pgrep -f "python.*parser" -l

# Быстрая диагностика системы
echo "=== СИСТЕМА ==="
uptime
df -h
echo "=== СИСТЕМА ==="
docker ps
echo "=== ПОСЛЕДНИЕ ЛОГИ ==="
tail -5 logs/*.log
```

## Контакты и поддержка

При возникновении проблем:
1. Проверьте логи всех компонентов в директории `logs/`
2. Запустите `./monitor.sh` для общей диагностики
3. Проверьте статус Docker контейнеров
4. Убедитесь, что все зависимости установлены
5. Проверьте доступность API CoinGecko
6. Используйте отдельные компоненты для локализации проблемы

**Новые файлы в v2.0:**
- `parser_id.py` - получение CoinGecko ID через API
- `updater.py` - обновленный с прямым OHLC API
- Улучшенный `run.sh` с тремя этапами
- Расширенное cron расписание
- Улучшенный мониторинг

---

**Версия**: 2.0  
**Дата обновления**: 2025  
**Автор**: Crypto Parser Team