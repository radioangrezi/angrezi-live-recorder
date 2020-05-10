#!/usr/bin/env python3
"""

Record form a local sound device in with (almost) arbitrary duration.
Files fill be cut when max size for wav of 4 GB is reached.
Allows remote triggerd cuts via HTTP request. Does not start automatically.

Based on: https://python-sounddevice.readthedocs.io/en/0.3.14/examples.html#recording-with-arbitrary-duration

"""
import argparse
import tempfile
import sys
import signal
from datetime import datetime
import time
import threading
from enum import Enum
import os, sys
from flask_cors import CORS
import multiprocessing
import logging
import numpy
import subprocess 

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
    help='input device (numeric ID or substring). Cant be used with --stream.')
parser.add_argument(
    '-r', '--samplerate', type=int, default=4400, help='sampling rate')
parser.add_argument(
    '-c', '--channels', type=int, default=2, help='number of input channels')
parser.add_argument(
    '-t', '--subtype', type=str, help='sound file subtype (e.g. "PCM_24")')
parser.add_argument(
    '-p', '--port', type=int, help='web server port for API requests. if empty server will not be started.')
parser.add_argument(
    '--debug', help='Output DEBUG log.', action='store_true')
parser.add_argument(
    '--airtime-conf', type=str, help='Airtime config file to read. Usually: /etc/airtime/airtime.conf')
parser.add_argument(
    'filename', nargs='?', metavar='FILENAME', help='audio file to store recording to')
parser.add_argument(
    '-s', '--stream', type=str,
    help='Stream url to record with streamripper. Cant be used with --device.')
args = parser.parse_args()

# recording states

class STATES(Enum):
    ERROR = -2
    CUTTING = -1
    IDLE = 0
    RECORDING = 1
    STOPPED = 2

# signal to start and stop recording

class SignalEvent(object):

    value = False

    def is_set(self):
        return self.value

    def set(self, value):
        self.value = value

    def clear(self):
        self.value = False

interrupt = SignalEvent()
recording_on_off = False

def receive_signal_start(signum, stack):
    global recording_on_off, interrupt
    interrupt.set(False)
    recording_on_off = True

def receive_signal_stop(signum, stack):
    global recording_on_off, interrupt
    interrupt.set(True)
    recording_on_off = False

def receive_signal_cut(signum, stack):
    global recording_on_off, interrupt
    interrupt.set(True)
    recording_on_off = True

signal.signal(signal.SIGUSR1, receive_signal_start)
signal.signal(signal.SIGUSR2, receive_signal_stop)
signal.signal(signal.SIGALRM, receive_signal_cut)

# these are shared between processes

recording_start_timestamp = multiprocessing.Value('d', 0)

def set_recording_timestamp(timestamp):
    recording_start_timestamp.value = timestamp

recording_state = multiprocessing.Value('i', 0)

def set_recording_state(enum):
    recording_state.value = enum.value
def get_recording_state_enum(state):
    return STATES(state.value)

recording_filename_recv , recording_filename_send = multiprocessing.Pipe(duplex=False)
recording_showslug_recv , recording_showslug_send = multiprocessing.Pipe(duplex=False)

# WEB API in a separate process

from app import flaskThread, connect_to_airtime_api
shared = {}
shared['recording_start_timestamp'] = recording_start_timestamp
shared['recording_state'] = recording_state
shared['recording_showslug_send'] = recording_showslug_send
shared['recording_filename_recv'] = recording_filename_recv
shared['STATES'] = STATES

api_server = None

DEVICE = 'device'
STREAM = 'stream'
SOURCE = None

def start_api_server(port=5000):
    global api_server
    if __name__ == "__main__":
        connect_to_airtime_api(args.airtime_conf)
        api_server = multiprocessing.Process(target=flaskThread, kwargs={'shared':shared,'port':port,'debug':args.debug,'rec_pid':os.getpid()})
        api_server.start()

# AUDIO RECORDER - based on https://python-sounddevice.readthedocs.io/en/0.3.12/examples.html#recording-with-arbitrary-duration

logging.basicConfig()
log = logging.getLogger('recorder')

if args.debug:
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)

try:
    import sounddevice as sd
    import soundfile as sf

    if args.list_devices:
        print(sd.query_devices())
        parser.exit(0)

    if args.filename is None:
        print("Error: No filename argument provided. Use -h for help.")
        parser.exit(0)

    if args.stream is not None and args.device is not None:
        print("Error: Audio device and stream url rguments given! Use --stream to record from stream url OR --device to record from local device. Use -h for help.")
        parser.exit(0)

    if args.stream is not None:
        SOURCE = STREAM
    else:
        SOURCE = DEVICE

    # only start api server if port argument is set. just record if not.
    if args.port:
        start_api_server(port=args.port)
    else:
        # autostart recording if no webserver
        recording_on_off = False
        # FIXME back to True

    if args.samplerate is None:
        device_info = sd.query_devices(args.device, 'input')
        # soundfile expects an int, sounddevice provides a float:
        args.samplerate = int(device_info['default_samplerate'])

    q = queue.Queue()

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
                # recordning loop: running once per frame (or until q is empty)
                while True: 
                    # enforce a hard limit on the file size (wav max: ~ 4 GB)
                    data_size = len(file) * frame_size
                    # log.debug("Current data size: %i" % data_size)
                    if interrupt.is_set() and data_size < 10:
                        # two cuts without any data in between.
                        # skip cut
                        interrupt.clear()

                    if interrupt.is_set() or data_size >= max_data_size:
                        interrupt.clear()
                        log.info("Recorder: making cut")
                        log.info('Recorder: Finished file ' + repr(filename))
                        file.close()
                        set_recording_state(STATES.IDLE)
                        return -1 # stop / end of recording (need new filename)
                    else:
                        set_recording_state(STATES.RECORDING)
                        file.write(q.get())

    def record_stream_to_file(filename):
        global recording_state, recording_start_timestamp
        # alternative: https://github.com/jpaille/streamripper
        ripper = subprocess.Popen([
            'streamripper',
            args.stream,
            #'-d',
            #'./streams',
            #'-l',
            #'10800',
            '-A',
            '-a',
            filename
        ])
        set_recording_timestamp(time.mktime(datetime.now().timetuple()))
        # enforce a hard limit on the file size (wav max: ~ 4 GB). THIS IS MP3, now!
        set_recording_state(STATES.RECORDING)
        time.sleep(600)
        if interrupt.is_set():
            interrupt.clear()
            log.info("Recorder: making cut")
            log.info('Recorder: Finished file ' + repr(filename))
            ripper.terminate()
            try:
                os.system("rm *.cue")
            except:
                pass
            set_recording_state(STATES.IDLE)
            return -1 # stop / end of recording (need new filename)
        print('cleanup')
        ripper.terminate()


    def generate_filename_and_directory():
        # add date and time to filename
        filename = datetime.now().strftime(args.filename)

        # get show name from pipe and add to filename if available
        if recording_showslug_recv.poll():
            recording_filename = recording_showslug_recv.recv()
            if recording_filename and recording_filename is not "":
                name, extension = os.path.splitext(filename)
                filename = name + "_" + recording_filename + extension

        # send full filename back to (another) pipe to the frontend
        recording_filename_send.send(filename)
        log.info('Recorder: Starting file ' + repr(filename))

        directory = os.path.dirname(filename) or os.getcwd()
        if not os.path.exists(directory):
            os.makedirs(directory)

        return filename


    i = 0
    # file loop: runs once per recordning, waiting (ideling) unlimitedly until a new recoring shall start
    print('#' * 80)
    print('press Ctrl+C to stop the recording')
    print('#' * 80)
    while True:
        # do not run if (requested) state is not off (False)
        if recording_on_off:
            if SOURCE is STREAM:
                filename = generate_filename_and_directory()
                print('recording from stream...')
                if record_stream_to_file(filename) != -1:
                    break
                i = i + 1
            else:
                filename = generate_filename_and_directory()
                print('recording from device...')
                if record_to_file(filename) != -1:
                    break
                i = i + 1
        time.sleep(1)

except KeyboardInterrupt:
    if api_server:
        api_server.terminate()
        api_server.join()

    try:
        os.system("rm *.cue")
    except:
        pass
    set_recording_state(STATES.ERROR)
    parser.exit(0)

except Exception as e:
    set_recording_state(STATES.ERROR)
    parser.exit(type(e).__name__ + ': ' + str(e))
