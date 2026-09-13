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
page_link= os.getenv('PAGE_LINK', '')

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

@app.route('/import')
def imp_calls():
    try:
        # Импортируем звонки из Б24 в CH
        iNext = 0 #инициализируем счетчик страниц
        d = dict() #инициализация словаря для накопления данных
        while iNext>=0 and iNext < 100: #ограничим для теста количество записей, в реале 500К записей грузятся 5 часов
            response = requests.get(page_link+str(iNext), headers={'User-Agent': UserAgent().chrome}) #получаем порцию данных из Б24
            profile = json.loads(response.content.decode('utf-8')) #запрос возвращает 50 записей за раз
            cRes=profile['result'] #потрошим результат запроса
            if 'next' in profile: #если есть следующая партия - т.е. еще не конец парсинга
                iNext=profile['next']
            else:
                iNext=-999
            for cEl in cRes: #перебираем текущие 50 записей
                cDate = cEl['CALL_START_DATE'][:10] #выкусываем дату из строки
                if cEl['PORTAL_USER_ID'] in ('16','17','35','47','140','144','1392'): #фильтруем звонки по консультантам техподдержки
                    if cDate not in d: #если такой даты еще нет в словаре - добавляем, зануляем счетчик звонков и сразу присваиваем сумму из csv
                        d[cDate] = [0,dSum[cDate[:8]+'01']]
                    d[cDate][0] += 1 #плюсуем счетчик звонков
            print('Читаем следующую партию: '+str(iNext) +  ' Дата: '+ cDate)
        prevCalls = 0 #звонки за предыдущий день занулим для 1-го шага
        for el in d: #перекидываем данные из словаря в датафрейм с обогащением признаками
            try:
                nYear = int(el[:4])     #год
                nMonth = int(el[5:7])   #месяц
                nDay = int(el[8:10])    #день месяца
                nDoW = datetime.date(nYear, nMonth, nDay).weekday() #день недели
                if d[el][0] < 10: #если звонков мало - считаем выходным/праздничным днем
                    nHoliday = 1
                else:  
                    nHoliday = 0
                if nDay < 7 and nMonth > 1: #начало месяца не в январе
                    nDecade = 1 #начало (признак начало/середины/конца месяца)
                elif nMonth == 1 and nDay < 15: #начало месяца в январе
                    nDecade = 1 #начало
                elif nDay > 25:
                    nDecade = 3 #конец
                else:
                    nDecade = 2 #середина
                final_df = final_df.append({'date':datetime.date(nYear, nMonth, nDay), 'year':nYear,'month':nMonth, 'day':nDay, 'dow':nDoW, 'holiday':nHoliday, 'decade':nDecade, 'prevcalls':prevCalls, 'sum':d[el][1], 'calls':d[el][0]}, ignore_index=True)
                prevCalls = d[el][0] #звонки за предыдущий день
            except:
                print(el,'- некорректные данные, пропускаем')
        final_df.to_csv('calls.csv') #сохраняем датафрейм в csv
        print("Кол-во строк",final_df.shape[0]) #контроль размера датафрейма
        return jsonify({
            "status": "success", 
            "message": f"Импортировано {str(iCalls)} звонков"
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Ошибка импорта: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)