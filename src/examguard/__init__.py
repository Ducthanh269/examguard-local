"""ExamGuard Local: explainable, local exam observation and review."""

__version__ = "0.1.0"

# Keep third-party caches inside the app, not the user's global profile.
import os
from pathlib import Path
_cache = Path(os.environ.get('EXAMGUARD_ROOT', Path(__file__).resolve().parent.parent)) / 'data' / 'cache'
_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', str(_cache / 'matplotlib'))
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
