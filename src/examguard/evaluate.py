"""Event-level evaluation with one-to-one matching and explicit label completeness."""
from pathlib import Path
import json
import math
from statistics import median

TARGETS = ('phone', 'multiple_faces', 'look_away')


def validate_labels(labels):
    if labels.get('complete') is not True:
        raise ValueError('Labels must declare complete=true only after the entire video has been reviewed')
    duration = labels.get('duration_seconds')
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('duration_seconds must be finite and positive')
    if not labels.get('subject_id') or not labels.get('session_id'):
        raise ValueError('subject_id and session_id are required for leakage checks')
    for event in labels.get('events', []):
        if event.get('kind') not in TARGETS:
            raise ValueError(f'Unsupported event kind: {event.get("kind")}')
        for key in ('start', 'end'):
            if not isinstance(event.get(key), (int,float)) or not math.isfinite(event[key]):
                raise ValueError(f'Invalid {key}')
        if not 0 <= event['start'] < event['end'] <= duration:
            raise ValueError('Ground truth interval outside session')


def evaluate(predictions, labels, tolerance=1.0):
    validate_labels(labels)
    if tolerance < 0 or not math.isfinite(tolerance):
        raise ValueError('Invalid tolerance')
    per_kind = {}
    total_tp = total_fp = total_fn = 0
    all_latencies = []
    for kind in TARGETS:
        truths = [e for e in labels.get('events', []) if e['kind'] == kind]
        preds = sorted([e for e in predictions if e['kind'] == kind], key=lambda e:e['detected_at'])
        # Bipartite maximum matching prevents one alert counting multiple truths.
        candidates = []
        for pred in preds:
            detected = pred['detected_at']
            if not math.isfinite(detected) or not 0 <= detected <= labels['duration_seconds']:
                raise ValueError('Prediction outside labelled session')
            choices = [j for j, truth in enumerate(truths)
                       if truth['start']-tolerance <= detected <= truth['end']+tolerance]
            candidates.append(sorted(choices, key=lambda j: abs(detected-truths[j]['start'])))
        matched = {}
        def assign(i, visited):
            for j in candidates[i]:
                if j in visited:
                    continue
                visited.add(j)
                if j not in matched or assign(matched[j], visited):
                    matched[j] = i
                    return True
            return False
        for i in range(len(preds)):
            assign(i, set())
        tp = len(matched)
        fp, fn = len(preds)-tp, len(truths)-tp
        latencies = [max(0, preds[i]['detected_at']-truths[j]['start']) for j,i in matched.items()]
        per_kind[kind] = {'true_positive':tp, 'false_positive':fp, 'false_negative':fn,
                          'precision':tp/(tp+fp) if tp+fp else None,
                          'recall':tp/(tp+fn) if tp+fn else None,
                          'median_latency_seconds':median(latencies) if latencies else None}
        total_tp += tp
        total_fp += fp
        total_fn += fn
        all_latencies.extend(latencies)
    return {'session_id':labels['session_id'], 'subject_id':labels['subject_id'],
            'duration_seconds':labels['duration_seconds'], 'matching_tolerance_seconds':tolerance,
            'true_positive':total_tp, 'false_positive':total_fp, 'false_negative':total_fn,
            'precision':total_tp/(total_tp+total_fp) if total_tp+total_fp else None,
            'recall':total_tp/(total_tp+total_fn) if total_tp+total_fn else None,
            'false_alerts_per_monitored_hour':total_fp*3600/labels['duration_seconds'],
            'median_latency_seconds':median(all_latencies) if all_latencies else None,
            'per_kind':per_kind,
            'note':'Event detection only; not a cheating conviction. Null means not estimable. Complete labels required.'}


def evaluate_session(folder, label_path):
    folder = Path(folder)
    labels = json.loads(Path(label_path).read_text(encoding='utf-8'))
    session = json.loads((folder/'session.json').read_text(encoding='utf-8'))
    if labels.get('session_id') != session['id']:
        raise ValueError('Labels belong to a different session')
    if session.get('status') != 'finished':
        raise ValueError('Evaluate a completed, non-error session')
    if abs(labels.get('duration_seconds',0)-session['duration']) > max(1.0,session['duration']*.01):
        raise ValueError('Label duration does not match session duration')
    predictions = json.loads((folder/'events.json').read_text(encoding='utf-8'))
    return evaluate(predictions, labels)
