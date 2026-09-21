# Retrospective — encino_orm

Living retrospective across milestones.

## Milestone: v0.3.0 — Production Hardening

**Shipped:** 2026-09-20
**Phases:** 8 | **Plans:** 57 | **Commits:** ~359 | **Timeline:** 2026-09-17 → 2026-09-20 (~4 días)

### What Was Built

- Red de seguridad de CI que puede fallar: ruff, mypy + `py.typed`, cobertura por patas con ratchet, escaneo de dependencias, interruptor de motores requeridos y release gateado por CI.
- Seam único `encino_orm/dialects/` para validación de identificadores y construcción DML; `Query` inmutable; bug `COUNT(*)` corregido en los 7 sitios; snapshots SQL por dialecto.
- Corrección de datos: migraciones con ledger/rollback/reconcile, `CachedModel` sin lecturas obsoletas, `scope()` aplicado al DML.
- Pool correcto bajo concurrencia (`PooledConnection`, captura de id dentro del INSERT, `reset_on_release`).
- Resiliencia: clasificación de desconexiones, reconexión exactamente-una-vez, `pre_ping`/`max_connection_lifetime`, taxonomía pública de errores.
- Config/opcional: `ConnectionRegistry` y `SecurityConfig` inmutables; `exec()` sustituido por closures con snapshots OpenAPI/SDL byte-idénticos.
- Rendimiento: profiling-first, harness de benchmarks con gate 2×, `copy_table` por lotes, tracer acotado y caches weak.
- Release: `0.2.7` (deprecaciones) → `0.3.0rc1` → `0.3.0` por OIDC trusted publishing, sin token de larga vida, con entorno `pypi` protegido; retiradas reales + `CHANGELOG`/`MIGRATION-0.3`.

### What Worked

- **Medir antes de optimizar (PERF-03):** la línea base de profiling se comprometió antes de tocar `copy_table`, dando evidencia de comparación inequívoca.
- **Guardas de snapshot / byte-idénticas:** OpenAPI y SDL capturadas ANTES del rewrite de `exec()` convirtieron la no-regresión en un diff cero verificable.
- **Loop verificar → revisar → corregir:** en la Fase 7 el code-review encontró un High real (corrupción silenciosa por filas desparejas) y un Medium (SQL inválido) que se corrigieron con commits atómicos y se re-verificaron en CI.
- **OIDC validado primero en TestPyPI:** hizo segura y ensayable la migración de publicación de producción.

### What Was Inefficient

- **Choke points incompletos:** la Fase 2 necesitó 3 rondas de gap closure porque el "único punto de validación" no estaba barrido en todas las posiciones de interpolación; la Fase 3 sumó rondas 2-4 + `CR-R4-01`.
- **Summaries faltantes al cierre:** la Fase 7 se cerró con verifier/review pero sin `07-01`/`07-04` SUMMARY; hubo que reconstruirlos al cerrar el milestone (drift de ROADMAP/STATE).
- **Desviación del "v0.2.6 maintenance line":** el corte de 0.2.7 desde `main` endurecido (D-01) simplificó pero divergió del ROADMAP; requirió override registrado.
- **Config de trusted publisher:** el primer publish de PyPI falló por `invalid-publisher` (workflow name/environment en PyPI), detectado tarde; se corrigió y re-lanzó el tag existente.

### Patterns Established

- Seam único por concern con allowlist estricta; escape hatch documentado (`schema=`).
- Snapshots como guardián de no-regresión en rewrites de metaprogramación.
- Benchmarks zero-dep con pisos calibrados y canario que mide la función de producción.
- Declaración de conocimiento diferido (Pitfalls) por fase; guards file-wide donde el artefacto se promueve.
- Publicación OIDC con entorno protegido (branch + tag) y gate `publish: needs: [ci]`.

### Key Lessons

- Un "choke point" declarado no lo es hasta barrer TODAS las posiciones; presupuestar una ronda de sweep tras el primer fix.
- Al cerrar una fase, exigir SUMMARY por plan o registrar explícitamente la excepción, para no dejar drift.
- El código de release también necesita test: los guards de config/CHANGELOG atraparon inconsistencias antes de publicar.
- Validar el camino de publicación en un entorno desechable (TestPyPI) antes del de producción.

### Cost Observations

- Model mix: orquestador + subagentes GSD (`gsd-planner`, `gsd-phase-researcher`, `gsd-executor`, `gsd-verifier`, `gsd-code-reviewer`, `gsd-plan-checker`).
- Sessions: múltiples, con checkpoints humanos en los pasos de publicación.
- Notable: el uso de subagentes por plan mantuvo el contexto del orquestador bajo; el coste principal fue el loop de revisión de la Fase 7 y las rondas de gap-closure de Fases 2/3.
