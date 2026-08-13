from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path
from .models import Base, Operador

db_path = Path(__file__).parent.parent / "data" / "taxis.sqlite"
db_path.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Crear operadores por defecto si no existen
    db = SessionLocal()
    if db.query(Operador).count() == 0:
        ops = [Operador(nombre="Operador 1 (Mañana)"), 
               Operador(nombre="Operador 2 (Tarde)"), 
               Operador(nombre="Operador 3 (Noche)")]
        db.add_all(ops)
        db.commit()
    db.close()
    print(f"Base de datos SQLite iniciada en {db_path}")

def get_session():
    return SessionLocal()
