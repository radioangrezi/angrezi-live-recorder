#!/usr/bin/env python3
"""Create a recording with arbitrary duration.

PySoundFile (https://github.com/bastibe/PySoundFile/) has to be installed!

"""
import argparse
import tempfile
import queue
import sys
import signal
from datetime import datetime
import threading
from flask import Flask
from flask import jsonify
from flask import request
from enum import Enum

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
#parser.add_argument(
#    'filename', nargs='?', metavar='FILENAME',
#    help='audio file to store recording to')
parser.add_argument(
    '-t', '--subtype', type=str, help='sound file subtype (e.g. "PCM_24")')
parser.add_argument(
    '-p', '--port', type=int, help='web server port', default=5000)
args = parser.parse_args()

class STATES(Enum):
    ERROR = -2
    UNKOWN = -1
    IDLE = 0
    RECORDING = 1
    STOPPED = 2

# these are shared between threads

interrupt = threading.Event()
recording_start_datetime = None
recording_state = STATES.IDLE

# super simple flask web api

app = Flask(__name__)

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
    app.run(port=args.port, host='0.0.0.0')

if __name__ == "__main__":
    threading.Thread(target=flaskThread).start()

try:
    import sounddevice as sd
    import soundfile as sf

    if args.list_devices:
        print(sd.query_devices())
        parser.exit(0)
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
            print("%i: %s" % (frames, status), file=sys.stderr)
        q.put(indata.copy())

    def record_to_file(filename):
        global recording_state, recording_start_datetime
        # Make sure the file is opened before recording anything:
        with sf.SoundFile(filename, mode='x', samplerate=args.samplerate,
                          channels=args.channels, subtype=args.subtype) as file:
            with sd.InputStream(samplerate=args.samplerate, device=args.device,
                                channels=args.channels, callback=callback,
                                blocksize=16, dtype='int16'):
                recording_start_datetime = datetime.now()
                while True:
                    if interrupt.is_set():
                        interrupt.clear()
                        print("### MAKING CUT ####")
                        recording_state = STATES.STOPPED
                        print('\nRecording finished: ' + repr(filename))
                        file.close()
                        return -1
                    else:
                        recording_state = STATES.RECORDING
                        file.write(q.get())

    i = 0
    while True:
        filename = datetime.now().strftime("studio-live-%Y-%m-%d-%H-%M-%S.wav")
        if record_to_file(filename) != -1:
            break
        i = i + 1

except KeyboardInterrupt:
    recording_state = STATES.ERROR
    print('\nRecording finished: ' + repr(filename))
    parser.exit(0)
except Exception as e:
    recording_state = STATES.ERROR
    parser.exit(type(e).__name__ + ': ' + str(e))
