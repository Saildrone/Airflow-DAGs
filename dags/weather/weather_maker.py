import os
import json
import requests

from datetime import datetime
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators import WeatherFileSensor
from airflow.contrib.operators.kubernetes_pod_operator import KubernetesPodOperator


NAM_BASE_DIR = '/data/weatherdata/nam'


def download_kelp(**context):
    execution_date_dt = context['execution_date']
    execution_date_str = execution_date_dt.isoformat()

    file_name = os.path.join('/tmp', 'kelp_drones_{}.json'.format(execution_date_str))

    with open(file_name, 'w+') as f:
        r = requests.get('https://kelp.saildrone.com/inventory/drones')
        json.dump(r.json(), f, indent=2)


dag = DAG('weather_maker', description='Extract weather input data and trigger forecasts',
          schedule_interval='0 * * * *',
          start_date=datetime(2017, 3, 20), catchup=False)

metgrib_op = PythonOperator(task_id='metgrid',
                            python_callable=download_kelp,
                            dag=dag,
                            provide_context=True)

ungrib_operators = []

for i in range(1, 4):
    forecast_hour = i * 3
    file_path = '{% "/data/weatherdata/nam/" + {{ execution_date.strftime("%Y/%m/%d")}} %}'

    check_file_op = WeatherFileSensor(file_path=file_path,
                                      task_id='weather_file_sensor_{}'.format(forecast_hour),
                                      poke_interval=5,
                                      dag=dag)

    ungrib_op = KubernetesPodOperator(namespace='airflow',
                                      name='run-ungrib-{}'.format(forecast_hour),
                                      task_id='run_ungrib_{}'.format(forecast_hour),
                                      dag=dag,
                                      image='quay.io/sdtechops/wrf',
                                      image_pull_secrets='quayio-pull',
                                      cmds=['bash', '-cx'])

    ungrib_op.set_upstream(check_file_op)

    ungrib_operators.append(ungrib_op)

metgrib_op.set_upstream(ungrib_operators)
