import cv2
import numpy as np
import sys
import argparse
from Actuator import start_conveyor, stop_conveyor, arm_move, connect_dobot
from Computer_Vision import setup_camera, draw_roi, cleanup, detect_largest_object, draw_detection, is_inside_roi
from Computer_Vision import ROI_X, ROI_Y, ROI_W, ROI_H, COLOR_RANGES

# ==========================================
# KONFIGURASI GLOBAL (Sama persis untuk Mode Manual & Otomatis)
# ==========================================


# ==========================================
# ARGUMENT PARSING
# ==========================================
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Sistem Sortir Balok Dobot - Mode Manual & Otomatis (Color Grid Recognition)"
    )
    parser.add_argument("--manual", nargs=2, metavar=("COL", "ROW"),
                         help="Aktifkan mode manual. Format: --manual col row")
    parser.add_argument("--merah", nargs="*", default=[],
                         help="Mode otomatis - daftar grid merah, contoh: 1,1 2,1")
    parser.add_argument("--kuning", nargs="*", default=[],
                         help="Mode otomatis - daftar grid kuning")
    parser.add_argument("--hijau", nargs="*", default=[],
                         help="Mode otomatis - daftar grid hijau")
    parser.add_argument("--biru", nargs="*", default=[],
                         help="Mode otomatis - daftar grid biru")
    return parser.parse_args()


def parse_pairs(pair_list):
    """Ubah list teks 'kolom,baris' (dari HMI) menjadi list tuple (int, int)."""
    result = []
    for pair in pair_list:
        if ',' in pair:
            try:
                c, r = map(int, pair.split(','))
                result.append((c, r))
            except ValueError:
                continue
    return result


# ==========================================
# MODE MANUAL: drop-off satu objek ke satu grid target
# ==========================================
def run_manual(target_col, target_row):
    print(f"[VISION] Memulai misi drop-off ke Grid Manual: Kolom {target_col}, Baris {target_row}")

    cap = setup_camera(fps=30, width=640, height=480)
    start_conveyor()
    object_found = False

    print("[VISION] Mencari benda di arena ROI...")

    try:
        while not object_found:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Gagal membaca dari kamera.")
                break

            draw_roi(frame, "Area Deteksi (ROI)")
            
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            for color_name, ranges in COLOR_RANGES.items():
                if object_found:
                    break

                hasil = detect_largest_object(hsv, ranges)
                if hasil is None:
                    continue

                cX, cY, x, y, w, h = hasil

                if not is_inside_roi(cX, cY):
                    continue   # objek terdeteksi & dilacak, tapi belum masuk ROI -> jangan ganggu conveyor/arm

                stop_conveyor()
                object_found = True   # (atau object_detected_in_this_frame = True di run_auto)
                object_found = True

                draw_detection(frame, x, y, w, h, cX, cY, f"{color_name} Center")
                cv2.imshow("Camera Feed", frame)
                cv2.waitKey(1)

                print(f"[AKSI] Robotic arm bergerak ke ({cX}, {cY}) untuk mengambil objek {color_name}")
                arm_move(cX, cY, color_name, target_col, target_row)
                print(f"[AKSI] Selesai mengambil {color_name}.")
                break

            cv2.imshow("Camera Feed", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n[WARNING] Mode manual dihentikan paksa oleh pengguna (Ctrl+C).")
    finally:
        cleanup(cap)


# ==========================================
# MODE OTOMATIS: sortir banyak objek sesuai antrean grid per warna
# ==========================================
def run_auto(misi_aktif):
    total_misi = sum(len(coords) for coords in misi_aktif.values())
    if total_misi == 0:
        print("[ERROR] Tidak ada koordinat target grid yang dipilih dari HMI. Program dihentikan.")
        sys.exit(1)

    print("\n=== MEMULAI MODE OTOMATIS (COLOR GRID RECOGNITION) ===")
    for warna, target_list in misi_aktif.items():
        if target_list:
            grid_str = ", ".join([f"({c},{r})" for c, r in target_list])
            print(f"-> Balok [{warna}] akan ditata sekuensial ke Grid: {grid_str}")
    print(f"Total target pengerjaan: {total_misi} balok.")
    print("======================================================\n")

    cap = setup_camera(fps=30, width=640, height=480)
    misi_selesai = 0

    print("[VISION] Menjalankan conveyor & memulai pemindaian area ROI...")
    start_conveyor()

    try:
        while misi_selesai < total_misi:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Gagal membaca data frame dari kamera.")
                break

            draw_roi(frame, f"Area Deteksi Otomatis ({misi_selesai}/{total_misi})")
            
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            object_detected_in_this_frame = False

            for color_name, ranges in COLOR_RANGES.items():
                # Lewati warna yang kuota targetnya sudah habis / tidak ditugaskan
                if not misi_aktif[color_name]:
                    continue
                if object_detected_in_this_frame:
                    break

                hasil = detect_largest_object(hsv, ranges)
                if hasil is None:
                    continue

                cX_roi, cY_roi, x, y, w, h = hasil
                cX_global = cX_roi + ROI_X
                cY_global = cY_roi + ROI_Y

                stop_conveyor()
                object_detected_in_this_frame = True

                target_col, target_row = misi_aktif[color_name].pop(0)

                draw_detection(frame, x, y, w, h, cX_global, cY_global,
                                f"TARGET: {color_name} -> Grid ({target_col},{target_row})")
                cv2.imshow("Camera Feed - Auto Mode", frame)
                cv2.waitKey(1)

                print(f"\n[SORT] Menemukan objek warna {color_name}!")
                print(f"[AKSI] Mengambil koordinat global ({cX_global}, {cY_global}) -> Menaruh ke Grid ({target_col}, {target_row})")

                arm_move(cX_global, cY_global, color_name, target_col, target_row)

                misi_selesai += 1
                print(f"[STATUS] Progress penataan: {misi_selesai}/{total_misi} selesai.\n")

                if misi_selesai < total_misi:
                    print("[VISION] Menjalankan kembali conveyor...")
                    start_conveyor()
                    # Buang frame lama di buffer kamera pasca-lengan bergerak
                    for _ in range(5):
                        cap.read()
                break

            cv2.imshow("Camera Feed - Auto Mode", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[INFO] Program dihentikan melalui tombol 'q' pada jendela kamera.")
                break

        print("\n[BERHASIL] Seluruh penataan balok berdasarkan konfigurasi grid HMI SELESAI!")

    except KeyboardInterrupt:
        print("\n[WARNING] Mode otomatis dihentikan paksa oleh pengguna (Ctrl+C).")
    finally:
        cleanup(cap)


# ==========================================
# MAIN ENTRY POINT — PEMILIH MODE MANUAL / OTOMATIS
# ==========================================
def main():
    args = parse_arguments()

    # Hubungkan ke Dobot (TANPA homing -- homing sudah dilakukan sekali oleh
    # Initialize.py saat HMI pertama kali dibuka). Setiap kali Main.py dipanggil
    # HMI sebagai proses baru, ia harus membuka koneksi serialnya sendiri.
    print("[VISION] Menghubungkan ke Dobot...")
    connect_dobot()

    if args.manual:
        # ---- MODE MANUAL ----
        target_col = int(args.manual[0])
        target_row = int(args.manual[1])
        run_manual(target_col, target_row)
    else:
        # ---- MODE OTOMATIS ----
        misi_aktif = {
            "Merah":  parse_pairs(args.merah),
            "Kuning": parse_pairs(args.kuning),
            "Hijau":  parse_pairs(args.hijau),
            "Biru":   parse_pairs(args.biru),
        }
        if sum(len(v) for v in misi_aktif.values()) == 0:
            print("[ERROR] Tidak ada argumen koordinat grid dari HMI. Program dihentikan.")
            sys.exit(1)
        run_auto(misi_aktif)

    sys.exit(0)


if __name__ == "__main__":
    main()
