"""Desktop / packaging entry point."""
import sys
from pathlib import Path
import os

if getattr(sys, 'frozen', False):
    # PyInstaller layout: ExamGuard.exe sits next to _internal\ (data, models, libs).
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent

os.environ['EXAMGUARD_ROOT'] = str(ROOT)

if __name__ == '__main__':
    from examguard.desktop import launch
    from examguard.config import Config
    config_path = ROOT / 'config.json'
    try:
        raise SystemExit(launch(ROOT, Config.load(config_path if config_path.exists() else None)))
    except Exception:
        import traceback
        (ROOT/'data').mkdir(exist_ok=True)
        (ROOT/'data'/'startup_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise