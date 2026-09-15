Дипломная работа Заварницына Сергея\n
Курс OTUS ML Avdanced\n
2026 год

1. Клонировать репозиторий git clone https://github.com/sergicz/ML_Adv_Diplom.git
2. Настроить .env (пример .env.example)
    - параметры подключения к базе ClickHouse
    - настройки порта Flask
    - веб-хук с API-KEY к Битрикс24
3. Запустить микросервисы "docker compose up --build"
4. API Flask-приложения (по умолчанию http://127.0.0.1:5001), поддерживаются GET, POST
 - проверка работы http://127.0.0.1:5001
 - проверка связи с CH http://127.0.0.1:5001/clickhouse-test
 - импорт звонков из Б24 http://127.0.0.1:5001/import
 - обучение модели до даты http://127.0.0.1:5001/train, входной json {"target_date":"2024-02-11"}
 - предсказание на будущую дату http://127.0.0.1:5001/predict, входной json {"target_date":"2024-02-11"}