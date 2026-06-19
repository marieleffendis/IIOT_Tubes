import time
import numpy as np
import cv2

# --- KONFIGURASI KOORDINAT DOBOT ---
# Sesuaikan nilai Z ini dengan kondisi fisik meja/conveyor Anda
Z_HOVER = 50   # Ketinggian aman (melayang di atas conveyor) agar tidak menabrak benda lain
Z_PICK = -10   # Ketinggian saat menempel pada objek (menyentuh conveyor)
HOME_R = 0     # Rotasi default end-effector

# Titik istirahat robot (Home)
HOME_X = 4.5
HOME_Y = 270
HOME_Z = 50

pts_kamera = np.array([
    [440, 120], # Titik 1
    [440, 360], # Titik 2
    [340, 360], # Titik 3
    [340, 120]  # Titik 4
], dtype="float32")

pts_dobot = np.array([
    [168.5, -196],   # Titik 1
    [-14.6, -217.4],  # Titik 2
    [-24.4, -142.1],  # Titik 3
    [156.9, -118.8]   # Titik 4
], dtype="float32")

# Hitung Matriks Transformasi (Persamaan)
MATRIKS_KALIBRASI = cv2.getPerspectiveTransform(pts_kamera, pts_dobot)

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

def arm_move(device, cam_x, cam_y, color):
    """
    Menjalankan urutan pergerakan lengan robot (Pick and Place).
    """
    if device is None:
        print("[ERROR] Dobot tidak terhubung. Mengabaikan perintah gerak.")
        return

    # 1. Terjemahkan koordinat
    target_x, target_y = coordinate_transform(cam_x, cam_y)
    print(f"[ARM] Menerima tugas: Objek {color} di Kam({cam_x}, {cam_y}) -> Dobot({target_x}, {target_y})")

    # 2. Bergerak ke atas objek (Hover)
    # Gunakan wait=True agar program Python menunggu sampai robot selesai bergerak secara fisik
    print("[ARM] Bergerak ke titik aman di atas objek...")
    device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

    # 3. Turun dan ambil objek
    print("[ARmM] Turun mengabil objek...")
    device.move_to(target_x, target_y, Z_PICK, HOME_R, wait=True)
    
    # Nyalakan pompa hisap (Suction Cup) - Sesuaikan jika Anda pakai Gripper
    device.suck(True)
    time.sleep(0.5) # Beri jeda agar hisapan vakum menguat sebelum ditarik

    # 4. Naik kembali ke posisi Hover (membawa objek)
    device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

    # 5. Tentukan lokasi pembuangan (Drop-off) berdasarkan warna
    # (Silakan ubah koordinat X, Y pembuangan sesuai fisik di lapangan)
    """if color == "Merah":
        drop_x, drop_y = 150, 150
    elif color == "Biru":
        drop_x, drop_y = 150, -150
    elif color == "Hijau":
        drop_x, drop_y = 100, 150
    else:
        drop_x, drop_y = 200, 100 # Default/Kuning"""
    drop_x, drop_y = 20, 233

    # 6. Bergerak ke keranjang warna dan jatuhkan
    print(f"[ARM] Menaruh objek {color} ke area pembuangan...")
    device.move_to(drop_x, drop_y, Z_HOVER, HOME_R, wait=True)
    device.move_to(drop_x, drop_y, Z_PICK, HOME_R, wait=True)
    
    # Matikan hisapan
    device.suck(False)
    time.sleep(0.5) # Beri waktu agar objek benar-benar terlepas
    
    # Naik lagi ke posisi aman
    device.move_to(drop_x, drop_y, Z_HOVER, HOME_R, wait=True)

    # 7. Kembali ke posisi standby (Home)
    print("[ARM] Selesai. Kembali ke Home.")
    device.move_to(HOME_X, HOME_Y, HOME_Z, HOME_R, wait=True)