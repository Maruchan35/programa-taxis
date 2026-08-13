from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Operador(Base):
    __tablename__ = "operadores"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, index=True)
    
    llamadas = relationship("Llamada", back_populates="operador")

class Llamada(Base):
    __tablename__ = "llamadas"
    
    id = Column(Integer, primary_key=True, index=True)
    linea = Column(String, index=True) # ej: "Fija 1", "Celular Micrófono"
    operador_id = Column(Integer, ForeignKey("operadores.id"))
    fecha_hora_inicio = Column(DateTime, index=True)
    fecha_hora_fin = Column(DateTime)
    duracion_segundos = Column(Integer)
    ruta_audio = Column(String)
    estado = Column(String, default="completada")
    notas = Column(String, nullable=True)
    
    operador = relationship("Operador", back_populates="llamadas")
    segmentos = relationship("TranscripcionSegmento", back_populates="llamada", cascade="all, delete-orphan")

class TranscripcionSegmento(Base):
    __tablename__ = "transcripcion_segmentos"
    
    id = Column(Integer, primary_key=True, index=True)
    llamada_id = Column(Integer, ForeignKey("llamadas.id"))
    hablante = Column(String)
    texto = Column(String)
    tiempo_inicio = Column(Float)
    tiempo_fin = Column(Float)
    
    llamada = relationship("Llamada", back_populates="segmentos")
