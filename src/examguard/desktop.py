from pathlib import Path
from dataclasses import replace
import json
import queue
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QComboBox, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget, QDialog, QTextEdit, QDialogButtonBox, QScrollArea,
    QAbstractItemView,
)

from . import __version__
from .config import Config
from .engine import LABELS
from .runner import Runner
from .storage import Store

STATUS = {
    'normal': ('ĐANG GIÁM SÁT', '#52d9b0'),
    'calibrating': ('ĐANG HIỆU CHỈNH', '#78b5fa'),
    'observing': ('ĐANG XÁC NHẬN', '#eac56d'),
    'review': ('CẦN XEM LẠI', '#f2ac6d'),
    'unavailable': ('THIẾU DỮ LIỆU', '#e7aaab'),
}
REVIEWS = {'pending':'Chưa xem', 'confirmed':'Sự kiện đúng', 'false_positive':'Báo nhầm', 'uncertain':'Chưa rõ'}
STYLE = '''
QWidget { background: #101923; color: #e6edf4; font-family: "Segoe UI"; font-size: 13px; }
QMainWindow { background: #101923; }
QFrame#sidebar { background: #15212d; border-right: 1px solid #283846; }
QFrame#card { background: #192632; border: 1px solid #2b3d4c; border-radius: 10px; }
QLabel { background: transparent; }
QLabel#muted { color: #9cafc0; }
QLabel#title { font-size: 26px; font-weight: 650; }
QLabel#number { font-size: 27px; font-weight: 650; }
QPushButton { background: #233747; border: 1px solid #395164; border-radius: 7px; padding: 10px 14px; }
QPushButton:hover { background: #304a5e; }
QPushButton:disabled { color: #738594; background: #192732; border-color: #283b49; }
QPushButton#primary { background: #54d6b0; border-color: #54d6b0; color: #102720; font-weight: 700; }
QPushButton#primary:hover { background: #78e7c5; }
QComboBox, QSpinBox, QTextEdit { background: #101923; border: 1px solid #3b5062; padding: 8px; border-radius: 5px; }
QComboBox QAbstractItemView { background: #1c2c3a; selection-background-color: #32516a; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QProgressBar { background: #253747; border: none; border-radius: 4px; min-height: 8px; max-height: 8px; }
QProgressBar::chunk { background: #54d6b0; border-radius: 4px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 12px 22px; color: #9cafc0; border-bottom: 2px solid #263747; }
QTabBar::tab:selected { color: #64dfbc; border-bottom: 2px solid #64dfbc; }
QTableWidget { background: #15212d; border: 1px solid #283e4e; border-radius: 6px; gridline-color: #243645; selection-background-color: #2a465b; }
QHeaderView::section { background: #1d2c39; color: #a9bed0; border: 0; padding: 10px; }
QScrollArea { border: none; }
QToolTip { background: #243b4e; color: white; border: 1px solid #46667d; }
'''


def text_label(text, name=None, wrap=False):
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def pixmap_from_bgr(frame):
    import cv2
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(image)


def clock_text(seconds):
    seconds = max(0, int(seconds or 0))
    return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'


class ReviewDialog(QDialog):
    def __init__(self, event, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Xem bằng chứng • ExamGuard')
        self.resize(800, 680)
        self.event, self.store = event, store
        self.capture = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        layout = QVBoxLayout(self)
        layout.addWidget(text_label(LABELS.get(event['kind'], event['kind']), 'title'))
        layout.addWidget(text_label(f"Phát hiện {clock_text(event['detected_at'])} · {event['reason']}", 'muted', True))
        self.preview = QLabel('Chưa có clip bằng chứng')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(640, 300)
        self.preview.setStyleSheet('background:#080e14;border-radius:8px;')
        layout.addWidget(self.preview, 1)
        self.play = QPushButton('Phát lại clip')
        self.play.clicked.connect(self.replay)
        layout.addWidget(self.play)
        status = event.get('clip_status', '')
        if status == 'partial_session_ended':
            layout.addWidget(text_label('Clip thiếu phần sau vì phiên đã kết thúc.', 'muted'))
        elif status not in ('ready',):
            layout.addWidget(text_label(f'Trạng thái bằng chứng: {status}', 'muted'))
        self.verdict = QComboBox()
        for key, label in REVIEWS.items():
            self.verdict.addItem(label, key)
        self.verdict.setCurrentIndex(max(0, self.verdict.findData(event.get('review', 'pending'))))
        layout.addWidget(self.verdict)
        self.note = QTextEdit(event.get('note', ''))
        self.note.setPlaceholderText('Ghi chú của giám thị. Xác nhận sự kiện không đồng nghĩa kết luận gian lận.')
        self.note.setMaximumHeight(75)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.replay()

    def replay(self):
        import cv2
        self.timer.stop()
        if self.capture:
            self.capture.release()
            self.capture = None
        path = self.event.get('clip')
        if not path or not Path(path).exists() or self.event.get('clip_status') == 'recording':
            self.preview.setText('Clip đang ghi, đã tắt lưu, hoặc không còn trên máy.\nVẫn có thể ghi nhận đánh giá sự kiện.')
            return
        # Only clips under local session storage may be opened from database rows.
        if not Path(path).resolve().is_relative_to(self.store.root):
            self.preview.setText('Đường dẫn clip không hợp lệ.')
            return
        self.capture = cv2.VideoCapture(path)
        if not self.capture.isOpened():
            self.preview.setText('Không đọc được clip. Kiểm tra dữ liệu bằng chứng.')
            self.capture.release()
            self.capture = None
            return
        fps = self.capture.get(cv2.CAP_PROP_FPS) or 5
        self.timer.start(max(20, int(1000/fps)))
        self.next_frame()

    def next_frame(self):
        if not self.capture:
            return
        ok, frame = self.capture.read()
        if not ok:
            self.timer.stop()
            return
        self.preview.setPixmap(pixmap_from_bgr(frame).scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def save(self):
        self.store.review(self.event['id'], self.verdict.currentData(), self.note.toPlainText())
        self.accept()

    def done(self, result):
        self.timer.stop()
        if self.capture:
            self.capture.release()
        super().done(result)


class MainWindow(QMainWindow):
    def __init__(self, root, config=None):
        super().__init__()
        # Offscreen QA and restricted Windows font services need explicit fonts.
        for filename in ('segoeui.ttf', 'segoeuib.ttf'):
            font_path = Path('C:/Windows/Fonts') / filename
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))
        QApplication.instance().setFont(QFont('Segoe UI', 10))
        self.root = Path(root)
        self.base_config = config or Config()
        self.store = Store(self.root / 'data')
        self.runner = None
        self.messages = queue.Queue(maxsize=3)
        self.current_sid = None
        self.video_path = None
        self.display_events = []
        self.demo_events = []
        self.last_refresh = 0
        self.close_pending = False
        self.setWindowTitle(f'ExamGuard Local {__version__} • Hỗ trợ giám sát thi')
        self.resize(1320, 860)
        self.setMinimumSize(1080, 720)
        self.setStyleSheet(STYLE)
        container = QWidget()
        self.setCentralWidget(container)
        outer = QHBoxLayout(container)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(275)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22,28,22,22)
        side.setSpacing(14)
        brand = text_label('EXAMGUARD', 'title')
        brand.setStyleSheet('font-size:23px;letter-spacing:2px;color:#6ce0bd;')
        side.addWidget(brand)
        side.addWidget(text_label('LOCAL  /  DESKTOP', 'muted'))
        side.addSpacing(14)
        side.addWidget(text_label('NGUỒN QUAN SÁT', 'muted'))
        self.source = QComboBox()
        self.source.addItems(['Webcam trực tiếp', 'Video có sẵn'])
        side.addWidget(self.source)
        self.camera = QSpinBox()
        self.camera.setRange(0,9)
        self.camera.setPrefix('Camera số ')
        side.addWidget(self.camera)
        self.pick = QPushButton('Chọn video…')
        self.pick.clicked.connect(self.choose_video)
        self.pick.setVisible(False)
        side.addWidget(self.pick)
        self.filename = text_label('MP4 · AVI · MOV · MKV', 'muted', True)
        self.filename.setVisible(False)
        side.addWidget(self.filename)
        self.source.currentIndexChanged.connect(self.source_changed)
        side.addSpacing(6)
        self.paper = QCheckBox('Cho phép cúi viết giấy nháp')
        self.paper.setChecked(self.base_config.allow_paper)
        self.paper.setToolTip('Bật: không dùng nhìn xuống làm dấu hiệu hành vi. Điện thoại vẫn được kiểm tra.')
        side.addWidget(self.paper)
        self.record = QCheckBox('Lưu clip quanh sự kiện')
        self.record.setChecked(self.base_config.record_evidence)
        side.addWidget(self.record)
        self.consent = QCheckBox('Đã thông báo việc giám sát')
        self.consent.setToolTip('Chỉ bắt đầu khi người được quan sát đã biết việc sử dụng camera và lưu bằng chứng.')
        side.addWidget(self.consent)
        self.start = QPushButton('Bắt đầu phiên')
        self.start.setObjectName('primary')
        self.start.clicked.connect(self.start_session)
        side.addWidget(self.start)
        self.stop = QPushButton('Kết thúc và lưu')
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.stop_session)
        side.addWidget(self.stop)
        self.demo = QPushButton('Thử giao diện bằng mô phỏng')
        self.demo.clicked.connect(lambda: self.start_session(demo=True))
        side.addWidget(self.demo)
        side.addStretch()
        side.addWidget(text_label('DỮ LIỆU Ở TRÊN MÁY', 'muted'))
        side.addWidget(text_label('Không tải video lên đám mây.\nKhông tự kết luận gian lận.\nGiám thị xem và xác nhận sự kiện.', 'muted', True))
        side.addWidget(text_label(f'Phiên bản {__version__} · CPU', 'muted'))
        outer.addWidget(sidebar)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24,24,24,18)
        layout.setSpacing(15)
        top = QHBoxLayout()
        title_group = QVBoxLayout()
        title_group.addWidget(text_label('Quan sát có bằng chứng', 'title'))
        title_group.addWidget(text_label('Nhận diện sự kiện · Hạn chế báo nhầm · Giám thị xác minh', 'muted'))
        top.addLayout(title_group, 1)
        self.badge = text_label('●  CHƯA BẮT ĐẦU')
        self.badge.setStyleSheet('color:#9cafc0;font-weight:700;')
        top.addWidget(self.badge)
        layout.addLayout(top)
        cards = QHBoxLayout()
        self.metrics = {}
        for key, name, initial in [('time','THỜI GIAN NGUỒN','00:00:00'),('risk','ĐIỂM HÀNH VI','—'),('events','SỰ KIỆN','0'),('quality','CHẤT LƯỢNG','—')]:
            card = QFrame()
            card.setObjectName('card')
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16,12,16,12)
            card_layout.addWidget(text_label(name, 'muted'))
            value = text_label(initial, 'number')
            card_layout.addWidget(value)
            self.metrics[key] = value
            cards.addWidget(card)
        layout.addLayout(cards)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        live = QWidget()
        live_layout = QVBoxLayout(live)
        live_layout.setContentsMargins(0,14,0,0)
        self.preview = QLabel('Camera đang tắt\n\nChọn nguồn và bắt đầu phiên để hiệu chỉnh cá nhân.\nCó thể thử giao diện bằng dữ liệu mô phỏng trước.')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(260)
        self.preview.setStyleSheet('background:#080f17;border:1px solid #293d4d;border-radius:10px;color:#91a7ba;')
        live_layout.addWidget(self.preview, 1)
        self.instruction = text_label('Hiệu chỉnh khoảng 30 giây: đặt camera cố định, nhìn màn hình và làm bài bình thường.', 'muted', True)
        live_layout.addWidget(self.instruction)
        self.progress = QProgressBar()
        self.progress.setRange(0,100)
        self.progress.setTextVisible(False)
        live_layout.addWidget(self.progress)
        self.detail = text_label('Mô hình: MediaPipe Face Landmarker + YOLOX-S · Điểm hành vi không phải xác suất gian lận.', 'muted', True)
        live_layout.addWidget(self.detail)
        self.tabs.addTab(live, 'Quan sát')
        history = QWidget()
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(0,14,0,0)
        history_top = QHBoxLayout()
        self.sessions = QComboBox()
        self.sessions.currentIndexChanged.connect(self.select_session)
        history_top.addWidget(self.sessions, 1)
        refresh = QPushButton('Làm mới')
        refresh.clicked.connect(self.refresh_sessions)
        history_top.addWidget(refresh)
        export = QPushButton('Xuất CSV')
        export.clicked.connect(self.export)
        history_top.addWidget(export)
        history_layout.addLayout(history_top)
        self.table = QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(['Thời điểm','Sự kiện','Đánh giá','Bằng chứng'])
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.review_selected)
        history_layout.addWidget(self.table)
        review = QPushButton('Xem clip và đánh giá sự kiện đã chọn')
        review.clicked.connect(self.review_selected)
        history_layout.addWidget(review)
        history_layout.addWidget(text_label('“Sự kiện đúng” xác nhận điều quan sát được. Quyết định vi phạm thuộc về giám thị.', 'muted', True))
        self.tabs.addTab(history, 'Sự kiện & xem lại')
        guide = QTextEdit()
        guide.setReadOnly(True)
        guide.setHtml('''<h2>Bắt đầu một phiên đáng tin cậy</h2>
        <p>1. Đặt webcam cố định, thấy rõ mặt. Tránh ngược sáng, tránh người đi lại phía sau.</p>
        <p>2. Chọn đúng quy chế giấy nháp. Thông báo cho người được quan sát trước khi bắt đầu.</p>
        <p>3. Trong khoảng 30 giây hiệu chỉnh, đọc màn hình và làm bài bình thường. Đoạn mờ, nhắm mắt hoặc nhiều người không được tính.</p>
        <p>4. Điện thoại/người thứ hai cần xuất hiện ổn định. Nhìn lệch cần nhiều tín hiệu hỗ trợ và đủ thời gian.</p>
        <p>5. Vào <b>Sự kiện &amp; xem lại</b>, mở clip, đánh dấu sự kiện đúng / báo nhầm / chưa rõ.</p>
        <h3>Phạm vi và giới hạn</h3>
        <p>Đây là công cụ hỗ trợ giám thị một máy. Không nhận diện danh tính, cảm xúc, âm thanh hay màn hình khác.
        Không phát hiện được điện thoại nằm ngoài khung hình. Mô hình điện thoại phổ thông chưa được huấn luyện riêng cho phòng thi.</p>
        <p>“Thiếu dữ liệu” không có nghĩa là bình thường. Chất lượng hiển thị là kiểm tra ảnh và hình học, không phải xác suất đúng của AI.</p>
        <p>Clip lưu khoảng 5 giây trước/sau thời điểm cảnh báo; phiên kết thúc sớm có thể thiếu phần sau.
        Không lưu âm thanh. Dữ liệu nằm trong thư mục <b>data/sessions</b>. Chỉ chia sẻ khi có quyền.</p>
        <h3>Chưa có tỷ lệ false positive thực địa</h3>
        <p>Các ngưỡng là cấu hình thận trọng ban đầu. Cần video có nhãn độc lập để đánh giá precision, recall và cảnh báo giả/giờ.
        Mô phỏng giao diện không phải kết quả đánh giá nhận diện.</p>''')
        self.tabs.addTab(guide, 'Cách dùng & giới hạn')
        self.footer = text_label('Sẵn sàng · Camera chỉ mở khi anh bấm Bắt đầu phiên.', 'muted', True)
        layout.addWidget(self.footer)
        outer.addWidget(body, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(80)
        self.refresh_sessions()

    def source_changed(self, index):
        self.camera.setVisible(index == 0)
        self.pick.setVisible(index == 1)
        self.filename.setVisible(index == 1)

    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Chọn video', str(self.root), 'Video (*.mp4 *.avi *.mov *.mkv *.webm)')
        if path:
            self.video_path = path
            self.filename.setText(Path(path).name)

    def set_running(self, running):
        for widget in (self.source,self.camera,self.pick,self.paper,self.record,self.consent,self.start,self.demo):
            widget.setEnabled(not running)
        self.stop.setEnabled(running)

    def start_session(self, checked=False, demo=False):
        if self.runner and self.runner.is_alive():
            return
        if not demo and not self.consent.isChecked():
            QMessageBox.information(self, 'Thông báo giám sát', 'Đánh dấu đã thông báo việc giám sát trước khi bắt đầu.')
            return
        if not demo and self.source.currentIndex() == 1 and not self.video_path:
            self.choose_video()
            if not self.video_path:
                return
        source = self.camera.value() if self.source.currentIndex() == 0 else self.video_path
        config = replace(self.base_config, allow_paper=self.paper.isChecked(), record_evidence=self.record.isChecked())
        while not self.messages.empty():
            self.messages.get_nowait()
        self.current_sid = None
        self.demo_events.clear()
        self.metrics['events'].setText('0')
        self.progress.setValue(0)
        self.runner = Runner(source, config, self.root, self.messages, demo=demo)
        self.set_running(True)
        self.tabs.setCurrentIndex(0)
        self.footer.setText('MÔ PHỎNG • Không dùng camera, không lưu làm bằng chứng' if demo else 'Đang khởi động…')
        self.runner.start()

    def stop_session(self):
        if self.runner:
            self.runner.stop_requested.set()
            self.stop.setEnabled(False)
            self.footer.setText('Đang kết thúc và lưu clip…')

    def poll(self):
        latest = None
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break
            if message['type'] == 'frame':
                latest = message
                if message['demo']:
                    self.demo_events.extend(message['result'].new_events)
            elif message['type'] == 'loading':
                self.footer.setText(message['message'])
                self.badge.setText('●  ĐANG CHUẨN BỊ / CHỜ HÌNH')
            elif message['type'] == 'finished':
                self.set_running(False)
                self.badge.setText('●  ĐÃ KẾT THÚC')
                self.footer.setText(message.get('error') or ('Đã lưu phiên. Mở Sự kiện & xem lại để kiểm tra.' if message.get('sid') else 'Đã kết thúc mô phỏng.'))
                if message.get('error'):
                    QMessageBox.warning(self, 'Không thể tiếp tục phiên', message['error'])
                self.refresh_sessions()
                if self.close_pending:
                    QTimer.singleShot(0, self.close)
            elif message['type'] == 'error':
                self.footer.setText(message['message'])
        if latest:
            result, obs = latest['result'], latest['observation']
            self.current_sid = latest['sid']
            label, color = STATUS[result.status]
            self.badge.setText(('MÔ PHỎNG · ' if latest['demo'] else '●  ') + label)
            self.badge.setStyleSheet(f'color:{color};font-weight:700;')
            self.preview.setPixmap(pixmap_from_bgr(latest['frame']).scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.metrics['time'].setText(clock_text(result.timestamp))
            self.metrics['risk'].setText(f'{result.risk:.0f} / 100' if result.calibration >= 1 and result.status != 'unavailable' else '—')
            self.metrics['quality'].setText('Đủ rõ' if result.quality >= self.base_config.min_quality else 'Cần chỉnh')
            self.progress.setValue(int(result.calibration*100))
            self.instruction.setText(result.message + (f' · {result.calibration:.0%}' if result.calibration < 1 else ''))
            self.detail.setText(f"Khuôn mặt: {obs.face_count}  ·  Xử lý: {latest['latency_ms']:.0f} ms  ·  Bộ nhớ: {result.diagnostics['short']:.2f} / {result.diagnostics['long']:.2f}")
            active = ', '.join(LABELS[k] for k in result.active)
            self.footer.setText(('MÔ PHỎNG • ' if latest['demo'] else '') + (active or 'Chưa có sự kiện đang hoạt động') + ' · Điểm số không phải kết luận gian lận.')
            if time.monotonic()-self.last_refresh > 1:
                count = len(self.demo_events) if latest['demo'] else len(self.store.events(self.current_sid))
                self.metrics['events'].setText(str(count))
                self.refresh_events()
                self.last_refresh = time.monotonic()
        if self.runner and self.runner.is_alive() and time.monotonic()-self.runner.last_heartbeat > 4:
            self.badge.setText('●  CHỜ DỮ LIỆU MỚI')
            self.badge.setStyleSheet('color:#e7aaab;font-weight:700;')
            self.metrics['risk'].setText('—')

    def refresh_sessions(self):
        previous = self.current_sid or self.sessions.currentData()
        self.sessions.blockSignals(True)
        self.sessions.clear()
        for session in self.store.sessions():
            source = 'Webcam ' + session['source'] if session['source'].isdigit() else Path(session['source']).name
            self.sessions.addItem(f"{session['id']} · {source} · {clock_text(session['duration'])}", session['id'])
        index = self.sessions.findData(previous)
        if index >= 0:
            self.sessions.setCurrentIndex(index)
        self.sessions.blockSignals(False)
        self.refresh_events()

    def select_session(self):
        self.refresh_events()

    def refresh_events(self):
        sid = self.sessions.currentData()
        # Add live session as soon as it exists; don't wait until stopping.
        if self.current_sid and self.sessions.findData(self.current_sid) < 0:
            self.sessions.insertItem(0, self.current_sid + ' · Đang chạy', self.current_sid)
            self.sessions.setCurrentIndex(0)
            sid = self.current_sid
        self.display_events = self.store.events(sid) if sid else []
        self.table.setRowCount(len(self.display_events))
        for index, event in enumerate(self.display_events):
            clip_status = event['clip_status']
            clip_label = {'ready':'Có clip', 'recording':'Đang ghi', 'disabled':'Đã tắt lưu',
                          'partial_session_ended':'Clip chưa đủ phần sau'}.get(clip_status, clip_status)
            values = [clock_text(event['detected_at']), LABELS.get(event['kind'],event['kind']),
                      REVIEWS.get(event['review'], event['review']), clip_label]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 1:
                    item.setForeground(QColor('#f2c58a'))
                self.table.setItem(index, column, item)

    def review_selected(self, *args):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.display_events):
            return
        dialog = ReviewDialog(self.display_events[row], self.store, self)
        dialog.exec()
        self.refresh_events()

    def export(self):
        sid = self.sessions.currentData()
        if not sid:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Xuất danh sách sự kiện', str(self.root / f'{sid}.csv'), 'CSV (*.csv)')
        if path:
            self.store.export(sid, path)
            self.footer.setText(f'Đã xuất {path}')

    def closeEvent(self, event):
        if self.runner and self.runner.is_alive():
            self.close_pending = True
            self.stop_session()
            event.ignore()
        else:
            event.accept()


def launch(root, config=None):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('ExamGuard Local')
    window = MainWindow(root, config)
    window.show()
    return app.exec()
