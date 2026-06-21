import cv2
import numpy as np
import sys
import argparse
import time
from Actuator import start_conveyor, stop_conveyor, arm_move, init_dobot

def main():
    # ==========================================
    # 1. PARSING ARGUMEN KOORDINAT PER WARNA
    # ==========================================
    # Menerima penugasan posisi grid untuk masing-masing warna dari HMI
    parser = argparse.ArgumentParser(description="Mode Otomatis Berbasis Rekognisi Warna HSV")
    parser.add_argument('--merah', nargs=2, type=int, help='Format: --merah col row')
    parser.add_argument('--hijau', nargs=2, type=int, help='Format: --hijau col row')
    parser.add_argument('--kuning', nargs=2, type=int, help='Format: --kuning col row')
    parser.add_argument('--biru', nargs=2, type=int, help='Format: --biru col row')
    args = parser.parse_args()

    # Simpan target grid ke dalam dictionary tugas jika dikonfigurasi dari HMI
    color_targets = {}
    if args.merah:   color_targets["Merah"]  = {"col": args.merah[0], "row": args.merah[1]}
    if args.hijau:  color_targets["Hijau"]  = {"col": args.hijau[0], "row": args.hijau[1]}
    if args.kuning: color_targets["Kuning"] = {"col": args.kuning[0], "row": args.kuning[1]}
    if args.biru:   color_targets["Biru"]   = {"col": args.biru[0], "row": args.biru[1]}

    if not color_targets:
        print("[ERROR] Tidak ada warna balok yang diberikan koordinat targetnya. Program dihentikan.")
        sys.exit(1)

    print("\n=== MEMULAI MODE OTOMATIS (COLOR RECOGNITION) ===")
    for color, target in color_targets.items():
        print(f"-> Balok [{color}] akan dikirim ke Grid: Kolom {target['col']}, Baris {target['row']}")
    print("=================================================\n")

    # ==========================================
    # 2. INISIALISASI HARDWARE (PERSIS MANUAL.PY)
    # ==========================================
    print("[VISION] Menghubungkan ke Dobot...")
    init_dobot()

    cap = cv2.VideoCapture(0) # Sesuaikan indeks kamera Anda
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FPS, 24)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) #ya

    # Database rentang warna HSV (Disamakan persis dengan Manual.py & Calibration.py)
    color_ranges = {
        "Merah": [ 
            (np.array([0, 120, 70]), np.array([10, 255, 255])),
            (np.array([170, 120, 70]), np.array([180, 255, 255]))
        ],
        "Hijau": [(np.array([40, 50, 50]), np.array([90, 255, 255]))],
        "Kuning": [(np.array([20, 100, 100]), np.array([30, 255, 255]))],
        "Biru": [(np.array([100, 150, 0]), np.array([140, 255, 255]))]
    }

    # Definisi kotak awal ROI (Disamakan persis dengan Manual.py)
    ROI_X, ROI_Y, ROI_W, ROI_H = 325, 100, 140, 280

    print("[VISION] Menjalankan conveyor & memulai scan area ROI...")
    start_conveyor()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Gagal membaca data frame dari kamera.")
                break

            # 1. Gambar kotak panduan visual ROI pada layar monitor
            cv2.rectangle(frame, (ROI_X, ROI_Y), (ROI_X + ROI_W, ROI_Y + ROI_H), (255, 0, 0), 2)
            cv2.putText(frame, "Area Deteksi Otomatis (ROI)", (ROI_X, ROI_Y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

            # 2. Potong frame fokus hanya pada area ROI
            roi_frame = frame[ROI_Y:ROI_Y + ROI_H, ROI_X:ROI_X + ROI_W]
            hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)

            object_detected_in_this_frame = False

            # 3. Looping pengecekan warna yang aktif ditugaskan saja
            for color_name, ranges in color_ranges.items():
                # Jika warna ini tidak diset posisinya dari HMI, lewati (skip)
                if color_name not in color_targets:
                    continue
                
                if object_detected_in_this_frame:
                    break

                # Buat mask warna balok
                mask = np.zeros(hsv.shape[:2], dtype="uint8")
                for lower, upper in ranges:
                    mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower, upper))

                # Reduksi Noise (Erode & Dilate)
                mask = cv2.erode(mask, None, iterations=2)
                mask = cv2.dilate(mask, None, iterations=2)

                contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                if contours:
                    c = max(contours, key=cv2.contourArea)
                    
                    # Cek threshold luas kontur minimal balok (> 500 piksel)
                    if cv2.contourArea(c) > 500:
                        M = cv2.moments(c)
                        if M["m00"] != 0:
                            # Hitung centroid lokal ROI
                            cX_roi = int(M["m10"] / M["m00"])
                            cY_roi = int(M["m01"] / M["m00"])
                            
                            # Konversi koordinat ke tingkat GLOBAL Frame Kamera
                            cX_global = cX_roi + ROI_X
                            cY_global = cY_roi + ROI_Y
                            
                            # A. Rem conveyor dengan cepat demi presisi titik koordinat
                            stop_conveyor()
                            object_detected_in_this_frame = True

                            # B. Ambil target koordinat drop-off yang sudah diassign untuk warna ini
                            target_col = color_targets[color_name]["col"]
                            target_row = color_targets[color_name]["row"]

                            # Render visual kotak hijau pengunci target objek sebelum lengan bergerak
                            x, y, w, h = cv2.boundingRect(c)
                            cv2.rectangle(frame, (x + ROI_X, y + ROI_Y), (x + w + ROI_X, y + h + ROI_Y), (0, 255, 0), 2)
                            cv2.circle(frame, (cX_global, cY_global), 5, (255, 255, 255), -1)
                            cv2.putText(frame, f"TARGET: {color_name}", (cX_global - 20, cY_global - 20), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                            cv2.imshow("Camera Feed - Auto Mode", frame)
                            cv2.waitKey(1)

                            # C. Eksekusi pergerakan pick and place lengan robot Dobot Magician
                            print(f"\n[SORT] Menemukan balok {color_name}!")
                            print(f"[AKSI] Menggerakkan robot ke ({cX_global}, {cY_global}) -> Kirim ke Grid ({target_col}, {target_row})")
                            
                            arm_move(cX_global, cY_global, color_name, target_col, target_row)
                            print(f"[AKSI] Selesai menata balok {color_name}.\n")

                            # D. Jalankan kembali conveyor belt untuk mencari balok berikutnya
                            print("[VISION] Menjalankan kembali conveyor...")
                            start_conveyor()
                            
                            # Flush buffer kamera (Buang 5 frame lawas agar tidak double detect akibat lagging)
                            for _ in range(5): 
                                cap.read()
                            break

            # Tampilkan feed kamera monitor real-time
            cv2.imshow("Camera Feed - Auto Mode", frame)
            
            # Tekan 'q' pada keyboard monitor untuk keluar secara aman
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[INFO] Program dihentikan melalui tombol 'q'.")
                break

    except KeyboardInterrupt:
        print("\n[WARNING] Mode otomatis dihentikan paksa oleh pengguna (Ctrl+C).")
    finally:
        # Menutup perangkat dan melepas koneksi kamera dengan aman
        cap.release()
        cv2.destroyAllWindows()
        stop_conveyor()
        print("[SISTEM] Mode otomatis selesai. Mengembalikan kendali ke HMI.\n")
        sys.exit(0)

if __name__ == "__main__":
    main()