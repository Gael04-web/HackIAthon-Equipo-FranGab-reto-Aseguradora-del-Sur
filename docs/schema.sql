-- Schema para Supabase: Aseguradora del Sur — Detección de Fraudes
-- Dataset real: Evento Datasets_Sinteticos_Fraude_500_v2.xlsx
-- IDs son TEXT (SIN-0001, POL-0001, ASEG-0010, TALLER-007, DOC-0001)

-- Limpiar tablas anteriores (ejecutar si ya existen)
-- DROP TABLE IF EXISTS documentos, siniestros, polizas, proveedores, asegurados CASCADE;

CREATE TABLE asegurados (
    id_asegurado        TEXT PRIMARY KEY,
    nombre_asegurado    TEXT,
    segmento            TEXT,
    ciudad              TEXT,
    antiguedad_anios    INT,
    num_polizas         INT,
    reclamos_12m        INT,
    reclamos_historico_total  INT,
    reclamos_rc_sin_tercero   INT,
    perfil_riesgo       TEXT   -- Alto / Medio / Bajo
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
    id_proveedor        TEXT PRIMARY KEY,
    nombre              TEXT,
    tipo                TEXT,
    ciudad              TEXT,
    reclamos_asociados  INT,
    monto_promedio      NUMERIC,
    en_lista_restrictiva BOOLEAN,
    motivo_restriccion  TEXT
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
    decision_analista               TEXT DEFAULT 'Pendiente'
);

CREATE TABLE documentos (
    id_documento    TEXT PRIMARY KEY,
    id_siniestro    TEXT REFERENCES siniestros(id_siniestro),
    tipo_documento  TEXT,
    nombre_archivo  TEXT,
    url_pdf         TEXT    -- URL pública en Supabase Storage (bucket: siniestros-docs)
);
