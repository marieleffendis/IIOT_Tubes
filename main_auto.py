import cv2
import numpy as np
import sys
import argparse
import time
from Conveyor import start_conveyor, stop_conveyor, init_dobot
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

    # Struktur penyimpanan antrean target grid per warna: {"Warna": [(col, row), ...]}
    misi_aktif = {"Merah": [], "Kuning": [], "Hijau": [], "Biru": []}
    
    # Fungsi pembantu untuk memisah teks "kolom,baris" menjadi tuple (int, int)
    def parse_pairs(pair_list):
        result = []
        for pair in pair_list:
            if ',' in pair:
                try:
                    c, r = map(int, pair.split(','))
                    result.append((c, r))
                except ValueError:
                    continue
        return result

    # Memasukkan hasil parsing dari GUI ke dalam antrean misi
    misi_aktif["Merah"]  = parse_pairs(args.merah)
    misi_aktif["Kuning"] = parse_pairs(args.kuning)
    misi_aktif["Hijau"]  = parse_pairs(args.hijau)
    misi_aktif["Biru"]   = parse_pairs(args.biru)
    
    # Hitung total balok yang ditugaskan untuk diproses
    total_misi = sum(len(coords) for coords in misi_aktif.values())
    if total_misi == 0:
        print("[ERROR] Tidak ada koordinat target grid yang dipilih dari HMI. Program dihentikan.")
        sys.exit(1)

    print("\n=== MEMULAI MODE OTOMATIS (COLOR GRID RECOGNITION) ===")
    for warna, target_list in misi_aktif.items():
        if target_list:
            grid_str = ", ".join([f"({c},{r})" for c, r in target_list])
            print(f"-> Balok [{warna}] akan ditata sekuensial ke Grid: {grid_str}")
    print(f"Total target pengerjaan: {total_misi} balok.")
    print("======================================================\n")

    # ==========================================
    # 2. INISIALISASI HARDWARE & KAMERA
    # ==========================================
    print("[VISION] Menghubungkan ke Dobot...")
    init_dobot()

    cap = cv2.VideoCapture(0)  # Sesuaikan indeks kamera Anda (0, 1, atau 2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FPS, 24)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Database rentang warna HSV (Disamakan dengan Manual.py & Calibration.py)
    color_ranges = {
        "Merah": [ 
            (np.array([0, 120, 70]), np.array([10, 255, 255])),
            (np.array([170, 120, 70]), np.array([180, 255, 255]))
        ],
        "Hijau": [(np.array([40, 50, 50]), np.array([90, 255, 255]))],
        "Kuning": [(np.array([20, 100, 100]), np.array([30, 255, 255]))],
        "Biru": [(np.array([100, 150, 0]), np.array([140, 255, 255]))]
    }

    # Definisi ROI (Disamakan persis dengan Manual.py)
    ROI_X, ROI_Y, ROI_W, ROI_H = 325, 100, 140, 280
    misi_selesai = 0

    print("[VISION] Menjalankan conveyor & memulai pemindaian area ROI...")
    start_conveyor()

    # ==========================================
    # 3. CORE LOOP PEMROSESAN OTOMATIS
    # ==========================================
    try:
        while misi_selesai < total_misi:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Gagal membaca data frame dari kamera.")
                break

            # Gambar batas kotak area deteksi ROI
            cv2.rectangle(frame, (ROI_X, ROI_Y), (ROI_X + ROI_W, ROI_Y + ROI_H), (255, 0, 0), 2)
            cv2.putText(frame, f"Area Deteksi Otomatis ({misi_selesai}/{total_misi})", (ROI_X, ROI_Y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

            # Potong citra gambar agar fokus dalam ROI
            roi_frame = frame[ROI_Y:ROI_Y + ROI_H, ROI_X:ROI_X + ROI_W]
            hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)

            object_detected_in_this_frame = False

            # Lakukan scan warna berdasarkan urutan database warna
            for color_name, ranges in color_ranges.items():
                # Jika kuota target untuk warna ini sudah habis atau tidak ada, lewati
                if not misi_aktif[color_name]:
                    continue
                
                if object_detected_in_this_frame:
                    break

                # Segmentasi thresholding warna
                mask = np.zeros(hsv.shape[:2], dtype="uint8")
                for lower, upper in ranges:
                    mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower, upper))

                # Reduksi derau noise gambar (Erode & Dilate)
                mask = cv2.erode(mask, None, iterations=2)
                mask = cv2.dilate(mask, None, iterations=2)

                contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                if contours:
                    c = max(contours, key=cv2.contourArea)
                    
                    # Filter luas piksel minimal objek balok
                    if cv2.contourArea(c) > 500:
                        M = cv2.moments(c)
                        if M["m00"] != 0:
                            # Hitung letak centroid lokal ROI
                            cX_roi = int(M["m10"] / M["m00"])
                            cY_roi = int(M["m01"] / M["m00"])
                            
                            # Transformasi ke koordinat Kamera Global
                            cX_global = cX_roi + ROI_X
                            cY_global = cY_roi + ROI_Y
                            
                            # A. Hentikan conveyor sesegera mungkin demi presisi koordinat objek
                            stop_conveyor()
                            object_detected_in_this_frame = True

                            # B. Ambil target koordinat paling depan dari antrean warna ini (FIFO)
                            target_col, target_row = misi_aktif[color_name].pop(0)

                            # Gambarkan bounding box penanda target visual sebelum lengan bergerak
                            x, y, w, h = cv2.boundingRect(c)
                            cv2.rectangle(frame, (x + ROI_X, y + ROI_Y), (x + w + ROI_X, y + h + ROI_Y), (0, 255, 0), 2)
                            cv2.circle(frame, (cX_global, cY_global), 5, (255, 255, 255), -1)
                            cv2.putText(frame, f"TARGET: {color_name} -> Grid ({target_col},{target_row})", 
                                        (cX_global - 30, cY_global - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                            cv2.imshow("Camera Feed - Auto Mode", frame)
                            cv2.waitKey(1)

                            # C. Perintahkan Lengan Dobot untuk memindahkan objek ke target grid
                            print(f"\n[SORT] Menemukan objek warna {color_name}!")
                            print(f"[AKSI] Mengambil koordinat global ({cX_global}, {cY_global}) -> Menaruh ke Grid ({target_col}, {target_row})")
                            
                            arm_move(cX_global, cY_global, color_name, target_col, target_row)
                            
                            misi_selesai += 1
                            print(f"[STATUS] Progress penataan: {misi_selesai}/{total_misi} selesai.\n")

                            # D. Jalankan conveyor kembali jika target belum terpenuhi sepenuhnya
                            if misi_selesai < total_misi:
                                print("[VISION] Menjalankan kembali conveyor...")
                                start_conveyor()
                                # Buang frame lama di buffer kamera pasca-lengan bergerak bebas
                                for _ in range(5): 
                                    cap.read()
                            break

            # Tampilkan feed kamera real-time di layar monitor alat
            cv2.imshow("Camera Feed - Auto Mode", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[INFO] Program dihentikan melalui tombol 'q' pada jendela kamera.")
                break

        print("\n[BERHASIL] Seluruh penataan balok berdasarkan konfigurasi grid HMI SELESAI!")

    except KeyboardInterrupt:
        print("\n[WARNING] Mode otomatis dihentikan paksa oleh pengguna (Ctrl+C).")
    finally:
        # Membersihkan koneksi peripheral, kamera, dan mengamankan conveyor belt
        cap.release()
        cv2.destroyAllWindows()
        stop_conveyor()
        print("[SISTEM] Pemrosesan selesai. Mengembalikan kendali penuh ke GUI HMI.\n")
        sys.exit(0)

if __name__ == "__main__":
    main()