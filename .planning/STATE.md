---
gsd_state_version: 1.0
milestone: v0.2.6
milestone_name: milestone
status: executing
stopped_at: Completed 02-05-PLAN.md
last_updated: "2026-09-18T05:45:40.714Z"
last_activity: 2026-09-18 -- Phase 02 planning complete
progress:
  total_phases: 8
  completed_phases: 1
  total_plans: 14
  completed_plans: 10
  percent: 13
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-17)

**Core value:** El ORM debe ser confiable en producción sobre cualquiera de los seis motores — correcto bajo concurrencia, seguro frente a inyección y configuraciones erróneas, y predecible en rendimiento.
**Current focus:** Phase 02 — Dialect Seam & Engine Parity
**Milestone:** encino_orm 0.2.6 → 0.3.0 (production hardening)

## Current Position

Phase: 02 (Dialect Seam & Engine Parity) — EXECUTING
Plan: 5 of 5
Status: Ready to execute
Last activity: 2026-09-18 -- Phase 02 planning complete

Progress: [█████████░] 90%

## Performance Metrics

**Velocity:**

- Total plans completed: 5
- Average duration: —
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 6 min | 4 tasks | 60 files |
| Phase 01 P02 | 9 min | 3 tasks | 4 files |
| Phase 01 P03 | 8 min | 3 tasks | 10 files |
| Phase 01 P04 | 12 min | 3 tasks | 12 files |
| Phase 01 P05 | 3 min | 3 tasks | 1 files |
| Phase 02 P01 | 4 min | 3 tasks | 11 files |
| Phase 02 P02 | 8 min | 5 tasks | 16 files |
| Phase 02 P03 | 6 min | 3 tasks | 14 files |
| Phase 02 P04 | 8 min | 3 tasks | 12 files |
| Phase 02 P05 | 10 min | 3 tasks | 11 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 8 phases derived from the research's dependency chain; standard granularity accepted at its upper bound because hard ordering constraints forbid compression.
- [Roadmap]: DATA (Phase 3) runs parallel to DIAL (Phase 2) — disjoint modules, no file overlap.
- [Roadmap]: TS-37 placeholder caching deferred to v2 as DATA-07; re-open only if profiling shows it in the top 5 hot paths.
- [Roadmap]: 0.2.7 is cut from the `v0.2.6` maintenance line, not from hardened `main`, so deprecation warnings describe behavior that still exists.
- [Phase ?]: line-length = 100 es la fuente de verdad para ruff (desviación consciente de AGENTS.md §Code Style; baseline medido 195 hallazgos a 88 vs 128 a 100). — Menor churn mecánico y menos hallazgos reales enterrados; el valor de config prevalece sobre la convención textual.
- [Phase 01]: PERF203 se ignora por fichero en encino_orm/base.py y encino_orm/pool.py. — El try/except debe permanecer dentro de bucles acotados (reintentos de deadlock y adquisición del pool); sacarlo cambia la semántica. Desviación documentada del plan, que esperaba corregirlo a mano.
- [Phase 01]: El F821 de encino_orm/model/query_builder.py se corrige con un import TYPE_CHECKING, no con supresión. — Erased en runtime, preserva el contrato de importación diferida de AGENTS.md; se verificó que F821 no aparece en ninguna lista de per-file-ignores.
- [Phase 01]: Ratchet de mypy con ignore_errors por modulo (15 modulos, 64 errores/17 ficheros) en lugar de # type: ignore — El conteo de supresiones inline en encino_orm/ sigue siendo 0; warn_unused_ignores impide la podredumbre. Los arreglos mecanicos quedan diferidos (research A6).
- [Phase 01]: El job typecheck sincroniza los mismos extras que test (--extra http --extra security --extra graphql) — El ratchet de mypy se midio con fastapi/PyJWT/strawberry-graphql importables; sin ellos ignore_missing_imports los vuelve Any y el gate mediria otro conjunto de errores (W3).
- [Phase 01]: Los 5 avisos GHSA de PyJWT 2.12.1 se aceptan con uv audit --ignore explicito y comentado — El flag ignore-until-fixed no suprime avisos que ya tienen fix (2.13.0), verificado empiricamente. El cap PyJWT inferior a 2.13 se ampliara al revalidar la capa security (Fase 6, CFG-02).
- [Phase 01]: pip-audit se alimenta de un fichero temporal con la salida de uv export — pip-audit no acepta -r - (stdin) ni lee uv.lock (--locked . -> no lockfiles found), verificado empiricamente. Se mantienen dos feeds de avisos independientes: OSV (uv audit) y PyPA (pip-audit).
- [Phase 01]: El piso de cobertura se fija en 82 contra el 83% equivalente a CI (medido hoy 84.42% con -m 'not optional_engine'), NO contra el 88% local con seis motores: en CI solo corren MySQL y PostgreSQL y oracle.py cae del 59% al 16% (Pitfall 2b). Fase 2 lo sube (D-04/D-06).
- [Phase 01]: El guard de seleccion de markers se refuerza con una comprobacion por fichero de motor: la asercion '> 0' del plan no detectaba la retirada del pytestmark de un solo fichero (quedaban 26 tests integration), de modo que el fallo inducido exigido por el plan habria pasado en verde.
- [Phase 01]: S603 en per-file-ignores para tests/test_pytest_config.py: el comando de subprocess lleva rutas de tmp_path y no puede ser literal; se prefirio a un # noqa para preservar el invariante noqa=0 de 01-01.
- [Phase 01]: El step de test de CI emite --junitxml=junit.xml y --cov* pero NO anade -m 'not optional_engine', ENCINO_ORM_REQUIRE_ENGINES ni el gate de skips: son del plan 01-04 y anadirlos haria inatribuible su prueba de fallo inducido.
- [Phase 01]: El gate de skips se reconcilia en la INVOCACION: el job requerido corre con -m 'not optional_engine', asi que skipped mayor que 0 en el XML es un skip NO marcado por construccion (D-02). — El JUnit-XML no lleva informacion de markers; deseleccionar los 13 tests opcionales antes del run elimina la ambiguedad en la fuente (verificado: no aparecen en el XML).
- [Phase 01]: El interruptor es solo env var (ENCINO_ORM_REQUIRE_ENGINES), nunca auto-deteccion (D-03). — La auto-deteccion es el fallo silencioso que la fase elimina; en local, sin la var, un motor ausente sigue omitiendo.
- [Phase 01]: release.yml no puede usar needs: sobre un job de otro fichero: CI se expone con on.workflow_call y publish llama ./.github/workflows/ci.yml (CI-08). — Con ./ el workflow llamado es el del mismo commit que el caller (correcto sobre un tag); workflow_run correria contra la rama por defecto.
- [Phase 01]: El except Exception de los 8 fixtures de motor NO se estrecha en Fase 1. — Un typo de env var o un ImportError degradan a skip en local y el interruptor lo hace irrelevante en CI (cualquier fallo de un motor requerido es fallo duro); estrecharlo es Pitfall 1 y queda para Fase 2.
- [Phase 01]: S314 (xml.etree.ElementTree) se ignora por fichero en tools/ci/check_skips.py con justificacion escrita (T-01-11). — El XML es un artefacto de build del propio job y ET de CPython no resuelve entidades externas; defusedxml violaria la regla solo-stdlib del gate.
- [Phase 01]: Los tests del arnes llevan el nombre del modulo en el metodo (test_check_skips_*, test_require_engines_*) para que -k seleccione de verdad. — TestCheckSkipsMain no contiene el literal check_skips (falta el guion bajo), asi que -k deseleccionaba los 13 tests y pasaba en vacio.
- [Phase 01]: Los tests de caracterizacion del pool capturan el comportamiento actual tal cual (D-09): la carrera de acquire() con 5 tareas y max_size=2 produce _size=5 de forma determinista gracias a una barrera hecha con asyncio.Event (piso 3.10); la asercion _size > _max_size se espera invertir en Fase 4 (POOL-02).
- [Phase 01]: Baselines medidos para Fase 4: last_id fuera de transaccion lee un cache a nivel de pool compartido entre tareas (POOL-03); release() no confirma, no revierte ni comprueba liveness (POOL-04); close() cierra una conexion que un llamador aun mantiene (POOL-06).
- [Phase 02]: La allowlist de identificadores NO se relaja para aceptar nombres cualificados; el caso schema.tabla se resuelve con un parametro schema= validado por separado en 02-02 (Pitfall 10).
- [Phase 02]: sql.py:_COLUMN_RE y model/query_builder.py:_COLUMN_RE se conservan sin unificar: aceptan puntos a proposito y unificarlas seria un cambio de comportamiento; queda documentado con comentario y como candidata de seguimiento.
- [Phase 02]: El anclaje $ del allowlist acepta un salto final (tabla\n); se conserva tal cual por ser refactor puro y se caracteriza en un test en lugar de endurecerlo silenciosamente.
- [Phase ?]: MariaDB conserva UPSERT_KIND='on_conflict' verbatim (identidad exacta Engine.MYSQL); se marca como hallazgo para fase posterior, no se arregla en 02-02.
- [Phase ?]: Los dos separadores del objetivo de conflicto quedan pinados: build_upsert usa ',' sin espacio y build_insert usa ', ' con espacio.
- [Phase ?]: D-03 literal: hash/eq de Query sobre (sql_template, fields), EXCLUYE ignore_duplicated; si DATA-07 usa este hash como clave, debe anadir el flag.
- [Phase 02]: La inmutabilidad de Query es de ATRIBUTO, no profunda: reasignar lanza, pero q.fields.append(v) y q.params[...] = v no lanzan y ademas invalidan el hash calculado del estado vivo; documentado en el docstring y en 0-design.md.
- [Phase 02]: En LIMITS solo sqlite (32766) y postgresql (32767) estan verificados empiricamente/en fuente; mysql/mariadb (65535), mssql (2100) y oracle (65535) quedan marcados NO verificados y su sonda pertenece al job engine-heavy de 02-05.
- [Phase 02]: Query.__slots__ se ordeno (RUF023) y se anadieron anotaciones de clase desnudas (mypy no ve slots escritos con object.__setattr__); los slots siguen siendo privados con properties sin setter, sin cambio de comportamiento.
- [Phase ?]: El alias del wrapper de conteo pasa de _encino_orm_count a encino_orm_count: Oracle rechaza identificadores que empiezan por _ (ORA-00911).
- [Phase ?]: La paginacion de Model.search se delega en fetch_many en vez de emitir LIMIT/OFFSET inline: SQL Server y Oracle usan OFFSET ... FETCH NEXT y solo el adaptador conoce su sintaxis.
- [Phase ?]: sync_schema emite ADD <col> <tipo> (sin la palabra COLUMN): es la forma valida en los seis motores.
- [Phase ?]: El filtro name= de list_tables queda fuera de alcance por estar roto en 4 de 6 motores (alias referenciado en WHERE); registrado en deferred-items.md.
- [Phase 02]: syrupy==6.1.1 se fija con pin exacto (como ruff): el formato de serializacion de los snapshots .ambr esta versionado, y sin pin una version nueva podria reformatearlos y romper CI en un PR no relacionado.
- [Phase 02]: Los snapshots de SQL son un GATE, no advisory: 9 tests DB-free en el job SQLite siempre activo; el .ambr va en el mismo commit que el test y un snapshot ausente FALLA (syrupy es sound). Se acepta el default estricto de snapshots huerfanos (sin --snapshot-warn-unused).
- [Phase 02]: MariaDB y Redis se promueven a requeridos en el job test EN EL MISMO commit que retira sus marcadores optional_engine (Pitfall H): promover sin quitar el marcador deja los tests deseleccionados y CI verde sin verificar nada.
- [Phase 02]: El job engine-heavy selecciona motores por FICHERO, no por marker: test_mssql.py/test_oracle.py conservan optional_engine para que el job test los deseleccione, y filtrar por marker alli dejaria el job probando CERO tests.
- [Phase 02]: engine-heavy instala msodbcsql18 + unixodbc-dev explicitamente (ubuntu-24.04 no trae ninguno) y sobreescribe ENCINO_ORM_ORACLE_SERVICE=FREEPDB1 (la imagen CI es gvenzl/oracle-free; docker-compose.yml usa XEPDB1). Sin continue-on-error en ningun job de gate.
- [Phase 02]: Sin pisos de cobertura de adaptador todavia: oracle.py mide 16% en la corrida equivalente a CI porque Oracle esta deseleccionado. Los numeros se fijan cuando engine-heavy este verde; su cobertura ya fluye al job coverage via el patron coverage-*.
- [Phase 02]: coverage.json se anade a .gitignore: es un artefacto generado por el job coverage que alimenta tools/ci/check_coverage_floors.py.

### Pending Todos

None yet.

### Blockers/Concerns

- **Phase 1 gate on Phase 4:** CI-09 pool characterization tests must exist before any POOL refactor. If Phase 1 is compressed, this item cannot be.
- **`ARCHITECTURE.md` is wrong** about PostgreSQL `lastval()` being transaction-scoped (it is session-scoped). Correct it before Phase 4 planning. See ROADMAP.md "Research Corrections".
- **POOL-04 is the milestone's highest-risk change:** flipping release-from-commit to release-from-rollback can silently drop standalone writes. The three-step sequence in ROADMAP.md must be followed.
- **Open research flags:** Phase 2 (syrupy/testcontainers topology), Phase 4 (`PooledConnection` + `last_id` API contract), Phase 5 (per-driver disconnect classification), Phase 6 (`__signature__`, GraphQL namespace), Phase 7 (per-dialect parameter ceilings).
- 5 avisos GHSA reales de PyJWT 2.12.1 (auth bypass, SSRF, DoS) quedan allowlisteados en el job deps hasta ampliar el cap PyJWT inferior a 2.13; requiere decision de seguimiento en la Fase 6 (CFG-02).

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Performance | DATA-07 — `Query` placeholder caching (TS-37) | Deferred to v2, pending profiler evidence | 2026-09-17 (roadmap) |
| Observability | OBSV-01…05, RELI-01…05, DATA-05/06 | Deferred to 0.3.x / 0.4+ | 2026-09-17 (roadmap) |

## Session Continuity

Last session: 2026-09-18T04:54:57.737Z
Stopped at: Completed 02-05-PLAN.md
Resume file: None
