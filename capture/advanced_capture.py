import threading
import time
import collections
import sounddevice as sd
import numpy as np
import wave
import json
import torch
from datetime import datetime
from pathlib import Path

# Estados de la Máquina de Estados
STATE_IDLE = "En espera"
STATE_RECORDING = "🔴 Grabando..."
STATE_COOLDOWN = "⏳ Cooldown..."

class AdvancedCaptureSystem:
    def __init__(self, on_call_finished_callback):
        self.on_call_finished = on_call_finished_callback
        self._running = False
        self._threads = []
        
        # Archivos y Rutas
        self.base_dir = Path(__file__).parent.parent / "data"
        self.audio_dir = self.base_dir / "audios"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.base_dir / "system_state.json"
        
        # Iniciar archivo de estado y locks
        self.vad_lock = threading.Lock()
        self.state_lock = threading.Lock()
        
        self._write_state({})
        self.current_state = {}
        
        # Parámetros de Audio
        self.sample_rate = 16000
        
        # Cargar Silero VAD
        print("[VAD] Cargando modelo Silero VAD desde PyTorch Hub...")
        self.model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                           model='silero_vad',
                                           force_reload=False,
                                           trust_repo=True)
        print("[VAD] Modelo Silero VAD cargado exitosamente.")
        
    def _write_state(self, state_dict):
        with self.state_lock:
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
        print("[Captura] Iniciando Arquitectura de Captura Concurrente Avanzada...")
        
        # Instanciar hilos independientes
        t_mic = threading.Thread(target=self._capture_thread, args=("Celulares", 5.0)) # 5 seg cooldown
        t_mic.daemon = True
        t_mic.start()
        self._threads.append(t_mic)
        
        t_usb = threading.Thread(target=self._capture_thread, args=("Fija 1", 3.0)) # 3 seg cooldown
        t_usb.daemon = True
        t_usb.start()
        self._threads.append(t_usb)

    def stop(self):
        self._running = False
        for t in self._threads:
            t.join(timeout=2)
        print("[Captura] Sistema detenido.")

    def _is_speech_silero(self, audio_chunk):
        """
        Evalúa un chunk de audio usando Silero VAD (Ruta Pesada / Celulares).
        """
        audio_float = audio_chunk.astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_float)
        
        try:
            with self.vad_lock:
                confidence = self.model(audio_tensor, self.sample_rate).item()
            return confidence > 0.5 
        except Exception:
            return False

    def _is_speech_rms(self, audio_chunk):
        """
        Evalúa un chunk de audio matemáticamente (Ruta Rápida / Líneas Fijas).
        Es 10,000x más rápido que Silero y no satura CPU.
        """
        rms = np.sqrt(np.mean(np.square(audio_chunk.astype(np.float32))))
        # Umbral dinámico para línea pura (cable USB suele ser silencioso)
        return rms > 300 

    def _capture_thread(self, line_name, cooldown_seconds):
        self._update_status(line_name, STATE_IDLE)
        
        # Tamaño de ventana: 512 samples a 16kHz (32 ms) - Requerido por Silero VAD
        frame_size = 512
        
        # Ring Buffer: Almacenar hasta 3 segundos de audio pre-roll
        MAX_PREROLL_FRAMES = int((self.sample_rate * 3.0) / frame_size)
        ring_buffer = collections.deque(maxlen=MAX_PREROLL_FRAMES)
        
        # Variables de la máquina de estados
        state = STATE_IDLE
        frames_grabados = []
        cooldown_frames = 0
        MAX_COOLDOWN_FRAMES = int((self.sample_rate * cooldown_seconds) / frame_size)
        
        start_time = None
        
        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16') as stream:
                print(f"[{line_name}] Thread listo y escuchando (Cooldown: {cooldown_seconds}s, Buffer: 3s)")
                while self._running:
                    data, overflowed = stream.read(frame_size)
                    audio_chunk = data.flatten()
                    
                    # RUTA ASIMÉTRICA: Decidir modelo según línea
                    if "Celular" in line_name or "Micrófono" in line_name:
                        is_speech = self._is_speech_silero(audio_chunk)
                        engine_name = "Silero VAD"
                    else:
                        is_speech = self._is_speech_rms(audio_chunk)
                        engine_name = "RMS Energy"
                    
                    # Máquina de Estados
                    if state == STATE_IDLE:
                        ring_buffer.append(audio_chunk.tobytes())
                        if is_speech:
                            state = STATE_RECORDING
                            start_time = datetime.now()
                            # Volcar el ring buffer en la grabación final para no perder la primera palabra
                            frames_grabados.extend(list(ring_buffer))
                            ring_buffer.clear()
                            self._update_status(line_name, STATE_RECORDING)
                            print(f"[{line_name}] IDLE -> RECORDING (Voz detectada con {engine_name})")
                            
                    elif state == STATE_RECORDING:
                        frames_grabados.append(audio_chunk.tobytes())
                        if not is_speech:
                            state = STATE_COOLDOWN
                            cooldown_frames = 0
                            
                    elif state == STATE_COOLDOWN:
                        frames_grabados.append(audio_chunk.tobytes())
                        if is_speech:
                            # Volvió a hablar, cancelamos el cooldown y volvemos a RECORDING
                            state = STATE_RECORDING
                        else:
                            cooldown_frames += 1
                            if cooldown_frames > MAX_COOLDOWN_FRAMES:
                                # Se terminó el cooldown, guardar y volver a IDLE
                                duration = (datetime.now() - start_time).total_seconds()
                                
                                # Si duró muy poco, descartar
                                if duration > 1.5:
                                    self._update_status(line_name, "🟡 Guardando...")
                                    self._save_and_emit(line_name, frames_grabados, start_time, int(duration))
                                else:
                                    print(f"[{line_name}] Falsa alarma (muy corto). Descartado.")
                                
                                state = STATE_IDLE
                                frames_grabados = []
                                start_time = None
                                self._update_status(line_name, STATE_IDLE)
                                
        except Exception as e:
            import traceback
            print(f"[{line_name}] Error crítico en hilo de captura: {e}")
            traceback.print_exc()
            self._update_status(line_name, "Desconectada")

    def _save_and_emit(self, line_name, frames, start_time, duration):
        filename = f"llamada_{line_name.replace(' ', '_')}_{start_time.strftime('%Y%m%d_%H%M%S')}.wav"
        filepath = self.audio_dir / filename
        
        with wave.open(str(filepath), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16 bits
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(frames))
            
        print(f"[{line_name}] Grabación de {duration}s finalizada: {filename}")
        self.on_call_finished(line_name, str(filepath), start_time, duration)

if __name__ == "__main__":
    def dummy_callback(line, path, start, dur):
        print(f">> ARCHIVO LISTO: {path} ({dur}s)")
        
    cap = AdvancedCaptureSystem(dummy_callback)
    cap.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cap.stop()
