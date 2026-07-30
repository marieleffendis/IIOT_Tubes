import os
import sys
import time
import cv2
import math
import mediapipe as mp
import serial.tools.list_ports

try:
    from pydobotplus import Dobot
except ImportError:
    Dobot = None

# --- DAFTAR KEYWORD PENCARIAN PORT USB (LINUX & WINDOWS) ---
PORT_HINT_KEYWORDS = [
    "dobot", "cp210", "ch340", "silicon labs", "usb-serial", "usb serial", 
    "arduino", "atmega", "usbiodriver", "ftdi", "ttyusb", "ttyacm"
]

# --- KOORDINAT AMAN AWAL (SAFE HOME) ---
current_x = 250 
current_y = 0
current_z = 0

# --- LIMIT FISIK DOBOT ---
X_MIN, X_MAX = 155, 245
Y_MIN, Y_MAX = -130, 130
Z_MIN, Z_MAX = -12, 90

# --- RENTANG GRID HASIL DETEKSI TANGAN ---
KOLOM_MIN, KOLOM_MAX = 3, 131     # dari w=640
BARIS_MIN, BARIS_MAX = 10, 106    # dari h=480

# --- KOEFISIEN LINEAR (grid -> koordinat Dobot) ---
A = (Y_MAX - Y_MIN) / (KOLOM_MAX - KOLOM_MIN)
B = Y_MIN - A * KOLOM_MIN

C = (X_MAX - X_MIN) / (BARIS_MAX - BARIS_MIN)
D = X_MIN - C * BARIS_MIN

E = (Z_MIN - Z_MAX) / (BARIS_MAX - BARIS_MIN)
F = Z_MAX - E * BARIS_MIN               

def clamp(value, lo, hi):
    return max(lo, min(hi, value))

def list_candidate_ports():
    """
    Mendeteksi semua port serial yang tersedia di sistem (Linux/Windows) 
    dan memprioritaskan yang sesuai dengan keyword perangkat USB serial.
    """
    ports = list(serial.tools.list_ports.comports())
    hinted, others = [], []
    for p in ports:
        text = f"{p.device} {p.description or ''} {p.manufacturer or ''}".lower()
        if any(k in text for k in PORT_HINT_KEYWORDS):
            hinted.append(p.device)
        else:
            others.append(p.device)
    return hinted + others

def connect_dobot_linux(max_attempts_per_port: int = 2, retry_delay_s: float = 0.8):
    """
    Fungsi untuk melakukan scanning dan auto-connect ke Dobot secara fleksibel.
    """
    if Dobot is None:
        print("[ERROR] Library pydobotplus belum terinstall.")
        return None

    candidates = list_candidate_ports()
    if not candidates:
        print("[WARNING] Tidak ada serial port (USB/ACM) yang terdeteksi di sistem.")
        return None

    print(f"[INFO] Kandidat port ditemukan: {candidates}")

    for port in candidates:
        for attempt in range(1, max_attempts_per_port + 1):
            device = None
            try:
                print(f"[INFO] Mencoba menghubungkan ke {port} (Percobaan {attempt})...")
                device = Dobot(port=port)
                try:
                    device.speed(100, 100)
                except Exception:
                    pass
                print(f"[INFO] Berhasil terhubung ke Dobot pada port: {port}")
                return device
            except Exception as exc:
                print(f"[DEBUG] Gagal di port {port}: {exc}")
                if device is not None:
                    try:
                        device.close()
                    except Exception:
                        pass
                time.sleep(retry_delay_s)
                
    print("[ERROR] Gagal terhubung ke semua kandidat port yang tersedia.")
    return None

def clear_dobot_queue(device):
    """
    Coba kosongkan antrian command Dobot secara paksa di level hardware.
    """
    # Ditambahkan "_set_queued_cmd_clear" dan "force_clear" yang merupakan method standar pydobot
    metode_clear = (
        "_set_queued_cmd_clear", 
        "force_clear", 
        "clear_queue", 
        "set_queued_cmd_clear", 
        "stop_queue"
    )
    
    for method_name in metode_clear:
        method = getattr(device, method_name, None)
        if callable(method):
            try:
                method()
                return
            except Exception:
                continue

last_sent_x = 250
last_sent_y = 0
last_sent_z = 0

def kode_untuk_dobot(jari_terbuka, petak_kolom, petak_baris, device):
    global current_x, current_y, current_z
    global last_sent_x, last_sent_y, last_sent_z
    
    if jari_terbuka < 3:
        # Mode 1: Depan-belakang (X) dan Kiri-kanan (Y)
        target_y = clamp(A * petak_kolom + B, Y_MIN, Y_MAX)
        target_x = clamp(C * petak_baris + D, X_MIN, X_MAX)
        target_z = current_z
    else:
        # Mode 2: Atas-bawah (Z) dan Kiri-kanan (Y)
        target_y = clamp(A * petak_kolom + B, Y_MIN, Y_MAX)
        target_z = clamp(E * petak_baris + F, Z_MIN, Z_MAX)
        target_x = current_x

    # --- DEADZONE LOGIC ---
    # Hitung selisih jarak target baru dengan koordinat terakhir yang dikirim
    jarak_pindah = math.sqrt(
        (target_x - last_sent_x)**2 + 
        (target_y - last_sent_y)**2 + 
        (target_z - last_sent_z)**2
    )

    # Hanya eksekusi jika pergeseran lebih dari 5 mm (sesuaikan angka ini jika perlu)
    if jarak_pindah > 5.0:
        current_x, current_y, current_z = target_x, target_y, target_z
        
        # Kosongkan sisa buffer sebelum mengirim rute baru
        clear_dobot_queue(device)
        
        # Kirim perintah gerak
        device.move_to(current_x, current_y, current_z, 0, wait=False)
        
        # Catat titik terakhir yang dieksekusi
        last_sent_x, last_sent_y, last_sent_z = current_x, current_y, current_z


# --- INISIALISASI DOBOT ---
print("[INFO] Menghubungkan ke Dobot (Auto-Detect USB Linux/Windows)...")
device = connect_dobot_linux()
if device is None:
    print("[ERROR] Dobot tidak terhubung. Keluar.")
    sys.exit(1)

print("[INFO] Memulai proses Homing (sekitar 30 detik)...")
device.home()
time.sleep(30)

# --- PERCEPAT KECEPATAN GERAK DOBOT ---
try:
    device.speed(velocity=100, acceleration=100)
    print("[INFO] Speed Dobot di-set via device.speed().")
except AttributeError:
    try:
        device.set_ptp_joint_params(velocity=100, acceleration=100)
        print("[INFO] Speed Dobot di-set via device.set_ptp_joint_params().")
    except AttributeError:
        print("[WARNING] Tidak menemukan method set speed yang cocok.")


# --- 1. Sembunyikan Log Warning TensorFlow ---
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

# --- 2. Fix Path File Model ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "hand_landmarker.task")

if not os.path.exists(MODEL_PATH):
    print(f"\n[ERROR] File 'hand_landmarker.task' TIDAK DITEMUKAN di: {MODEL_PATH}")
    sys.exit(1)

# --- 3. Inisialisasi MediaPipe Tasks ---
BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

latest_result = None

def print_result(result, output_image, timestamp_ms: int):
    global latest_result
    latest_result = result

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.LIVE_STREAM,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
    result_callback=print_result
)

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)
]

UKURAN_PETAK = 5 

# --- PENGATURAN COOLDOWN DOBOT ---
waktu_terakhir_kirim = 0
COOLDOWN_DOBOT = 0.2

# --- SMOOTHING POSISI TANGAN (EMA) ---
ALPHA_SMOOTH = 0.3
smooth_x, smooth_y = None, None

# --- PENGATURAN KAMERA & FPS ---
video = cv2.VideoCapture(0)
video.set(cv2.CAP_PROP_FPS, 24)
video.set(cv2.CAP_PROP_BUFFERSIZE, 1)

TARGET_FPS = 24
FRAME_DELAY = 1.0 / TARGET_FPS

with HandLandmarker.create_from_options(options) as landmarker:
    while video.isOpened():
        loop_start_time = time.time()

        ret, frame = video.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape 

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        frame_timestamp_ms = int(time.time() * 1000)
        landmarker.detect_async(mp_image, frame_timestamp_ms)

        if latest_result and latest_result.hand_landmarks:
            for hand_landmarks, handedness in zip(latest_result.hand_landmarks, latest_result.handedness):
                sum_x = 0
                sum_y = 0
                
                for connection in HAND_CONNECTIONS:
                    start_idx, end_idx = connection
                    pt1 = (int(hand_landmarks[start_idx].x * w), int(hand_landmarks[start_idx].y * h))
                    pt2 = (int(hand_landmarks[end_idx].x * w), int(hand_landmarks[end_idx].y * h))
                    cv2.line(frame, pt1, pt2, (0, 255, 0), 2)

                for lm in hand_landmarks:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)
                    sum_x += cx
                    sum_y += cy
                
                titik_berat_x_raw = int(sum_x / 21) + 15
                titik_berat_y_raw = int(sum_y / 21) + 50

                if smooth_x is None:
                    smooth_x, smooth_y = float(titik_berat_x_raw), float(titik_berat_y_raw)
                else:
                    smooth_x = ALPHA_SMOOTH * titik_berat_x_raw + (1 - ALPHA_SMOOTH) * smooth_x
                    smooth_y = ALPHA_SMOOTH * titik_berat_y_raw + (1 - ALPHA_SMOOTH) * smooth_y

                titik_berat_x = int(smooth_x)
                titik_berat_y = int(smooth_y)
                petak_baris = titik_berat_y // UKURAN_PETAK
                petak_kolom = titik_berat_x // UKURAN_PETAK
                cv2.circle(frame, (titik_berat_x, titik_berat_y), 10, (0, 255, 255), -1)
                
                jari_terbuka = 0
                hand_label = handedness[0].category_name
                
                def get_dist(idx1, idx2):
                    x1, y1 = hand_landmarks[idx1].x * w, hand_landmarks[idx1].y * h
                    x2, y2 = hand_landmarks[idx2].x * w, hand_landmarks[idx2].y * h
                    return math.hypot(x1 - x2, y1 - y2)

                if get_dist(4, 17) > get_dist(3, 17):
                    jari_terbuka += 1

                jari_lainnya = [(8, 6), (12, 10), (16, 14), (20, 18)]
                for tip, pip in jari_lainnya:
                    if get_dist(tip, 0) > get_dist(pip, 0):
                        jari_terbuka += 1

                teks_lokasi = f"Lokasi: ({petak_baris}, {petak_kolom})"
                cv2.putText(frame, teks_lokasi, (titik_berat_x - 40, titik_berat_y - 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                            
                teks_jari = f"Jari Terbuka: {jari_terbuka}"
                cv2.putText(frame, teks_jari, (titik_berat_x - 40, titik_berat_y - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                print(f"[{hand_label}] Jari: {jari_terbuka} | Petak: ({petak_kolom}, {petak_baris})")

                waktu_sekarang = time.time()
                if (waktu_sekarang - waktu_terakhir_kirim) > COOLDOWN_DOBOT:
                    kode_untuk_dobot(jari_terbuka, petak_kolom, petak_baris, device)
                    waktu_terakhir_kirim = waktu_sekarang 

        cv2.imshow("Hand Control - Grid System", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        loop_time = time.time() - loop_start_time
        if loop_time < FRAME_DELAY:
            time.sleep(FRAME_DELAY - loop_time)

video.release()
cv2.destroyAllWindows()