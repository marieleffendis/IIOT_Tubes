import time
import logging
import threading
import queue
import platform
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

PORT_HINT_KEYWORDS = ["dobot", "cp210", "ch340", "silicon labs", "usb-serial", "usb serial"]

# ---------------------------------------------------------------------------
# Konfigurasi Gerak & Dobot
# ---------------------------------------------------------------------------
STEP_XY_MM = 20.0
STEP_Z_MM = 20.0
STEP_X_MM = 25.0
CONVEYOR_SPEED = 0.5

COMMAND_COOLDOWN_S = 0.4
RECONNECT_INTERVAL_S = 5

GESTURE_TO_JOG = {
    "Gerakan ke Kiri":     ("y", "left"),
    "Gerakan ke Kanan":    ("y", "right"),
    "Gerakan ke Atas":     ("z", "up"),
    "Gerakan ke Bawah":    ("z", "down"),
    "Gerakan ke Depan":    ("x", "forward"),
    "Gerakan ke Belakang": ("x", "backward"),
}

AXIS_DIRECTIONS = {
    ("x", "forward"):  (+1, 0, 0),
    ("x", "backward"): (-1, 0, 0),
    ("y", "left"):     (0, -1, 0),
    ("y", "right"):    (0, +1, 0),
    ("z", "up"):       (0, 0, +1),
    ("z", "down"):     (0, 0, -1),
}

# ---------------------------------------------------------------------------
# Konfigurasi Zona Navigasi (5 Jari)
# ---------------------------------------------------------------------------
ZONE = {
    "left":   {"enter": 0.35, "exit": 0.40},   
    "right":  {"enter": 0.65, "exit": 0.60},   
    "top":    {"enter": 0.40, "exit": 0.46},   
    "bottom": {"enter": 0.60, "exit": 0.54},   
}

SMOOTHING_WINDOW = 7
HAND_LOST_GRACE_S = 0.4
STABILITY_THRESHOLD = 5

# ---------------------------------------------------------------------------
# Konfigurasi Kamera & Performa
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
PRINT_EVERY_N_FRAMES = 10


# ---------------------------------------------------------------------------
# Kelas CameraStream (Ultra-Low Latency + Thread-Safe untuk Orbbec)
# ---------------------------------------------------------------------------
class CameraStream:
    def __init__(self, src=0, width=640, height=480):
        if platform.system() == 'Windows':
            self.stream = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        else:
            self.stream = cv2.VideoCapture(src, cv2.CAP_V4L2)
            
        self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.stream.set(cv2.CAP_PROP_FPS, 30)

        self.target_width = width
        self.target_height = height

        self.grabbed, self.frame = self.stream.read()
        if self.grabbed:
            self.frame = cv2.resize(self.frame, (self.target_width, self.target_height))
            
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self.update, daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            if not self.stream.isOpened():
                break
            
            grabbed = self.stream.grab()
            if grabbed:
                success, frame = self.stream.retrieve()
                if success:
                    frame = cv2.resize(frame, (self.target_width, self.target_height))
                    with self.lock:
                        self.frame = frame
                        self.grabbed = True
            else:
                with self.lock:
                    self.grabbed = False

    def read(self):
        with self.lock:
            if self.frame is None:
                return self.grabbed, None
            return self.grabbed, self.frame.copy()

    def release(self):
        self.stopped = True
        self.stream.release()

    def isOpened(self):
        return self.stream.isOpened()


# ---------------------------------------------------------------------------
# Kelola koneksi Dobot (auto-detect port)
# ---------------------------------------------------------------------------
def list_candidate_ports():
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
    if Dobot is None:
        log.error("pydobotplus belum terinstall. Jalankan: pip install pydobotplus")
        return None

    candidates = list_candidate_ports()
    if not candidates:
        log.warning("Tidak ada serial port terdeteksi sama sekali.")
        return None

    for port in candidates:
        for attempt in range(1, max_attempts_per_port + 1):
            device = None
            try:
                device = Dobot(port=port)
                device.speed(DEFAULT_VELOCITY, DEFAULT_ACCELERATION)
                return device
            except Exception as exc:
                if device is not None:
                    try:
                        device.close()
                    except Exception:
                        pass
                time.sleep(retry_delay_s)
    return None

def get_device_port(device) -> str:
    try:
        return device._ser.port
    except Exception:
        return "unknown"

class DobotController:
    def __init__(self):
        self.device = None
        self.connected = False
        self.port = None
        self.suction = False
        self.conveyor = False
        self._lock = threading.RLock()
        self.cmd_queue = queue.Queue()
        self._stop_worker = threading.Event()
        self._worker_thread = threading.Thread(target=self._process_commands, daemon=True)
        self._worker_thread.start()

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
        start = time.time()
        while not self.cmd_queue.empty() and (time.time() - start) < timeout:
            time.sleep(0.05)

    def shutdown_worker(self):
        self._stop_worker.set()
        self._worker_thread.join(timeout=2)

    def connect(self) -> bool:
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
        with self._lock:
            if not self.connected or self.device is None:
                return False
            try:
                self.device.home()
                time.sleep(wait_seconds)
                return True
            except Exception as exc:
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
        with self._lock:
            self.device = None
            self.connected = False
            self.port = None

    def clear_queue(self):
        while not self.cmd_queue.empty():
            try:
                self.cmd_queue.get_nowait()
                self.cmd_queue.task_done()
            except queue.Empty:
                break

    def jog(self, axis: str, direction: str):
        if (axis, direction) not in AXIS_DIRECTIONS:
            return
        # Tidak membersihkan antrean agar perintah aktuator/suction tetap bisa diselipkan
        self.cmd_queue.put((self._do_jog, (axis, direction)))

    def _do_jog(self, axis: str, direction: str):
        with self._lock:
            if not self.connected or self.device is None:
                return
            device = self.device
        dx, dy, dz = AXIS_DIRECTIONS[(axis, direction)]
        
        if axis == "z":
            step = STEP_Z_MM
        elif axis == "x":
            step = STEP_X_MM
        else:
            step = STEP_XY_MM

        try:
            device.move_rel(x=dx * step, y=dy * step, z=dz * step, r=0, wait=False)
        except Exception as exc:
            self._mark_disconnected(exc)

    def set_suction(self, enable: bool):
        # Langsung masukkan ke antrean tanpa memutus gerakan sumbu/jogging
        self.cmd_queue.put((self._send_suction, (enable,)))

    def _send_suction(self, enable: bool):
        with self._lock:
            if not self.connected or self.device is None:
                return
            device = self.device
        try:
            device.suck(enable)
            self.suction = enable
        except Exception as exc:
            self._mark_disconnected(exc)

    def set_conveyor(self, enable: bool, speed: float = CONVEYOR_SPEED):
        self.cmd_queue.put((self._send_conveyor, (enable, speed)))

    def _send_conveyor(self, enable: bool, speed: float):
        with self._lock:
            if not self.connected or self.device is None:
                return
            device = self.device
        try:
            device.conveyor_belt(speed=speed if enable else 0.0, direction=1)
            self.conveyor = enable
        except Exception as exc:
            self._mark_disconnected(exc)

def background_reconnect(dobot: DobotController, stop_event: threading.Event):
    while not stop_event.is_set():
        if not dobot.connected:
            dobot.connect()
        stop_event.wait(RECONNECT_INTERVAL_S)

def classify_zone(wrist_x: float, wrist_y: float, current_zone: str) -> str:
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
        dobot.do_homing() 
    
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
        model_complexity=0,   
        min_detection_confidence=0.75,
        min_tracking_confidence=0.6,
    )

    cap = CameraStream(src=CAMERA_INDEX, width=CAMERA_WIDTH, height=CAMERA_HEIGHT).start()

    tip_ids = [4, 8, 12, 16, 20]

    last_action_time = 0.0
    current_zone = "Diam (Tengah)"

    wrist_x_buf = deque(maxlen=SMOOTHING_WINDOW)
    wrist_y_buf = deque(maxlen=SMOOTHING_WINDOW)

    last_hand_seen_time = 0.0
    last_gerakan_robot = "Diam"
    last_posisi_tangan = "Diam"
    
    candidate_fingers = -1
    consecutive_count = 0
    stable_fingers_count = 0
    prev_fingers_count = -1

    frame_count = 0

    window_name = "Hand Gesture -> Dobot Control"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        import tkinter
        _root = tkinter.Tk()
        screen_w = _root.winfo_screenwidth()
        screen_h = _root.winfo_screenheight()
        _root.destroy()
    except Exception:
        screen_w, screen_h = 640, 480 

    cv2.resizeWindow(window_name, screen_w, screen_h)
    cv2.moveWindow(window_name, 0, 0)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                continue

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
            raw_fingers_count = 0
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

                    raw_fingers_count = fingers.count(1)
                    last_hand_seen_time = now

                    wrist_x_buf.append(landmarks[0].x)
                    wrist_y_buf.append(landmarks[0].y)
                    wrist_x = sum(wrist_x_buf) / len(wrist_x_buf)
                    wrist_y = sum(wrist_y_buf) / len(wrist_y_buf)

                    if raw_fingers_count == candidate_fingers:
                        consecutive_count += 1
                    else:
                        candidate_fingers = raw_fingers_count
                        consecutive_count = 1

                    if consecutive_count >= STABILITY_THRESHOLD:
                        stable_fingers_count = candidate_fingers

                    fingers_count = stable_fingers_count

                    # LOGIKA UTAMA GESTUR
                    if fingers_count == 5:
                        posisi_tangan = "Navigasi"
                        current_zone = classify_zone(wrist_x, wrist_y, current_zone)
                        gerakan_robot = current_zone

                        if gerakan_robot in GESTURE_TO_JOG and (now - last_action_time) > COMMAND_COOLDOWN_S:
                            axis, direction = GESTURE_TO_JOG[gerakan_robot]
                            dobot.jog(axis, direction)
                            last_action_time = now
                        prev_fingers_count = fingers_count

                    elif fingers_count == 3:
                        posisi_tangan = "Kontrol Maju/Mundur"
                        gerakan_robot = "Gerakan ke Depan"
                        if (now - last_action_time) > COMMAND_COOLDOWN_S:
                            dobot.jog("x", "forward")
                            last_action_time = now
                        prev_fingers_count = fingers_count

                    elif fingers_count == 4:
                        posisi_tangan = "Kontrol Maju/Mundur"
                        gerakan_robot = "Gerakan ke Belakang"
                        if (now - last_action_time) > COMMAND_COOLDOWN_S:
                            dobot.jog("x", "backward")
                            last_action_time = now
                        prev_fingers_count = fingers_count

                    else:
                        posisi_tangan = "Kontrol Aktuator"
                        current_zone = "Diam (Tengah)"

                        if fingers_count != prev_fingers_count and (now - last_action_time) > COMMAND_COOLDOWN_S:
                            if fingers_count == 1:
                                new_state = not dobot.conveyor
                                dobot.set_conveyor(new_state)
                                gerakan_robot = f"Conveyor {'ON' if new_state else 'OFF'} (Toggle)"
                                last_action_time = now
                            elif fingers_count == 2:
                                # Suction Toggle: Bisa diubah statusnya kapan saja secara paralel
                                new_state = not dobot.suction
                                dobot.set_suction(new_state)
                                gerakan_robot = f"Suction {'ON' if new_state else 'OFF'} (Paralel Toggle)"
                                last_action_time = now
                            elif fingers_count == 0:
                                dobot.set_suction(False)
                                dobot.set_conveyor(False)
                                gerakan_robot = "Stop Semua Aktuator (Mengepal)"
                                last_action_time = now

                            prev_fingers_count = fingers_count
            else:
                if (now - last_hand_seen_time) > HAND_LOST_GRACE_S:
                    fingers_count = 0
                    posisi_tangan = "Diam"
                    gerakan_robot = "Diam"
                    current_zone = "Diam (Tengah)"
                    wrist_x_buf.clear()
                    wrist_y_buf.clear()
                    candidate_fingers = -1
                    consecutive_count = 0
                    stable_fingers_count = 0
                    prev_fingers_count = -1
                else:
                    fingers_count = stable_fingers_count
                    posisi_tangan = last_posisi_tangan
                    gerakan_robot = last_gerakan_robot

            last_gerakan_robot = gerakan_robot
            last_posisi_tangan = posisi_tangan

            status_koneksi = f"Terhubung ({dobot.port})" if dobot.connected else "Mencari Dobot..."

            if frame_count % PRINT_EVERY_N_FRAMES == 0:
                print(f"[DOBOT: {status_koneksi}] Aksi: {gerakan_robot} | Posisi: {posisi_tangan} | "
                      f"Jari Stabil: {fingers_count} | Suction: {'ON' if dobot.suction else 'OFF'} | "
                      f"Conveyor: {'ON' if dobot.conveyor else 'OFF'}")

            cv2.putText(image, f"Aksi: {gerakan_robot}", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(image,
                        f"Jari Stabil: {fingers_count} | Suc: {'ON' if dobot.suction else 'OFF'} | "
                        f"Conv: {'ON' if dobot.conveyor else 'OFF'}",
                        (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(image, f"Dobot: {status_koneksi}", (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (255, 255, 0) if dobot.connected else (0, 0, 255), 2, cv2.LINE_AA)

            cv2.imshow(window_name, image)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break
    finally:
        stop_event.set()
        dobot.set_suction(False)
        dobot.set_conveyor(False)
        dobot.wait_queue_empty(timeout=2.0)
        dobot.shutdown_worker()
        dobot.disconnect()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()