# live-recorder

## usage

should work with Python 2.7 and 3

### Linux

`python /var/angrezi/live-recorder/recorder.py -d stream_in_16 -t PCM_16 "%Y/%m/%d/studio-live-%Y-%m-%d-%H-%M-%S.wav"`

### Mac

`python recorder.py -d 0 rec-test-%Y-%m-%d-%H-%M-%S.wav`

### Dev

Webserver only: `flask run`