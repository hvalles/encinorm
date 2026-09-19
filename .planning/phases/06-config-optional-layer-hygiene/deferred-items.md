# Deferred Items — Phase 06 (config-optional-layer-hygiene)

Items descubiertos durante la ejecución que quedan **fuera del alcance** del plan
que los encontró. No se corrigen aquí.

## 06-05 (Wave 3 — gates, CHANGELOG, docs)

### El cross-check de `pip-audit` en CI no audita los extras opcionales

- **Descubierto en:** Task 3 (bump de `PyJWT`), 2026-09-19.
- **Qué:** el job `deps` de `.github/workflows/ci.yml` ejecuta
  `uv export --format requirements-txt --no-emit-project --no-hashes` y alimenta
  ese fichero a `pip-audit`. `uv export` **sin `--all-extras`/`--extra`** solo
  exporta las dependencias por defecto y el grupo `dev`; los extras `security`,
  `http`, `graphql`, etc. quedan **fuera**. Verificado localmente: el export de
  228 líneas no contiene `pyjwt`, `fastapi` ni `strawberry-graphql`.
- **Consecuencia:** el segundo feed (PyPA) no cubre `PyJWT` — precisamente la
  dependencia cuyo cap se subió. El `uv audit` (feed OSV) sí la cubre, así que el
  gate primario es correcto; el cross-check es más débil de lo que su comentario
  sugiere.
- **Evidencia del bump:** `uv audit` sin ignores → "Found no known vulnerabilities
  and no adverse project statuses in 97 packages"; `pip-audit -r <export>` → "No
  known vulnerabilities found"; además se auditó `pyjwt==2.14.0` **directamente**
  con `pip-audit -r` → "No known vulnerabilities found".
- **Propuesta (fuera de alcance):** añadir `--all-extras` (o los `--extra`
  relevantes) al `uv export` del job `deps` para que el feed PyPA cubra la
  superficie opcional. Requiere su propio commit y revalidar el runtime del job.
