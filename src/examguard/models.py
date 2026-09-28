"""Download explicit, versioned model artifacts; never at application startup."""
from pathlib import Path
import hashlib
import json
import urllib.request

MODELS = {
    'face_landmarker.task': {
        'url': 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
        'min_size': 3000000,
        'source': 'Google MediaPipe Face Landmarker, float16 version 1',
    },
    'yolox.onnx': {
        'url': 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx',
        'sha256': 'c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063',
        'min_size': 35000000,
        'source': 'OpenCV Zoo YOLOX-S, COCO 80 classes, November 2022',
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def download_models(directory, report=print):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, spec in MODELS.items():
        target = root / name
        expected = spec.get('sha256')
        valid = target.exists() and target.stat().st_size >= spec['min_size']
        if valid and expected:
            valid = sha256(target) == expected
        if not valid:
            report(f'Downloading {name} ...')
            temporary = target.with_suffix(target.suffix + '.part')
            request = urllib.request.Request(spec['url'], headers={'User-Agent': 'ExamGuard-Local/0.1'})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as stream:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            if temporary.stat().st_size < spec['min_size']:
                raise RuntimeError(f'Incomplete model: {name}')
            if expected and sha256(temporary) != expected:
                raise RuntimeError(f'Invalid checksum: {name}')
            temporary.replace(target)
        manifest[name] = {**spec, 'sha256': sha256(target), 'size': target.stat().st_size}
        report(f'Ready: {name}')
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
