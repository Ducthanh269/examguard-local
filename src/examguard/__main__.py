import argparse
from dataclasses import fields
import json
import os
from pathlib import Path
import sys

from .config import Config


def app_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description='ExamGuard Local — local observation and evidence review')
    parser.add_argument('--root', type=Path, default=app_root())
    parser.add_argument('--config', type=Path)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('gui')
    sub.add_parser('download-models')
    sub.add_parser('doctor')
    analyze = sub.add_parser('analyze', help='Analyze a video offline; does not open a webcam')
    analyze.add_argument('video', type=Path)
    replay = sub.add_parser('replay', help='Replay observations through the engine with a new configuration')
    replay.add_argument('observations', type=Path)
    replay.add_argument('--output', required=True, type=Path)
    ev = sub.add_parser('evaluate')
    ev.add_argument('session', type=Path)
    ev.add_argument('labels', type=Path)
    ev.add_argument('--output', type=Path)
    init = sub.add_parser('label-template')
    init.add_argument('session', type=Path)
    init.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    cfg = Config.load(args.config)
    root = args.root.resolve()
    if args.command in (None, 'gui'):
        from .desktop import launch
        return launch(root, cfg)
    if args.command == 'download-models':
        from .models import download_models
        download_models(root/'models')
    elif args.command == 'doctor':
        import importlib.metadata
        from .models import MODELS, sha256
        state = {'root':str(root), 'python':sys.version, 'models':{}, 'packages':{}}
        for name, spec in MODELS.items():
            path = root/'models'/name
            valid = path.exists() and path.stat().st_size >= spec['min_size']
            if valid and spec.get('sha256'):
                valid = sha256(path) == spec['sha256']
            state['models'][name] = {'present_and_valid':valid}
        for package in ('numpy','mediapipe','opencv-contrib-python','PySide6','Pillow'):
            try:
                state['packages'][package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                state['packages'][package] = 'MISSING'
        print(json.dumps(state,ensure_ascii=False,indent=2))
        return 0 if all(x['present_and_valid'] for x in state['models'].values()) and 'MISSING' not in state['packages'].values() else 1
    elif args.command == 'analyze':
        from .runner import Runner
        if not args.video.is_file():
            raise ValueError('Video does not exist')
        runner = Runner(str(args.video.resolve()), cfg, root)
        runner.start()
        last_second = -1
        import queue
        while runner.is_alive() or not runner.messages.empty():
            try:
                message = runner.messages.get(timeout=.5)
            except queue.Empty:
                continue
            if message['type'] == 'frame':
                result = message['result']
                second = int(result.timestamp)
                if second//10 != last_second:
                    last_second = second//10
                    print(f'{second}s: {result.status}, risk={result.risk}')
        if runner.failure:
            raise RuntimeError(runner.failure)
        print(f'Session: {root / "data" / "sessions" / runner.sid}')
    elif args.command == 'replay':
        from .engine import Engine, Observation
        engine, events = Engine(cfg), []
        with args.observations.open(encoding='utf-8') as stream:
            for line in stream:
                obs = Observation(**json.loads(line)['observation'])
                result = engine.step(obs)
                events.extend(result.new_events)
        engine.finish()
        args.output.write_text(json.dumps([e.to_dict() for e in events],ensure_ascii=False,indent=2),encoding='utf-8')
        args.output.with_suffix('.config.json').write_text(json.dumps(cfg.to_dict(),indent=2),encoding='utf-8')
    elif args.command == 'evaluate':
        from .evaluate import evaluate_session
        result = evaluate_session(args.session,args.labels)
        text = json.dumps(result,ensure_ascii=False,indent=2)
        if args.output:
            args.output.write_text(text,encoding='utf-8')
        print(text)
    elif args.command == 'label-template':
        session = json.loads((args.session/'session.json').read_text(encoding='utf-8'))
        payload = {'session_id':session['id'],'subject_id':'REPLACE_WITH_ANONYMOUS_ID',
                   'complete':False,'duration_seconds':session['duration'],'events':[],
                   'instructions':'Review the entire video. Add {kind: phone|multiple_faces|look_away, start: seconds, end: seconds}. Set complete=true only when finished.'}
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump(payload,stream,ensure_ascii=False,indent=2)
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except (ValueError,RuntimeError,OSError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        raise SystemExit(1)
