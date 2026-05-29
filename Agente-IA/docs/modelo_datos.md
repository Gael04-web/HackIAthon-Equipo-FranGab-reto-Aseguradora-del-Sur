# Modelo de Datos — Fraudia Claims

Todas las tablas residen en Supabase (PostgreSQL). El script `src/ingestion/load_data.py` crea los registros sintéticos.

## Tablas

### `asegurados`
Representa a cada persona o empresa asegurada.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_asegurado` | UUID (PK) | Identificador único |
| `segmento` | TEXT | VIP / Estandar / Corporativo |
| `antiguedad_anios` | INT | Años como cliente (0–15) |
| `ciudad` | TEXT | Guayaquil / Quito / Cuenca / Manta |
| `num_polizas` | INT | Pólizas activas del asegurado |
| `reclamos_12m` | INT | Siniestros en los últimos 12 meses |
| `mora_actual` | BOOL | Si tiene pagos en mora |
| `score_cliente` | FLOAT | Score interno de calidad (50–100) |

---

### `polizas`
Contratos de seguro vinculados a un asegurado.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_poliza` | UUID (PK) | Identificador único |
| `id_asegurado` | UUID (FK) | Referencia a `asegurados` |
| `ramo` | TEXT | Vehiculos / Salud / Vida / Hogar |
| `fecha_inicio` | DATE | Inicio de vigencia |
| `fecha_fin` | DATE | Fin de vigencia |
| `prima` | FLOAT | Prima anual pagada |
| `suma_asegurada` | FLOAT | Límite máximo de cobertura |
| `deducible` | FLOAT | Monto a cargo del asegurado |
| `canal_venta` | TEXT | Broker / Directo / Digital / Banco |
| `ciudad` | TEXT | Ciudad de emisión |
| `estado_poliza` | TEXT | Activa / Cancelada / Vencida |

---

### `proveedores`
Talleres, clínicas, médicos y peritos que atienden siniestros.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_proveedor` | UUID (PK) | Identificador único |
| `nombre` | TEXT | Nombre de la empresa |
| `tipo` | TEXT | Taller / Clinica / Medico / Perito / Repuestos |
| `ciudad` | TEXT | Ciudad de operación |
| `reclamos_asociados` | INT | Total histórico de siniestros tramitados |
| `monto_promedio` | FLOAT | Monto promedio de reclamos |
| `pct_casos_observados` | FLOAT | % de casos con irregularidades (0.0–1.0) |
| `antiguedad_anios` | INT | Años en el mercado |
| `en_lista_restrictiva` | BOOL | Figuras en lista negra antifraude |

---

### `siniestros`
Tabla central. Cada fila es un evento de siniestro reportado.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_siniestro` | UUID (PK) | Identificador único |
| `id_poliza` | UUID (FK) | Referencia a `polizas` |
| `id_asegurado` | UUID (FK) | Referencia a `asegurados` |
| `id_proveedor` | UUID (FK) | Referencia a `proveedores` |
| `ramo` | TEXT | Ramo del seguro |
| `cobertura` | TEXT | Choque / Robo / Enfermedad / Incendio / RC |
| `fecha_ocurrencia` | DATE | Cuándo ocurrió el siniestro |
| `fecha_reporte` | DATE | Cuándo lo reportó el cliente |
| `monto_reclamado` | FLOAT | Monto solicitado por el asegurado |
| `monto_estimado` | FLOAT | Estimación interna |
| `monto_pagado` | FLOAT | Monto efectivamente pagado |
| `estado` | TEXT | Reportado / En Analisis / Aprobado / Rechazado |
| `sucursal` | TEXT | Matriz / Sucursal Norte / Sucursal Sur |
| `descripcion` | TEXT | Narración libre del evento |
| `documentos_completos` | BOOL | Si se entregó documentación completa |
| `beneficiario` | TEXT | Quién recibe el pago |
| `dias_desde_inicio_poliza` | INT | Feature para detección temprana de fraude |
| `dias_desde_fin_poliza` | INT | Feature para detección de fraude al vencimiento |
| `dias_entre_ocurrencia_reporte` | INT | Demora en reportar |
| `historial_siniestros_asegurado` | INT | Frecuencia histórica del asegurado |
| `etiqueta_fraude_simulada` | INT | 1 = fraude simulado, 0 = legítimo (solo en datos sintéticos) |
| `decision_analista` | TEXT | Pendiente / Fraude Confirmado / En Investigación / Legítimo |

---

### `documentos`
Documentos adjuntos a un siniestro.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_documento` | UUID (PK) | Identificador único |
| `id_siniestro` | UUID (FK) | Referencia a `siniestros` |
| `tipo_documento` | TEXT | Factura / Informe Policial / Historia Clinica / Presupuesto |
| `entregado` | BOOL | Si fue presentado por el cliente |
| `legible` | BOOL | Si el documento es legible |
| `fecha_emision` | DATE | Fecha en el documento |
| `inconsistencia_detectada` | BOOL | Si el sistema detectó anomalías |
| `observacion` | TEXT | Nota del analista |

## Relaciones

```
asegurados ──< polizas ──< siniestros >── proveedores
                               │
                               └──< documentos
```

## Volúmenes de Datos Sintéticos

| Tabla | Registros |
|-------|-----------|
| asegurados | 200 |
| polizas | 300 |
| proveedores | 50 |
| siniestros | 500 |
| documentos | 20 |
