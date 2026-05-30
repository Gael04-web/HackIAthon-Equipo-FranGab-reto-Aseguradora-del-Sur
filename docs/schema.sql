-- Schema para Supabase: Aseguradora del Sur — Detección de Fraudes
-- Dataset real: Evento Datasets_Sinteticos_Fraude_500_v2.xlsx
-- IDs son TEXT (SIN-0001, POL-0001, ASEG-0010, TALLER-007, DOC-0001)

-- Limpiar tablas anteriores (ejecutar si ya existen)
-- DROP TABLE IF EXISTS documentos, vehiculos, siniestros, polizas, proveedores, asegurados CASCADE;

CREATE TABLE asegurados (
    id_asegurado             TEXT PRIMARY KEY,
    nombre_asegurado         TEXT,
    segmento                 TEXT,
    ciudad                   TEXT,
    antiguedad_anios         INT,
    num_polizas              INT,
    reclamos_12m             INT,
    reclamos_historico_total INT,
    reclamos_rc_sin_tercero  INT,
    perfil_riesgo            TEXT   -- Alto / Medio / Bajo
);

CREATE TABLE polizas (
    id_poliza       TEXT PRIMARY KEY,
    id_asegurado    TEXT REFERENCES asegurados(id_asegurado),
    ramo            TEXT,
    fecha_inicio    DATE,
    fecha_fin       DATE,
    suma_asegurada  NUMERIC,
    prima           NUMERIC,
    canal_venta     TEXT,
    estado_poliza   TEXT
);

CREATE TABLE proveedores (
    id_proveedor         TEXT PRIMARY KEY,
    nombre               TEXT,
    tipo                 TEXT,
    ciudad               TEXT,
    reclamos_asociados   INT,
    monto_promedio       NUMERIC,
    en_lista_restrictiva BOOLEAN,
    motivo_restriccion   TEXT
);

CREATE TABLE siniestros (
    id_siniestro                    TEXT PRIMARY KEY,
    id_poliza                       TEXT REFERENCES polizas(id_poliza),
    id_asegurado                    TEXT REFERENCES asegurados(id_asegurado),
    id_proveedor                    TEXT REFERENCES proveedores(id_proveedor),
    ramo                            TEXT,
    placa_vehiculo                  TEXT,
    cobertura                       TEXT,
    fecha_ocurrencia                DATE,
    fecha_reporte                   DATE,
    dias_entre_ocurrencia_reporte   INT,
    monto_reclamado                 NUMERIC,
    monto_estimado                  NUMERIC,
    monto_pagado                    NUMERIC,
    estado                          TEXT,
    sucursal                        TEXT,
    descripcion                     TEXT,
    documentos_completos            BOOLEAN,
    en_lista_restrictiva            BOOLEAN,
    dias_desde_inicio_poliza        INT,
    dias_desde_fin_poliza           INT,
    historial_siniestros_asegurado  INT,
    suma_asegurada                  NUMERIC,
    max_similarity_nlp              FLOAT,
    numero_parte_policial           TEXT,
    beneficiario                    TEXT,
    decision_analista               TEXT DEFAULT 'Pendiente'
);

-- Vehículos asegurados: placa, chasis, motor, marca, modelo, año
-- Un vehículo puede aparecer en múltiples siniestros (señal de alerta)
CREATE TABLE vehiculos (
    id_vehiculo  TEXT PRIMARY KEY,
    id_siniestro TEXT REFERENCES siniestros(id_siniestro),
    placa        TEXT,
    marca        TEXT,
    modelo       TEXT,
    anio         INT,
    chasis       TEXT,   -- número de chasis VIN (señal de fraude si se repite)
    motor        TEXT    -- número de motor (señal de fraude si se repite)
);

CREATE TABLE documentos (
    id_documento  TEXT PRIMARY KEY,
    id_siniestro  TEXT REFERENCES siniestros(id_siniestro),
    tipo_documento TEXT,
    nombre_archivo TEXT,
    url_pdf        TEXT    -- URL pública en Supabase Storage (bucket: siniestros-docs)
);


-- ===========================================================================
-- Seguridad: Row Level Security (RLS) + políticas para el rol anon
-- ---------------------------------------------------------------------------
-- La app y el script de carga usan la "anon public key". Con RLS habilitado,
-- el rol anon NO puede leer ni escribir nada hasta definir políticas. Esto
-- mantiene la seguridad ACTIVA y concede los permisos que el sistema necesita.
-- Ejecutar este bloque DESPUÉS de crear las tablas (puede ser antes o después
-- de cargar los datos: las políticas de INSERT permiten que load_data.py corra).
-- ===========================================================================

ALTER TABLE asegurados   ENABLE ROW LEVEL SECURITY;
ALTER TABLE polizas      ENABLE ROW LEVEL SECURITY;
ALTER TABLE proveedores  ENABLE ROW LEVEL SECURITY;
ALTER TABLE siniestros   ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehiculos    ENABLE ROW LEVEL SECURITY;
ALTER TABLE documentos   ENABLE ROW LEVEL SECURITY;

-- LECTURA pública (la app consulta el portafolio completo)
CREATE POLICY "anon read asegurados"  ON asegurados  FOR SELECT TO anon USING (true);
CREATE POLICY "anon read polizas"     ON polizas     FOR SELECT TO anon USING (true);
CREATE POLICY "anon read proveedores" ON proveedores FOR SELECT TO anon USING (true);
CREATE POLICY "anon read siniestros"  ON siniestros  FOR SELECT TO anon USING (true);
CREATE POLICY "anon read vehiculos"   ON vehiculos   FOR SELECT TO anon USING (true);
CREATE POLICY "anon read documentos"  ON documentos  FOR SELECT TO anon USING (true);

-- INSERT en todas las tablas (necesario para la ingesta con load_data.py
-- y para registrar siniestros/documentos desde la app)
CREATE POLICY "anon insert asegurados"  ON asegurados  FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon insert polizas"     ON polizas     FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon insert proveedores" ON proveedores FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon insert siniestros"  ON siniestros  FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon insert vehiculos"   ON vehiculos   FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon insert documentos"  ON documentos  FOR INSERT TO anon WITH CHECK (true);

-- UPDATE en siniestros (decisión del analista) y documentos (url_pdf en recarga)
CREATE POLICY "anon update siniestros" ON siniestros FOR UPDATE TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon update documentos" ON documentos FOR UPDATE TO anon USING (true) WITH CHECK (true);

-- Permitir subir/leer PDFs en el bucket de Storage
CREATE POLICY "anon upload docs" ON storage.objects
    FOR INSERT TO anon WITH CHECK (bucket_id = 'siniestros-docs');
