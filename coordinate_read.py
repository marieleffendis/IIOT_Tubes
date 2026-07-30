from serial.tools import list_ports
from pydobotplus import Dobot
import time
import sys

def main():
    print("=== PROGRAM KONTROL DOBOT (WINDOWS STABLE) ===")
    
    # 1. Deteksi Port
    available_ports = list_ports.comports()
    if not available_ports:
        print("ERROR: Dobot tidak terdeteksi.")
        sys.exit(1)
    
    port = available_ports[0].device
    print(f"Menghubungkan ke Dobot di port: {port}...")

    try:
        # 2. Inisialisasi koneksi 
        device = Dobot(port=port)
        print("Koneksi berhasil dibuat!")
    except Exception as e:
        print(f"Gagal terhubung ke Dobot. Error: {e}")
        sys.exit(1)

    # 3. Melakukan Homing Kalibrasi Mekanik
    print("\n[INFO] Memulai proses Homing (sekitar 25 detik)...")
    device.home()
    time.sleep(25) # Menunggu kalibrasi fisik mesin selesai

    # 4. Pindah ke Posisi Standby
    home_x, home_y, home_z, home_r = 250, 0, 50, 0
    print(f"[INFO] Homing selesai. Bergerak ke koordinat Standby X:{home_x} Y:{home_y} Z:{home_z} R:{home_r}...")
    device.move_to(home_x, home_y, home_z, home_r, wait=True)
    print("Posisi Standby tercapai.\n")

    # 5. Looping untuk mencetak koordinat
    print("=== SISTEM PEMBACAAN KOORDINAT AKTIF ===")
    print("Tekan Ctrl+C di terminal untuk berhenti.\n")
    
    try:
        while True:
            current_pos = device.get_pose()
            
            if current_pos:
                # Mengakses atribut berdasarkan struktur internal kelas Pose -> Position
                x = current_pos.position.x
                y = current_pos.position.y
                z = current_pos.position.z
                r = current_pos.position.r
                
                print(f"Koordinat Saat Ini -> X: {x:.2f} | Y: {y:.2f} | Z: {z:.2f} | R: {r:.2f}")
            else:
                print("Gagal membaca koordinat dari sensor (Data kosong).")
                
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[INFO] Looping dihentikan oleh pengguna.")
        
    finally:
        device.close()
        print("[INFO] Koneksi Dobot diputus dengan aman.")

if __name__ == "__main__":
    main()