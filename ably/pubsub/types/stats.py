import logging
from datetime import datetime

log = logging.getLogger(__name__)


class Stats:

    def __init__(self, entries=None, unit=None, interval_id=None, in_progress=None, app_id=None, schema=None):
        self.interval_id = interval_id or ''
        self.entries = entries
        self.unit = unit
        self.interval_time = interval_from_interval_id(self.interval_id)
        self.in_progress = in_progress
        self.app_id = app_id
        self.schema = schema

    @classmethod
    def from_dict(cls, stats_dict):
        stats_dict = stats_dict or {}

        kwargs = {
            "entries": stats_dict.get("entries"),
            "unit": stats_dict.get("unit"),
            "interval_id": stats_dict.get("intervalId"),
            "in_progress": stats_dict.get("inProgress"),
            "app_id": stats_dict.get("appId"),
            "schema": stats_dict.get("schema"),
        }

        return cls(**kwargs)

    @classmethod
    def from_array(cls, stats_array):
        return [cls.from_dict(d) for d in stats_array]

    @staticmethod
    def to_interval_id(date_time, granularity):
        return date_time.strftime(INTERVALS_FMT[granularity])


def stats_response_processor(response):
    stats_array = response.to_native()
    return Stats.from_array(stats_array)


INTERVALS_FMT = {
    'minute': '%Y-%m-%d:%H:%M',
    'hour': '%Y-%m-%d:%H',
    'day': '%Y-%m-%d',
    'month': '%Y-%m',
}


def granularity_from_interval_id(interval_id):
    for key, value in INTERVALS_FMT.items():
        try:
            datetime.strptime(interval_id, value)
            return key
        except ValueError:
            pass
    raise ValueError("Unsupported intervalId")


def interval_from_interval_id(interval_id):
    granularity = granularity_from_interval_id(interval_id)
    return datetime.strptime(interval_id, INTERVALS_FMT[granularity])
