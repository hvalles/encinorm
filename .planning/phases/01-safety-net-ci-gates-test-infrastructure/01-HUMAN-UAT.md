---
status: resolved
phase: 01-safety-net-ci-gates-test-infrastructure
source: [01-VERIFICATION.md]
started: 2026-09-17T23:58:17Z
updated: 2026-09-18T01:10:00Z
---

## Current Test

[all tests resolved]

## Tests

### 1. CI-08 — el gate de release bloquea de verdad

expected: En una rama con un gate rojo, `publish` no arranca: el job reutilizable `ci` falla y `publish` aparece como `skipped` / nunca corre. Registrar la URL del run.

Pasos: push de un tag (o `workflow_dispatch`) sobre una rama con un gate deliberadamente rojo.
Motivo: requiere push a GitHub y un run real de Actions; no hay `gh` instalado. El cableado estructural (`needs: [ci]` + `uses: ./.github/workflows/ci.yml`) está verificado, pero la dependencia viva no se ejecutó.

result: resolved — run https://github.com/hvalles/encinorm/actions/runs/35295736525 (release.yml, tag `v0.0.0-verify-ci08` sobre el commit `9818a4f` de la rama scratch `ci/verify-gates`, con el step de publish neutralizado a un `echo`). Resultado: los 4 legs de `CI (reusable)` fallaron, y **`Build and publish` = skipped**. Un gate rojo impide publicar. Además validó por primera vez el patrón `workflow_call` invocado desde otro workflow. Rama y tag ya eliminados (local y remoto).

### 2. CI-01 — quitar un servicio de motor requerido hace fallar el job

expected: Quitando el servicio `mysql` (o `postgres`) de `ci.yml` en una rama scratch y haciendo push, el job `test` **falla** en lugar de pasar con skips (porque `ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql` convierte el skip en fallo). Registrar la URL del run y revertir.

Motivo: requiere editar `ci.yml` y correr en GitHub. El equivalente local exacto SÍ está probado (motor requerido inalcanzable → exit 1 con 13 errores, no skips), pero la corrida real con el servicio eliminado no se ejecutó.

result: resolved — run https://github.com/hvalles/encinorm/actions/runs/35295072430 (CI en PR #3, rama `ci/verify-gates` con el servicio `mysql` eliminado de `ci.yml` y `ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql` intacto). Resultado: **Python 3.10, 3.11, 3.12 y 3.13 = failure**; lint, tipos y deps = success; cobertura = skipped. Firma correcta: solo falla el job que depende de la BD, y falla en vez de omitir. Rama y PR ya eliminados.

### 3. Normalización del goal en modo MVP

expected: El goal de la Fase 1 en ROADMAP.md se reescribe en forma `Como …, quiero …, para que …`, o el desarrollador confirma explícitamente que un goal técnico (no user story) es lo intencionado para esta fase de CI/infraestructura.

Motivo: la Fase 1 está marcada `Mode: mvp`, pero `gsd-sdk query user-story.validate` devuelve `false` para su goal. La verificación se hizo contra los Success Criteria del ROADMAP (el contrato técnico), no contra una tabla de User Flow Coverage.

result: resolved — confirmado por el desarrollador: el goal técnico es lo intencionado. El flag `**Mode:** mvp` se retiró de la sección de Fase 1 en ROADMAP.md (ahora `**Mode:** standard`, con nota explicativa); `gsd-sdk query phase.mvp-mode 1` devuelve `active: false`. Las fases 2-8 conservan su modo sin cambios.

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

