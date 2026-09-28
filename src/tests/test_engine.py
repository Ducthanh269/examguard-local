from dataclasses import replace
import math
import random
import unittest

from examguard.config import Config
from examguard.engine import Engine, Observation


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(calibration_seconds=2, calibration_samples=10)
        self.engine = Engine(self.config)
        self.t = 0.0
        self.events = []

    def feed(self, seconds, fps=10, **kwargs):
        result = None
        for _ in range(round(seconds*fps)):
            self.t += 1/fps
            result = self.engine.step(Observation(self.t, **kwargs))
            self.events.extend(result.new_events)
        return result

    def calibrate(self):
        self.feed(2.5)
        self.assertTrue(self.engine.ready)

    def test_quiet_session_and_small_noise_no_alerts(self):
        self.calibrate()
        rng = random.Random(31)
        for _ in range(6000):
            self.t += .1
            r = self.engine.step(Observation(self.t, yaw=rng.gauss(0,2), pitch=rng.gauss(0,3),
                                             gaze_x=.5+rng.gauss(0,.02), gaze_y=.5+rng.gauss(0,.03)))
            self.assertEqual(r.new_events, [])

    def test_short_glance_does_not_alert(self):
        self.calibrate()
        self.feed(.8, yaw=40, gaze_x=.8)
        self.feed(8)
        self.assertFalse(self.events)
        self.assertLess(self.engine.long, .15)

    def test_sustained_supported_look_emits_once(self):
        self.calibrate()
        self.feed(20,yaw=30,gaze_x=.8)
        self.assertEqual([x.kind for x in self.events], ['look_away'])
        self.assertGreater(self.events[0].detected_at-self.events[0].start,4.9)

    def test_eye_only_does_not_alert(self):
        self.calibrate()
        self.feed(30,gaze_x=.9)
        self.assertFalse(self.events)

    def test_paper_allowed_downward_no_alert(self):
        self.calibrate()
        self.feed(30,pitch=35,gaze_y=.85)
        self.assertFalse(self.events)

    def test_paper_disabled_downward_alert(self):
        self.engine = Engine(replace(self.config,allow_paper=False))
        self.calibrate()
        self.feed(20,pitch=35,gaze_y=.85)
        self.assertEqual([e.kind for e in self.events],['look_away'])

    def test_bad_quality_cannot_trigger_behavior(self):
        self.calibrate()
        result = self.feed(30,quality=.1,yaw=50,gaze_x=.95)
        self.assertEqual([e.kind for e in self.events],['poor_quality'])
        self.assertEqual(result.status,'unavailable')

    def test_missing_face_is_separate_event(self):
        self.calibrate()
        self.feed(8,face_count=0,yaw=None,pitch=None,gaze_x=None,gaze_y=None)
        self.assertEqual([e.kind for e in self.events],['face_absent'])

    def test_two_faces_need_persistence(self):
        self.calibrate()
        self.feed(1,face_count=2)
        self.feed(3)
        self.assertFalse(self.events)
        self.feed(4,face_count=2)
        self.assertEqual([e.kind for e in self.events],['multiple_faces'])

    def test_cached_phone_detection_never_counts_as_new_hits(self):
        self.calibrate()
        self.feed(10,phone_score=.99,phone_timestamp=self.t,phone_track=1)
        self.assertFalse(self.events)

    def test_stable_phone_needs_distinct_samples(self):
        self.calibrate()
        for _ in range(60):
            self.t += .1
            r=self.engine.step(Observation(self.t,phone_score=.9,phone_timestamp=math.floor(self.t),phone_track=1))
            self.events.extend(r.new_events)
        self.assertEqual([e.kind for e in self.events],['phone'])

    def test_low_confidence_phone_no_alert(self):
        self.calibrate()
        for _ in range(80):
            self.t+=.1
            r=self.engine.step(Observation(self.t,phone_score=.5,phone_timestamp=math.floor(self.t)))
            self.assertFalse(r.new_events)

    def test_phone_track_switch_resets_confirmation(self):
        self.calibrate()
        for i in range(10):
            self.t+=1
            r=self.engine.step(Observation(self.t,phone_score=.99,phone_timestamp=self.t,phone_track=i))
            self.assertFalse(r.new_events)

    def test_future_phone_sample_rejected(self):
        self.calibrate()
        for _ in range(60):
            self.t+=.1
            r=self.engine.step(Observation(self.t,phone_score=.99,phone_timestamp=self.t+10))
            self.assertFalse(r.new_events)

    def test_stream_gap_does_not_manufacture_duration(self):
        self.calibrate()
        self.feed(1,face_count=2)
        self.t+=60
        r=self.engine.step(Observation(self.t,face_count=2))
        self.assertFalse(r.new_events)

    def test_calibration_requires_clean_duration(self):
        self.feed(30,quality=.1)
        self.assertFalse(self.engine.ready)
        self.feed(1)
        self.assertFalse(self.engine.ready)

    def test_nonfinite_features_are_unavailable(self):
        self.calibrate()
        r=self.feed(3,yaw=float('nan'))
        self.assertEqual(r.status,'unavailable')
        self.assertTrue(math.isfinite(r.risk))

    def test_nonmonotonic_time_rejected(self):
        self.engine.step(Observation(1))
        with self.assertRaises(ValueError):
            self.engine.step(Observation(1))

    def test_frame_rate_independent_event_timing(self):
        detected=[]
        for fps in (5,10,30):
            engine=Engine(self.config)
            for i in range(1,round(20*fps)):
                t=i/fps
                r=engine.step(Observation(t,yaw=30 if t>=4 else 0,gaze_x=.8 if t>=4 else .5))
                detected.extend(e.detected_at for e in r.new_events if e.kind=='look_away')
        self.assertEqual(len(detected),3)
        self.assertLess(max(detected)-min(detected),.5)

    def test_anchor_limits_slow_baseline_drift(self):
        self.calibrate()
        for i in range(4000):
            self.t+=.1
            self.engine.step(Observation(self.t,yaw=min(30,i*.01)))
        self.assertLessEqual(abs(self.engine.baseline['yaw']-self.engine.anchor['yaw']),5)

    def test_finished_events_have_end(self):
        self.calibrate()
        self.feed(4,face_count=2)
        closed=self.engine.finish()
        self.assertEqual(len(closed),1)
        self.assertIsNotNone(closed[0].end)

    def test_invalid_settings_rejected(self):
        for changes in ({'look_dwell_seconds':0},{'phone_confidence':2},{'phone_min_hits':1},{'min_quality':float('nan')}):
            with self.assertRaises(ValueError):
                Config(**changes)


if __name__=='__main__':
    unittest.main()
