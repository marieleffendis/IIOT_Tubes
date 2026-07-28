"""
dobot_gesture_control.py

Kontrol Dobot Magician langsung dari gesture tangan (kamera), TANPA REST API/Flask.
Logic gesture diambil dari Hand_Gesture.py, logic kontrol Dobot diambil dari index.py
(class DobotManager) — di sini disederhanakan jadi DobotController yang dipanggil
langsung di dalam loop kamera.
"""

import time
import logging
from typing import Optional

import cv2
import mediapipe as mp

try:
    from pydobotplus import Dobot
except ImportError:
    Dobot = None  # Tetap bisa jalan untuk testing kamera/gesture tanpa Dobot terpasang

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dobot-gesture")

# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
STEP_XY_MM = 20.0
STEP_Z_MM = 20.0
DEFAULT_VELOCITY = 100.0
DEFAULT_ACCELERATION = 100.0
CONVEYOR_SPEED = 0.5

DOBOT_PORT = None          # None = auto-detect port
COMMAND_COOLDOWN_S = 0.5   # Jeda minimum antar perintah gerak, biar tidak membanjiri Dobot tiap frame

# Pemetaan gerakan tangan (mode 5 jari) ke (axis, direction) untuk jog
GESTURE_TO_JOG = {
    "Gerakan ke Kiri":  ("y", "left"),
    "Gerakan ke Kanan": ("y", "right"),
    "Gerakan ke Atas":  ("z", "up"),
    "Gerakan ke Bawah": ("z", "down"),
}

# Pemetaan (axis, direction) ke arah gerak relatif (dx, dy, dz) — sama seperti di index.py
AXIS_DIRECTIONS = {
    ("x", "forward"):  (+1, 0, 0),
    ("x", "backward"): (-1, 0, 0),
    ("y", "left"):     (0, +1, 0),
    ("y", "right"):    (0, -1, 0),
    ("z", "up"):       (0, 0, +1),
    ("z", "down"):     (0, 0, -1),
}


# ---------------------------------------------------------------------------
# Kontroler Dobot (tanpa Flask, dipanggil langsung dari loop gesture)
# ---------------------------------------------------------------------------
class DobotController:
    def __init__(self, port: Optional[str] = None):
        self.device = None
        self.connected = False
        self.suction = False
        self.conveyor = False
        self.port = port

    def connect(self) -> bool:
        if Dobot is None:
            log.error("pydobotplus belum terinstall. Jalankan: pip install pydobotplus")
            return False
        try:
            log.info("Menghubungkan ke Dobot%s...", f" di {self.port}" if self.port else " (auto-detect)")
            self.device = Dobot(port=self.port)
            self.device.speed(DEFAULT_VELOCITY, DEFAULT_ACCELERATION)
            self.connected = True
            log.info("Dobot terhubung.")
            return True
        except Exception as exc:
            log.warning("Gagal terhubung ke Dobot: %s", exc)
            self.device = None
            self.connected = False
            return False

    def disconnect(self):
        if self.device is not None:
            try:
                self.device.close()
            except Exception as exc:
                log.warning("Error saat menutup koneksi: %s", exc)
        self.device = None
        self.connected = False

    def jog(self, axis: str, direction: str):
        if not self.connected or self.device is None:
            return
        key = (axis, direction)
        if key not in AXIS_DIRECTIONS:
            log.warning("Perintah jog tidak dikenal: %s", key)
            return
        dx, dy, dz = AXIS_DIRECTIONS[key]
        step = STEP_Z_MM if axis == "z" else STEP_XY_MM
        try:
            self.device.move_rel(x=dx * step, y=dy * step, z=dz * step, r=0, wait=False)
        except Exception as exc:
            log.warning("Gagal jog: %s", exc)
            self.connected = False

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
            log.warning("Gagal set suction: %s", exc)
            self.connected = False

    def set_conveyor(self, enable: bool, speed: float = CONVEYOR_SPEED):
        if not self.connected or self.device is None or self.conveyor == enable:
            return
        try:
            self.device.conveyor_belt(speed=speed if enable else 0.0, direction=1)
            self.conveyor = enable
            log.info("Conveyor: %s", "ON" if enable else "OFF")
        except Exception as exc:
            log.warning("Gagal set conveyor: %s", exc)
            self.connected = False


# ---------------------------------------------------------------------------
# Loop utama: deteksi gesture + eksekusi langsung ke Dobot
# ---------------------------------------------------------------------------
def main():
    dobot = DobotController(port=DOBOT_PORT)
    dobot.connect()  # Kalau gagal, tetap lanjut supaya kamera/gesture tetap bisa ditest

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
    last_fb_time = 0.0  # forward/backward

    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                print("Gagal membaca frame dari kamera.")
                break

            frame = cv2.flip(frame, 1)
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            results = hands.process(image)
            image.flags.writeable = True
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            fingers_count = 0
            posisi_tangan = "Diam"
            gerakan_robot = "Diam"
            now = time.time()

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                    landmarks = hand_landmarks.landmark
                    fingers = []

                    # Jempol
                    if landmarks[tip_ids[0]].x < landmarks[tip_ids[0] - 1].x:
                        fingers.append(1)
                    else:
                        fingers.append(0)

                    # 4 jari lainnya
                    for id in range(1, 5):
                        if landmarks[tip_ids[id]].y < landmarks[tip_ids[id] - 2].y:
                            fingers.append(1)
                        else:
                            fingers.append(0)

                    fingers_count = fingers.count(1)
                    wrist_x = landmarks[0].x
                    wrist_y = landmarks[0].y

                    if fingers_count == 5:
                        # --- MODE NAVIGASI (jog XY/Z) ---
                        if wrist_x < 0.30:
                            posisi_tangan = gerakan_robot = "Gerakan ke Kiri"
                        elif wrist_x > 0.70:
                            posisi_tangan = gerakan_robot = "Gerakan ke Kanan"
                        elif wrist_y < 0.30:
                            posisi_tangan = gerakan_robot = "Gerakan ke Atas"
                        elif wrist_y > 0.70:
                            posisi_tangan = gerakan_robot = "Gerakan ke Bawah"
                        else:
                            posisi_tangan = gerakan_robot = "Diam (Tengah)"

                        if gerakan_robot in GESTURE_TO_JOG and (now - last_jog_time) > COMMAND_COOLDOWN_S:
                            axis, direction = GESTURE_TO_JOG[gerakan_robot]
                            dobot.jog(axis, direction)
                            last_jog_time = now

                    else:
                        # --- MODE AKTUATOR / MAJU-MUNDUR ---
                        posisi_tangan = "Kontrol Jari"
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
                            # Tangan mengepal (0 jari) -> stop semua aktuator
                            gerakan_robot = "Diam"
                            dobot.set_suction(False)
                            dobot.set_conveyor(False)

            status_koneksi = "Terhubung" if dobot.connected else "Tidak Terhubung"
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

            cv2.imshow('Hand Gesture -> Dobot Control (Direct)', image)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        dobot.set_suction(False)
        dobot.set_conveyor(False)
        dobot.disconnect()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()