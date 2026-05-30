import os
import json
import random
import string
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Ruta al Excel del dataset real.
# Por defecto busca en data/dataset/ dentro del proyecto.
# Se puede sobreescribir con la variable de entorno DATASET_PATH.
_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
DATASET_PATH = os.getenv(
    "DATASET_PATH",
    os.path.join(_BASE, "data", "dataset", "Evento_Datasets_Sinteticos_Fraude_500_v2.xlsx")
)


# ---------------------------------------------------------------------------
# Lectura del Excel
# ---------------------------------------------------------------------------

def load_excel() -> dict:
    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(
            f"No se encontró el dataset en:\n  {DATASET_PATH}\n"
            "Copia el archivo Excel a esa ruta o define la variable DATASET_PATH en .env"
        )
    print(f"Leyendo dataset desde: {DATASET_PATH}")
    return pd.read_excel(DATASET_PATH, sheet_name=None)


# ---------------------------------------------------------------------------
# Transformaciones por tabla
# ---------------------------------------------------------------------------

def transform_asegurados(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().rename(columns={
        'ID Asegurado':                   'id_asegurado',
        'Nombres Asegurado':              'nombre_asegurado',
        'Segmento':                       'segmento',
        'Ciudad':                         'ciudad',
        'Antigüedad (años)':              'antiguedad_anios',
        'N° Pólizas Activas':             'num_polizas',
        'N° Reclamos Últimos 12 Meses':   'reclamos_12m',
        'N° Reclamos Histórico Total':    'reclamos_historico_total',
        'Reclamos RC sin Tercero':        'reclamos_rc_sin_tercero',
        'Perfil Riesgo Histórico':        'perfil_riesgo',
    })
    df['nombre_asegurado']         = df['nombre_asegurado'].fillna('')
    df['reclamos_historico_total'] = pd.to_numeric(df['reclamos_historico_total'], errors='coerce').fillna(0).astype(int)
    df['reclamos_rc_sin_tercero']  = pd.to_numeric(df['reclamos_rc_sin_tercero'],  errors='coerce').fillna(0).astype(int)
    return df


def transform_polizas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().rename(columns={
        'ID Póliza':          'id_poliza',
        'ID Asegurado':       'id_asegurado',
        'Ramo':               'ramo',
        'Fecha Inicio':       'fecha_inicio',
        'Fecha Fin':          'fecha_fin',
        'Suma Asegurada ($)': 'suma_asegurada',
        'Prima Anual ($)':    'prima',
        'Canal Venta':        'canal_venta',
        'Estado Póliza':      'estado_poliza',
    })
    for col in ['fecha_inicio', 'fecha_fin']:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
    return df


def transform_proveedores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.drop(columns=[c for c in df.columns if 'Unnamed' in str(c)], errors='ignore')
    df = df.rename(columns={
        'ID Proveedor':            'id_proveedor',
        'Nombre Proveedor':        'nombre',
        'Tipo':                    'tipo',
        'Ciudad':                  'ciudad',
        'N° Siniestros Asociados': 'reclamos_asociados',
        'En Lista Restrictiva':    'en_lista_restrictiva',
        'Motivo Restricción':      'motivo_restriccion',
        'Promedio Monto ($)':      'monto_promedio',
    })
    df['en_lista_restrictiva'] = df['en_lista_restrictiva'].map({'Sí': True, 'Si': True, 'No': False}).fillna(False)
    df['motivo_restriccion']   = df['motivo_restriccion'].replace({'No': ''}).fillna('')
    df['monto_promedio']       = pd.to_numeric(
        df['monto_promedio'].astype(str).str.replace('—', '', regex=False), errors='coerce'
    ).fillna(0.0)
    return df


def transform_siniestros(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().rename(columns={
        'ID Siniestro':                  'id_siniestro',
        'ID Póliza':                     'id_poliza',
        'ID Asegurado':                  'id_asegurado',
        'Ramo':                          'ramo',
        'Placa Vehículo Asegurado':      'placa_vehiculo',
        'Cobertura':                     'cobertura',
        'Fecha Ocurrencia':              'fecha_ocurrencia',
        'Fecha Reporte':                 'fecha_reporte',
        'Días Ocurr→Reporte':            'dias_entre_ocurrencia_reporte',
        'Monto Reclamado ($)':           'monto_reclamado',
        'Monto Estimado ($)':            'monto_estimado',
        'Monto Pagado ($)':              'monto_pagado',
        'Estado':                        'estado',
        'Sucursal':                      'sucursal',
        'ID Proveedor':                  'id_proveedor',
        'Descripción del Evento':        'descripcion',
        'Docs Completos':                'documentos_completos',
        'Prov. Lista Restrictiva':       'en_lista_restrictiva',
        'Días desde Inicio Póliza':      'dias_desde_inicio_poliza',
        'Días hasta Fin Póliza':         'dias_desde_fin_poliza',
        'N° Reclamos Previos Asegurado': 'historial_siniestros_asegurado',
        'Suma Asegurada ($)':            'suma_asegurada',
        'Similitud Narrativa Máx.':      'max_similarity_nlp',
        'Número Parte Policial':         'numero_parte_policial',
    })

    # Booleanos
    df['documentos_completos'] = df['documentos_completos'].map({'Sí': True, 'Si': True, 'No': False}).fillna(False)
    df['en_lista_restrictiva'] = df['en_lista_restrictiva'].map({'Sí': True, 'Si': True, 'No': False}).fillna(False)

    # Fechas
    for col in ['fecha_ocurrencia', 'fecha_reporte']:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')

    # Nulos
    df['placa_vehiculo']        = df['placa_vehiculo'].fillna('')
    df['numero_parte_policial'] = df['numero_parte_policial'].fillna('')
    df['descripcion']           = df['descripcion'].fillna('')
    df['max_similarity_nlp']    = pd.to_numeric(df['max_similarity_nlp'], errors='coerce').fillna(0.0)
    df['monto_pagado']          = pd.to_numeric(df['monto_pagado'], errors='coerce').fillna(0.0)

    # Decisión analista vacía al inicio
    df['decision_analista'] = 'Pendiente'

    return df


def transform_documentos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().rename(columns={
        'ID Documento':       'id_documento',
        'ID Siniestro':       'id_siniestro',
        'Tipo Documento':     'tipo_documento',
        'Nombre Archivo PDF': 'nombre_archivo',
    })
    df['nombre_archivo'] = df['nombre_archivo'].fillna('')
    df['url_pdf']        = None  # se rellena después de subir a Storage
    # Reemplazar todos los NaN/NaT restantes por None para JSON válido
    df = df.where(pd.notna(df), other=None)
    return df


# ---------------------------------------------------------------------------
# Supabase Storage — subida de PDFs
# ---------------------------------------------------------------------------

DOCS_FOLDER = os.path.join(_BASE, "data", "docs")
STORAGE_BUCKET = "siniestros-docs"


def upload_pdfs_to_storage(df_docs: pd.DataFrame) -> pd.DataFrame:
    """
    Sube todos los PDFs de data/docs/ al bucket de Supabase Storage
    y actualiza el DataFrame de documentos con la url_pdf pública.
    """
    if not os.path.exists(DOCS_FOLDER):
        print("  Carpeta data/docs/ no encontrada. Saltando subida de PDFs.")
        return df_docs

    storage_url = SUPABASE_URL.rstrip('/') + f"/storage/v1/object/{STORAGE_BUCKET}/"
    headers_storage = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "x-upsert":      "true",
    }

    import glob
    pdfs = glob.glob(os.path.join(DOCS_FOLDER, "*.pdf"))
    print(f"  Subiendo {len(pdfs)} PDFs a Supabase Storage (bucket: {STORAGE_BUCKET})...")

    url_map = {}  # filename → public URL
    for pdf_path in pdfs:
        filename = os.path.basename(pdf_path)
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            resp = requests.post(
                storage_url + filename,
                data=pdf_bytes,
                headers={**headers_storage, "Content-Type": "application/pdf"},
                timeout=30,
            )
            if resp.ok:
                public_url = (
                    SUPABASE_URL.rstrip('/') +
                    f"/storage/v1/object/public/{STORAGE_BUCKET}/{filename}"
                )
                url_map[filename] = public_url
            else:
                print(f"    ⚠️  {filename}: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            print(f"    ⚠️  Error subiendo {filename}: {e}")

    print(f"  PDFs subidos: {len(url_map)}/{len(pdfs)}")

    # Mapear url_pdf a cada documento según nombre_archivo
    def find_url(nombre_archivo):
        if not nombre_archivo:
            return None
        # Buscar coincidencia directa o parcial
        for fname, url in url_map.items():
            if nombre_archivo in fname or fname in nombre_archivo:
                return url
        return None

    df_docs = df_docs.copy()
    df_docs['url_pdf'] = df_docs['nombre_archivo'].apply(find_url)
    return df_docs


# ---------------------------------------------------------------------------
# Carga a Supabase
# ---------------------------------------------------------------------------

def upload_to_supabase(data_dict: dict):
    """Sube datos a Supabase usando la REST API directamente (sin supabase-py)."""
    base_url = SUPABASE_URL.rstrip('/') + "/rest/v1/"
    headers  = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }

    print("Conectado a Supabase. Subiendo datos (upsert)...")
    order      = ['asegurados', 'polizas', 'proveedores', 'siniestros', 'vehiculos', 'documentos']
    chunk_size = 100

    # Usar upsert para no fallar si los datos ya existen
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    def _clean(val):
        """Convierte NaN/NaT/inf a None para JSON válido."""
        import math
        if val is None:
            return None
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val

    def _clean_records(records):
        return [{k: _clean(v) for k, v in r.items()} for r in records]

    for table in order:
        records = _clean_records(data_dict[table])
        print(f"  Upsert {len(records)} registros en '{table}'...")
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            resp  = requests.post(
                base_url + table,
                data=json.dumps(chunk),
                headers=headers,
                timeout=30,
            )
            if not resp.ok:
                print(f"  Error en '{table}' chunk {i}: {resp.status_code} — {resp.text[:200]}")
                resp.raise_for_status()

    print("Carga a Supabase completada con éxito.")


# ---------------------------------------------------------------------------
# Generar tabla de Vehículos y enriquecer Siniestros con Beneficiario
# ---------------------------------------------------------------------------

MARCAS_MODELOS = {
    'Toyota':    ['Hilux', 'Corolla', 'RAV4', 'Land Cruiser', 'Yaris'],
    'Chevrolet': ['D-Max', 'Sail', 'Tracker', 'Captiva', 'Traverse'],
    'Kia':       ['Sportage', 'Rio', 'Sorento', 'Picanto', 'Cerato'],
    'Hyundai':   ['Tucson', 'Accent', 'Santa Fe', 'Elantra', 'Creta'],
    'Nissan':    ['Frontier', 'Sentra', 'X-Trail', 'Kicks', 'Versa'],
    'Mazda':     ['CX-5', 'Mazda 3', 'Mazda 6', 'BT-50', 'CX-30'],
}
NOMBRES_BENEFICIARIOS = [
    "García Morales Luis", "Pérez Vásquez Ana", "Torres Espinoza Carlos",
    "Rodríguez Cárdenas María", "López Herrera Pedro", "Castillo Vargas Rosa",
    "Mendoza Alvarado Jorge", "Ramos Flores Isabel", "Cabrera Ortega Diego",
    "Vásquez Muñoz Patricia", "Salazar Reyes Andrés", "Mora Jiménez Carmen",
]

def _rand_chasis() -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=17))

def _rand_motor() -> str:
    prefix = random.choice(['1NZ', '2GR', '3VZ', 'G4FC', 'D4CB', 'MR20'])
    suffix = ''.join(random.choices(string.digits, k=7))
    return f"{prefix}-{suffix}"

def generate_vehiculos(df_sin: pd.DataFrame) -> tuple:
    """
    Genera la tabla vehiculos para siniestros de ramo Vehículos.
    Introduce deliberadamente chasis/motor repetidos en ~8% de los casos
    para simular fraude de partes. Retorna (df_vehiculos, df_sin_enriquecido).
    """
    random.seed(42)
    vehiculos = []
    sin_df = df_sin.copy()

    # Pool de beneficiarios (algunos se repetirán en casos de fraude)
    sin_df['beneficiario'] = ''

    # Generar chasis/motor únicos base
    chasis_pool  = [_rand_chasis() for _ in range(500)]
    motor_pool   = [_rand_motor()  for _ in range(500)]

    # Índices de siniestros Vehículos
    idx_veh = sin_df[sin_df['ramo'] == 'Vehículos'].index.tolist()
    idx_fraud_veh = idx_veh[:int(len(idx_veh) * 0.08)]  # 8% comparten chasis/motor

    chasis_fraude = _rand_chasis()
    motor_fraude  = _rand_motor()

    for i, idx in enumerate(idx_veh):
        row  = sin_df.loc[idx]
        placa = row.get('placa_vehiculo', '') or f"GEN-{i:04d}"
        marca = random.choice(list(MARCAS_MODELOS.keys()))
        modelo = random.choice(MARCAS_MODELOS[marca])
        anio  = random.randint(2010, 2024)

        # Fraude: mismo chasis/motor en varios siniestros
        if idx in idx_fraud_veh:
            chasis = chasis_fraude
            motor  = motor_fraude
        else:
            chasis = chasis_pool[i % len(chasis_pool)]
            motor  = motor_pool[i % len(motor_pool)]

        vehiculos.append({
            'id_vehiculo':  f"VEH-{i+1:04d}",
            'id_siniestro': row['id_siniestro'],
            'placa':        placa,
            'marca':        marca,
            'modelo':       modelo,
            'anio':         anio,
            'chasis':       chasis,
            'motor':        motor,
        })

    # Asignar beneficiarios (algunos repetidos en casos de fraude)
    beneficiario_fraude = NOMBRES_BENEFICIARIOS[0]
    for i, idx in enumerate(sin_df.index):
        row = sin_df.loc[idx]
        # Casos con score alto (primeros 75) reciben beneficiario repetido
        if i < 75 and random.random() < 0.3:
            sin_df.at[idx, 'beneficiario'] = beneficiario_fraude
        else:
            sin_df.at[idx, 'beneficiario'] = random.choice(NOMBRES_BENEFICIARIOS)

    df_veh = pd.DataFrame(vehiculos)
    return df_veh, sin_df


# ---------------------------------------------------------------------------
# Backup CSV
# ---------------------------------------------------------------------------

def save_csv(df: pd.DataFrame):
    out = os.path.join(_BASE, "data", "synthetic", "siniestros.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False)
    print(f"CSV guardado en: {out}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sheets = load_excel()

    df_aseg = transform_asegurados(sheets['3_Asegurados'])
    df_pol  = transform_polizas(sheets['2_Polizas'])
    df_prov = transform_proveedores(sheets['4_Proveedores'])
    df_sin  = transform_siniestros(sheets['1_Siniestros'])
    df_docs = transform_documentos(sheets['5_Documentos'])

    # Generar vehículos y enriquecer siniestros con beneficiario
    df_veh, df_sin = generate_vehiculos(df_sin)

    print(f"\nResumen del dataset:")
    print(f"  Asegurados : {len(df_aseg)}")
    print(f"  Pólizas    : {len(df_pol)}")
    print(f"  Proveedores: {len(df_prov)}")
    print(f"  Siniestros : {len(df_sin)}")
    print(f"  Vehículos  : {len(df_veh)}")
    print(f"  Documentos : {len(df_docs)}")

    save_csv(df_sin)

    if SUPABASE_URL and SUPABASE_KEY and "your_" not in SUPABASE_KEY:
        df_docs = upload_pdfs_to_storage(df_docs)

        upload_to_supabase({
            'asegurados': df_aseg.to_dict('records'),
            'polizas':    df_pol.to_dict('records'),
            'proveedores': df_prov.to_dict('records'),
            'siniestros': df_sin.to_dict('records'),
            'vehiculos':  df_veh.to_dict('records'),
            'documentos': df_docs.to_dict('records'),
        })
    else:
        print("Credenciales de Supabase no configuradas. Solo se guardó el CSV local.")
