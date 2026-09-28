"""Time-based conservative decision engine. No camera / model dependencies.

Scores are risk indicators, NOT probabilities or disciplinary decisions.
Durations accumulate only over observed contiguous measurements.
"""
from dataclasses import dataclass, field, asdict
from collections import deque
import math
import statistics
import uuid

from .config import Config


LABELS = {
    'phone': 'Điện thoại xuất hiện',
    'multiple_faces': 'Có người thứ hai',
    'look_away': 'Nhìn lệch kéo dài',
    'face_absent': 'Không thấy khuôn mặt',
    'poor_quality': 'Hình ảnh không đủ rõ',
}


@dataclass
class Observation:
    timestamp: float
    quality: float = 1.0
    face_count: int = 1
    yaw: float | None = 0.0
    pitch: float | None = 0.0
    gaze_x: float | None = 0.5
    gaze_y: float | None = 0.5
    eyes_open: bool = True
    phone_score: float | None = None
    phone_timestamp: float | None = None
    phone_track: int = 0
    pose_shift: float | None = None
    shape_residual: float | None = None
    quality_reason: str = ''


@dataclass
class Event:
    kind: str
    start: float
    detected_at: float
    reason: str
    peak_score: float = 0.0
    end: float | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self):
        return asdict(self)


@dataclass
class Result:
    timestamp: float
    status: str
    risk: float
    calibration: float
    quality: float
    message: str
    active: list[str]
    new_events: list[Event]
    closed_events: list[Event]
    diagnostics: dict


class Sustained:
    def __init__(self):
        self.start = None
        self.last = None
        self.hits = 0
        self.clear_since = None
        self.event = None

    def break_run(self):
        self.start = self.last = None
        self.hits = 0


def clip(x, lo=0.0, hi=1.0):
    return min(hi, max(lo, x))


def robust_stats(values, floor):
    median = statistics.median(values)
    mad = statistics.median(abs(x - median) for x in values)
    return median, max(floor, 1.4826 * mad)


class Engine:
    FLOORS = {'yaw': 4.0, 'pitch': 5.0, 'gaze_x': 0.04, 'gaze_y': 0.06}
    DRIFT_LIMIT = {'yaw': 5.0, 'pitch': 6.0, 'gaze_x': 0.05, 'gaze_y': 0.06}

    def __init__(self, config=None):
        self.config = config or Config()
        self.last_t = None
        self.calibration_time = 0.0
        self.calibration_data = deque(maxlen=max(3000, self.config.calibration_samples * 3))
        self.baseline = {}
        self.anchor = {}
        self.scales = {}
        self.short = self.long = 0.0
        self.quiet_scores = deque(maxlen=600)
        self.quiet_sample_t = -math.inf
        self.trackers = {kind: Sustained() for kind in LABELS}
        self.last_phone_timestamp = -math.inf
        self.phone_track = None
        self.previous_calibration_valid = False

    @property
    def ready(self):
        return bool(self.baseline)

    def _close(self, tracker, timestamp, closed):
        if tracker.event:
            tracker.event.end = timestamp
            closed.append(tracker.event)
            tracker.event = None

    def _event_step(self, kind, condition, t, dwell, score, reason, new, closed,
                    max_gap=None, min_hits=2):
        tracker = self.trackers[kind]
        gap = max_gap or self.config.max_gap_seconds
        if tracker.last is not None and t - tracker.last > gap:
            self._close(tracker, tracker.last, closed)
            tracker.break_run()
            tracker.clear_since = None
        if condition:
            tracker.clear_since = None
            if tracker.start is None:
                tracker.start = t
            tracker.last = t
            tracker.hits += 1
            if tracker.event:
                tracker.event.peak_score = max(tracker.event.peak_score, score)
            elif t - tracker.start >= dwell - 1e-8 and tracker.hits >= min_hits:
                tracker.event = Event(kind, tracker.start, t, reason, score)
                new.append(tracker.event)
        else:
            tracker.break_run()
            if tracker.event:
                if tracker.clear_since is None:
                    tracker.clear_since = t
                if t - tracker.clear_since >= self.config.exit_dwell_seconds - 1e-8:
                    self._close(tracker, tracker.clear_since, closed)
                    tracker.clear_since = None

    def finish(self, timestamp=None):
        closed = []
        for tracker in self.trackers.values():
            self._close(tracker, self.last_t if timestamp is None else timestamp, closed)
            tracker.break_run()
        return closed

    def step(self, obs: Observation) -> Result:
        t = obs.timestamp
        if not math.isfinite(t) or t < 0:
            raise ValueError('timestamp must be finite and nonnegative')
        if self.last_t is not None and t <= self.last_t:
            raise ValueError('timestamps must be strictly increasing')
        cfg = self.config
        dt_raw = 0 if self.last_t is None else t - self.last_t
        new, closed = [], []
        discontinuity = dt_raw > cfg.max_gap_seconds
        if discontinuity:
            for tracker in self.trackers.values():
                self._close(tracker, self.last_t, closed)
                tracker.break_run()
                tracker.clear_since = None
            self.short = 0.0
            self.previous_calibration_valid = False
        dt = min(dt_raw, 0.5) if not discontinuity else 0.0
        self.long *= math.exp(-math.log(2) * dt_raw / cfg.long_half_life)
        self.last_t = t
        quality = clip(obs.quality) if math.isfinite(obs.quality) else 0.0
        frame_ok = quality >= cfg.min_quality
        valid = frame_ok and obs.face_count == 1 and all(
            getattr(obs, k) is not None and math.isfinite(getattr(obs, k))
            for k in self.FLOORS)
        # Objects use independent, NEW inference samples. Repeated cached results
        # must never manufacture persistence, even if the camera runs at 60 FPS.
        phone_current = False
        pts = obs.phone_timestamp
        if pts is not None and math.isfinite(pts) and pts > self.last_phone_timestamp:
            if 0 <= t - pts <= cfg.phone_sample_gap:
                self.last_phone_timestamp = pts
                phone_current = (frame_ok and obs.phone_score is not None
                                 and math.isfinite(obs.phone_score)
                                 and obs.phone_score >= cfg.phone_confidence)
                if phone_current and self.phone_track != obs.phone_track:
                    tracker = self.trackers['phone']
                    self._close(tracker, tracker.last or pts, closed)
                    tracker.break_run()
                self.phone_track = obs.phone_track
                self._event_step('phone', phone_current, pts, cfg.phone_dwell_seconds,
                                 100 * (obs.phone_score or 0),
                                 'Điện thoại được nhận diện ổn định qua nhiều lần quan sát; cần xem clip.',
                                 new, closed, cfg.phone_sample_gap, cfg.phone_min_hits)
        if t - self.last_phone_timestamp > cfg.phone_sample_gap:
            tracker = self.trackers['phone']
            self._close(tracker, tracker.last or t, closed)
            tracker.break_run()
        phone_pending = self.trackers['phone'].start is not None or self.trackers['phone'].event is not None
        self._event_step('multiple_faces', frame_ok and obs.face_count >= 2, t,
                         cfg.face_dwell_seconds, 80, 'Nhiều khuôn mặt xuất hiện liên tục; chưa kết luận gian lận.', new, closed)
        self._event_step('poor_quality', not frame_ok, t, cfg.quality_dwell_seconds, 0,
                         obs.quality_reason or 'Không đủ chất lượng để đánh giá hành vi.', new, closed)
        self._event_step('face_absent', frame_ok and obs.face_count == 0, t,
                         cfg.absent_dwell_seconds, 0, 'Không thấy khuôn mặt trong vùng camera.', new, closed)
        calibration_valid = valid and obs.eyes_open and not phone_pending
        if not self.ready:
            if calibration_valid:
                self.calibration_data.append({k: getattr(obs, k) for k in self.FLOORS})
                if self.previous_calibration_valid:
                    self.calibration_time += dt
            self.previous_calibration_valid = calibration_valid
            if (self.calibration_time >= cfg.calibration_seconds
                    and len(self.calibration_data) >= cfg.calibration_samples):
                stats = {k: robust_stats([x[k] for x in self.calibration_data], floor)
                         for k, floor in self.FLOORS.items()}
                if stats['yaw'][1] > 12 or stats['gaze_x'][1] > 0.15:
                    self.calibration_data.clear()
                    self.calibration_time = 0
                    self.previous_calibration_valid = False
                else:
                    self.baseline = {k: v[0] for k, v in stats.items()}
                    self.anchor = self.baseline.copy()
                    self.scales = {k: v[1] for k, v in stats.items()}
                    self.calibration_data.clear()
        risk = 0.0
        diagnostics = {'short': self.short, 'long': self.long, 'baseline': self.baseline.copy()}
        condition = False
        dwell = cfg.look_dwell_seconds
        if self.ready and valid:
            delta = {k: getattr(obs, k) - self.baseline[k] for k in self.FLOORS}
            z = {k: abs(delta[k]) / self.scales[k] for k in self.FLOORS}
            # Require independent geometric support for moderate horizontal deviation.
            head = abs(delta['yaw']) > max(18.0, 3.0 * self.scales['yaw'])
            eye = obs.eyes_open and abs(delta['gaze_x']) > max(0.12, 3.0 * self.scales['gaze_x'])
            extreme_head = abs(delta['yaw']) > max(35.0, 4.0 * self.scales['yaw'])
            vertical = (not cfg.allow_paper and obs.eyes_open
                        and abs(delta['pitch']) > max(22.0, 3 * self.scales['pitch'])
                        and abs(delta['gaze_y']) > max(0.15, 3 * self.scales['gaze_y']))
            supported = (head and eye) or extreme_head or vertical
            strength = max(z['yaw'], z['gaze_x'] if obs.eyes_open else 0)
            if vertical:
                strength = max(strength, z['pitch'], z['gaze_y'])
            instantaneous = 1 / (1 + math.exp(-clip(strength - 3, -30, 30))) if supported else 0.0
            a = 1 - math.exp(-math.log(2) * dt / cfg.short_half_life)
            target = clip(max(0.0, instantaneous - 0.30) ** 2 / 0.49)
            self.short += a * (target - self.short)
            if supported and self.short >= cfg.short_confirm:
                self.long = clip(self.long + (1 - math.exp(-dt / 8)) * self.short)
            risk = 100 * clip(0.15 * instantaneous + 0.55 * instantaneous * self.short + 0.30 * self.long)
            if len(self.quiet_scores) >= 20:
                center, spread = robust_stats(self.quiet_scores, 1.0)
                threshold = clip(center + 3.2 * spread, 35, 60)
            else:
                threshold = 35.0
            condition = supported and self.short >= cfg.short_confirm and risk >= threshold
            dwell = cfg.strong_head_dwell_seconds if extreme_head and not eye else cfg.look_dwell_seconds
            # Only quiet, trusted samples adapt, with a permanent anchor limit.
            if not supported and not phone_pending and not any(x.event for x in self.trackers.values()) and max(z.values()) < 2:
                alpha = 1 - math.exp(-dt / cfg.baseline_tau)
                for k in self.FLOORS:
                    self.baseline[k] = clip(self.baseline[k] + alpha * delta[k],
                                            self.anchor[k] - self.DRIFT_LIMIT[k],
                                            self.anchor[k] + self.DRIFT_LIMIT[k])
                if t - self.quiet_sample_t >= 1:
                    self.quiet_scores.append(risk)
                    self.quiet_sample_t = t
            diagnostics.update(z=z, delta=delta, threshold=threshold, supported=supported,
                               short=self.short, long=self.long)
        else:
            self.short *= math.exp(-math.log(2) * dt_raw / cfg.short_half_life)
        self._event_step('look_away', condition, t, dwell, risk,
                         'Đầu và mắt lệch kéo dài hoặc đầu quay mạnh; xem ngữ cảnh trước khi xác nhận.', new, closed)
        active = [kind for kind, tracker in self.trackers.items() if tracker.event]
        if any(k in active for k in ('phone', 'multiple_faces', 'look_away')):
            status, message = 'review', 'Có sự kiện cần giám thị xem lại'
        elif not frame_ok or obs.face_count != 1 or not valid:
            status, message = 'unavailable', obs.quality_reason or 'Chưa đủ dữ liệu để đánh giá'
        elif not self.ready:
            status, message = 'calibrating', 'Nhìn màn hình, đọc và làm bài bình thường; giữ camera cố định'
        elif condition or phone_pending:
            status, message = 'observing', 'Đang xác nhận tín hiệu; chưa tạo cảnh báo'
        else:
            status, message = 'normal', 'Chưa có sự kiện cần xem lại'
        progress = 1.0 if self.ready else min(0.99, self.calibration_time / cfg.calibration_seconds)
        return Result(t, status, round(risk, 1), progress, quality, message, active, new, closed, diagnostics)
