import threading
import queue
import time
from database.crud import get_session
from database.models import Llamada, TranscripcionSegmento
from datetime import timedelta

class ProcessingPipeline:
    def __init__(self):
        self.call_queue = queue.Queue()
        self._running = False
        self._thread = None
        
        self.model = None
        self._init_models()

    def _init_models(self):
        print("[Procesador IA] Inicializando motor Whisper...")
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel("base", device="cpu", compute_type="int8")
            print("[Procesador IA] Whisper 'base' cargado en memoria listo para transcribir.")
        except Exception as e:
            print(f"[Procesador IA] Aviso: faster-whisper no cargó. El software guardará el audio sin texto ({e}).")

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop)
        self._thread.daemon = True
        self._thread.start()
        
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()

    def enqueue_call(self, operador_id, line_id, filepath, start_time, duration_sec):
        self.call_queue.put({
            "operador_id": operador_id,
            "line_id": line_id,
            "filepath": filepath,
            "start_time": start_time,
            "duration": duration_sec
        })

    def _worker_loop(self):
        while self._running:
            try:
                data = self.call_queue.get(timeout=1)
                self._process_call(data)
                self.call_queue.task_done()
            except queue.Empty:
                continue

    def _process_call(self, data):
        print(f"\n[Procesador IA] Reduciendo ruido y extrayendo texto de la llamada en {data['line_id']}...")
        end_time = data['start_time'] + timedelta(seconds=data['duration'])
        
        filepath = data['filepath']
        
        # Aplicar reducción de ruido (NoiseReduce)
        try:
            import noisereduce as nr
            import scipy.io.wavfile as wav
            
            rate, wave_data = wav.read(filepath)
            # Reducimos ruido espectral
            reduced_noise = nr.reduce_noise(y=wave_data, sr=rate)
            # Guardamos sobre el mismo archivo
            wav.write(filepath, rate, reduced_noise)
            print(f"[Procesador IA] Filtro de reducción de ruido aplicado a {filepath}.")
        except Exception as e:
            print(f"[Procesador IA] No se pudo aplicar reducción de ruido: {e}")
        
        segments_data = []
        if self.model:
            try:
                # Extrae el texto del audio en español
                segments, info = self.model.transcribe(filepath, language="es")
                for i, segment in enumerate(segments):
                    # Como aún no implementamos la diarización de pyannote, intercalamos Operador/Cliente
                    hablante = "Operador" if i % 2 == 0 else "Cliente"
                    segments_data.append({
                        "hablante": hablante,
                        "texto": segment.text.strip(),
                        "inicio": segment.start,
                        "fin": segment.end
                    })
            except Exception as e:
                print(f"[Procesador IA] Error transcribiendo con IA: {e}")
                
        # Insertar información en SQLite
        db = get_session()
        try:
            nueva_llamada = Llamada(
                operador_id=data['operador_id'],
                linea=data['line_id'],
                fecha_hora_inicio=data['start_time'],
                fecha_hora_fin=end_time,
                duracion_segundos=data['duration'],
                ruta_audio=data['filepath']
            )
            db.add(nueva_llamada)
            db.commit()
            db.refresh(nueva_llamada)
            
            for seg in segments_data:
                db.add(TranscripcionSegmento(
                    llamada_id=nueva_llamada.id,
                    hablante=seg["hablante"],
                    texto=seg["texto"],
                    tiempo_inicio=seg["inicio"],
                    tiempo_fin=seg["fin"]
                ))
            db.commit()
            print(f"[Procesador IA] Guardado exitoso de audio y texto (ID de base de datos: {nueva_llamada.id}).")
        except Exception as e:
            print(f"Error base de datos: {e}")
            db.rollback()
        finally:
            db.close()
