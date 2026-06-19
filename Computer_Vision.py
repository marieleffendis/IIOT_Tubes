import cv2
import numpy as np
import time
from pydobotplus import Dobot
from Conveyor import start_conveyor, stop_conveyor
from Arm import arm_move

device = Dobot(port='/dev/ttyUSB2')    

cap = cv2.VideoCapture(0) # Sesuaikan indeks kamera

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FPS, 30)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# Inisialisasi status conveyor di LUAR loop agar tidak terus-menerus di-reset
conveyor_running = True
start_conveyor() 

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

while True:
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
    
    object_processed = False

    for color_name, ranges in color_ranges.items():
        if object_processed: 
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
                    if conveyor_running:
                        stop_conveyor()
                        conveyor_running = False
                    
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
                    arm_move(device, cX_global, cY_global, color_name)
                    time.sleep(10) # Simulasi waktu kerja lengan robot
                    print(f"[AKSI] Selesai mengambil {color_name}.")
                    
                    # Nyalakan kembali setelah selesai
                    conveyor_running = True
                    start_conveyor()
                    object_processed = True

                    for _ in range(5):
                        ret_flush, frame_flush = cap.read()
                    
                    break 

    # Update tampilan jika tidak ada objek yang diproses di iterasi ini
    if not object_processed:
        cv2.imshow("Camera Feed", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
device.close()
cv2.destroyAllWindows()