"""
Initialize.py

Dijalankan HANYA oleh HMI.py, satu kali saat aplikasi pertama dibuka.
Ini adalah SATU-SATUNYA tempat proses homing fisik Dobot terjadi (~20 detik),
supaya Main.py (mode Manual & Auto) tidak perlu mengulang homing setiap kali
dipanggil HMI untuk tiap aksi sortir.

Setelah file ini selesai, koneksi serial di proses ini ditutup -- tapi
kalibrasi homing tetap tersimpan di firmware Dobot selama tidak mati listrik.
Main.py akan membuka koneksi serial barunya sendiri lewat Actuator.connect_dobot()
tanpa perlu homing ulang.

Exit code 0  = koneksi & homing berhasil
Exit code 1  = gagal (tidak ada port / gagal connect)
"""
import sys
import time
from Actuator import connect_dobot


def main():
    device = connect_dobot()
    if device is None:
        print("[ERROR] Gagal terhubung ke Dobot. Homing dibatalkan.")
        sys.exit(1)

    print("[INFO] Memulai proses Homing. Pastikan area sekitar robot KOSONG!")
    print("[INFO] Menunggu homing selesai (20 detik)...")
    device.home()
    time.sleep(20)  # Jeda manual untuk homing
    print("[INFO] Homing dianggap selesai, siap menjalankan conveyor!")
    sys.exit(0)


if __name__ == "__main__":
    main()
