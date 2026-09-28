from collections import deque
from pathlib import Path
import json
import cv2


class EvidenceRecorder:
    """Bounded JPEG ring; short per-event clips, never full-session recording.

    AVI uses fixed cadence. Actual source times are burned into frames and
    written to a sidecar, including gaps. An early session stop is explicit.
    """
    def __init__(self, folder, config, callback):
        self.folder = Path(folder) / 'evidence'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.callback = callback
        self.ring = deque()
        self.pending = {}
        self.last_sample = -1e9
        self.size = (640, 360)

    def push(self, frame, timestamp):
        if not self.config.record_evidence or timestamp-self.last_sample < 1/self.config.evidence_fps - 1e-6:
            return
        self.last_sample = timestamp
        height, width = frame.shape[:2]
        scale = min(self.size[0]/width, self.size[1]/height)
        resized = cv2.resize(frame, (max(1,int(width*scale)), max(1,int(height*scale))))
        import numpy as np
        canvas = np.zeros((self.size[1], self.size[0], 3), dtype=np.uint8)
        canvas[:resized.shape[0], :resized.shape[1]] = resized
        cv2.putText(canvas, f'Source time {timestamp:.2f}s', (12, self.size[1]-15), cv2.FONT_HERSHEY_SIMPLEX, .5, (255,255,255), 1)
        ok, encoded = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return
        self.ring.append((timestamp, encoded))
        while self.ring and timestamp-self.ring[0][0] > self.config.pre_roll_seconds:
            self.ring.popleft()
        for event_id, pending in list(self.pending.items()):
            self._write(pending, timestamp, canvas)
            if timestamp >= pending['until']:
                self._finish(event_id, 'ready')

    def start(self, event):
        if not self.config.record_evidence:
            self.callback(event.id, None, 'disabled')
            return
        path = self.folder / f'{event.id}.avi'
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), self.config.evidence_fps, self.size)
        if not writer.isOpened():
            writer.release()
            self.callback(event.id, None, 'codec_error')
            return
        pending = {'writer': writer, 'path': path, 'until': event.detected_at+self.config.post_roll_seconds,
                   'times': [], 'next': None, 'event': event.to_dict()}
        self.pending[event.id] = pending
        for t, encoded in self.ring:
            if t >= event.detected_at-self.config.pre_roll_seconds:
                frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                if frame is not None:
                    self._write(pending, t, frame)
        self.callback(event.id, path, 'recording')

    def _write(self, pending, timestamp, frame):
        if pending['next'] is None:
            pending['next'] = timestamp
        # Cap fill across camera stalls; the sidecar records real source time.
        pending['next'] = max(pending['next'], timestamp-1.0)
        while pending['next'] <= timestamp + 1e-6:
            pending['writer'].write(frame)
            pending['times'].append(timestamp)
            pending['next'] += 1/self.config.evidence_fps

    def _finish(self, event_id, status):
        pending = self.pending.pop(event_id)
        pending['writer'].release()
        path = pending['path']
        if not path.exists() or path.stat().st_size < 1000 or not pending['times']:
            status = 'write_error'
        metadata = {'event': pending['event'], 'source_timestamps': pending['times'],
                    'status': status, 'playback_fps': self.config.evidence_fps}
        path.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        self.callback(event_id, path, status)

    def close(self):
        for event_id in list(self.pending):
            self._finish(event_id, 'partial_session_ended')
