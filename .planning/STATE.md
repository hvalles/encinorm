---
gsd_state_version: 1.0
milestone: v0.2.6
milestone_name: milestone
status: executing
stopped_at: Phase 8 context gathered
last_updated: "2026-09-19T20:54:52.509Z"
last_activity: 2026-09-19 -- Phase 8 planning complete
progress:
  total_phases: 8
  completed_phases: 6
  total_plans: 57
  completed_plans: 47
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-17)

**Core value:** El ORM debe ser confiable en producción sobre cualquiera de los seis motores — correcto bajo concurrencia, seguro frente a inyección y configuraciones erróneas, y predecible en rendimiento.
**Current focus:** Phase 8 — release 0.3.0
**Milestone:** encino_orm 0.2.6 → 0.3.0 (production hardening)

## Current Position

Phase: 8 (pending)
Plan: Phase 7 complete (4/4)
Status: Ready to execute
Last activity: 2026-09-19 -- Phase 8 planning complete

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 46
- Average duration: —
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 5 | - | - |
| 02 | 12 | - | - |
| 3 | 13 | - | - |
| 04 | 3 | 6 | - |
| 4 | 6 | - | - |
| 5 | 4 | - | - |
| 6 | 5 | - | - |

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
| Phase 02 P06 | 2 min | 2 tasks | 7 files |
| Phase 02 P07 | 3 min | 2 tasks | 3 files |
| Phase 02 P08 | 14 min | 3 tasks | 17 files |
| Phase 02 P09 | 3 min | 2 tasks | 10 files |
| Phase 02 P10 | 4 min | 2 tasks | 2 files |
| Phase 02 P11 | 4 min | 2 tasks | 6 files |
| Phase 02 P12 | 2 min | 2 tasks | 4 files |
| Phase 03 P01 | 7 min | 3 tasks | 9 files |
| Phase 03 P03 | 7 min | 3 tasks | 4 files |
| Phase 3 P5 | 5 min | 1 tasks | 2 files |
| Phase 03 P02 | 3 min | 3 tasks | 14 files |
| Phase 03 P04 | 1 min | 2 tasks | 2 files |
| Phase 03 P06 | 8 | 3 tasks | 6 files |
| Phase 03 P07 | 2min | 2 tasks | 2 files |
| Phase 03 P09 | 8min | 3 tasks | 2 files |
| Phase 03 P10 | 6 min | 2 tasks | 3 files |
| Phase 03 P11 | 4 min | 2 tasks | 2 files |
| Phase 03 P12 | 4 min | 2 tasks | 2 files |
| Phase 03 P13 | 3 min | 2 tasks | 3 files |
| Phase 04 P01 | 7 min | 3 tasks | 5 files |
| Phase 04 P05 | 25 | 3 tasks | 4 files |
| Phase 04 P02 | 16 | 3 tasks | 28 files |
| Phase 04 P03 | 3min | 3 tasks | 5 files |
| Phase 04 P04 | 8min | 3 tasks | 5 files |
| Phase 04 P06 | 20 min | 3 tasks | 1 files |
| Phase 05 P01 | 5 min | 3 tasks | 14 files |
| Phase 5 P2 | 9 min | 3 tasks | 8 files |
| Phase 5 P3 | 3min | 3 tasks | 7 files |
| Phase 5 P4 | 7 min | 3 tasks | 15 files |
| Phase 06 P01 | 6 min | 2 tasks | 4 files |
| Phase 06 P02 | 4 min | 2 tasks | 4 files |
| Phase 06 P03 | 2 min | 3 tasks | 3 files |
| Phase 06 P04 | 7 min | 3 tasks | 3 files |
| Phase 06 P05 | 20 | 3 tasks | 17 files |
| Phase 07 P01 | - | - | 1 files |
| Phase 07 P02 | - | - | - |
| Phase 07 P03 | - | 3 tasks | 6 files |
| Phase 07 P04 | - | - | - |

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
- [Phase ?]: 02-06: alias y nombre de columna validados por la allowlist estricta; indexes_ddl fail-closed — Cierra CR-01/WR-06 haciendo de la allowlist un cuello de botella real sin relajarla
- [Phase 02]: 02-07: contrato de cardinalidad de Query sin carve-out + compilacion desde indice normalizado; doc de diseno sincronizado con guard de fuente — Un contrato documentado que no se aplica normaliza el uso roto; el carve-out era redundante y erroneo, y {00} producia KeyError en el adaptador.
- [Phase ?]: 02-08: paginacion de QueryBuilder delegada en el adaptador; MariaDB upsert emite ON DUPLICATE KEY UPDATE; Model.insert(replace=True) deriva el objetivo de conflicto de la PK solo en suffix (PostgreSQL) y conserva conflict=None en merge (MSSQL/Oracle); el MERGE de MSSQL/Oracle se corrige en la frontera del driver (';' y FROM dual) preservando la byte-identidad de snapshots y golden strings — Cierra el GAP 3 (WR-03/WR-04/WR-05) con cobertura en los seis motores; los dos fixes de MERGE son defectos preexistentes que bloqueaban la cobertura de motor
- [Phase ?]: 02-09: list_tables(name=) filtra sobre una columna REAL de una tabla derivada (encino_orm_tables) con LOWER() en ambos lados y valor ligado; cierra el GAP 4 y el ultimo diferido huerfano de la fase sin tocar el camino sin filtro — PostgreSQL/MySQL/SQL Server/Oracle no permiten alias de columna en WHERE; envolver expone name como columna real y deja el camino sin filtro byte-identico
- [Phase ?]: 02-10: _table validado con la allowlist ESTRICTA en QueryBuilder.__init__ (incondicional, fail-closed) y en join() antes del chequeo de duplicados; cierra el CR-01 de la ronda 2 sin relajar la allowlist
- [Phase ?]: 02-10: el barrido confirma que _table era el ultimo punto de interpolacion que necesitaba la allowlist estricta; las posiciones de expresion (select/group_by/order_by/sort_by/agregados) conservan _COLUMN_RE tolerante a puntos por decision (Pitfall 10) y se fijan con tests de caracterizacion + guard de fuente
- [Phase 02]: 02-11: el render merge falla CERRADO en _merge_sql (punto unico de build_insert/build_upsert) cuando una columna de conflicto no esta en el INSERT; cierra CR-02 sin derivar un default silencioso — En un modelo de PK autoincremental el id no viaja en data, asi que ON (dst.id = src.id) referenciaba una columna inexistente (MSSQL 207 / ORA-00904); elegir una columna representativa en silencio reintroduciria el mismo defecto semantico
- [Phase 02]: 02-11: Model.insert deja de consumir/asignar last_id() cuando la sentencia ejecutada es un MERGE (devuelve 0 y deja obj.id intacto); cierra CR-03 — MssqlDb.execute solo refresca _last_id para INSERT y OracleDb.execute solo con RETURNING; consumir el cache devolvia el id de OTRA fila (regresion de 02-08). La captura real del id (OUTPUT INSERTED.id) pertenece a la Fase 4 / POOL-03
- [Phase 02]: 02-12: extiende la seccion [Unreleased] ### Corregido EXISTENTE (sin encabezado duplicado) con el contrato de cardinalidad de Query y los cambios de CR-01/CR-02/CR-03; la enumeracion completa de breaking changes del milestone sigue siendo de la Fase 8 (08-04)
- [Phase 02]: 02-12: el fallback columns[0] del MERGE (familia ORA-38104) se documenta como NO corregido y con dueno; el render merge se documenta como fail-closed, no como mejora semantica del upsert (un upsert por PK autoincremental es inexpresable en MSSQL/Oracle por construccion)
- [Phase 02]: 02-12: ORA-38104 y la captura real de last_id quedan con dueno explicito Fase 4 / plan 04-02 / POOL-03, registrado en los TRES artefactos (deferred-items.md, ROADMAP.md, REQUIREMENTS.md); se elimina la afirmacion falsa de que no quedaba ningun item sin dueno
- [Phase 03]: 03-01: MIGRATIONS_TABLE es la fuente unica del nombre del ledger; los 6 adaptadores importan desde migration.py (adaptador->migration, sin ciclos). — Evita duplicar la constante en 6 ficheros y el ciclo de importacion.
- [Phase 03]: 03-01: rollback_migration borra la fila {name} y NUNCA registra una fila con sufijo de reversion; la fila pasa a rolling_back durante el down (D-06/D-07). — Re-aplicar tras el rollback vuelve a ejecutar el up; el ledger deja de mentir.
- [Phase 03]: 03-01: columna status en los 6 motores con DEFAULT 'applied' y ALTER TABLE idempotente verify-then-swallow (re-lee el catalogo; no matchea codigos de error del driver). — ADD COLUMN IF NOT EXISTS no es portable; el catalogo es la fuente de verdad.
- [Phase 03]: 03-01: S608 per-file-ignore para migration.py y tests/test_migrations.py (nombre de tabla validado con check_identifier; name/status ligados como parametros). — Mantiene noqa=0 y el patron ya usado por los 6 adaptadores.
- [Phase 03]: 03-01: se corrigio un I001 preexistente en tests/test_ci_harness.py (reproducido en un git-archive limpio de HEAD) que bloqueaba el gate de lint en una corrida sin cache. — El gate ruff check encino_orm tests debe salir 0; reordenamiento mecanico sin cambio de comportamiento.
- [Phase ?]: 03-03: CachedModel invalida por overrides de update/delete/upsert tras super() (post-commit), NO por el hook after_commit (no dispara en upsert/insert_many ni recibe la clave); save queda cubierto por delegacion (D-15).
- [Phase ?]: 03-03: insert_many(cache=...) invalida la clave de la PK del modelo presente en rows (mismo dominio que load()); sin cache= no invalida; _cache_key_for classmethod construye la clave sin instancia (D-16).
- [Phase ?]: 03-03: un fallo de cache.delete registra un warning de logging y NO propaga (fail-open, D-12); solo se invalida la clave afectada, sin namespace (D-11).
- [Phase 3]: 03-05: MemoryCacheBackend acotado con LRU (OrderedDict + move_to_end en get/set + popitem(last=False), max_size=1024 por defecto); el docstring declara el contrato dev/test-only (D-13/D-14). _store se anota OrderedDict[str, tuple[bytes, float|None]] porque anotar max_size activa el chequeo de cuerpo de mypy (el modulo no estaba en el ratchet).
- [Phase 03]: 03-02: TRANSACTIONAL_DDL es un dato por dialecto leido en runtime (no una rama); MySQL 8.0/MariaDB atomic DDL es atomico por sentencia, NO rollbackable (Pitfall 2).
- [Phase 03]: 03-02: el runner nunca llama db.commit(); usa async with db.transaction(), valido igual para adaptadores directos y PoolDb.
- [Phase 03]: 03-02: un pending que sobrevive se deja A PROPOSITO (nunca se re-ejecuta el DDL ni se asume applied); resolve_migration es la via humana de resolucion (D-02/D-05).
- [Phase 03]: 03-02: el parametro applied de resolve_migration significa 'debe quedar registrada como aplicada?', no 'corrio el SQL?' (D-17); ejecuta las cuatro acciones de D-08.
- [Phase 03]: 03-04: la guia documenta el contrato dev/test-only de MemoryCacheBackend (LRU max_size=1024) y la invalidacion local al proceso, post-commit y fail-open de CachedModel; remite a docs/design/5-security.md 5.4 para el mecanismo.
- [Phase 03]: 03-04: las entradas de CHANGELOG son aditivas y no prejuzgan la enumeracion completa de cambios incompatibles del milestone, que posee la Fase 8 (08-04).
- [Phase 03]: 03-06: el dominio de caché de CachedModel pasa a ser canónico (SOLO la PK de la fila); load() escribe siempre bajo la PK y update/delete/upsert resuelven la PK real de la fila afectada antes de invalidar (de la instancia si las claves de escritura son la PK; de la BD con un SELECT ligado y con scope si no). — Cierra CR-01: una escritura sin la PK en la instancia (id=None) ya no deja viva la entrada [id=1]; el residual inverso desaparece por construcción. Supersede la premisa de D-11 (la lectura no-PK deja de acierto en caché); D-12 y D-16 intactos.
- [Phase 03]: IN-01: se documenta el reintento del rollback en el docstring de resolve_migration y en el error de reconcile_migrations, en vez de automatizarlo (el helper no recibe la Migration ni el SQL del down; el ledger solo guarda el up). — Automatizarlo cambiaria la firma publica y el contrato D-05/D-17.
- [Phase 03]: WR-01: doble defensa con flag inserted (propiedad de la fila) + compare-and-delete {name, status: pending} (estado esperado). — El flag evita borrar la fila de otro proceso; el status evita borrar una fila applied por una promocion concurrente.
- [Phase 03]: Ronda 3: la revisión de 03-06/03-07 halló CR-01 multi-fila (una escritura por clave no-PK afecta N filas pero solo se invalidaba 1) y CR-02 (la clave de caché no se namespacea por scope(), permitiendo lectura/escritura cruzada de tenant). Se decide corregir AMBOS más los residuales WR-01/WR-02/WR-03 (opción "fix all") en 03-08/03-09/03-10. — DATA-03 promete "sin lecturas obsoletas" y el core value prioriza la seguridad de los datos; dejar un cruce de tenant conocido es inaceptable.
- [Phase 03]: Ronda 3: `_cache_key_for` incluye `current_scope().digest()`; sin scope la clave es idéntica a la anterior (compatible). La invalidación resuelve TODAS las PKs afectadas vía `search(columns=pk_cols, include_deleted=True)` y re-resuelve tras la escritura para acotar el TOCTOU (WR-02). — El namespace por scope es un cambio de formato de clave: se registra en CHANGELOG; entradas viejas quedan huérfanas hasta el TTL.
- [Phase 03]: Ronda 4 (SEC-01): `Model.update`/`delete` añaden el fragmento de `current_scope()` al WHERE del DML componiendo una `Query` nueva en la capa `Model` (`_scoped_dml`), sin tocar builders ni adaptadores. — Cierra CR-R3-01; sin scope el DML es byte-idéntico (sin churn de snapshots).
- [Fase 4 prep]: El job `engine-heavy` fallaba SIEMPRE por cobertura: corre solo `test_mssql.py`+`test_oracle.py` (35% parcial) contra el `fail_under=82` global de `[tool.coverage.report]`. Se añade `--cov-fail-under=0` a esa pata; el piso real lo aplica el job `coverage` sobre la unión. — Los 46 tests ya pasaban; el fallo era del gate de cobertura parcial, no de los motores.
- [Fase 4]: La revisión de la fase halló 2 Critical en POOL-03: `Model.insert` interpolaba el campo `"id"` en `RETURNING`/`OUTPUT INSERTED` (rompe PKs renombradas con `Column(name=...)` en PostgreSQL/MSSQL/Oracle) y un INSERT ignorado devolvía el `lastrowid` de la inserción anterior (asignaba a `self.id` el id de OTRA fila). Fix: `returning = self._col("id")` y `rowcount == 0` → `None` en SQLite/MySQL. Además se endureció el pool: ownership en `release()`, validación `min_size <= max_size`, cierre de `keep` si `close()` corre durante el reaper, sondeo `in_transaction()` guardado en los caminos de error, `session()` captura `BaseException`, `execute` delega en `_run`, y `PooledConnection` se re-exporta.
- [Phase 03]: 03-09: la compensación pre-DDL borra por IDENTIDAD de fila ({id: ledger_id}, capturada best-effort con last_id() tras el INSERT) cuando el motor la expone; fallback {name, status: pending} si last_id() falla (no por motor: Oracle usa RETURNING id INTO y sí lo expone), residual asignado a Fase 4 / POOL-03. — {name, status} no prueba propiedad: borraría la fila pending que otro runner re-publicó tras el rollback (WR-01 residual).
- [Phase 03]: 03-09: la compensación va en su propio try/except con logger.warning y el raise exterior re-lanza SIEMPRE la excepción raíz del DDL (IN-01); el test de IN-02 verifica comportamiento (la fila deja de ser ambigua) en vez de un substring de __doc__. — Un fallo de la compensación no debe reemplazar el error original; una aserción sobre texto de docstring es frágil y no prueba el efecto.
- [Phase ?]: 03-10: docs alineados con la invalidación multi-fila, el namespace de scope y el residual TOCTOU; CHANGELOG registra el cambio de formato de clave y los fixes CR-01/WR-01 residual. Cierra WR-03.
- [Phase 03]: 03-11: el scope() se aplica al WHERE del DML de `Model.update`/`delete` (helper `_scoped_dml` sobre el `Query` del builder, con `_shift_placeholders` y params ligados) SOLO cuando `current_scope() is not None`, leído dentro del closure transaccional; sin scope el `Query` es byte-idéntico. La composición es de la capa `Model`: no se tocan los builders ni los seis adaptadores (snapshots intactos). — Cierra CR-R3-01/SEC-01 (una clave no-PK ya no cruza tenants) y WR-R3-01 por construcción (la sonda de `CachedModel` y la escritura ven el mismo conjunto de filas).
- [Phase 03]: 03-12: `_union` deduplica por huella hashable `tuple(sorted((k, repr(v)) for k, v in item.items()))` y los overrides `update`/`delete`/`upsert` invalidan vía un helper `_invalidate_after_write` que envuelve `_union` en `try/except` y degrada a la concatenación de sondas. — Cierra WR-R3-02: una PK no hashable (`list`/`dict`, admitida por pydantic y `_from_db`) ya no propaga `TypeError` después del commit, preservando la garantía fail-open D-12. `repr` mantiene el dedupe de PKs escalares.
- [Phase 03]: 03-13: docs veraces tras la ronda 4 — el overclaim 'escritura cruzada cerrada' se reformula (la caché deja de HABILITAR una escritura cruzada; el cierre real es SEC-01); se documenta que escritor y lector deben correr bajo el mismo scope() (WR-R3-04) y se registran los residuales de upsert (claves de conflicto globales) y de huella determinista (IN-R3-03); la nota de last_id() deja de nombrar a Oracle (IN-R3-01).
- [Phase 04]: 04-01: `PooledConnection` es `@dataclass(eq=False)` (no frozen) — hash por identidad para vivir en `_connections`/`_checked_out`; un dataclass con `eq=True` sería unhashable.
- [Phase 04]: 04-01: `acquire()` reserva `_size` ANTES del `await` y la devuelve en `except BaseException`; el test de overshoot se reescribió con `EventBarrier.release()` + `acquire(timeout=0.5)` porque con `parties=5` solo `max_size` tareas alcanzan `connect()` (el test literal del plan se colgaría). Evidencia RED `_size == 5` → GREEN `_size == 2`.
- [Phase 04]: 04-01: `needs_check = idle_timeout is None or handle.is_idle_for(idle_timeout)` preserva la semántica de `_needs_check` (con `idle_timeout=None` siempre se comprueba liveness); `is_idle_for(None)` devuelve `False` como pedía el plan.
- [Phase 04]: 04-01: `_current_connection` guarda el handle y `resolve_db()` desenvaina `.driver` (Pitfall 8); `session()` NO fija `_current_connection` (Open Question 2) y `last_id()` fuera de transacción devuelve 0 (Open Question 3).
- [Phase 04]: 04-05: pytest-timeout==2.4.0/pytest-repeat==0.9.4 pinados tras aprobacion humana explicita; upstream canonico github.com/pytest-dev/... verificado en PyPI.
- [Phase 04]: 04-05: timeout global DESACTIVADO (timeout = 0); el limite va por marker SOLO en los tests de barrera, para no matar el job engine-heavy (Oracle 60-120 s). --timeout-method=signal en los jobs test y engine-heavy.
- [Phase 04]: 04-05: tests/_pool_helpers.py ofrece EventBarrier 3.10-safe (solo asyncio.Event) + FakeDb/BlockingFakeDb con execute_insert; los ficheros de test existentes NO se migran aqui (esa migracion es de 04-06).
- [Phase 04]: 04-02: Query.returns_id/id_column son metadata de ejecucion (excluidas de __eq__/__hash__); build_insert(returning=) es opt-in y el SQL sin returning es byte-identico (snapshots y golden strings regenerados y revisados).
- [Phase 04]: 04-02: el builder fija returns_id=False en la rama MERGE+replace; MERGE ... RETURNING no existe en Oracle (ORA-00933), asi que el fix ORA-38104 solo da EJECUTABILIDAD y Model.insert(replace=True) sigue devolviendo 0 sin asignar self.id.
- [Phase 04]: 04-02: el DeprecationWarning de last_id() vive en un unico helper (base._warn_last_id_deprecated) y se habilita en la Task 3, tras migrar los 2 llamadores internos y los 29 call sites de test (B2), para que filterwarnings=['error'] no vea un warning sin migrar.
- [Phase 04]: POOL-04: orden safety-critical respetado — commit/rollback explícito en execute/_run antes de invertir release() a rollback por defecto — Correction #5; TestPoolAutocommit/TestPoolStandaloneCommit verdes sin editar
- [Phase 04]: 04-04: el reaper perezoso NO reencola dentro del bucle de drenado (el sketch del plan producia un bucle infinito); recolecta keep/to_close y reencola/cierra despues. — Reencolar un handle no reapeado mientras se sigue drenando lo devuelve a get_nowait() y la cola nunca se vacia (reproducido con timeout).
- [Phase 04]: 04-04: connect() reabre el pool (_closed=False); release() cierra handles con pool cerrado o generacion obsoleta; _generation se asigna por handle y se incrementa en close(). — Sin el reset, un connect() tras close() cerraria todos los handles nuevos al liberarse; la generacion (A6) invalida los obsoletos tras close/reconnect.
- [Phase 04]: 04-04: el ratchet de mypy de encino_orm.pool NO se retira (5 errores de tipado: 3 var-annotated + 2 override sobre atributos escribibles de Db); PT011/B017 diferidos y sin piso de cobertura para pool.py. — Los override exigen tocar base.py (fuera de alcance) y # type: ignore inline esta prohibido; el residual queda documentado para que el ratchet no mienta (Open Questions 4/5).
- [Phase 04]: 04-06: los tests de admision liberan los handles (acquire -> sleep(0) -> release) y llaman `barrier.release()` explicitamente, porque con la reserva-antes-del-await solo `max_size` tareas alcanzan `connect()` y la barrera `parties=5` nunca se libera sola; se asserta `len(set(handles)) == max_size` (handles reutilizados), no 5 handles distintos (inalcanzable con `max_size=2`). — Evita un test colgante y afirma la propiedad real de capacidad (T-04-06-01).
- [Phase 04]: 04-06: POOL-07 cubierto con 6 tests deterministas (carrera de admision, ids concurrentes sin cruce, commit standalone visible, `execute_insert` en transaccion, variante `stress` con `repeat(5)` y barrera single-use); el valor RED historico (`_size == 5`, cruce de ids) queda en la caracterizacion de Fase 1 porque `files_modified` prohibe editar `pool.py`. — Los tests AFIRMAN el comportamiento final; sin editar los ficheros de 04-04.
- [Phase 05]: 05-01: `is_disconnect_error` por adaptador con senal TIPADA (errno/SQLSTATE/tipo/`.full_code`); el substring solo refuerza el caso MSSQL `HY000`. Los codigos de lock (1213/1205, 1205/1222, ORA-60/54/8177, `locked`/`busy`) quedan explicitamente FUERA para no romper `retry()`; la exclusion mutua se prueba por motor (Success Criterion 1). — Una clasificacion cruzada romperia el reintento por deadlock y expondria el Core Value a duplicar una escritura.
- [Phase 05]: 05-01: MSSQL extrae el mensaje aceptando `args[1]` tupla (dobles) o string (pyodbc real); Oracle usa `from oracledb import exceptions` dentro de `real_oracle_disconnect` porque `oracledb.exceptions` no se expone como atributo tras `import oracledb`. — Ambas formas reales verificadas contra los drivers instalados; los drivers opcionales siguen sin importarse a nivel de modulo.
- [Phase 05]: 05-01: `FakeResilientDb` define los metodos publicos con un puente `hasattr(Db, "_with_reconnect")`: en 05-01 (publicos aun abstractos) delegan en los privados y en 05-02 reenvian a `super()` para no saltarse el template method. — Satisface el criterio de instanciabilidad de 05-01 y deja el helper operativo para 05-02/03/04 sin editar la infraestructura.
- [Phase 5]: 05-02: _with_reconnect reconecta exactamente una vez y solo fuera de tx; política A2 (lecturas re-ejecutan, escrituras pre-ejecución ejecutan, mid-statement reconectan y relanzan, dentro de tx relanzan). — Un reintento ciego de una escritura ambigua duplicaría datos en silencio (Core Value); el guard in_transaction() y la distinción pre-ejecución vs mid-statement lo impiden.
- [Phase 05]: 05-03: `pre_ping`/`max_connection_lifetime` son opt-in (defaults `False`/`None`), se fijan por instancia desde `connect(**kwargs)` y `_resilience_opts` hace pop ANTES de guardarlos/reenviarlos al driver. El reciclado mide EDAD con `time.monotonic()` y `_maybe_recycle` reconecta INMEDIATAMENTE si la sonda falla; el chequeo es perezoso (sin daemon) y `pool.py` queda intacto. — `pre_ping` añade un round-trip por operación, así que su coste debe ser opt-in; la inactividad y el reciclado a nivel de pool son del reaper de Fase 4 / RELI-03 (v2).
- [Phase 05]: la taxonomia es aditiva y _translate_exception cortocircuita el lock PRIMERO (devuelve el original sin traducir) para que retry() siga reconociendolo; el resto se traduce a ConnectionLostError/OperationalError/IntegrityError/ProgrammingError. — Traducir un lock romperia el reintento por deadlock (Pitfall 3 / T-05-04-01); ConnectionLostError hereda de ConnectionError y los tres QueryError-derived pasan a mapearse a HTTP 400.
- [Phase 05]: chaining raise ... from exc adoptado como desviacion DELIBERADA de la convencion del repo, documentada en docs/engines.md y CHANGELOG.md. — La traduccion REEMPLAZA el tipo de excepcion; perder la causa del driver destruiria el diagnostico (ASVS V7 / T-05-04-05).
- [Phase 05]: el ratchet de mypy retira base/oracle/mysql/mssql tras corregir sus residuales sin # type: ignore; encino_orm.pool queda intacto. — base:109 (last_exc) y mysql:69 (args) se arreglaron en Task 1; oracle out.getvalue() se corrige con guard out is not None en Task 3; pool es residual de Fase 4.
- [Phase 06]: ConnectionRegistry con estado de instancia reemplaza el global mutable _default_db; resolve_db() sin argumentos conserva el default del _registry de modulo — Dos apps/tenants en el mismo proceso dejan de pisarse; la firma retrocompatible evita romper model/model.py y el barrel (Pitfall 11)
- [Phase 06]: El DeprecationWarning de los shims set_default_db/get_default_db vive SOLO en los shims y aterriza en el MISMO commit que la migracion de tests/test_singleton.py (W1) — filterwarnings=[error] convierte el camino caliente en fallo de suite (Pitfall 1); ningun commit intermedio queda rojo
- [Phase 06]: El import perezoso de pool dentro de ConnectionRegistry.resolve() usa from . import pool — Preserva el contrato de importacion diferida y satisface el grep de control del plan, cuyo regex ^\s* tambien matcheaba el import intencional
- [Phase 06]: SecurityConfig es un @dataclass(frozen=True) en encino_orm/security/config.py que solo importa stdlib — El value object inmutable reemplaza los globales mutables; los guards cierran sobre la config y mutar guard.SECRET/GET_DB deja de cambiar 200/401/403 (Success Criterion 2) y el nucleo no adquiere dependencia dura de fastapi/PyJWT
- [Phase 06]: security_dependencies(config) devuelve (get_current_user_factory, require_factory) con Annotated[...] en la inyeccion — B008 deja de aplicar y el per-file-ignore de guard.py es retirable por 06-05; fastapi sigue importandose dentro de cada factoria (importacion diferida)
- [Phase 06]: El DeprecationWarning del fallback legacy se emite en guard.py DESPUES de validar la config — Sin globales lanza AuthenticationError sin avisar (fail-closed bajo filterwarnings=[error]); el mensaje nombra los globales y su reemplazo, nunca el valor del secreto (Pitfall 12)
- [Phase 06]: La constante SECRET del test se renombra a _SIGNING_MATERIAL y Depends(...) migra a Annotated[...] — S105 y B008 quedan retirables por 06-05 (probe ruff --isolated en verde)
- [Phase 06]: El snapshot OpenAPI (tests/__snapshots__/test_http_openapi.ambr) se captura y commitea CONTRA el exec() vigente (ca20a32) ANTES del rewrite (fa76bcf); Task 2 corre sin --snapshot-update y exige diff cero — Un snapshot capturado despues bendice la regresion y vacia el Criterio de Exito 3 (T-06-03-01/Pitfall 2)
- [Phase 06]: _build_path_handler construye closures get/put/delete con inspect.Signature en __signature__ (PK -> data/physical -> db=Depends(get_db) sin annotation); handler.__name__/__qualname__ = 'handler' preserva el operationId — FastAPI lee __signature__ tal cual; sin exec() no hay S102 ni __globals__ fragil (Pitfalls 3/4/5)
- [Phase 06]: create/list_ migran a Annotated[object, Depends(get_db)] (list_ con default None por seguir a parametros con default) — Elimina los 2 B008 de routes.py que 06-05 retirara; el OpenAPI byte-identico lo cubre el snapshot
- [Phase 06]: La SDL GraphQL (tests/__snapshots__/test_graphql_namespace.ambr) se captura y commitea CONTRA el exec() vigente (e1fbcd3) ANTES del rewrite (66671d0/d98ca92); las Tasks 2/3 corren sin --snapshot-update y exigen diff cero — Un snapshot capturado despues bendice la regresion y vacia el guardian de CFG-03 GraphQL (T-06-04-01/Pitfall 2)
- [Phase 06]: _pk_resolver construye closures get/update/delete con inspect.Signature en __signature__ (info + PKs + data para update); resolver.__name__/__qualname__ = 'resolver' y la coercion id=int(id) va en el cuerpo (_cast) — Strawberry deriva los argumentos GraphQL de la firma; sin exec() no hay S102 ni __globals__ fragil
- [Phase 06]: build_schema registra un modulo sintetico por build (types.ModuleType + sys.modules) y ya no muta el namespace de encino_orm.graphql.schema con setattr — Dos builds sucesivos dejan de acumular tipos y de apuntar al tipo del ultimo build (Success Criterion 4)
- [Phase 06]: El modulo sintetico por build NO se borra en un finally: los filtros autorreferentes resuelven sus LazyType en EJECUCION (LazyType.resolve_type no cachea), asi que se libera con weakref.finalize cuando el schema se recolecta — El del sys.modules del plan rompia { agentes(filter: ...) } con ModuleNotFoundError; el fallback autorizado (conservar el modulo) se endurece atando su vida al schema (evidencia en 06-04-SUMMARY)
- [Phase 06]: El test de no-mutacion del namespace usa un modelo sonda (Sonda) que ningun otro build registra — Con [Region, Agente] la asercion pasaba en vacio porque tests previos ya habian mutado el modulo (orden de ejecucion)
- [Phase 06]: 06-05: las entradas del ratchet mypy asignadas a Fase 6 SE CONSERVAN con la causa reescrita (http.routes 5, security.guard 2, http.parsing 2, graphql.* 7, security.models 4 errores residuales de tipado); retirarlas deja mypy rojo y el plan autoriza el residual con causa — Los per-file-ignores S102/B008 SI se retiran (probe ruff --isolated limpio), pero los residuales de tipado no son artefacto del exec() y no se corrigen sin # type: ignore inline (prohibido)
- [Phase 06]: 06-05: el cap de PyJWT sube a >=2.8,<2.15 (2.14.0) con uv lock --upgrade-package; uv audit (OSV) y pip-audit (PyPA) limpios sin ignores y tests/test_security.py verde, de modo que se retiran los 5 ignores GHSA de ci.yml — uv lock a secas conserva la version fijada aunque el rango se amplie; el upgrade explicito es necesario para que el fix entre. Fail-closed: si algo fallara se restaura el cap y se conservan los ignores
- [Phase 06]: 06-05: docs/trust-boundaries.md documenta Filter.raw/Query/db.fn.* con ejemplos SEGURO/INSEGURO y tests/test_trust_boundaries.py congela que los parsers HTTP/GraphQL no pueden emitir Filter.raw (conjuntos cerrados de operadores) — CFG-05 Success Criterion 5; la prosa cita anchors reales y el test impide que la pagina desaparezca o se vacie
- [Phase 07]: PERF-01 se entrega con `build_multi_insert`/`_placeholders_from` multi-VALUES por dialecto (Oracle `INSERT ALL` con `multi_values=False`) y `copy_table` batch en `encino_orm/transfer.py` con chunk `batch_size = min(MAX_PARAMS // n, MAX_ROWS)` (público, medido por el canario LR-02). Degradación de fallback post-review: `target_cols == []` emite fila default POR DIALECTO (`_default_row_sql`: `DEFAULT VALUES` en sqlite/postgres/mssql, `() VALUES ()` en mysql/mariadb, `(pk) VALUES (DEFAULT)` en oracle) — regresión MR-01; `per_row == 0` (n > MAX_PARAMS) degrada a insert de fila única (LR-01); `build_multi_insert` valida longitud por fila fail-closed (HR-01), sin cambio de API — Sonda cross-engine (4 ficheros: mysql/postgresql 500 filas, mssql/oracle 100 filas) pasa local; MSSQL usa `preserve_ids=False` porque `INT IDENTITY` rechaza IDs explicitos sin IDENTITY_INSERT (driver no lo habilita). PERF-02..04 cerradas y verificadas (07-VERIFICATION.md PASS 4/4; 07-REVIEW.md resuelto).
- [Phase 07]: El benchmark generativo `test_multi_insert_gen_floor` calibra su piso en el MISMO commit (floor 780 = 0.6× de la mediana local 1,306 ops/s para 200 filas × 5 cols) en vez del 900 literal del RESEARCH, porque RESEARCH media sobre un harness distinto (1,516 vs 1,306) — PRIMER run de CI recalibra ±20%; el smoke asserta `len(params) == rows*cols` y la ausencia de `INSERT ALL` en SQLite.
- [Phase 07]: Evidencia >=2× medida contra el commit pre-batching `0b5696b` via worktree temporal: 10,000 filas × 5 cols → 48,691 filas/s (0.2054s) vs 5,823 filas/s (1.7173s) = **8.4×**; el profiler `--scale=1` (2,000×2, sqlite :memory:) da 1.004× porque el round-trip es despreciable a esa escala (documentado como esperado en SUMMARY).
- [Phase 07]: Oracle `LIMITS["oracle"]` (65535 binds) mantiene "NO verificado empiricamente": la sonda de 100 filas (600 binds, INSERT ALL) prueba el camino, no el techo — el throttling termico de este host colapsa lotes de 500 filas a ~240-450 ops/s, por eso la sonda Oracle/MSSQL es de 100 filas.
- [Phase 07]: Primera corrida del job `benchmarks` en CI (2026-09-19): batch_sizing mide ~2,65M (sigma 33,9K) en el runner ubuntu 2-vCPU frente a 10,5M locales — la unidad es aritmetica pura y su throughput escala con la frecuencia del core, no con el ancho de banda Python (las otras 5 unidades pasan sus pisos locales). Su piso se recalibra a 1,58M (2,65M x 0.6) en el MISMO commit (`ebb17e3`), segun la disciplina de calibracion del plan 07-02; el job resuelve ademas el error de coleccion que producia `uv sync --group dev` (sin extras http/security/graphql) al importar test_graphql.py et al. en la recoleccion: ahora ejecuta solo `tests/test_benchmarks.py` (`eee91c8`). Segunda corrida (5ebc844): CI 10/10 jobs verde, incl. Benchmarks y Lint.

### Pending Todos

None yet.

### Blockers/Concerns

- **Phase 1 gate on Phase 4:** CI-09 pool characterization tests must exist before any POOL refactor. If Phase 1 is compressed, this item cannot be.
- **`ARCHITECTURE.md` is wrong** about PostgreSQL `lastval()` being transaction-scoped (it is session-scoped). Correct it before Phase 4 planning. See ROADMAP.md "Research Corrections".
- **POOL-04 is the milestone's highest-risk change:** flipping release-from-commit to release-from-rollback can silently drop standalone writes. The three-step sequence in ROADMAP.md must be followed.
- **Open research flags:** Phase 2 (syrupy/testcontainers topology), Phase 4 (`PooledConnection` + `last_id` API contract), Phase 5 (per-driver disconnect classification), Phase 6 (`__signature__`, GraphQL namespace), Phase 7 (per-dialect parameter ceilings).
- **Resuelto en 06-05:** los 5 avisos GHSA de PyJWT 2.12.1 quedaron saldados al subir el cap a `>=2.8,<2.15` (2.14.0) con `uv audit`/`pip-audit` limpios y sin ignores; `ci.yml` ya no allowlistea avisos.
- **Residual de tipado (06-05):** las entradas del ratchet mypy de `http.routes` (5), `security.guard` (2), `http.parsing` (2), `graphql.*` (7) y `security.models` (4) SE CONSERVAN con causa escrita: no son artefacto del `exec()` y no se corrigen sin `# type: ignore` inline (prohibido). Candidato a una fase de calidad posterior.
- **Gap de supply-chain (06-05):** el `pip-audit` del job `deps` no audita los extras opcionales (`uv export` sin `--all-extras`), por lo que no cubre `PyJWT`/`fastapi`/`strawberry`. Registrado en `.planning/phases/06-config-optional-layer-hygiene/deferred-items.md`.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Performance | DATA-07 — `Query` placeholder caching (TS-37) | Deferred to v2, pending profiler evidence | 2026-09-17 (roadmap) |
| Observability | OBSV-01…05, RELI-01…05, DATA-05/06 | Deferred to 0.3.x / 0.4+ | 2026-09-17 (roadmap) |

## Session Continuity

Last session: 2026-09-19T20:00:25.473Z
Stopped at: Phase 8 context gathered
Resume file: .planning/phases/08-release-0-3-0/08-CONTEXT.md
