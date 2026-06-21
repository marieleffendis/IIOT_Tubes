"""
gabung.py

GUI utama sistem Dobot Magician.
Halaman:
    1. LoginPage          — autentikasi
    2. ModeSelectionPage  — pilih MODE 1 (Manual Grid) atau MODE 2 (Auto Sort)
    3. DirectControlPage  — 16 tombol grid 4×4 untuk kontrol manual (1-indexed)
    4. SmartSortPage      — upload gambar target PNG, jalankan otomatis
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import sys
import os
import threading

# ============================================================
# STYLE
# ============================================================
FONT_HEADER    = ("Helvetica", 16, "bold")
FONT_SUBHEADER = ("Helvetica", 14, "bold")
FONT_BODY      = ("Helvetica", 12)
FONT_BTN       = ("Helvetica", 11, "bold")
FONT_SMALL     = ("Helvetica", 9)

COLOR_BG       = "#2c3e50"
COLOR_FG       = "white"
COLOR_ACCENT   = "#34495e"
COLOR_BTN_1    = "#1abc9c"
COLOR_BTN_2    = "#e67e22"
COLOR_DANGER   = "#e74c3c"
COLOR_SELECTED = "#f39c12"

# Warna tombol grid sesuai label warna (dekorasi saja)
GRID_BTN_COLORS = {
    "red"   : "#c0392b",
    "green" : "#27ae60",
    "blue"  : "#2980b9",
    "yellow": "#f1c40f",
}


# ============================================================
# APLIKASI UTAMA
# ============================================================
class DobotIntegratedApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Dobot Magician — IIoT Control System")
        self.attributes("-fullscreen", True)

        self.current_process = None
        self.dobot_device = None

        # Binding keyboard
        self.bind("<Escape>", lambda e: self.confirm_exit())
        self.bind("p", self.emergency_stop)
        self.bind("P", self.emergency_stop)

        # Container frame
        self.container = tk.Frame(self)
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # Status bar
        self.status_var = tk.StringVar(value="[INFO] Menghubungkan ke Dobot & Homing (Silakan Tunggu)...")
        tk.Label(self, textvariable=self.status_var, bd=1, relief=tk.SUNKEN,
                 anchor=tk.W, bg="#dcdcdc", font=FONT_SMALL).pack(side=tk.BOTTOM, fill=tk.X)

        # Daftar halaman
        self.frames = {}
        for F in (LoginPage, ModeSelectionPage, DirectControlPage, SmartSortPage):
            frame = F(parent=self.container, controller=self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginPage")

    def show_frame(self, page_name):
        self.frames[page_name].tkraise()
    

    def confirm_exit(self):
        if messagebox.askokcancel("Keluar", "Tutup aplikasi?"):
            self.destroy()
            sys.exit()

    def emergency_stop(self, event=None):
        print("[EMERGENCY] Tombol P ditekan!")
        if self.current_process and self.current_process.poll() is None:
            self.current_process.kill()
        self.status_var.set("⛔ EMERGENCY STOP TRIGGERED!")
        messagebox.showwarning("EMERGENCY", "Sistem dihentikan paksa!")

    def get_script_path(self, script_name):
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, script_name)
        if not os.path.exists(path):
            path = os.path.join(base, "unit_test", script_name)
        return path

    def run_script_blocking(self, script_name, args=None):
        if args is None:
            args = []
        path = self.get_script_path(script_name)

        if not os.path.exists(path):
            self.status_var.set(f"Error: {script_name} tidak ditemukan")
            messagebox.showerror("File Missing", f"File {script_name} tidak ditemukan!")
            return False

        try:
            cmd = [sys.executable, path] + args
            self.status_var.set(f"▶ Menjalankan: {script_name} {' '.join(args)}")
            print(f"[RUN] {cmd}")

            self.current_process = subprocess.Popen(cmd)
            self.current_process.wait()

            rc = self.current_process.returncode
            if rc == 0:
                self.status_var.set("✅ Proses Selesai.")
                return True
            else:
                self.status_var.set(f"❌ Error (Code {rc})")
                return False

        except Exception as e:
            self.status_var.set(f"System Error: {e}")
            return False
        finally:
            self.current_process = None


# ============================================================
# PAGE 1: LOGIN
# ============================================================
class LoginPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        tk.Label(self, text="SISTEM INTEGRASI DOBOT MAGICIAN",
                 font=FONT_HEADER, fg=COLOR_FG, bg=COLOR_BG).pack(pady=40)
        tk.Label(self, text="Tekan  P  untuk Emergency Stop  |  Esc untuk Keluar",
                 font=FONT_SMALL, fg=COLOR_DANGER, bg=COLOR_BG).pack()

        frm = tk.Frame(self, bg=COLOR_BG)
        frm.pack(pady=30)

        tk.Label(frm, text="Username:", font=FONT_BODY, fg=COLOR_FG, bg=COLOR_BG).grid(row=0, column=0, padx=10, pady=8, sticky="e")
        self.entry_user = tk.Entry(frm, font=FONT_BODY)
        self.entry_user.grid(row=0, column=1, padx=10, pady=8)
        self.entry_user.insert(0, "pi")

        tk.Label(frm, text="Password:", font=FONT_BODY, fg=COLOR_FG, bg=COLOR_BG).grid(row=1, column=0, padx=10, pady=8, sticky="e")
        self.entry_pass = tk.Entry(frm, font=FONT_BODY, show="*")
        self.entry_pass.grid(row=1, column=1, padx=10, pady=8)
        self.entry_pass.insert(0, "1234")

        self.entry_pass.bind("<Return>", lambda e: self.check_login())

        tk.Button(self, text="LOGIN", font=FONT_BTN, bg="#27ae60", fg="white",
                  width=18, command=self.check_login).pack(pady=25)

    def check_login(self):
        if self.entry_user.get() == "pi" and self.entry_pass.get() == "1234":
            self.entry_user.delete(0, "end")
            self.entry_pass.delete(0, "end")
            self.controller.show_frame("ModeSelectionPage")
        else:
            messagebox.showerror("Login Gagal", "Username atau password salah.")


# ============================================================
# PAGE 2: MODE SELECTION
# ============================================================
class ModeSelectionPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#ecf0f1")
        self.controller = controller

        tk.Label(self, text="PILIH MODE OPERASI", font=FONT_HEADER,
                 bg="#ecf0f1", fg="#2c3e50").pack(pady=40)

        frm = tk.Frame(self, bg="#ecf0f1")
        frm.pack(expand=True)

        btn_cfg = dict(font=FONT_BTN, fg="white", width=22, height=6)

        tk.Button(frm, text="MODE 1\nDirect Control\n(Pilih Posisi Grid Manual)",
                  bg=COLOR_BTN_1, **btn_cfg,
                  command=lambda: controller.show_frame("DirectControlPage")
                  ).grid(row=0, column=0, padx=40, pady=20)

        tk.Button(frm, text="MODE 2\nSmart Auto-Sort\n(Upload Gambar Target)",
                  bg=COLOR_BTN_2, **btn_cfg,
                  command=lambda: controller.show_frame("SmartSortPage")
                  ).grid(row=0, column=1, padx=40, pady=20)

        tk.Button(self, text="Logout", font=FONT_BODY, bg="#95a5a6", fg="white",
                  command=lambda: controller.show_frame("LoginPage")).pack(pady=20)


# ============================================================
# PAGE 3: DIRECT CONTROL — 16 tombol grid 4×4 (1-indexed)
# ============================================================
class DirectControlPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_ACCENT)
        self.controller  = controller
        self.all_buttons = []
        self.selected_btn = None

        # --- Header ---
        tk.Label(self, text="MODE 1 — DIRECT GRID CONTROL",
                 font=FONT_HEADER, fg=COLOR_FG, bg=COLOR_ACCENT).pack(pady=15)
        tk.Label(self,
                 text="Klik satu posisi pada grid 4×4. Robot akan bergerak ke posisi tersebut.",
                 font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT).pack()

        # --- Grid tombol ---
        grid_frame = tk.Frame(self, bg=COLOR_ACCENT)
        grid_frame.pack(pady=20)

        # Header kolom
        tk.Label(grid_frame, text="", bg=COLOR_ACCENT, width=4).grid(row=0, column=0)
        for c in range(1, 5):
            tk.Label(grid_frame, text=f"Col {c}", font=FONT_SMALL,
                     fg="#7f8c8d", bg=COLOR_ACCENT, width=10).grid(row=0, column=c)

        for row in range(1, 5):
            # Header baris
            tk.Label(grid_frame, text=f"Row {row}", font=FONT_SMALL,
                     fg="#7f8c8d", bg=COLOR_ACCENT).grid(row=row, column=0, padx=4)
            for col in range(1, 5):
                label = f"({col},{row})"
                btn   = tk.Button(
                    grid_frame,
                    text=label,
                    font=FONT_BTN,
                    bg=COLOR_BTN_1,
                    fg="white",
                    width=8,
                    height=3,
                    relief=tk.RAISED,
                    command=lambda c=col, r=row: self._on_grid_click(c, r)
                )
                btn.grid(row=row, column=col, padx=3, pady=3)
                self.all_buttons.append(btn)

        # --- Tombol bawah ---
        bottom = tk.Frame(self, bg=COLOR_ACCENT)
        bottom.pack(pady=10)

        self.lbl_selected = tk.Label(bottom, text="Posisi dipilih: —",
                                     font=FONT_BODY, fg=COLOR_SELECTED, bg=COLOR_ACCENT)
        self.lbl_selected.pack(pady=5)

        self.btn_execute = tk.Button(bottom, text="▶  EKSEKUSI ROBOT", font=FONT_BTN,
                                     bg=COLOR_DANGER, fg="white", width=22, height=2,
                                     state=tk.DISABLED, command=self._execute_selected)
        self.btn_execute.pack(pady=5)

        self.btn_back = tk.Button(bottom, text="Kembali ke Menu", font=FONT_BODY,
                                  bg="#95a5a6", fg="white",
                                  command=lambda: controller.show_frame("ModeSelectionPage"))
        self.btn_back.pack(pady=8)
        self.all_buttons.append(self.btn_back)
        self.all_buttons.append(self.btn_execute)

        self._selected_col = None
        self._selected_row = None

    def _on_grid_click(self, col, row):
        # Tandai tombol yang dipilih.
        # Reset highlight tombol sebelumnya
        for btn in self.all_buttons:
            if btn not in (self.btn_back, self.btn_execute):
                btn.configure(bg=COLOR_BTN_1, relief=tk.RAISED)

        # Highlight tombol terpilih
        # Temukan tombol yang sesuai (col,row) dari list
        idx = (row - 1) * 4 + (col - 1)
        self.all_buttons[idx].configure(bg=COLOR_SELECTED, relief=tk.SUNKEN)

        self._selected_col = col
        self._selected_row = row
        self.lbl_selected.configure(text=f"Posisi dipilih: ({col}, {row})")
        self.btn_execute.configure(state=tk.NORMAL)

    def _execute_selected(self):
        if self._selected_col is None:
            return
        col, row = self._selected_col, self._selected_row

        # Lock semua tombol
        for btn in self.all_buttons:
            btn.configure(state=tk.DISABLED)

        threading.Thread(
            target=self._run_thread,
            args=(col, row),
            daemon=True
        ).start()

    def _run_thread(self, col, row):
        self.controller.run_script_blocking(
            "Manual.py", ["--manual", str(col), str(row)]
        )
        self.after(0, self._unlock_buttons)

    def _unlock_buttons(self):
        for btn in self.all_buttons:
            if btn == self.btn_back:
                btn.configure(state=tk.NORMAL, bg="#95a5a6")
            elif btn == self.btn_execute:
                btn.configure(state=tk.DISABLED)   # tetap disabled sampai pilih lagi
            else:
                btn.configure(state=tk.NORMAL, bg=COLOR_BTN_1, relief=tk.RAISED)
        # Reset highlight
        if self._selected_col is not None:
            idx = (self._selected_row - 1) * 4 + (self._selected_col - 1)
            self.all_buttons[idx].configure(bg=COLOR_BTN_1)
        self._selected_col = None
        self._selected_row = None
        self.lbl_selected.configure(text="Posisi dipilih: —")


# ============================================================
# PAGE 4: SMART AUTO-SORT — Interaktif Grid Visual assignment
# ============================================================
class SmartSortPage(tk.Frame):
    """
    User memilih warna di panel kiri, lalu mengeklik posisi grid 4x4 di kanan
    untuk memetakan lokasi penataan balok. Argumen dikirim ke main_auto.py.
    """

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_ACCENT)
        self.controller = controller

        # --- Status Variabel Internal ---
        self.selected_color = tk.StringVar(value="Merah") # Default warna terpilih pertama
        self.color_options = ["Merah", "Kuning", "Hijau", "Biru"]
        
        # Menyimpan peta hasil assignment: {(col, row): "Warna" atau None}
        self.grid_assignments = {}
        # Menyimpan referensi widget tombol grid kanan: {(col, row): widget_button}
        self.grid_buttons = {}

        # --- Header Atas ---
        tk.Label(self, text="MODE 2 — SMART AUTO-SORT (GRID ASSIGNMENT)",
                 font=FONT_HEADER, fg=COLOR_FG, bg=COLOR_ACCENT).pack(pady=10)
        tk.Label(self,
                 text="Langkah: 1) Pilih warna di kiri. 2) Klik kotak pada grid kanan untuk menaruh. (Klik ulang grid untuk hapus)",
                 font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT).pack(pady=2)

        # --- Main Workspace Splitter (Kiri & Kanan) ---
        workspace_frame = tk.Frame(self, bg=COLOR_ACCENT)
        workspace_frame.pack(pady=15, padx=20, fill=tk.BOTH, expand=True)

        # --------------------------------------------------------
        # PANEL KIRI: Pemilih Warna Aktif
        # --------------------------------------------------------
        left_panel = tk.LabelFrame(workspace_frame, text=" 1. Pilih Warna Balok ", font=FONT_BODY,
                                   fg=COLOR_FG, bg=COLOR_ACCENT, padx=15, pady=15)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 20))

        self.color_selector_btns = {}
        for color in self.color_options:
            # Menggunakan skema warna yang selaras dengan aplikasi
            btn_bg = GRID_BTN_COLORS.get(color.lower(), "#7f8c8d")
            text_fg = "white" if color != "Kuning" else "black" # Kuning teks hitam agar kontras

            btn = tk.Button(left_panel, text=f"■  {color}", font=FONT_BTN,
                            bg=btn_bg, fg=text_fg, width=14, height=2, relief=tk.RAISED,
                            command=lambda c=color: self._set_active_color(c))
            btn.pack(pady=10)
            self.color_selector_btns[color] = btn

        # Set highlight awal pada warna default (Merah)
        self._set_active_color("Merah")

        # --------------------------------------------------------
        # PANEL KANAN: Grid 4x4 Visual Interaktif
        # --------------------------------------------------------
        right_panel = tk.LabelFrame(workspace_frame, text=" 2. Papan Target Penataan 4x4 ", font=FONT_BODY,
                                    fg=COLOR_FG, bg=COLOR_ACCENT, padx=20, pady=15)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 10))

        # Mengatur berat kolom/baris agar grid fleksibel melebar rata
        for i in range(5):
            right_panel.columnconfigure(i, weight=1)
            right_panel.rowconfigure(i, weight=1)

        # Label Header Kolom (Col 1 - 4)
        for c in range(1, 5):
            tk.Label(right_panel, text=f"Col {c}", font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT).grid(row=0, column=c, sticky="s")

        # Membuat susunan Tombol Grid 4x4 (Row & Col 1-indexed)
        for row in range(1, 5):
            # Label Header Baris (Row 1 - 4)
            tk.Label(right_panel, text=f"Row {row}", font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT).grid(row=row, column=0, sticky="e", padx=(0, 5))
            
            for col in range(1, 5):
                coord = (col, row)
                self.grid_assignments[coord] = None # Set awal kosong

                # Buat tombol grid default (Kosong, warna abu-abu netral)
                btn_grid = tk.Button(
                    right_panel,
                    text=".", # Default teks titik penunjuk kosong
                    font=FONT_BTN,
                    bg="#7f8c8d",
                    fg="white",
                    relief=tk.RAISED,
                    bd=2,
                    command=lambda c=col, r=row: self._on_grid_cell_click(c, r)
                )
                btn_grid.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
                self.grid_buttons[coord] = btn_grid

        # --- Control & Status Section (Bawah) ---
        bottom_frame = tk.Frame(self, bg=COLOR_ACCENT)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 15))

        self.lbl_info = tk.Label(bottom_frame, text="Sistem siap. Silakan petakan susunan warna.", 
                                  font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT)
        self.lbl_info.pack()

        btn_action_frame = tk.Frame(bottom_frame, bg=COLOR_ACCENT)
        btn_action_frame.pack(pady=5)

        self.btn_start = tk.Button(btn_action_frame, text="▶  MULAI MISI AUTO-SORT",
                                   font=FONT_BTN, bg=COLOR_BTN_2, fg="white",
                                   width=26, height=2, command=self._start_process)
        self.btn_start.pack(side=tk.LEFT, padx=10)

        self.btn_back = tk.Button(btn_action_frame, text="Kembali ke Menu",
                                  font=FONT_BODY, bg="#95a5a6", fg="white", width=16, height=2,
                                  command=lambda: controller.show_frame("ModeSelectionPage"))
        self.btn_back.pack(side=tk.LEFT, padx=10)

    def _set_active_color(self, color):
        """ Mengganti fokus pilihan warna aktif di panel bagian kiri """
        self.selected_color.set(color)
        
        # Reset border semua tombol warna kiri
        for c, btn in self.color_selector_btns.items():
            btn.configure(relief=tk.RAISED, bd=2)
            
        # Beri efek tertekan dalam (Sunken) dan border tebal pada warna aktif
        self.color_selector_btns[color].configure(relief=tk.SUNKEN, bd=5)

    def _on_grid_cell_click(self, col, row):
        """ Menangani klik tombol grid visual kanan """
        coord = (col, row)
        current_assigned = self.grid_assignments[coord]
        active_color = self.selected_color.get()

        # JIKA kotak tersebut sudah berisi warna yang SAMA, lakukan RESET (Hapus penugasan)
        if current_assigned == active_color:
            self.grid_assignments[coord] = None
            self.grid_buttons[coord].configure(text=".", bg="#7f8c8d", fg="white")
            print(f"[GUI] Reset Grid ({col},{row}) menjadi kosong.")
        else:
            # JIKA kosong atau berisi warna lain, overwrite dengan warna aktif sekarang
            self.grid_assignments[coord] = active_color
            bg_target = GRID_BTN_COLORS.get(active_color.lower(), "#2c3e50")
            text_fg = "white" if active_color != "Kuning" else "black"
            
            # Ubah teks tombol menampilkan koordinat penugasan (X, Y) sesuai maumu
            self.grid_buttons[coord].configure(text=f"({col},{row})", bg=bg_target, fg=text_fg)
            print(f"[GUI] Assign Warna {active_color} ke Grid ({col},{row}).")

    def _start_process(self):
        """ Menyusun argument CLI dari grid data untuk dikirim ke main_auto.py """
        args_to_send = []
        summary_msg = "Konfirmasi target sorting otomatis:\n"
        has_assignment = False

        # Kelompokkan penugasan berdasarkan jenis warna balok
        color_batches = {"merah": [], "kuning": [], "hijau": [], "biru": []}

        for coord, color in self.grid_assignments.items():
            if color is not None:
                col, row = coord
                color_key = color.lower()
                color_batches[color_key].append(f"{col},{row}")
                has_assignment = True

        if not has_assignment:
            messagebox.showwarning("Papan Grid Kosong", "Silakan tentukan minimal satu posisi warna pada papan grid target!")
            return

        # Mengemas argumen dalam format dinamis, misal: --merah 1,1 2,1 --kuning 4,3
        for color_name, pairs in color_batches.items():
            if pairs:
                args_to_send.append(f"--{color_name}")
                args_to_send.extend(pairs)
                summary_msg += f"- {color_name.capitalize()}: {', '.join([f'Grid({p})' for p in pairs])}\n"

        if not messagebox.askyesno("Konfirmasi Penataan", f"{summary_msg}\nApakah tata letak di atas sudah sesuai susunan fisik?"):
            return

        # Kunci interaksi GUI saat jalan
        self.btn_start.configure(state=tk.DISABLED, bg="#7f8c8d")
        self.btn_back.configure(state=tk.DISABLED)
        self.lbl_info.configure(text="⏳ Lengan robot sedang menyusun balok secara otomatis...", fg=COLOR_SELECTED)

        # Eksekusi script backend di dalam thread agar GUI tidak freeze
        threading.Thread(target=self._run_thread, args=(args_to_send,), daemon=True).start()

    def _run_thread(self, args):
        success = self.controller.run_script_blocking("main_auto.py", args)
        self.after(0, lambda: self._on_done(success))

    def _on_done(self, success):
        # Buka kembali kunci tombol GUI
        self.btn_start.configure(state=tk.NORMAL, bg=COLOR_BTN_2)
        self.btn_back.configure(state=tk.NORMAL)
        if success:
            self.lbl_info.configure(text="✅ Penataan selesai.", fg="#27ae60")
            messagebox.showinfo("Sukses", "Dobot selesai menata seluruh balok sesuai tata letak grid!")
        else:
            self.lbl_info.configure(text="❌ Proses terhenti atau gagal. Cek log konsol terminal.", fg=COLOR_DANGER)

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app = DobotIntegratedApp()
    app.mainloop()