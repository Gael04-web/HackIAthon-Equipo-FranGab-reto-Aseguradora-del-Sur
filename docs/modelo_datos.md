# Modelo de Datos — Fraudia Claims

Todas las tablas residen en **Supabase (PostgreSQL)**. Los datos provienen del dataset real `Evento_Datasets_Sinteticos_Fraude_500_v2.xlsx` y se cargan con `src/ingestion/load_data.py`. El script DDL está en `docs/schema.sql`.

Los identificadores son **TEXT** con formato legible: `SIN-0001`, `POL-0001`, `ASEG-0010`, `TALLER-007`, `DOC-0001`, `VEH-0001`.

---

## Tablas

### `asegurados`
Cada persona o empresa asegurada (174 registros).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_asegurado` | TEXT (PK) | Identificador (ASEG-XXXX) |
| `nombre_asegurado` | TEXT | Nombre del asegurado (sintético) |
| `segmento` | TEXT | Natural / Jurídico |
| `ciudad` | TEXT | Ciudad del asegurado |
| `antiguedad_anios` | INT | Años como cliente |
| `num_polizas` | INT | Pólizas activas |
| `reclamos_12m` | INT | Reclamos en los últimos 12 meses |
| `reclamos_historico_total` | INT | Reclamos históricos totales |
| `reclamos_rc_sin_tercero` | INT | Reclamos de RC sin tercero identificado (alimenta RF-12/RF-13) |
| `perfil_riesgo` | TEXT | Alto / Medio / Bajo (alimenta RF-09) |

---

### `polizas`
Contratos de seguro vinculados a un asegurado (500 registros).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_poliza` | TEXT (PK) | Identificador (POL-XXXX) |
| `id_asegurado` | TEXT (FK) | Referencia a `asegurados` |
| `ramo` | TEXT | Vehículos / Hogar / Salud |
| `fecha_inicio` | DATE | Inicio de vigencia |
| `fecha_fin` | DATE | Fin de vigencia |
| `suma_asegurada` | NUMERIC | Límite máximo de cobertura |
| `prima` | NUMERIC | Prima anual |
| `canal_venta` | TEXT | Broker / Digital / Agente / Banco |
| `estado_poliza` | TEXT | Vigente / Expirada |

---

### `proveedores`
Talleres, clínicas y peritos (33 registros).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_proveedor` | TEXT (PK) | Identificador (TALLER-XXX / HOSP-XXX / PROV-XXX) |
| `nombre` | TEXT | Nombre del proveedor |
| `tipo` | TEXT | Taller / Salud / Perito / ... |
| `ciudad` | TEXT | Ciudad de operación |
| `reclamos_asociados` | INT | Total de siniestros tramitados |
| `monto_promedio` | NUMERIC | Monto promedio de reclamos |
| `en_lista_restrictiva` | BOOL | En lista negra antifraude (alimenta RF-04) |
| `motivo_restriccion` | TEXT | Razón de la restricción (si aplica) |

---

### `siniestros`
Tabla central. Cada fila es un siniestro reportado (500 registros).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_siniestro` | TEXT (PK) | Identificador (SIN-XXXX) |
| `id_poliza` | TEXT (FK) | Referencia a `polizas` |
| `id_asegurado` | TEXT (FK) | Referencia a `asegurados` |
| `id_proveedor` | TEXT (FK) | Referencia a `proveedores` |
| `ramo` | TEXT | Vehículos / Hogar / Salud |
| `placa_vehiculo` | TEXT | Placa (si es ramo Vehículos) |
| `cobertura` | TEXT | 15 coberturas reales (Choque, Robo, Responsabilidad Civil, Incendio, Hospitalización...) |
| `fecha_ocurrencia` | DATE | Cuándo ocurrió |
| `fecha_reporte` | DATE | Cuándo se reportó |
| `dias_entre_ocurrencia_reporte` | INT | Demora en reportar (RF-02/RF-06) |
| `monto_reclamado` | NUMERIC | Monto solicitado (RF-07) |
| `monto_estimado` | NUMERIC | Estimación interna |
| `monto_pagado` | NUMERIC | Monto pagado |
| `estado` | TEXT | Reserva / Pago Total / Pago Parcial / Negativa / Liquidado / Investigación |
| `sucursal` | TEXT | Ciudad de la sucursal (10 ciudades) |
| `descripcion` | TEXT | Narración libre (alimenta NLP / RF-08) |
| `documentos_completos` | BOOL | Documentación completa (RF-05) |
| `en_lista_restrictiva` | BOOL | Proveedor del siniestro en lista restrictiva |
| `dias_desde_inicio_poliza` | INT | Días desde inicio de vigencia (RF-01) |
| `dias_desde_fin_poliza` | INT | Días hasta fin de vigencia (RF-01) |
| `historial_siniestros_asegurado` | INT | Frecuencia del asegurado (RF-03) |
| `suma_asegurada` | NUMERIC | Suma asegurada de la póliza |
| `max_similarity_nlp` | FLOAT | Similitud máxima de narrativa (precalculada, RF-08) |
| `numero_parte_policial` | TEXT | N° de parte policial (si aplica) |
| `beneficiario` | TEXT | Beneficiario del pago (RF-11) |
| `decision_analista` | TEXT | Pendiente / Fraude Confirmado / En Investigación / Legítimo |

> **Etiqueta de fraude:** el modelo ML deriva la etiqueta del campo `estado` (`Investigación` y `Negativa` = sospechoso). No hay columna de etiqueta verificada — ver `docs/limitaciones.md`.

---

### `vehiculos`
Datos del vehículo asegurado, uno por siniestro de ramo Vehículos (~350 registros).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_vehiculo` | TEXT (PK) | Identificador (VEH-XXXX) |
| `id_siniestro` | TEXT (FK) | Referencia a `siniestros` |
| `placa` | TEXT | Placa del vehículo |
| `marca` | TEXT | Marca (Toyota, Chevrolet, Kia...) |
| `modelo` | TEXT | Modelo |
| `anio` | INT | Año del vehículo |
| `chasis` | TEXT | Número de chasis VIN (alimenta RF-10) |
| `motor` | TEXT | Número de motor (alimenta RF-10) |

> El chasis/motor repetido entre siniestros es señal de vehículo clonado o fraude de partes (RF-10).

---

### `documentos`
Documentos adjuntos a un siniestro (1.263 registros; 26 con PDF físico en Storage).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id_documento` | TEXT (PK) | Identificador (DOC-XXXX) |
| `id_siniestro` | TEXT (FK) | Referencia a `siniestros` |
| `tipo_documento` | TEXT | Factura / Parte Policial / Declaración de Accidente / Peritaje / Fotografías... |
| `nombre_archivo` | TEXT | Nombre del archivo PDF (si tiene) |
| `url_pdf` | TEXT | URL pública en Supabase Storage (bucket `siniestros-docs`) |

---

## Supabase Storage

Los PDFs reales (facturas, partes policiales, declaraciones de accidente) se almacenan en el bucket **`siniestros-docs`** (público). La columna `documentos.url_pdf` apunta a cada archivo. La app los muestra embebidos y los analiza con Gemini.

---

## Relaciones

```
asegurados ──< polizas ──< siniestros >── proveedores
                               │
                               ├──< documentos  (url_pdf → Storage)
                               │
                               └──< vehiculos
```

---

## Volúmenes de Datos

| Tabla | Registros |
|-------|-----------|
| asegurados | 174 |
| polizas | 500 |
| proveedores | 33 |
| siniestros | 500 |
| vehiculos | ~350 |
| documentos | 1.263 (26 con PDF) |

---

## Distribución del dataset

- **Ramos:** Vehículos (350), Hogar (85), Salud (65)
- **15 coberturas** reales del sector
- **10 ciudades** ecuatorianas como sucursales
- **6 estados** de siniestro
- **3 proveedores** en lista restrictiva con motivo

Los siniestros nuevos registrados desde la app reciben un ID correlativo (`SIN-0501`, `SIN-0502`...) y sus PDFs adjuntos se suben al bucket de Storage.
