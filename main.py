"""Desktop mail widget: Usagi + speech bubble next to mail list.
Pinned under other windows, draggable, per-monitor-layout position."""
import glob
import os
import random
import sys
import threading
import webbrowser
from datetime import datetime

import win32con
import win32gui
from PyQt5.QtCore import QObject, QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAction, QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from mail import BASE_DIR, fetch_all, load_config, save_config

DARK_BG = QColor(20, 20, 20, 210)
TEXT = "#E8E8E8"
DIM = "#888888"
FONT = "맑은 고딕"
WIDTH = 360          # mail panel
SIDE = 150           # usagi column
NAMES = {"naver": "네이버", "gmail": "Gmail"}
ALLOWED_URLS = ("https://mail.naver.com/", "https://mail.google.com/")
DRAG_THRESHOLD = 5
ASSET_DIR = os.path.join(BASE_DIR, "assets", "private")

# {n}: new mail count, {u}: unread count. Edit freely.
PHRASES = {
    "new": ["우라! 새 메일 {n}통!", "야하! 메일 왔다!", "푸루루루! 새 메일 {n}통!"],
    "unread": ["훙? 안 읽은 메일 {u}통", "하아… {u}통이나 남았어", "우라? 읽어줘!"],
    "idle": ["푸루루루…", "야하~", "훙~ 조용하다"],
    "error": ["하아?! 연결이 안 돼", "우라?! 메일함이 안 열려"],
}


# ---------------------------------------------------------------- pure logic (tested in test_mail.py)

def mood(new_count, unread_count, has_error):
    if new_count:
        return "new"
    if has_error:
        return "error"
    return "unread" if unread_count else "idle"


def pick_image(files, state, exclude=None):
    """Random '<state>_*' file; falls back to 'idle_*', then any file. None if no files."""
    by = lambda s: [f for f in files if os.path.basename(f).startswith(s + "_")]
    pool = by(state) or by("idle") or list(files)
    if len(pool) > 1 and exclude in pool:
        pool.remove(exclude)
    return random.choice(pool) if pool else None


def count_new(prev_max, items):
    """Mails with UID above the previous max. prev_max None (first fetch) -> 0."""
    if prev_max is None:
        return 0
    return sum(1 for it in items if it["uid"] > prev_max)


# ---------------------------------------------------------------- image helpers

def load_sprite(path, size=SIDE):
    """Scale, then make the white background transparent (flood fill from the edges only,
    so white inside the character, like eye highlights, is kept)."""
    img = QImage(path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    seen = set()
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        seen.add((x, y))
        c = QColor(img.pixel(x, y))
        if min(c.red(), c.green(), c.blue()) < 225:  # hit the outline / body
            continue
        img.setPixel(x, y, 0)
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return QPixmap.fromImage(img)


class _Signals(QObject):
    fetched = pyqtSignal(dict)


class Bubble(QWidget):
    TAIL = 12

    def __init__(self):
        super().__init__()
        self.setFixedWidth(SIDE)
        self._text = ""

    def set_text(self, text):
        self._text = text
        fm = QFontMetrics(QFont(FONT, 10, QFont.Bold))
        r = fm.boundingRect(0, 0, SIDE - 24, 1000, Qt.TextWordWrap, text)
        self.setFixedHeight(r.height() + 20 + self.TAIL)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = QRectF(1, 1, self.width() - 2, self.height() - self.TAIL - 2)
        path = QPainterPath()
        path.addRoundedRect(body, 14, 14)
        cx = body.center().x()
        tail = QPainterPath()
        tail.moveTo(cx - 10, body.bottom() - 1)
        tail.lineTo(cx, self.height() - 1)
        tail.lineTo(cx + 10, body.bottom() - 1)
        path = path.united(tail)
        p.setBrush(QColor("#FFFDF5"))
        p.setPen(QPen(QColor("#222222"), 2))
        p.drawPath(path)
        p.setPen(QColor("#222222"))
        p.setFont(QFont(FONT, 10, QFont.Bold))
        p.drawText(body.adjusted(10, 8, -10, -8), Qt.AlignCenter | Qt.TextWordWrap, self._text)


class Panel(QWidget):
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(DARK_BG))
        p.setPen(QPen(QColor(80, 80, 80, 180), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)


class MailWidget(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.cfg.setdefault("positions", {})
        self._data = {name: [] for name in cfg["accounts"]}  # last good items per account
        self._max_uid = {}       # account -> highest UID seen
        self._new_count = 0      # stays until user clicks a mail or Usagi
        self._errors = {}
        self._state = None
        self._image = None
        self._sprites = {}       # path -> QPixmap cache
        self._busy = False
        self._press_pos = None
        self._drag_offset = None
        self.menu = None         # set by main(): same menu as tray, opened by right-click
        self._sig = _Signals()
        self._sig.fetched.connect(self._on_fetched)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        side = QVBoxLayout()
        side.setSpacing(2)
        side.addStretch()
        self._bubble = Bubble()
        side.addWidget(self._bubble)
        self._usagi = QLabel()
        self._usagi.setFixedWidth(SIDE)
        self._usagi.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self._usagi.setCursor(Qt.PointingHandCursor)
        self._usagi.setProperty("usagi", True)
        side.addWidget(self._usagi)
        root.addLayout(side)

        self._panel = Panel()
        self._panel.setFixedWidth(WIDTH)
        root.addWidget(self._panel, 0, Qt.AlignBottom)
        self._layout = QVBoxLayout(self._panel)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(3)
        self._status = self._label("로딩 중...", 8, color=DIM)

        btn = QPushButton("↻", self._panel)  # absolute position: survives layout rebuilds
        btn.setFixedSize(22, 22)
        btn.move(WIDTH - 14 - 22, 8)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("지금 새로고침")
        btn.setStyleSheet(
            f"QPushButton {{ color: {TEXT}; background: transparent; border: 1px solid #555; border-radius: 11px; font-size: 13px; }}"
            "QPushButton:hover { background: rgba(255,255,255,30); }"
        )
        btn.clicked.connect(self.refresh)

        self._render()
        self._update_usagi(force=True)
        pos = self._load_position()
        self.move(pos["x"], pos["y"])
        self.refresh()

    # ---------------------------------------------------------------- monitor (same as notion-widget)

    @staticmethod
    def _monitor_key():
        screens = sorted(QApplication.screens(), key=lambda s: s.geometry().x())
        return "|".join(
            f"{g.width()}x{g.height()}@{g.x()},{g.y()}" for g in (s.geometry() for s in screens)
        )

    def _load_position(self):
        saved = self.cfg["positions"].get(self._monitor_key())
        if saved:
            return saved
        primary = QApplication.primaryScreen().geometry()
        return {"x": primary.x() + 40, "y": primary.y() + 80}

    def _save_position(self):
        self.cfg["positions"][self._monitor_key()] = {"x": self.x(), "y": self.y()}
        save_config(self.cfg)

    def on_screen_change(self):
        QTimer.singleShot(1500, self._reposition)  # wait for Windows to re-layout screens

    def _reposition(self):
        pos = self._load_position()
        self.move(pos["x"], pos["y"])
        self._pin_to_desktop()

    def _pin_to_desktop(self):
        win32gui.SetWindowPos(
            int(self.winId()), win32con.HWND_BOTTOM, 0, 0, 0, 0,
            win32con.SWP_NOACTIVATE | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._pin_to_desktop()

    # ---------------------------------------------------------------- usagi

    def _unread_count(self):
        return sum(it["unread"] for items in self._data.values() for it in items)

    def _update_usagi(self, force=False):
        """Change image + phrase only when the state changes (or forced by click/startup)."""
        unread = self._unread_count()
        state = mood(self._new_count, unread, bool(self._errors))
        if state == self._state and not force:
            return
        self._state = state
        files = sorted(glob.glob(os.path.join(ASSET_DIR, "*.png")))
        self._image = pick_image(files, state, exclude=self._image)
        if self._image:
            if self._image not in self._sprites:
                self._sprites[self._image] = load_sprite(self._image)
            self._usagi.setPixmap(self._sprites[self._image])
        self._bubble.set_text(random.choice(PHRASES[state]).format(n=self._new_count, u=unread))
        self.adjustSize()

    def _acknowledge(self):
        self._new_count = 0
        self._update_usagi(force=True)

    # ---------------------------------------------------------------- list UI

    @staticmethod
    def _label(text, size=10, bold=False, color=TEXT):
        lb = QLabel(text)
        lb.setTextFormat(Qt.PlainText)  # mail text is untrusted: never render as HTML
        lb.setFont(QFont(FONT, size, QFont.Bold if bold else QFont.Normal))
        lb.setStyleSheet(f"color: {color}; background: transparent;")
        return lb

    def _render(self):
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w and w is not self._status:
                w.deleteLater()
        fm_width = WIDTH - 28
        for name, items in self._data.items():
            head = NAMES.get(name, name)
            if name in self._errors:
                head += "  ⚠ 연결 실패"
            hl = self._label(head, 11, bold=True)
            if name in self._errors:
                hl.setToolTip(self._errors[name])
            self._layout.addWidget(hl)
            if not items and name not in self._errors:
                self._layout.addWidget(self._label("  메일 없음", 9, color=DIM))
            for it in items:
                font = QFont(FONT, 10, QFont.Bold if it["unread"] else QFont.Normal)
                text = ("● " if it["unread"] else "   ") + it["subject"]
                text = QFontMetrics(font).elidedText(text, Qt.ElideRight, fm_width)
                lb = self._label(text, 10, bold=it["unread"], color=TEXT if it["unread"] else DIM)
                lb.setToolTip(f"{it['subject']}\n{it['sender']}\n{it['date']}")
                lb.setCursor(Qt.PointingHandCursor)
                lb.setProperty("url", it["url"])
                self._layout.addWidget(lb)
            self._layout.addSpacing(6)
        self._layout.addWidget(self._status)
        self._panel.adjustSize()
        self.adjustSize()

    # ---------------------------------------------------------------- data

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        self._status.setText("새로고침 중...")
        threading.Thread(target=lambda: self._sig.fetched.emit(fetch_all(self.cfg)), daemon=True).start()

    def _on_fetched(self, result):
        self._busy = False
        self._errors = {}
        for name, items in result.items():
            if isinstance(items, str):
                self._errors[name] = items  # keep previous items
                continue
            self._new_count += count_new(self._max_uid.get(name), items)
            if items:
                self._max_uid[name] = max(self._max_uid.get(name, 0), max(it["uid"] for it in items))
            self._data[name] = items
        self._render()
        self._status.setText(f"{datetime.now():%H:%M} 기준" + ("  · 일부 실패" if self._errors else ""))
        self._update_usagi()
        self._pin_to_desktop()

    # ---------------------------------------------------------------- mouse: drag vs click

    def contextMenuEvent(self, e):
        if self.menu:
            self.menu.exec_(e.globalPos())
            self._pin_to_desktop()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_pos = e.globalPos()
            self._drag_offset = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() == Qt.LeftButton:
            if (e.globalPos() - self._press_pos).manhattanLength() >= DRAG_THRESHOLD:
                self.move(e.globalPos() - self._drag_offset)

    def mouseReleaseEvent(self, e):
        if self._press_pos is None:
            return
        moved = (e.globalPos() - self._press_pos).manhattanLength() >= DRAG_THRESHOLD
        if moved:
            self._save_position()
        else:
            child = self.childAt(e.pos())
            url = child.property("url") if child else None
            if isinstance(url, str) and url.startswith(ALLOWED_URLS):
                webbrowser.open(url)
                self._acknowledge()
            elif child is self._usagi:
                self._acknowledge()
                self.refresh()
        self._press_pos = self._drag_offset = None
        self._pin_to_desktop()


def _tray_icon():
    px = QPixmap(64, 64)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#F2C94C"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, 64, 64)
    p.setPen(QPen(QColor("#333333"), 5))
    p.setBrush(Qt.NoBrush)
    p.drawRect(14, 20, 36, 24)
    p.drawPolyline(QPoint(14, 20), QPoint(32, 34), QPoint(50, 20))
    p.end()
    return QIcon(px)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config()
    w = MailWidget(cfg)
    w.show()

    timer = QTimer()
    timer.timeout.connect(w.refresh)
    timer.start(cfg.get("refresh_seconds", 180) * 1000)

    tray = QSystemTrayIcon(_tray_icon(), app)
    tray.setToolTip("usagi-mail")
    menu = QMenu()
    menu.setStyleSheet(
        "QMenu { background: #1e1e1e; color: #e8e8e8; border: 1px solid #444; font-family: 맑은 고딕; font-size: 10pt; }"
        "QMenu::item:selected { background: #3a3a3a; }"
        "QMenu::separator { height: 1px; background: #444; margin: 4px 0; }"
    )
    act_toggle = QAction("위젯 숨기기", app)

    def toggle():
        w.setVisible(not w.isVisible())
        act_toggle.setText("위젯 숨기기" if w.isVisible() else "위젯 보이기")

    act_toggle.triggered.connect(toggle)
    menu.addAction(act_toggle)
    act_refresh = QAction("지금 새로고침", app)
    act_refresh.triggered.connect(w.refresh)
    menu.addAction(act_refresh)
    menu.addSeparator()
    act_quit = QAction("종료", app)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    w.menu = menu
    tray.activated.connect(lambda r: toggle() if r == QSystemTrayIcon.DoubleClick else None)
    tray.show()

    app.screenAdded.connect(lambda _: w.on_screen_change())
    app.screenRemoved.connect(lambda _: w.on_screen_change())
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
