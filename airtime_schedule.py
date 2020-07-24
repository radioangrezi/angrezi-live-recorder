import datetime
import threading
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
import traceback, os
import pytz
from tzlocal import get_localzone

scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SECONDS_WITHIN_START_IMMEDIATELY = 3
SECONDS_RELOAD = 5
SECONDS_MIN_DURATION = 10

assert SECONDS_WITHIN_START_IMMEDIATELY < SECONDS_RELOAD
# otherwise you will miss some beginnings


def now():
    try:
        localtz = get_localzone()
    except:
        localtz = pytz.UTC
    return localtz.localize(datetime.datetime.now())


class GenericBroadcast(object):

    start = datetime.datetime
    end = datetime.datetime
    name = "NO NAME"
    id = 0


class AirtimeBroadcast(GenericBroadcast):
    # modeled and named after Airtime API:

    # end_timestamp: "2020-07-21 21:00:00"
    # ends: "2020-07-21 21:00:00"
    # id: 611
    # image_path: ""
    # instance_id: 732
    # name: "(test) rec"
    # record: 1
    # start_timestamp: "2020-07-21 20:00:00"
    # starts: "2020-07-21 20:00:00"
    # type: "show"
    # url: ""

    # airtime_api.get_live_info()
    # airtime_api.get_on_air_light()

    def __init__(self, r, timezone=pytz.UTC):
        self.timezone = timezone
        print(self.timezone)
        self.load_dict(r)

    def load_dict(self, r):
        # this is also used to update the dict later on
        self._dict = r

        self.start = datetime.datetime.strptime(r['starts'], '%Y-%m-%d %H:%M:%S')
        self.start = self.timezone.localize(self.start)
        self.end = datetime.datetime.strptime(r['ends'], '%Y-%m-%d %H:%M:%S')
        self.end = self.timezone.localize(self.end)
        self.name = r['name']
        self.description = r['description']
        self.instance_id = int(r['instance_id'])
        self.id = int(r['id'])
        self.image_path = r['image_path']
        self.record = bool(r['record'])

    def is_same_dict(self, compare_r):
        return self._dict == compare_r

    def get_unique_id(self):
        return self.instance_id

    @classmethod
    def get_unique_id_from_dict(cls, r):
        return int(r['instance_id'])


def try_to_remove_job(job):
    try:
        job.remove()
    except (AttributeError, JobLookupError):
        pass


class AirtimeBroadcastRecording(AirtimeBroadcast):

    recorder = None

    def __init__(self, r, now=False, auto_schedule_recording=True, timezone=pytz.UTC):

        self.start_job = None
        self.start_job_date = None
        self.end_job = None
        self.end_job_date = None

        # load dict to broadcast
        super(AirtimeBroadcastRecording, self).__init__(r, timezone)

        # autoschedule
        if auto_schedule_recording:
            self.schedule_recording()

    def trigger_start(self, id, name):
        logger.debug("Start of recording was triggered.")
        try_to_remove_job(self.start_job)
        if AirtimeBroadcastRecording.recorder.running():
            logging.warning("Can not start scheduled rec. Recorder already running.")
            return

        AirtimeBroadcastRecording.recorder.start()
        try_to_remove_job(self.start_job)

    def trigger_end(self, id, name):
        logger.debug("End of recording was triggered.")
        if AirtimeBroadcastRecording.recorder.running():
            AirtimeBroadcastRecording.recorder.stop()
            try_to_remove_job(self.end_job)
        else:
            raise RuntimeError("Can not stop scheduled rec. Recorder not running.")

    def schedule_recording(self, start=True, end=True):
        if not self.record:
            logger.warning("This broadcasts has no recording enabled. Skipping.")
            return

        if self.end and self.start and (self.end - self.start < datetime.timedelta(seconds=10)):
            logger.warning("Scheduled recording will be shorter than 10 seconds. Aborting.")
            return

        if start:
            if self.start < now() + datetime.timedelta(seconds=SECONDS_WITHIN_START_IMMEDIATELY):
                # start immediately if start has passed or within 3 sec from now
                self.trigger_start(id=self.id, name=self.name)

            else:
                if self.start_job:
                    self.start_job.reschedule('date', run_date=self.start)
                    logger.info("Start was re-scheduled at %s with job %s" % (str(self.start), str(self.start_job.name)))
                else:
                    self.start_job = scheduler.add_job(self.trigger_start, 'date', run_date=self.start, name="rec-start-airtime-%i" % self.instance_id, kwargs={'id': self.instance_id, 'name': self.name})
                    logger.info("Start was scheduled at %s with job %s" % (str(self.start), str(self.start_job.name)))

        if end:
            if self.end_job:
                self.end_job.reschedule('date', run_date=self.end)
                logger.info("End was re-scheduled at %s with job %s" % (str(self.end), str(self.end_job.name)))
            else:
                self.end_job = scheduler.add_job(self.trigger_end, 'date', run_date=self.end,
                                                 name="rec-end-airtime-%i" % self.instance_id,
                                                 kwargs={'id': self.get_unique_id(), 'name': self.name})
                logger.info("End was scheduled at %s with job %s" % (str(self.end), str(self.end_job.name)))

        if self.record and self.end < now():
            logger.info("Broadcast is stale. Un-Scheduling...")
            self.unschedule_and_stop_recording()

    def unschedule_and_stop_recording(self):
            try_to_remove_job(self.start_job)
            try_to_remove_job(self.end_job)
            if self.start < now() and self.end >= now():
                self.recorder.stop()

# TODO listen to cancel() event on job via add_listener()?! to than cancel or stop recording
# TODO move schedule_recording etc. to Broadcast instance?!
# TOOO Reintegrate with models in recorder.py
# TODO move api out to api.py
# TODO compare StreamRecorderWithAirtime (.process, .end etc.) with Broadcast
# TODO leos bug report
# TODO shows are created twice, once in next and once
# TODO remove job if recording stopped via frontend. -> needs different connection to frontend / architecture!
# TODO no MORE POLLING IN FRONTEND!
# TODO many logger.info -> logger.debug


class AirtimeRecordingScheduler(object):

    class BroadcastSlot:

        rec_class = AirtimeBroadcastRecording
        scheduled_broadcasts = dict()

        def __init__(self, brodcast=None):
            self._broadcast = brodcast

        def __getattr__(self, item):
            return getattr(self._broadcast, item)

        def update(self, r, now=False, stop_stale=True, others=[], timezone=pytz.UTC):
            previous_broadcast = self._broadcast
            was_slot_updated = False

            if len(r) > 0 and  isinstance(r[0], dict):
                # if broadcast is passed
                r = r[0]
                id = self.rec_class.get_unique_id_from_dict(r)
                if self._broadcast and self._broadcast.is_same_dict(r):
                    was_slot_updated = False

                else:
                    # broadcast already exists but needs updating
                    if id in self.scheduled_broadcasts:
                        broadcast = self.scheduled_broadcasts[id]
                        broadcast.load_dict(r)
                    else:
                    # fully new broadcast
                        broadcast = self.rec_class(r, auto_schedule_recording=False, timezone=timezone)
                        self.scheduled_broadcasts[id] = broadcast
                    self._broadcast = broadcast
                    was_slot_updated = True
            else:
                # no broadcast passed
                self._broadcast = None
                if previous_broadcast and previous_broadcast not in others:
                    # stop stale / finished show and recordings
                    logger.info("Un-Scheduling... %i %s" % (previous_broadcast.get_unique_id(), previous_broadcast.__repr__()))
                    previous_broadcast.unschedule_and_stop_recording()
                    try:
                        del self.scheduled_broadcasts[previous_broadcast.get_unique_id()]
                    except KeyError:
                        pass
                    was_slot_updated = True

            if was_slot_updated and self._broadcast:
                # schedule if we have changes
                logger.info("Scheduling... %i %s" % (self._broadcast.get_unique_id(), self._broadcast.__repr__()))
                self._broadcast.schedule_recording()

            return was_slot_updated

    def __init__(self, airtime_api, recorder_instance):
        self._api = airtime_api
        AirtimeBroadcastRecording.recorder = recorder_instance

        # the API is not offering correct results on the previous show.
        # since we can not record past shows anyway we do not care.
        # self.previous = None
        self.current = AirtimeRecordingScheduler.BroadcastSlot()
        self.next = AirtimeRecordingScheduler.BroadcastSlot()

        self.update()
        self.job = None
        self.schedule_update()


    def update(self):
        logger.debug("Updating schedule from Airtime using API")
        r = self._api.get_live_info()

        self.airtime_timezone = pytz.timezone(r['timezone'])
        self.current.update(r['currentShow'], now=True, others=[self.next], timezone=self.airtime_timezone)
        self.next.update(r['nextShow'], others=[self.current], timezone=self.airtime_timezone)

    def schedule_update(self):
        if self.job:
            logger.warning("Periodic update running already with job %s" % self.job.id)
            return
        self.job = scheduler.add_job(self.update, 'interval', seconds=SECONDS_RELOAD)
        logger.debug("Runing perodic update on job %s" % self.job.id)

