from serial.tools import list_ports
from pydobotplus import Dobot
import time

CONVEYOR_SPEED = 0.45       
CONVEYOR_DELAY = 1.16

def init_dobot():
    # Mencari port dan menghubungkan ke Dobot.
    available_ports = list(list_ports.comports())
    if not available_ports:
        print("[ERROR] Tidak ada port serial yang ditemukan.")
        return None

    if len(available_ports) > 1:
        port = available_ports[1].device
    else:
        port = available_ports[0].device

    print(f"[INFO] Mencoba terhubung ke Dobot di port: {port}...")
    try:
        device = Dobot(port=port)
        print("[INFO] Dobot terhubung berhasil.")
    except Exception as e:
        print(f"[ERROR] Gagal connect ke Dobot: {e}")
        return None

    print("[INFO] Memulai proses Homing. Pastikan area sekitar robot KOSONG!")
    print("[INFO] Menunggu homing selesai (20 detik)...")
    device.home()
    time.sleep(20) # Jeda manual untuk homing
    print("[INFO] Homing dianggap selesai, siap menjalankan conveyor!")
    return device
# device = init_dobot()
device = None

def start_conveyor():
    print("[CONVEYOR] START")
    if device: 
        device.conveyor_belt(speed=CONVEYOR_SPEED, direction=1)

def stop_conveyor():
    print("[CONVEYOR] STOP")
    if device: 
        device.conveyor_belt(speed=0, direction =1)
    device.conveyor_belt(speed=0, direction=1)