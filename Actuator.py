import time
import numpy as np
import cv2
import sys
from serial.tools import list_ports
from pydobotplus import Dobot

device = None

def init_dobot():
    # Mencari port dan menghubungkan ke Dobot (Logika lama kamu)
    available_ports = list(list_ports.comports())
    if not available_ports:
        print("[ERROR] Tidak ada port serial yang ditemukan.")
        return None

    if len(available_ports) > 1:
        port = available_ports[1].device
    else:
        port = available_ports[0].device
        
    print(f"[INFO] Mencoba terhubung ke Dobot di port: {port}...")
    try:
        device = Dobot(port=port)
        print("[INFO] Dobot terhubung berhasil.")
    except Exception as e:
        print(f"[ERROR] Gagal connect ke Dobot: {e}")
        return None

    print("[INFO] Memulai proses Homing. Pastikan area sekitar robot KOSONG!")
    print("[INFO] Menunggu homing selesai (20 detik)...")
    device.home()
    time.sleep(20) # Jeda manual untuk homing
    print("[INFO] Homing dianggap selesai, siap menjalankan conveyor!")
    return device

# --- KONFIGURASI KOORDINAT DOBOT ---
# Sesuaikan nilai Z ini dengan kondisi fisik meja/conveyor Anda
Z_HOVER = 50   # Ketinggian aman (melayang di atas conveyor) agar tidak menabrak benda lain
Z_PICK = -12   # Ketinggian saat menempel pada objek (menyentuh conveyor)
HOME_R = 0     # Rotasi default end-effector

# Titik istirahat robot (Home)
HOME_X = 4.5
HOME_Y = 270
HOME_Z = 50

# Kecepatan Conveyor
CONVEYOR_SPEED = 0.45       
CONVEYOR_DELAY = 1.16

pts_kamera = np.array([
    [330, 120],
    [327, 358],
    [230, 362],
    [230, 117],
    [312, 203],
    [308, 170],
    [274, 230],
    [319, 275],
    [268, 298],
    [325, 297],
    [269, 138],
    [242, 180],
    [237, 279],
    [256, 332],
    [294, 251],
], dtype="float32")

pts_dobot = np.array([
    [216.1, 141.5],
    [212.9, -43.2],
    [134.6, -43.2],
    [135.9, 142.5],
    [198.7, 79.1],
    [196.3, 102.9],
    [169.5, 57.8],
    [204.7, 20.8],
    [164.3, 5.1],
    [209.7, 6.3],
    [168.2, 126.7],
    [144.6, 95.1],
    [139.8, 20.2],
    [157.6, -21.2],
    [186.4, 41.4],
], dtype="float32")

# Hitung Matriks Transformasi (Persamaan)
MATRIKS_KALIBRASI, status = cv2.findHomography(pts_kamera, pts_dobot)

# --- FUNGSI TRANSLASI ---
def coordinate_transform(cam_x, cam_y):
    """
    Mengubah koordinat piksel kamera menjadi milimeter Dobot.
    """
    # Bentuk array sesuai format yang diminta OpenCV
    titik_kamera = np.array([[[float(cam_x), float(cam_y)]]], dtype="float32")
    
    # Aplikasikan persamaan matriks
    titik_dobot = cv2.perspectiveTransform(titik_kamera, MATRIKS_KALIBRASI)
    
    # Ekstrak hasil X dan Y
    dobot_x = titik_dobot[0][0][0]
    dobot_y = titik_dobot[0][0][1]
    
    return round(dobot_x, 2), round(dobot_y, 2)

def arm_move(cam_x, cam_y, color, target_col, target_row):
    """
    Menjalankan urutan pergerakan lengan robot (Pick and Place).
    """
    if device is None:
        print("[ERROR] Dobot tidak terhubung. Mengabaikan perintah gerak.")
        return
    
    grid_coordinates = {
        1: {1: (-18.3, 197.1), 2: (6.13, 197.1), 3: (30.57, 197.1), 4: (55, 197.1)},
        2: {1: (-18.3, 222.73), 2: (6.13, 222.73), 3: (30.57, 222.73), 4: (55, 222.73)},
        3: {1: (-18.3, 248.37), 2: (6.13, 248.37), 3: (30.57, 248.37), 4: (55, 248.37)},
        4: {1: (-18.3, 274), 2: (6.13, 274), 3: (30.57, 274), 4: (55, 274)},
    }  

    try: 
        drop_x, drop_y = grid_coordinates[target_col][target_row]
        print(f"[ARM] Menghitung target penempatan fisik: Grid({target_col},{target_row}) -> Dobot X:{drop_x}, Y:{drop_y}")
    except KeyError: 
        print("[PERINGATAN] Koordinat grid salah! Menggunakan koordinat default.")

    # 1. Terjemahkan koordinat
    target_x, target_y = coordinate_transform(cam_x, cam_y)
    print(f"[ARM] Menerima tugas: Objek {color} di Kam({cam_x}, {cam_y}) -> Dobot({target_x}, {target_y})")

    # 2. Bergerak ke atas objek (Hover)
    # Gunakan wait=True agar program Python menunggu sampai robot selesai bergerak secara fisik
    print("[ARM] Bergerak ke titik aman di atas objek...")
    device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

    # 3. Turun dan ambil objek
    print("[ARM] Turun mengabil objek...")
    device.move_to(target_x, target_y, Z_PICK, HOME_R, wait=True)
    
    # Nyalakan pompa hisap (Suction Cup) - Sesuaikan jika Anda pakai Gripper
    device.suck(True)
    time.sleep(1) # Beri jeda agar hisapan vakum menguat sebelum ditarik

    # 4. Naik kembali ke posisi Hover (membawa objek)
    device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

    # 5. Bergerak ke keranjang warna dan jatuhkan
    print(f"[ARM] Menaruh objek {color} ke area pembuangan Grid ({target_col}, {target_row})...")
    device.move_to(drop_x, drop_y, Z_HOVER, HOME_R, wait=True)
    device.move_to(drop_x, drop_y, -45, HOME_R, wait=True)
    
    # Matikan hisapan
    device.suck(False)
    time.sleep(1) # Beri waktu agar objek benar-benar terlepas
    
    # Naik lagi ke posisi aman
    device.move_to(drop_x, drop_y, Z_HOVER, HOME_R, wait=True)

    # 7. Kembali ke posisi standby (Home)
    print("[ARM] Selesai. Kembali ke Home.")
    device.move_to(HOME_X, HOME_Y, HOME_Z, HOME_R, wait=True)

def start_conveyor():
    print("[CONVEYOR] START")
    device.conveyor_belt(speed=CONVEYOR_SPEED, direction=1)

def stop_conveyor():
    print("[CONVEYOR] STOP")
    device.conveyor_belt(speed=0, direction=1)