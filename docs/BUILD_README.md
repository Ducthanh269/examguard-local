# ExamGuard Local - Build Guide

## Cấu trúc dự án

```
.
├── examguard/          # Mã nguồn chính
│   ├── config.py       # Cấu hình & validation
│   ├── engine.py       # Rule-based detection engine
│   ├── vision.py       # MediaPipe + YOLOX inference
│   ├── runner.py       # Thread xử lý video
│   ├── evidence.py     # Ghi clip AVI
│   ├── storage.py      # SQLite + CSV export
│   ├── evaluate.py     # Precision/recall evaluation
│   ├── desktop.py      # PySide6 GUI
│   └── __main__.py     # CLI entry point
├── tests/              # Unit tests (34 tests)
├── models/             # ML models (face_landmarker.task, yolox.onnx)
├── data/               # SQLite + sessions (tạo khi chạy)
├── launch.py           # Entry point cho cả dev và frozen
├── examguard.spec      # PyInstaller spec
├── requirements.txt    # Python dependencies
├── SETUP.cmd           # Cài đặt môi trường
├── START.cmd           # Chạy ứng dụng
├── TEST.cmd            # Chạy unit tests
└── BUILD.cmd           # Đóng gói thành .exe
```

## Quy trình

### 1. Cài đặt (lần đầu)
```
SETUP.cmd
```
Tạo venv `.runtime\`, cài dependencies, tải models.

### 2. Chạy từ source
```
START.cmd
```
Dùng Python trong `.runtime\`.

### 3. Chạy tests
```
TEST.cmd
```
34 unit tests, bao gồm smoke test với models thật.

### 4. Đóng gói .exe
```
BUILD.cmd
```
Tạo `dist\ExamGuard\ExamGuard.exe` (~430 MB folder).

Sau khi build, `START.cmd` tự động dùng `.exe` thay vì Python.

## Cấu trúc output sau khi build

```
dist\ExamGuard\
├── ExamGuard.exe              # Executable chính (~5 MB)
├── _internal\                 # Bundled dependencies
│   ├── models\
│   │   ├── face_landmarker.task
│   │   ├── yolox.onnx
│   │   └── manifest.json
│   ├── *.pyd, *.dll           # Python + native libs
│   ├── PySide6\               # Qt plugins
│   └── ...
└── data\                      # Tạo khi chạy lần đầu
    ├── examguard.sqlite3
    └── sessions\
```

## Lưu ý kỹ thuật

- **EXAMGUARD_ROOT**: `launch.py` tự động trỏ đến thư mục chứa `.exe`
- **Models**: PyInstaller đặt trong `_internal\models\`, code tự tìm đúng vị trí
- **Console**: Build ở chế độ windowed (không hiện console)
- **Data**: SQLite + clips lưu cùng thư mục với `.exe`

## Troubleshooting

**Build chậm**: Lần đầu mất 3-5 phút do PyInstaller phân tích dependencies.

**Models không tìm thấy**: Kiểm tra `dist\ExamGuard\_internal\models\` có đủ 3 file.

**App không khởi động**: Xem `data\startup_error.txt` để biết chi tiết lỗi.

**Muốn build lại từ đầu**: Xóa `build\`, `dist\`, rồi chạy `BUILD.cmd`.