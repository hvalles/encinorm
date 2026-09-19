# Discussion Log — Phase 8: Release 0.3.0

**Date:** 2026-09-19
**Areas discussed:** Corte de 0.2.7, Gate del entorno pypi, OIDC / TestPyPI, Publicación real vs en seco

## Área 1 — Corte de 0.2.7

**Pregunta:** ¿Cómo se corta y publica 0.2.7? Todo vive en `main` (branching:none) y las
remociones de 0.3.0 deben NO colarse en 0.2.7.

**Opciones presentadas:**
1. Tag en main (recomendado) — 08-01 aterriza, CI verde, tag `v0.2.7`, publica; remociones después.
2. Rama `v0.2.x` dedicada — línea de mantenimiento separada.
3. Pre-release antes (TestPyPI) — validar warnings antes de PyPI.

**Selección:** Tag en main (recomendado).

**Decisión (D-01):** tag `v0.2.7` sobre main en el commit de congelación tras 08-01; publica
antes de cualquier remoción/0.3.0; main sigue a 0.3.0; sin rama nueva salvo hotfix.

## Área 2 — Gate del entorno pypi

**Pregunta:** Criterio 2 exige "no publicar con CI rojo". ¿Qué nivel de protección?

**Opciones presentadas:**
1. Approval + checks (recomendado) — entorno `pypi` protegido, deployment branch main,
   required status checks + approval.
2. Solo checks — CI verde como vía única, sin approval manual.
3. Solo `needs` en workflow — sin environment protection.

**Selección:** Approval + checks (recomendado).

**Decisión (D-02):** entorno `pypi` con branch main + required checks + approval; fallback
documentado (wait timer + checks + `workflow_dispatch`) si el plan no soporta required reviewers.

## Área 3 — OIDC / TestPyPI

**Pregunta:** ¿Cómo se despliega OIDC trusted publishing vs los tokens actuales?

**Opciones presentadas:**
1. OIDC en test, prod en rc1 (recomendado).
2. OIDC desde 0.2.7.
3. Mantener tokens.

**Selección inicial:** Mantener tokens.

**Detección de conflicto:** REL-03 exige OIDC activo + `PYPI_API_TOKEN` eliminado; "conservar
tokens + OIDC inactivo" no satisface el requisito. Se re-preguntó.

**Opciones de resolución:**
1. Activamos OIDC en test (recomendado) — valida en TestPyPI, PyPI por OIDC desde 0.3.0rc1, token PyPI eliminado.
2. OIDC solo en 0.3.x — token para 0.2.7, OIDC activo desde rc1.
3. Re-planificar REL-03.

**Selección final:** Activamos OIDC en test (recomendado).

**Decisión (D-03):** OIDC se valida primero en TestPyPI; PyPI por OIDC desde 0.3.0rc1;
`PYPI_API_TOKEN` eliminado (REL-03 ✓).

## Área 4 — Publicación real vs en seco

**Pregunta:** Las publicaciones PyPI requieren credenciales que la sesión no posee. ¿Cómo se ejecuta?

**Opciones presentadas:**
1. Tú disparas las publicaciones (recomendado) — la fase automatiza todo lo previo + checkpoints.
2. End-to-end con tus credenciales.
3. Valida y documenta, no publica.

**Selección:** Tú disparas las publicaciones (recomendado).

**Decisión (D-04):** la fase automatiza workflows/gates/tags/docs/dry-runs; las publicaciones
reales las dispara el usuario con checkpoint.

## No discutido (discreción del agente)

- Ubicación/alcance de `MIGRATION-0.3.md` (área ofrecida y no seleccionada) → `docs/` + enlace
  desde README, enumerando todas las rupturas desde 0.2.6.
- Checks exactos exigidos por el entorno; estrategia de validación local.

## Deferred

- Rama de mantenimiento `v0.2.x` — diferida hasta que surja un hotfix.
