import cv2
import sys
import time
import json
import threading
import argparse

import paho.mqtt.client as mqtt

from Actuator import start_conveyor, stop_conveyor, arm_move, connect_dobot
from Computer_Vision import (
    setup_camera,
    draw_roi,
    cleanup,
    detect_largest_object,
    draw_detection,
    is_inside_roi,
    is_inside_pick_zone,
    COLOR_RANGES,
)

# =========================================================
# KONFIGURASI
# =========================================================
STABLE_FRAMES = 3          # jumlah frame beruntun agar objek dianggap stabil
POST_STOP_DELAY = 0.25     # jeda setelah conveyor berhenti sebelum pick
POST_PICK_FLUSH_FRAMES = 5 # buang frame buffer setelah arm selesai bergerak

VALID_COLS = {1, 2, 3, 4}
VALID_ROWS = {1, 2, 3, 4}

# =========================================================
# KONFIGURASI MQTT
# =========================================================
MQTT_HOST = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "IIoT/Labtek_VI/Lab_TF_C/docon_01"

# State bersama yang dipublish sebagai telemetry. Disimpan dalam dict
# tunggal supaya gampang diakses/diupdate dari mana saja tanpa banyak
# deklarasi 'global'.
mqtt_state = {
    "fps": 0,
    "color": None,
    "x": None,
    "y": None,
    "angle": 0.0,
    "conveyor_running": False,
    "system_state": "idle",   # idle | busy
    "system_mode": "manual",  # manual | auto
}

# Flag untuk mencegah eksekusi perintah target ganda secara bersamaan
_manual_lock = threading.Lock()

mqttc = None  # diisi oleh setup_mqtt()


def on_connect(client, userdata, flags, rc):
    print("[MQTT] Terhubung ke broker.")
    client.subscribe(f"{BASE_TOPIC}/Command/#")


def on_message(client, userdata, msg):
    print(f"[MQTT] Dipanggil: {msg.topic}")

    if msg.topic == f"{BASE_TOPIC}/Command/camera":
        client.publish(
            f"{BASE_TOPIC}/Telemetry/camera",
            json.dumps({"fps": mqtt_state["fps"]})
        )

    elif msg.topic == f"{BASE_TOPIC}/Command/color":
        client.publish(
            f"{BASE_TOPIC}/Telemetry/color",
            json.dumps({"color": mqtt_state["color"]})
        )

    elif msg.topic == f"{BASE_TOPIC}/Command/dobot":
        client.publish(
            f"{BASE_TOPIC}/Telemetry/dobot",
            json.dumps({
                "x": mqtt_state["x"],
                "y": mqtt_state["y"],
                "angle": mqtt_state["angle"],
            }),
        )

    elif msg.topic == f"{BASE_TOPIC}/Command/conveyor":
        client.publish(
            f"{BASE_TOPIC}/Telemetry/conveyor",
            json.dumps({"running": mqtt_state["conveyor_running"]})
        )

    elif msg.topic == f"{BASE_TOPIC}/Command/system":
        # FIX #3: kirim sebagai JSON bukan plain string
        client.publish(
            f"{BASE_TOPIC}/State/system",
            json.dumps({"state": mqtt_state["system_state"]})
        )

    elif msg.topic == f"{BASE_TOPIC}/Command/mode":
        # FIX #3: kirim sebagai JSON bukan plain string
        client.publish(
            f"{BASE_TOPIC}/State/mode",
            json.dumps({"mode": mqtt_state["system_mode"]})
        )

    # FIX #2: handler baru untuk Command/target dari dashboard Node-RED
    elif msg.topic == f"{BASE_TOPIC}/Command/target":
        try:
            data = json.loads(msg.payload)
            col = int(data.get("col", 0))
            row = int(data.get("row", 0))

            if not validate_grid_target(col, row):
                print(f"[MQTT] Target grid tidak valid dari dashboard: ({col},{row})")
                return

            # Cek apakah sudah ada operasi manual yang berjalan
            if _manual_lock.locked():
                print("[MQTT] Perintah diabaikan: sistem sedang menjalankan tugas lain.")
                return

            print(f"[MQTT] Perintah target diterima dari dashboard: Grid ({col}, {row})")
            # Jalankan di thread terpisah agar tidak memblokir loop MQTT
            threading.Thread(
                target=run_manual,
                args=(col, row),
                daemon=True
            ).start()

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"[MQTT] Payload Command/target tidak valid: {e}")


def setup_mqtt():
    """
    Inisialisasi koneksi MQTT. Kalau broker tidak tersedia, program tetap
    jalan tanpa MQTT (mqttc akan None dan publish_telemetry jadi no-op).
    """
    global mqttc
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        mqttc = client
    except Exception as e:
        print(f"[MQTT] Gagal terhubung ke broker ({MQTT_HOST}:{MQTT_PORT}): {e}")
        mqttc = None
    return mqttc


def publish_telemetry(topic_suffix, payload):
    """
    Helper untuk publish payload (dict -> JSON, atau string langsung)
    ke BASE_TOPIC/topic_suffix. Aman dipanggil walau MQTT belum/gagal connect.
    """
    if mqttc is None:
        return
    try:
        data = payload if isinstance(payload, str) else json.dumps(payload)
        mqttc.publish(f"{BASE_TOPIC}/{topic_suffix}", data)
    except Exception as e:
        print(f"[MQTT] Gagal publish ke {topic_suffix}: {e}")


def stop_mqtt():
    if mqttc is not None:
        time.sleep(0.2)  # beri jeda agar publish terakhir terkirim
        mqttc.loop_stop()
        mqttc.disconnect()
        print("[MQTT] Koneksi ditutup.")


# =========================================================
# ARGUMENT PARSING
# =========================================================
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Sistem Sortir Balok Dobot - Mode Manual & Otomatis"
    )
    parser.add_argument(
        "--manual", nargs=2, metavar=("COL", "ROW"),
        help="Aktifkan mode manual. Format: --manual col row"
    )
    parser.add_argument(
        "--merah", nargs="*", default=[],
        help="Mode otomatis - daftar grid merah, contoh: 1,1 2,1"
    )
    parser.add_argument(
        "--kuning", nargs="*", default=[],
        help="Mode otomatis - daftar grid kuning"
    )
    parser.add_argument(
        "--hijau", nargs="*", default=[],
        help="Mode otomatis - daftar grid hijau"
    )
    parser.add_argument(
        "--biru", nargs="*", default=[],
        help="Mode otomatis - daftar grid biru"
    )
    return parser.parse_args()


def parse_pairs(pair_list):
    """
    Ubah list teks 'kolom,baris' (dari HMI) menjadi list tuple (int, int).
    Contoh input: ["1,1", "2,3"]
    """
    result = []
    for pair in pair_list:
        if "," not in pair:
            continue
        try:
            c, r = map(int, pair.split(","))
            result.append((c, r))
        except ValueError:
            continue
    return result


def validate_grid_target(col, row):
    return col in VALID_COLS and row in VALID_ROWS


def sanitize_missions(misi_aktif):
    """
    Buang target grid yang tidak valid.
    """
    cleaned = {}
    total = 0

    for warna, coords in misi_aktif.items():
        valid_coords = []
        for c, r in coords:
            if validate_grid_target(c, r):
                valid_coords.append((c, r))
            else:
                print(f"[PERINGATAN] Grid tidak valid untuk {warna}: ({c},{r}) -> diabaikan.")
        cleaned[warna] = valid_coords
        total += len(valid_coords)

    return cleaned, total


def flush_camera_buffer(cap, frames=5):
    """
    Buang beberapa frame agar buffer kamera tidak memakai frame lama.
    """
    for _ in range(frames):
        cap.read()


def scan_detections(hsv, allowed_colors=None):
    """
    Scan semua warna dan kembalikan list deteksi:
    [(warna, cX, cY, box, angle, inside_roi, inside_pick_zone), ...]
    """
    detections = []

    for color_name, ranges in COLOR_RANGES.items():
        if allowed_colors is not None and color_name not in allowed_colors:
            continue

        hasil = detect_largest_object(hsv, ranges)
        if hasil is None:
            continue

        cX, cY, box, angle = hasil
        inside_roi = is_inside_roi(cX, cY)
        inside_pick = is_inside_pick_zone(cX, cY)

        detections.append((color_name, cX, cY, box, angle, inside_roi, inside_pick))

    return detections


def choose_inside_pick_zone_candidate(detections):
    """
    Ambil kandidat pertama yang sudah cukup dalam di ROI.
    """
    for det in detections:
        if det[6]:  # inside_pick_zone
            return det
    return None


# =========================================================
# PUBLISH STATE HELPERS
# FIX #3: semua state dikirim sebagai JSON agar konsisten
# dengan node json di Node-RED
# =========================================================
def publish_system_state(state_value):
    mqtt_state["system_state"] = state_value
    publish_telemetry("State/system", {"state": state_value})


def publish_system_mode(mode_value):
    mqtt_state["system_mode"] = mode_value
    publish_telemetry("State/mode", {"mode": mode_value})


def publish_conveyor_state(running: bool):
    mqtt_state["conveyor_running"] = running
    # FIX #4: sertakan label deskriptif selain boolean
    label = "Berjalan" if running else "Berhenti"
    publish_telemetry("Telemetry/conveyor", {"running": running, "status": label})


# =========================================================
# MODE MANUAL
# =========================================================
def run_manual(target_col, target_row):
    if not validate_grid_target(target_col, target_row):
        print(f"[ERROR] Grid manual tidak valid: ({target_col},{target_row})")
        sys.exit(1)

    # FIX #2: gunakan lock agar tidak ada dua sesi manual berjalan bersamaan
    with _manual_lock:
        print(f"[VISION] Memulai mode manual -> target Grid ({target_col}, {target_row})")

        publish_system_mode("manual")

        cap = setup_camera(fps=30, width=640, height=480)
        start_conveyor()
        publish_conveyor_state(True)

        object_found = False
        stable_count = 0
        last_candidate_color = None

        prev_time = time.time()

        try:
            while not object_found:
                ret, frame = cap.read()
                if not ret:
                    print("[ERROR] Gagal membaca frame kamera.")
                    continue

                # Hitung fps sederhana berdasarkan delta antar frame
                now = time.time()
                dt = now - prev_time
                prev_time = now
                if dt > 0:
                    mqtt_state["fps"] = round(1.0 / dt, 1)

                draw_roi(frame, "Area Deteksi (Manual)")
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

                detections = scan_detections(hsv)
                candidate = choose_inside_pick_zone_candidate(detections)

                # Tampilkan semua deteksi yang ditemukan
                for color_name, cX, cY, box, angle, inside_roi, inside_pick in detections:
                    if inside_pick:
                        label = f"{color_name} (PICK ZONE)"
                    elif inside_roi:
                        label = f"{color_name} (INSIDE ROI)"
                    else:
                        label = f"{color_name} (Outside ROI)"
                    draw_detection(frame, box, cX, cY, label, angle)

                # Stabilitas kandidat
                if candidate is not None:
                    color_name, cX, cY, box, angle, inside_roi, inside_pick = candidate

                    mqtt_state["color"] = color_name
                    mqtt_state["x"] = cX
                    mqtt_state["y"] = cY
                    mqtt_state["angle"] = angle

                    if color_name == last_candidate_color:
                        stable_count += 1
                    else:
                        stable_count = 1
                        last_candidate_color = color_name

                    cv2.putText(
                        frame,
                        f"Stable: {stable_count}/{STABLE_FRAMES}",
                        (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2
                    )

                    if stable_count >= STABLE_FRAMES:
                        print(f"\n[INFO] Objek stabil terdeteksi: {color_name} di ROI ({cX}, {cY})")
                        stop_conveyor()
                        publish_conveyor_state(False)

                        time.sleep(POST_STOP_DELAY)

                        publish_system_state("busy")

                        print(f"[AKSI] Robotic arm bergerak ke ({cX}, {cY}) untuk mengambil objek {color_name}")
                        arm_move(cX, cY, color_name, target_col, target_row, angle)
                        print(f"[AKSI] Selesai mengambil {color_name}.")

                        publish_system_state("idle")

                        object_found = True
                        break
                else:
                    stable_count = 0
                    last_candidate_color = None
                    mqtt_state["color"] = None
                    mqtt_state["x"] = None
                    mqtt_state["y"] = None

                # FIX #1: publish x, y, angle sebagai field terpisah agar
                # Node-RED bisa akses {{msg.payload.x}}, {{msg.payload.y}},
                # dan {{msg.payload.angle}} secara individual
                publish_telemetry("Telemetry/dobot", {
                    "x": mqtt_state["x"],
                    "y": mqtt_state["y"],
                    "angle": mqtt_state["angle"],
                })
                publish_telemetry("Telemetry/color", {"color": mqtt_state["color"]})
                publish_telemetry("Telemetry/camera", {"fps": mqtt_state["fps"]})

                cv2.imshow("Camera Feed - Manual Mode", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("[INFO] Program dihentikan melalui tombol 'q'.")
                    break

            if object_found:
                print("[BERHASIL] Mode manual selesai.")

        except KeyboardInterrupt:
            print("\n[WARNING] Mode manual dihentikan paksa oleh pengguna (Ctrl+C).")
        finally:
            cleanup(cap)


# =========================================================
# MODE OTOMATIS
# =========================================================
def run_auto(misi_aktif):
    misi_aktif, total_misi = sanitize_missions(misi_aktif)

    if total_misi == 0:
        print("[ERROR] Tidak ada koordinat target grid yang valid dari HMI. Program dihentikan.")
        sys.exit(1)

    print("\n=== MEMULAI MODE OTOMATIS ===")
    for warna, target_list in misi_aktif.items():
        if target_list:
            grid_str = ", ".join([f"({c},{r})" for c, r in target_list])
            print(f"-> Balok [{warna}] akan ditata ke Grid: {grid_str}")
    print(f"Total target pengerjaan: {total_misi} balok.")
    print("==============================\n")

    publish_system_mode("auto")

    cap = setup_camera(fps=30, width=640, height=480)
    misi_selesai = 0

    start_conveyor()
    publish_conveyor_state(True)
    print("[VISION] Conveyor berjalan. Sistem mulai memindai ROI.")

    stable_count = 0
    last_candidate_key = None

    prev_time = time.time()

    try:
        while misi_selesai < total_misi:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Gagal membaca frame kamera.")
                continue

            now = time.time()
            dt = now - prev_time
            prev_time = now
            if dt > 0:
                mqtt_state["fps"] = round(1.0 / dt, 1)

            draw_roi(frame, f"Auto Mode ({misi_selesai}/{total_misi})")
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            allowed_colors = {warna for warna, daftar in misi_aktif.items() if len(daftar) > 0}
            detections = scan_detections(hsv, allowed_colors=allowed_colors)
            candidate = choose_inside_pick_zone_candidate(detections)

            # Tampilkan semua deteksi
            for color_name, cX, cY, box, angle, inside_roi, inside_pick in detections:
                if inside_pick:
                    label = f"{color_name} (PICK ZONE)"
                elif inside_roi:
                    label = f"{color_name} (INSIDE ROI)"
                else:
                    label = f"{color_name} (Outside ROI)"
                draw_detection(frame, box, cX, cY, label, angle)

            # Kandidat valid harus stabil beberapa frame
            if candidate is not None:
                color_name, cX, cY, box, angle, inside_roi, inside_pick = candidate

                mqtt_state["color"] = color_name
                mqtt_state["x"] = cX
                mqtt_state["y"] = cY
                mqtt_state["angle"] = angle

                candidate_key = color_name

                if candidate_key == last_candidate_key:
                    stable_count += 1
                else:
                    stable_count = 1
                    last_candidate_key = candidate_key

                cv2.putText(
                    frame,
                    f"Stable: {stable_count}/{STABLE_FRAMES}",
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2
                )

                if stable_count >= STABLE_FRAMES:
                    if not misi_aktif[color_name]:
                        # Kuota warna ini ternyata habis, lanjut scan
                        stable_count = 0
                        last_candidate_key = None
                    else:
                        stop_conveyor()
                        publish_conveyor_state(False)

                        time.sleep(POST_STOP_DELAY)

                        target_col, target_row = misi_aktif[color_name].pop(0)

                        print(f"\n[SORT] Menemukan objek warna {color_name} di ROI!")
                        print(f"[AKSI] Ambil ({cX}, {cY}) -> Taruh ke Grid ({target_col}, {target_row})")

                        publish_system_state("busy")

                        arm_move(cX, cY, color_name, target_col, target_row, angle)

                        publish_system_state("idle")

                        misi_selesai += 1
                        print(f"[STATUS] Progress penataan: {misi_selesai}/{total_misi} selesai.\n")

                        stable_count = 0
                        last_candidate_key = None

                        if misi_selesai < total_misi:
                            print("[VISION] Menjalankan kembali conveyor...")
                            start_conveyor()
                            publish_conveyor_state(True)
                            flush_camera_buffer(cap, POST_PICK_FLUSH_FRAMES)
            else:
                stable_count = 0
                last_candidate_key = None
                mqtt_state["color"] = None
                mqtt_state["x"] = None
                mqtt_state["y"] = None

            # FIX #1: struktur payload konsisten, x/y/angle sebagai field terpisah
            publish_telemetry("Telemetry/dobot", {
                "x": mqtt_state["x"],
                "y": mqtt_state["y"],
                "angle": mqtt_state["angle"],
            })
            publish_telemetry("Telemetry/color", {"color": mqtt_state["color"]})
            publish_telemetry("Telemetry/camera", {"fps": mqtt_state["fps"]})

            cv2.imshow("Camera Feed - Auto Mode", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                print("[INFO] Program dihentikan melalui tombol 'q'.")
                break

        if misi_selesai == total_misi:
            print("\n[BERHASIL] Seluruh penataan balok berdasarkan konfigurasi grid HMI selesai!")

    except KeyboardInterrupt:
        print("\n[WARNING] Mode otomatis dihentikan paksa oleh pengguna (Ctrl+C).")
    finally:
        cleanup(cap)


# =========================================================
# MAIN ENTRY POINT
# =========================================================
def main():
    args = parse_arguments()

    setup_mqtt()

    print("[VISION] Menghubungkan ke Dobot...")
    connect_dobot()

    try:
        if args.manual:
            target_col = int(args.manual[0])
            target_row = int(args.manual[1])
            run_manual(target_col, target_row)
        else:
            misi_aktif = {
                "Merah": parse_pairs(args.merah),
                "Kuning": parse_pairs(args.kuning),
                "Hijau": parse_pairs(args.hijau),
                "Biru": parse_pairs(args.biru),
            }

            if sum(len(v) for v in misi_aktif.values()) == 0:
                print("[ERROR] Tidak ada argumen koordinat grid dari HMI. Program dihentikan.")
                sys.exit(1)

            run_auto(misi_aktif)
    finally:
        stop_mqtt()

    sys.exit(0)


if __name__ == "__main__":
    main()