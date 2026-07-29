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
STEP_R_DEG = 10.0           # Sudut jog sumbu R per klik (derajat)  <-- TAMBAHAN BARU
DEFAULT_VELOCITY = 100.0    
DEFAULT_ACCELERATION = 100.0
CONVEYOR_SPEED = 0.5        # Kecepatan default conveyor (0.0 - 1.0)
RECONNECT_INTERVAL_S = 5    
HOMING_DURATION_S = 20       # Jeda tunggu setelah home() dikirim ke Dobot (detik)

PORT_HINT_KEYWORDS = ["dobot", "cp210", "ch340", "silicon labs", "usb-serial", "usb serial"]
PORT_CONNECT_MAX_ATTEMPTS = 2      
PORT_CONNECT_RETRY_DELAY_S = 0.8   

# Pemetaan perintah dari frontend JavaScript (axis, direction) ke arah gerak relatif (dx, dy, dz, dr)
AXIS_DIRECTIONS = {
    ("x", "forward"):          (+1, 0, 0, 0),   # Sumbu X Maju
    ("x", "backward"):         (-1, 0, 0, 0),   # Sumbu X Mundur
    ("y", "left"):             (0, -1, 0, 0),   # Sumbu Y Kiri
    ("y", "right"):            (0, +1, 0, 0),   # Sumbu Y Kanan
    ("z", "up"):               (0, 0, +1, 0),   # Sumbu Z Naik
    ("z", "down"):             (0, 0, -1, 0),   # Sumbu Z Turun
    ("r", "clockwise"):        (0, 0, 0, +1),   # Rotasi R Searah Jarum Jam      <-- TAMBAHAN BARU
    ("r", "counterclockwise"): (0, 0, 0, -1),   # Rotasi R Berlawanan Arah     <-- TAMBAHAN BARU
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

    def _list_candidate_ports(self):
        ports = list(list_ports.comports())
        hinted, others = [], []
        for p in ports:
            text = f"{p.description or ''} {p.manufacturer or ''}".lower()
            if any(k in text for k in PORT_HINT_KEYWORDS):
                hinted.append(p.device)
            else:
                others.append(p.device)
        return hinted + others

    def _attempt_connect_port(self, port: str):
        for attempt in range(1, PORT_CONNECT_MAX_ATTEMPTS + 1):
            device = None
            try:
                log.info("Mencoba menghubungkan ke Dobot di %s (percobaan %d)...", port, attempt)
                device = Dobot(port=port)
                device.speed(DEFAULT_VELOCITY, DEFAULT_ACCELERATION)
                return device
            except Exception as exc:
                log.warning("Gagal konek ke %s (percobaan %d): [%s] %r",
                            port, attempt, type(exc).__name__, str(exc))
                if device is not None:
                    try:
                        device.close()
                    except Exception:
                        try:
                            device._ser.close()
                        except Exception:
                            pass
                time.sleep(PORT_CONNECT_RETRY_DELAY_S)
        return None

    def connect(self, port: Optional[str] = None) -> bool:
        with self._lock:
            if Dobot is None:
                self.state.last_error = "pydobotplus belum terinstall"
                log.error(self.state.last_error)
                return False

            if self._device is not None:
                self.disconnect()

            candidates = [port] if port else self._list_candidate_ports()
            if not candidates:
                self.state.last_error = ("Tidak ada serial port terdeteksi sama sekali. "
                                          "Pastikan kabel USB Dobot terpasang.")
                log.warning(self.state.last_error)
                return False

            log.info("Port kandidat yang akan dicoba: %s", candidates)

            device = None
            connected_port = None
            for candidate_port in candidates:
                device = self._attempt_connect_port(candidate_port)
                if device is not None:
                    connected_port = candidate_port
                    break

            if device is None:
                self.state.connected = False
                self.state.last_error = (
                    f"Dobot tidak ditemukan/gagal dikonek di {len(candidates)} "
                    f"port yang dicoba: {candidates}"
                )
                log.warning(self.state.last_error)
                return False

            self._device = device
            actual_port = connected_port
            try:
                actual_port = self._device._ser.port
            except Exception:
                pass

            self.state.connected = True
            self.state.port = actual_port
            self.state.last_error = None
            self._refresh_pose_locked()
            log.info("Dobot terhubung di %s", actual_port)

        if not self.state.homed:
            try:
                self.home()
            except Exception as exc:
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

        log.info("Menunggu homing selesai (%d detik)...", HOMING_DURATION_S)
        time.sleep(HOMING_DURATION_S)

        with self._lock:
            self.state.homing = False
            if not self.state.connected:
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

            dx, dy, dz, dr = AXIS_DIRECTIONS[key]
            
            # Tentukan besaran step masing-masing sumbu
            if axis == "z":
                step_val = STEP_Z_MM
            elif axis == "r":
                step_val = STEP_R_DEG
            else:
                step_val = STEP_XY_MM

            try:
                self._device.move_rel(
                    x=dx * (step_val if axis == "x" else 0), 
                    y=dy * (step_val if axis == "y" else 0), 
                    z=dz * (step_val if axis == "z" else 0), 
                    r=dr * (step_val if axis == "r" else 0), 
                    wait=True
                )
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