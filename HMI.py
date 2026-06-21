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

from IIOT_Tubes.Actuator import init_dobot

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
    def _initialize_dobot_at_start(self):
            """Melakukan homing sekali saja saat aplikasi HMI dibuka"""
            try:
                self.dobot_device = init_dobot()
                if self.dobot_device:
                    self.status_var.set("Status: Dobot Siap — Silakan Login & Pilih Mode")
                else:
                    self.status_var.set("Status: ❌ Gagal Terhubung ke Dobot!")
            except Exception as e:
                self.status_var.set(f"Status: Error Koneksi ({e})")
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
# PAGE 4: SMART AUTO-SORT — Visual Grid & Live Summary Panel
# ============================================================
class SmartSortPage(tk.Frame):
    """
    Halaman Auto-Sort yang user-friendly dan profesional.
    User memilih warna aktif di kiri, memetakan grid di kanan.
    Dilengkapi panel ringkasan (summary) real-time agar bebas dari salah input.
    """

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        # --- Variabel Kontrol Internal ---
        self.selected_color = tk.StringVar(value="Merah")
        self.color_options = ["Merah", "Kuning", "Hijau", "Biru"]
        
        # Peta penugasan: {(col, row): "Warna" atau None}
        self.grid_assignments = {(c, r): None for c in range(1, 5) for r in range(1, 5)}
        self.grid_buttons = {}

        # --- Header Utama ---
        header_frame = tk.Frame(self, bg=COLOR_BG)
        header_frame.pack(pady=(15, 5), fill=tk.X)
        
        tk.Label(header_frame, text="⚙️ MODE 2 — SMART AUTO-SORT SYSTEM",
                 font=FONT_HEADER, fg=COLOR_FG, bg=COLOR_BG).pack()
        tk.Label(header_frame,
                 text="Pilih warna balok di panel kiri, lalu klik kotak grid tujuan di panel kanan untuk menata susunan.",
                 font=FONT_SMALL, fg="#95a5a6", bg=COLOR_BG).pack(pady=2)

        # --- Workspace Utama (Split Kiri & Kanan) ---
        workspace = tk.Frame(self, bg=COLOR_BG)
        workspace.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)

        # --------------------------------------------------------
        # PANEL KIRI: Pemilih Warna & Ringkasan Real-Time
        # --------------------------------------------------------
        left_panel = tk.Frame(workspace, bg=COLOR_BG)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 15))

        # Sub-Panel 1: Pemilih Warna Aktif
        color_frame = tk.LabelFrame(left_panel, text=" 1. Pilih Warna Aktif ", font=FONT_BODY,
                                    fg=COLOR_FG, bg=COLOR_ACCENT, padx=15, pady=15, relief=tk.GROOVE)
        color_frame.pack(fill=tk.X, pady=(0, 15))

        self.color_selector_btns = {}
        for color in self.color_options:
            bg_color = GRID_BTN_COLORS.get(color.lower(), "#7f8c8d")
            fg_color = "white" if color != "Kuning" else "black"

            btn = tk.Button(color_frame, text=f"■  Balok {color}", font=FONT_BTN,
                            bg=bg_color, fg=fg_color, width=15, height=2, bd=2, cursor="hand2",
                            command=lambda c=color: self._set_active_color(c))
            btn.pack(pady=6)
            self.color_selector_btns[color] = btn

        # Sorot warna default pertama (Merah)
        self._set_active_color("Merah")

        # Sub-Panel 2: Ringkasan Real-Time (Mencegah Keliru)
        summary_frame = tk.LabelFrame(left_panel, text=" 📋 Ringkasan Penugasan ", font=FONT_BODY,
                                      fg=COLOR_FG, bg=COLOR_ACCENT, padx=15, pady=10, relief=tk.GROOVE)
        summary_frame.pack(fill=tk.BOTH, expand=True)

        self.summary_labels = {}
        for color in self.color_options:
            dot_color = GRID_BTN_COLORS.get(color.lower(), "white")
            
            row_f = tk.Frame(summary_frame, bg=COLOR_ACCENT)
            row_f.pack(fill=tk.X, pady=4)
            
            tk.Label(row_f, text=f"■ {color}:", font=FONT_SMALL, fg=dot_color, bg=COLOR_ACCENT, width=8, anchor="w").pack(side=tk.LEFT)
            
            lbl_pos = tk.Label(row_f, text="Belum diset", font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT, anchor="w")
            lbl_pos.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.summary_labels[color] = lbl_pos

        # --------------------------------------------------------
        # PANEL KANAN: Grid 4x4 Visual Interaktif
        # --------------------------------------------------------
        right_panel = tk.LabelFrame(workspace, text=" 2. Papan Tata Letak Grid Target ", font=FONT_BODY,
                                    fg=COLOR_FG, bg=COLOR_ACCENT, padx=20, pady=15, relief=tk.GROOVE)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Konfigurasi proporsi grid agar melebar proporsional
        for i in range(5):
            right_panel.columnconfigure(i, weight=1)
            right_panel.rowconfigure(i, weight=1)

        # Header teks kolom atas (Col 1 - Col 4)
        for c in range(1, 5):
            tk.Label(right_panel, text=f"KOLOM {c}", font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT).grid(row=0, column=c, pady=(0, 5))

        # Generate matrik tombol 4x4
        for row in range(1, 5):
            # Header teks baris kiri (Row 1 - Row 4)
            tk.Label(right_panel, text=f"BARIS {row}", font=FONT_SMALL, fg="#bdc3c7", bg=COLOR_ACCENT).grid(row=row, column=0, padx=(0, 10), sticky="e")
            
            for col in range(1, 5):
                coord = (col, row)
                
                btn_grid = tk.Button(
                    right_panel,
                    text="Kosong",
                    font=FONT_SMALL,
                    bg="#7f8c8d",
                    fg="#2c3e50",
                    relief=tk.FLAT,
                    bd=1,
                    cursor="hand2"
                )
                btn_grid.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                
                # Bind event klik dan hover animasi
                btn_grid.configure(command=lambda c=col, r=row: self._on_grid_cell_click(c, r))
                btn_grid.bind("<Enter>", lambda e, b=btn_grid: b.configure(state=tk.ACTIVE))
                btn_grid.bind("<Leave>", lambda e, b=btn_grid: b.configure(state=tk.NORMAL))
                
                self.grid_buttons[coord] = btn_grid

        # --------------------------------------------------------
        # PANEL BAWAH: Status Operasi & Tombol Aksi Eksekusi
        # --------------------------------------------------------
        bottom_panel = tk.Frame(self, bg=COLOR_BG)
        bottom_panel.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 15))

        # Garis pembatas tipis profesional
        divider = tk.Frame(bottom_panel, height=2, bg=COLOR_ACCENT)
        divider.pack(fill=tk.X, pady=(0, 10))

        self.lbl_info = tk.Label(bottom_panel, text="Sistem Siap. Silakan lakukan pemetaan grid di atas.", 
                                  font=FONT_BODY, fg=COLOR_BTN_1, bg=COLOR_BG)
        self.lbl_info.pack(pady=2)

        action_btns = tk.Frame(bottom_panel, bg=COLOR_BG)
        action_btns.pack()

        self.btn_start = tk.Button(action_btns, text="▶  JALANKAN AUTO-SORT",
                                   font=FONT_BTN, bg=COLOR_BTN_2, fg="white",
                                   width=25, height=2, bd=0, cursor="hand2",
                                   command=self._start_process)
        self.btn_start.pack(side=tk.LEFT, padx=15)

        self.btn_back = tk.Button(action_btns, text="↩️ Kembali ke Menu",
                                  font=FONT_BODY, bg="#7f8c8d", fg="white",
                                  width=15, height=2, bd=0, cursor="hand2",
                                  command=lambda: controller.show_frame("ModeSelectionPage"))
        self.btn_back.pack(side=tk.LEFT, padx=15)

    def _set_active_color(self, color):
        """ Mengubah fokus pemilihan warna balok pada panel sebelah kiri """
        self.selected_color.set(color)
        for c, btn in self.color_selector_btns.items():
            if c == color:
                btn.configure(relief=tk.SUNKEN, bd=4, highlightbackground="white")
            else:
                btn.configure(relief=tk.RAISED, bd=2)

    def _on_grid_cell_click(self, col, row):
        """ Menangani aksi klik pada matrik tombol koordinat """
        coord = (col, row)
        current_assigned = self.grid_assignments[coord]
        active_color = self.selected_color.get()

        # Kasus 1: Klik ulang pada warna yang sama -> Reset jadi kosong
        if current_assigned == active_color:
            self.grid_assignments[coord] = None
            self.grid_buttons[coord].configure(text="Kosong", bg="#7f8c8d", fg="#2c3e50", font=FONT_SMALL)
        else:
            # Kasus 2: Assign atau overwrite warna baru
            self.grid_assignments[coord] = active_color
            bg_target = GRID_BTN_COLORS.get(active_color.lower(), "#2c3e50")
            text_fg = "white" if active_color != "Kuning" else "black"
            
            # Ubah gaya tombol menjadi mencolok sesuai warna tugasnya
            self.grid_buttons[coord].configure(text=f"Grid ({col},{row})", bg=bg_target, fg=text_fg, font=FONT_BTN)

        # Refresh isi komponen "Panel Ringkasan" di sisi kiri
        self._update_summary_display()

    def _update_summary_display(self):
        """ Memperbarui visual daftar text koordinat pada panel ringkasan secara berkala """
        # Reset penampung data koordinat sementara
        coords_by_color = {color: [] for color in self.color_options}
        
        for coord, color in self.grid_assignments.items():
            if color:
                coords_by_color[color].append(f"({coord[0]},{coord[1]})")
        
        # Tempel hasil pengelompokan ke Label UI masing-masing warna
        for color, label_widget in self.summary_labels.items():
            list_coords = coords_by_color[color]
            if list_coords:
                # Mengurutkan tulisan koordinat agar rapi, contoh: (1,1), (2,1)
                label_widget.configure(text=", ".join(sorted(list_coords)), fg="white", font=FONT_BTN)
            else:
                label_widget.configure(text="Belum diset", fg="#bdc3c7", font=FONT_SMALL)

    def _start_process(self):
        """ Mengompilasi seluruh data grid menjadi string parameter terstruktur untuk main_auto.py """
        args_to_send = []
        summary_msg = "Rencana pengaturan posisi penataan:\n"
        has_assignment = False

        color_batches = {color.lower(): [] for color in self.color_options}

        for coord, color in self.grid_assignments.items():
            if color:
                col, row = coord
                color_batches[color.lower()].append(f"{col},{row}")
                has_assignment = True

        if not has_assignment:
            messagebox.showwarning("Grid Kosong", "Peringatan: Anda belum menentukan satu pun posisi target pada grid!")
            return

        for color_name, pairs in color_batches.items():
            if pairs:
                args_to_send.append(f"--{color_name}")
                args_to_send.extend(pairs)
                summary_msg += f"• Balok {color_name.capitalize()} ➔ {', '.join([f'({p})' for p in pairs])}\n"

        if not messagebox.askyesno("Konfirmasi Misi", f"{summary_msg}\nApakah Anda ingin mengirim koordinat ini ke Dobot Magician?"):
            return

        # Mengunci seluruh tombol agar tidak terjadi double-trigger crash selama robot bekerja
        self.btn_start.configure(state=tk.DISABLED, bg="#7f8c8d")
        self.btn_back.configure(state=tk.DISABLED)
        self.lbl_info.configure(text="⏳ Lengan robot terhubung. Menjalankan proses sorting otomatis...", fg=COLOR_SELECTED)

        # Meluncurkan background sub-process thread
        threading.Thread(target=self._run_thread, args=(args_to_send,), daemon=True).start()

    def _run_thread(self, args):
        success = self.controller.run_script_blocking("main_auto.py", args)
        self.after(0, lambda: self._on_done(success))

    def _on_done(self, success):
        # Membuka kembali proteksi tombol interaksi UI
        self.btn_start.configure(state=tk.NORMAL, bg=COLOR_BTN_2)
        self.btn_back.configure(state=tk.NORMAL)
        if success:
            self.lbl_info.configure(text="✅ Seluruh balok berhasil ditata.", fg=COLOR_BTN_1)
            messagebox.showinfo("Misi Sukses", "Proses Auto-Sort berhasil! Lengan robot telah selesai mengurutkan balok.")
        else:
            self.lbl_info.configure(text="❌ Proses gagal. Silakan periksa log terminal.", fg=COLOR_DANGER)
# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app = DobotIntegratedApp()
    app.mainloop()