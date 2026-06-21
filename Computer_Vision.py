import cv2
import numpy as np
from Actuator import stop_conveyor

COLOR_RANGES = {
    "Merah": [
        (np.array([0, 120, 70]), np.array([10, 255, 255])),
        (np.array([170, 120, 70]), np.array([180, 255, 255]))
    ],
    "Hijau": [(np.array([40, 50, 50]), np.array([90, 255, 255]))],
    "Kuning": [(np.array([20, 100, 100]), np.array([30, 255, 255]))],
    "Biru": [(np.array([100, 150, 0]), np.array([140, 255, 255]))]
}

# Definisi ROI (Area Deteksi). Sesuaikan dengan posisi fisik conveyor di kamera.
ROI_X, ROI_Y, ROI_W, ROI_H = 215, 100, 140, 280
MIN_CONTOUR_AREA = 500

def is_inside_roi(cX, cY):
    """True jika titik (koordinat global) berada di dalam batas ROI."""
    return ROI_X <= cX <= ROI_X + ROI_W and ROI_Y <= cY <= ROI_Y + ROI_H

def setup_camera(fps=30, width=640, height=480):
    """Inisialisasi VideoCapture dengan parameter standar yang dipakai kedua mode."""
    cap = cv2.VideoCapture(0)  # Sesuaikan indeks kamera Anda (0, 1, atau 2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def draw_roi(frame, label):
    """Gambar kotak batas ROI beserta label statusnya di frame."""
    cv2.rectangle(frame, (ROI_X, ROI_Y), (ROI_X + ROI_W, ROI_Y + ROI_H), (255, 0, 0), 2)
    cv2.putText(frame, label, (ROI_X, ROI_Y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)


def build_mask(hsv, ranges):
    # Segmentasi warna + reduksi noise (erode & dilate).
    mask = np.zeros(hsv.shape[:2], dtype="uint8")
    for lower, upper in ranges:
        mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower, upper))
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)
    return mask


def detect_largest_object(hsv, ranges, min_area=MIN_CONTOUR_AREA):
    mask = build_mask(hsv, ranges)
    contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) <= min_area:
        return None

    M = cv2.moments(c)
    if M["m00"] == 0:
        return None

    cX = int(M["m10"] / M["m00"])
    cY = int(M["m01"] / M["m00"])
    
    # 1. Dapatkan rectangle dengan orientasi sudut
    rect = cv2.minAreaRect(c)
    
    # 2. Ekstrak 4 titik sudut dari rect untuk keperluan visualisasi (box)
    box = cv2.boxPoints(rect)
    box = np.intp(box) 
    
    # 3. Ekstrak sudut mentah dari OpenCV
    angle = rect[2]

    # 4. Normalisasi Sudut untuk Persegi
    # Karena objek dipastikan persegi, rotasi 90 derajat menghasilkan wujud yang identik.
    # Stabilkan sudut menggunakan modulo agar selalu berada di rentang [0, 90).
    normalized_angle = angle % 90
    
    # Opsional: Geser rentang menjadi [-45, 45] untuk meminimalkan jarak putar 
    # motor servo pada end-effector (Dobot).
    if normalized_angle > 45:
        normalized_angle -= 90

    return cX, cY, box, normalized_angle

def draw_detection(frame, box, cX, cY, label, angle):
    # Menggambar kotak pembatas yang mengikuti kemiringan objek
    cv2.drawContours(frame, [box], 0, (0, 255, 0), 2)
    
    # Menandai titik tengah
    cv2.circle(frame, (cX, cY), 5, (255, 255, 255), -1)
    
    # Menampilkan label dan sudut
    info_text = f"{label} | A: {angle:.1f} deg"
    cv2.putText(frame, info_text, (cX - 40, cY - 20), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

def cleanup(cap):
    # Membersihkan koneksi peripheral, kamera, dan mengamankan conveyor belt."""
    cap.release()
    cv2.destroyAllWindows()
    stop_conveyor()
    print("[SISTEM] Proses selesai. Mengembalikan kendali penuh ke GUI HMI.\n")