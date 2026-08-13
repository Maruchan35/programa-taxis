import time
from capture.advanced_capture import AdvancedCaptureSystem
from processing.pipeline import ProcessingPipeline
from database.crud import init_db

def main():
    print("=== SERVIDOR DE GRABACIÓN Y ANÁLISIS DE TAXIS ===")
    print("Inicializando componentes...")
    
    init_db()
    
    ai_pipeline = ProcessingPipeline()
    ai_pipeline.start()
    
    # Callback que se ejecuta cuando el micrófono ambiental o el USB detectan que una llamada ha terminado
    def on_call_recorded(line_id, filepath, start_time, duration):
        print(f"> Llamada capturada en {line_id}. Transfiriendo a la IA...")
        
        # En una arquitectura completa, la UI le pasaría el ID del operador logueado. 
        # Aquí asignamos el ID 1 simulando que "Operador 1" es el que está en turno en el servidor.
        operador_actual_id = 1 
        ai_pipeline.enqueue_call(operador_actual_id, line_id, filepath, start_time, duration)

    # Iniciar Captura Avanzada (Micrófonos + USB)
    capture = AdvancedCaptureSystem(on_call_recorded)
    capture.start()
    
    print("==================================================")
    print("✓ Sistema Activo. Micrófonos y tarjetas USB en escucha...")
    print("Habla por el micrófono para probar el detector de voz (VAD).")
    print("Presiona Ctrl+C en esta consola para apagar el sistema.")
    print("==================================================")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nApagando micrófonos y cerrando sistema...")
        capture_sys.stop()
        ai_pipeline.stop()

if __name__ == "__main__":
    main()
