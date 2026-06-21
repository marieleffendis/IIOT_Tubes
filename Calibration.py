import cv2
import numpy as np

# --- Inisialisasi Kamera ---
cap = cv2.VideoCapture(0) # Sesuaikan indeks kamera

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FPS, 30)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# --- Rentang Warna ---
color_ranges = {
    "Merah": [
        (np.array([0, 120, 70]), np.array([10, 255, 255])),
        (np.array([170, 120, 70]), np.array([180, 255, 255]))
    ],
    "Hijau": [(np.array([40, 50, 50]), np.array([90, 255, 255]))],
    "Kuning": [(np.array([20, 100, 100]), np.array([30, 255, 255]))],
    "Biru": [(np.array([100, 150, 0]), np.array([140, 255, 255]))]
}

# --- Definisi Kotak ROI ---
ROI_X, ROI_Y, ROI_W, ROI_H = 325, 100, 140, 280

print("=== PROGRAM KALIBRASI KAMERA DIMULAI ===")
print("Taruh objek di atas area ROI untuk melihat koordinatnya.")
print("Tekan 'q' pada jendela kamera untuk keluar.\n")

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
    hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
    
    object_processed = False

    # 3. Proses deteksi warna
    for color_name, ranges in color_ranges.items():
        if object_processed: 
            break

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
                    
                    # Gambar bounding box dan centroid
                    x, y, w, h = cv2.boundingRect(c)
                    cv2.rectangle(frame, (x + ROI_X, y + ROI_Y), (x + w + ROI_X, y + h + ROI_Y), (0, 255, 0), 2)
                    cv2.circle(frame, (cX_global, cY_global), 5, (255, 255, 255), -1)
                    cv2.putText(frame, f"{color_name} (X:{cX_global}, Y:{cY_global})", 
                                (cX_global - 20, cY_global - 20), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                    # [PENTING] Print koordinat secara kontinu ke terminal
                    print(f"Kalibrasi - {color_name} -> X_Pixel: {cX_global} | Y_Pixel: {cY_global}")
                    
                    object_processed = True
                    break 

    # Update tampilan
    cv2.imshow("Kalibrasi Kamera", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()