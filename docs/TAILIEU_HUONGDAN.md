# ExamGuard Local - Tài liệu kỹ thuật & hướng dẫn sử dụng

> **Phiên bản**: 0.1.0  
> **Loại**: Ứng dụng desktop giám sát thi cử cục bộ (offline)  
> **Đối tượng**: Giám thị, quản lý phòng thi, nhà trường

---

## Mục lục

1. [Tổng quan sản phẩm](#1-tổng-quan-sản-phẩm)
2. [Công dụng & đối tượng sử dụng](#2-công-dụng--đối-tượng-sử-dụng)
3. [Công nghệ sử dụng](#3-công-nghệ-sử-dụng)
4. [Công thức & thuật toán](#4-công-thức--thuật-toán)
5. [Kiến trúc hệ thống](#5-kiến-trúc-hệ-thống)
6. [Hướng dẫn cài đặt](#6-hướng-dẫn-cài-đặt)
7. [Hướng dẫn sử dụng](#7-hướng-dẫn-sử-dụng)
8. [Hướng dẫn đánh giá (Evaluation)](#8-hướng-dẫn-đánh-giá-evaluation)
9. [Hướng dẫn đóng gói .exe](#9-hướng-dẫn-đóng-gói-exe)
10. [Giới hạn & lưu ý đạo đức](#10-giới-hạn--lưu-ý-đạo-đức)

---

## 1. Tổng quan sản phẩm

**ExamGuard Local** là ứng dụng desktop chạy **hoàn toàn offline trên một máy tính**, giúp giám thị phát hiện các hành vi gian lận thi cử qua webcam. Điểm khác biệt cốt lõi:

- **Không upload video/dữ liệu** lên cloud
- **Không nhận diện danh tính**, cảm xúc, giọng nói hay màn hình
- **Chỉ đưa ra cảnh báo có bằng chứng** (clip ngắn) để giám thị xem xét
- **Quyết định cuối cùng luôn thuộc về con người**

### Các hành vi được phát hiện

| Mã | Hành vi | Điều kiện kích hoạt |
|---|---|---|
| `phone` | Điện thoại xuất hiện | YOLOX phát hiện class "cell phone" với confidence ≥ 0.78, lặp lại ≥ 3 lần trong khoảng cách mẫu mới |
| `multiple_faces` | Có người thứ hai | ≥ 2 khuôn mặt liên tục ≥ 2.5 giây |
| `look_away` | Nhìn lệch kéo dài | Đầu + mắt cùng lệch ≥ 5 giây (hoặc đầu quay mạnh ≥ 8 giây) |
| `face_absent` | Không thấy khuôn mặt | Không có mặt trong khung hình ≥ 5 giây |
| `poor_quality` | Hình ảnh không đủ rõ | Frame tối/mờ/nhiễu ≥ 3 giây |

---

## 2. Công dụng & đối tượng sử dụng

### Công dụng chính

1. **Hỗ trợ giám thị thời gian thực**: Phát hiện sớm các hành vi đáng ngờ, giảm tải cho giám thị khi phải quan sát nhiều thí sinh
2. **Lưu bằng chứng khách quan**: Clip AVI ngắn (~5 giây trước/sau) kèm timestamp thực từ nguồn video
3. **Đánh giá sau kỳ thi**: Giám thị xem lại các sự kiện, phân loại (đúng/sai/chưa rõ) trước khi đưa ra quyết định
4. **Đo lường hiệu quả**: Công cụ evaluation tính precision/recall trên dữ liệu có nhãn

### Đối tượng sử dụng

- **Giám thị phòng thi**: Cài trên laptop, kết nối webcam, chạy nền
- **Quản lý kỳ thi**: Xem lại báo cáo tổng hợp, xuất CSV
- **Nhà phát triển/nghiên cứu**: Chạy evaluation, benchmark trên video có nhãn

### Không phù hợp cho

- Phát hiện gian lận qua màn hình (screen capture)
- Nhận diện danh tính thí sinh
- Giám sát từ xa qua internet
- Phát hiện âm thanh/ghi âm

---

## 3. Công nghệ sử dụng

### Stack chính

| Công nghệ | Phiên bản | Vai trò |
|---|---|---|
| **Python** | 3.12 | Ngôn ngữ chính |
| **PySide6** | 6.11.2 | GUI desktop (Qt6) |
| **MediaPipe Tasks** | 0.10.21 | Face landmark detection (478 điểm) |
| **OpenCV** | 4.11.0 | Xử lý ảnh, video I/O, DNN inference |
| **YOLOX-S** | ONNX export | Object detection (80 lớp COCO) |
| **NumPy** | 1.26.4 | Tính toán ma trận |
| **Pillow** | 12.3.0 | Hỗ trợ ảnh |
| **SQLite3** | Built-in | Lưu trữ sessions & events |
| **PyInstaller** | 6.22.3 | Đóng gói .exe |

### Mô hình AI

#### MediaPipe Face Landmarker (float16)
- **Nguồn**: Google MediaPipe
- **Đầu vào**: Frame RGB
- **Đầu ra**: 478 landmarks 3D (x, y, z) cho mỗi khuôn mặt
- **Sử dụng**: Ước lượng yaw, pitch, gaze ratio, shape residual
- **Kích thước**: ~3.7 MB

#### YOLOX-S (OpenCV Zoo, Nov 2022)
- **Nguồn**: OpenCV Zoo
- **Lớp quan tâm**: class 67 (cell phone)
- **Input**: 640×640 RGB, letterbox
- **Output**: 8400 anchors × 85 (x, y, w, h, obj, 80 classes)
- **Kích thước**: ~35 MB

### Kiến trúc phần mềm

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

---

## 4. Công thức & thuật toán

### 4.1. Hiệu chuẩn (Calibration) - 30 giây đầu

Mục đích: Học baseline (giá trị bình thường) của từng thí sinh trong điều kiện ngồi yên, nhìn màn hình.

**Các biến được hiệu chuẩn**: `yaw`, `pitch`, `gaze_x`, `gaze_y`

**Điều kiện mẫu hợp lệ**:
- `quality ≥ 0.60` (ảnh đủ sáng, đủ nét)
- `face_count == 1` (đúng 1 mặt)
- Tất cả giá trị finite
- `eyes_open == True`
- Không có sự kiện phone đang pending

**Robust statistics** (chống outlier):

$$\text{median} = \text{median}(x_1, x_2, \ldots, x_n)$$

$$\text{MAD} = \text{median}(|x_i - \text{median}|)$$

$$\sigma_{\text{robust}} = 1.4826 \times \text{MAD}$$

Hệ số `1.4826` là hằng số chuẩn hóa để MAD tương đương độ lệch chuẩn với phân phối chuẩn.

**Điều kiện chấp nhận baseline**:
- `MAD(yaw) ≤ 12°` (đầu không xoay nhiều lúc bình thường)
- `MAD(gaze_x) ≤ 0.15` (mắt không nhìn lệch nhiều)

Nếu vượt ngưỡng → reset và hiệu chuẩn lại.

### 4.2. Z-score & phát hiện lệch

Sau hiệu chuẩn, mỗi frame mới được chuẩn hóa:

$$\Delta_k = x_k - \text{baseline}_k$$

$$z_k = \frac{|\Delta_k|}{\sigma_{\text{robust},k}}$$

**Quy tắc "supported"** (cần nhiều bằng chứng cùng lúc):

$$\text{supported} = (\text{head} \land \text{eye}) \lor \text{extreme\_head} \lor \text{vertical}$$

Trong đó:
- `head`: `|Δyaw| > max(18°, 3σ_yaw)` — đầu xoay đáng kể
- `eye`: `|Δgaze_x| > max(0.12, 3σ_gaze_x)` **AND** mắt mở — mắt nhìn lệch
- `extreme_head`: `|Δyaw| > max(35°, 4σ_yaw)` — đầu quay rất mạnh
- `vertical`: `|Δpitch| > max(22°, 3σ_pitch)` **AND** `|Δgaze_y| > max(0.15, 3σ_gaze_y)` — nhìn xuống (chỉ khi tắt "cho phép giở giấy nháp")

### 4.3. Bộ lọc thời gian (Temporal filtering)

Hai bộ lọc exponential moving average với half-life khác nhau:

**Short-term** (phản ứng nhanh, half-life = 0.7s):

$$a = 1 - e^{-\ln(2) \cdot \Delta t / T_{\text{short}}}$$

$$\text{short}_{t+1} = \text{short}_t + a \cdot (\text{target} - \text{short}_t)$$

**Long-term** (tích lũy, half-life = 23.1s):

$$\text{long}_{t+1} = \text{long}_t \cdot e^{-\ln(2) \cdot \Delta t / T_{\text{long}}}$$

**Target** (ngưỡng hóa):

$$\text{target} = \frac{\max(0, \text{instantaneous} - 0.30)^2}{0.49}$$

**Instantaneous risk** (sigmoid):

$$\text{instantaneous} = \frac{1}{1 + e^{-(\text{strength} - 3)}}$$

trong đó `strength = max(z_yaw, z_gaze_x)` (hoặc thêm `z_pitch`, `z_gaze_y` nếu vertical).

### 4.4. Điểm hành vi (Risk score)

$$R = 100 \times \text{clip}(0.15 \cdot I + 0.55 \cdot I \cdot S + 0.30 \cdot L)$$

Trong đó:
- `I` = instantaneous risk
- `S` = short-term EMA
- `L` = long-term EMA
- `clip(x)` = giới hạn trong [0, 1]

**Ngưỡng cảnh báo động** (adaptive threshold):

Dựa trên robust stats của 20 mẫu risk gần nhất trong điều kiện "yên tĩnh":

$$\text{threshold} = \text{clip}(\text{center} + 3.2 \cdot \text{spread}, 35, 60)$$

### 4.5. Phát hiện điện thoại (Phone detection)

YOLOX-S chạy mỗi `object_interval = 0.8s` (không phải mỗi frame để tiết kiệm CPU).

**Quy tắc chống cache giả**:
- Mỗi detection phải có `phone_timestamp` mới hơn lần trước
- Khoảng cách giữa 2 mẫu phải ≤ `phone_sample_gap = 2.2s`
- Track ID phải ổn định (IoU ≥ 0.12 với detection trước)

**Điều kiện kích hoạt**:
- `phone_score ≥ 0.78` (confidence cao)
- ≥ 3 mẫu độc lập (`phone_min_hits`)
- Duy trì ≥ 2.5 giây

### 4.6. Kabsch residual (so sánh hình dạng khuôn mặt)

Dùng để phát hiện người khác (khuôn mặt khác hẳn baseline):

1. Lấy 7 điểm landmark chính: `[1, 33, 263, 61, 291, 152, 168]`
2. Trừ mean (translation invariant)
3. Chia cho norm (scale invariant)
4. SVD để tìm rotation tối ưu: `U, Σ, V^T = SVD(P^T Q)`
5. Correction để đảm bảo rotation thuộc SO(3): `det(U V^T)`
6. Residual: `√(mean((P R - Q)²))`

### 4.7. IoU (Intersection over Union)

Dùng cho tracking điện thoại giữa các frame:

$$\text{IoU}(A, B) = \frac{|A \cap B|}{|A \cup B|}$$

Nếu IoU < 0.12 với box trước → track ID mới (reset confirmation).

### 4.8. Bipartite matching (Evaluation)

Khi đánh giá precision/recall, mỗi prediction chỉ được match với 1 ground truth (và ngược lại):

1. Tạo danh sách candidate: prediction `i` có thể match truth `j` nếu `truth_j.start - tol ≤ detected_at ≤ truth_j.end + tol`
2. Sắp xếp candidate theo khoảng cách đến `start`
3. Dùng thuật toán Hungarian-like (DFS augmenting path) để tìm matching tối đa

---

## 5. Kiến trúc hệ thống

### Luồng dữ liệu (Data flow)

```
Webcam/Video
    ↓ (CAP_DSHOW, 960×540)
VideoCapture
    ↓ (mỗi 100ms = 10 FPS inference)
FaceAnalyzer (MediaPipe)
    ↓ Observation (yaw, pitch, gaze, quality)
Engine.step()
    ↓ Result (status, risk, new_events)
EvidenceRecorder
    ↓ (ring buffer 5s, AVI clip khi có event)
Store (SQLite)
    ↓
GUI (PySide6) ← Queue (thread-safe)
```

### Threading model

- **Main thread**: GUI (PySide6 event loop)
- **Runner thread** (daemon): Đọc frame, chạy inference, ghi evidence
- **Communication**: `queue.Queue(maxsize=3)` — backpressure nếu GUI chậm

### Cấu trúc thư mục dữ liệu

```
data/
├── examguard.sqlite3          # Database chính
├── cache/
│   └── matplotlib/            # Font cache
└── sessions/
    └── YYYYMMDD-HHMMSS-XXXXXX/
        ├── session.json       # Metadata
        ├── environment.json   # Phiên bản packages
        ├── observations.jsonl # Mỗi dòng = 1 frame
        ├── events.json        # Danh sách sự kiện
        ├── events.csv         # Export cho Excel
        └── evidence/
            ├── <event_id>.avi
            └── <event_id>.json  # Sidecar với source timestamps
```

### Schema SQLite

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created TEXT,
    source TEXT,
    folder TEXT,
    status TEXT,
    duration REAL DEFAULT 0,
    config TEXT  -- JSON
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT,           -- phone|multiple_faces|look_away|face_absent|poor_quality
    start REAL,          -- giây
    detected_at REAL,
    end REAL,
    reason TEXT,
    peak_score REAL,
    review TEXT DEFAULT 'pending',  -- pending|confirmed|false_positive|uncertain
    note TEXT DEFAULT '',
    clip TEXT,
    clip_status TEXT DEFAULT 'pending',
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY,
    event_id TEXT,
    created TEXT,
    verdict TEXT,
    note TEXT
);
```

---

## 6. Hướng dẫn cài đặt

### Yêu cầu hệ thống

- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.12 (chỉ cần khi chạy từ source)
- **Webcam**: Bất kỳ webcam USB tương thích DirectShow
- **RAM**: ≥ 4 GB (khuyến nghị 8 GB)
- **CPU**: Bất kỳ CPU x64 hiện đại (chạy inference trên CPU, không cần GPU)
- **Dung lượng**: ~500 MB cho bundle .exe

### Cài đặt từ source

```cmd
SETUP.cmd
```

Script này sẽ:
1. Tạo virtual environment `.runtime\`
2. Cài đặt từ `requirements.txt`
3. Tải models (~40 MB) vào `models\`
4. Chạy `doctor` để kiểm tra

### Cài đặt từ .exe đã build

1. Copy thư mục `dist\ExamGuard\` đến máy đích
2. Double-click `ExamGuard.exe`
3. Lần đầu chạy sẽ tạo `data\` cùng thư mục

---

## 7. Hướng dẫn sử dụng

### 7.1. Khởi động

Double-click `START.cmd` (hoặc `ExamGuard.exe`).

### 7.2. Thiết lập trước khi thi

1. **Chọn nguồn quan sát**:
   - `Webcam trực tiếp` + chọn camera index (0 = mặc định)
   - `Video có sẵn` + chọn file MP4/AVI/MOV/MKV

2. **Cấu hình**:
   - ☑ **Cho phép cầm viết giấy nháp**: Bật nếu thí sinh được dùng giấy nháp (mặc định: bật)
   - ☑ **Lưu clip quanh sự kiện**: Bật để có bằng chứng video (mặc định: bật)
   - ☑ **Đã thông báo việc giám sát**: **BẮT BUỘC** đánh dấu trước khi bắt đầu

3. **Bắt đầu phiên**: Click `Bắt đầu phiên`

### 7.3. Hiệu chuẩn (30 giây đầu)

- Thí sinh nhìn màn hình, làm bài bình thường
- Không nói chuyện, không nhìn sang bên
- Thanh tiến trình sẽ chạy từ 0% → 100%
- Khi đạt 100%, hệ thống bắt đầu giám sát thực sự

### 7.4. Theo dõi thời gian thực

**Các chỉ số trên dashboard**:
- **Thời gian nguồn**: Thời gian thực từ video
- **Điểm hành vi**: 0-100 (càng cao = càng đáng ngờ)
- **Sự kiện**: Số cảnh báo đã phát hiện
- **Chất lượng**: "Đủ rõ" hoặc "Cần chỉnh"

**Trạng thái** (badge màu):
- 🟢 **ĐANG GIÁM SÁT**: Bình thường
- 🔵 **ĐANG HIỆU CHỈNH**: Đang học baseline
- 🟡 **ĐANG XÁC NHẬN**: Có tín hiệu đáng ngờ, chờ xác nhận
- 🟠 **CẦN XEM LẠI**: Có sự kiện cần giám thị xem
- 🔴 **THIẾU DỮ LIỆU**: Camera/ảnh có vấn đề

### 7.5. Xem lại sự kiện

1. Chuyển sang tab **Sự kiện & xem lại**
2. Chọn session từ dropdown
3. Double-click vào sự kiện → mở dialog xem clip
4. Xem clip, đọc lý do, chọn đánh giá:
   - **Sự kiện đúng**: Xác nhận có gian lận
   - **Báo nhầm**: Hệ thống sai
   - **Chưa rõ**: Cần thêm thông tin
5. Ghi chú (tùy chọn) → Lưu

### 7.6. Xuất báo cáo

Click `Xuất CSV` → chọn vị trí lưu → file CSV sẽ có:
- Thời điểm phát hiện
- Loại sự kiện
- Đánh giá của giám thị
- Đường dẫn clip
- Ghi chú

**Lưu ý bảo mật CSV**: Các ghi chú bắt đầu bằng `=`, `+`, `-`, `@` sẽ được escape tự động để tránh Excel formula injection.

### 7.7. Kết thúc phiên

Click `Kết thúc và lưu` → hệ thống sẽ:
1. Đóng tất cả clip đang ghi
2. Cập nhật database
3. Xuất `events.csv` và `events.json`

---

## 8. Hướng dẫn đánh giá (Evaluation)

### 8.1. Tạo template nhãn

```cmd
.runtime\Scripts\python.exe -m examguard label-template data\sessions\<session_id> --output labels.json
```

Mở `labels.json` và điền:
- `subject_id`: Mã ẩn danh của thí sinh
- `complete`: `true` (chỉ sau khi xem hết video)
- `events`: Danh sách `[{"kind": "phone", "start": 10, "end": 15}, ...]`

### 8.2. Chạy evaluation

```cmd
.runtime\Scripts\python.exe -m examguard evaluate data\sessions\<session_id> labels.json --output result.json
```

### 8.3. Đọc kết quả

```json
{
  "true_positive": 5,
  "false_positive": 2,
  "false_negative": 1,
  "precision": 0.714,
  "recall": 0.833,
  "false_alerts_per_monitored_hour": 2.0,
  "median_latency_seconds": 1.2,
  "per_kind": {
    "phone": {"precision": 1.0, "recall": 0.8, ...},
    "multiple_faces": {...},
    "look_away": {...}
  }
}
```

**Giải thích**:
- **Precision**: Trong các cảnh báo, bao nhiêu % là đúng
- **Recall**: Trong các sự kiện thật, bao nhiêu % được phát hiện
- **False alerts/hour**: Tần suất báo nhầm
- **Median latency**: Độ trễ trung vị từ lúc bắt đầu đến lúc cảnh báo

---

## 9. Hướng dẫn đóng gói .exe

### Build

```cmd
BUILD.cmd
```

Quy trình:
1. Xóa `build\` và `dist\` cũ
2. Chạy PyInstaller với `examguard.spec`
3. Verify models có trong bundle
4. Output: `dist\ExamGuard\ExamGuard.exe`

### Cấu trúc output

```
dist\ExamGuard\
├── ExamGuard.exe              # 4.7 MB
└── _internal\                 # 426 MB
    ├── models\
    │   ├── face_landmarker.task
    │   ├── yolox.onnx
    │   └── manifest.json
    ├── PySide6\               # Qt plugins
    ├── *.pyd, *.dll           # Python + native
    └── ...
```

### Phân phối

- Copy toàn bộ thư mục `dist\ExamGuard\` (không chỉ file .exe)
- Hoặc nén thành ZIP và gửi
- Người dùng chỉ cần giải nén và chạy `ExamGuard.exe`

### Tùy chỉnh spec

Mở `examguard.spec` để:
- Thêm icon: `icon='path/to/icon.ico'`
- Đổi tên: `name='ExamGuard_v2'`
- Thêm/bớt hidden imports
- Loại trừ modules không cần thiết (đã tối ưu sẵn)

---

## 10. Giới hạn & lưu ý đạo đức

### Giới hạn kỹ thuật

1. **Chỉ phát hiện trong khung hình camera**: Điện thoại nằm ngoài khung → không phát hiện
2. **Không nhận diện danh tính**: Không biết thí sinh nào đang gian lận (cần kết hợp với danh sách phòng thi)
3. **Không phân tích màn hình**: Không phát hiện tra cứu Google, copy-paste
4. **Không ghi âm**: Chỉ video, không có audio
5. **Phụ thuộc chất lượng camera**: Ánh sáng kém, mặt nhỏ → giảm độ chính xác
6. **Model phone chưa được huấn luyện riêng cho phòng thi**: Có thể báo nhầm với vật dụng khác

### Lưu ý đạo đức & pháp lý

⚠️ **BẮT BUỘC**:

1. **Thông báo trước**: Thí sinh phải biết họ đang được giám sát (có checkbox trong app)
2. **Đồng thuận**: Nên có văn bản đồng thuận từ thí sinh/phụ huynh
3. **Minh bạch**: Clip chỉ dùng để xem xét, không công khai
4. **Quyết định cuối cùng thuộc về con người**: AI chỉ hỗ trợ, giám thị quyết định
5. **Bảo mật dữ liệu**: Dữ liệu lưu local, không upload. Cần bảo vệ máy cài đặt
6. **Tuân thủ pháp luật**: Tùy quốc gia, có thể cần tuân thủ GDPR, luật bảo vệ dữ liệu cá nhân

### Khuyến nghị sử dụng

- ✅ Dùng như **công cụ hỗ trợ**, không thay thế giám thị
- ✅ Kết hợp với **camera tổng quan** của phòng thi
- ✅ **Hiệu chỉnh đúng cách** (30 giây đầu rất quan trọng)
- ✅ **Xem lại clip** trước khi đưa ra quyết định kỷ luật
- ❌ Không dùng clip làm bằng chứng duy nhất
- ❌ Không tự động trừ điểm dựa trên cảnh báo AI

---

## Phụ lục: Tham khảo

### Tài liệu kỹ thuật

- MediaPipe Face Landmarker: https://developers.google.com/mediapipe/solutions/vision/face_landmarker
- YOLOX: https://github.com/Megvii-BaseDetection/YOLOX
- OpenCV DNN: https://docs.opencv.org/4.x/d2/d58/tutorial_table_of_content_dnn.html
- PySide6: https://doc.qt.io/qtforpython-6/

### Thuật toán

- Kabsch algorithm: https://en.wikipedia.org/wiki/Kabsch_algorithm
- MAD (Median Absolute Deviation): https://en.wikipedia.org/wiki/Median_absolute_deviation
- Bipartite matching: https://en.wikipedia.org/wiki/Matching_(graph_theory)

### Liên hệ & đóng góp

- Báo lỗi: Tạo issue kèm `data\startup_error.txt` hoặc `data\last_error.txt`
- Đóng góp: Fork, sửa, gửi pull request
- Email: [Thêm email của bạn]

---

**Phiên bản tài liệu**: 1.0  
**Cập nhật lần cuối**: 2026  
**Tác giả**: ExamGuard Team