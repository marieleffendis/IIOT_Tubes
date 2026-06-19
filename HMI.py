import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os
import threading

# ==========================================
# KONFIGURASI TAMPILAN (Style)
# ==========================================
FONT_HEADER = ("Helvetica", 16, "bold")
FONT_SUBHEADER = ("Helvetica", 14, "bold")
FONT_BODY = ("Helvetica", 12)
FONT_BTN = ("Helvetica", 11, "bold")
COLOR_BG = "#2c3e50"      # Background Gelap
COLOR_FG = "white"        # Text Putih
COLOR_ACCENT = "#34495e"  # Background Panel
COLOR_BTN_1 = "#1abc9c"   # Tombol Mode 1 (Turquoise)
COLOR_BTN_2 = "#e67e22"   # Tombol Mode 2 (Orange)
COLOR_DANGER = "#e74c3c"  # Tombol Stop/Logout

class DobotIntegratedApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Dobot Magician Integrated System")
        self.geometry("900x600")
        self.resizable(False, False)
        self.attributes('-fullscreen', False)
        
        # Variabel Proses Global (agar bisa di-kill via Emergency Stop)
        self.current_process = None 
        
        # Binding Tombol Darurat Global
        self.bind("<Escape>", lambda event: self.confirm_exit())
        self.bind("p", self.emergency_stop)
        self.bind("P", self.emergency_stop)

        # Container Utama
        self.container = tk.Frame(self)
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # Status Bar
        self.status_var = tk.StringVar(value="Status: Siap (Pilih Mode)")
        self.status_bar = tk.Label(self, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W, bg="#dcdcdc")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.frames = {}

        # Mendaftarkan Semua Halaman
        for F in (LoginPage, ModeSelectionPage, DirectControlPage, SmartSortPage):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginPage")

    def show_frame(self, page_name):
        """Menampilkan halaman tertentu"""
        frame = self.frames[page_name]
        frame.tkraise()

    def confirm_exit(self):
        if messagebox.askokcancel("Keluar", "Tutup aplikasi?"):
            self.destroy()
            sys.exit()

    def emergency_stop(self, event=None):
        """Emergency Stop Global"""
        print("\n[EMERGENCY] Tombol P ditekan!")
        if self.current_process and self.current_process.poll() is None:
            print(f"Mematikan proses PID: {self.current_process.pid}")
            self.current_process.kill()
        
        self.status_var.set("STATUS: EMERGENCY STOP TRIGGERED!")
        messagebox.showwarning("EMERGENCY", "Sistem dihentikan paksa!")

    def get_script_path(self, script_name):
        """Helper path pencarian script"""
        base_path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_path, script_name)
        
        # Cek folder unit_test jika tidak ada di root
        if not os.path.exists(path):
             path = os.path.join(base_path, "unit_test", script_name)
        
        return path

    def run_script_blocking(self, script_name, args=[]):
        """Fungsi eksekusi script yang digunakan oleh kedua mode"""
        script_path = self.get_script_path(script_name)

        if not os.path.exists(script_path):
            self.status_var.set(f"Error: {script_name} tidak ditemukan")
            messagebox.showerror("File Missing", f"File {script_name} tidak ditemukan!")
            return

        try:
            self.status_var.set(f"Menjalankan: {script_name} {args if args else ''}...")
            command = [sys.executable, script_path] + args
            print(f"Running: {command}")

            self.current_process = subprocess.Popen(command)
            self.current_process.wait() # Menunggu hingga selesai

            if self.current_process.returncode == 0:
                self.status_var.set("✅ Proses Selesai.")
                return True
            else:
                self.status_var.set(f"❌ Error (Code {self.current_process.returncode})")
                return False

        except Exception as e:
            print(f"Error execution: {e}")
            self.status_var.set(f"System Error: {str(e)}")
            return False
        finally:
            self.current_process = None


# ==========================================
# PAGE 1: LOGIN PAGE
# ==========================================
class LoginPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg=COLOR_BG)

        tk.Label(self, text="SISTEM INTEGRASI DOBOT", font=FONT_HEADER, fg=COLOR_FG, bg=COLOR_BG).pack(pady=50)
        tk.Label(self, text="(Tekan 'P' untuk Emergency Stop)", font=("Helvetica", 10), fg=COLOR_DANGER, bg=COLOR_BG).pack()

        frame_input = tk.Frame(self, bg=COLOR_BG)
        frame_input.pack(pady=20)

        # Username
        tk.Label(frame_input, text="Username:", font=FONT_BODY, fg=COLOR_FG, bg=COLOR_BG).grid(row=0, column=0, padx=10, pady=5)
        self.entry_user = tk.Entry(frame_input, font=FONT_BODY)
        self.entry_user.grid(row=0, column=1, padx=10, pady=5)
        self.entry_user.insert(0, "admin") # Default

        # Password
        tk.Label(frame_input, text="Password:", font=FONT_BODY, fg=COLOR_FG, bg=COLOR_BG).grid(row=1, column=0, padx=10, pady=5)
        self.entry_pass = tk.Entry(frame_input, font=FONT_BODY, show="*")
        self.entry_pass.grid(row=1, column=1, padx=10, pady=5)
        self.entry_pass.insert(0, "1234") # Default

        tk.Button(self, text="LOGIN", font=FONT_BTN, bg="#27ae60", fg="white", width=15, 
                  command=self.check_login).pack(pady=30)

    def check_login(self):
        if self.entry_user.get() == "admin" and self.entry_pass.get() == "1234":
            self.entry_user.delete(0, 'end')
            self.entry_pass.delete(0, 'end')
            # MASUK KE HALAMAN PEMILIHAN MODE
            self.controller.show_frame("ModeSelectionPage")
        else:
            messagebox.showerror("Error", "Login Gagal!")


# ==========================================
# PAGE 2: MODE SELECTION (PILIH MODE)
# ==========================================
class ModeSelectionPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg="#ecf0f1")

        tk.Label(self, text="PILIH MODE OPERASI", font=FONT_HEADER, bg="#ecf0f1", fg="#2c3e50").pack(pady=40)

        btn_container = tk.Frame(self, bg="#ecf0f1")
        btn_container.pack(expand=True)

        # Tombol Mode 1: Direct Control (Posisi A/B/C/D Manual)
        btn_mode1 = tk.Button(btn_container, text="MODE 1\nDirect Control\n(Trigger Tombol)", 
                              font=FONT_BTN, bg=COLOR_BTN_1, fg="white", width=20, height=5,
                              command=lambda: controller.show_frame("DirectControlPage"))
        btn_mode1.grid(row=0, column=0, padx=30, pady=20)

        # Tombol Mode 2: Smart Sorting (Configurable)
        btn_mode2 = tk.Button(btn_container, text="MODE 2\nSmart Sorting\n(Konfigurasi Warna)", 
                              font=FONT_BTN, bg=COLOR_BTN_2, fg="white", width=20, height=5,
                              command=lambda: controller.show_frame("SmartSortPage"))
        btn_mode2.grid(row=0, column=1, padx=30, pady=20)

        # Tombol Logout
        tk.Button(self, text="Logout", font=FONT_BODY, bg="#95a5a6", fg="white",
                  command=lambda: controller.show_frame("LoginPage")).pack(pady=30)


# ==========================================
# PAGE 3: DIRECT CONTROL (Dari gui_main.py)
# ==========================================
class DirectControlPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg=COLOR_ACCENT)

        tk.Label(self, text="MODE 1: DIRECT POSITION", font=FONT_HEADER, fg="white", bg=COLOR_ACCENT).pack(pady=20)
        tk.Label(self, text="Klik tombol untuk menjalankan script posisi tertentu", fg="#bdc3c7", bg=COLOR_ACCENT).pack()

        grid_frame = tk.Frame(self, bg=COLOR_ACCENT)
        grid_frame.pack(expand=True)

        self.btn_params = {'font': FONT_BODY, 'bg': COLOR_BTN_1, 'fg': "white", 'width': 15, 'height': 2}
        self.buttons = []

        # Membuat tombol trigger script
        self.create_btn(grid_frame, "POSISI A", "posA.py", 0, 0)
        self.create_btn(grid_frame, "POSISI B", "posB.py", 0, 1)
        self.create_btn(grid_frame, "POSISI C", "posC.py", 1, 0)
        self.create_btn(grid_frame, "POSISI D", "posD.py", 1, 1)

        self.btn_back = tk.Button(self, text="Kembali ke Menu", font=FONT_BODY, bg="#95a5a6", fg="white",
                                  command=lambda: controller.show_frame("ModeSelectionPage"))
        self.btn_back.pack(pady=20)
        self.buttons.append(self.btn_back)

    def create_btn(self, parent, text, script_name, r, c):
        btn = tk.Button(parent, text=text, **self.btn_params,
                        command=lambda: self.start_thread(script_name))
        btn.grid(row=r, column=c, padx=15, pady=15)
        self.buttons.append(btn)

    def start_thread(self, script_name):
        # Disable tombol
        for btn in self.buttons:
            btn.configure(state=tk.DISABLED, bg="#7f8c8d")
        
        # Jalankan
        threading.Thread(target=self._execute, args=(script_name,)).start()

    def _execute(self, script_name):
        self.controller.run_script_blocking(script_name)
        # Enable kembali tombol setelah selesai
        self.after(0, self.enable_buttons)

    def enable_buttons(self):
        for btn in self.buttons:
            if btn == self.btn_back:
                btn.configure(state=tk.NORMAL, bg="#95a5a6")
            else:
                btn.configure(state=tk.NORMAL, bg=COLOR_BTN_1)


# ==========================================
# PAGE 4: SMART SORT (Dari app.py)
# ==========================================
class SmartSortPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.configure(bg=COLOR_ACCENT)

        tk.Label(self, text="MODE 2: SMART SORTING", font=FONT_HEADER, fg="white", bg=COLOR_ACCENT).pack(pady=10)
        tk.Label(self, text="Atur warna target untuk setiap posisi, lalu klik Start", fg="#bdc3c7", bg=COLOR_ACCENT).pack(pady=(0, 20))

        grid_frame = tk.Frame(self, bg=COLOR_ACCENT)
        grid_frame.pack(pady=10)

        self.color_options = ["Merah", "Hijau", "Biru", "Kuning"]
        self.selections = {}

        # Dropdown konfigurasi
        self.create_dropdown(grid_frame, "Posisi A:", "A", 0)
        self.create_dropdown(grid_frame, "Posisi B:", "B", 1)
        self.create_dropdown(grid_frame, "Posisi C:", "C", 2)
        self.create_dropdown(grid_frame, "Posisi D:", "D", 3)

        btn_frame = tk.Frame(self, bg=COLOR_ACCENT)
        btn_frame.pack(pady=20)

        self.btn_start = tk.Button(btn_frame, text="MULAI MISI", font=FONT_BTN, 
                                   bg=COLOR_BTN_2, fg="white", width=20, height=2,
                                   command=self.start_process)
        self.btn_start.pack(side=tk.TOP, pady=5)

        self.btn_back = tk.Button(btn_frame, text="Kembali ke Menu", font=FONT_BODY, bg="#95a5a6", fg="white",
                  command=lambda: controller.show_frame("ModeSelectionPage"))
        self.btn_back.pack(side=tk.TOP, pady=10)

    def create_dropdown(self, parent, label_text, key, row_idx):
        tk.Label(parent, text=label_text, font=("Helvetica", 12, "bold"), fg="white", bg=COLOR_ACCENT).grid(row=row_idx, column=0, padx=20, pady=10, sticky="e")
        var = tk.StringVar()
        combo = ttk.Combobox(parent, textvariable=var, values=self.color_options, state="readonly", font=("Helvetica", 11))
        combo.grid(row=row_idx, column=1, padx=20, pady=10, sticky="w")
        combo.current(row_idx) 
        self.selections[key] = var

    def start_process(self):
        colors = {
            "A": self.selections["A"].get(),
            "B": self.selections["B"].get(),
            "C": self.selections["C"].get(),
            "D": self.selections["D"].get()
        }

        if not messagebox.askyesno("Konfirmasi", "Mulai proses Smart Sorting dengan konfigurasi ini?"):
            return

        # UI Locking
        self.btn_start.configure(state=tk.DISABLED, bg="#7f8c8d")
        self.btn_back.configure(state=tk.DISABLED)
        
        # Jalankan Thread
        threading.Thread(target=self._run_thread, args=(colors,)).start()

    def _run_thread(self, colors):
        # Jalankan main_auto.py dengan argumen
        args = [colors['A'], colors['B'], colors['C'], colors['D']]
        success = self.controller.run_script_blocking("main_auto.py", args)
        
        # UI Unlock
        self.after(0, self.unlock_ui)
        if success:
            messagebox.showinfo("Info", "Misi Selesai!")

    def unlock_ui(self):
        self.btn_start.configure(state=tk.NORMAL, bg=COLOR_BTN_2)
        self.btn_back.configure(state=tk.NORMAL)


# ==========================================
# MAIN LOOP
# ==========================================
if __name__ == "__main__":
    app = DobotIntegratedApp()
    app.mainloop()