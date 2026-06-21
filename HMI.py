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
# PAGE 4: SMART AUTO-SORT — Konfigurasi Target Warna ke Grid
# ============================================================
class SmartSortPage(tk.Frame):
    """
    User menentukan posisi grid 4x4 untuk masing-masing warna balok.
    Program main_auto.py akan menyusun balok dari conveyor ke posisi tersebut.
    """

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_ACCENT)
        self.controller = controller

        # --- Header ---
        tk.Label(self, text="MODE 2 — SMART AUTO-SORT (COLOR ASSIGNMENT)",
                 font=FONT_HEADER, fg=COLOR_FG, bg=COLOR_ACCENT).pack(pady=15)
        tk.Label(self,
                 text="Tentukan posisi target Kolom (1-4) dan Baris (1-4) untuk setiap warna balok.",
                 font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT).pack()

        # --- Form Setting Warna ---
        form_frame = tk.LabelFrame(self, text=" Pengaturan Posisi Grid Target ", font=FONT_BODY,
                                   fg=COLOR_FG, bg=COLOR_ACCENT, padx=20, pady=15)
        form_frame.pack(pady=20, padx=40, fill=tk.BOTH, expand=True)

        # Konfigurasi Grid Layout di dalam form_frame
        form_frame.columnconfigure(1, weight=1)
        form_frame.columnconfigure(2, weight=1)

        # Header baris form
        tk.Label(form_frame, text="Warna Balok", font=FONT_BTN, fg=COLOR_FG, bg=COLOR_ACCENT).grid(row=0, column=0, pady=5, sticky="w")
        tk.Label(form_frame, text="Kolom (Col)", font=FONT_BTN, fg=COLOR_FG, bg=COLOR_ACCENT).grid(row=0, column=1, pady=5)
        tk.Label(form_frame, text="Baris (Row)", font=FONT_BTN, fg=COLOR_FG, bg=COLOR_ACCENT).grid(row=0, column=2, pady=5)

        # Daftar warna dan variabel penyimpan input
        self.colors = ["Merah", "Hijau", "Kuning", "Biru"]
        self.inputs = {}

        options_grid = ["", "1", "2", "3", "4"] # Kosong berarti warna tersebut tidak diaktifkan/disortir

        for idx, color in enumerate(self.colors):
            row_idx = idx + 1
            
            # Label Warna
            lbl_color = tk.Label(form_frame, text=f"■ {color}", font=FONT_BODY, 
                                 fg=GRID_BTN_COLORS.get(color.lower(), COLOR_FG), bg=COLOR_ACCENT)
            lbl_color.grid(row=row_idx, column=0, pady=10, sticky="w")
            
            # Combobox Kolom
            cb_col = ttk.Combobox(form_frame, values=options_grid, width=8, state="readonly", font=FONT_BODY)
            cb_col.grid(row=row_idx, column=1, pady=10)
            cb_col.current(0) # Default kosong
            
            # Combobox Baris
            cb_row = ttk.Combobox(form_frame, values=options_grid, width=8, state="readonly", font=FONT_BODY)
            cb_row.grid(row=row_idx, column=2, pady=10)
            cb_row.current(0) # Default kosong
            
            # Simpan referensi widget ke dictionary
            self.inputs[color] = {"col": cb_col, "row": cb_row}

        # --- Preview/Status info ---
        self.lbl_info = tk.Label(self, text="Siap menerima penugasan koordinat.", font=FONT_SMALL,
                                  fg="#95a5a6", bg=COLOR_ACCENT)
        self.lbl_info.pack()

        # --- Tombol aksi ---
        btn_frame = tk.Frame(self, bg=COLOR_ACCENT)
        btn_frame.pack(pady=15)

        self.btn_start = tk.Button(btn_frame, text="▶  MULAI MISI AUTO-SORT",
                                   font=FONT_BTN, bg=COLOR_BTN_2, fg="white",
                                   width=28, height=2, command=self._start_process)
        self.btn_start.pack(pady=8)

        self.btn_back = tk.Button(btn_frame, text="Kembali ke Menu",
                                  font=FONT_BODY, bg="#95a5a6", fg="white",
                                  command=lambda: controller.show_frame("ModeSelectionPage"))
        self.btn_back.pack(pady=5)

    def _start_process(self):
        # 1. Bangun argument list berdasarkan input combobox
        args_to_send = []
        summary_msg = "Konfirmasi target sorting:\n"
        has_assignment = False

        for color in self.colors:
            col_val = self.inputs[color]["col"].get()
            row_val = self.inputs[color]["row"].get()
            
            # Jika kedua combobox kolom & baris diisi
            if col_val != "" and row_val != "":
                args_to_send.extend([f"--{color.lower()}", col_val, row_val])
                summary_msg += f"- {color} -> Grid ({col_val}, {row_val})\n"
                has_assignment = True
            elif (col_val != "" and row_val == "") or (col_val == "" and row_val != ""):
                messagebox.showwarning("Input Tidak Lengkap", f"Koordinat untuk warna {color} harus diisi lengkap (Kolom DAN Baris)!")
                return

        if not has_assignment:
            messagebox.showwarning("Input Kosong", "Minimal tentukan posisi target untuk satu warna balok!")
            return

        if not messagebox.askyesno("Konfirmasi Misi", f"{summary_msg}\nApakah susunan di atas sudah benar?"):
            return

        # Disable tombol agar tidak double klik saat proses berjalan
        self.btn_start.configure(state=tk.DISABLED, bg="#7f8c8d")
        self.btn_back.configure(state=tk.DISABLED)
        self.lbl_info.configure(text="⏳ Proses sortir otomatis sedang berjalan...", fg=COLOR_SELECTED)

        # Jalankan di thread terpisah agar GUI tidak membeku (freeze)
        threading.Thread(target=self._run_thread, args=(args_to_send,), daemon=True).start()

    def _run_thread(self, args):
        # Memanggil main_auto.py secara blocking dengan argumen warna dinamis
        success = self.controller.run_script_blocking("main_auto.py", args)
        self.after(0, lambda: self._on_done(success))

    def _on_done(self, success):
        # Mengembalikan status tombol aktif kembali
        self.btn_start.configure(state=tk.NORMAL, bg=COLOR_BTN_2)
        self.btn_back.configure(state=tk.NORMAL)
        if success:
            self.lbl_info.configure(text="✅ Misi selesai.", fg="#27ae60")
            messagebox.showinfo("Selesai", "Proses Auto-Sort selesai menata seluruh balok target!")
        else:
            self.lbl_info.configure(text="❌ Misi gagal atau dihentikan. Periksa log terminal.", fg=COLOR_DANGER)

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app = DobotIntegratedApp()
    app.mainloop()