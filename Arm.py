from pydobotplus import Dobot, CustomPosition
from time import sleep
import config


# ==========================================
# POSISI DASAR
# ==========================================

def get_posisi_awal():
    return CustomPosition(
        config.DOBOT_ORIGIN_X, config.DOBOT_ORIGIN_Y,
        config.DOBOT_Z_TRAVEL, config.DOBOT_R
    )

def get_posisi_kamera():
    return CustomPosition(360, 350, config.DOBOT_Z_TRAVEL, config.DOBOT_R)


# ==========================================
# 16 POSISI DROP ZONE (grid 4×4, 1-indexed)
# Urutan: baris demi baris, kiri ke kanan
#   (col=1,row=1)=A  (col=2,row=1)=B  (col=3,row=1)=C  (col=4,row=1)=D
#   (col=1,row=2)=E  ...              ...              (col=4,row=2)=H
#   ...
#   (col=1,row=4)=M  ...              ...              (col=4,row=4)=P
#
# ⚠️  Sesuaikan nilai X, Y, Z dengan pengukuran fisik robot Anda!
# ==========================================

def _grid_positions():
    """
    Kembalikan dict {(col, row): CustomPosition} untuk semua 16 sel.
    Ubah nilai X/Y/Z di sini sesuai koordinat fisik drop zone.
    """
    # Contoh layout: kolom bergerak di sumbu X, baris di sumbu Y
    # Jarak antar sel: sesuaikan CELL_SPACING_X / CELL_SPACING_Y
    #
    # Titik referensi pojok kiri-atas (col=1, row=1):
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


# ==========================================
# GERAK DASAR
# ==========================================

def ke_posisi_awal(device: Dobot):
    pos = get_posisi_awal()
    device.move_to(pos.x, pos.y, pos.z, pos.r, wait=True)


def ke_posisi_kamera(device: Dobot):
    pos = get_posisi_kamera()
    device.move_to(pos.x, pos.y, pos.z, pos.r, wait=True)


# ==========================================
# AKSI PICK & PLACE
# ==========================================

def pick_payload(device: Dobot, position: CustomPosition):
    print("[PICK] Mengambil payload...")
    ke_posisi_kamera(device)
    sleep(1)
    device.move_to(position.x, position.y, config.DOBOT_Z_PICK, position.r, wait=True)
    sleep(1)
    device.grip(enable=False)   # GRIP ON
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
    device.move_to(position.x, position.y, config.DOBOT_Z_PLACE, position.r, wait=True)
    sleep(1)
    device.grip(enable=True)    # GRIP OFF
    sleep(1)
    ke_posisi_awal(device)
    sleep(1)


# ==========================================
# SEKUENS UTAMA — satu fungsi untuk semua 16 posisi
# ==========================================

def jalankan_posisi(device: Dobot, col: int, row: int):
    target = get_dropzone(col, row)
    label  = chr(ord('A') + (row - 1) * 4 + (col - 1))
    print(f"[POSISI {label}] Grid ({col},{row}) → X:{target.x} Y:{target.y} Z:{target.z}")

    pick_payload(device, get_posisi_kamera())
    place_payload(device, target)
    ke_posisi_awal(device)
    print(f"[POSISI {label}] Selesai.")


# ==========================================
# HELPER — build dispatch map untuk main.py
# ==========================================

def build_posisi_map():
    return {
        (col, row): (lambda dev, c=col, r=row: jalankan_posisi(dev, c, r))
        for row in range(1, 5)
        for col in range(1, 5)
    }


# ==========================================
# ALIAS — tetap kompatibel dengan posA.py lama
# ==========================================

def posisiA(device): jalankan_posisi(device, col=1, row=1)
def posisiB(device): jalankan_posisi(device, col=2, row=1)
def posisiC(device): jalankan_posisi(device, col=3, row=1)
def posisiD(device): jalankan_posisi(device, col=4, row=1)
def posisiE(device): jalankan_posisi(device, col=1, row=2)
def posisiF(device): jalankan_posisi(device, col=2, row=2)
def posisiG(device): jalankan_posisi(device, col=3, row=2)
def posisiH(device): jalankan_posisi(device, col=4, row=2)
def posisiI(device): jalankan_posisi(device, col=1, row=3)
def posisiJ(device): jalankan_posisi(device, col=2, row=3)
def posisiK(device): jalankan_posisi(device, col=3, row=3)
def posisiL(device): jalankan_posisi(device, col=4, row=3)
def posisiM(device): jalankan_posisi(device, col=1, row=4)
def posisiN(device): jalankan_posisi(device, col=2, row=4)
def posisiO(device): jalankan_posisi(device, col=3, row=4)
def posisiP(device): jalankan_posisi(device, col=4, row=4)