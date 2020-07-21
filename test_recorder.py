from __future__ import unicode_literals
import os
import time
# -*- coding: utf-8 -*-

# default test values / parser args

port = 5000

stream = "https://st02.sslstream.dlf.de/dlf/02/128/mp3/stream.mp3"
filename = "rec-test_%station_%Y-%m-%d-%H-%M-%S_%label.mp3"


from recorder import StreamRecorderWithAirtime


def test_recorder():
    rec = StreamRecorderWithAirtime(stream, filename)
    rec.start()
    time.sleep(1)
    rec.stop()
    os.remove(rec.filename)


def test_webserver():
    pass


def test_api_connection():
    pass


