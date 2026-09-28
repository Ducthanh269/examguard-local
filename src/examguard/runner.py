from dataclasses import asdict
from pathlib import Path
import importlib.metadata
import json
import math
import queue
import threading
import time
import traceback

from .config import Config
from .engine import Engine, Observation
from .storage import Store, write_observation


class Runner(threading.Thread):
    def __init__(self, source, config, root, output_queue=None, demo=False):
        super().__init__(daemon=True)
        self.source = source
        self.config = config
        self.root = Path(root)
        self.messages = output_queue or queue.Queue(maxsize=3)
        self.stop_requested = threading.Event()
        self.demo = demo
        self.sid = None
        self.failure = None
        self.finished = False
        self.last_heartbeat = time.monotonic()

    def publish(self, message):
        while True:
            try:
                self.messages.put_nowait(message)
                return
            except queue.Full:
                try:
                    self.messages.get_nowait()
                except queue.Empty:
                    pass

    def run(self):
        if self.demo:
            self._demo()
            return
        cap = faces = recorder = log = None
        engine = Engine(self.config)
        store = Store(self.root / 'data')
        try:
            import cv2
            from .vision import FaceAnalyzer, PhoneDetector
            from .evidence import EvidenceRecorder
            cv2.setNumThreads(2)
            # PyInstaller puts bundled data under _internal\ next to the executable.
            model_dir = self.root / ('_internal' if (self.root / '_internal').is_dir() else '') / 'models'
            for name in ('face_landmarker.task', 'yolox.onnx'):
                if not (model_dir / name).exists():
                    raise RuntimeError(f'Thiếu mô hình {name}. Chạy CÀI ĐẶT trước khi bắt đầu.')
            self.publish({'type': 'loading', 'message': 'Đang nạp mô hình trên CPU…'})
            faces = FaceAnalyzer(model_dir / 'face_landmarker.task')
            phones = PhoneDetector(model_dir / 'yolox.onnx')
            camera = isinstance(self.source, int)
            cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW if camera else cv2.CAP_ANY)
            if not cap.isOpened():
                raise RuntimeError('Không mở được webcam/video. Kiểm tra quyền camera hoặc đổi số camera.')
            if camera:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            if not math.isfinite(source_fps) or source_fps <= 0:
                if not camera:
                    raise RuntimeError('Video không có FPS hợp lệ; chuyển sang MP4/AVI có timestamp trước khi phân tích.')
                source_fps = 30.0
            manifest = json.loads((model_dir / 'manifest.json').read_text(encoding='utf-8')) if (model_dir / 'manifest.json').exists() else {}
            self.sid, folder = store.create_session(self.source, self.config, manifest)
            versions = {name: importlib.metadata.version(name) for name in ('numpy', 'opencv-contrib-python', 'mediapipe', 'Pillow')}
            (folder / 'environment.json').write_text(json.dumps(versions, indent=2), encoding='utf-8')
            recorder = EvidenceRecorder(folder, self.config, store.set_clip)
            log = (folder / 'observations.jsonl').open('w', encoding='utf-8')
            started = time.monotonic()
            last_processed, last_object = -1e9, -1e9
            frame_index = 0
            phone_score, phone_ts, phone_track, phone_boxes = None, None, 0, []
            failures = 0
            while not self.stop_requested.is_set():
                ok, frame = cap.read()
                if not ok:
                    if not camera:
                        break
                    failures += 1
                    self.publish({'type':'loading', 'message':'Mất hình camera; đang thử đọc lại…'})
                    if failures >= 10:
                        raise RuntimeError('Camera đã ngừng trả hình. Phiên được dừng, dữ liệu trước đó đã lưu.')
                    time.sleep(.2)
                    continue
                failures = 0
                t = time.monotonic()-started if camera else frame_index/source_fps
                frame_index += 1
                if t-last_processed < 1/self.config.inference_fps - 1e-8:
                    if camera:
                        time.sleep(.005)
                    continue
                last_processed = t
                process_start = time.monotonic()
                if frame.shape[1] > 960:
                    frame = cv2.resize(frame, (960, round(frame.shape[0]*960/frame.shape[1])))
                obs, face_boxes = faces.analyze(frame, t)
                if t-last_object >= self.config.object_interval:
                    phone_boxes, phone_score, phone_track = phones.detect(frame)
                    phone_ts, last_object = t, t
                obs.phone_score, obs.phone_timestamp, obs.phone_track = phone_score, phone_ts, phone_track
                result = engine.step(obs)
                write_observation(log, obs, result)
                recorder.push(frame, t)
                for event in result.new_events:
                    store.save_event(self.sid, event)
                    recorder.start(event)
                for event in result.closed_events:
                    store.save_event(self.sid, event)
                elapsed = time.monotonic()-process_start
                display = frame.copy()
                for box in face_boxes:
                    x1,y1,x2,y2 = [int(v) for v in box]
                    cv2.rectangle(display, (x1,y1), (x2,y2), (155,200,70), 2)
                if phone_ts is not None and t-phone_ts < self.config.phone_sample_gap:
                    for detected in phone_boxes:
                        x1,y1,x2,y2 = [int(v) for v in detected['box']]
                        cv2.rectangle(display,(x1,y1),(x2,y2),(60,180,245),2)
                        cv2.putText(display, f"Phone {detected['score']:.2f}", (x1,max(20,y1-8)), cv2.FONT_HERSHEY_SIMPLEX,.55,(60,180,245),2)
                self.last_heartbeat = time.monotonic()
                self.publish({'type':'frame', 'frame':display, 'result':result,
                              'observation':obs, 'sid':self.sid, 'latency_ms':elapsed*1000,
                              'source_fps':source_fps, 'demo':False})
                log.flush()
            for event in engine.finish():
                store.save_event(self.sid, event)
        except Exception as exc:
            self.failure = str(exc)
            self.publish({'type':'error', 'message':str(exc)})
            error_path = self.root / 'data' / 'last_error.txt'
            error_path.parent.mkdir(exist_ok=True)
            error_path.write_text(traceback.format_exc(), encoding='utf-8')
        finally:
            if recorder:
                recorder.close()
            if log:
                log.close()
            if cap:
                cap.release()
            if faces:
                faces.close()
            if self.sid:
                for event in engine.finish():
                    store.save_event(self.sid, event)
                store.finish_session(self.sid, engine.last_t or 0, 'error' if self.failure else 'finished')
            self.finished = True
            self.publish({'type':'finished', 'sid':self.sid, 'error':self.failure})

    def _demo(self):
        """Explicitly synthetic interface tour. Never written as real evidence."""
        import numpy as np
        import cv2
        from dataclasses import replace
        engine = Engine(replace(self.config, calibration_seconds=3, calibration_samples=15))
        index = 0
        try:
            while not self.stop_requested.is_set():
                t = index*.1
                phone = 12 <= t % 40 < 18
                away = 22 <= t % 40 < 34
                obs = Observation(t, yaw=30 if away else 0,
                                  gaze_x=.75 if away else .5,
                                  phone_score=.94 if phone else 0,
                                  phone_timestamp=math.floor(t), phone_track=1)
                result = engine.step(obs)
                frame = np.full((450,800,3), (37,27,17), dtype=np.uint8)
                cv2.putText(frame,'DEMO - SYNTHETIC SIGNALS',(75,90),cv2.FONT_HERSHEY_SIMPLEX,1,(180,220,220),2)
                cv2.circle(frame,(400,220),70,(110,140,160),2)
                cv2.line(frame,(400,290),(400,370),(110,140,160),3)
                if phone:
                    cv2.rectangle(frame,(530,230),(585,325),(50,190,250),3)
                if away:
                    cv2.arrowedLine(frame,(400,210),(510,210),(50,190,250),3)
                cv2.putText(frame,f't = {t:.1f}s | risk = {result.risk:.0f}',(170,415),cv2.FONT_HERSHEY_SIMPLEX,.7,(200,220,220),1)
                self.last_heartbeat=time.monotonic()
                self.publish({'type':'frame','frame':frame,'result':result,'observation':obs,
                              'sid':None,'latency_ms':0,'source_fps':10,'demo':True})
                index += 1
                self.stop_requested.wait(.1)
        except Exception as exc:
            self.failure=str(exc)
        finally:
            self.finished=True
            self.publish({'type':'finished','sid':None,'error':self.failure})
