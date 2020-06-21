from datetime import datetime, timedelta
from unittest import TestCase

import croniter

from dsari.croniter_hash import croniter_hash


class TestCroniterHash(TestCase):
    epoch = datetime(2020, 1, 1, 0, 0)
    hash_id = "hello"

    def test_hash_hourly(self):
        """Test manually-defined hourly"""
        obj = croniter_hash("H * * * *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 0, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 0, 10) + timedelta(hours=1)
        )

    def test_hash_daily(self):
        """Test manually-defined daily"""
        obj = croniter_hash("H H * * *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 11, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 11, 10) + timedelta(days=1)
        )

    def test_hash_weekly(self):
        """Test manually-defined weekly"""
        obj = croniter_hash("H H * * H", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 3, 11, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 3, 11, 10) + timedelta(weeks=1)
        )

    def test_hash_monthly(self):
        """Test manually-defined monthly"""
        obj = croniter_hash("H H H * *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 11, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 11, 10) + timedelta(days=31)
        )

    def test_hash_yearly(self):
        """Test manually-defined yearly"""
        obj = croniter_hash("H H H H *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 9, 1, 11, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 9, 1, 11, 10) + timedelta(days=365)
        )

    def test_hash_word_midnight(self):
        """Test built-in @midnight

        @midnight is actually up to 3 hours after midnight, not exactly midnight
        """
        obj = croniter_hash("@midnight", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 2, 10, 32))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 2, 10, 32) + timedelta(days=1)
        )

    def test_hash_word_hourly(self):
        """Test built-in @hourly"""
        obj = croniter_hash("@hourly", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 0, 10, 32))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 0, 10, 32) + timedelta(hours=1)
        )

    def test_hash_word_daily(self):
        """Test built-in @daily"""
        obj = croniter_hash("@daily", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 11, 10, 32))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 11, 10, 32) + timedelta(days=1)
        )

    def test_hash_word_weekly(self):
        """Test built-in @weekly"""
        obj = croniter_hash("@weekly", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 3, 11, 10, 32))
        self.assertEqual(
            obj.get_next(datetime),
            datetime(2020, 1, 3, 11, 10, 32) + timedelta(weeks=1),
        )

    def test_hash_word_monthly(self):
        """Test built-in @monthly"""
        obj = croniter_hash("@monthly", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 11, 10, 32))
        self.assertEqual(
            obj.get_next(datetime),
            datetime(2020, 1, 1, 11, 10, 32) + timedelta(days=31),
        )

    def test_hash_word_yearly(self):
        """Test built-in @yearly"""
        obj = croniter_hash("@yearly", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 9, 1, 11, 10, 32))
        self.assertEqual(
            obj.get_next(datetime),
            datetime(2020, 9, 1, 11, 10, 32) + timedelta(days=365),
        )

    def test_hash_word_annually(self):
        """Test built-in @annually

        @annually is the same as @yearly
        """
        obj_annually = croniter_hash("@annually", self.epoch, hash_id=self.hash_id)
        obj_yearly = croniter_hash("@yearly", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj_annually.get_next(datetime), obj_yearly.get_next(datetime))

    def test_hash_second(self):
        """Test seconds

        If a sixth field is provided, seconds are included in the datetime()
        """
        obj = croniter_hash("H H * * * H", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 11, 10, 32))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 11, 10, 32) + timedelta(days=1)
        )

    def test_hash_id_change(self):
        """Test a different hash_id returns different results given same definition and epoch"""
        obj = croniter_hash("H H * * *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 11, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 11, 10) + timedelta(days=1)
        )
        obj = croniter_hash("H H * * *", self.epoch, hash_id="different id")
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 0, 24))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 0, 24) + timedelta(days=1)
        )

    def test_hash_epoch_change(self):
        """Test a different epoch returns different results given same definition and hash_id"""
        obj = croniter_hash("H H * * *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 11, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 11, 10) + timedelta(days=1)
        )
        obj = croniter_hash(
            "H H * * *", datetime(2011, 11, 11, 11, 11), hash_id=self.hash_id
        )
        self.assertEqual(obj.get_next(datetime), datetime(2011, 11, 12, 11, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2011, 11, 12, 11, 10) + timedelta(days=1)
        )

    def test_hash_range(self):
        """Test a hashed range definition"""
        obj = croniter_hash("H H H(3-5) * *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 5, 11, 10))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 5, 11, 10) + timedelta(days=31)
        )

    def test_hash_id_bytes(self):
        """Test hash_id as a bytes object"""
        obj = croniter_hash("H H * * *", self.epoch, hash_id=b"\x01\x02\x03\x04")
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 14, 53))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 14, 53) + timedelta(days=1)
        )

    def test_hash_float(self):
        """Test result as a float object"""
        obj = croniter_hash("H H * * *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(float), 1577877000.0)
        self.assertEqual(obj.get_next(float), 1577877000.0 + (60 * 60 * 24))

    def test_random(self):
        """Test random definition"""
        obj = croniter_hash("R R * * *", self.epoch, hash_id=self.hash_id)
        result_1 = obj.get_next(datetime)
        self.assertGreaterEqual(result_1, datetime(2020, 1, 1, 0, 0))
        self.assertLessEqual(result_1, datetime(2020, 1, 1, 0, 0) + timedelta(days=1))
        result_2 = obj.get_next(datetime)
        self.assertGreaterEqual(result_2, datetime(2020, 1, 2, 0, 0))
        self.assertLessEqual(result_2, datetime(2020, 1, 2, 0, 0) + timedelta(days=1))

    def test_random_range(self):
        """Test random definition within a range"""
        obj = croniter_hash("R R R(10-20) * *", self.epoch, hash_id=self.hash_id)
        result_1 = obj.get_next(datetime)
        self.assertGreaterEqual(result_1, datetime(2020, 1, 10, 0, 0))
        self.assertLessEqual(result_1, datetime(2020, 1, 10, 0, 0) + timedelta(days=11))
        result_2 = obj.get_next(datetime)
        self.assertGreaterEqual(result_2, datetime(2020, 2, 10, 0, 0))
        self.assertLessEqual(result_2, datetime(2020, 2, 10, 0, 0) + timedelta(days=11))

    def test_random_float(self):
        """Test random definition, float result"""
        obj = croniter_hash("R R * * *", self.epoch, hash_id=self.hash_id)
        result_1 = obj.get_next(float)
        self.assertGreaterEqual(result_1, 1577836800.0)
        self.assertLessEqual(result_1, 1577836800.0 + (60 * 60 * 24))
        result_2 = obj.get_next(float)
        self.assertGreaterEqual(result_2, 1577923200.0)
        self.assertLessEqual(result_2, 1577923200.0 + (60 * 60 * 24))

    def test_cron(self):
        """Test standard croniter functionality"""
        obj = croniter_hash("35 6 * * *", self.epoch, hash_id=self.hash_id)
        self.assertEqual(obj.get_next(datetime), datetime(2020, 1, 1, 6, 35))
        self.assertEqual(
            obj.get_next(datetime), datetime(2020, 1, 1, 6, 35) + timedelta(days=1)
        )

    def test_invalid_definition(self):
        """Test an invalid defition raises CroniterNotAlphaError"""
        with self.assertRaises(croniter.CroniterNotAlphaError):
            croniter_hash("X X * * *", self.epoch, hash_id=self.hash_id)

    def test_invalid_get_next_type(self):
        """Test an invalid get_next type raises TypeError"""
        obj = croniter_hash("H H * * *", self.epoch, hash_id=self.hash_id)
        with self.assertRaises(TypeError):
            obj.get_next(str)

    def test_invalid_hash_id_type(self):
        """Test an invalid hash_id type raises TypeError"""
        with self.assertRaises(TypeError):
            croniter_hash("H H * * *", self.epoch, hash_id={1: 2})
