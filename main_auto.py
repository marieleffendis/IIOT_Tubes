import cv2
import numpy as np
import sys
import argparse
import time
from serial.tools import list_ports
from pydobotplus import Dobot

# Import modul peripheral baru Anda
import Conveyor
from Conveyor import start_conveyor, stop_conveyor
from Arm import arm_move

def main():
    # ==========================================
    # 1. PARSING ARGUMEN MULTI-KOORDINAT DARI HMI
    # ==========================================
    parser = argparse.ArgumentParser(description="Smart Auto-Sort Mode Berbasis Penugasan Grid Visual HMI")
    parser.add_argument("--merah", nargs="*", default=[], help="Daftar grid merah, contoh: 1,1 2,1")
    parser.add_argument("--kuning", nargs="*", default=[], help="Daftar grid kuning")
    parser.add_argument("--hijau", nargs="*", default=[], help="Daftar grid hijau")
    parser.add_argument("--biru", nargs="*", default=[], help="Daftar grid biru")
    args = parser.parse_args()

    # Struktur penyimpanan antrean target grid per warna
    misi_aktif = {"Merah": [], "Kuning": [], "Hijau": [], "Biru": []}
    
    def parse_pairs(pair_list):
        result = []
        for pair in pair_list:
            if ',' in pair:
                try:
                    c, r = map(int, pair.split(','))
                    result.append((c, r))
                except ValueError:
                    pass
        return result

    misi_aktif["Merah"]  = parse_pairs(args.merah)
    misi_aktif["Kuning"] = parse_pairs(args.kuning)
    misi_aktif["Hijau"]  = parse_pairs(args.hijau)
    misi_aktif["Biru"]   = parse_pairs(args.biru)

    total_misi = sum(len(v) for v in misi_aktif.values())
    misi_selesai = 0

    if total_misi == 0:
        print("[ERROR] Tidak ada target koordinat grid yang diterima dari HMI.")
        sys.exit(1)

    # ==========================================
    # 2. INISIALISASI PERIPHERAL & KONEKSI ROBOT
    # ==========================================
    print("[VISION] Menghubungkan langsung ke Dobot via Conveyor interface...")
    available_ports = list(list_ports.comports())
    if not available_ports:
        print("[ERROR] Port serial tidak ditemukan.")
        sys.exit(1)
        
    port = available_ports[1].device if len(available_ports) > 1 else available_ports[0].device
    device = Dobot(port=port)
    
    # Bagikan instansiasi device global ke modul Conveyor
    Conveyor.device = device

    # ==========================================
    # 3. KONFIGURASI VISION (HSV & ROI)
    # ==========================================
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FPS, 24)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    color_ranges = {
        "Merah": [
            (np.array([0, 120, 70]), np.array([10, 255, 255])),
            (np.array([170, 120, 70]), np.array([180, 255, 255]))
        ],
        "Hijau": [(np.array([40, 50, 50]), np.array([90, 255, 255]))],
        "Kuning": [(np.array([20, 100, 100]), np.array([30, 255, 255]))],
        "Biru": [(np.array([100, 150, 0]), np.array([140, 255, 255]))]
    }

    ROI_X, ROI_Y, ROI_W, ROI_H = 325, 100, 140, 280

    print("\n[SISTEM] Memulai sorting otomatis. Menjalankan conveyor...")
    start_conveyor()

    try:
        while misi_selesai < total_misi:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Gagal menangkap frame kamera.")
                break

            # Gambar batas ROI panduan visual
            cv2.rectangle(frame, (ROI_X, ROI_Y), (ROI_X + ROI_W, ROI_Y + ROI_H), (255, 0, 0), 2)
            roi_frame = frame[ROI_Y:ROI_Y+ROI_H, ROI_X:ROI_X+ROI_W]
            hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)

            for color_name, targets in misi_aktif.items():
                if not targets:
                    continue  # Lewati jika antrean warna ini sudah kosong

                # Pembuatan mask filter warna HSV
                ranges = color_ranges.get(color_name, [])
                mask = np.zeros(hsv.shape[:2], dtype="uint8")
                for lower, upper in ranges:
                    mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower, upper))

                mask = cv2.erode(mask, None, iterations=2)
                mask = cv2.dilate(mask, None, iterations=2)

                contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                if contours:
                    c = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(c) > 500:
                        M = cv2.moments(c)
                        if M["m00"] != 0:
                            cX_roi = int(M["m10"] / M["m00"])
                            cY_roi = int(M["m01"] / M["m00"])
                            cX_global = cX_roi + ROI_X
                            cY_global = cY_roi + ROI_Y

                            # Ambil koordinat tujuan terdepan dari list antrean
                            target_col, target_row = targets.pop(0)
                            
                            # Hentikan conveyor seketika objek dikunci
                            stop_conveyor()
                            print(f"[DETEKSI] Menemukan balok {color_name} pada koordinat Piksel ({cX_global}, {cY_global})")
                            print(f"           -> Target Drop: Grid Kolom {target_col}, Baris {target_row}")

                            # Gambar umpan balik visual sebelum lengan menghalangi
                            x, y, w, h = cv2.boundingRect(c)
                            cv2.rectangle(frame, (x + ROI_X, y + ROI_Y), (x + w + ROI_X, y + h + ROI_Y), (0, 255, 0), 2)
                            cv2.circle(frame, (cX_global, cY_global), 5, (255, 255, 255), -1)
                            cv2.imshow("Camera Feed - Auto Mode", frame)
                            cv2.waitKey(1)

                            # Eksekusi pergerakan lengan robot Dobot ke grid tujuan
                            arm_move(device, cX_global, cY_global, color_name, target_col, target_row)
                            
                            misi_selesai += 1
                            print(f"[STATUS] Progress penataan: {misi_selesai}/{total_misi} selesai.\n")

                            if misi_selesai < total_misi:
                                print("[VISION] Menjalankan kembali conveyor...")
                                start_conveyor()
                                # Mengosongkan sisa frame buffer agar terhindar dari deteksi ganda akibat lag
                                for _ in range(5):
                                    cap.read()
                            break

            cv2.imshow("Camera Feed - Auto Mode", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[INFO] Program dihentikan melalui tombol 'q'.")
                break

        print("\n[BERHASIL] Seluruh penataan balok sesuai peta grid HMI selesai!")

    except KeyboardInterrupt:
        print("\n[WARNING] Mode otomatis dihentikan paksa oleh pengguna.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        stop_conveyor()
        device.close()
        print("[SISTEM] Pemrosesan selesai. Mengembalikan kendali penuh ke GUI HMI.\n")
        sys.exit(0)

if __name__ == "__main__":
    main()