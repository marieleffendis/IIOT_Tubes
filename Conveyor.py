from serial.tools import list_ports
from pydobotplus import Dobot

CONVEYOR_SPEED = 0.75       
CONVEYOR_DELAY = 1.16

def init_dobot():
    # Mencari port dan menghubungkan ke Dobot.
    available_ports = list_ports.comports()
    if not available_ports:
        print("[ERROR] Tidak ada port serial yang ditemukan.")
        return None

    port = available_ports[1].device
    print(f"[INFO] Mencoba terhubung ke Dobot di port: {port}...")
    try:
        device = Dobot(port=port)
        print("[INFO] Dobot terhubung berhasil.")
        print("[INFO] Memulai proses Homing. Pastikan area sekitar robot KOSONG!")
        # wait=True sangat penting agar program tidak lanjut sebelum homing selesai
        device.home(wait=True)
        return device
    except Exception as e:
        print(f"[ERROR] Gagal connect ke Dobot: {e}")
        return None

device = init_dobot()

def start_conveyor():
    print("[CONVEYOR] START")
    device.conveyor_belt(speed=CONVEYOR_SPEED, direction=1)

def stop_conveyor():
    print("[CONVEYOR] STOP")
    device.conveyor_belt(speed=0, direction=1)