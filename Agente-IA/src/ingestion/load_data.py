import os
import random
import uuid
from datetime import datetime, timedelta
import pandas as pd
from faker import Faker
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

fake = Faker('es_ES')

# Configuración Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Constantes
CIUDADES = ["Guayaquil", "Quito", "Cuenca", "Manta"]
RAMOS_PROBS = {"Vehiculos": 0.50, "Salud": 0.20, "Vida": 0.15, "Hogar": 0.15}
RAMOS = list(RAMOS_PROBS.keys())
PROBS = list(RAMOS_PROBS.values())

N_ASEGURADOS = 10
N_POLIZAS = 10
N_PROVEEDORES = 5
N_SINIESTROS = 10
N_DOCUMENTOS = 20

def generate_data():
    print("Generando datos sintéticos...")
    
    # 1. Asegurados
    asegurados = []
    for _ in range(N_ASEGURADOS):
        asegurados.append({
            "id_asegurado": str(uuid.uuid4()),
            "segmento": random.choice(["VIP", "Estandar", "Corporativo"]),
            "antiguedad_anios": random.randint(0, 15),
            "ciudad": random.choice(CIUDADES),
            "num_polizas": random.randint(1, 5),
            "reclamos_12m": random.randint(0, 3),
            "mora_actual": random.random() < 0.1,
            "score_cliente": round(random.uniform(50.0, 100.0), 2)
        })
        
    # 2. Pólizas
    polizas = []
    for _ in range(N_POLIZAS):
        asegurado = random.choice(asegurados)
        fecha_inicio = fake.date_between(start_date='-3y', end_date='today')
        fecha_fin = fecha_inicio + timedelta(days=365)
        suma_asegurada = round(random.uniform(5000, 100000), 2)
        polizas.append({
            "id_poliza": str(uuid.uuid4()),
            "id_asegurado": asegurado["id_asegurado"],
            "ramo": random.choices(RAMOS, weights=PROBS, k=1)[0],
            "fecha_inicio": fecha_inicio.isoformat(),
            "fecha_fin": fecha_fin.isoformat(),
            "prima": round(suma_asegurada * random.uniform(0.01, 0.05), 2),
            "suma_asegurada": suma_asegurada,
            "deducible": round(suma_asegurada * random.uniform(0.05, 0.1), 2),
            "canal_venta": random.choice(["Broker", "Directo", "Digital", "Banco"]),
            "ciudad": asegurado["ciudad"],
            "estado_poliza": random.choice(["Activa", "Cancelada", "Vencida"])
        })
        
    # 3. Proveedores
    proveedores = []
    for _ in range(N_PROVEEDORES):
        es_restrictiva = random.random() < 0.15
        pct_obs = round(random.uniform(0.31, 0.60) if es_restrictiva else random.uniform(0.0, 0.15), 2)
        proveedores.append({
            "id_proveedor": str(uuid.uuid4()),
            "nombre": fake.company(),
            "tipo": random.choice(["Taller", "Clinica", "Medico", "Perito", "Repuestos"]),
            "ciudad": random.choice(CIUDADES),
            "reclamos_asociados": random.randint(1, 50),
            "monto_promedio": round(random.uniform(500, 10000), 2),
            "pct_casos_observados": pct_obs,
            "antiguedad_anios": random.randint(1, 20),
            "en_lista_restrictiva": es_restrictiva
        })

    # Narrativas fraudulentas comunes
    narrativas_fraude = [
        "El vehículo estaba estacionado y al salir encontré el golpe en la parte trasera.",
        "Robo de celular al salir de la oficina por dos sujetos en moto.",
        "Accidente en intersección, el otro vehículo no respetó la señal de pare y se dio a la fuga."
    ]

    # 4. Siniestros
    siniestros = []
    for i in range(N_SINIESTROS):
        poliza = random.choice(polizas)
        fecha_inicio_pol = datetime.fromisoformat(poliza["fecha_inicio"]).date()
        fecha_fin_pol = datetime.fromisoformat(poliza["fecha_fin"]).date()
        
        # Lógica de distribución forzada para la DEMO (3 Rojos, 2 Amarillos, 5 Verdes)
        if i < 3: # ROJOS (Fraude descarado)
            is_fraud = True
            dias_desde_inicio = random.randint(1, 5)
            dias_reporte = random.randint(10, 30)
            historial = random.randint(4, 8)
            docs_completos = False
            monto_reclamado = poliza["suma_asegurada"] * round(random.uniform(0.95, 0.99), 2)
            prov_malos = [p for p in proveedores if p["en_lista_restrictiva"] or p["pct_casos_observados"] > 0.3]
            proveedor = random.choice(prov_malos) if prov_malos else random.choice(proveedores)
            descripcion = random.choice(narrativas_fraude)
            
        elif i < 5: # AMARILLOS (Riesgo medio/sospechoso)
            is_fraud = False
            dias_desde_inicio = random.randint(10, 40)
            dias_reporte = random.randint(5, 10)
            historial = random.randint(2, 3)
            docs_completos = True
            monto_reclamado = poliza["suma_asegurada"] * round(random.uniform(0.70, 0.85), 2)
            proveedor = random.choice(proveedores)
            descripcion = fake.text(max_nb_chars=100)
            
        else: # VERDES (Totalmente normales)
            is_fraud = False
            dias_desde_inicio = random.randint(100, 300)
            dias_reporte = random.randint(1, 3)
            historial = random.randint(0, 1)
            docs_completos = True
            monto_reclamado = poliza["suma_asegurada"] * round(random.uniform(0.10, 0.40), 2)
            prov_buenos = [p for p in proveedores if not p["en_lista_restrictiva"]]
            proveedor = random.choice(prov_buenos) if prov_buenos else random.choice(proveedores)
            descripcion = fake.text(max_nb_chars=150)

        fecha_ocurrencia = fecha_inicio_pol + timedelta(days=dias_desde_inicio)
        fecha_reporte = fecha_ocurrencia + timedelta(days=dias_reporte)
        dias_desde_fin = (fecha_fin_pol - fecha_ocurrencia).days
        monto_estimado = monto_reclamado * round(random.uniform(0.8, 1.0), 2)
        monto_pagado = 0.0 # asumimos pendiente

        siniestros.append({
            "id_siniestro": str(uuid.uuid4()),
            "id_poliza": poliza["id_poliza"],
            "id_asegurado": poliza["id_asegurado"],
            "id_proveedor": proveedor["id_proveedor"],
            "ramo": poliza["ramo"],
            "cobertura": random.choice(["Choque", "Robo", "Enfermedad", "Incendio", "RC"]),
            "fecha_ocurrencia": fecha_ocurrencia.isoformat(),
            "fecha_reporte": fecha_reporte.isoformat(),
            "monto_reclamado": round(monto_reclamado, 2),
            "monto_estimado": round(monto_estimado, 2),
            "monto_pagado": round(monto_pagado, 2),
            "estado": random.choice(["Reportado", "En Analisis", "Aprobado", "Rechazado"]),
            "sucursal": random.choice(["Matriz", "Sucursal Norte", "Sucursal Sur"]),
            "descripcion": descripcion,
            "documentos_completos": docs_completos,
            "beneficiario": fake.name(),
            "dias_desde_inicio_poliza": dias_desde_inicio,
            "dias_desde_fin_poliza": dias_desde_fin,
            "dias_entre_ocurrencia_reporte": dias_reporte,
            "historial_siniestros_asegurado": historial,
            "etiqueta_fraude_simulada": 1 if is_fraud else 0
        })
        
    # 5. Documentos
    documentos = []
    for _ in range(N_DOCUMENTOS):
        siniestro = random.choice(siniestros)
        documentos.append({
            "id_documento": str(uuid.uuid4()),
            "id_siniestro": siniestro["id_siniestro"],
            "tipo_documento": random.choice(["Factura", "Informe Policial", "Historia Clinica", "Presupuesto"]),
            "entregado": random.random() < 0.8,
            "legible": random.random() < 0.9,
            "fecha_emision": fake.date_between(start_date='-1y', end_date='today').isoformat(),
            "inconsistencia_detectada": random.random() < 0.1,
            "observacion": fake.sentence() if random.random() < 0.3 else ""
        })

    return asegurados, polizas, proveedores, siniestros, documentos

def upload_to_supabase(data_dict):
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Conectado a Supabase. Subiendo datos...")
        
        # Limpieza previa opcional o manejo de upsert. Aquí simplemente insertamos.
        # Orden de inserción importa por FKs
        tables = ["asegurados", "polizas", "proveedores", "siniestros", "documentos"]
        for table in tables:
            print(f"Insertando {len(data_dict[table])} registros en {table}...")
            # Supabase API limite de payload, dividir en chunks
            chunk_size = 100
            for i in range(0, len(data_dict[table]), chunk_size):
                chunk = data_dict[table][i:i+chunk_size]
                supabase.table(table).insert(chunk).execute()
        print("Carga a Supabase completada con éxito.")
    except Exception as e:
        print(f"Error al subir a Supabase: {e}")
        print("Asegúrate de que las tablas existan y las credenciales sean correctas.")

def save_to_csv(siniestros):
    os.makedirs("data/synthetic", exist_ok=True)
    df = pd.DataFrame(siniestros)
    path = "data/synthetic/siniestros.csv"
    df.to_csv(path, index=False)
    print(f"Siniestros guardados localmente en {path}")

if __name__ == "__main__":
    asegurados, polizas, proveedores, siniestros, documentos = generate_data()
    
    # Backup CSV
    save_to_csv(siniestros)
    
    # Supabase (si está configurado)
    if SUPABASE_URL and SUPABASE_KEY and "your_" not in SUPABASE_KEY:
        data_dict = {
            "asegurados": asegurados,
            "polizas": polizas,
            "proveedores": proveedores,
            "siniestros": siniestros,
            "documentos": documentos
        }
        upload_to_supabase(data_dict)
    else:
        print("Credenciales de Supabase no configuradas. Saltando subida a BD.")
