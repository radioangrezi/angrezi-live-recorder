# live-recorder

Audio recorder build in Python to work together with [LibreTime](https://github.com/LibreTime/libretime) / [Airtime](https://www.airtime.pro/), for usage in radio studio (or similar).

Records a http radio stream (via streamripper) for a maximum duration of 24 hours.
Allows to remotely trigger cuts via HTTP request. Comes with a very simple frontend.

## Requirements

- Python 2.7 (3.X is not supported by `api_client.py)
- pip and virtualenv (recommended)
- streamripper (binary, e.g. via `apt install streamripper`)
- install requirements via `pip install -r requirements.txt`

## Usage

`recorder.py --port 5000 --airtime-conf airtime.conf --stream https://st02.sslstream.dlf.de/dlf/02/128/mp3/stream.mp3 rec-test_%station_%Y-%m-%d-%H-%M-%S_%label.mp3

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
