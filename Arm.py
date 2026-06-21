import time
import numpy as np
import cv2

# --- KONFIGURASI KOORDINAT DOBOT ---
# Sesuaikan nilai Z ini dengan kondisi fisik meja/conveyor Anda
Z_HOVER = 50   # Ketinggian aman (melayang di atas conveyor) agar tidak menabrak benda lain
Z_PICK = -12   # Ketinggian saat menempel pada objek (menyentuh conveyor)
HOME_R = 0     # Rotasi default end-effector

# Titik istirahat robot (Home)
HOME_X = 4.5
HOME_Y = 270
HOME_Z = 50

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

def arm_move(device, cam_x, cam_y, color, target_col, target_row):
    """
    Menjalankan urutan pergerakan lengan robot (Pick and Place).
    """
    if device is None:
        print("[ERROR] Dobot tidak terhubung. Mengabaikan perintah gerak.")
        return
    
    grid_coordinates = {
        1: {1: (-18, 198), 2: (6.33, 198), 3: (30.67, 198), 4: (55, 198)},
        2: {1: (-18, 233.67), 2: (6.33, 233.67), 3: (30.67, 233.67), 4: (55, 233.67)},
        3: {1: (-18, 249.33), 2: (6.33, 249.33), 3: (30.67, 249.33), 4: (55, 249.33)},
        4: {1: (-18, 275), 2: (6.33, 275), 3: (30.67, 275), 4: (55, 275)},
    }   

    try: 
        drop_x, drop_y = grid_coordinates[target_col][target_row]
        print(f"[ARM] Menghitung target penempatan fisik: Grid({target_col},{target_row}) -> Dobto X:{drop_x}, Y:{drop_y}")
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
    time.sleep(0.5) # Beri waktu agar objek benar-benar terlepas
    
    # Naik lagi ke posisi aman
    device.move_to(drop_x, drop_y, Z_HOVER, HOME_R, wait=True)

    # 7. Kembali ke posisi standby (Home)
    print("[ARM] Selesai. Kembali ke Home.")
    device.move_to(HOME_X, HOME_Y, HOME_Z, HOME_R, wait=True)