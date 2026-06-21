import cv2
import numpy as np
import time
import sys
import argparse
from serial.tools import list_ports
from pydobotplus import Dobot
from ultralytics import YOLO  # Library untuk me-load model best.pt

# Import modul bawaan dari proyekmu
from Conveyor import start_conveyor, stop_conveyor
import Conveyor
from Arm import arm_move

# --- KUNCI PEMETAAN POSISI GRID (Template 4x4 maumu) ---
# Format format (x,y) -> (Kolom, Baris)
# Karena maumu (1,1) ada di B, maka pemetaan alfabet baris ke index angka:
ROW_MAP = {'A': 4, 'B': 1, 'C': 2, 'D': 3}

def dapatkan_misi_via_ml(image_path, model_path="best.pt"):
    """
    Menggunakan model Machine Learning YOLO (best.pt) untuk mendeteksi 
    letak kotak warna pada lembar target dan mengonversinya ke koordinat grid (col, row).
    """
    print(f"[ML-AI] Me-load model Machine Learning: {model_path}...")
    try:
        model = YOLO(model_path)
    except Exception as e:
        print(f"[ERROR] Gagal memuat model '{model_path}'. Pastikan file ada di folder yang sama. Error: {e}")
        sys.exit(1)

    # Jalankan prediksi model pada gambar target dari HMI
    print(f"[ML-AI] Menganalisis gambar target: {image_path}")
    results = model(image_path, conf=0.5)[0] # Confidence threshold 50%

    # Dictionary menampung misi target: { "Warna": [(col, row), (col, row)] }
    misi_target = {"Merah": [], "Hijau": [], "Biru": [], "Kuning": []}

    # Ambil ukuran gambar asli untuk kalkulasi pembagian grid secara dinamis
    orig_h, orig_w = results.orig_shape
    grid_w = orig_w / 4
    grid_h = orig_h / 4

    # Urutan label baris dan kolom pada kertas fisik Anda
    labels_row = ['A', 'B', 'C', 'D']
    labels_col = [1, 2, 3, 4]

    print("[ML-AI] Menghitung koordinat hasil prediksi model...")
    
    # Loop setiap objek yang berhasil dideteksi oleh YOLO best.pt
    for box in results.boxes:
        # Ambil koordinat tengah objek (Center X, Center Y)
        xyxy = box.xyxy[0].cpu().numpy()
        cX = (xyxy[0] + xyxy[2]) / 2
        cY = (xyxy[1] + xyxy[3]) / 2

        # Ambil ID kelas dan nama kelas (misal kelas 0: 'hijau', kelas 1: 'biru', dst)
        class_id = int(box.cls[0])
        class_name = results.names[class_id].capitalize() # Samakan kapitalisasi huruf awal

        # Tentukan objek berada di kolom ke berapa (0 sampai 3) dan baris berapa (0 sampai 3)
        col_idx = int(cX // grid_w)
        row_idx = int(cY // grid_h)

        # Batasi indeks agar tidak out of bounds jika deteksi di paling ujung kertas
        col_idx = max(0, min(3, col_idx))
        row_idx = max(0, min(3, row_idx))

        # Dapatkan label fisik alfabet/angka kertas
        nama_baris_fisik = labels_row[row_idx]
        nama_kolom_fisik = labels_col[col_idx]

        # Konversi nama baris alfabet ke koordinat angka pesanan robot maumu
        target_col = nama_kolom_fisik
        target_row = ROW_MAP[nama_baris_fisik]

        # Simpan ke daftar misi jika termasuk warna yang didukung oleh sistem sortir
        if class_name in misi_target:
            misi_target[class_name].append((target_col, target_row))
            print(f"   [AI DETECTED] -> {class_name} ditemukan di area Kotak ({nama_kolom_fisik}, {nama_baris_fisik}) -> Misi Robot: Grid ({target_col}, {target_row})")

    return misi_target


def main():
    parser = argparse.ArgumentParser(description="Smart Auto-Sort Mode Berbasis ML YOLO best.pt")
    parser.add_argument("--image", required=True, help="Path ke gambar cetakan layout 4x4")
    args = parser.parse_args()

    # 1. Ekstrak peta posisi akhir objek menggunakan Model Machine Learning
    misi_aktif = dapatkan_misi_via_ml(args.image, model_path="best.pt")
    
    # Hitung total objek yang harus disortir
    total_misi = sum(len(coords) for coords in misi_aktif.values())
    if total_misi == 0:
        print("[AUTO] Model ML tidak mendeteksi adanya kotak warna yang valid. Misi dibatalkan.")
        sys.exit(1)
    
    print(f"[AUTO] ML Sukses! Ditemukan {total_misi} target penataan pada gambar.\n")

    # 2. Hubungkan langsung ke Dobot tanpa Homing ulang
    available_ports = list(list_ports.comports())
    if not available_ports:
        print("[ERROR] Port Dobot tidak ditemukan.")
        sys.exit(1)
        
    port = available_ports[1].device if len(available_ports) > 1 else available_ports[0].device
    print(f"[AUTO] Menyambungkan ke Dobot pada port {port}...")
    device = Dobot(port=port)
    Conveyor.device = device 

    # 3. Aktifkan Kamera Scanner Conveyor
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Koordinat ROI deteksi conveyor milikmu
    ROI_X, ROI_Y, ROI_W, ROI_H = 325, 100, 140, 280
    
    color_ranges_live = {
        "Merah": [(np.array([0, 120, 70]), np.array([10, 255, 255])),
                  (np.array([170, 120, 70]), np.array([180, 255, 255]))],
        "Hijau": [(np.array([40, 50, 50]), np.array([90, 255, 255]))],
        "Kuning": [(np.array([20, 100, 100]), np.array([30, 255, 255]))],
        "Biru": [(np.array([100, 150, 0]), np.array([140, 255, 255]))]
    }

    # Mulai jalankan Conveyor untuk menyuplai benda
    start_conveyor()
    misi_selesai = 0

    try:
        # Loop berjalan otomatis sampai seluruh target dari AI terpenuhi
        while misi_selesai < total_misi:
            ret, frame = cap.read()
            if not ret:
                break

            roi_frame = frame[ROI_Y:ROI_Y + ROI_H, ROI_X:ROI_X + ROI_W]
            hsv_live = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
            benda_ditemukan = False

            for color_name, ranges in color_ranges_live.items():
                if benda_ditemukan:
                    break

                mask = np.zeros(hsv_live.shape[:2], dtype="uint8")
                for lower, upper in ranges:
                    mask = cv2.bitwise_or(mask, cv2.inRange(hsv_live, lower, upper))

                mask = cv2.erode(mask, None, iterations=2)
                mask = cv2.dilate(mask, None, iterations=2)
                contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                if contours:
                    c = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(c) > 500:
                        # Cek apakah warna benda di conveyor ini masih dibutuhkan oleh antrean misi ML
                        if len(misi_aktif[color_name]) > 0:
                            M = cv2.moments(c)
                            if M["m00"] != 0:
                                cX_global = int(M["m10"] / M["m00"]) + ROI_X
                                cY_global = int(M["m01"] / M["m00"]) + ROI_Y
                                
                                # Rem conveyor secepatnya
                                stop_conveyor()
                                benda_ditemukan = True
                                
                                # Ambil tugas target grid ( FIFO ) hasil prediksi ML tadi
                                target_col, target_row = misi_aktif[color_name].pop(0)
                                
                                print(f"\n[EXECUTE] Menemukan supply objek {color_name}!")
                                print(f"          -> Mengirim ke koordinat tujuan AI: Grid ({target_col}, {target_row})")
                                
                                # Eksekusi pergerakan lengan robot Dobot ke grid tujuan
                                arm_move(device, cX_global, cY_global, color_name, target_col, target_row)
                                
                                misi_selesai += 1
                                print(f"[STATUS MISI] Progress: {misi_selesai}/{total_misi} objek selesai ditata.")
                                
                                # Jalankan conveyor lagi jika misi belum selesai semuanya
                                if misi_selesai < total_misi:
                                    start_conveyor()
                                    for _ in range(5): cap.read() # Flush buffer kamera
                                break

            cv2.imshow("Auto Sort Mode (ML Active)", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        print("\n[BERHASIL] Seluruh penataan objek berdasarkan prediksi model Machine Learning SELESAI!")
        stop_conveyor()

    except KeyboardInterrupt:
        print("\n[WARNING] Mode otomatis dihentikan paksa.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        stop_conveyor()
        device.close()
        sys.exit(0)

if __name__ == "__main__":
    main()