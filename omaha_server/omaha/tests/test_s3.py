from django.test import TestCase, override_settings

import moto
import boto
import mock

from crash.factories import CrashFactoryWithFiles, SymbolsFactory
from feedback.factories import FeedbackFactory
from omaha.factories import VersionFactory
from sparkle.factories import SparkleVersionFactory

from crash.models import Crash, Symbols
from feedback.models import Feedback
from omaha.models import Version
from sparkle.models import SparkleVersion
from omaha_server.utils import storage_with_spaces_instance
from omaha.limitation import bulk_delete
from storages.backends.s3boto import S3BotoStorage


class BaseS3Test(object):
    model = None
    factory = None
    file_fields = None

    @moto.mock_s3
    def test_model_delete(self):
        conn = boto.connect_s3()
        conn.create_bucket('test')
        obj = self.factory()

        keys = conn.get_bucket('test').get_all_keys()
        keys = [key.name for key in keys]
        for field in self.file_fields:
            self.assertIn(getattr(obj, field).name, keys)

        obj.delete()
        keys = conn.get_bucket('test').get_all_keys()
        self.assertFalse(keys)

    @moto.mock_s3
    def test_model_update(self):
        conn = boto.connect_s3()
        conn.create_bucket('test')
        obj = self.factory()
        new_obj = self.factory()

        old_keys = conn.get_bucket('test').get_all_keys()
        old_keys = [key.name for key in old_keys]

        for field in self.file_fields:
            self.assertIn(getattr(obj, field).name, old_keys)
            setattr(obj, field, getattr(new_obj, field))
            obj.save()

        new_keys = conn.get_bucket('test').get_all_keys()
        self.assertFalse(set(old_keys) & set(new_keys))

    @moto.mock_s3
    def test_bulk_delete(self):
        conn = boto.connect_s3()
        conn.create_bucket('test')
        self.factory.create_batch(10)
        qs = self.model.objects.all()
        self.assertEqual(qs.count(), 10)
        keys = conn.get_bucket('test').get_all_keys()
        self.assertEqual(len(keys), len(self.file_fields) * 10)
        with mock.patch('boto.__init__') as my_mock:
            my_mock.connect_s3.return_value = conn
            try:                                    # When we try to delete nonexistent key from s3 in pre_delete signal
                bulk_delete(self.model, qs)         # original boto doesn't raise S3ResponseError: 404 Not Found
            except boto.exception.S3ResponseError:  # but mocked boto does
                pass

        keys = conn.get_bucket('test').get_all_keys()
        self.assertFalse(keys)


@override_settings(DEFAULT_FILE_STORAGE='storages.backends.s3boto.S3BotoStorage')
class CrashS3Test(BaseS3Test, TestCase):
    def setUp(self):
        self._file_field = self.model._meta.get_field_by_name('upload_file_minidump')[0]
        self._archive_field = self.model._meta.get_field_by_name('archive')[0]
        self._default_storage = self._file_field.storage
        test_storage = S3BotoStorage()
        self._file_field.storage = test_storage
        self._archive_field.storage = test_storage

    def tearDown(self):
        self._file_field.storage = self._default_storage
        self._archive_field.storage = self._default_storage

    model = Crash
    factory = CrashFactoryWithFiles
    file_fields = ['archive', 'upload_file_minidump']


@override_settings(DEFAULT_FILE_STORAGE='storages.backends.s3boto.S3BotoStorage')
class FeedbackS3Test(BaseS3Test, TestCase):
    model = Feedback
    factory = FeedbackFactory
    file_fields = ['screenshot', 'blackbox', 'system_logs', 'attached_file']

@override_settings(DEFAULT_FILE_STORAGE='storages.backends.s3boto.S3BotoStorage')
class SymbolsS3Test(BaseS3Test, TestCase):
    model = Symbols
    factory = SymbolsFactory
    file_fields = ['file']

    def setUp(self):
        storage_with_spaces_instance._setup()



@override_settings(DEFAULT_FILE_STORAGE='storages.backends.s3boto.S3BotoStorage')
class OmahaVersionS3Test(BaseS3Test, TestCase):
    model = Version
    factory = VersionFactory
    file_fields = ['file']


@override_settings(DEFAULT_FILE_STORAGE='storages.backends.s3boto.S3BotoStorage')
class SparkleVersionS3Test(BaseS3Test, TestCase):
    model = SparkleVersion
    factory = SparkleVersionFactory
    file_fields = ['file']
