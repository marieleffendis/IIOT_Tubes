import time

# --- KONFIGURASI KOORDINAT DOBOT ---
# Sesuaikan nilai Z ini dengan kondisi fisik meja/conveyor Anda
Z_HOVER = 50   # Ketinggian aman (melayang di atas conveyor) agar tidak menabrak benda lain
Z_PICK = -10   # Ketinggian saat menempel pada objek (menyentuh conveyor)
HOME_R = 0     # Rotasi default end-effector

# Titik istirahat robot (Home)
HOME_X = 250
HOME_Y = 0
HOME_Z = 50

def coordinate_translate(cam_x, cam_y):
    """
    Fungsi untuk menerjemahkan piksel kamera (X, Y) ke milimeter koordinat Dobot.
    Saat ini masih berupa fungsi dummy (placeholder). 
    Silakan masukkan rumus kalibrasi Anda di sini nanti.
    """
    # TODO: Ganti dengan rumus kalibrasi (misal: regresi linear atau matriks affine)
    dobot_x = cam_x  
    dobot_y = cam_y  
    
    return dobot_x, dobot_y

def arm_move(device, cam_x, cam_y, color):
    """
    Menjalankan urutan pergerakan lengan robot (Pick and Place).
    """
    if device is None:
        print("[ERROR] Dobot tidak terhubung. Mengabaikan perintah gerak.")
        return

    # 1. Terjemahkan koordinat
    target_x, target_y = coordinate_translate(cam_x, cam_y)
    print(f"[ARM] Menerima tugas: Objek {color} di Kam({cam_x}, {cam_y}) -> Dobot({target_x}, {target_y})")

    # 2. Bergerak ke atas objek (Hover)
    # Gunakan wait=True agar program Python menunggu sampai robot selesai bergerak secara fisik
    print("[ARM] Bergerak ke titik aman di atas objek...")
    device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

    # 3. Turun dan ambil objek
    print("[ARmM] Turun mengabil objek...")
    device.move_to(target_x, target_y, Z_PICK, HOME_R, wait=True)
    
    # Nyalakan pompa hisap (Suction Cup) - Sesuaikan jika Anda pakai Gripper
    device.suck(True)
    time.sleep(0.5) # Beri jeda agar hisapan vakum menguat sebelum ditarik

    # 4. Naik kembali ke posisi Hover (membawa objek)
    device.move_to(target_x, target_y, Z_HOVER, HOME_R, wait=True)

    # 5. Tentukan lokasi pembuangan (Drop-off) berdasarkan warna
    # (Silakan ubah koordinat X, Y pembuangan sesuai fisik di lapangan)
    if color == "Merah":
        drop_x, drop_y = 150, 150
    elif color == "Biru":
        drop_x, drop_y = 150, -150
    elif color == "Hijau":
        drop_x, drop_y = 100, 150
    else:
        drop_x, drop_y = 200, 100 # Default/Kuning

    # 6. Bergerak ke keranjang warna dan jatuhkan
    print(f"[ARM] Menaruh objek {color} ke area pembuangan...")
    device.move_to(drop_x, drop_y, Z_HOVER, HOME_R, wait=True)
    device.move_to(drop_x, drop_y, Z_PICK, HOME_R, wait=True)
    
    # Matikan hisapan
    device.suck(False)
    time.sleep(0.5) # Beri waktu agar objek benar-benar terlepas
    
    # Naik lagi ke posisi aman
    device.move_to(drop_x, drop_y, Z_HOVER, HOME_R, wait=True)

    # 7. Kembali ke posisi standby (Home)
    print("[ARM] Selesai. Kembali ke Home.")
    device.move_to(HOME_X, HOME_Y, HOME_Z, HOME_R, wait=True)