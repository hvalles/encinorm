# Phase 3: Data Correctness - Context

**Gathered:** 2026-09-18
**Status:** Ready for planning

<domain>
## Phase Boundary

**Migraciones y caché dejan de mentir.** Una migración revertida puede re-aplicarse, un `migrate()` fallido deja un estado **reconciliable** (no un esquema cambiado sin registro, ni un registro sin esquema), y `CachedModel` **nunca** sirve una fila obsoleta tras una escritura.

Cubre **DATA-01…DATA-04**. Módulos: `encino_orm/migration.py`, `encino_orm/model/cached.py`, `encino_orm/model/cache_backend.py`, y el `migrate()`/`_ensure_migrations_table()` de los 6 adaptadores.

**No** entrega: refactor del pool (Fase 4), resiliencia/reconexión (Fase 5), validación de identificadores (Fase 2, ya cerrada).

</domain>

<decisions>
## Implementation Decisions

### Reconciliación de migraciones (DATA-02)
- **D-01:** **Máquina de estados de 2 fases.** La tabla de migraciones gana una columna `status` con valores `pending` / `applied` / `rolling_back`. `migrate()` inserta la fila como **`pending` ANTES** de ejecutar el DDL y la promueve a `applied` **después**. En motores con DDL transaccional (PostgreSQL/SQLite/SQL Server) la fila y el DDL van en la misma transacción, así que un `pending` nunca sobrevive; la maquinaria es inerte allí.
- **D-02:** **Un `pending` es ambiguo → fallo ruidoso.** Al reconciliar, un `pending` significa "no sabemos si el DDL corrió". Se lanza **`MigrationError` incluyendo el SQL de la migración y la instrucción de resolución**. **NUNCA** se re-ejecuta el DDL automáticamente (peligroso con DDL no idempotente) ni se asume `applied` (eso sería el registro mintiendo, justo lo que la fase elimina).
- **D-03:** **Dónde corre la reconciliación:** una comprobación dentro de `migrate()` (antes de aplicar cualquier migración) **y** una API pública `reconcile_migrations(db)` para el arranque de la aplicación. Cubre al que migra y al que solo arranca.
- **D-04:** **La columna `status` existe en los 6 motores, uniforme.** Sin ramas de dialecto en el runner. OJO: `_ensure_migrations_table` usa `CREATE TABLE IF NOT EXISTS`, que **no** añade columnas a una tabla ya existente → hace falta un **`ALTER TABLE` idempotente** (detectar la columna en el catálogo y añadirla solo si falta) para instalaciones existentes.
- **D-05:** **Resolución humana con un helper:** `resolve_migration(db, name, *, applied: bool)`. El humano responde una sola pregunta —"¿corrió el SQL?"— y el helper **infiere la acción** del estado actual de la fila (ver D-08). No se le pide escribir SQL a mano.

### Ledger de rollback (DATA-01)
- **D-06:** **`rollback_migration` ejecuta el `down` y BORRA la fila `{name}`; NO registra `{name}:down`.** El `down` no es una migración aplicada del usuario, así que `migrate_status()` sigue mostrando solo migraciones realmente aplicadas. Re-aplicar funciona porque `{name}` ya no existe. (`down is None` sigue siendo `MigrationError`, como hoy.)
- **D-07:** **Estado `rolling_back` propio durante el `down`.** La fila `{name}` pasa a `rolling_back` antes de ejecutar el `down` y se borra después. Un estado propio (en vez de reutilizar `pending`) es lo que permite que la reconciliación **sepa la dirección** y dé instrucciones específicas.
- **D-08:** **Tabla de resolución de `resolve_migration`** (acción inferida del estado + la respuesta del humano):

  | Estado de la fila | `applied` (¿corrió el SQL?) | Acción |
  |---|---|---|
  | `pending` | `True` | Marcar `applied` (el DDL sí corrió) |
  | `pending` | `False` | Borrar la fila (re-migrar) |
  | `rolling_back` | `False` | Borrar la fila (el `down` sí corrió) |
  | `rolling_back` | `True` | Restaurar `applied` (el `down` no corrió) y reintentar el rollback |

### Invalidación de caché (DATA-03)
- **D-09:** **Invalidar en TODAS las rutas de escritura:** `update`, `delete`, `save`, `upsert` e `insert_many`. `insert` puro **no** invalida (no había fila cacheada para esa clave). Se aplica aquí la **lección de Fase 2**: un "choke point" declarado no lo es hasta barrer todas las posiciones de escritura.
- **D-10:** **Store-then-invalidate.** Se escribe en la BD y **solo tras el commit** se invalida la caché, enganchado al hook `after_commit` que `_transactional` ya dispara. Si la invalidación falla, el peor caso es una lectura obsoleta acotada por el TTL — nunca se pierde el dato. Es el patrón cache-aside documentado.
- **D-11:** **Solo la clave afectada**, sin invalidación de namespace. `CachedModel.load()` solo cachea por clave de PK (`_cache_key(keys)`), así que no existen entradas por filtro que haya que barrer.
- **D-12:** **Fallo de invalidación = log warning y continuar (fail-open).** La escritura ya se commiteó; propagar el error daría al llamador un fallo sobre una escritura exitosa, y el dato quedaría inconsistente igualmente hasta el TTL.

### Cota de `MemoryCacheBackend` (DATA-04)
- **D-13:** **LRU con `max_size=1024` por defecto.** `get` y `set` mueven la clave al final (`OrderedDict.move_to_end`); al insertar con el store lleno se desaloja la entrada menos recientemente usada. 1024 no rompe los tests existentes.
- **D-14:** **Contrato dev/test documentado** en el docstring y en los docs: el backend en memoria es para desarrollo y pruebas, no para producción. `RedisCacheBackend` no cambia (Redis ya acota y expira).

### the agent's Discretion
- Si añadir pisos de cobertura para `migration.py`/`cached.py`/`cache_backend.py` en `tools/ci/check_coverage_floors.py` (el mecanismo ya existe desde Fase 2).
- La forma exacta del `ALTER TABLE` idempotente por dialecto (consulta al catálogo + `ADD COLUMN`).
- Nombres exactos y firma de los métodos nuevos (`reconcile_migrations`, `resolve_migration`, la columna `status`).
- Si `insert_many` invalida por lote o clave a clave.
- Si `migrate_status()` cambia de forma al exponer `status`.

### Enmiendas tras la investigación (03-RESEARCH.md)
La investigación contradijo dos decisiones ya tomadas. Se enmiendan aquí; `03-RESEARCH.md` es la referencia técnica.

- **D-15 (enmienda a D-10 — el hook `after_commit` NO sirve):** la investigación verificó en el código que `after_commit` **no se dispara** para `upsert` (tiene su propio `retry`/transacción, `model/model.py:648-652`) ni para `insert_many` (su propio `db.transaction()`, `:572`), y que **no recibe ni la acción ni la clave**. **Mecanismo corregido:** `CachedModel` **sobreescribe `update`, `delete` y `upsert`** e invalida la clave tras el retorno de `super()` (que ya es post-commit); `save` queda cubierto por delegación. El principio de D-10 (store-then-invalidate, solo tras el commit) se mantiene; cambia el punto de enganche.
- **D-16 (enmienda a D-09 — `insert_many`):** `insert_many` es un `classmethod` sin acceso a la instancia `_cache`. **Gana un parámetro opcional `cache=`**; cuando se pasa, invalida las claves afectadas. Sin `cache=`, no invalida (documentado, consistente con `insert` puro). El resto de D-09 no cambia.
- **D-17 (enmienda a D-08 — semántica del parámetro):** el parámetro `applied` significa **"¿debe quedar la migración como aplicada?"**, no "¿corrió el SQL?". Con ese significado la tabla de D-08 queda coherente tal cual (incluida la fila `rolling_back`+`True` → restaurar `applied`); solo se corrige el encabezado que decía "¿corrió el SQL?".

**Restricciones técnicas verificadas por la investigación (el planner DEBE respetarlas):**
- El runner **no puede llamar `db.commit()`**: `PoolDb.commit()` lanza `ConnectionError` por diseño (`pool.py:245-248`). Usar `async with db.transaction()`, que funciona igual en adaptadores directos y en pools. En MySQL/MariaDB/Oracle el commit implícito del DDL es lo que publica la fila `pending`.
- `ALTER TABLE ADD COLUMN IF NOT EXISTS` **no es portable** (solo PostgreSQL y MariaDB). Receta: consultar el catálogo con el `columns_of()` que ya existe en los 6 adaptadores + `ADD ... NOT NULL DEFAULT 'applied'` + guard "verify-then-swallow" que **re-lee el catálogo** en vez de matchear códigos de error del driver.
- **Pitfall 8 (teatro de seguridad) es evitable y testeable:** la ambigüedad es real (MySQL/MariaDB commitean implícitamente *antes* del DDL), así que el test de inyección de fallo debe asertar que `reconcile_migrations` **detecta** el `pending`, no que sea imposible.


### Folded Todos
Ninguno — no había todos pendientes para esta fase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Contexto de proyecto y alcance
- `.planning/PROJECT.md` — Core value y límites del milestone
- `.planning/REQUIREMENTS.md` — Esta fase cubre **DATA-01…DATA-04**
- `.planning/ROADMAP.md` — Sección de Fase 3 (4 planes: 03-01…03-04), **Restricciones Duras de Ordenamiento** y **Research Corrections**
- `.planning/STATE.md` — Posición actual y blockers

### Contexto de fases previas (decisiones que aplican aquí)
- `.planning/phases/02-dialect-seam-engine-parity/02-CONTEXT.md` — Decisiones D-01…D-06 (Query inmutable, allowlist estricta)
- `.planning/phases/02-dialect-seam-engine-parity/02-VERIFICATION-FINAL.md` — La **lección del choke point** (D-09 se apoya en ella) y la lista de residuales con dueño
- `.planning/phases/01-safety-net-ci-gates-test-infrastructure/01-CONTEXT.md` — D-04/D-06 (pisos de cobertura) y D-09

### Investigación (decisiones y trampas)
- `.planning/research/ARCHITECTURE.md` — Patrones de pool/transacción/ciclo de vida; el patrón `transactional_ddl` y reconciliación
- `.planning/research/PITFALLS.md` — **Pitfall 8** (migraciones atómicas como teatro de seguridad) y **Pitfall 17** (cachés sin límite)
- `.planning/research/SUMMARY.md` — Sección de Fase 3: `transactional_ddl` por dialecto y cache-aside (patrón de Microsoft), sin research adicional

### Mapa del código
- `.planning/codebase/CONCERNS.md` — El bug de rollback de migraciones, `migrate()` no atómico, `CachedModel` que nunca invalida, caché en memoria sin límite
- `.planning/codebase/TESTING.md` — Patrón skip-guard, markers, tests por motor
- `.planning/codebase/CONVENTIONS.md` — Estilo, comentarios en español, naming

### Código y configuración vivos
- `encino_orm/migration.py` — `Migration`, `apply_migration`, `rollback_migration:25-29` (el bug), `migrations_from_dir`
- `encino_orm/model/cached.py` — `CachedModel.load():22-47` (cachea por PK), `_cache_key:17-20`; **cero llamadas a `cache.delete`**
- `encino_orm/model/cache_backend.py` — `CacheBackend` Protocol (`delete` en `:8`), `MemoryCacheBackend:11-32` (sin cota), `RedisCacheBackend:35-59`
- `encino_orm/model/model.py` — `_transactional` y su hook `after_commit` (punto de enganche de D-10); `save`/`upsert`/`insert_many`/`update`/`delete`
- `encino_orm/sqlite.py` — `migrate():222-234`, `_ensure_migrations_table():241-250`
- `encino_orm/mysql.py` — `migrate():248-260`, `_ensure_migrations_table():267-276` (DDL con commit implícito)
- `encino_orm/{mariadb,postgresql,mssql,oracle}.py` — Los otros cuatro `migrate()`/`_ensure_migrations_table()`
- `pyproject.toml` — `[tool.coverage]`, `[tool.pytest.ini_options]`
- `tools/ci/check_coverage_floors.py` — El gate de pisos por módulo (Fase 2)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`CacheBackend.delete()` ya existe en el Protocol** (`cache_backend.py:8`) y en ambos backends — la interfaz está lista, solo falta que alguien la llame. La invalidación no requiere ampliar el Protocol.
- **El hook `after_commit` de `_transactional`** (`model/model.py`) ya se dispara tras el commit: es el punto de enganche natural para D-10 sin inventar un mecanismo nuevo.
- **`_MIGRATIONS_TABLE`** ya existe en los 6 adaptadores con `name UNIQUE`, `applied_at`, `sql_text`; la columna `status` se suma ahí.
- **`tools/ci/check_coverage_floors.py`** (Fase 2) ya aplica pisos por módulo sobre `coverage json` — el patrón está listo si se decide cubrir los módulos de esta fase.
- **Fakes a mano + `monkeypatch`** (`tests/test_pool.py`, `tests/test_pool_characterization.py`) son el patrón aceptado para dobles; preferirlos a `unittest.mock`.

### Established Patterns
- **`migrate()` es idempotente por nombre**: consulta `WHERE name = {0}` y retorna si ya existe. La máquina de estados debe preservar esa idempotencia.
- **Los 6 adaptadores duplican `migrate()`/`_ensure_migrations_table()`** (Fase 2 dejó los *builders* centralizados en `dialects/`, pero la lógica de migraciones sigue copiada). Cualquier cambio debe aplicarse a los seis o centralizarse.
- **DDL con commit implícito** en MySQL/MariaDB/Oracle vs transaccional en PostgreSQL/SQLite/SQL Server — el eje de DATA-02.
- **`_set_private` / `object.__setattr__`** para el estado privado de `Model` (`model/model.py:79`) — `CachedModel` lo usa para rehidratar desde caché.
- **Comentarios y docstrings en español** explicando el *por qué*; sin secciones `Args:`/`Returns:`.
- **Import diferido obligatorio**: el core no adquiere dependencias duras de capas opcionales.

### Integration Points
- `encino_orm/migration.py` — El runner y el ledger (D-01…D-08).
- Los 6 `migrate()` + `_ensure_migrations_table()` — La columna `status`, el `ALTER TABLE` idempotente y la comprobación de `pending`.
- `encino_orm/model/cached.py` — La invalidación por clave (D-09…D-12).
- `encino_orm/model/model.py` — El hook `after_commit` donde se engancha la invalidación.
- `encino_orm/model/cache_backend.py` — La cota LRU (D-13/D-14).
- `docs/` — El contrato dev/test del backend en memoria y, si aplica, el procedimiento de reconciliación.

</code_context>

<specifics>
## Specific Ideas

- **`rollback_migration` (`migration.py:29`)** hoy llama `db.migrate(f"{m.name}:down", ...)`: ejecuta el `down` **e inserta** la fila `:down`, pero nunca borra `{name}` → re-aplicar es un no-op silencioso. Es el bug exacto de DATA-01.
- **`migrate()` (`sqlite.py:232-234`, `mysql.py:258-260`)** hace `execute(DDL) → insert(registro) → commit`. Si el proceso muere en medio, en MySQL/Oracle el DDL ya commiteó y el registro falta → el esquema cambió y el ledger miente. Es el caso exacto de DATA-02.
- **`CachedModel.load()` (`cached.py:22-47`)** escribe en caché en cada miss; el grep de `cache.delete` sobre `encino_orm/` da **cero** resultados. La interfaz existe y nunca se usa. Es el bug exacto de DATA-03.
- **`MemoryCacheBackend._store` (`cache_backend.py:15`)** es un dict plano sin cota; la expiración solo se evalúa al leer la misma clave (`:22-24`), así que claves nunca re-leídas se acumulan indefinidamente.
- **`applied_at` tiene `DEFAULT CURRENT_TIMESTAMP`** en los 6 dialectos: si en vez de una columna `status` se quisiera reutilizar `applied_at` como marcador de `pending`, habría que quitarle el default. Se descartó (D-04) por cambiar el significado de una columna existente.

</specifics>

<deferred>
## Deferred Ideas

- **Centralizar la lógica de `migrate()` en un solo módulo** (como se hizo con los builders en Fase 2): la duplicación en 6 adaptadores sigue ahí, pero centralizarla es un refactor mayor que no exige DATA-02. Candidato para una fase posterior.
- **Ledger de rollbacks histórico** (tabla separada con el detalle de cada reversión): descartado en D-06 por superficie extra; se reconsidera si alguien necesita auditoría de reversiones.
- **Write-through / caché por consulta**: descartado en D-11; hoy `CachedModel` solo cachea por PK.
- **Reintento automático de DDL asumiendo idempotencia**: descartado en D-02; peligroso con DDL no idempotente.
- **`MemoryCacheBackend` con purga de expirados antes de desalojar**: descartado en D-13 por simplicidad; se reconsidera si aparece presión de memoria en tests.

### Reviewed Todos (not folded)
Ninguno — no había todos pendientes para esta fase.

</deferred>

---

*Phase: 3-Data Correctness*
*Context gathered: 2026-09-18*
