import datetime
import unittest

from dsari import utils


class TestUtils(unittest.TestCase):
    def test_seconds_to_td(self):
        self.assertEqual(
            utils.seconds_to_td(123), datetime.timedelta(minutes=2, seconds=3)
        )

    def test_td_to_seconds(self):
        self.assertEqual(
            utils.td_to_seconds(datetime.timedelta(minutes=2, seconds=3)), 123
        )

    def test_epoch_to_dt(self):
        now = datetime.datetime.now()
        self.assertEqual(utils.epoch_to_dt(now.timestamp()), now)

    def test_dt_to_epoch(self):
        now = datetime.datetime.now()
        self.assertEqual(utils.dt_to_epoch(now), now.timestamp())
