# Phase 3: Data Correctness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-18
**Phase:** 3-Data Correctness
**Areas discussed:** Reconciliación de migraciones, Ledger de rollback, Invalidación de caché, Cota de MemoryCacheBackend

---

## Reconciliación de migraciones

### ¿Cómo reconciliamos una migración cuyo DDL no es transaccional?

| Option | Description | Selected |
|--------|-------------|----------|
| Estado 2 fases + fallo ruidoso | `pending` antes del DDL; al reconciliar, un `pending` es ambiguo → `MigrationError` con el SQL | ✓ |
| Estado 2 fases + reintento | Reintento automático asumiendo DDL idempotente | |
| Solo transaccional + detectar | Sin máquina de estados; transacción donde se pueda | |

**User's choice:** Estado 2 fases + fallo ruidoso
**Notes:** Re-ejecutar DDL automáticamente se descartó por peligroso con DDL no idempotente; asumir `applied` se descartó porque sería el registro mintiendo.

### ¿Cuándo se ejecuta la reconciliación?

| Option | Description | Selected |
|--------|-------------|----------|
| En `migrate()` + API | Comprobación en `migrate()` + `reconcile_migrations(db)` para el arranque | ✓ |
| Solo en `migrate()` | Sin API nueva | |
| Solo API explícita | El usuario decide cuándo | |

**User's choice:** En `migrate()` + API

### ¿Dónde vive el marcador de estado?

| Option | Description | Selected |
|--------|-------------|----------|
| En los 6 motores, uniforme | Columna `status` siempre; requiere `ALTER TABLE` idempotente | ✓ |
| Solo no transaccionales | Esquema distinto y ramas de dialecto | |
| Reusar `applied_at` | Cambia el significado de una columna existente | |

**User's choice:** En los 6 motores, uniforme

### Cuando la reconciliación encuentra un `pending`, ¿cómo lo resuelve el humano?

| Option | Description | Selected |
|--------|-------------|----------|
| Lanzar + helper de resolución | `resolve_migration(db, name, *, applied=bool)` | ✓ |
| Lanzar, resolver por SQL | El mensaje de error da el SQL exacto | |
| Auto-marcar aplicada | Cómodo pero el registro puede mentir | |

**User's choice:** Lanzar + helper de resolución

---

## Ledger de rollback

### ¿Qué deja el ledger tras un rollback?

| Option | Description | Selected |
|--------|-------------|----------|
| Borrar fila, sin registrar :down | `migrate_status()` solo muestra migraciones aplicadas | ✓ |
| Borrar + registrar :down histórico | Deja rastro pero mezcla eventos con migraciones | |
| Ledger separado | Máximo historial, más superficie | |

**User's choice:** Borrar fila, sin registrar :down

### ¿El rollback también usa la máquina de estados de 2 fases?

| Option | Description | Selected |
|--------|-------------|----------|
| Reutilizar `pending` | Simétrico pero la reconciliación no distingue la dirección | |
| Estado `rolling_back` propio | La reconciliación sabe la dirección y da instrucciones específicas | ✓ |
| Sin maquinaria en rollback | El fallo parcial queda indetectado | |

**User's choice:** Estado `rolling_back` propio

### ¿Cómo se expone la resolución?

| Option | Description | Selected |
|--------|-------------|----------|
| Helper único, acción inferida | `resolve_migration(db, name, *, applied)` | ✓ |
| Dos helpers explícitos | `resolve_pending` + `resolve_rollback` | |
| Acción explícita del humano | `action="mark_applied"\|"delete"\|"restore_applied"` | |

**User's choice:** Helper único, acción inferida

---

## Invalidación de caché

### ¿Qué rutas de escritura invalidan la caché?

| Option | Description | Selected |
|--------|-------------|----------|
| Todas las rutas de escritura | `update`/`delete`/`save`/`upsert`/`insert_many`; `insert` puro no | ✓ |
| Solo update/delete | Letra del ROADMAP; deja `save`/`upsert` obsoletos | |
| Todas + namespace | Sobre-invalida hoy | |

**User's choice:** Todas las rutas de escritura
**Notes:** Se aplicó explícitamente la lección de Fase 2 ("un choke point declarado no lo es hasta barrer todas las posiciones").

### ¿En qué orden se invalida respecto a la escritura?

| Option | Description | Selected |
|--------|-------------|----------|
| Store-then-invalidate | Invalidar tras el commit (hook `after_commit`) | ✓ |
| Invalidate-then-store | Una lectura intermedia repuebla con el valor viejo | |
| Write-through | Evita el miss pero hay que construir el payload y manejar carreras | |

**User's choice:** Store-then-invalidate

### ¿Qué pasa si la invalidación falla?

| Option | Description | Selected |
|--------|-------------|----------|
| Log y continuar | Fail-open; el TTL acota la obsolescencia | ✓ |
| Propagar el error | Error sobre una escritura ya commiteada | |
| Doble intento | Más robusto, más round-trips | |

**User's choice:** Log y continuar

---

## Cota de MemoryCacheBackend

### ¿Cómo acotamos el backend en memoria?

| Option | Description | Selected |
|--------|-------------|----------|
| LRU + contrato documentado | `max_size` con evicción LRU + docstring/docs dev-test-only | ✓ |
| Solo LRU | Resuelve el crecimiento, contrato solo en el código | |
| Solo documentar | Cero código; el riesgo de prod permanece | |

**User's choice:** LRU + contrato documentado

### ¿Cuál es el valor por defecto y la política exacta?

| Option | Description | Selected |
|--------|-------------|----------|
| 1024 + LRU puro | `OrderedDict.move_to_end`; desaloja la primera al llenar | ✓ |
| None por defecto | Conserva el default inseguro | |
| 1024 + purga expirados | Mejor uso de memoria, más código | |

**User's choice:** 1024 + LRU puro

---

## the agent's Discretion

- Pisos de cobertura para `migration.py`/`cached.py`/`cache_backend.py` (el mecanismo ya existe desde Fase 2).
- Forma exacta del `ALTER TABLE` idempotente por dialecto.
- Nombres y firmas exactos de los métodos nuevos.
- Si `insert_many` invalida por lote o clave a clave.
- Si `migrate_status()` cambia de forma al exponer `status`.

## Deferred Ideas

- Centralizar la lógica de `migrate()` (hoy duplicada en 6 adaptadores) — refactor mayor, fase posterior.
- Ledger de rollbacks histórico en tabla separada — descartado por superficie extra.
- Write-through / caché por consulta — descartado; hoy solo se cachea por PK.
- Reintento automático de DDL — descartado por peligroso con DDL no idempotente.
- Purga de expirados antes de desalojar en el backend en memoria — descartado por simplicidad.
