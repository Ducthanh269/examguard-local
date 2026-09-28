from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict
import csv
import json
import sqlite3
import uuid
from contextlib import contextmanager

from . import __version__


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / 'examguard.sqlite3'
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, created TEXT, source TEXT, folder TEXT,
                    status TEXT, duration REAL DEFAULT 0, config TEXT);
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    kind TEXT, start REAL, detected_at REAL, end REAL,
                    reason TEXT, peak_score REAL, review TEXT DEFAULT 'pending',
                    note TEXT DEFAULT '', clip TEXT, clip_status TEXT DEFAULT 'pending',
                    FOREIGN KEY(session_id) REFERENCES sessions(id));
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, event_id TEXT, created TEXT,
                    verdict TEXT, note TEXT);
            ''')

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.database, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        try:
            with con:
                yield con
        finally:
            con.close()

    def create_session(self, source, config, model_manifest=None):
        sid = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
        folder = self.root / 'sessions' / sid
        folder.mkdir(parents=True)
        created = datetime.now(timezone.utc).isoformat()
        metadata = {'id': sid, 'version': __version__, 'created': created,
                    'source': str(source), 'config': config.to_dict(),
                    'models': model_manifest or {}, 'status': 'running',
                    'score_is_probability': False}
        (folder / 'session.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        with self.connect() as con:
            con.execute('INSERT INTO sessions(id,created,source,folder,status,config) VALUES(?,?,?,?,?,?)',
                        (sid, created, str(source), str(folder), 'running', json.dumps(config.to_dict())))
        return sid, folder

    def save_event(self, sid, event):
        with self.connect() as con:
            con.execute('''INSERT INTO events(id,session_id,kind,start,detected_at,end,reason,peak_score)
                           VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                           end=excluded.end, peak_score=excluded.peak_score''',
                        (event.id, sid, event.kind, event.start, event.detected_at,
                         event.end, event.reason, event.peak_score))

    def set_clip(self, event_id, path, status):
        with self.connect() as con:
            con.execute('UPDATE events SET clip=?, clip_status=? WHERE id=?', (str(path) if path else None, status, event_id))

    def finish_session(self, sid, duration, status='finished'):
        with self.connect() as con:
            con.execute('UPDATE sessions SET status=?,duration=? WHERE id=?', (status, duration, sid))
            row = con.execute('SELECT folder FROM sessions WHERE id=?', (sid,)).fetchone()
        if row:
            path = Path(row['folder']) / 'session.json'
            metadata = json.loads(path.read_text(encoding='utf-8'))
            metadata.update(status=status, duration=duration)
            path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
            self.export(sid, Path(row['folder']) / 'events.csv')
            events = self.events(sid)
            (Path(row['folder']) / 'events.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')

    def sessions(self):
        with self.connect() as con:
            return [dict(row) for row in con.execute('SELECT * FROM sessions ORDER BY created DESC')]

    def events(self, sid):
        with self.connect() as con:
            return [dict(row) for row in con.execute('SELECT * FROM events WHERE session_id=? ORDER BY detected_at', (sid,))]

    def review(self, event_id, verdict, note=''):
        if verdict not in ('confirmed', 'false_positive', 'uncertain', 'pending'):
            raise ValueError('Invalid review verdict')
        with self.connect() as con:
            if not con.execute('SELECT 1 FROM events WHERE id=?', (event_id,)).fetchone():
                raise ValueError('Event not found')
            con.execute('UPDATE events SET review=?,note=? WHERE id=?', (verdict, note, event_id))
            con.execute('INSERT INTO reviews(event_id,created,verdict,note) VALUES(?,?,?,?)',
                        (event_id, datetime.now(timezone.utc).isoformat(), verdict, note))

    def export(self, sid, path):
        rows = self.events(sid)
        fields = ['id','session_id','kind','start','detected_at','end','reason','peak_score','review','note','clip','clip_status']
        with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                # Prevent a reviewer-supplied note from becoming an Excel formula.
                writer.writerow({k: ("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v)
                                 for k,v in row.items()})


def write_observation(stream, observation, result):
    payload = {'observation': asdict(observation), 'status': result.status,
               'risk': result.risk, 'calibration': result.calibration,
               'active': result.active, 'diagnostics': result.diagnostics}
    stream.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + '\n')
