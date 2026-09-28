"""MediaPipe face geometry + CPU OpenCV YOLOX inference.

No age, identity, emotion, or demographic classification is performed.
Gaze is an approximate iris position, not a calibrated screen coordinate.
"""
import math
from pathlib import Path
import cv2
import numpy as np
from .engine import Observation


def kabsch_residual(points, reference):
    """Translation/scale invariant shape residual; rotation is kept separately."""
    p = np.asarray(points, dtype=float)
    q = np.asarray(reference, dtype=float)
    if p.shape != q.shape or p.ndim != 2 or p.shape[1] != 3:
        raise ValueError('Expected matching N x 3 point arrays')
    if not np.isfinite(p).all() or not np.isfinite(q).all():
        raise ValueError('Nonfinite landmarks')
    p = p - p.mean(axis=0)
    q = q - q.mean(axis=0)
    pn, qn = np.linalg.norm(p), np.linalg.norm(q)
    if min(pn, qn) < 1e-8:
        return None
    p, q = p / pn, q / qn
    u, _, vt = np.linalg.svd(p.T @ q)
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(u @ vt)
    rotation = u @ correction @ vt
    return float(np.sqrt(np.mean((p @ rotation - q) ** 2)))


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2-x1) * max(0, y2-y1)
    area_a = max(0, a[2]-a[0]) * max(0, a[3]-a[1])
    area_b = max(0, b[2]-b[0]) * max(0, b[3]-b[1])
    return intersection / max(1e-9, area_a + area_b - intersection)


class PhoneDetector:
    """YOLOX-S export uses RGB 0..255 and top-left letterbox, no /255."""
    def __init__(self, path, threshold=0.45):
        self.net = cv2.dnn.readNetFromONNX(np.frombuffer(Path(path).read_bytes(), dtype=np.uint8))
        self.threshold = threshold
        self.grid = np.concatenate([np.array([(x, y) for y in range(640//s)
                                              for x in range(640//s)], dtype=np.float32)
                                    for s in (8, 16, 32)])
        self.stride = np.concatenate([np.full((640//s)**2, s, dtype=np.float32)
                                      for s in (8, 16, 32)])[:, None]
        self.previous_box = None
        self.track_id = 0

    def detect(self, frame):
        h, w = frame.shape[:2]
        scale = min(640/w, 640/h)
        canvas = np.full((640, 640, 3), 114, dtype=np.float32)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (max(1, int(w*scale)), max(1, int(h*scale))))
        canvas[:resized.shape[0], :resized.shape[1]] = resized
        self.net.setInput(np.ascontiguousarray(canvas.transpose(2, 0, 1)[None]))
        raw = self.net.forward()[0]
        if raw.shape != (8400, 85):
            raise RuntimeError(f'Unsupported YOLOX output: {raw.shape}')
        probabilities = raw[:, 4, None] * raw[:, 5:]
        classes = probabilities.argmax(axis=1)
        # COCO class 67 = cell phone. Ignore detections whose best class is different.
        rows = np.where((classes == 67) & (probabilities[:, 67] >= self.threshold))[0]
        boxes, scores = [], []
        for index in rows:
            center = (raw[index, :2] + self.grid[index]) * self.stride[index]
            extent = np.exp(np.clip(raw[index, 2:4], -15, 15)) * self.stride[index]
            x, y = (center - extent/2) / scale
            bw, bh = extent / scale
            x1, y1 = float(np.clip(x, 0, w)), float(np.clip(y, 0, h))
            x2, y2 = float(np.clip(x+bw, 0, w)), float(np.clip(y+bh, 0, h))
            if x2-x1 < 8 or y2-y1 < 8:
                continue
            boxes.append([x1, y1, x2-x1, y2-y1])
            scores.append(float(probabilities[index, 67]))
        keep = cv2.dnn.NMSBoxes(boxes, scores, self.threshold, 0.45)
        detections = []
        for index in np.asarray(keep).reshape(-1):
            x, y, bw, bh = boxes[index]
            detections.append({'box': [x, y, x+bw, y+bh], 'score': scores[index]})
        best = max(detections, key=lambda x: x['score'], default=None)
        if best:
            if self.previous_box is None or iou(self.previous_box, best['box']) < 0.12:
                self.track_id += 1
            self.previous_box = best['box']
        else:
            self.previous_box = None
        return detections, (best['score'] if best else 0.0), self.track_id


class FaceAnalyzer:
    def __init__(self, model_path):
        import mediapipe as mp
        self.mp = mp
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=Path(model_path).read_bytes()),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=3, min_face_detection_confidence=0.65,
            min_face_presence_confidence=0.65, min_tracking_confidence=0.65)
        self.detector = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        self.reference = None
        self.last_ms = -1

    def close(self):
        self.detector.close()

    def analyze(self, frame, timestamp):
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        frame_quality = 1.0 if 30 < brightness < 235 else 0.25
        quality_reason = '' if frame_quality == 1 else 'Ảnh quá tối hoặc quá sáng'
        rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        ms = max(self.last_ms + 1, int(timestamp * 1000))
        self.last_ms = ms
        result = self.detector.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ms)
        faces = []
        for landmarks in result.face_landmarks:
            points = np.array([(p.x*w, p.y*h, p.z*w) for p in landmarks])
            if not np.isfinite(points).all():
                continue
            lo, hi = points[:, :2].min(axis=0), points[:, :2].max(axis=0)
            if hi[0]-lo[0] >= max(45, w*0.07) and hi[1]-lo[1] >= max(45, h*0.08):
                faces.append((points, [float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])]))
        obs = Observation(timestamp, quality=frame_quality, face_count=len(faces),
                          yaw=None, pitch=None, gaze_x=None, gaze_y=None,
                          quality_reason=quality_reason)
        boxes = [box for _, box in faces]
        if len(faces) != 1:
            return obs, boxes
        points, box = faces[0]
        x1, y1, x2, y2 = [int(v) for v in box]
        roi = gray[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
        blur = float(cv2.Laplacian(roi, cv2.CV_64F).var()) if roi.size else 0
        if blur < 18 or x2-x1 < 85:
            obs.quality = min(obs.quality, 0.35)
            obs.quality_reason = 'Khuôn mặt nhỏ hoặc ảnh mờ; đưa camera gần hơn'
        image_points = points[[1, 152, 33, 263, 61, 291], :2].astype(np.float64)
        geometry = np.array([(0,0,0), (0,330,-65), (-225,-170,-135),
                             (225,-170,-135), (-150,150,-125), (150,150,-125)], dtype=np.float64)
        camera = np.array([[w,0,w/2], [0,w,h/2], [0,0,1]], dtype=np.float64)
        solved, rvec, tvec = cv2.solvePnP(geometry, image_points, camera, np.zeros(4), flags=cv2.SOLVEPNP_ITERATIVE)
        if solved:
            rotation, _ = cv2.Rodrigues(rvec)
            pitch, yaw, _ = cv2.RQDecomp3x3(rotation)[0]
            projected, _ = cv2.projectPoints(geometry, rvec, tvec, camera, np.zeros(4))
            error = np.linalg.norm(projected.reshape(-1,2)-image_points, axis=1).mean() / max(1, x2-x1)
            if error < 0.16 and abs(yaw) < 85 and abs(pitch) < 85:
                obs.yaw, obs.pitch = float(yaw), float(pitch)
        def eye(left, right, top, bottom, iris):
            p, q = points[left,:2], points[right,:2]
            axis = q-p
            length = np.linalg.norm(axis)
            if length < 5:
                return None
            direction = axis/length
            if direction[0] < 0:
                p, q, direction = q, p, -direction
            normal = np.array([-direction[1], direction[0]])
            center = points[iris,:2].mean(axis=0)
            ratio_x = float(np.dot(center-p, direction)/length)
            upper, lower = points[top,:2], points[bottom,:2]
            opening = abs(float(np.dot(lower-upper, normal)))
            ratio_y = float(np.dot(center-upper, normal)/max(2, opening))
            return ratio_x, ratio_y, opening/length
        eyes = [eye(33,133,159,145,[468,469,470,471,472]),
                eye(362,263,386,374,[473,474,475,476,477])]
        if all(e is not None for e in eyes):
            obs.gaze_x = float(np.mean([e[0] for e in eyes]))
            obs.gaze_y = float(np.mean([e[1] for e in eyes]))
            obs.eyes_open = min(e[2] for e in eyes) > 0.12
            if not 0 <= obs.gaze_x <= 1 or not -0.5 <= obs.gaze_y <= 1.5:
                obs.gaze_x = obs.gaze_y = None
        shape = points[[1, 33, 263, 61, 291, 152, 168]]
        if self.reference is None and obs.quality >= .6 and obs.yaw is not None:
            self.reference = shape.copy()
        if self.reference is not None:
            obs.shape_residual = kabsch_residual(shape, self.reference)
        return obs, boxes
