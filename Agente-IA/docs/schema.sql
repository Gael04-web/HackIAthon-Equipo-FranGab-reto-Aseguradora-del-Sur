-- Schema para Supabase: Aseguradora del Sur - Detección de Fraudes

CREATE TABLE asegurados (
    id_asegurado UUID PRIMARY KEY,
    segmento TEXT,
    antiguedad_anios INT,
    ciudad TEXT,
    num_polizas INT,
    reclamos_12m INT,
    mora_actual BOOLEAN,
    score_cliente FLOAT
);

CREATE TABLE polizas (
    id_poliza UUID PRIMARY KEY,
    id_asegurado UUID REFERENCES asegurados(id_asegurado),
    ramo TEXT CHECK (ramo IN ('Vehiculos','Salud','Vida','Generales','Hogar')),
    fecha_inicio DATE,
    fecha_fin DATE,
    prima NUMERIC,
    suma_asegurada NUMERIC,
    deducible NUMERIC,
    canal_venta TEXT,
    ciudad TEXT,
    estado_poliza TEXT
);

CREATE TABLE proveedores (
    id_proveedor UUID PRIMARY KEY,
    nombre TEXT,
    tipo TEXT,
    ciudad TEXT,
    reclamos_asociados INT,
    monto_promedio NUMERIC,
    pct_casos_observados FLOAT,
    antiguedad_anios INT,
    en_lista_restrictiva BOOLEAN
);

CREATE TABLE siniestros (
    id_siniestro UUID PRIMARY KEY,
    id_poliza UUID REFERENCES polizas(id_poliza),
    id_asegurado UUID REFERENCES asegurados(id_asegurado),
    id_proveedor UUID REFERENCES proveedores(id_proveedor),
    ramo TEXT,
    cobertura TEXT,
    fecha_ocurrencia DATE,
    fecha_reporte DATE,
    monto_reclamado NUMERIC,
    monto_estimado NUMERIC,
    monto_pagado NUMERIC,
    estado TEXT,
    sucursal TEXT,
    descripcion TEXT,
    documentos_completos BOOLEAN,
    beneficiario TEXT,
    dias_desde_inicio_poliza INT,
    dias_desde_fin_poliza INT,
    dias_entre_ocurrencia_reporte INT,
    historial_siniestros_asegurado INT,
    etiqueta_fraude_simulada INT DEFAULT 0,
    decision_analista TEXT DEFAULT 'Pendiente'
);

CREATE TABLE documentos (
    id_documento UUID PRIMARY KEY,
    id_siniestro UUID REFERENCES siniestros(id_siniestro),
    tipo_documento TEXT,
    entregado BOOLEAN,
    legible BOOLEAN,
    fecha_emision DATE,
    inconsistencia_detectada BOOLEAN,
    observacion TEXT
);
