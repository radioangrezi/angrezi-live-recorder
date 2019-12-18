# live-recorder

Audio recorder build in Python to work together with [LibreTime](https://github.com/LibreTime/libretime) / [Airtime](https://www.airtime.pro/), for usage in radio studio (or similar).

Records form a local sound device in with (almost) arbitrary duration.
Files fill be cut when max. size for wav (of ~ 4 GB) is reached.
Allows to remotely trigger cuts via HTTP request. Comes with a very simple frontend.

State: **Beta** (Check `app.py` for a to do list.)

## Requirements

- Python 2.7 (3.X is not supported by `api_client.py)
- pip and virtualenv (recommended)
- python-sounddevice supported soundcard as input device
- install requirements via `pip install -r requirements.txt`

## Usage

`recorder.py --list-devices` to list available input devices.
`recorder.py -d XX "%Y/%m/%d/studio-live-%Y-%m-%d-%H-%M-%S.wav"` to start recording without web server (does not autostart!)
`recorder.py --port 5000 -d XX "%Y/%m/%d/studio-live-%Y-%m-%d-%H-%M-%S.wav"` to start recording with webserver.

### Examples

Linux (Production): `python /var/angrezi/live-recorder/recorder.py -d stream_in_16 -t PCM_16 "%Y/%m/%d/studio-live-%Y-%m-%d-%H-%M-%S.wav"`
Mac (Development): `python recorder.py -d 0 rec-test-%Y-%m-%d-%H-%M-%S.wav`
Webserver only (Development): `flask run`

## Architecture

### `recorder.py`

(parent process)

Simple recorder build with `python-sounddevice` to record form a given input device to a wav file.

Based on: https://python-sounddevice.readthedocs.io/en/0.3.14/examples.html#recording-with-arbitrary-duration

### `app.py`

(child process)

Simple API build with Flask to control the recorder, and proxy requests to the Airtime API (which otherwise would need authentication).

## API

#### `/status-summary/`

Returns a JSON object containing info on the recorder (including: recording time, state, filename), current show (from Airtime), the On-Air-Light (from Airtime).

#### `/recording-request-cut/`

Shall inform `recorder.py` to start a new file.

Returns 200 and a success message if the request is posted to the pipe (other process). This does not mean that the cut did take place!

#### `/recording-disconnect-stop/`

Shall inform Airtime to disconnect the master source and `recorder.py` to stop recording (run idle).

Returns 200 and a success message if the request is posted to the pipe (other process). This does not mean that that all actions did take place!

#### `/recording-connect-start/`

Shall inform Airtime to connect the master source and `recorder.py` to start recording.

Returns 200 and a success message if the request is posted to the pipe (other process). This does not mean that that all actions did take place!

#### `/airtime/live-info/`
#### `/airtime/on-air-light/`
#### `/airtime/bootstrap-info/`

Proxy calls to Airtime API (without changes).

#### `/disconnect-master/`
#### `/connect-master/`

Direct calls to connect or disconnect the master source. Currently not used in frontend.
