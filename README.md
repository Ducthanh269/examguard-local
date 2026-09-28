# ExamGuard Local

> **Local, explainable exam proctoring for desktops.** Detects suspicious behavior via webcam with evidence clips — fully offline, no cloud, no identity recognition.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![PySide6](https://img.shields.io/badge/PySide6-6.11.2-green.svg)](https://doc.qt.io/qtforpython-6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-34%2F34%20pass-brightgreen.svg)](#testing)

[🇻🇳 Tài liệu tiếng Việt](docs/TAILIEU_HUONGDAN.md) | [📖 Build Guide](docs/BUILD_README.md)

---

## 🎯 What is ExamGuard Local?

ExamGuard Local is a **desktop application** that helps exam proctors detect cheating behaviors in real-time using a webcam. Unlike cloud-based proctoring tools, it runs **100% offline on a single machine** — no video leaves the computer, no identity is recognized, and the final decision always belongs to a human reviewer.

### Key Principles

- 🔒 **Privacy-first**: All data stays on the local machine
- 🤖 **AI-assisted, not AI-decided**: Flags suspicious events for human review
- 📹 **Evidence-based**: Short video clips around each detected event
- 🌐 **Offline**: No internet required after setup
- 🪟 **Lightweight**: Runs on CPU, no GPU needed

---

## ✨ Features

### Detected Behaviors

| Behavior | Trigger Condition |
|---|---|
| 📱 **Phone detected** | YOLOX-S detects cell phone ≥ 3 independent samples with confidence ≥ 0.78 |
| 👥 **Multiple faces** | ≥ 2 faces visible continuously for ≥ 2.5 seconds |
| 👀 **Looking away** | Head + gaze deviation sustained ≥ 5 seconds (or extreme head turn ≥ 8s) |
| 🚫 **Face absent** | No face in frame for ≥ 5 seconds |
| 🌫️ **Poor quality** | Dark/blurry frame for ≥ 3 seconds |

### Technical Highlights

- **Adaptive baseline**: 30-second calibration learns each student's normal posture
- **Robust statistics**: Median + MAD (1.4826×) for outlier-resistant thresholds
- **Dual EMA filtering**: Short-term (0.7s half-life) + long-term (23.1s half-life)
- **Anti-cache phone detection**: Each YOLOX sample must be a fresh inference
- **Bipartite matching**: One-to-one prediction/ground-truth pairing for evaluation
- **Evidence clips**: AVI with sidecar JSON containing real source timestamps

---

## 🖼️ Screenshots

> *Add screenshots of the GUI here after running the app*

```
┌─────────────────────────────────────────────────┐
│  EXAMGUARD LOCAL          [● ĐANG GIÁM SÁT]    │
├──────────┬──────────────────────────────────────┤
│ Nguồn    │  ┌────────┐ ┌────────┐ ┌────────┐  │
│ ○ Webcam │  │ 00:05  │ │  42/100│ │   3    │  │
│ ○ Video  │  │ TIME   │ │  RISK  │ │ EVENTS │  │
│          │  └────────┘ └────────┘ └────────┘  │
│ ☐ Paper  │  ┌────────────────────────────────┐ │
│ ☐ Record │  │                                │ │
│ ☐ Notif  │  │      [Camera Preview]          │ │
│          │  │                                │ │
│ [START]  │  └────────────────────────────────┘ │
└──────────┴──────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.12 | Core application |
| **GUI** | PySide6 6.11.2 | Desktop interface (Qt6) |
| **Face Detection** | MediaPipe Face Landmarker | 478 3D landmarks per face |
| **Object Detection** | YOLOX-S (ONNX) | Cell phone detection (COCO class 67) |
| **Computer Vision** | OpenCV 4.11.0 | Image processing, DNN inference |
| **Storage** | SQLite3 | Sessions, events, reviews |
| **Packaging** | PyInstaller 6.22.3 | Standalone .exe distribution |

### Models

- **Face Landmarker** (~3.7 MB): Google MediaPipe, float16, 478 landmarks
- **YOLOX-S** (~35 MB): OpenCV Zoo, November 2022, 80 COCO classes

---

## 📦 Installation

### Option 1: Use Pre-built Executable (Recommended)

1. Download the latest release from [Releases](../../releases)
2. Extract `ExamGuard.zip`
3. Run `ExamGuard.exe`

No Python installation required.

### Option 2: Run from Source

**Requirements**: Python 3.12, Windows 10/11

```cmd
# Clone the repository
git clone https://github.com/yourusername/examguard-local.git
cd examguard-local

# Run setup (creates venv, installs deps, downloads models)
scripts\SETUP.cmd

# Start the application
scripts\START.cmd
```

### Option 3: Build Your Own Executable

```cmd
scripts\BUILD.cmd
```

Output: `dist\ExamGuard\ExamGuard.exe`

---

## 🚀 Usage

### Quick Start

1. **Launch** the application
2. **Select source**: Webcam or video file
3. **Configure**:
   - ☑ Allow paper notes (recommended: ON)
   - ☑ Record evidence clips (recommended: ON)
   - ☑ **Informed consent** (REQUIRED — must be checked)
4. **Click "Start Session"**
5. **Calibration** (30 seconds): Student looks at screen normally
6. **Monitor**: Watch the dashboard for status changes
7. **Review**: Go to "Events & Review" tab to examine flagged events
8. **Stop & Save**: Click "Stop and Save"

### Status Indicators

| Color | Status | Meaning |
|---|---|---|
| 🟢 Green | **MONITORING** | Normal operation |
| 🔵 Blue | **CALIBRATING** | Learning baseline (first 30s) |
| 🟡 Yellow | **CONFIRMING** | Suspicious signal detected |
| 🟠 Orange | **NEEDS REVIEW** | Event flagged for proctor |
| 🔴 Red | **NO DATA** | Camera/quality issue |

### Reviewing Events

1. Switch to **"Events & Review"** tab
2. Select a session from the dropdown
3. Double-click an event to open the review dialog
4. Watch the clip, read the reason
5. Mark as: **Confirmed** / **False Positive** / **Uncertain**
6. Add notes (optional) → Save

### Exporting Reports

Click **"Export CSV"** to save all events with timestamps, types, reviews, and clip paths.

---

## 🧪 Testing

```cmd
scripts\TEST.cmd
```

**34 unit tests** covering:
- Engine logic (calibration, dwell times, event detection)
- Evaluation (bipartite matching, precision/recall)
- Storage (SQLite, CSV export, formula injection prevention)
- Vision (Kabsch residual, IoU, evidence clips)
- Model smoke tests (real MediaPipe + YOLOX on blank frames)

---

## 📊 Evaluation

Measure precision/recall against labeled ground truth:

```cmd
# Generate label template
.runtime\Scripts\python.exe -m examguard label-template data\sessions\<session_id> --output labels.json

# Edit labels.json: add subject_id, mark complete=true, list events

# Run evaluation
.runtime\Scripts\python.exe -m examguard evaluate data\sessions\<session_id> labels.json --output result.json
```

### Sample Output

```json
{
  "true_positive": 5,
  "false_positive": 2,
  "false_negative": 1,
  "precision": 0.714,
  "recall": 0.833,
  "false_alerts_per_monitored_hour": 2.0,
  "median_latency_seconds": 1.2
}
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│              GUI Layer (PySide6)                │
│  MainWindow, ReviewDialog, Tabs, Metrics        │
└────────────────────┬────────────────────────────┘
                     │ Queue (thread-safe)
┌────────────────────▼────────────────────────────┐
│           Runner Thread (daemon)                │
│  VideoCapture → Vision → Engine → Storage       │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐
   │ Vision  │  │ Engine  │  │Evidence │
   │MediaPipe│  │ Rules   │  │  AVI    │
   │ YOLOX   │  │ Stats   │  │ Ring    │
   └─────────┘  └─────────┘  └─────────┘
                     │
                     ▼
              ┌─────────────┐
              │   Storage   │
              │   SQLite    │
              └─────────────┘
```

### Data Flow

1. **Capture**: Webcam/video → OpenCV (10 FPS inference, 5 FPS evidence)
2. **Vision**: MediaPipe extracts face landmarks → yaw, pitch, gaze ratios
3. **Engine**: Compares to baseline → risk score → event detection
4. **Evidence**: Ring buffer (5s pre-roll) → AVI clip on event
5. **Storage**: SQLite + JSONL observations + CSV export
6. **GUI**: Real-time display via thread-safe queue

---

## 📁 Project Structure

```
examguard-local/
├── src/
│   ├── examguard/           # Main module
│   │   ├── config.py        # Configuration & validation
│   │   ├── engine.py        # Rule-based detection engine
│   │   ├── vision.py        # MediaPipe + YOLOX inference
│   │   ├── runner.py        # Video processing thread
│   │   ├── evidence.py      # AVI clip recording
│   │   ├── storage.py       # SQLite + CSV export
│   │   ├── evaluate.py      # Precision/recall evaluation
│   │   ├── desktop.py       # PySide6 GUI
│   │   └── __main__.py      # CLI entry point
│   ├── tests/               # Unit tests (34 tests)
│   ├── models/              # ML models
│   └── launch.py            # Entry point
├── docs/
│   ├── TAILIEU_HUONGDAN.md  # Vietnamese documentation
│   └── BUILD_README.md      # Build instructions
├── scripts/
│   ├── SETUP.cmd            # Install dependencies
│   ├── START.cmd            # Run application
│   ├── TEST.cmd             # Run tests
│   ├── BUILD.cmd            # Build .exe
│   ├── examguard.spec       # PyInstaller spec
│   └── requirements.txt     # Python dependencies
├── dist/                    # Pre-built executable
│   └── ExamGuard/
│       ├── ExamGuard.exe
│       └── _internal/
├── .gitignore
├── LICENSE
└── README.md
```

---

## ⚖️ Limitations & Ethics

### Technical Limitations

1. **Camera-only detection**: Phones outside the frame are not detected
2. **No identity recognition**: Cannot identify which student is cheating
3. **No screen analysis**: Cannot detect Google searches, copy-paste
4. **No audio recording**: Video only
5. **Camera quality dependent**: Poor lighting/small faces reduce accuracy
6. **Generic phone model**: Not specifically trained for exam scenarios

### Ethical Requirements ⚠️

**MANDATORY** before use:

1. ✅ **Inform students** that they are being monitored
2. ✅ **Obtain consent** (written agreement recommended)
3. ✅ **Transparency**: Clips are for review only, not public
4. ✅ **Human decision**: AI assists, proctors decide
5. ✅ **Data security**: Protect the machine running the software
6. ✅ **Legal compliance**: Follow local data protection laws (GDPR, etc.)

### Recommended Use

- ✅ As a **support tool**, not a replacement for proctors
- ✅ Combined with **overview cameras** of the exam room
- ✅ With **proper calibration** (first 30 seconds are critical)
- ✅ With **clip review** before any disciplinary action

- ❌ Do NOT use clips as the sole evidence
- ❌ Do NOT auto-deduct points based on AI alerts

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```cmd
scripts\SETUP.cmd
scripts\TEST.cmd
```

### Code Style

- Follow PEP 8
- Add tests for new features
- Update documentation

---

## 📄 License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [MediaPipe](https://developers.google.com/mediapipe) — Face landmark detection
- [OpenCV Zoo](https://github.com/opencv/opencv_zoo) — YOLOX-S model
- [PySide6](https://doc.qt.io/qtforpython-6/) — Qt6 Python bindings
- [PyInstaller](https://www.pyinstaller.org/) — Executable packaging

---

## 📞 Support

- 📖 **Documentation**: [docs/TAILIEU_HUONGDAN.md](docs/TAILIEU_HUONGDAN.md)
- 🐛 **Bug reports**: [Open an issue](../../issues)
- 💬 **Questions**: [GitHub Discussions](../../discussions)

---

## ⚠️ Disclaimer

This software is provided "as is", without warranty of any kind. The authors are not responsible for any misuse or ethical violations. Users are responsible for ensuring compliance with local laws and ethical guidelines when deploying this software.

**Remember**: AI is a tool to assist human judgment, not replace it. Always review evidence before making decisions that affect students.