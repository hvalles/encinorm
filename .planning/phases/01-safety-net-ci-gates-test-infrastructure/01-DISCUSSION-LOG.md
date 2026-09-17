# Phase 1: Safety Net — CI Gates & Test Infrastructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-17
**Phase:** 1-Safety Net — CI Gates & Test Infrastructure
**Areas discussed:** Motores requeridos, Política de cobertura, Endurecer pytest

---

## Motores requeridos

### ¿Qué motores debe EXIGIR el interruptor de CI en la Fase 1?

| Option | Description | Selected |
|--------|-------------|----------|
| MySQL + PostgreSQL | Solo los servicios que ya existen; el switch nace pero casi no cambia el resultado actual | ✓ |
| + MariaDB + Redis | Imágenes ligeras; cubre dialecto MySQL/MariaDB y caché Redis con coste bajo | |
| Los seis motores | Máxima confianza pero ~4GB y 1-3 min de arranque sobre timeout de 15 min | |

**User's choice:** MySQL + PostgreSQL
**Notes:** Conservador y alineado con la infraestructura actual. El switch queda extensible para Fase 2 (DIAL-08).

### ¿Cómo tratamos los motores que NO son requeridos en Fase 1?

| Option | Description | Selected |
|--------|-------------|----------|
| Skip marcado | Marker explícito (`optional_engine`); el gate de skipped solo falla por skips NO marcados | ✓ |
| Skip marcado + job manual | Añade workflow_dispatch para motores ausentes | |
| Mocks equivalentes | Sustituir tests de motores ausentes por mocks que verifican SQL generado | |

**User's choice:** Skip marcado
**Notes:** Evita falsos positivos del gate de skipped manteniendo visibilidad de los motores no cubiertos.

### ¿Cómo se activa el interruptor de motores requeridos?

| Option | Description | Selected |
|--------|-------------|----------|
| Solo CI, por env var | El interruptor se activa con env var definida solo en CI; local sigue saltando | ✓ |
| Auto-detección | Si detecta el servicio, lo exige; si no, salta (riesgo de degradar a verde) | |
| Siempre requerido | Correr la suite local exige MySQL y PostgreSQL siempre | |

**User's choice:** Solo CI, por env var
**Notes:** La auto-detección se descartó explícitamente por reproducir el anti-patrón "CI verde que no verifica nada".

---

## Política de cobertura

### ¿Cómo estructuramos los umbrales de cobertura?

| Option | Description | Selected |
|--------|-------------|----------|
| Global bajo + piso dialecto | Ratchet global bajo + piso alto en el seam de dialectos/builders | ✓ |
| Único global | Un solo número para todo el paquete | |
| Solo reportar | Publicar el reporte sin bloquear | |

**User's choice:** Global bajo + piso dialecto
**Notes:** Motivado por el bug de `COUNT(*)`: un número global marca como cubierto código que solo funciona en SQLite.

### ¿La cobertura bloquea el merge en Fase 1, o arranca como ratchet?

| Option | Description | Selected |
|--------|-------------|----------|
| Ratchet no-baja | Baseline del estado actual; el gate falla solo si la cobertura baja | ✓ |
| Objetivo fijo 70/90 | Exige números absolutos desde el primer commit | |
| No bloquea aún | Reporte informativo sin bloqueo | |

**User's choice:** Ratchet no-baja
**Notes:** Permite mergear la infraestructura sin obligar a escribir una tanda masiva de tests primero.

### ¿Cuándo definimos el piso alto por dialecto?

| Option | Description | Selected |
|--------|-------------|----------|
| Mecanismo ahora, piso en F2 | Fase 1 monta `parallel=true`, `COVERAGE_FILE` por job y `coverage combine`; el piso se fija en Fase 2 | ✓ |
| Fijar todo ahora | Definir módulos y porcentajes aunque el seam aún no exista | |
| Sin piso por dialecto | Solo el gate global | |

**User's choice:** Mecanismo ahora, piso en F2
**Notes:** Mantiene la frontera de fase: el piso apunta al seam `dialects/`, que nace en Fase 2.

---

## Endurecer pytest

### ¿Cómo tratamos los warnings de pytest?

| Option | Description | Selected |
|--------|-------------|----------|
| Error + allowlist | `filterwarnings = ["error", ...]` con ignores explícitos, comentados y acotados | ✓ |
| Error total | Cero warnings tolerados desde ya | |
| No bloquear | Mantener el comportamiento por defecto | |

**User's choice:** Error + allowlist
**Notes:** Los warnings nuevos fallan; los conocidos y justificados quedan documentados en la allowlist.

### ¿Qué markers registramos y aplicamos?

| Option | Description | Selected |
|--------|-------------|----------|
| Registrar y marcar integración | `integration`, `optional_engine`, `concurrency`, `benchmark`; aplicar `integration` para que el comando del README funcione | ✓ |
| Solo markers nuevos | Registrar solo `optional_engine` y `concurrency` | |
| Clasificar todo ahora | Añadir `slow` y clasificar toda la suite | |

**User's choice:** Registrar y marcar integración
**Notes:** Convierte en real el comando documentado `uv run pytest -m "not integration"` (`README.md:130`).

### ¿Hasta dónde llega el alcance de Fase 1 al endurecer pytest?

| Option | Description | Selected |
|--------|-------------|----------|
| Config + arreglos mínimos | Config endurecida + corregir solo las incompatibilidades, en commits separados y bisectables | ✓ |
| Config + tightening amplio | Reescribir además asserts genéricos y de estado privado en toda la suite | |
| Config sin warnings aún | Solo markers y loop scopes; diferir `filterwarnings=error` | |

**User's choice:** Config + arreglos mínimos
**Notes:** No se reescriben `pytest.raises(Exception)` ni asserts de estado privado en esta fase.

---

## the agent's Discretion

- Selección exacta del primer ruleset de `ruff` (empezar por `E/W/F/I/UP/B/C4/SIM/PERF/FURB/ASYNC/RUF/S/PT`, diferir `ANN`/`D`/`PL`).
- Valor numérico del piso global inicial del ratchet de cobertura (contra el baseline medido).
- Versión exacta de `uv` a fijar (mínimo recomendado 0.12.15, por `uv audit`).
- Forma concreta del gate post-run sobre JUnit-XML.

## Deferred Ideas

- Matriz multi-motor completa (MariaDB/Redis/MSSQL/Oracle) — Fase 2 (DIAL-08).
- Piso de cobertura por dialecto — Fase 2, sobre el seam `dialects/`.
- Reescritura de asserts genéricos y de estado privado — fuera de Fase 1.
- `uv check` / `ty` como gate — mantener local hasta comparar ruido contra mypy.
