import sys
import json
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import datetime

from database.crud import init_db, get_session
from database.models import Operador, Llamada

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Grabación de Taxis - Dashboard Analítico")
        self.geometry("1400x900")
        
        self.operador_activo = None
        init_db()
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self.show_login_screen()

    def show_login_screen(self):
        if hasattr(self, 'dashboard'):
            self.dashboard.destroy()
            
        self.login_frame = ctk.CTkFrame(self)
        self.login_frame.grid(row=0, column=0, sticky="nsew")
        
        self.login_frame.grid_rowconfigure(0, weight=1)
        self.login_frame.grid_rowconfigure(4, weight=1)
        self.login_frame.grid_columnconfigure(0, weight=1)
        self.login_frame.grid_columnconfigure(2, weight=1)
        
        ctk.CTkLabel(self.login_frame, text="Control de Turnos", font=ctk.CTkFont(size=30, weight="bold")).grid(row=1, column=1, pady=(0, 20))
        
        db = get_session()
        operadores = [o.nombre for o in db.query(Operador).all()]
        db.close()
        
        if not operadores:
            operadores = ["Sin operadores"]
            
        self.operador_var = ctk.StringVar(value=operadores[0])
        self.op_dropdown = ctk.CTkOptionMenu(self.login_frame, variable=self.operador_var, values=operadores, width=250, height=40)
        self.op_dropdown.grid(row=2, column=1, pady=10)
        
        self.btn_login = ctk.CTkButton(self.login_frame, text="Iniciar Turno", command=self.do_login, width=250, height=40)
        self.btn_login.grid(row=3, column=1, pady=20)
        
    def do_login(self):
        op_nombre = self.operador_var.get()
        db = get_session()
        op = db.query(Operador).filter(Operador.nombre == op_nombre).first()
        db.close()
        
        if op:
            self.operador_activo = op
            self.login_frame.destroy()
            self.show_main_dashboard()
        else:
            messagebox.showerror("Error", "Operador no encontrado.")

    def show_main_dashboard(self):
        self.dashboard = DashboardFrame(self, self.operador_activo, self.show_login_screen)
        self.dashboard.grid(row=0, column=0, sticky="nsew")

class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master, operador_activo, logout_callback):
        super().__init__(master)
        self.operador_activo = operador_activo
        self.logout_callback = logout_callback
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=3) # Panel KPI y Gráfica
        self.grid_columnconfigure(1, weight=7) # Panel Central (Historial/Detalles)
        
        self.create_header()
        self.create_charts_panel()
        self.create_history_and_details_panel()
        
        self.state_file = Path(__file__).parent.parent / "data" / "system_state.json"
        self.poll_system_state()
        
    def create_header(self):
        header = ctk.CTkFrame(self, height=60, corner_radius=0)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        
        ctk.CTkLabel(header, text=f"📊 Analytics Dashboard | 👤 {self.operador_activo.nombre}", 
                     font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20, pady=15)
                     
        ctk.CTkButton(header, text="Cerrar Sesión / Cambiar Turno", fg_color="#d62728", hover_color="#a11d1e", 
                      command=self.logout_callback).pack(side="right", padx=20, pady=15)
                      
        self.indicators_frame = ctk.CTkFrame(header, fg_color="transparent")
        self.indicators_frame.pack(side="right", padx=20, pady=15)
        
    def poll_system_state(self):
        try:
            if self.state_file.exists():
                with open(self.state_file, "r") as f:
                    state = json.load(f)
            else:
                state = {}
        except Exception:
            state = {}
            
        for widget in self.indicators_frame.winfo_children():
            widget.destroy()
            
        if not state:
            ctk.CTkLabel(self.indicators_frame, text="⚫ Sistema Apagado", text_color="gray", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        else:
            for line_name, status in state.items():
                if "Grabando" in status:
                    color = "#ff4a4a" # Rojo intermitente
                elif "Guardando" in status or "Procesando" in status:
                    color = "#ffcc00" # Amarillo
                else:
                    color = "gray"
                lbl_text = f"{line_name}: {status}"
                ctk.CTkLabel(self.indicators_frame, text=lbl_text, text_color=color, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
                
        self.after(1000, self.poll_system_state)

    def create_charts_panel(self):
        panel = ctk.CTkFrame(self)
        panel.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        # Tarjetas KPI
        kpi_frame = ctk.CTkFrame(panel, fg_color="transparent")
        kpi_frame.pack(fill="x", pady=20)
        
        self.kpi_total = ctk.CTkLabel(kpi_frame, text="Llamadas Hoy\n0", font=ctk.CTkFont(size=18, weight="bold"))
        self.kpi_total.pack(side="left", expand=True)
        
        self.kpi_avg = ctk.CTkLabel(kpi_frame, text="Duración Media\n0s", font=ctk.CTkFont(size=18, weight="bold"))
        self.kpi_avg.pack(side="left", expand=True)
        
        # Gráfica pequeña
        self.fig = Figure(figsize=(3, 3), dpi=100)
        self.fig.patch.set_facecolor('#2b2b2b')
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#2b2b2b')
        self.ax.tick_params(colors='white')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=panel)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkButton(panel, text="Refrescar Estadísticas", command=self.update_chart).pack(fill="x", padx=20, pady=10)
        self.update_chart()
        
    def update_chart(self):
        db = get_session()
        hoy = datetime.date.today()
        llamadas_hoy = db.query(Llamada).filter(Llamada.fecha_hora_inicio >= hoy).all()
        
        total = len(llamadas_hoy)
        if total > 0:
            avg = sum(l.duracion_segundos for l in llamadas_hoy if l.duracion_segundos) // total
        else:
            avg = 0
            
        self.kpi_total.configure(text=f"Llamadas Hoy\n{total}")
        self.kpi_avg.configure(text=f"Promedio\n{avg}s")
        
        self.ax.clear()
        fijas = len([l for l in llamadas_hoy if "Fija" in l.linea])
        celulares = len([l for l in llamadas_hoy if "Celular" in l.linea])
        self.ax.bar(['Fijas', 'Celulares'], [fijas, celulares], color=['#1f77b4', '#ff7f0e'])
        self.ax.set_title("Distribución (Hoy)", color="white")
        self.canvas.draw()
        db.close()

    def create_history_and_details_panel(self):
        panel = ctk.CTkFrame(self)
        panel.grid(row=1, column=1, sticky="nsew", padx=(0,10), pady=10)
        
        panel.grid_rowconfigure(1, weight=1) # Historial
        panel.grid_rowconfigure(2, weight=1) # Detalles integrados
        panel.grid_columnconfigure(0, weight=1)
        
        # Filtros
        search_frame = ctk.CTkFrame(panel, fg_color="transparent")
        search_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        ctk.CTkLabel(search_frame, text="Fecha (YYYY-MM-DD):").pack(side="left", padx=5)
        self.date_entry = ctk.CTkEntry(search_frame, width=110)
        self.date_entry.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        self.date_entry.pack(side="left", padx=5)
        
        ctk.CTkLabel(search_frame, text="Línea:").pack(side="left", padx=5)
        self.linea_var = ctk.StringVar(value="Todas")
        ctk.CTkOptionMenu(search_frame, variable=self.linea_var, values=["Todas", "Fija 1", "Fija 2", "Celulares"], width=120).pack(side="left", padx=5)
        
        ctk.CTkButton(search_frame, text="Filtrar", command=self.load_history, width=100).pack(side="left", padx=15)
        
        # Historial Superior
        self.scrollable_list = ctk.CTkScrollableFrame(panel, label_text="Historial de Llamadas Filtradas")
        self.scrollable_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        # Detalles Inferior Integrado
        self.details_panel = ctk.CTkFrame(panel, border_width=2, border_color="#3a3a3a")
        self.details_panel.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        
        self.details_panel.grid_rowconfigure(1, weight=1)
        self.details_panel.grid_columnconfigure(0, weight=1)
        
        header_frame = ctk.CTkFrame(self.details_panel, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=5)
        
        self.details_header = ctk.CTkLabel(header_frame, text="Selecciona un registro arriba para cargar la transcripción y el audio.", font=ctk.CTkFont(weight="bold"))
        self.details_header.pack(side="left", padx=10)
        
        self.btn_play = ctk.CTkButton(header_frame, text="▶ Reproducir Audio", fg_color="#2ca02c", hover_color="#217a21", state="disabled", command=self.play_audio)
        self.btn_play.pack(side="right", padx=5)
        
        self.btn_stop = ctk.CTkButton(header_frame, text="⏹ Detener", fg_color="#d62728", hover_color="#a11d1e", state="disabled", command=self.stop_audio)
        self.btn_stop.pack(side="right", padx=5)
        
        self.textbox = ctk.CTkTextbox(self.details_panel, font=ctk.CTkFont(size=14))
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.textbox.configure(state="disabled")
        
        self.selected_llamada = None
        self.load_history()
        
    def load_history(self):
        for widget in self.scrollable_list.winfo_children():
            widget.destroy()
            
        db = get_session()
        query = db.query(Llamada).order_by(Llamada.id.desc())
        
        fecha = self.date_entry.get().strip()
        if fecha:
            query = query.filter(Llamada.fecha_hora_inicio >= fecha)
            
        linea = self.linea_var.get()
        if linea != "Todas":
            query = query.filter(Llamada.linea.contains(linea))
            
        llamadas = query.limit(50).all()
        
        if not llamadas:
            ctk.CTkLabel(self.scrollable_list, text="No hay resultados.").pack(pady=20)
            db.close()
            return
            
        for llamada in llamadas:
            item_frame = ctk.CTkFrame(self.scrollable_list)
            item_frame.pack(fill="x", pady=2, padx=5)
            
            dt_str = llamada.fecha_hora_inicio.strftime("%H:%M") if llamada.fecha_hora_inicio else "??:??"
            op_name = llamada.operador.nombre if llamada.operador else "Desconocido"
            info = f"🕒 {dt_str} | 📞 {llamada.linea} | 👤 {op_name} | ⏱ {llamada.duracion_segundos}s"
            
            ctk.CTkLabel(item_frame, text=info).pack(side="left", padx=10, pady=5)
            ctk.CTkButton(item_frame, text="Cargar", width=80, command=lambda c=llamada: self.show_details(c)).pack(side="right", padx=10)
            
        db.close()

    def show_details(self, llamada):
        self.stop_audio()
        self.selected_llamada = llamada
        
        self.details_header.configure(text=f"Línea: {llamada.linea} | Fecha: {llamada.fecha_hora_inicio}")
        self.btn_play.configure(state="normal")
        self.btn_stop.configure(state="normal")
        
        db = get_session()
        llamada_db = db.merge(llamada)
        
        self.textbox.configure(state="normal")
        self.textbox.delete("0.0", "end")
        
        if not llamada_db.segmentos:
            self.textbox.insert("0.0", "Sin transcripción disponible o llamada en silencio.")
        else:
            texto_completo = ""
            for seg in sorted(llamada_db.segmentos, key=lambda x: x.tiempo_inicio):
                tiempo_i = f"{int(seg.tiempo_inicio//60):02d}:{int(seg.tiempo_inicio%60):02d}"
                tiempo_f = f"{int(seg.tiempo_fin//60):02d}:{int(seg.tiempo_fin%60):02d}"
                texto_completo += f"[{tiempo_i} - {tiempo_f}] {seg.hablante.upper()}:\n{seg.texto}\n\n"
            self.textbox.insert("0.0", texto_completo)
            
        self.textbox.configure(state="disabled")
        db.close()

    def play_audio(self):
        import winsound
        from pathlib import Path
        if self.selected_llamada and self.selected_llamada.ruta_audio and Path(self.selected_llamada.ruta_audio).exists():
            try:
                winsound.PlaySound(self.selected_llamada.ruta_audio, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                messagebox.showerror("Error", f"Error de audio: {e}")
        else:
            messagebox.showwarning("Atención", "Audio no encontrado.")
            
    def stop_audio(self):
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)

if __name__ == "__main__":
    app = App()
    app.mainloop()
