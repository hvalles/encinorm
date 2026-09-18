# Phase 2: Dialect Seam & Engine Parity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-18
**Phase:** 2-Dialect Seam & Engine Parity
**Areas discussed:** Refactor de Query

---

## Áreas presentadas (no todas discutidas)

Se presentaron 5 áreas grises. El usuario eligió discutir **solo** el refactor de `Query`:

| Área | Resultado |
|------|-----------|
| Validación de identificadores | No discutida — a criterio de research/planning |
| Matriz CI multi-motor | No discutida — a criterio de research/planning |
| Piso cobertura dialecto | No discutida — a criterio de research/planning |
| **Refactor de Query** | **Discutida** |
| Snapshots syrupy | No discutida — a criterio de research/planning |

---

## Refactor de Query

### ¿Cómo abordamos el refactor de `Query`?

| Option | Description | Selected |
|--------|-------------|----------|
| Ruptura limpia | `Query` inmutable; `rebind` eliminado; documentado en CHANGELOG + MIGRATION-0.3.md | ✓ |
| Inmutable + shim deprecado | `rebind()` sigue existiendo devolviendo copia con `DeprecationWarning` | |
| Arreglos mínimos | Solo corregir sentinel y `format`; mantener mutabilidad y `rebind` | |

**User's choice:** Ruptura limpia
**Notes:** Se justificó con el hallazgo de que `rebind` no se usa en ningún punto de `encino_orm/` ni de `tests/`; solo aparece en `docs/design/0-design.md`. Riesgo real bajo.

### ¿Qué interfaz expone el `Query` inmutable?

| Option | Description | Selected |
|--------|-------------|----------|
| Accesores tipados + compat | `sql`/`params` tipados + property `query` de solo lectura; los adaptadores migran en DIAL-02 | ✓ |
| Mantener query[0]/query[1] | Inmutable con la lista posicional como atributo público | |
| Ruptura total del contrato | Los adaptadores pasan a `.sql`/`.params` en el mismo commit | |

**User's choice:** Accesores tipados + compat
**Notes:** Evita que DIAL-05 toque los 6 adaptadores; la migración a los accesores tipados se hace en DIAL-02, cuando ya se reescriben los builders.

### ¿Qué semántica de igualdad/hash queremos?

| Option | Description | Selected |
|--------|-------------|----------|
| Igualdad completa + hash estricto | `__eq__` plantilla+params; `__hash__` sobre tupla de params con `TypeError` si no son hashables | ✓ |
| Solo sobre la plantilla | `__eq__`/`__hash__` solo por `sql_template` | |
| Solo inmutable | Sin `__eq__`/`__hash__` (identidad por objeto) | |

**User's choice:** Igualdad completa + hash estricto
**Notes:** Habilita un cache-key real para DATA-07 (v2) y falla ruidosamente en vez de devolver un hash engañoso.

### ¿Qué contrato de plantilla mantiene `Query`?

| Option | Description | Selected |
|--------|-------------|----------|
| Mantener {n} + compilar bien | `Query("… ({0},{1})", [a,b])` sigue siendo la entrada; se arregla la compilación y se valida cardinalidad | ✓ |
| {n} + dict nombrado opcional | Acepta también `%(nombre)s` con dict | |
| Solo %(nombre)s | Elimina la traducción `{n}` | |

**User's choice:** Mantener {n} + compilar bien
**Notes:** Se documentó el bug real: `format()` itera `enumerate(cols)`, así que solo reemplaza índices contiguos desde 0; un `{2}` con 2 params queda literal.

### `docs/design/0-design.md` documenta `rebind` con ejemplos. ¿Qué hacemos?

| Option | Description | Selected |
|--------|-------------|----------|
| Actualizar el design doc | Reescribir la sección de `Query` a la API nueva + nota de migración | ✓ |
| Marcar como histórico | Aviso de "superado" sin reescribir | |
| Diferir a Fase 8 | No tocar docs ahora; el CHANGELOG cubre la ruptura | |

**User's choice:** Actualizar el design doc
**Notes:** El sitio de docs se publica (hvalles.github.io/encinorm), así que no debe documentar una API eliminada.

---

## the agent's Discretion

- Estructura interna del seam `dialects/` (nombres de módulos, forma de los hooks por dialecto).
- Forma exacta de `with_params()` y de la validación de cardinalidad.
- Valores concretos de `MAX_PARAMS`/`MAX_ROWS` por dialecto (la investigación los marca como no verificados empíricamente).
- Selección del SQL exacto que se congela en los snapshots.
- Las 4 áreas no discutidas (validación de identificadores, matriz CI, piso de cobertura, snapshots syrupy) quedan a criterio de research/planning, sujetas a las restricciones duras del ROADMAP y de `research/PITFALLS.md`.

## Deferred Ideas

- Cache de placeholders compilados (TS-37) → v2 como `DATA-07`; D-03 deja `Query` listo (hashable) sin implementarlo.
- Modo de params nombrados con dict — descartado para esta fase.
- Subir el piso global de cobertura — el piso por dialecto es lo prometido para Fase 2.
