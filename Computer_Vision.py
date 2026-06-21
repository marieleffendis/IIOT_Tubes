import cv2
import numpy as np
import time
import sys
import argparse
from pydobotplus import Dobot
from Conveyor import start_conveyor, stop_conveyor, device 
from Arm import arm_move
import Conveyor
from serial.tools import list_ports

# Menangkap baris dan kolom yang dikirim oleh HMI.py
parser =  argparse.ArgumentParser()
parser.add_argument('--manual', nargs=2, help='Format: --manual col row')
args = parser.parse_args()

if args.manual: 
	target_col = int(args.manual[0])
	target_row = int(args.manual[1])
	print(f"[VISION] Memulai misi drop-off ke Grid Manual: Kolom {target_col}, Baris {target_row}")
else: 
	print("[ERROR] Tidal ada argumen koordinat grid dari HMI. Program dihentikan.")
	sys.exit()

available_ports = list(list_ports.comports())

if not available_ports:
    sys.exit(1)

if len(available_ports) > 1:
    port = available_ports[1].device
else:
    port = available_ports[0].device
    
print(f"[VISION] Menghubungkan langsung ke port {port} (Tanpa Homing) ...")
device = Dobot(port=port)

Conveyor.device = device

cap = cv2.VideoCapture(0) # Sesuaikan indeks kamera
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FPS, 30)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# Inisialisasi status conveyor di LUAR loop agar tidak terus-menerus di-reset
conveyor_running = True
start_conveyor() 
object_found = False

color_ranges = {
    "Merah": [ 
        (np.array([0, 120, 70]), np.array([10, 255, 255])),
        (np.array([170, 120, 70]), np.array([180, 255, 255]))
    ],
    "Hijau": [(np.array([40, 50, 50]), np.array([90, 255, 255]))],
    "Kuning": [(np.array([20, 100, 100]), np.array([30, 255, 255]))],
    "Biru": [(np.array([100, 150, 0]), np.array([140, 255, 255]))]
}

# --- DEFINISI KOTAK ROI (Tetap di layar) ---
# Format: X_awal, Y_awal, Lebar, Tinggi
# Sesuaikan angka ini dengan posisi fisik conveyor Anda di kamera
ROI_X, ROI_Y, ROI_W, ROI_H = 325, 100, 140, 280

print("[VISION] Mencari benda di arena ROI...")

while not object_found:
    ret, frame = cap.read()
    if not ret:
        print("Gagal membaca dari kamera.")
        break

    # 1. Gambar kotak ROI di layar (sebagai panduan visual)
    cv2.rectangle(frame, (ROI_X, ROI_Y), (ROI_X + ROI_W, ROI_Y + ROI_H), (255, 0, 0), 2)
    cv2.putText(frame, "Area Deteksi (ROI)", (ROI_X, ROI_Y - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    # 2. Potong frame hanya pada area ROI
    roi_frame = frame[ROI_Y:ROI_Y + ROI_H, ROI_X:ROI_X + ROI_W]
    
    # 3. Ubah warna HANYA pada bagian ROI
    hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)

    for color_name, ranges in color_ranges.items():
        if object_found: 
            break # Hentikan pencarian warna lain jika sudah ada 1 objek yang diproses

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
                    # 4. Hitung titik tengah LOKAL (relatif terhadap ROI)
                    cX_roi = int(M["m10"] / M["m00"])
                    cY_roi = int(M["m01"] / M["m00"])
                    
                    # 5. Konversi ke titik tengah GLOBAL (relatif terhadap frame utama)
                    cX_global = cX_roi + ROI_X
                    cY_global = cY_roi + ROI_Y
                    
                    # Matikan conveyor
                    stop_conveyor()
                    object_found = True

                    # Gambar bounding box dan centroid menggunakan koordinat GLOBAL
                    x, y, w, h = cv2.boundingRect(c)
                    
                    cv2.rectangle(frame, (x + ROI_X, y + ROI_Y), (x + w + ROI_X, y + h + ROI_Y), (0, 255, 0), 2)
                    cv2.circle(frame, (cX_global, cY_global), 5, (255, 255, 255), -1)
                    cv2.putText(frame, f"{color_name} Center", (cX_global - 20, cY_global - 20), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                    # Update tampilan SEBELUM arm memblokir program
                    cv2.imshow("Camera Feed", frame)
                    cv2.waitKey(1)

                    # Panggil fungsi lengan robot dengan koordinat GLOBAL
                    print(f"[AKSI] Robotic arm bergerak ke ({cX_global}, {cY_global}) untuk mengambil objek {color_name}")
                    arm_move(device, cX_global, cY_global, color_name, target_col, target_row)
                    print(f"[AKSI] Selesai mengambil {color_name}.")
                                     
                    break 

    # Update tampilan jika tidak ada objek yang diproses di iterasi ini
    cv2.imshow("Camera Feed", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("[SISTEM] Proses selesai. Mengembalikan kendali ke HMI.\n")
sys.exit(0)