from pathlib import Path
import tempfile
import unittest

from examguard.config import Config
from examguard.engine import Event
from examguard.storage import Store


class StorageTests(unittest.TestCase):
    def test_session_event_review_export_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            sid, path=store.create_session('test.avi',Config())
            event=Event('phone',1,4,'test',90)
            store.save_event(sid,event)
            store.review(event.id,'false_positive','=SUM(1,2)')
            event.end=8
            store.save_event(sid,event)
            store.finish_session(sid,30)
            rows=store.events(sid)
            self.assertEqual(rows[0]['review'],'false_positive')
            self.assertEqual(rows[0]['end'],8)
            self.assertTrue((path/'events.json').exists())
            self.assertIn("'=SUM",(path/'events.csv').read_text(encoding='utf-8-sig'))
            self.assertEqual(store.sessions()[0]['status'],'finished')

    def test_bad_review_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            with self.assertRaises(ValueError):
                store.review('absent','confirmed')
