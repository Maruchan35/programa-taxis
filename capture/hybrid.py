import threading
import time
import queue
import sounddevice as sd
import numpy as np
import wave
import json
from datetime import datetime
from pathlib import Path

class HybridCaptureSystem:
    def __init__(self, on_call_finished_callback):
        self.on_call_finished = on_call_finished_callback
        self._running = False
        self._threads = []
        
        # Rutas de almacenamiento
        self.base_dir = Path(__file__).parent.parent / "data"
        self.audio_dir = self.base_dir / "audios"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.base_dir / "system_state.json"
        
        # Iniciar archivo de estado
        self._write_state({})
        self.current_state = {}
        
        # Configuración VAD de energía pura (sin dependencias C++)
        self.energy_threshold = 500 # Umbral de volumen (ajustar según el micrófono)
        self.sample_rate = 16000 
        
    def _write_state(self, state_dict):
        try:
            with open(self.state_file, "w") as f:
                json.dump(state_dict, f)
        except Exception:
            pass

    def _update_status(self, line_name, status):
        self.current_state[line_name] = status
        self._write_state(self.current_state)
        
    def start(self):
        self._running = True
        print("[Captura] Iniciando sistema híbrido de captura de hardware...")
        
        # Iniciar hilos de escucha para las distintas líneas.
        # Por ahora usamos el dispositivo de grabación por defecto para emular ambas cosas.
        
        t_mic = threading.Thread(target=self._listen_ambient_mic, args=("Micrófono Ambiental (Celulares)",))
        t_mic.daemon = True
        t_mic.start()
        self._threads.append(t_mic)
        
        t_usb = threading.Thread(target=self._listen_usb_line, args=("Fija 1 (Tarjeta USB)",))
        t_usb.daemon = True
        t_usb.start()
        self._threads.append(t_usb)

    def stop(self):
        self._running = False
        for t in self._threads:
            t.join(timeout=2)
        print("[Captura] Sistema de hardware detenido.")
        
    def _listen_ambient_mic(self, line_name):
        self._record_with_vad(line_name)
        
    def _listen_usb_line(self, line_name):
        self._record_with_vad(line_name)

    def _record_with_vad(self, line_name):
        """
        Escucha un stream de audio. Usa VAD para detectar cuando alguien habla.
        Si hay voz, graba. Si hay X segundos de silencio, corta y empaqueta la llamada.
        """
        # Configuración de frames para webrtcvad (10, 20 o 30 ms)
        frame_duration = 30 # ms
        frame_size = int(self.sample_rate * frame_duration / 1000) # samples
        
        recording = False
        frames_grabados = []
        silence_counter = 0
        MAX_SILENCE_FRAMES = 100 # 3 segundos de silencio corrido = fin de llamada
        
        start_time = None
        self._update_status(line_name, "En espera")
        
        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16') as stream:
                print(f"[Captura] Escuchando activamente en dispositivo: '{line_name}'...")
                while self._running:
                    data, overflowed = stream.read(frame_size)
                    audio_frame = data.tobytes()
                    
                    rms = np.sqrt(np.mean(np.square(data.astype(np.float32))))
                    is_speech = rms > self.energy_threshold
                        
                    if is_speech:
                        if not recording:
                            recording = True
                            start_time = datetime.now()
                            print(f"[{line_name}] ¡Voz detectada! Iniciando grabación de servicio...")
                            self._update_status(line_name, "🔴 Grabando...")
                        frames_grabados.append(audio_frame)
                        silence_counter = 0
                    else:
                        if recording:
                            frames_grabados.append(audio_frame)
                            silence_counter += 1
                            
                            if silence_counter > MAX_SILENCE_FRAMES:
                                duration = (datetime.now() - start_time).total_seconds()
                                if duration > 2:
                                    self._save_and_emit(line_name, frames_grabados, start_time, int(duration))
                                else:
                                    print(f"[{line_name}] Falsa alarma (muy corto). Audio descartado.")
                                    
                                recording = False
                                frames_grabados = []
                                silence_counter = 0
                                self._update_status(line_name, "En espera")
        except Exception as e:
            print(f"[{line_name}] Error crítico accediendo al hardware de audio: {e}")
            self._update_status(line_name, "Desconectada")

    def _save_and_emit(self, line_name, frames, start_time, duration):
        filename = f"servicio_{line_name.replace(' ', '_').replace('(', '').replace(')', '')}_{start_time.strftime('%Y%m%d_%H%M%S')}.wav"
        filepath = self.audio_dir / filename
        
        with wave.open(str(filepath), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16 bits
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(frames))
            
        print(f"[{line_name}] Audio cerrado. {duration}s grabados en: {filename}")
        self.on_call_finished(line_name, str(filepath), start_time, duration)
