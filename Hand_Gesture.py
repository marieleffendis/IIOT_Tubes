"""
dobot_gesture_control_v2.py

Perbaikan dari versi sebelumnya:
1. AUTO-DETECT PORT: scan semua serial port yang tersedia, coba konek satu per satu
   sampai ketemu yang benar-benar Dobot -- tidak perlu edit DOBOT_PORT manual lagi.
   Ada juga thread background yang otomatis mencoba reconnect kalau koneksi putus.
2. REGION DETEKSI LEBIH STABIL:
   - Smoothing posisi wrist (rata-rata beberapa frame terakhir) supaya tidak jitter.
   - Hysteresis per-zona: ambang untuk MASUK zona dan KELUAR zona dibedakan,
     jadi gesture tidak "flicker" pas tangan pas di garis batas.
"""

import time
import logging
import threading
from collections import deque
from typing import Optional

import cv2
import mediapipe as mp
from serial.tools import list_ports

try:
    from pydobotplus import Dobot
except ImportError:
    Dobot = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dobot-gesture")

# ---------------------------------------------------------------------------
# Konfigurasi Gerak & Dobot
# ---------------------------------------------------------------------------
STEP_XY_MM = 20.0
STEP_Z_MM = 20.0
DEFAULT_VELOCITY = 100.0
DEFAULT_ACCELERATION = 100.0
CONVEYOR_SPEED = 0.5

COMMAND_COOLDOWN_S = 0.4
RECONNECT_INTERVAL_S = 5   # jeda antar percobaan auto-reconnect saat koneksi putus

# Kata kunci untuk mengenali kandidat port Dobot lebih dulu (dicoba paling awal).
# Kalau tidak ada yang cocok, semua port lain tetap akan dicoba juga.
PORT_HINT_KEYWORDS = ["dobot", "cp210", "ch340", "silicon labs", "usb-serial", "usb serial"]

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
# ENTER = ambang untuk mulai masuk ke zona itu
# EXIT  = ambang untuk keluar dari zona itu (dibuat lebih longgar dari ENTER)
# Selisih ENTER-EXIT ini yang bikin gesture tidak flicker di garis batas.
ZONE = {
    "left":   {"enter": 0.30, "exit": 0.36},   # wrist_x < enter -> masuk KIRI
    "right":  {"enter": 0.70, "exit": 0.64},   # wrist_x > enter -> masuk KANAN
    "top":    {"enter": 0.55, "exit": 0.62},   # wrist_y < enter -> masuk ATAS
    "bottom": {"enter": 0.75, "exit": 0.68},   # wrist_y > enter -> masuk BAWAH
}

SMOOTHING_WINDOW = 5   # jumlah frame terakhir yang dirata-rata untuk posisi wrist
HAND_LOST_GRACE_S = 0.4  # kalau tangan hilang sebentar (mediapipe miss), state gesture tetap dipertahankan


# ---------------------------------------------------------------------------
# Auto-detect & kelola koneksi Dobot
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


class DobotController:
    def __init__(self):
        self.device = None
        self.connected = False
        self.port = None
        self.suction = False
        self.conveyor = False
        self._lock = threading.RLock()

    def connect(self) -> bool:
        """Coba konek ke Dobot dengan auto-scan semua port yang mungkin."""
        if Dobot is None:
            log.error("pydobotplus belum terinstall. Jalankan: pip install pydobotplus")
            return False

        with self._lock:
            if self.connected:
                return True

            candidates = list_candidate_ports()
            if not candidates:
                log.warning("Tidak ada serial port terdeteksi sama sekali.")
                return False

            for port in candidates:
                try:
                    log.info("Mencoba menghubungkan ke Dobot di %s ...", port)
                    device = Dobot(port=port)
                    device.speed(DEFAULT_VELOCITY, DEFAULT_ACCELERATION)
                    self.device = device
                    self.port = port
                    self.connected = True
                    log.info("Dobot terhubung di port: %s", port)
                    return True
                except Exception as exc:
                    log.debug("Gagal di %s: %s", port, exc)
                    continue

            log.warning("Dobot tidak ditemukan di port manapun (%d port dicoba).", len(candidates))
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
        self.device = None
        self.connected = False
        self.port = None

    def jog(self, axis: str, direction: str):
        if not self.connected or self.device is None:
            return
        key = (axis, direction)
        if key not in AXIS_DIRECTIONS:
            return
        dx, dy, dz = AXIS_DIRECTIONS[key]
        step = STEP_Z_MM if axis == "z" else STEP_XY_MM
        try:
            self.device.move_rel(x=dx * step, y=dy * step, z=dz * step, r=0, wait=False)
        except Exception as exc:
            self._mark_disconnected(exc)

    def move_forward_backward(self, forward: bool):
        self.jog("x", "forward" if forward else "backward")

    def set_suction(self, enable: bool):
        if not self.connected or self.device is None or self.suction == enable:
            return
        try:
            self.device.suck(enable)
            self.suction = enable
            log.info("Suction: %s", "ON" if enable else "OFF")
        except Exception as exc:
            self._mark_disconnected(exc)

    def set_conveyor(self, enable: bool, speed: float = CONVEYOR_SPEED):
        if not self.connected or self.device is None or self.conveyor == enable:
            return
        try:
            self.device.conveyor_belt(speed=speed if enable else 0.0, direction=1)
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

    # Prioritas: Atas dan Bawah dicek dulu (area vertikal lebih luas & lebih sering dipakai),
    # baru Kiri/Kanan.
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
    dobot.connect()  # coba konek langsung di awal

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
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )

    cap = cv2.VideoCapture(0)
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

    window_name = "Hand Gesture -> Dobot Control (v2: Auto Port + Stable Zone)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                print("Gagal membaca frame dari kamera.")
                break

            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            results = hands.process(image)
            image.flags.writeable = True
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            # --- Gambar garis batas zona (pakai ambang "enter" sebagai referensi visual) ---
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

                    # --- Smoothing posisi wrist ---
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
                            dobot.jog(axis, direction)
                            last_jog_time = now

                    else:
                        posisi_tangan = "Kontrol Jari"
                        current_zone = "Diam (Tengah)"  # reset hysteresis saat keluar mode navigasi

                        if fingers_count == 1:
                            dobot.set_conveyor(True)
                            dobot.set_suction(False)
                            gerakan_robot = "Conveyor Hidup (1 Jari)"
                        elif fingers_count == 2:
                            dobot.set_suction(True)
                            dobot.set_conveyor(False)
                            gerakan_robot = "Suction Hidup (2 Jari)"
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
                            gerakan_robot = "Diam (Mengepal)"
                            dobot.set_suction(False)
                            dobot.set_conveyor(False)
            else:
                # Tangan tidak terdeteksi sesaat (mediapipe miss) -> pertahankan state
                # terakhir selama masih dalam grace period, biar tidak "kedip" ke Diam.
                if (now - last_hand_seen_time) > HAND_LOST_GRACE_S:
                    fingers_count = 0
                    posisi_tangan = "Diam"
                    gerakan_robot = "Diam"
                    current_zone = "Diam (Tengah)"
                    wrist_x_buf.clear()
                    wrist_y_buf.clear()
                else:
                    fingers_count = last_fingers_count
                    posisi_tangan = last_posisi_tangan
                    gerakan_robot = last_gerakan_robot

            last_gerakan_robot = gerakan_robot
            last_posisi_tangan = posisi_tangan
            last_fingers_count = fingers_count

            status_koneksi = f"Terhubung ({dobot.port})" if dobot.connected else "Mencari Dobot..."
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

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        stop_event.set()
        dobot.set_suction(False)
        dobot.set_conveyor(False)
        dobot.disconnect()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()