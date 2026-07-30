import cv2
import time
import random
import sys

# Impor fungsi-fungsi fundamental dari file yang sudah ada
from Actuator import (
    connect_dobot, start_conveyor, stop_conveyor, 
    coordinate_transform, Z_HOVER, Z_PICK, HOME_R
)
from Computer_Vision import (
    setup_camera, cleanup, detect_largest_object, 
    COLOR_RANGES, is_inside_pick_zone
)

# =========================================================
# TITIK STANDBY (Posisi setelah homing)
# =========================================================
STANDBY_X = 111
STANDBY_Y = -191
STANDBY_Z = 100

def main():
    # 1. Robot Homing
    print("[INFO] Menghubungkan ke Dobot...")
    device = connect_dobot()
    if device is None:
        print("[ERROR] Dobot tidak terhubung. Keluar.")
        sys.exit(1)

    print("[INFO] Memulai proses Homing (sekitar 20 detik)...")
    device.home()
    time.sleep(30)

    # 2. Pergi ke titik yang ditentukan tepat setelah homing
    print("[INFO] Homing selesai. Bergerak ke titik standby...")
    device.move_to(STANDBY_X, STANDBY_Y, STANDBY_Z, HOME_R, wait=True)

    # 3. Kamera menyala
    print("[INFO] Menyalakan kamera...")
    cap = setup_camera()

    # 4. Conveyor berjalan
    print("[INFO] Menjalankan conveyor...")
    start_conveyor()

    print("\n=== SISTEM LOOPING AKTIF ===")
    print("Tekan 'q' pada jendela kamera atau Ctrl+C di terminal untuk berhenti.\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            objek_ditemukan = None

            # 5. Kamera mendeteksi objek
            # Melakukan scanning untuk semua rentang warna yang ada
            for color_name, ranges in COLOR_RANGES.items():
                hasil = detect_largest_object(hsv, ranges)
                if hasil:
                    cX, cY, box, angle = hasil
                    
                    # Memastikan objek sudah masuk area ambil (Pick Zone)
                    if is_inside_pick_zone(cX, cY):
                        objek_ditemukan = (cX, cY, angle, color_name)
                        break

            # Jika ada objek yang valid untuk diambil
            if objek_ditemukan:
                cX, cY, angle, color_name = objek_ditemukan
                print(f"\n[VISION] Objek {color_name} terdeteksi di ({cX}, {cY}).")

                # Hentikan conveyor sebelum mengambil
                stop_conveyor()
                time.sleep(0.25)

                # 6. Arm mengambil objek
                target_x, target_y = coordinate_transform(cX, cY)
                print(f"[ARM] Mengambil objek di koordinat Dobot ({target_x}, {target_y})...")

                device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)
                device.move_to(target_x, target_y, Z_PICK, HOME_R, wait=True)
                device.suck(True)
                time.sleep(1)
                device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

                # 7. Arm memindahkan objek ke posisi acak
                rand_x = random.uniform(175, 220)
                rand_y = random.uniform(-240, -165)
                rand_angle = random.uniform(0, 45)
                print(f"[ARM] Memindahkan objek ke posisi acak X: {rand_x:.2f}, Y: {rand_y:.2f}...")

                device.move_to(rand_x, rand_y, Z_HOVER, angle, wait=True)
                # Turun ke Z=-8 untuk menaruh objek seperti pada skrip aslinya
                device.move_to(rand_x, rand_y, -8, rand_angle, wait=True) 

                # 8. Arm melepas objek
                device.suck(False)
                time.sleep(1)
                
                # Naik kembali ke posisi aman
                device.move_to(rand_x, rand_y, Z_HOVER, rand_angle, wait=True)
                device.move_to(STANDBY_X, STANDBY_Y, STANDBY_Z, HOME_R, wait=True)

                # 9. Conveyor kembali jalan (Loop)
                print("[INFO] Operasi selesai. Conveyor berjalan kembali.")
                start_conveyor()

                # Membuang frame lama dari buffer kamera agar tidak ada false positive
                for _ in range(5):
                    cap.read()

            # Menampilkan frame visual (Opsional, agar Anda tahu apa yang dilihat kamera)
            cv2.imshow("Kamera Dobot", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n[INFO] Dihentikan paksa oleh pengguna.")
    finally:
        cleanup(cap)
        print("[INFO] Sistem dimatikan dengan aman.")

if __name__ == "__main__":
    main()