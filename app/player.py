"""Built-in viewer: plays video & audio and shows images inside Maria Free Download."""
import os

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSlider, QStyle, QVBoxLayout, QWidget)

from i18n import T

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".3gp", ".ts", ".mpg", ".mpeg"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac", ".wma"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".ico", ".tif", ".tiff"}

STYLE = """
QDialog { background: #111418; }
QLabel { color: #e5e7eb; }
QPushButton { color: #fff; background: #1f2933; border: 1px solid #334155; border-radius: 6px;
              padding: 6px 12px; }
QPushButton:hover { background: #0e7490; border-color: #0e7490; }
QSlider::groove:horizontal { height: 5px; background: #334155; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #22a6c3; border-radius: 2px; }
QSlider::handle:horizontal { background: #fff; width: 13px; height: 13px; margin: -5px 0; border-radius: 6px; }
QScrollArea { background: #111418; border: none; }
"""


def media_kind(path):
    ext = os.path.splitext(path or "")[1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    return None


def fmt_ms(ms):
    s = max(0, int(ms // 1000))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class MediaViewer(QDialog):
    def __init__(self, parent, path, open_external):
        super().__init__(parent)
        self.path = path
        self.kind = media_kind(path)
        self.open_external = open_external
        self.setWindowTitle(f"{os.path.basename(path)} – {T('Media Player')}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(STYLE)
        self.resize(960, 600)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)
        self.player = None
        if self.kind == "image":
            self._build_image()
        else:
            self._build_av()
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._escape)
        QShortcut(QKeySequence(Qt.Key_F), self, activated=self.toggle_fullscreen)

    # ------------------------------------------------------------- images
    def _build_image(self):
        self.pixmap = QPixmap(self.path)
        self.fit = True
        self.img = QLabel(alignment=Qt.AlignCenter)
        self.img.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.img)
        self.scroll.setWidgetResizable(True)
        self.lay.addWidget(self.scroll, 1)
        bar = self._bar()
        self.fit_btn = QPushButton(T("Actual size"))
        self.fit_btn.clicked.connect(self._toggle_fit)
        info = QLabel(f"{self.pixmap.width()} × {self.pixmap.height()}")
        bar.addWidget(info)
        bar.addStretch()
        bar.addWidget(self.fit_btn)
        self._add_common_buttons(bar)
        if self.pixmap.isNull():
            QTimer.singleShot(0, self._cannot_play)
        QTimer.singleShot(0, self._render_image)

    def _toggle_fit(self):
        self.fit = not self.fit
        self.fit_btn.setText(T("Actual size") if self.fit else T("Fit"))
        self.scroll.setWidgetResizable(self.fit)
        self._render_image()

    def _render_image(self):
        if self.pixmap.isNull():
            return
        if self.fit:
            area = self.scroll.viewport().size()
            pm = self.pixmap
            if pm.width() > area.width() or pm.height() > area.height():
                pm = pm.scaled(area, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img.setPixmap(pm)
        else:
            self.img.setPixmap(self.pixmap)
            self.img.resize(self.pixmap.size())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.kind == "image":
            self._render_image()

    # ------------------------------------------------------------- audio / video
    def _build_av(self):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)

        if self.kind == "video":
            self.video = QVideoWidget()
            self.video.setStyleSheet("background: black")
            self.video.mouseDoubleClickEvent = lambda e: self.toggle_fullscreen()
            self.player.setVideoOutput(self.video)
            self.lay.addWidget(self.video, 1)
        else:
            self.resize(620, 300)
            art = QLabel("♫", alignment=Qt.AlignCenter)
            art.setStyleSheet("font-size: 96px; color: #22a6c3;")
            name = QLabel(os.path.basename(self.path), alignment=Qt.AlignCenter)
            name.setWordWrap(True)
            name.setStyleSheet("font-size: 15px; padding: 0 20px 10px;")
            box = QWidget()
            v = QVBoxLayout(box)
            v.addStretch()
            v.addWidget(art)
            v.addWidget(name)
            v.addStretch()
            self.lay.addWidget(box, 1)

        # seek bar
        seek_row = QHBoxLayout()
        seek_row.setContentsMargins(12, 8, 12, 0)
        self.pos_label = QLabel("00:00")
        self.dur_label = QLabel("00:00")
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player.setPosition)
        seek_row.addWidget(self.pos_label)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.dur_label)
        w = QWidget()
        w.setLayout(seek_row)
        self.lay.addWidget(w)

        bar = self._bar()
        st = self.style()
        self.play_btn = QPushButton()
        self.play_btn.setIcon(st.standardIcon(QStyle.SP_MediaPause))
        self.play_btn.setIconSize(QSize(20, 20))
        self.play_btn.clicked.connect(self.toggle_play)
        back = QPushButton("-10s")
        back.clicked.connect(lambda: self.player.setPosition(max(0, self.player.position() - 10000)))
        fwd = QPushButton("+10s")
        fwd.clicked.connect(lambda: self.player.setPosition(self.player.position() + 10000))
        vol_icon = QLabel("🔊")
        vol_icon.setToolTip(T("Volume"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.setFixedWidth(110)
        self.vol.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        bar.addWidget(back)
        bar.addWidget(self.play_btn)
        bar.addWidget(fwd)
        bar.addSpacing(12)
        bar.addWidget(vol_icon)
        bar.addWidget(self.vol)
        bar.addStretch()
        if self.kind == "video":
            fs = QPushButton(T("Fullscreen"))
            fs.clicked.connect(self.toggle_fullscreen)
            bar.addWidget(fs)
        self._add_common_buttons(bar)

        self.player.durationChanged.connect(self._duration)
        self.player.positionChanged.connect(self._position)
        self.player.playbackStateChanged.connect(self._state)
        self.player.errorOccurred.connect(lambda *a: self._cannot_play())
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.toggle_play)
        QShortcut(QKeySequence(Qt.Key_Right), self,
                  activated=lambda: self.player.setPosition(self.player.position() + 5000))
        QShortcut(QKeySequence(Qt.Key_Left), self,
                  activated=lambda: self.player.setPosition(max(0, self.player.position() - 5000)))

        self.player.setSource(QUrl.fromLocalFile(self.path))
        self.player.play()

    def _duration(self, d):
        self.seek.setRange(0, d)
        self.dur_label.setText(fmt_ms(d))

    def _position(self, p):
        if not self.seek.isSliderDown():
            self.seek.setValue(p)
        self.pos_label.setText(fmt_ms(p))

    def _state(self, s):
        from PySide6.QtMultimedia import QMediaPlayer
        icon = QStyle.SP_MediaPause if s == QMediaPlayer.PlayingState else QStyle.SP_MediaPlay
        self.play_btn.setIcon(self.style().standardIcon(icon))

    def toggle_play(self):
        from PySide6.QtMultimedia import QMediaPlayer
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    # ------------------------------------------------------------- shared
    def _bar(self):
        row = QHBoxLayout()
        row.setContentsMargins(12, 8, 12, 10)
        w = QWidget()
        w.setLayout(row)
        self.lay.addWidget(w)
        return row

    def _add_common_buttons(self, bar):
        ext = QPushButton(T("Open with default program"))
        ext.clicked.connect(lambda: self.open_external(self.path))
        close = QPushButton(T("Close"))
        close.clicked.connect(self.close)
        bar.addWidget(ext)
        bar.addWidget(close)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _escape(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.close()

    def _cannot_play(self):
        if getattr(self, "_asked", False):
            return
        self._asked = True
        r = QMessageBox.question(self, T("Media Player"),
                                 T("This file can't be played here. Open it with the default program?"))
        if r == QMessageBox.Yes:
            self.open_external(self.path)
        self.close()

    def closeEvent(self, e):
        if self.player:
            self.player.stop()
        super().closeEvent(e)
