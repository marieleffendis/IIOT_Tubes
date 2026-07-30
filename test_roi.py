import cv2
import numpy as np
# Mengimpor setup_camera agar spesifikasi resolusi & FPS sama persis dengan sistem utama
from Computer_Vision import setup_camera

# --- KOORDINAT AWAL ROI ---
# Nilai default awal diambil dari Computer_Vision.py
ROI_X, ROI_Y, ROI_W, ROI_H = 235, 145, 235, 150

# Langkah pergeseran (piksel) setiap kali tombol ditekan
STEP = 5

def main():
    global ROI_X, ROI_Y, ROI_W, ROI_H
    
    # Menyiapkan kamera dengan konfigurasi standar yang dipakai sistem utama (640x480)
    cap = setup_camera(fps=24, width=800, height=600)
    
    if not cap.isOpened():
        print("[ERROR] Kamera tidak dapat dibuka!")
        return

    print("=" * 60)
    print("      PROGRAM KALIBRASI & PENYESUAIAN POSISI ROI KAMERA      ")
    print("=" * 60)
    print("Gunakan Keyboard untuk menggeser & mengubah ukuran ROI:")
    print("  [W] / [S] : Geser ROI ke ATAS / BAWAH")
    print("  [A] / [D] : Geser ROI ke KIRI / KANAN")
    print("  [I] / [K] : Tambah / Kurangi TINGGI (Height) ROI")
    print("  [J] / [L] : Tambah / Kurangi LEBAR (Width) ROI")
    print("  [R]       : Reset ke posisi default")
    print("  [ESC] / [Q] : Selesai & Cetak Nilai Akhir ROI")
    print("=" * 60)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Gagal membaca frame dari kamera.")
            break

        # Ambil ukuran frame asli untuk batas maksimum
        frame_h, frame_w = frame.shape[:2]

        # Validasi agar ROI tidak keluar dari batas frame kamera
        ROI_X = max(0, min(ROI_X, frame_w - ROI_W))
        ROI_Y = max(0, min(ROI_Y, frame_h - ROI_H))
        ROI_W = max(10, min(ROI_W, frame_w - ROI_X))
        ROI_H = max(10, min(ROI_H, frame_h - ROI_Y))

        # --- GAMBAR VISUALISASI ---
        # 1. Gambar Kotak ROI (Warna Biru)
        cv2.rectangle(frame, (ROI_X, ROI_Y), (ROI_X + ROI_W, ROI_Y + ROI_H), (255, 0, 0), 2)
        
        # 2. Gambar Titik Pusat ROI (Silang Merah) untuk membantu alignment
        center_x = ROI_X + ROI_W // 2
        center_y = ROI_Y + ROI_H // 2
        cv2.drawMarker(frame, (center_x, center_y), (0, 0, 255), cv2.MARKER_CROSS, 15, 2)

        # 3. Tampilkan Teks Informasi di Layar
        info_str = f"ROI_X: {ROI_X} | ROI_Y: {ROI_Y} | ROI_W: {ROI_W} | ROI_H: {ROI_H}"
        cv2.putText(frame, info_str, (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        cv2.putText(frame, f"Frame Size: {frame_w}x{frame_h}", (10, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Tampilkan Jendela Kamera
        cv2.imshow("Kalibrasi ROI Kamera", frame)

        # --- KONTROL KEYBOARD ---
        key = cv2.waitKey(30) & 0xFF

        if key in (27, ord('q')):  # ESC atau Q untuk keluar
            break
        elif key == ord('w'):  # Ke Atas
            ROI_Y -= STEP
        elif key == ord('s'):  # Ke Bawah
            ROI_Y += STEP
        elif key == ord('a'):  # Ke Kiri
            ROI_X -= STEP
        elif key == ord('d'):  # Ke Kanan
            ROI_X += STEP
        elif key == ord('i'):  # Tambah Tinggi
            ROI_H += STEP
        elif key == ord('k'):  # Kurangi Tinggi
            ROI_H -= STEP
        elif key == ord('l'):  # Tambah Lebar
            ROI_W += STEP
        elif key == ord('j'):  # Kurangi Lebar
            ROI_W -= STEP
        elif key == ord('r'):  # Reset
            ROI_X, ROI_Y, ROI_W, ROI_H = 215, 100, 140, 280

    # Membersihkan kamera & window
    cap.release()
    cv2.destroyAllWindows()

    # Cetak hasil akhir ke terminal
    print("\n" + "=" * 60)
    print("  HASIL KALIBRASI SELESAI! Salin kode di bawah ke Computer_Vision.py:")
    print("=" * 60)
    print(f"ROI_X, ROI_Y, ROI_W, ROI_H = {ROI_X}, {ROI_Y}, {ROI_W}, {ROI_H}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()