import time
import logging
import threading
import queue
from collections import deque
from serial.tools import list_ports

import cv2
import mediapipe as mp

try:
    from pydobotplus import Dobot
except ImportError:
    Dobot = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dobot-gesture")

# ---------------------------------------------------------------------------
# Konfigurasi Koneksi Dobot
# ---------------------------------------------------------------------------
DEFAULT_VELOCITY = 100.0
DEFAULT_ACCELERATION = 100.0

# Kata kunci untuk mengenali kandidat port Dobot lebih dulu (dicoba paling awal).
# Kalau tidak ada yang cocok, semua port lain tetap akan dicoba juga.
PORT_HINT_KEYWORDS = ["dobot", "cp210", "ch340", "silicon labs", "usb-serial", "usb serial"]

# ---------------------------------------------------------------------------
# Konfigurasi Gerak & Dobot
# ---------------------------------------------------------------------------
STEP_XY_MM = 20.0
STEP_Z_MM = 20.0
CONVEYOR_SPEED = 0.5

COMMAND_COOLDOWN_S = 0.4
RECONNECT_INTERVAL_S = 5   # jeda antar percobaan auto-reconnect saat koneksi putus

GESTURE_TO_JOG = {
    "Gerakan ke Kiri":  ("y", "left"),
    "Gerakan ke Kanan": ("y", "right"),
    "Gerakan ke Atas":  ("z", "up"),
    "Gerakan ke Bawah": ("z", "down"),
}

AXIS_DIRECTIONS = {
    ("x", "forward"):  (+1, 0, 0),
    ("x", "backward"): (-1, 0, 0),
    ("y", "left"):     (0, +1, 0),
    ("y", "right"):    (0, -1, 0),
    ("z", "up"):       (0, 0, +1),
    ("z", "down"):     (0, 0, -1),
}

# ---------------------------------------------------------------------------
# Konfigurasi Zona Navigasi (5 jari) -- dengan Hysteresis
# ---------------------------------------------------------------------------
ZONE = {
    "left":   {"enter": 0.30, "exit": 0.36},   # wrist_x < enter -> masuk KIRI
    "right":  {"enter": 0.70, "exit": 0.64},   # wrist_x > enter -> masuk KANAN
    "top":    {"enter": 0.55, "exit": 0.62},   # wrist_y < enter -> masuk ATAS
    "bottom": {"enter": 0.75, "exit": 0.68},   # wrist_y > enter -> masuk BAWAH
}

SMOOTHING_WINDOW = 5   # jumlah frame terakhir yang dirata-rata untuk posisi wrist
HAND_LOST_GRACE_S = 0.4  # kalau tangan hilang sebentar (mediapipe miss), state gesture tetap dipertahankan

# ---------------------------------------------------------------------------
# Konfigurasi Kamera & Performa
# ---------------------------------------------------------------------------
CAMERA_INDEX = 1
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
PRINT_EVERY_N_FRAMES = 10   # throttle log terminal supaya tidak jadi bottleneck


# ---------------------------------------------------------------------------
# Kelola koneksi Dobot (auto-detect port)
# ---------------------------------------------------------------------------
def list_candidate_ports():
    """Urutkan port: yang match keyword Dobot/USB-serial duluan, sisanya menyusul."""
    ports = list(list_ports.comports())
    hinted, others = [], []
    for p in ports:
        text = f"{p.description or ''} {p.manufacturer or ''}".lower()
        if any(k in text for k in PORT_HINT_KEYWORDS):
            hinted.append(p.device)
        else:
            others.append(p.device)
    return hinted + others


def connect_dobot(max_attempts_per_port: int = 2, retry_delay_s: float = 0.8):
    """Auto-scan semua serial port dan coba konek ke Dobot.

    Return:
        Instance Dobot yang sudah terhubung (siap dipakai), atau None kalau gagal.
    """
    if Dobot is None:
        log.error("pydobotplus belum terinstall. Jalankan: pip install pydobotplus")
        return None

    candidates = list_candidate_ports()
    if not candidates:
        log.warning("Tidak ada serial port terdeteksi sama sekali. "
                    "Pastikan kabel USB Dobot terpasang.")
        return None

    log.info("Port yang terdeteksi: %s", candidates)

    for port in candidates:
        for attempt in range(1, max_attempts_per_port + 1):
            device = None
            try:
                log.info("Mencoba menghubungkan ke Dobot di %s (percobaan %d)...", port, attempt)
                device = Dobot(port=port)
                device.speed(DEFAULT_VELOCITY, DEFAULT_ACCELERATION)
                log.info("Dobot terhubung di port: %s", port)
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
                time.sleep(retry_delay_s)

    log.warning("Dobot tidak ditemukan/gagal dikonek di %d port yang dicoba: %s",
                len(candidates), candidates)
    return None


def get_device_port(device) -> str:
    """Ambil nama port aktual dari instance Dobot yang sudah terhubung (untuk ditampilkan di UI/log)."""
    try:
        return device._ser.port
    except Exception:
        return "unknown"


class DobotController:
    """
    Semua perintah gerak/aktuator yang dipanggil dari video loop TIDAK
    langsung bicara ke serial port. Mereka cuma `put()` ke cmd_queue dan
    balik lagi ke video loop dengan hampir tanpa delay. Worker thread
    (_process_commands) yang mengeksekusi command satu-satu ke Dobot di
    background, jadi berapa pun lama request-response serial-nya, video
    loop tidak pernah ikut nunggu.
    """

    def __init__(self):
        self.device = None
        self.connected = False
        self.port = None
        self.suction = False
        self.conveyor = False
        self._lock = threading.RLock()

        self.cmd_queue = queue.Queue()
        self._stop_worker = threading.Event()
        self._worker_thread = threading.Thread(
            target=self._process_commands, daemon=True
        )
        self._worker_thread.start()

    # --- Worker thread: eksekusi command serial di background ---
    def _process_commands(self):
        while not self._stop_worker.is_set():
            try:
                fn, args = self.cmd_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                fn(*args)
            except Exception as exc:
                log.warning("Command worker error: [%s] %r", type(exc).__name__, str(exc))
            finally:
                self.cmd_queue.task_done()

    def wait_queue_empty(self, timeout: float = 2.0):
        """Blok sebentar sampai semua command di queue selesai diproses --
        dipanggil saat shutdown supaya perintah suction/conveyor OFF
        terakhir sempat benar-benar terkirim ke Dobot sebelum disconnect."""
        start = time.time()
        while not self.cmd_queue.empty() and (time.time() - start) < timeout:
            time.sleep(0.05)

    def shutdown_worker(self):
        self._stop_worker.set()
        self._worker_thread.join(timeout=2)

    # --- Koneksi (dipanggil dari main thread saat start, dan dari reconnect thread) ---
    def connect(self) -> bool:
        """Buka koneksi serial baru ke Dobot (auto-detect port)."""
        with self._lock:
            if self.connected:
                return True

            device = connect_dobot()
            if device is None:
                return False

            self.device = device
            self.port = get_device_port(device)
            self.connected = True
            return True

    def do_homing(self, wait_seconds: int = 20) -> bool:
        """Jalankan proses homing fisik Dobot. Dipanggil SEKALI di awal main(),
        SEBELUM kamera dibuka -- supaya robot benar-benar di posisi nol dulu
        sebelum menerima perintah gerak dari gesture."""
        with self._lock:
            if not self.connected or self.device is None:
                log.warning("Tidak bisa homing: Dobot belum terhubung.")
                return False
            try:
                log.info("Memulai proses Homing. Pastikan area sekitar robot KOSONG!")
                self.device.home()
                log.info("Menunggu homing selesai (%d detik)...", wait_seconds)
                time.sleep(wait_seconds)
                log.info("Homing selesai. Dobot siap menerima perintah gesture.")
                return True
            except Exception as exc:
                log.warning("Homing gagal: [%s] %r", type(exc).__name__, str(exc))
                self._mark_disconnected(exc)
                return False

    def disconnect(self):
        with self._lock:
            if self.device is not None:
                try:
                    self.device.close()
                except Exception:
                    pass
            self.device = None
            self.connected = False

    def _mark_disconnected(self, exc: Exception):
        log.warning("Koneksi ke Dobot terputus (%s): %s", self.port, exc)
        with self._lock:
            self.device = None
            self.connected = False
            self.port = None

    # --- API non-blocking, aman dipanggil dari video loop tiap frame ---
    def jog(self, axis: str, direction: str):
        if (axis, direction) not in AXIS_DIRECTIONS:
            return
        self.cmd_queue.put((self._do_jog, (axis, direction)))

    def _do_jog(self, axis: str, direction: str):
        with self._lock:
            if not self.connected or self.device is None:
                return
            device = self.device
        dx, dy, dz = AXIS_DIRECTIONS[(axis, direction)]
        step = STEP_Z_MM if axis == "z" else STEP_XY_MM
        try:
            device.move_rel(x=dx * step, y=dy * step, z=dz * step, r=0, wait=False)
        except Exception as exc:
            self._mark_disconnected(exc)

    def move_forward_backward(self, forward: bool):
        self.jog("x", "forward" if forward else "backward")

    def set_suction(self, enable: bool):
        if self.suction == enable:
            return
        self.cmd_queue.put((self._send_suction, (enable,)))

    def _send_suction(self, enable: bool):
        with self._lock:
            if not self.connected or self.device is None:
                return
            device = self.device
        try:
            device.suck(enable)
            self.suction = enable
            log.info("Suction: %s", "ON" if enable else "OFF")
        except Exception as exc:
            self._mark_disconnected(exc)

    def set_conveyor(self, enable: bool, speed: float = CONVEYOR_SPEED):
        if self.conveyor == enable:
            return
        self.cmd_queue.put((self._send_conveyor, (enable, speed)))

    def _send_conveyor(self, enable: bool, speed: float):
        with self._lock:
            if not self.connected or self.device is None:
                return
            device = self.device
        try:
            device.conveyor_belt(speed=speed if enable else 0.0, direction=1)
            self.conveyor = enable
            log.info("Conveyor: %s", "ON" if enable else "OFF")
        except Exception as exc:
            self._mark_disconnected(exc)


def background_reconnect(dobot: DobotController, stop_event: threading.Event):
    """Thread daemon: kalau koneksi putus atau belum konek, terus coba reconnect
    otomatis tiap RECONNECT_INTERVAL_S detik -- tidak perlu restart script."""
    while not stop_event.is_set():
        if not dobot.connected:
            dobot.connect()
        stop_event.wait(RECONNECT_INTERVAL_S)


# ---------------------------------------------------------------------------
# Klasifikasi zona dengan hysteresis
# ---------------------------------------------------------------------------
def classify_zone(wrist_x: float, wrist_y: float, current_zone: str) -> str:
    """Tentukan zona (Kiri/Kanan/Atas/Bawah/Tengah) dengan hysteresis supaya
    tidak flicker saat posisi tangan pas di garis batas."""

    def in_zone(name, value_below=None, value_above=None):
        z = ZONE[name]
        thresh = z["exit"] if current_zone == name else z["enter"]
        if value_below is not None:
            return value_below < thresh
        return value_above > thresh

    if in_zone("top", value_below=wrist_y):
        return "Gerakan ke Atas"
    if in_zone("bottom", value_above=wrist_y):
        return "Gerakan ke Bawah"
    if in_zone("left", value_below=wrist_x):
        return "Gerakan ke Kiri"
    if in_zone("right", value_above=wrist_x):
        return "Gerakan ke Kanan"
    return "Diam (Tengah)"


# ---------------------------------------------------------------------------
# Loop Utama
# ---------------------------------------------------------------------------
def main():
    dobot = DobotController()

    if dobot.connect():
        dobot.do_homing()  # WAJIB selesai dulu sebelum kamera & gesture scanning dimulai
    else:
        log.warning("Dobot tidak terhubung di awal -- lanjut tanpa homing. "
                    "Kamera & gesture tetap aktif, kontrol Dobot menunggu auto-reconnect.")

    stop_event = threading.Event()
    reconnect_thread = threading.Thread(
        target=background_reconnect, args=(dobot, stop_event), daemon=True
    )
    reconnect_thread.start()

    mp_drawing = mp.solutions.drawing_utils
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        model_complexity=0,   # lite model -- jauh lebih ringan per frame dibanding default (1)
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )

    cap = cv2.VideoCapture(CAMERA_INDEX)
    # Paksa MJPG + resolusi kecil + buffer minim: mengurangi bandwidth USB dan
    # mencegah OpenCV menumpuk frame lama di buffer (yang bikin delay makin
    # "ngaret" kalau proses MediaPipe lebih lambat dari capture rate).
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    tip_ids = [4, 8, 12, 16, 20]

    last_jog_time = 0.0
    last_fb_time = 0.0
    current_zone = "Diam (Tengah)"

    wrist_x_buf = deque(maxlen=SMOOTHING_WINDOW)
    wrist_y_buf = deque(maxlen=SMOOTHING_WINDOW)

    last_hand_seen_time = 0.0
    last_gerakan_robot = "Diam"
    last_posisi_tangan = "Diam"
    last_fingers_count = 0
    prev_fingers_count = -1  # dipakai buat deteksi transisi gesture (biar toggle, bukan hold)
    frame_count = 0

    window_name = "Hand Gesture -> Dobot Control (v3: Async Command Queue)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        import tkinter
        _root = tkinter.Tk()
        screen_w = _root.winfo_screenwidth()
        screen_h = _root.winfo_screenheight()
        _root.destroy()
    except Exception:
        screen_w, screen_h = 640, 480  # fallback kalau tkinter tidak tersedia

    cv2.resizeWindow(window_name, screen_w, screen_h)
    cv2.moveWindow(window_name, 0, 0)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                print("Gagal membaca frame dari kamera.")
                break

            frame_count += 1
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            results = hands.process(image)
            image.flags.writeable = True
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            x_left = int(w * ZONE["left"]["enter"])
            x_right = int(w * ZONE["right"]["enter"])
            y_top = int(h * ZONE["top"]["enter"])
            y_bottom = int(h * ZONE["bottom"]["enter"])
            cv2.line(image, (x_left, 0), (x_left, h), (0, 255, 255), 1, cv2.LINE_AA)
            cv2.line(image, (x_right, 0), (x_right, h), (0, 255, 255), 1, cv2.LINE_AA)
            cv2.line(image, (0, y_top), (w, y_top), (0, 255, 255), 1, cv2.LINE_AA)
            cv2.line(image, (0, y_bottom), (w, y_bottom), (0, 255, 255), 1, cv2.LINE_AA)

            now = time.time()
            fingers_count = 0
            posisi_tangan = last_posisi_tangan
            gerakan_robot = last_gerakan_robot

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                    landmarks = hand_landmarks.landmark
                    fingers = []

                    if landmarks[tip_ids[0]].x < landmarks[tip_ids[0] - 1].x:
                        fingers.append(1)
                    else:
                        fingers.append(0)

                    for id in range(1, 5):
                        if landmarks[tip_ids[id]].y < landmarks[tip_ids[id] - 2].y:
                            fingers.append(1)
                        else:
                            fingers.append(0)

                    fingers_count = fingers.count(1)
                    last_hand_seen_time = now

                    wrist_x_buf.append(landmarks[0].x)
                    wrist_y_buf.append(landmarks[0].y)
                    wrist_x = sum(wrist_x_buf) / len(wrist_x_buf)
                    wrist_y = sum(wrist_y_buf) / len(wrist_y_buf)

                    if fingers_count == 5:
                        posisi_tangan = "Navigasi"
                        current_zone = classify_zone(wrist_x, wrist_y, current_zone)
                        gerakan_robot = current_zone

                        if gerakan_robot in GESTURE_TO_JOG and (now - last_jog_time) > COMMAND_COOLDOWN_S:
                            axis, direction = GESTURE_TO_JOG[gerakan_robot]
                            dobot.jog(axis, direction)   # instan -- cuma masuk queue
                            last_jog_time = now

                    else:
                        posisi_tangan = "Kontrol Jari"
                        current_zone = "Diam (Tengah)"

                        if fingers_count == 1:
                            if prev_fingers_count != 1:
                                dobot.set_conveyor(not dobot.conveyor)
                            gerakan_robot = f"Conveyor {'ON' if dobot.conveyor else 'OFF'} (1 Jari)"
                        elif fingers_count == 2:
                            if prev_fingers_count != 2:
                                dobot.set_suction(not dobot.suction)
                            gerakan_robot = f"Suction {'ON' if dobot.suction else 'OFF'} (2 Jari)"
                        elif fingers_count == 3:
                            gerakan_robot = "Gerakan ke Depan (3 Jari)"
                            if (now - last_fb_time) > COMMAND_COOLDOWN_S:
                                dobot.move_forward_backward(forward=True)
                                last_fb_time = now
                        elif fingers_count == 4:
                            gerakan_robot = "Gerakan ke Belakang (4 Jari)"
                            if (now - last_fb_time) > COMMAND_COOLDOWN_S:
                                dobot.move_forward_backward(forward=False)
                                last_fb_time = now
                        else:
                            gerakan_robot = "Stop Semua Aktuator (Mengepal)"
                            dobot.set_suction(False)
                            dobot.set_conveyor(False)

                        prev_fingers_count = fingers_count
            else:
                if (now - last_hand_seen_time) > HAND_LOST_GRACE_S:
                    fingers_count = 0
                    posisi_tangan = "Diam"
                    gerakan_robot = "Diam"
                    current_zone = "Diam (Tengah)"
                    wrist_x_buf.clear()
                    wrist_y_buf.clear()
                    prev_fingers_count = -1
                else:
                    fingers_count = last_fingers_count
                    posisi_tangan = last_posisi_tangan
                    gerakan_robot = last_gerakan_robot

            last_gerakan_robot = gerakan_robot
            last_posisi_tangan = posisi_tangan
            last_fingers_count = fingers_count

            status_koneksi = f"Terhubung ({dobot.port})" if dobot.connected else "Mencari Dobot..."

            # Log ke terminal di-throttle -- tidak tiap frame, supaya print()
            # (I/O ke stdout) tidak ikut jadi sumber delay video.
            if frame_count % PRINT_EVERY_N_FRAMES == 0:
                print(f"[DOBOT: {status_koneksi}] Aksi: {gerakan_robot} | Posisi: {posisi_tangan} | "
                      f"Jari: {fingers_count} | Suction: {'ON' if dobot.suction else 'OFF'} | "
                      f"Conveyor: {'ON' if dobot.conveyor else 'OFF'}")

            cv2.putText(image, f"Aksi: {gerakan_robot}", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(image,
                        f"Jari: {fingers_count} | Suc: {'ON' if dobot.suction else 'OFF'} | "
                        f"Conv: {'ON' if dobot.conveyor else 'OFF'}",
                        (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(image, f"Dobot: {status_koneksi}", (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (255, 255, 0) if dobot.connected else (0, 0, 255), 2, cv2.LINE_AA)

            cv2.imshow(window_name, image)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # 27 = kode tombol Esc
                break
    finally:
        stop_event.set()
        dobot.set_suction(False)
        dobot.set_conveyor(False)
        dobot.wait_queue_empty(timeout=2.0)   # kasih waktu command OFF terakhir sempat terkirim
        dobot.shutdown_worker()
        dobot.disconnect()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()