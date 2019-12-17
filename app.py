#!/usr/bin/env python3

# RADIO ANGREZI CONTROLLER
# 2019-06-02, ja

# TODO: enhance frontend
# TODO: loggin to propper logfile
# TODO: add _part-XX if show longer than max. file length
# ERROR: segmentation fault 11. 
# ERROR: input overflow

# TODO: v2 cleanup api
# TODO: v2 reimplement frontend with react / backbone
# TODO: less requests?! websocket? or scheduled request similar to player frontend?
# TODO: State conditions: Only record if connected -> No. It is nice to be able to record without connection. (It just needs better representation in the frontend.)
# TODO: dont use flask in production!

import threading
from flask import Flask
from flask import jsonify
from flask import request
from flask_cors import CORS
# from flask_socketio import SocketIO

from api_client import AirtimeApiClient

# AIRTIME_CONFIG = '/etc/airtime/airtime.conf'
AIRTIME_CONFIG = 'airtime.conf'

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})
app.config['SECRET_KEY'] = 'YQbv2CkMndeRe5dE'
# socketio = SocketIO(app)

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

logging.basicConfig(level=logging.WARNING)

shared_with_recording_process = None

#########
# HELPERS
#########

def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    """
    import unicodedata, re
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
    value = unicode(re.sub('[^\w\s-]', '', value).strip().lower())
    value = unicode(re.sub('[-\s]+', '-', value))
    return value

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
# ACTIONS: not used in production
#########

@app.route("/disconnect-master/")
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

current_filename = None

def get_recorder_status():
    global current_filename
    from datetime import datetime
    recording_state = shared_with_recording_process['recording_state'].value
    recording_start_datetime = datetime.fromtimestamp(shared_with_recording_process['recording_start_timestamp'].value)
    label = STATES(recording_state).name
    if STATES(recording_state) is STATES.RECORDING:
        label = "%s: %s" % (STATES.RECORDING.name, str(datetime.now() - recording_start_datetime).split('.')[0])
    if shared_with_recording_process['recording_filename_recv'].poll():
            current_filename = shared_with_recording_process['recording_filename_recv'].recv()
    return { 'status': recording_state, 'text': label, 'filename': current_filename}

def get_show_name_and_send_to_pipe():
    live_info = airtime_api.get_live_info()
    if live_info and live_info['currentShow'] and live_info['currentShow'][0] and live_info['currentShow'][0]['name']:
        name = slugify(live_info['currentShow'][0]['name'])
        shared_with_recording_process['recording_showslug_send'].send(name)

@app.route("/recording-request-cut/")
def cut():
    get_show_name_and_send_to_pipe()
    shared_with_recording_process['interrupt'].set()
    shared_with_recording_process['recording_on_off'].value = True
    return Response("New file requested.", status=200, mimetype='application/json')

@app.route("/recording-disconnect-stop/")
def disconnect_stop():
    shared_with_recording_process['recording_on_off'].value = False
    shared_with_recording_process['interrupt'].set()
    response = airtime_api.notify_source_status('master_dj', 'false')
    # gives no response on success or failure :/
    return Response("Disconnection of Master Source (master_dj) requested.", status=200, mimetype='application/json')

@app.route("/recording-connect-start/")
def connect_start():
    get_show_name_and_send_to_pipe()
    shared_with_recording_process['recording_on_off'].value = True
    response = airtime_api.notify_source_status('master_dj', 'true')
    # gives no response on success or failure :/
    return Response("Connection of Master Source (master_dj) requested.", status=200, mimetype='application/json')

def flaskThread(port=None, shared=None, debug=False):
    global shared_with_recording_process, STATES
    shared_with_recording_process = shared
    STATES = shared_with_recording_process['STATES']
    get_show_name_and_send_to_pipe()
    try:
        port = port or args.port
    except NameError:
        port = None # default port 5000
    logging.info("Starting Webserver at %i" % port)
    app.run(port=port, host='0.0.0.0', debug=debug)

if __name__ == "__main__":
    threading.Thread(target=flaskThread).start()