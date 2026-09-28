# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-XX-XX

### Added
- Initial release
- Real-time detection of 5 behaviors: phone, multiple faces, look away, face absent, poor quality
- 30-second adaptive calibration with robust statistics
- Evidence clip recording (AVI + JSON sidecar)
- SQLite storage with CSV export
- PySide6 desktop GUI (dark theme, Vietnamese)
- Evaluation tools (precision/recall with bipartite matching)
- PyInstaller packaging for standalone .exe
- 34 unit tests with model smoke tests

### Technical Details
- MediaPipe Face Landmarker (478 landmarks)
- YOLOX-S object detection (COCO class 67 = cell phone)
- Dual EMA filtering (short 0.7s, long 23.1s half-life)
- Adaptive risk threshold based on quiet-period statistics
- Anti-cache phone detection (requires fresh inference samples)
- Kabsch residual for face shape comparison
- IoU-based phone tracking

### Security & Privacy
- 100% offline operation
- No identity recognition
- No audio recording
- Local data storage only
- Excel formula injection prevention in CSV export

[1.0.0]: https://github.com/yourusername/examguard-local/releases/tag/v1.0.0