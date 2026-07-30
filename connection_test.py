import serial
import time

PORT = '/dev/ttyUSB0'
BAUDRATE = 115200

def main():
    print(f"Membuka port {PORT} dengan konfigurasi khusus Windows...")
    try:
        # Membuka port dengan menonaktifkan rtscts dan dsrdtr agar tidak memicu reset hardware
        ser = serial.Serial(
            port=PORT,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1,
            rtscts=False,
            dsrdtr=False
        )
        
        # Mengatur status DTR dan RTS secara manual agar chip stabil
        ser.dtr = False
        ser.rts = False
        time.sleep(1)
        
        print("Port terbuka dengan stabil. Membersihkan buffer...")
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        print("Mendengarkan data dari Dobot (Tekan Ctrl+C untuk berhenti)...")
        while True:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"[DATA MASUK] Hex: {data.hex()} | ASCII: {data}")
            else:
                # Coba kirim byte interogasi ringan secara berkala jika diperlukan
                pass
                
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nProgram dihentikan oleh pengguna.")
    except Exception as e:
        print(f"Terjadi error: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Koneksi ditutup.")

if __name__ == "__main__":
    main()