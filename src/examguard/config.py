from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Config:
    calibration_seconds: float = 30.0
    calibration_samples: int = 80
    min_quality: float = 0.60
    max_gap_seconds: float = 1.5
    look_dwell_seconds: float = 5.0
    strong_head_dwell_seconds: float = 8.0
    face_dwell_seconds: float = 2.5
    absent_dwell_seconds: float = 5.0
    quality_dwell_seconds: float = 3.0
    phone_dwell_seconds: float = 2.5
    phone_min_hits: int = 3
    phone_confidence: float = 0.78
    phone_sample_gap: float = 2.2
    exit_dwell_seconds: float = 2.0
    short_half_life: float = 0.7
    long_half_life: float = 23.1
    short_confirm: float = 0.55
    baseline_tau: float = 60.0
    allow_paper: bool = True
    inference_fps: float = 10.0
    object_interval: float = 0.8
    evidence_fps: float = 5.0
    pre_roll_seconds: float = 5.0
    post_roll_seconds: float = 5.0
    record_evidence: bool = True

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool):
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field.name} must be finite and positive")
        for name in ('min_quality', 'phone_confidence', 'short_confirm'):
            if getattr(self, name) >= 1:
                raise ValueError(f"{name} must be less than 1")
        for name in ('calibration_samples', 'phone_min_hits'):
            if not isinstance(getattr(self, name), int):
                raise ValueError(f"{name} must be an integer")
        if self.phone_min_hits < 2:
            raise ValueError('phone_min_hits must be at least 2')

    def to_dict(self):
        return asdict(self)

    @classmethod
    def load(cls, path=None):
        if not path:
            return cls()
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown settings: {sorted(unknown)}")
        return cls(**data)
