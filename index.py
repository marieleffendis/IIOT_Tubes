import os
import time
import logging
import threading
from dataclasses import dataclass, asdict
from typing import Optional

from flask import Flask, jsonify, request, send_from_directory
from serial.tools import list_ports

try:
    from pydobotplus import Dobot
except ImportError:
    Dobot = None  # Backend tetap bisa jalan untuk testing UI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dobot-backend")

# ---------------------------------------------------------------------------
# Konfigurasi Gerak
# ---------------------------------------------------------------------------
STEP_XY_MM = 20.0           # Jarak jog sumbu X & Y per klik (mm)
STEP_Z_MM = 20.0            # Jarak jog sumbu Z per klik (mm)
DEFAULT_VELOCITY = 100.0    
DEFAULT_ACCELERATION = 100.0
CONVEYOR_SPEED = 0.5        # Kecepatan default conveyor (0.0 - 1.0)
RECONNECT_INTERVAL_S = 5    
HOMING_DURATION_S = 20       # Jeda tunggu setelah home() dikirim ke Dobot (detik)

# Pemetaan perintah dari frontend JavaScript ke arah gerak relatif (dx, dy, dz)
# Sesuaikan teks key ini jika label di tombol HTML Anda berbeda.
# Pemetaan perintah dari frontend JavaScript (axis, direction) ke arah gerak relatif (dx, dy, dz)
AXIS_DIRECTIONS = {
    ("x", "forward"):  (+1, 0, 0),   # Sumbu X Maju
    ("x", "backward"): (-1, 0, 0),   # Sumbu X Mundur
    ("y", "left"):     (0, +1, 0),   # Sumbu Y Kiri
    ("y", "right"):    (0, -1, 0),   # Sumbu Y Kanan
    ("z", "up"):       (0, 0, +1),   # Sumbu Z Naik
    ("z", "down"):     (0, 0, -1),   # Sumbu Z Turun
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")


# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------
@dataclass
class DobotState:
    connected: bool = False
    port: Optional[str] = None
    pose: Optional[dict] = None
    suction: bool = False
    conveyor: bool = False
    homed: bool = False
    homing: bool = False
    last_error: Optional[str] = None


class DobotManager:
    """Membungkus interaksi ke Dobot Magician secara thread-safe."""

    def __init__(self):
        self._device = None
        self._lock = threading.RLock()
        self.state = DobotState()

    def list_ports(self):
        return [p.device for p in list_ports.comports()]

    def connect(self, port: Optional[str] = None) -> bool:
        with self._lock:
            if Dobot is None:
                self.state.last_error = "pydobotplus belum terinstall"
                log.error(self.state.last_error)
                return False

            if self._device is not None:
                self.disconnect()

            try:
                log.info("Menghubungkan ke Dobot%s...", f" di {port}" if port else " (auto-detect)")
                self._device = Dobot(port=port)
                self._device.speed(DEFAULT_VELOCITY, DEFAULT_ACCELERATION)

                actual_port = port
                try:
                    actual_port = self._device._ser.port
                except Exception:
                    pass

                self.state.connected = True
                self.state.port = actual_port
                self.state.last_error = None
                self._refresh_pose_locked()
                log.info("Dobot terhubung di %s", actual_port)
            except Exception as exc:
                self._device = None
                self.state.connected = False
                self.state.last_error = f"Gagal terhubung: {exc}"
                log.warning(self.state.last_error)
                return False

        # Homing fisik HANYA dijalankan SEKALI selama proses backend ini hidup,
        # persis seperti pola HMI.py -> Main.py: dipicu otomatis tepat setelah
        # koneksi pertama kali berhasil (mis. saat aplikasi pertama dibuka).
        # Dijalankan DI LUAR lock (di atas) supaya /api/status tetap bisa
        # dipoll frontend untuk menampilkan progress selama ~20 detik ini.
        # Kalibrasi ini dianggap tetap valid di firmware Dobot selama proses
        # backend tidak restart / power Dobot tidak mati, sehingga aksi jog,
        # suction, conveyor (mode Manual & Auto) tidak perlu homing ulang.
        if not self.state.homed:
            try:
                self.home()
            except Exception as exc:
                # Koneksi tetap dianggap berhasil walau homing awal gagal;
                # bisa dipicu ulang manual lewat POST /api/home.
                log.warning("Homing otomatis gagal: %s", exc)

        return True

    def disconnect(self):
        with self._lock:
            if self._device is not None:
                try:
                    self._device.close()
                except Exception as exc:
                    log.warning("Error saat menutup koneksi: %s", exc)
            self._device = None
            self.state.connected = False
            self.state.pose = None

    def _refresh_pose_locked(self):
        pos = self._device.get_pose().position
        self.state.pose = {
            "x": round(pos.x, 2),
            "y": round(pos.y, 2),
            "z": round(pos.z, 2),
            "r": round(pos.r, 2),
        }

    def _ensure_connected(self):
        if not self.state.connected or self._device is None:
            raise RuntimeError("Dobot belum terhubung")

    def _mark_disconnected(self, exc: Exception):
        log.warning("Koneksi ke Dobot terputus: %s", exc)
        self._device = None
        self.state.connected = False
        self.state.last_error = str(exc)

    def home(self, force: bool = False) -> bool:
        """
        Menjalankan proses homing fisik Dobot (~20 detik).

        PENTING: homing di sini HANYA dijalankan sekali selama proses backend
        ini hidup (dipicu otomatis oleh connect() saat koneksi pertama kali
        berhasil). Ini supaya endpoint lain (jog, suction, conveyor -- mode
        Manual & Auto) tidak perlu mengulang homing setiap kali dipanggil.
        Kalibrasi homing tetap tersimpan di firmware Dobot selama tidak mati
        listrik / proses backend tidak di-restart.

        Set force=True (mis. lewat POST /api/home {"force": true}) untuk
        memaksa homing ulang, misalnya jika robot dicurigai kehilangan
        kalibrasi karena tersenggol atau kabel sempat lepas.
        """
        with self._lock:
            self._ensure_connected()

            if self.state.homed and not force:
                log.info("Homing dilewati: robot sudah pernah di-home pada sesi ini.")
                return True

            self.state.homing = True
            self.state.last_error = None
            try:
                log.info("Memulai proses Homing. Pastikan area sekitar robot KOSONG!")
                self._device.home()
            except Exception as exc:
                self.state.homing = False
                self._mark_disconnected(exc)
                raise

        # Jeda manual DI LUAR lock, supaya /api/status tetap responsif dan bisa
        # dipoll frontend untuk menampilkan progress ("homing": true) selama
        # proses ini berlangsung.
        log.info("Menunggu homing selesai (%d detik)...", HOMING_DURATION_S)
        time.sleep(HOMING_DURATION_S)

        with self._lock:
            self.state.homing = False
            if not self.state.connected:
                # Koneksi sempat putus selagi menunggu homing selesai.
                return False
            self.state.homed = True
            try:
                self._refresh_pose_locked()
            except Exception as exc:
                self._mark_disconnected(exc)
                raise
            log.info("Homing selesai, siap menjalankan conveyor / aksi sortir!")
            return True

    def jog(self, axis: str, direction: str):
        """Menggerakkan lengan berdasarkan parameter axis dan direction dari frontend."""
        with self._lock:
            self._ensure_connected()
            key = (axis, direction)
            if key not in AXIS_DIRECTIONS:
                raise ValueError(f"Perintah tidak dikenal: {key}")

            dx, dy, dz = AXIS_DIRECTIONS[key]
            step = STEP_Z_MM if axis == "z" else STEP_XY_MM

            try:
                self._device.move_rel(x=dx * step, y=dy * step, z=dz * step, r=0, wait=True)
                self._refresh_pose_locked()
            except Exception as exc:
                self._mark_disconnected(exc)
                raise
            return self.state.pose

    def set_suction(self, enable: bool):
        with self._lock:
            self._ensure_connected()
            try:
                self._device.suck(enable)
            except Exception as exc:
                self._mark_disconnected(exc)
                raise
            self.state.suction = enable
            return self.state.suction

    def set_conveyor(self, enable: bool, speed: float = CONVEYOR_SPEED):
        with self._lock:
            self._ensure_connected()
            try:
                self._device.conveyor_belt(speed=speed if enable else 0.0, direction=1)
            except Exception as exc:
                self._mark_disconnected(exc)
                raise
            self.state.conveyor = enable
            return self.state.conveyor

    def get_status(self):
        with self._lock:
            if self.state.connected:
                try:
                    self._refresh_pose_locked()
                except Exception as exc:
                    self._mark_disconnected(exc)
            return asdict(self.state)


manager = DobotManager()


def background_autoconnect():
    preferred_port = os.environ.get("DOBOT_PORT")
    while True:
        if not manager.state.connected:
            manager.connect(preferred_port)
        time.sleep(RECONNECT_INTERVAL_S)


# ---------------------------------------------------------------------------
# Flask Routes (API Endpoints)
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "Index.html")


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(manager.get_status())


@app.route("/api/ports", methods=["GET"])
def api_ports():
    return jsonify({"ports": manager.list_ports()})


@app.route("/api/connect", methods=["POST"])
def api_connect():
    body = request.get_json(silent=True) or {}
    ok = manager.connect(body.get("port"))
    return jsonify(manager.get_status()), (200 if ok else 503)


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    manager.disconnect()
    return jsonify(manager.get_status())


@app.route("/api/home", methods=["POST"])
def api_home():
    """
    Trigger homing manual (opsional).
    Body JSON: {"force": true} -> paksa homing ulang meski status.homed sudah True.
    Dalam pemakaian normal endpoint ini tidak wajib dipanggil, karena homing
    pertama sudah otomatis terjadi saat koneksi pertama berhasil (lihat
    DobotManager.connect). Sediakan ini untuk kasus robot dicurigai
    kehilangan kalibrasi tanpa perlu restart backend.
    """
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force", False))
    try:
        ok = manager.home(force=force)
        return jsonify({"ok": ok, **manager.get_status()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/jog", methods=["POST"])
def api_jog():
    body = request.get_json(silent=True) or {}
    axis = body.get("axis")         
    direction = body.get("direction") 
    try:
        pose = manager.jog(axis, direction)
        return jsonify({"ok": True, "pose": pose})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/suction", methods=["POST"])
def api_suction():
    body = request.get_json(silent=True) or {}
    try:
        state = manager.set_suction(bool(body.get("state", False)))
        return jsonify({"ok": True, "suction": state})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/conveyor", methods=["POST"])
def api_conveyor():
    body = request.get_json(silent=True) or {}
    try:
        state = manager.set_conveyor(
            bool(body.get("state", False)),
            float(body.get("speed", CONVEYOR_SPEED)),
        )
        return jsonify({"ok": True, "conveyor": state})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


if __name__ == "__main__":
    threading.Thread(target=background_autoconnect, daemon=True).start()
    try:
        app.run(host="0.0.0.0", port=5000, threaded=True)
    finally:
        manager.disconnect()