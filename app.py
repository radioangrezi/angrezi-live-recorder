#!/usr/bin/env python3

# RADIO ANGREZI CONTROLLER
# 2019-06-02, ja

# TODO: Filename generation and display
# TODO: State conditions: Only record if connected
# TODO: Stop recording when disconectin etc.
# TODO: enhance frontend
# TODO: README + minimal docs

# TODO: v2 cleanup api
# TODO: v2 reimplement frontend with react / backbone
# TODO: less requests?! websocket? or scheduled request similar to player frontend?

import threading
from flask import Flask
from flask import jsonify
from flask import request
from flask_cors import CORS
# from flask_socketio import SocketIO

from api_client import AirtimeApiClient

AIRTIME_HOST = 'studio.radioangrezi.de' #'localhost'
AIRTIME_PORT = 80
AIRTIME_PROTOCOL = 'http'
AIRTIME_API_KEY = 'XLFR6DU8F456S3J7UTF7'

# AIRTIME_CONFIG = '/etc/airtime/airtime.conf'
AIRTIME_CONFIG = 'airtime.conf'

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = 'YQbv2CkMndeRe5dE'
# socketio = SocketIO(app)

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG)

shared_with_recording_process = None

#########
# DIRECT AIRTIME API "PROXY"
#########

from flask import Response
import json

## uses api_client.py (from source libretime/python_apps/api_clients/api_clients/api_client.py)

airtime_api = AirtimeApiClient(config_path=AIRTIME_CONFIG)

if not airtime_api.is_server_compatible():
    raise Exception("Server is not compatible with API.")
    quit()

#@app.route("/airtime/live-info-v2/")

@app.route("/airtime/live-info/")
def get_live_info():
    response = airtime_api.get_live_info()
    return Response(json.dumps(response), status=200, mimetype='application/json')

@app.route("/airtime/on-air-light/")
def get_on_air_light():
    response = airtime_api.get_on_air_light()
    return Response(json.dumps(response), status=200, mimetype='application/json')

@app.route("/airtime/bootstrap-info/")
def get_bootstrap_info():
    response = airtime_api.get_bootstrap_info()
    return Response(json.dumps(response), status=200, mimetype='application/json')

#########
# ACTIONS x not used
#########

@app.route("/disconect-master/")
def disconect_master():
    response = airtime_api.notify_source_status('master_dj', 'false')
    return Response(json.dumps(response), status=200, mimetype='application/json')

@app.route("/connect-master/")
def connect_master():
    response = airtime_api.notify_source_status('master_dj', 'true')
    return Response(json.dumps(response), status=200, mimetype='application/json')

#########
# CUSTOM STATUS API
#########

@app.route("/status-summary/")
def get_status_summary():
    response = {}
    response['recorder'] = get_recorder_status()
    response['live_info'] = airtime_api.get_live_info()
    response['on_air_light'] = airtime_api.get_on_air_light()
    response['studio_darkice'] = None
    return Response(json.dumps(response), status=200, mimetype='application/json')

#########
# RECORDER
#########

def get_recorder_status():
    from datetime import datetime
    STATES = shared_with_recording_process['STATES']
    recording_state = shared_with_recording_process['recording_state'].value
    recording_start_datetime = datetime.fromtimestamp(shared_with_recording_process['recording_start_timestamp'].value)
    label = STATES(recording_state).name
    if STATES(recording_state) is STATES.RECORDING:
        label = "%s: %s" % (STATES.RECORDING.name, str(datetime.now() - recording_start_datetime).split('.')[0])
    return { 'status': recording_state, 'text': label}

@app.route("/recording-request-cut/")
# send filename
def cut():
    shared_with_recording_process['interrupt'].set()
    return "Cut requested."

@app.route("/recording-disconnect-stop/")
def disconnect_stop():
    response = airtime_api.notify_source_status('master_dj', 'false')
    # gives no response on success or failure :/
    return Response("Disconnection of Master Source (master_dj) requested.", status=200, mimetype='application/json')

@app.route("/recording-connect-start/")
def connect_start():
    response = airtime_api.notify_source_status('master_dj', 'true')
    # gives no response on success or failure :/
    return Response("Connection of Master Source (master_dj) requested.", status=200, mimetype='application/json')

def flaskThread(port=None, shared=None):
    global shared_with_recording_process
    shared_with_recording_process = shared
    try:
        port = port or args.port
    except NameError:
        port = None # default port 5000
    logging.info("Starting Webserver at %i" % port)
    app.run(port=port, host='0.0.0.0')

if __name__ == "__main__":
    threading.Thread(target=flaskThread).start()