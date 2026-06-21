import time
import numpy as np
import sys
from serial.tools import list_ports
import cv2
from pydobotplus import Dobot

device = None


def connect_dobot():
    """
    Mencari port serial dan membuka koneksi ke Dobot.
    Tidak melakukan homing di sini.
    """
    global device

    available_ports = list(list_ports.comports())

    if not available_ports:
        print("[ERROR] Tidak ada port serial yang terdeteksi.")
        sys.exit(1)

    print("[INFO] Port serial yang terdeteksi:")
    for i, p in enumerate(available_ports):
        print(f"  [{i}] {p.device} - {p.description}")

    # Pilih port pertama secara default.
    # Jika sistem Anda selalu butuh port tertentu, ubah di sini.
    port = available_ports[1].device

    print(f"[INFO] Mencoba terhubung ke Dobot di port: {port}...")
    try:
        device = Dobot(port=port)
        print("[INFO] Dobot terhubung berhasil.")
    except Exception as e:
        print(f"[ERROR] Gagal connect ke Dobot: {e}")
        device = None

    return device


# =========================================================
# KONFIGURASI KOORDINAT DOBOT
# =========================================================
Z_HOVER = 50
Z_PICK = -12
HOME_R = 0

HOME_X = 4.5
HOME_Y = 270
HOME_Z = 50

CONVEYOR_SPEED = 0.45
CONVEYOR_DELAY = 1.16


# =========================================================
# KALIBRASI KAMERA -> DOBOT
# =========================================================
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

MATRIKS_KALIBRASI, status = cv2.findHomography(pts_kamera, pts_dobot)


def coordinate_transform(cam_x, cam_y):
    """
    Mengubah koordinat piksel kamera menjadi koordinat milimeter Dobot.
    """
    if MATRIKS_KALIBRASI is None:
        raise RuntimeError("Matriks kalibrasi tidak tersedia.")

    titik_kamera = np.array([[[float(cam_x), float(cam_y)]]], dtype="float32")
    titik_dobot = cv2.perspectiveTransform(titik_kamera, MATRIKS_KALIBRASI)

    dobot_x = float(titik_dobot[0][0][0])
    dobot_y = float(titik_dobot[0][0][1])

    return round(dobot_x, 2), round(dobot_y, 2)


def get_drop_coordinates(target_col, target_row):
    """
    Mengambil koordinat tujuan drop berdasarkan grid.
    """
    grid_coordinates = {
        1: {1: (-18.3, 197.1), 2: (6.13, 197.1), 3: (30.57, 197.1), 4: (55.0, 197.1)},
        2: {1: (-18.3, 222.73), 2: (6.13, 222.73), 3: (30.57, 222.73), 4: (55.0, 222.73)},
        3: {1: (-18.3, 248.37), 2: (6.13, 248.37), 3: (30.57, 248.37), 4: (55.0, 248.37)},
        4: {1: (-18.3, 274.0), 2: (6.13, 274.0), 3: (30.57, 274.0), 4: (55.0, 274.0)},
    }

    if target_col not in grid_coordinates or target_row not in grid_coordinates[target_col]:
        raise ValueError(f"Grid target tidak valid: ({target_col}, {target_row})")

    return grid_coordinates[target_col][target_row]


def arm_move(cam_x, cam_y, color, target_col, target_row, angle=0.0):
    """
    Menjalankan urutan pick and place.
    """
    global device

    if device is None:
        print("[ERROR] Dobot tidak terhubung. Mengabaikan perintah gerak.")
        return

    try:
        drop_x, drop_y = get_drop_coordinates(target_col, target_row)
        print(
            f"[ARM] Target penempatan fisik: "
            f"Grid({target_col},{target_row}) -> Dobot X:{drop_x}, Y:{drop_y}"
        )
    except ValueError as e:
        print(f"[ERROR] {e}")
        return

    try:
        target_x, target_y = coordinate_transform(cam_x, cam_y)
    except Exception as e:
        print(f"[ERROR] Gagal transform koordinat kamera ke Dobot: {e}")
        return

    print(
        f"[ARM] Menerima tugas: Objek {color} di Kamera({cam_x}, {cam_y}) "
        f"-> Dobot({target_x}, {target_y})"
    )

    suction_active = False

    try:
        print("[ARM] Bergerak ke titik aman di atas objek...")
        device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

        print("[ARM] Turun mengambil objek...")
        device.move_to(target_x, target_y, Z_PICK, HOME_R, wait=True)

        device.suck(True)
        suction_active = True
        time.sleep(1)

        print("[ARM] Naik kembali ke posisi aman...")
        device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

        print(f"[ARM] Menaruh objek {color} ke Grid ({target_col}, {target_row})...")
        device.move_to(drop_x, drop_y, Z_HOVER, angle, wait=True)
        device.move_to(drop_x, drop_y, -45, angle, wait=True)

        device.suck(False)
        suction_active = False
        time.sleep(1)

        print("[ARM] Naik lagi ke posisi aman...")
        device.move_to(drop_x, drop_y, Z_HOVER, angle, wait=True)

        print("[ARM] Kembali ke Home...")
        device.move_to(HOME_X, HOME_Y, HOME_Z, HOME_R, wait=True)

    except Exception as e:
        print(f"[ERROR] Gagal menjalankan urutan arm_move: {e}")

    finally:
        if suction_active:
            try:
                device.suck(False)
            except Exception:
                pass


def start_conveyor():
    global device
    if device is None:
        print("[ERROR] Dobot tidak terhubung. Tidak bisa menjalankan conveyor.")
        return

    print("[CONVEYOR] START")
    device.conveyor_belt(speed=CONVEYOR_SPEED, direction=1)


def stop_conveyor():
    global device
    if device is None:
        print("[ERROR] Dobot tidak terhubung. Tidak bisa menghentikan conveyor.")
        return

    print("[CONVEYOR] STOP")
    device.conveyor_belt(speed=0, direction=1)