import ctypes
import json
import math
import random
import sys
import time
import traceback
from dataclasses import dataclass, asdict, fields
from pathlib import Path

if getattr(sys, "frozen", False):
    RESOURCES = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent
    RESOURCES = APP_DIR
ASSETS = RESOURCES / "assets"
SETTINGS_PATH = APP_DIR / "settings.json"
ERROR_LOG = APP_DIR / "error.log"


def fatal(title, detail=""):
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S\n") + title + "\n" + detail + "\n\n")
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(0, title + "\n\n" + detail[-1500:],
                                             "Epsilon Desktop Pet", 0x10)
        else:
            print(title + "\n" + detail)
    except Exception:
        pass


try:
    from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QRect
    from PyQt6.QtGui import (QAction, QColor, QCursor, QFont, QIcon, QImage, QPainter,
                             QPainterPath, QPen, QPixmap)
    from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget
except Exception:
    fatal("Failed to load PyQt6.", traceback.format_exc())
    sys.exit(1)

try:
    from PIL import Image, ImageChops
except Exception:
    fatal("Failed to load Pillow (pip install Pillow).", "")
    sys.exit(1)

IS_WIN = sys.platform == "win32"

if IS_WIN:
    user32 = ctypes.windll.user32
    _get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    _set_style = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    _get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _get_style.restype = ctypes.c_ssize_t
    _set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    _set_style.restype = ctypes.c_ssize_t

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def no_focus(widget):
    if not IS_WIN:
        return
    try:
        hwnd = ctypes.c_void_p(int(widget.winId()))
        style = _get_style(hwnd, GWL_EXSTYLE)
        if not (style & WS_EX_NOACTIVATE):
            _set_style(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:
        pass


def desktop_rect():
    r = QRect()
    for screen in QApplication.screens():
        r = r.united(screen.geometry())
    return r


def to_pixmap(img, dpr=1.0):
    img = img.convert("RGBA")
    qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height,
                  img.width * 4, QImage.Format.Format_RGBA8888).copy()
    pm = QPixmap.fromImage(qimg)
    pm.setDevicePixelRatio(dpr)
    return pm


@dataclass
class Settings:
    char_size: int = 96
    window_size: int = 170
    global_opacity: int = 100
    window_bg_opacity: int = 85
    char_opacity: int = 100
    push_force: int = 350
    fire_rate: int = 6
    friction: int = 15
    max_speed: int = 900
    bullet_speed: int = 520
    cursor_gap: int = 120
    follow_cursor: bool = True
    show_bullets: bool = True

    LIMITS = {
        "char_size": (16, 256), "window_size": (90, 500), "global_opacity": (10, 100),
        "window_bg_opacity": (0, 100), "char_opacity": (10, 100), "push_force": (50, 1500),
        "fire_rate": (1, 20), "friction": (2, 60), "max_speed": (200, 2500),
        "bullet_speed": (300, 2500), "cursor_gap": (0, 400),
    }

    def clamp(self):
        dfl = Settings()
        for name, (lo, hi) in self.LIMITS.items():
            try:
                v = int(round(float(getattr(self, name))))
            except Exception:
                v = getattr(dfl, name)
            setattr(self, name, max(lo, min(hi, v)))

    @classmethod
    def load(cls):
        s = cls()
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return s
        for fld in fields(cls):
            if fld.name in data:
                try:
                    val = data[fld.name]
                    cur = getattr(s, fld.name)
                    if isinstance(cur, bool):
                        val = val if isinstance(val, bool) else str(val).lower() in ("1", "true")
                    else:
                        val = type(cur)(val)
                    setattr(s, fld.name, val)
                except Exception:
                    pass
        s.clamp()
        return s

    def save(self):
        try:
            SETTINGS_PATH.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


_img_cache = {}


def load_png(name):
    if name not in _img_cache:
        _img_cache[name] = Image.open(ASSETS / name).convert("RGBA")
    return _img_cache[name]


def tint(img, rgb):
    img = img.convert("RGBA")
    alpha = img.getchannel("A")
    lum = img.convert("L")
    visible = Image.composite(lum, Image.new("L", lum.size, 0), alpha)
    hi = visible.getextrema()[1] or 255
    if hi < 8:
        hi = 255
    r, g, b = rgb
    chans = [lum.point(lambda v, k=k: min(255, v * 255 // hi) * k // 255) for k in (r, g, b)]
    return Image.merge("RGBA", (*chans, alpha))


def char_sprite(px):
    key = ("char", px)
    if key not in _img_cache:
        base = Image.alpha_composite(load_png("basic_fill.png"), load_png("basic_outline.png"))
        if px != base.width:
            base = base.resize((px, px), Image.LANCZOS)
        _img_cache[key] = base
    return _img_cache[key]


def expand_alpha(alpha, px):
    if px <= 0:
        return alpha
    out = alpha
    steps = max(12, px * 10)
    for i in range(steps):
        ang = 2 * math.pi * i / steps
        dx, dy = int(round(math.cos(ang) * px)), int(round(math.sin(ang) * px))
        out = ImageChops.lighter(out, ImageChops.offset(alpha, dx, dy))
    return out


def bullet_sprite(scale=1.0):
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    OUTLINE_PX = 2
    key = ("bullet", round(scale, 2))
    if key not in _img_cache:
        img = tint(load_png("bullet.png"), WHITE)
        if scale != 1.0:
            img = img.resize((max(4, int(img.width * scale)),
                              max(3, int(img.height * scale))), Image.LANCZOS)
        margin = OUTLINE_PX + 1
        canvas = Image.new("RGBA", (img.width + 2 * margin, img.height + 2 * margin),
                           (0, 0, 0, 0))
        canvas.paste(img, (margin, margin))
        ring = Image.new("RGBA", canvas.size, (*BLACK, 255))
        ring.putalpha(expand_alpha(canvas.getchannel("A"), OUTLINE_PX))
        _img_cache[key] = Image.alpha_composite(ring, canvas)
    return _img_cache[key]


def wall_ray(dx, dy, half):
    if abs(dx) > 1e-9:
        tx = half / dx if dx > 0 else -half / dx
    else:
        tx = float("inf")
    if abs(dy) > 1e-9:
        ty = half / dy if dy > 0 else -half / dy
    else:
        ty = float("inf")
    if tx <= ty:
        return max(tx, 0.0), (1.0 if dx > 0 else -1.0, 0.0)
    return max(ty, 0.0), (0.0, 1.0 if dy > 0 else -1.0)


@dataclass
class Bullet:
    ox: float
    oy: float
    dx: float
    dy: float
    speed: float
    t: float = 0.0
    t_hit: float = 0.0
    nx: float = 0.0
    ny: float = 0.0
    push: float = 0.0

    @property
    def x(self):
        return self.ox + self.dx * self.speed * self.t

    @property
    def y(self):
        return self.oy + self.dy * self.speed * self.t

    def angle(self):
        return math.degrees(math.atan2(self.dy, self.dx))


class Body:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.pend_x = 0.0
        self.pend_y = 0.0
        self.cool = 0.0

    @property
    def speed(self):
        return math.hypot(self.vx, self.vy)

    def hit(self, ux, uy, push):
        self.vx += ux * push
        self.vy += uy * push
        self.pend_x -= ux * push
        self.pend_y -= uy * push

    def step(self, dt, target, stop_r, cfg, bounds):
        shots = []
        push = float(max(1, cfg.push_force))
        rate = max(1, cfg.fire_rate)
        self.cool -= dt
        near = False

        if target is not None:
            tx = min(max(target[0], bounds[0]), bounds[2])
            ty = min(max(target[1], bounds[1]), bounds[3])
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            remain = max(dist - stop_r, 0.0)
            accel = push * rate * 0.6

            if remain > 0.5 and dist > 1e-6:
                ax, ay = dx / dist, dy / dist
                sp = min(float(cfg.max_speed), math.sqrt(2.0 * accel * remain))
                vx_ideal, vy_ideal = ax * sp, ay * sp
                ex = vx_ideal - (self.vx + self.pend_x)
                ey = vy_ideal - (self.vy + self.pend_y)
                if ex * ax + ey * ay > 0.5 * push and self.cool <= 0.0:
                    shots.append((ax, ay))
                    self.pend_x += ax * push
                    self.pend_y += ay * push
                    self.cool = (1.0 / rate) * random.uniform(0.85, 1.15)

                ex, ey = vx_ideal - self.vx, vy_ideal - self.vy
                par = ex * ax + ey * ay
                brake_x = ex - max(par, 0.0) * ax
                brake_y = ey - max(par, 0.0) * ay
                self._brake(brake_x, brake_y, accel * dt)
            else:
                self._brake(-self.vx, -self.vy, accel * dt)
            near = remain < 40.0

        fric = cfg.friction / 10.0
        if near and self.speed < push:
            fric *= 4.0
        decay = math.exp(-fric * dt)
        self.vx *= decay
        self.vy *= decay

        self.x += self.vx * dt
        self.y += self.vy * dt

        if self.x < bounds[0]:
            self.x, self.vx = bounds[0], abs(self.vx) * 0.45
        elif self.x > bounds[2]:
            self.x, self.vx = bounds[2], -abs(self.vx) * 0.45
        if self.y < bounds[1]:
            self.y, self.vy = bounds[1], abs(self.vy) * 0.45
        elif self.y > bounds[3]:
            self.y, self.vy = bounds[3], -abs(self.vy) * 0.45
        return shots

    def _brake(self, fx, fy, max_dv):
        m = math.hypot(fx, fy)
        if m > 1e-6 and max_dv > 0:
            f = min(m, max_dv) / m
            self.vx += fx * f
            self.vy += fy * f


class MascotWin(QWidget):
    def __init__(self, ctrl):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.ctrl = ctrl
        self.drag_off = None
        self.close_rect = QRectF()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

    def apply_cfg(self):
        self.setFixedSize(self.ctrl.cfg.window_size, self.ctrl.cfg.window_size)
        self.setWindowOpacity(self.ctrl.cfg.global_opacity / 100.0)
        self.update()

    def paintEvent(self, ev):
        cfg = self.ctrl.cfg
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(self.width() / 2.0, self.height() / 2.0)
        half = cfg.window_size / 2.0

        body = QPainterPath()
        body.addRoundedRect(QRectF(-half, -half, cfg.window_size, cfg.window_size), 8, 8)
        bg_op = cfg.window_bg_opacity / 100.0
        bg = QColor(27, 27, 36)
        bg.setAlpha(int(255 * bg_op))
        p.setPen(QPen(QColor(255, 255, 255, int(60 + 195 * bg_op)), 1.5))
        p.setBrush(bg)
        p.drawPath(body)

        self.close_rect = QRectF(half - 24, -half, 24, 24)
        p.setPen(QColor(255, 255, 255, 210))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(self.close_rect, Qt.AlignmentFlag.AlignCenter, "×")

        size = int(max(8, min(cfg.char_size, cfg.window_size - 16)))
        pm = self.ctrl.get_char_sprite(size, self.devicePixelRatioF())
        p.save()
        p.setOpacity(cfg.char_opacity / 100.0)
        p.drawPixmap(QPointF(-size / 2, -size / 2), pm)
        p.restore()

        bullet_pm = self.ctrl.bullet_pix
        if cfg.show_bullets and bullet_pm is not None and self.ctrl.bullets:
            bw = bullet_pm.width() / bullet_pm.devicePixelRatio()
            bh = bullet_pm.height() / bullet_pm.devicePixelRatio()
            p.save()
            p.setClipRect(QRectF(-half + 1, -half + 1, cfg.window_size - 2, cfg.window_size - 2))
            for b in self.ctrl.bullets:
                p.save()
                p.translate(b.x, b.y)
                p.rotate(b.angle())
                p.drawPixmap(QPointF(-bw / 2, -bh / 2), bullet_pm)
                p.restore()
            p.restore()

    def in_close(self, pos):
        return pos - QPointF(self.width() / 2.0, self.height() / 2.0)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self.close_rect.contains(self.in_close(ev.position())):
                self.ctrl.quit()
                return
            self.drag_off = ev.globalPosition() - QPointF(self.pos())
            self.ctrl.drag_start()
        elif ev.button() == Qt.MouseButton.RightButton:
            self.ctrl.show_menu(ev.globalPosition().toPoint())

    def mouseMoveEvent(self, ev):
        if self.drag_off is not None and (ev.buttons() & Qt.MouseButton.LeftButton):
            tl = ev.globalPosition() - self.drag_off
            self.ctrl.drag_to(tl.x() + self.width() / 2, tl.y() + self.height() / 2)

    def mouseReleaseEvent(self, ev):
        if self.drag_off is not None:
            self.drag_off = None
            self.ctrl.drag_end()

    def mouseDoubleClickEvent(self, ev):
        self.ctrl.toggle_follow()


class Ctrl:
    TICK_MS = 16

    def __init__(self, app):
        self.app = app
        self.cfg = Settings.load()
        self.bullets = []
        self.dragging = False
        self._geom = None
        self.bullet_pix = None
        self._sprite_cache = {}

        center = QApplication.primaryScreen().geometry().center()
        self.body = Body(center.x(), center.y())
        self.win = MascotWin(self)

        icon = QIcon(to_pixmap(char_sprite(64)))
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("Epsilon Desktop Pet")
        self.tray.setContextMenu(self._menu())
        self.tray.activated.connect(
            lambda reason: self.toggle_follow()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

        self.save_later = QTimer()
        self.save_later.setSingleShot(True)
        self.save_later.setInterval(500)
        self.save_later.timeout.connect(self.cfg.save)

        self.apply_cfg()
        self.win.show()
        no_focus(self.win)
        self.win.raise_()

        self.last = time.perf_counter()
        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(self.TICK_MS)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def _menu(self):
        menu = QMenu()
        self.act_follow = QAction("Follow cursor", menu, checkable=True)
        self.act_follow.setChecked(self.cfg.follow_cursor)
        self.act_follow.triggered.connect(lambda _=False: self.toggle_follow())
        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(self.quit)
        menu.addAction(self.act_follow)
        menu.addSeparator()
        menu.addAction(quit_act)
        self.menu = menu
        return menu

    def show_menu(self, pos):
        self.menu.exec(pos)

    def apply_cfg(self, save=True):
        cfg = self.cfg
        scale = max(0.6, min(cfg.char_size, cfg.window_size) / 64.0 * 0.8)
        self.bullet_pix = to_pixmap(bullet_sprite(scale))
        geom = (cfg.window_size, cfg.char_size)
        if geom != self._geom:
            self._geom = geom
            self.clear_bullets()
        self.win.apply_cfg()
        if self.act_follow.isChecked() != cfg.follow_cursor:
            self.act_follow.setChecked(cfg.follow_cursor)
        if save:
            self.save_later.start()

    def toggle_follow(self):
        self.cfg.follow_cursor = not self.cfg.follow_cursor
        self.apply_cfg()

    def clear_bullets(self):
        self.bullets.clear()
        self.body.pend_x = self.body.pend_y = 0.0

    def drag_start(self):
        self.dragging = True
        self.body.vx = self.body.vy = 0.0
        self.clear_bullets()

    def drag_to(self, cx, cy):
        self.body.x = cx
        self.body.y = cy
        self.body.vx = self.body.vy = 0.0
        self.win.move(round(cx - self.win.width() / 2), round(cy - self.win.height() / 2))

    def drag_end(self):
        self.dragging = False

    def quit(self):
        self.cfg.save()
        self.tray.hide()
        self.app.quit()

    def get_char_sprite(self, px, dpr):
        px4 = max(4, int(round(px * dpr)))
        pm = self._sprite_cache.get(px4)
        if pm is None:
            if len(self._sprite_cache) > 40:
                self._sprite_cache.clear()
            pm = to_pixmap(char_sprite(px4), dpr)
            self._sprite_cache[px4] = pm
        return pm

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self.last, 0.05)
        self.last = now
        cfg = self.cfg
        body = self.body

        desk = desktop_rect()
        half = cfg.window_size / 2.0
        bounds = (desk.left() + half, desk.top() + half,
                  desk.right() - half, desk.bottom() - half)
        if bounds[0] > bounds[2]:
            bounds = (desk.center().x(), bounds[1], desk.center().x(), bounds[3])
        if bounds[1] > bounds[3]:
            bounds = (bounds[0], desk.center().y(), bounds[2], desk.center().y())

        target = None
        stop_r = 0.0
        if cfg.follow_cursor and not self.dragging:
            c = QCursor.pos()
            target = (c.x(), c.y())
            stop_r = float(cfg.cursor_gap)

        if target is not None:
            for ux, uy in body.step(dt, target, stop_r, cfg, bounds):
                self.shoot(ux, uy)
        else:
            body.step(dt, None, stop_r, cfg, bounds)

        for b in self.bullets:
            b.t += dt
        landed = [b for b in self.bullets if b.t >= b.t_hit]
        if landed:
            self.bullets = [b for b in self.bullets if b.t < b.t_hit]
            for b in landed:
                body.hit(b.dx, b.dy, b.push)

        if not self.dragging:
            self.win.move(round(body.x - self.win.width() / 2),
                          round(body.y - self.win.height() / 2))
        self.win.update()

    def shoot(self, ux, uy):
        cfg = self.cfg
        half = cfg.window_size / 2.0
        ang = math.atan2(uy, ux) + math.radians(random.uniform(-1.5, 1.5))
        dx, dy = math.cos(ang), math.sin(ang)
        muzzle = min(cfg.char_size * 0.38, half * 0.6)
        t_wall, (nx, ny) = wall_ray(dx, dy, half)
        travel = max(t_wall - muzzle, 1.0)
        speed = float(max(50, cfg.bullet_speed))
        self.bullets.append(Bullet(dx * muzzle, dy * muzzle, dx, dy, speed,
                                   0.0, travel / speed, nx, ny, float(cfg.push_force)))
        if len(self.bullets) > 60:
            self.clear_bullets()


def main():
    needed = ["basic_fill.png", "basic_outline.png", "bullet.png"]
    missing = [name for name in needed if not (ASSETS / name).exists()]
    if missing:
        fatal("Missing images: " + ", ".join(missing), "Searched: " + str(ASSETS))
        sys.exit(1)

    def log_error(kind, value, tb):
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S\n")
                        + "".join(traceback.format_exception(kind, value, tb)) + "\n")
        except Exception:
            pass

    sys.excepthook = log_error

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    try:
        ctrl = Ctrl(app)  # noqa: F841
    except Exception:
        fatal("Startup failed.", traceback.format_exc())
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
