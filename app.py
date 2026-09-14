import os
from flask import Flask, jsonify, request
import clickhouse_connect
from fake_useragent import UserAgent
import requests      # Библиотека для отправки запросов
import logging
from prophet import Prophet
import joblib
import pandas as pd
import json

logging.basicConfig(level=logging.INFO)
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

@app.route('/import', methods=['GET', 'POST'])
def imp_calls():
    try:
        # Импортируем звонки из Б24 в CH
        cNext=client.query('SELECT next from itex.next')
        iNext = cNext.result_rows[0][0] #инициализируем счетчик страниц
        iLastID = iNext
        iFirstID = iNext
        while iNext>=0 and iNext < 10000000: #ограничим для теста количество записей, в реале 500К записей грузятся 5 часов
            d = dict() #инициализация словаря для накопления данных
            response = requests.get(page_link+str(iNext), headers={'User-Agent': UserAgent().chrome}) #получаем порцию данных из Б24
            profile = json.loads(response.content.decode('utf-8')) #запрос возвращает 50 записей за раз
            cRes=profile['result'] #потрошим результат запроса
            if 'next' in profile: #если есть следующая партия - т.е. еще не конец парсинга
                iNext=profile['next']
            else:
                iNext=-999
            for cEl in cRes: #перебираем текущие 50 записей
                cDate = cEl['CALL_START_DATE'][:10] #выкусываем дату из строки
                if cEl['PORTAL_USER_ID'] in ('16','17','3062','3068','144','1392','35','47','140'): #берем только звонки консультантам техподдержки
                    if cDate not in d: #если такой даты еще нет в словаре - добавляем, зануляем счетчик звонков 
                        d[cDate] = 0
                    d[cDate] += 1 #плюсуем счетчик звонков
                iLastID+=1
            for el in d: #перекидываем данные из словаря в CH
                logger.info(f'Записываем: {el}, {d[el]}')
                client.query(f"INSERT INTO itex.b24 (dat, calls) VALUES ('{el}', {d[el]})")
            client.query('alter table itex.next delete where 1=1')
            client.query(f'insert INTO itex.next (next) VALUES ({iNext})') #запоминаем где остановились                
            logger.info(f'Читаем следующую партию: '+str(iNext) +  ' Дата: '+ cDate)
        return jsonify({
            "status": "success", 
            "message": f"Импортировано {str(iLastID-iFirstID)} звонков. Итого {str(iLastID)} звонков"
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Ошибка импорта: {str(e)}"
        }), 500

@app.route('/train', methods=['GET', 'POST'])
def train():
    data = request.get_json(silent=True)  # silent=True не выбросит ошибку
    if data is None:
        return jsonify({"error": "Invalid JSON"}), 400
    dend = data.get('target_date','2018-01-01')
    df = client.query_df(f"SELECT toDate(dat) as ds, SUM(calls) AS y from itex.b24 where dat < '{target_date}' group by toDate(dat) order by toDate(dat)")
    if df.empty:
        return jsonify({"status": "error", "message": "База данных пуста или запрос не вернул результатов"}), 400
    logger.info(f'Модель обучена на данных до {dend}')
    model = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
    model.fit(df)
    model_data = {
        'model': model,
        'metadata': {
            'prophet_version': Prophet.__version__ if hasattr(Prophet, '__version__') else 'unknown',
            'training_data': {
                'rows_count': len(model.history),
                'date_range': {
                    'start': str(model.history['ds'].min().date()),
                    'end': str(model.history['ds'].max().date())
                }
            },
            'model_params': {
                'yearly_seasonality': model.yearly_seasonality,
                'weekly_seasonality': model.weekly_seasonality,
                'daily_seasonality': model.daily_seasonality
            },
            'notes': 'Модель для прогнозирования нагрузки звонков'
        }
    }
    joblib.dump(model_data, 'b24_model.joblib')
    logger.info('Сохраняем модель b24_model.joblib')
    return jsonify({
            "status": "success", 
            "message": f'Модель обучена и сохранена на данных до {dend}'
        })

@app.route('/predict', methods=['GET', 'POST'])
def predict():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    target_date = data.get('target_date')
    #lastdate = client.query('SELECT max(dat) from itex.b24').result_rows[0][0]
    logger.info('Загружаем модель b24_model.joblib')
    model_data = joblib.load('b24_model.joblib')
    metadata = model_data['metadata']
    model = model_data['model']
    lastdate = str(metadata['training_data']['date_range']['end'])
    logger.info(f"Формируем будущий период на {(pd.to_datetime(target_date)-pd.to_datetime(lastdate)).days} дней")
    future = model.make_future_dataframe(periods=(pd.to_datetime(target_date)-pd.to_datetime(lastdate)).days)
    logger.info(f'Предсказываем значение на {target_date}')
    forecast = model.predict(future)
    result = forecast[forecast['ds'] == pd.to_datetime(target_date)]
    fact = client.query(f"SELECT sum(calls) from itex.b24 where dat='{target_date}'").result_rows[0][0]
    if not result.empty:
        return jsonify({
            "status": "success", 
            "message": f"Прогноз на {target_date}: {int(result['yhat'].iloc[0])} факт {fact}"
        })
    else:
        return jsonify({
            "status": "error", 
            "message": f"Отсутствует дата {target_date} в будущем периоде"
        }), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)