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
- Chrome/Chromium для Selenium
- aiohttp, psycopg2, selenium (Python библиотеки)

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

### 2. Установка Chrome для Selenium
```bash
# Добавление репозитория Google Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Обновление и установка Chrome
sudo apt update
sudo apt install -y google-chrome-stable

# Установка ChromeDriver
CHROME_DRIVER_VERSION=$(curl -sS chromedriver.chromium.org/LATEST_RELEASE)
wget -O /tmp/chromedriver.zip http://chromedriver.chromium.org/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip
sudo unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver

# Проверка
google-chrome --version
chromedriver --version
```

### 3. Установка Docker
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

### 4. Установка Docker Compose
```bash
# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Проверка
docker-compose --version
```

### 5. Установка PostgreSQL клиента (опционально)
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

**Основные компоненты:**
- `docker-compose.yml` - конфигурация Docker
- `init_db.sql` - схема базы данных
- `clean_db.py` - управление базой данных

**Парсеры:**
- `parser.py` - основной парсер новых монет
- `parser_id.py` - получение CoinGecko ID монет  
- `parser_coingecko_social.py` - парсер социальных ссылок
- `updater.py` - обновление OHLC данных
- `cryptoranc_upcoin_table.py` - парсер upcoming ICO проектов
- `cryptorank_platform.py` - **НОВЫЙ**: парсер платформ для launchpad

**Системные файлы:**
- `run.sh` - скрипт полного цикла обновления
- `cron_wrapper.sh` - **ОБНОВЛЕН**: wrapper для cron с поддержкой новых команд
- `requirements.txt` - зависимости Python

### 5. Новые файлы в версии 3.0:
- **`cryptorank_platform.py`** - автоматически находит платформы для ICO проектов
- **Обновленный `cron_wrapper.sh`** - поддержка команд `upcoming`, `social-only`, `upcoming-stats`
- **Расширенный `init_db.sql`** - новая таблица `cryptorank_upcoming` с поддержкой JSON полей

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
selenium==4.15.2
python-dotenv==1.0.0
asyncio
logging
urllib3>=1.26.0
certifi
beautifulsoup4
lxml
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

# Platform parser settings
PLATFORM_SCAN_LIMIT=50
PLATFORM_MAX_RETRIES=3
```

### 4. Настройка прав на выполнение
```bash
# Сделать скрипты исполняемыми
chmod +x *.py *.sh
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

#### ✅ Проверка успешного восстановления
```bash
# Проверьте созданные таблицы
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
"

# Проверьте структуру основных таблиц
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\d cryptocurrencies"
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\d cryptorank_upcoming"

# Проверьте функции и представления
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\df"
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\dv"
```

#### 🎯 Что восстанавливается в версии 3.0:
- **Таблица `cryptocurrencies`** с социальными ссылками и Telegram поддержкой
- **Таблица `cryptorank_upcoming`** для ICO проектов с JSON полями
- **Индексы** для оптимизации запросов  
- **Функции**:
  - `update_last_updated_at()` - обновление времени для основной таблицы
  - `update_upcoming_updated_at()` - обновление времени для upcoming таблицы
  - `get_upcoming_stats()` - статистика upcoming проектов
  - `get_social_stats()` - статистика социальных ссылок
  - `analyze_telegram_message()` - анализ Telegram сообщений
- **Представления**:
  - `crypto_stats` - общая статистика с социальными данными
  - `upcoming_projects_stats` - статистика upcoming проектов
  - `upcoming_soon` - ближайшие проекты
  - `crypto_social_links` - социальные ссылки
  - `telegram_stats` - статистика Telegram
  - `crypto_without_social` - проекты без социальных ссылок

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
4. **🔧 ВОССТАНОВЛЕНИЕ СТРУКТУРЫ** (из init_db.sql)
5. **🔄 ПЕРЕИНИЦИАЛИЗАЦИЯ** (удаление + восстановление)
6. **Показать статистику**

### 1. Пошаговый тест всех компонентов

#### Этап 1: Парсинг новых монет + социальные ссылки
```bash
# Активировать venv если не активирован
source venv/bin/activate

# Запуск основного парсера (автоматически запустит и социальные ссылки)
python3 parser.py
```

#### Этап 2: Парсинг upcoming ICO проектов
```bash
# Запуск парсера upcoming проектов
python3 cryptoranc_upcoin_table.py
```

#### Этап 3: Поиск платформ для проектов (НОВОЕ)
```bash
# Запуск парсера платформ
python3 cryptorank_platform.py
```

#### Этап 4: Получение CoinGecko ID
```bash
# Запуск парсера ID (получает ID для монет без них)
python3 parser_id.py
```

#### Этап 5: Обновление OHLC данных
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
    COUNT(CASE WHEN ohlc_table_name IS NOT NULL THEN 1 END) as with_ohlc,
    COUNT(CASE WHEN array_length(telegram_channels, 1) > 0 THEN 1 END) as with_telegram,
    COUNT(CASE WHEN array_length(twitter_accounts, 1) > 0 THEN 1 END) as with_twitter
FROM cryptocurrencies;
"

# Проверка upcoming проектов
docker exec -it crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM get_upcoming_stats();
"

# Проверка платформ
docker exec -it crypto_db psql -U crypto_user -d crypto_db -c "
SELECT 
    COUNT(*) as projects_with_platforms,
    COUNT(DISTINCT jsonb_array_elements_text(launchpad)) as unique_platforms
FROM cryptorank_upcoming 
WHERE launchpad != '[]'::jsonb;
"
```

### 3. Полный цикл через run.sh (опционально)
```bash
# Запуск полного цикла (все этапы) - для ручного использования
./run.sh
```

## Автоматизация через Cron

### 1. Создание wrapper скрипта
```bash
nano cron_wrapper.sh
```

**ОБНОВЛЕННЫЙ** cron_wrapper.sh уже включает поддержку новых команд:
- `upcoming` - парсинг upcoming ICO проектов
- `social-only` - отдельный запуск социальных ссылок
- `upcoming-stats` - детальная статистика upcoming проектов

### 2. Настройка прав
```bash
chmod +x cron_wrapper.sh
```

### 3. Настройка crontab
```bash
crontab -e
```

Добавьте **ОБНОВЛЕННОЕ** расписание для версии 3.0:
```bash
# Crypto Parser Schedule v3.0
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

# Переменные
PROJECT_DIR=/home/user/projects/crypto-parser

# ЭТАП 1: Парсинг новых монет + социальные ссылки - каждый час
0 * * * * $PROJECT_DIR/cron_wrapper.sh parser >> $PROJECT_DIR/logs/parser.log 2>&1

# ЭТАП 2: Парсинг upcoming ICO проектов - каждые 6 часов
30 */6 * * * $PROJECT_DIR/cron_wrapper.sh upcoming >> $PROJECT_DIR/logs/upcoming.log 2>&1

# ЭТАП 3: Получение CoinGecko ID - каждый час (со сдвигом 30 минут)
30 * * * * $PROJECT_DIR/cron_wrapper.sh parser_id >> $PROJECT_DIR/logs/parser_id.log 2>&1

# ЭТАП 4: Обновление OHLC данных - каждые 4 часа
15 3,7,11,15,19,23 * * * $PROJECT_DIR/cron_wrapper.sh updater >> $PROJECT_DIR/logs/updater.log 2>&1

# Резервное копирование БД - ежедневно в 4:30
30 4 * * * $PROJECT_DIR/cron_wrapper.sh backup >> $PROJECT_DIR/logs/backup.log 2>&1

# Очистка старых логов - каждое воскресенье в 5:00
0 5 * * 0 find $PROJECT_DIR/logs -name "*.log" -mtime +30 -delete

# Очистка старых бэкапов - каждое воскресенье в 5:30
30 5 * * 0 find $PROJECT_DIR/backups -name "*.sql.gz" -mtime +7 -delete

# Расширенная статистика - дважды в день (утром и вечером)
0 9,21 * * * $PROJECT_DIR/cron_wrapper.sh stats >> $PROJECT_DIR/logs/stats.log

# Детальная статистика upcoming проектов - ежедневно в 10:00
0 10 * * * $PROJECT_DIR/cron_wrapper.sh upcoming-stats >> $PROJECT_DIR/logs/upcoming_stats.log

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

# Логи upcoming проектов
tail -f logs/upcoming.log

# Логи получения ID
tail -f logs/parser_id.log

# Логи обновления OHLC
tail -f logs/updater.log

# Статистика upcoming проектов
tail -f logs/upcoming_stats.log

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

# Расширенная статистика с новыми данными
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT 
    COUNT(*) as total_coins,
    COUNT(CASE WHEN coin_gecko_id IS NOT NULL THEN 1 END) as with_coingecko_id,
    COUNT(CASE WHEN ohlc_table_name IS NOT NULL THEN 1 END) as with_ohlc_table,
    COUNT(CASE WHEN array_length(telegram_channels, 1) > 0 THEN 1 END) as with_telegram,
    COUNT(CASE WHEN array_length(twitter_accounts, 1) > 0 THEN 1 END) as with_twitter,
    COUNT(CASE WHEN social_links_updated IS NOT NULL THEN 1 END) as social_updated,
    COUNT(CASE WHEN added_date::date = CURRENT_DATE THEN 1 END) as added_today
FROM cryptocurrencies;
"

# Статистика upcoming проектов
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM get_upcoming_stats();
"

# Статистика социальных ссылок
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM get_social_stats();
"
```

### 3. Новые команды для мониторинга версии 3.0
```bash
# Проверка upcoming проектов на этой неделе
./cron_wrapper.sh upcoming-stats

# Проверка социальных ссылок
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM crypto_social_links LIMIT 10;
"

# Проверка Telegram статистики
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM telegram_stats LIMIT 10;
"

# Проверка проектов без социальных ссылок
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM crypto_without_social LIMIT 10;
"
```

### 4. Скрипт мониторинга состояния (ОБНОВЛЕН)
```bash
nano monitor.sh
```

Содержимое:
```bash
#!/bin/bash
# Crypto Parser Monitor Script v3.0

PROJECT_DIR="/home/$USER/projects/crypto-parser"
cd "$PROJECT_DIR" || exit 1

echo "=== CRYPTO PARSER STATUS V3.0 ==="
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
    ', С Telegram: ' || COUNT(CASE WHEN array_length(telegram_channels, 1) > 0 THEN 1 END) ||
    ', С Twitter: ' || COUNT(CASE WHEN array_length(twitter_accounts, 1) > 0 THEN 1 END) ||
    ', Добавлено сегодня: ' || COUNT(CASE WHEN added_date::date = CURRENT_DATE THEN 1 END)
FROM cryptocurrencies;
" 2>/dev/null || echo "❌ БД недоступна"

# Upcoming проекты
echo
echo "🚀 Upcoming проекты:"
docker exec crypto_db psql -U crypto_user -d crypto_db -t -c "
SELECT 'Всего: ' || total_projects || ', Активных: ' || active_projects || ', На этой неделе: ' || this_week
FROM get_upcoming_stats();
" 2>/dev/null || echo "❌ Не удалось получить статистику upcoming"

echo
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

### 2. Применение изменений БД для версии 3.0
```bash
# Проверка текущей структуры БД
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\dt"

# Применение обновлений структуры (безопасно)
docker exec -i crypto_db psql -U crypto_user -d crypto_db < init_db.sql

# Проверка новых представлений и функций
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\dv"
docker exec crypto_db psql -U crypto_user -d crypto_db -c "\df"
```

### 3. Перезапуск сервисов
```bash
# Перезапуск контейнеров
docker-compose restart

# Тестовый запуск новых компонентов
source venv/bin/activate
python3 cryptoranc_upcoin_table.py  # Тест upcoming
python3 cryptorank_platform.py      # Тест платформ
python3 parser_coingecko_social.py  # Тест социальных ссылок
```

## Решение проблем

### 1. Проблемы с новыми парсерами

#### cryptorank_platform.py
```bash
# Ошибки с Selenium или Chrome
google-chrome --version
chromedriver --version

# Проблемы с таймаутами
# Увеличьте max_retries в коде или:
# Проверьте логи:
tail -f logs/platform.log

# Ручной тест
python3 cryptorank_platform.py
```

#### cryptoranc_upcoin_table.py
```bash
# Проблемы с парсингом таблицы
# Проверьте доступность сайта:
curl -I https://cryptorank.io/upcoming-ico

# Ручной тест
python3 cryptoranc_upcoin_table.py
```

#### parser_coingecko_social.py
```bash
# Ошибки Rate Limit CoinGecko
# Увеличьте задержки или проверьте API:
curl "https://api.coingecko.com/api/v3/coins/bitcoin"

# Ручной тест
python3 parser_coingecko_social.py
```

### 2. Проблемы с базой данных
```bash
# Проверка новых таблиц
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
"

# Если отсутствует таблица cryptorank_upcoming
docker exec -i crypto_db psql -U crypto_user -d crypto_db < init_db.sql

# Проверка JSON полей
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT project_name, launchpad 
FROM cryptorank_upcoming 
WHERE launchpad != '[]'::jsonb 
LIMIT 5;
"
```

### 3. Проблемы с Chrome/Selenium
```bash
# Переустановка Chrome
sudo apt remove google-chrome-stable
sudo apt autoremove
# Затем повторите установку из раздела "Установка зависимостей"

# Проверка работы в headless режиме
python3 -c "
from selenium import webdriver
options = webdriver.ChromeOptions()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
driver = webdriver.Chrome(options=options)
driver.get('https://google.com')
print('Chrome works!')
driver.quit()
"
```

## Новые возможности версии 3.0

### 1. Парсинг upcoming ICO проектов
```bash
# Ручной запуск
python3 cryptoranc_upcoin_table.py

# Через cron wrapper
./cron_wrapper.sh upcoming

# Статистика
./cron_wrapper.sh upcoming-stats
```

### 2. Автоматический поиск платформ
```bash
# Ручной запуск
python3 cryptorank_platform.py

# Проверка найденных платформ
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT project_name, launchpad 
FROM cryptorank_upcoming 
WHERE launchpad != '[]'::jsonb;
"
```

### 3. Расширенные социальные ссылки
```bash
# Проверка социальных данных
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT symbol, name, 
       array_length(telegram_channels, 1) as telegram_count,
       array_length(twitter_accounts, 1) as twitter_count,
       social_links_updated
FROM cryptocurrencies 
WHERE social_links_updated IS NOT NULL 
ORDER BY social_links_updated DESC 
LIMIT 10;
"
```

## Полезные команды для управления

```bash
# === НОВЫЕ КОМАНДЫ ВЕРСИИ 3.0 ===

# Статистика upcoming проектов
./cron_wrapper.sh upcoming-stats

# Запуск только социальных ссылок
./cron_wrapper.sh social-only

# Парсинг upcoming проектов
./cron_wrapper.sh upcoming

# === МОНИТОРИНГ НОВЫХ ДАННЫХ ===

# Проекты запускающиеся на этой неделе
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM upcoming_soon WHERE days_until_launch <= 7;
"

# Топ проектов по социальным ссылкам
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM crypto_social_links ORDER BY total_social_links DESC LIMIT 10;
"

# Проекты без социальных ссылок
docker exec crypto_db psql -U crypto_user -d crypto_db -c "
SELECT * FROM crypto_without_social LIMIT 10;
"

# Очистка колонки launchpad (если нужно)
python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, database='crypto_db', user='crypto_user', password='crypto_password')
cursor = conn.cursor()
cursor.execute('UPDATE cryptorank_upcoming SET launchpad = \\'[]\\';')
conn.commit()
print('Launchpad cleared')
"
```

## Контакты и поддержка

При возникновении проблем:
1. Проверьте логи всех компонентов в директории `logs/`
2. Запустите `./monitor.sh` для общей диагностики
3. Проверьте статус Docker контейнеров
4. Убедитесь, что Chrome и ChromeDriver установлены корректно
5. Проверьте доступность API CoinGecko и CryptoRank
6. Используйте отдельные компоненты для локализации проблемы

**Новые файлы в v3.0:**
- `cryptorank_platform.py` - автоматический поиск платформ
- `cryptoranc_upcoin_table.py` - парсер upcoming ICO проектов  
- `parser_coingecko_social.py` - расширенные социальные ссылки
- Обновленный `cron_wrapper.sh` с новыми командами
- Расширенный `init_db.sql` с поддержкой upcoming проектов

---

**Версия**: 3.0  
**Дата обновления**: Январь 2025  
**Автор**: Crypto Parser Team