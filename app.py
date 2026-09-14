import os
from flask import Flask, jsonify
import clickhouse_connect
from fake_useragent import UserAgent
import json
import requests      # Библиотека для отправки запросов
import datetime      # Библиотека для даты
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
app = Flask(__name__)
app.json.ensure_ascii = False

# Получаем настройки из переменных окружения
ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
ch_port = int(os.getenv('CLICKHOUSE_PORT', 8123))
ch_user = os.getenv('CLICKHOUSE_USER', 'default')
ch_password = os.getenv('CLICKHOUSE_PASSWORD', '')
ch_database = os.getenv('CLICKHOUSE_DB', 'default')
page_link= os.getenv('PAGE_LINK', '')

# Инициализируем клиент ClickHouse
logger.info(f"Подключение к ClickHouse: {ch_host}:{ch_port}")
client = clickhouse_connect.get_client(
    host=ch_host,
    port=ch_port,
    username=ch_user,
    password=ch_password,
    database=ch_database
)

@app.route('/')
def hello():
    logger.info("Запрос к корневому маршруту")
    return "Flask приложение работает!"

@app.route('/clickhouse-test')
def ch_test():
    try:
        # Выполняем простой запрос для проверки связи
        logger.info("Проверка связи с CH")
        result = client.query('SELECT version()')
        version = result.result_rows[0][0]
        return jsonify({
            "status": "success", 
            "message": "Успешное подключение к ClickHouse!",
            "clickhouse_version": version
        })
    except Exception as e:
        logger.error(f"Ошибка подключения: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error", 
            "message": f"Ошибка подключения: {str(e)}"
        }), 500

@app.route('/import')
def imp_calls():
    try:
        # Импортируем звонки из Б24 в CH
        cNext=client.query('SELECT next from itex.next')
        iNext = cNext.result_rows[0][0] #инициализируем счетчик страниц
        iLastID = iNext
        d = dict() #инициализация словаря для накопления данных
        while iNext>=0 and iNext < 10000000: #ограничим для теста количество записей, в реале 500К записей грузятся 5 часов
            response = requests.get(page_link+str(iNext), headers={'User-Agent': UserAgent().chrome}) #получаем порцию данных из Б24
            profile = json.loads(response.content.decode('utf-8')) #запрос возвращает 50 записей за раз
            cRes=profile['result'] #потрошим результат запроса
            if 'next' in profile: #если есть следующая партия - т.е. еще не конец парсинга
                if iNext > profile['next']: #если вдруг следующая партия меньше текущей
                    logger.info(f"Ошибка в данных {iNext} -> {profile['next']}")
                    break
                iNext=profile['next']
            else:
                iNext=-999
            for cEl in cRes: #перебираем текущие 50 записей
                cDate = cEl['CALL_START_DATE'][:10] #выкусываем дату из строки
                if cEl['PORTAL_USER_ID'] in ('16','17','3062','3068','144','1392','35','47','140'): #фильтруем звонки по консультантам техподдержки
                    if cDate not in d: #если такой даты еще нет в словаре - добавляем, зануляем счетчик звонков 
                        d[cDate] = 0
                    d[cDate] += 1 #плюсуем счетчик звонков
                iLastID+=1
            for el in d: #перекидываем данные из словаря в CH
                logger.info(f'Записываем: {el}, {d[el]}')
                client.query(f"INSERT INTO itex.b24 (dat, calls) VALUES ('{el}', {d[el]})")
            d = dict()
            client.query('alter table itex.next delete where 1=1')
            client.query(f'insert INTO itex.next (next) VALUES ({iLastID})') #запоминаем где остановились                
            logger.info(f'Читаем следующую партию: '+str(iNext) +  ' Дата: '+ cDate)
        # for el in d: #перекидываем данные из словаря в CH
        #     logger.info(f'Записываем: {el}, {d[el]}')
        #     client.query(f"INSERT INTO itex.b24 (dat, calls) VALUES ('{el}', {d[el]})")
        # client.query('alter table itex.next delete where 1=1')
        # client.query(f'insert INTO itex.next (next) VALUES ({iLastID})') #запоминаем где остановились
        return jsonify({
            "status": "success", 
            "message": f"Импортировано {str(iLastID)} звонков"
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Ошибка импорта: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)