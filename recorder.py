#!/usr/bin/env python3
"""Record form a local sound device in with (almost) arbitrary duration. Files fill be cut when max size for wav of 4 GB is reached. Allows remote triggerd cuts via HTTP request.
"""
import argparse
import tempfile
import sys
import signal
from datetime import datetime
import time
import threading
from flask import Flask
from flask import jsonify
from flask import request
from enum import Enum
import os, sys
from flask_cors import CORS
import multiprocessing
import logging
import numpy

# python 2/3 compatible
try: 
    import queue
except ImportError:
    import Queue as queue

def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    '-l', '--list-devices', action='store_true',
    help='show list of audio devices and exit')
parser.add_argument(
    '-d', '--device', type=int_or_str,
    help='input device (numeric ID or substring)')
parser.add_argument(
    '-r', '--samplerate', type=int, default=44100, help='sampling rate')
parser.add_argument(
    '-c', '--channels', type=int, default=2, help='number of input channels')
parser.add_argument(
    '-t', '--subtype', type=str, help='sound file subtype (e.g. "PCM_24")')
parser.add_argument(
    '-p', '--port', type=int, help='web server port for API requests. if empty server will not be started.')
parser.add_argument(
    'filename', nargs='?', metavar='FILENAME', help='audio file to store recording to')
args = parser.parse_args()

# recording states

class STATES(Enum):
    ERROR = -2
    UNKOWN = -1
    IDLE = 0
    RECORDING = 1
    STOPPED = 2

# these are shared between processes

interrupt = multiprocessing.Event()

recording_start_timestamp = multiprocessing.Value('d', 0)
def set_recording_timestamp(timestamp):
    recording_start_timestamp.value = timestamp

recording_state = multiprocessing.Value('i', 0)
def set_recording_state(enum):
    recording_state.value = enum.value
def get_recording_state_enum(state):
    return STATES(state.value)

api_server = None

# WEB API - super simple flask server

def run_api_server(interrupt, recording_state, recording_start_timestamp, port=5000):

    app = Flask(__name__)
    cors = CORS(app, resources={r"/*": {"origins": "*"}})

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.INFO)

    @app.route("/")
    def state():
        t = get_recording_state_enum(recording_state).name
        if get_recording_state_enum(recording_state) is STATES.RECORDING:
            t = "%s: %s" % (STATES.RECORDING.name, datetime.now() - datetime.fromtimestamp(recording_start_timestamp.value))
        return jsonify({'status': get_recording_state_enum(recording_state).value, 'text': t})

    @app.route("/reset")
    def reset():
        interrupt.set()
        log.info("api: cut requested")
        return jsonify({'status': get_recording_state_enum(recording_state).value, 'text': 'cut requested'})

    # start (in Process)
    app.run(port=port, host='0.0.0.0')

def start_api_server(port=5000):
    global api_server
    if __name__ == "__main__":
        api_server = multiprocessing.Process(target=run_api_server, args=(interrupt, recording_state, recording_start_timestamp), kwargs={'port':port})
        api_server.start()

# AUDIO RECORDER - based on https://python-sounddevice.readthedocs.io/en/0.3.12/examples.html#recording-with-arbitrary-duration

logging.basicConfig()
log = logging.getLogger('recorder')
log.setLevel(logging.INFO)

try:
    import sounddevice as sd
    import soundfile as sf

    if args.list_devices:
        print(sd.query_devices())
        parser.exit(0)

    if args.filename is None:
        print("error: no FILENAME argument provided. Use -h for help.")
        parser.exit(0)

    if args.port:
        start_api_server(port=args.port)

    if args.samplerate is None:
        device_info = sd.query_devices(args.device, 'input')
        # soundfile expects an int, sounddevice provides a float:
        args.samplerate = int(device_info['default_samplerate'])

    q = queue.Queue()

    print('#' * 80)
    print('press Ctrl+C to stop the recording')
    print('#' * 80)

    import copy

    def callback(indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print("%i: %s" % (frames, status))
        q.put(indata.copy())

    def record_to_file(filename):
        global recording_state, recording_start_timestamp
        max_data_size = numpy.iinfo(numpy.int32).max + 8# unsigned int
        log.debug("Max data size of wav: %i" % max_data_size)
        # Make sure the file is opened before recording anything:
        with sf.SoundFile(filename, mode='x', samplerate=args.samplerate,
                          channels=args.channels, subtype=args.subtype) as file:
            with sd.InputStream(samplerate=args.samplerate, device=args.device,
                                channels=args.channels, callback=callback,
                                blocksize=16, dtype='int16') as input:
                set_recording_timestamp(time.mktime(datetime.now().timetuple()))
                frame_size = file.channels * numpy.dtype(input.dtype).itemsize
                while True:
                    # enforce a hard limit on the file size (wav max: ~ 4 GB)
                    data_size = file.frames * frame_size
                    # log.debug("Current data size: %i" % data_size)
                    if interrupt.is_set() or data_size >= max_data_size:
                        interrupt.clear()
                        log.info("making cut")
                        set_recording_state(STATES.STOPPED)
                        log.info('Recording finished: ' + repr(filename))
                        file.close()
                        return -1
                    else:
                        set_recording_state(STATES.RECORDING)
                        file.write(q.get())



    i = 0
    while True:
        filename = datetime.now().strftime(args.filename)
        directory = os.path.dirname(filename) or os.getcwd()
        if not os.path.exists(directory):
            os.makedirs(directory)
        if record_to_file(filename) != -1:
            break
        i = i + 1

except KeyboardInterrupt:
    if api_server:
        api_server.terminate()
        api_server.join()

    set_recording_state(STATES.ERROR)
    print('\nRecording finished: ' + repr(filename))
    parser.exit(0)

except Exception as e:
    set_recording_state(STATES.ERROR)
    parser.exit(type(e).__name__ + ': ' + str(e))
