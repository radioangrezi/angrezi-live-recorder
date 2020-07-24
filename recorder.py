#!/usr/bin/env python2

# RADIO ANGREZI
# WEB (STREAM) RECORDER
# 2020-07-20, ja

# This is a micro-web-service.
# It will let you do these simple things:

# + record a web audio stream to disk (via streamripper)
# + no more: record from a local sound input to disk (this feature was part of v1)
# + connect to the Airtime / Libretime API to fetch a show schedule / metadata
# + auto-start the recording when a next show start
# + manually start and and stop a recording
# + set a name for the recorded file
# + auto generate a name form the show meta data using the API
# + auto-schedule recordings
# + auto-finish recordings after duration

# The service is called and configured only via command line arguments.
# Each recording is handeled in a separate process (streamripper).
# (v1 showed that doing the recording in python causes high CPU utilization and synchronizing problems.)

# Requirements_
# + streamrippper (binary), alternative: python-streamripper or radiorec
# + flask
# + airtime_api (REQUIRES PYTHON 2!)


from future.standard_library import install_aliases
install_aliases()

from flask import Flask
from flask import jsonify
from flask import request
from flask_cors import CORS
import logging, os
import threading
import argparse
import datetime
import subprocess
from urllib.request import urlopen, urlparse
import signal
import sys
from airtime_schedule import AirtimeRecordingScheduler, scheduler

app = Flask(__name__)
cors = CORS(app, resources={r"/*": {"origins": "*"}})

werkzeug_log = logging.getLogger('werkzeug')
werkzeug_log.setLevel(logging.WARNING)

log = logging.getLogger('recorder')
log.setLevel(logging.WARNING)

parser = argparse.ArgumentParser(description=__doc__)
# parser.add_argument(
#     '-l', '--list-devices', action='store_true',
#     help='show list of audio devices and exit')
# parser.add_argument(
#     '-d', '--device', type=int_or_str,
#     help='input device (numeric ID or substring). Cant be used with --stream.')
# parser.add_argument(
#     '-r', '--samplerate', type=int, default=4400, help='sampling rate')
# parser.add_argument(
#     '-c', '--channels', type=int, default=2, help='number of input channels')
# parser.add_argument(
#     '-t', '--subtype', type=str, help='sound file subtype (e.g. "PCM_24")')
parser.add_argument(
    '-s', '--stream', required=True, type=str,
    help='Stream url to record with streamripper.')
parser.add_argument(
    '-p', '--port', type=int, required=True, help='web server port for API requests. If empty server will not be started.')
parser.add_argument(
    '--debug', help='Output debug messages.', action='store_true')
parser.add_argument(
    '-v', '--verbose', help='Output info messages.', action='store_true')
parser.add_argument(
    '--airtime-conf', type=str, help='Airtime config file to read. Usually: /etc/airtime/airtime.conf')
parser.add_argument(
    'filename', nargs='?', metavar='FILENAME', help='audio file to store recording to. Use %station and %label to include metadata, strftime() codes for time.')
args = parser.parse_args()

if args.verbose:
    log.setLevel(logging.INFO)

if args.debug:
    log.setLevel(logging.DEBUG)

# uses api_client.py (from source libretime/python_apps/api_clients/api_clients/api_client.py)
# from past.translation import autotranslate
# autotranslate('api_client')
# autotranslation did not work.
from api_client import AirtimeApiClient
airtime_api = None

DEFAULT_FILENAME = "stream-rec_%station_%Y-%m-%d-%H-%M-%S.ext"
MAX_DURATION_IN_SEC = 24 * 60 * 60 # 24h
MAX_SILENCE_IN_SEC = 60 * 10 # 10min

class STATES(object):
    ERROR = -2
    CUTTING = -1
    IDLE = 0
    RECORDING = 1
    STOPPED = 2

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
# DATA MODEL
#########


class StreamRecorderWithAirtime(object):

    # class variables
    process = None

    # url =
    # start_time = None
    # end_duration = None
    # max_duration = time.timedelta(hours=24)
    filename_pattern = DEFAULT_FILENAME
    #directory = None
    process = None

    def __init__(self, url, filename_pattern = DEFAULT_FILENAME):
        self.start_time = None

        # check if url exists, fails if it does not
        urlopen(url)
        self.url = url
        url_name, self.extension = os.path.splitext(url)
        self.filename_pattern, filename_extension = os.path.splitext(filename_pattern)
        self.station_name = slugify(unicode(urlparse(url).netloc))

        self.directory = None
        self.filename = None
        self._filename = None

    def start(self, name=None):
        if self.running(): return
        self.start_time = datetime.datetime.now()
        self.generate_filename_and_directory(label='incomplete')
        self.record_stream_to_file()
        if not name:
            self.name = get_show_name()
        else:
            self.name = slugify(name)

    def stop(self):
        log.debug("Recording stop called.")
        if not self.running(): return
        self.stop_recording()
        self.update_filename()

    def duration(self):
        try:
            return datetime.datetime.now() - self.start_time
        except TypeError:
            return datetime.timedelta()

    @classmethod
    def running(cls):
        if cls.process:
            return cls.process.poll() is None
        else:
            return False

    def update_filename(self):
        # get show name form API and add to filename if available
        # TODO make API / source pluggable, so you are not dependend on Airtime
        # TODO allow for a custom name that is added
        if self.name and self.name is not "":
            self.generate_filename_and_directory(label=self.name)
        else:
            self.generate_filename_and_directory(label='')

        print(os.path.join(self.directory, self.filename))
        try:
            os.rename(os.path.join(self.directory, self._filename), os.path.join(self.directory, self.filename))
            self._filename = self.filename
        except OSError:
            pass

    def generate_filename_and_directory(self, label='unnamed'):
        filename = self.filename_pattern
        filename = filename.replace('%station', self.station_name)
        filename = filename.replace('%label', label)
        filename = self.start_time.strftime(filename)
        filename = filename.strip(" _.")
        filename += self.extension

        log.info('File: ' + repr(filename))

        directory = os.path.dirname(filename) or os.getcwd()
        if not os.path.exists(directory):
            os.makedirs(directory)

        self.directory = directory
        self.filename = filename

    def record_stream_to_file(self):
        # alternative to streamripper: https://github.com/jpaille/streamripper
        # TODO add max duration
        # TODO remove .cue files
        log.debug('Starting streamripper')
        self._filename = self.filename.replace('%', '') # make sure no tokens are left. otherwise we will not find the file again.
        # streamripper manpage: http://manpages.ubuntu.com/manpages/bionic/man1/streamripper.1.html
        self.__class__.process = subprocess.Popen([
            'streamripper',
            self.url,
            '-l', # Run for a predetermined length of time, in seconds
            str(MAX_DURATION_IN_SEC),
            '-A', # Don't create individual tracks
            '-o',
            'never', # never overwrite files
            '-t', # Don't overwrite tracks in incomplete directory
            '--debug' if args.debug else '',
            '--xs_silence_length=' + str(MAX_SILENCE_IN_SEC),
            '--xs2', # Use capisce's new algorithm (Apr 2008) for silence detection.
            '--codeset-metadata=utf8',
            #'-i', # dont add id3
            '-s', # no subfolder for each stream
            '-a',  # Dont create individual files. Set pattern for output filename. Will create .cue.
            self._filename
        ])
        self.start_time = datetime.datetime.now() # update starttime for more precision
        #set_recording_state(STATES.RECORDING)

    def stop_recording(self):
        if not self.running(): return
        log.info('Finishing file ' + repr(self._filename))
        self.__class__.process.terminate()
        self.__class__.process.wait()
        log.debug('Streamripper terminated.')
        # you can not get rid of the .cue, if you use the -a flag, which we need.
        try:
            os.system("rm *.cue")
        except:
            pass

#########
# DIRECT AIRTIME API "PROXY"
#########

from flask import Response
import json

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
    if airtime_api:
        response['live_info'] = airtime_api.get_live_info()
        response['on_air_light'] = airtime_api.get_on_air_light()
    return Response(json.dumps(response), status=200, mimetype='application/json')


#########
# RECORDER API
#########

current_filename = None


def get_recorder_status():
    if RECORDER.running():
        label = "%s: %s" % ("REC", str(RECORDER.duration()).split('.')[0])
        filename = RECORDER.filename
        return { 'status': STATES.RECORDING, 'text': label, 'filename': filename }
    else:
        return { 'status': STATES.IDLE, 'text': "IDLE", 'filename': '-'}


def get_show_name():
    if not airtime_api: return None
    live_info = airtime_api.get_live_info()
    if live_info and live_info['currentShow'] and live_info['currentShow'][0] and live_info['currentShow'][0]['name']:
        name = slugify(live_info['currentShow'][0]['name'])
        return name


@app.route("/recording-request-cut/")
def cut():
    RECORDER.stop()
    RECORDER.start()
    return Response("New file requested.", status=200, mimetype='application/json')


@app.route("/recording-disconnect-stop/")
def disconnect_stop():
    RECORDER.stop()
    response = airtime_api.notify_source_status('master_dj', 'false')
    # gives no response on success or failure :/
    return Response("Disconnection of Master Source (master_dj) requested.", status=200, mimetype='application/json')


@app.route("/recording-connect-start/")
def connect_start():
    RECORDER.start()
    response = airtime_api.notify_source_status('master_dj', 'true')
    # gives no response on success or failure :/
    return Response("Connection of Master Source (master_dj) requested.", status=200, mimetype='application/json')


@app.route("/recording-stop/")
def rec_stop():
    RECORDER.stop()
    return Response("Recording stopped.", status=200, mimetype='application/json')


@app.route("/recording-start/")
def rec_start():
    RECORDER.start()
    return Response("Recording started.", status=200, mimetype='application/json')


def connect_to_airtime_api(airtime_config='airtime.conf'):
    airtime_api = AirtimeApiClient(config_path=airtime_config)
    if not airtime_api.is_server_compatible():
        raise Exception("Server is not compatible with API.")
        quit()
    return airtime_api


if __name__ == "__main__":

    if args.airtime_conf:
        airtime_api = connect_to_airtime_api(args.airtime_conf)

    port = args.port or None # default port 5000
    debug = args.debug or False

    RECORDER = StreamRecorderWithAirtime(args.stream, args.filename)
    SCHEDULE = AirtimeRecordingScheduler(airtime_api, RECORDER)

    log.debug("Starting Webserver at %i" % port)
    # Do not use run(debug=True)! It will run a second instance of the process, thus a second scheduler etc.
    app.run(port=port, host='localhost')

    print("Shutting down...")
    RECORDER.stop()
    try:
        os.system("rm *.cue")
    except OSError:
        pass

    parser.exit(0)