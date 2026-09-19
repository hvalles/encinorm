# Phase 8: Release 0.3.0 - Context

**Gathered:** 2026-09-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Enviar de punta a punta el camino de deprecación de 0.3.0: publicar 0.2.7 con
`DeprecationWarning` en runtime por cada ruptura de 0.3.0, migrar la publicación a
OIDC trusted publishing con un entorno `pypi` protegido y gateado sobre CI verde,
publicar 0.3.0rc1 y luego 0.3.0, y completar la documentación de rupturas
(`CHANGELOG.md` con comportamiento viejo/nuevo por cada cambio incompatible +
`MIGRATION-0.3.md`) y la guía de README (pinning `~=0.2.6`, credenciales solo-dev,
enlace `prompts/`). Fuera de alcance: nuevos motores, funcionalidad nueva,
declaración de 1.0, y cualquier retirada de globales más allá de lo que exige REL-01.

</domain>

<decisions>
## Implementation Decisions

### Corte de 0.2.7
- **D-01:** 0.2.7 se corta como tag `v0.2.7` sobre `main` en el commit de congelación
  inmediatamente posterior a 08-01 (deprecaciones presentes, remociones ausentes). Se
  publica ANTES de que aterrice cualquier remoción o artefacto 0.3.0; `main` continúa
  hacia 0.3.0. No se crea rama `v0.2.x` dedicada (config `branching_strategy: none`);
  se creará solo si hace falta un hotfix de la línea 0.2.

### Gate del entorno pypi
- **D-02:** El entorno GitHub `pypi` es la única vía de publicación: deployment branch =
  `main`, CI completo como required status checks, y aprobación de la environment tras
  el tag. Publicar con CI rojo queda imposible. Si el plan de GitHub del repo no soporta
  required reviewers, el fallback documentado es wait timer + required checks + trigger
  manual por `workflow_dispatch`.

### OIDC / TestPyPI
- **D-03:** OIDC trusted publishing (`id-token: write`, sin `PYPI_API_TOKEN`) se activa y
  se valida PRIMERO contra TestPyPI; PyPI real usa OIDC desde 0.3.0rc1. `PYPI_API_TOKEN`
  se elimina (REL-03). 0.2.7 se publica con el mecanismo vigente (token/dispatch).
  `TEST_PYPI_API_TOKEN` permanece hasta validar OIDC en test, o se migra en el mismo
  movimiento.

### Ejecución de la fase
- **D-04:** La fase automatiza y valida todo lo previo a la publicación (workflows, gates,
  tags, docs, `uv build` + dry-run) y deja un checkpoint por versión. Las publicaciones
  reales a PyPI/TestPyPI las dispara el usuario; la sesión no maneja credenciales de
  publicación.

### the agent's Discretion
- Ubicación y alcance de `MIGRATION-0.3.md` (no discutido): colócalo en `docs/` con enlace
  desde README; debe enumerar todas las rupturas acumuladas desde 0.2.6 (Fases 2–7), no
  solo los shims deprecados.
- Selección de los checks exactos del CI exigidos como required status checks del entorno.
- Estrategia de validación local (`uv build`, `twine check`/equivalente, `uv publish
  --dry-run` si aplica).

### Folded Todos
- Ninguno (0 todos pendientes).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope y requisitos
- `.planning/ROADMAP.md` — sección "Phase 8: Release 0.3.0" (goal, 5 planes 08-01..08-05, criterios de éxito)
- `.planning/REQUIREMENTS.md` — REL-01..REL-05 (líneas 79–83)
- `.planning/PROJECT.md` — Constraints (compat 0.x con CHANGELOG obligatorio; sin nuevos motores; sin 1.0)

### Estado actual de release
- `pyproject.toml` — versión actual `0.2.6`, extras y entry point CLI
- `CHANGELOG.md` — sección `[Unreleased]` define las rupturas/deprecaciones ya presentes
- `.github/workflows/release.yml` — release actual con `PYPI_API_TOKEN` + OIDC documentado inline
- `.github/workflows/publish-testpypi.yml` — publish manual a TestPyPI con `TEST_PYPI_API_TOKEN`
- `.github/workflows/ci.yml` — jobs que deben ser los required status checks
- `README.md` — pinning, credenciales de desarrollo, enlace `prompts/`

### Referencia externa (fuentes oficiales, estables)
- PyPI Trusted Publishing (OIDC) y GitHub Environments — documentación oficial
- SemVer 2.0 y Keep a Changelog (ya referenciados en `CHANGELOG.md`)

No hay ADRs/specs internos adicionales.

</canonical_refs>

<specifics>
## Specific Ideas

- El tag 0.2.7 debe apuntar a un commit anterior a las remociones; 08-01 materializa ese
  punto de congelación y 08-03 no debe reordenar los commits.
- Criterio de Éxito #2 ("no way to publish past a red CI gate") ⇒ el environment `pypi`
  es el mecanismo, no solo `needs:` dentro del workflow.
- REL-03 exige OIDC activo + `PYPI_API_TOKEN` eliminado; conservar el token no es aceptable.

</specifics>

<deferred>
## Deferred Ideas

- Rama de mantenimiento `v0.2.x` dedicada — diferida; solo se crea si surge un hotfix de 0.2.x.

</deferred>

---

*Phase: 08-release-0-3-0*
*Context gathered: 2026-09-19*
