from pydobotplus import Dobot, CustomPosition
from time import sleep

DOBOT_ORIGIN_X   = 49      # x saat col=1
DOBOT_ORIGIN_Y   = 200     # y saat row=1
DOBOT_Z_PLACE    = -35.0   # z saat meletakkan blok
DOBOT_Z_PICK     = -55.0   # z saat mengambil blok dari conveyor (estimasi, kalibrasi ulang)
DOBOT_Z_TRAVEL   = 20.0    # z aman saat perpindahan
DOBOT_R          = 19      # rotasi claw (tetap)

def get_posisi_awal():
    return CustomPosition(
        DOBOT_ORIGIN_X, DOBOT_ORIGIN_Y,
        DOBOT_Z_TRAVEL, DOBOT_R
    )

def get_posisi_kamera():
    return CustomPosition(360, 350, DOBOT_Z_TRAVEL, DOBOT_R)

def _grid_positions():
    ORIGIN_X    =  49      # X untuk col=1
    ORIGIN_Y    = 200      # Y untuk row=1
    SPACING_X   = -20      # Pergeseran X setiap kolom bertambah 1  (negatif = menjauhi robot)
    SPACING_Y   = -20      # Pergeseran Y setiap baris bertambah 1
    Z_DROP      = -35      # Ketinggian drop zone (sama untuk semua)
    R_DROP      = 100      # Rotasi tool

    positions = {}
    for row in range(1, 5):
        for col in range(1, 5):
            x = ORIGIN_X + (col - 1) * SPACING_X
            y = ORIGIN_Y + (row - 1) * SPACING_Y
            positions[(col, row)] = CustomPosition(x, y, Z_DROP, R_DROP)
    return positions

# Build sekali saat modul diload
_GRID_POS = _grid_positions()


def get_dropzone(col: int, row: int) -> CustomPosition:
    """Kembalikan CustomPosition untuk sel grid (col, row), 1-indexed."""
    if (col, row) not in _GRID_POS:
        raise ValueError(f"Posisi grid ({col},{row}) tidak valid. Gunakan 1–4.")
    return _GRID_POS[(col, row)]

def ke_posisi_awal(device: Dobot):
    pos = get_posisi_awal()
    device.move_to(pos.x, pos.y, pos.z, pos.r, wait=True)


def ke_posisi_kamera(device: Dobot):
    pos = get_posisi_kamera()
    device.move_to(pos.x, pos.y, pos.z, pos.r, wait=True)


def pick_payload(device: Dobot, position: CustomPosition):
    print("[PICK] Mengambil payload...")
    ke_posisi_kamera(device)
    sleep(1)
    device.move_to(position.x, position.y, DOBOT_Z_PICK, position.r, wait=True)
    sleep(1)
    device.suck(True)   # GRIP ON
    sleep(1)
    ke_posisi_awal(device)
    sleep(1)


def place_payload(device: Dobot, position: CustomPosition):
    print("[PLACE] Meletakkan payload...")
    ke_posisi_kamera(device)
    sleep(1)
    ke_posisi_awal(device)
    sleep(1)
    device.move_to(position.x, position.y, position.z, position.r, wait=True)
    sleep(1)
    device.move_to(position.x, position.y, DOBOT_Z_PLACE, position.r, wait=True)
    sleep(1)
    device.suck(False)    # GRIP OFF
    sleep(1)
    ke_posisi_awal(device)
    sleep(1)

def jalankan_posisi(device: Dobot, col: int, row: int):
    target = get_dropzone(col, row)
    label  = chr(ord('A') + (row - 1) * 4 + (col - 1))
    print(f"[POSISI {label}] Grid ({col},{row}) → X:{target.x} Y:{target.y} Z:{target.z}")

    pick_payload(device, get_posisi_kamera())
    place_payload(device, target)
    ke_posisi_awal(device)
    print(f"[POSISI {label}] Selesai.")

def build_posisi_map():
    return {
        (col, row): (lambda dev, c=col, r=row: jalankan_posisi(dev, c, r))
        for row in range(1, 5)
        for col in range(1, 5)
    }