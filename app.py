import os
from flask import Flask, jsonify
import clickhouse_connect

app = Flask(__name__)

# Получаем настройки из переменных окружения
ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
ch_port = int(os.getenv('CLICKHOUSE_PORT', 8123))
ch_user = os.getenv('CLICKHOUSE_USER', 'default')
ch_password = os.getenv('CLICKHOUSE_PASSWORD', '')
ch_database = os.getenv('CLICKHOUSE_DB', 'default')

# Инициализируем клиент ClickHouse
client = clickhouse_connect.get_client(
    host=ch_host,
    port=ch_port,
    username=ch_user,
    password=ch_password,
    database=ch_database
)

@app.route('/')
def hello():
    return "Flask приложение работает!"

@app.route('/clickhouse-test')
def ch_test():
    try:
        # Выполняем простой запрос для проверки связи
        result = client.query('SELECT version()')
        version = result.result_rows[0][0]
        return jsonify({
            "status": "success", 
            "message": "Успешное подключение к ClickHouse!",
            "clickhouse_version": version
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Ошибка подключения: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)