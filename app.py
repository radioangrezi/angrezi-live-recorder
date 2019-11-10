#!/usr/bin/env python3

# RADIO ANGREZI CONTROLLER
# 2019-06-02, ja

import threading
from flask import Flask
from flask import jsonify
from flask import request

from api_client import AirtimeApiClient

AIRTIME_HOST = '10.10.22.144' #'localhost'
AIRTIME_PORT = 80
AIRTIME_PROTOCOL = 'http'
AIRTIME_API_KEY = 'XLFR6DU8F456S3J7UTF7'

# AIRTIME_CONFIG = '/etc/airtime/airtime.conf'
AIRTIME_CONFIG = 'airtime.conf'

app = Flask(__name__)

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG)

#########
# AIRTIME API "PROXY"
#########

from flask import Response
import json

## uses api_client.py (from source libretime/python_apps/api_clients/api_clients/api_client.py)

airtime_api = AirtimeApiClient(config_path=AIRTIME_CONFIG)

if not airtime_api.is_server_compatible():
    raise Exception("Server is not compatible with API.")
    quit()

@app.route("/airtime/live-info/")
def get_live_info():
    response = airtime_api.get_live_info()
    return Response(json.dumps(response), status=200, mimetype='application/json')
    
    #return str(airtime_api.get_bootstrap_info())

@app.route("/airtime/on-air-light/")
def get_on_air_light():
    response = airtime_api.get_on_air_light()
    return Response(json.dumps(response), status=200, mimetype='application/json')

#########
# ACTIONS
#########

@app.route("/disconect-master/")
def disconect_master():
    response = airtime_api.notify_source_status('master_dj', 'false')
    return Response(json.dumps(response), status=200, mimetype='application/json')

@app.route("/connect-master/")
def connect_master():
    response = airtime_api.notify_source_status('master_dj', 'true')
    return Response(json.dumps(response), status=200, mimetype='application/json')



@app.route("/")
def state():
    t = recording_state.name
    if recording_state is STATES.RECORDING:
        t = "%s: %s" % (STATES.RECORDING.name, datetime.now() - recording_start_datetime)
    return jsonify({ 'status': recording_state.value, 'text': t})

@app.route("/reset")
def reset():
    interrupt.set()
    print("### cut requested ###")
    return "new recording requested"

def flaskThread():
    try:
        port = args.port
    except NameError:
        port = None # default port 5000
    app.run(port=port, host='0.0.0.0')

if __name__ == "__main__":
    threading.Thread(target=flaskThread).start()