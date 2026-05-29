import os
import json
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
    return df


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

    print("Conectado a Supabase. Subiendo datos...")
    order      = ['asegurados', 'polizas', 'proveedores', 'siniestros', 'documentos']
    chunk_size = 100

    for table in order:
        records = data_dict[table]
        print(f"  Insertando {len(records)} registros en '{table}'...")
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            resp  = requests.post(
                base_url + table,
                data=json.dumps(chunk, default=str),
                headers=headers,
                timeout=30,
            )
            if not resp.ok:
                print(f"  Error en '{table}' chunk {i}: {resp.status_code} — {resp.text[:200]}")
                resp.raise_for_status()

    print("Carga a Supabase completada con éxito.")


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

    print(f"\nResumen del dataset:")
    print(f"  Asegurados : {len(df_aseg)}")
    print(f"  Pólizas    : {len(df_pol)}")
    print(f"  Proveedores: {len(df_prov)}")
    print(f"  Siniestros : {len(df_sin)}")
    print(f"  Documentos : {len(df_docs)}")

    save_csv(df_sin)

    if SUPABASE_URL and SUPABASE_KEY and "your_" not in SUPABASE_KEY:
        upload_to_supabase({
            'asegurados': df_aseg.to_dict('records'),
            'polizas':    df_pol.to_dict('records'),
            'proveedores': df_prov.to_dict('records'),
            'siniestros': df_sin.to_dict('records'),
            'documentos': df_docs.to_dict('records'),
        })
    else:
        print("Credenciales de Supabase no configuradas. Solo se guardó el CSV local.")
