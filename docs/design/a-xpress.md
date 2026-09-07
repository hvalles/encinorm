# Documento de Diseño — Motores adicionales: MariaDB, SQL Server Express y Oracle XE

Diseño para incorporar tres motores SQL relacionales de uso generalizado a
`encino_orm`, siguiendo el contrato `Db` y el patrón "una clase por motor"
documentado en `docs/engines.md`: **MariaDB** (compatibilidad de protocolo MySQL,
reusa `MysqlDb`), **Microsoft SQL Server Express** (T-SQL, driver `aioodbc`) y
**Oracle XE 21c** (PL/SQL, driver `oracledb` en modo *thin* asíncrono).

> Deriva de `prompts/analisys-12.md`. Precedentes de diseño: `docs/design/0-design.md`
> (contrato `Db`), `docs/design/8-pk.md` (PK/DLL por motor), `docs/design/7-missing.md`
> (upsert/bulk por motor). Es **aditivo**: `sqlite`/`mysql`/`postgresql` no cambian.

---

## 1. Objetivos y alcance

| # | Objetivo |
|---|----------|
| 1 | Registrar **MariaDB** como *objetivo de compatibilidad* de `MysqlDb` sin duplicar lógica de driver. |
| 2 | Implementar `MssqlDb` (SQL Server Express) sobre `aioodbc`, con T-SQL correcto (`IDENTITY`, `SCOPE_IDENTITY`, `MERGE`, `OFFSET/FETCH`). |
| 3 | Implementar `OracleDb` (Oracle XE) sobre `oracledb` thin async, con PL/SQL correcto (`IDENTITY` + `RETURNING INTO`, binds `:n`, `MERGE`, `FETCH FIRST`). |
| 4 | Añadir `DDL_MAP`, introspección y funciones portables (`db.fn`) para los tres motores. |
| 5 | Pruebas de integración reales vía Docker, que **se omiten** si el servidor no está disponible (patrón `tests/test_mysql.py`). |
| 6 | No tocar el comportamiento de los motores existentes (regresión de la suite completa). |
| 7 | Instalación **a petición**: MariaDB sin extra (reusa `aiomysql`); MSSQL/Oracle como extras `mssql`/`oracle` con **import perezoso** (ver §11). |

**Fuera de alcance** (decisión de `analisys-12.md`): Oracle Free 23ai (mismo
dialecto, imagen de ~9 GB y `docker login`), DB2 (sin driver async nativo),
CockroachDB/ClickHouse/MongoDB/Redis/TiDB/Cassandra.

---

## 2. Estado actual y contrato

- **Motores**: `SqliteDb` (`aiosqlite`), `MysqlDb` (`aiomysql`), `PostgresDb`
  (`asyncpg`); registro en `encino_orm/pool.py` (`_ENGINES`), `encino_orm/engine.py`
  (`Engine`), `encino_orm/model/types.py` (`DDL_MAP`).
- **Contrato `Db`** (`encino_orm/base.py`): `connect/close/is_alive`, `commit`/
  `rollback(save_point)`/`save_point`/`in_transaction`, builders `insert`/
  `update`/`delete`, `execute`/`fetch_all`/`fetch_one`/`fetch_many`/`exists`/
  `last_id`, `migrate`/`migrate_status`, e introspección opcional (`_tables_sql`,
  `columns_of`). `transaction()`/`retry()` ya están en `Db`.
- **`Query`**: placeholders genéricos `{n}` → intermedio `%(parameter_0000)s` +
  dict → nativo por motor en `_prepare` (`?`/`%s`/`$n`). Los motores nuevos deben
  traducir `%(...)s` a su placeholder nativo.
- **`Model.upsert`** (`encino_orm/model/model.py:507`) ya ramifica por dialecto:
  MySQL `ON DUPLICATE KEY`, resto `ON CONFLICT ... excluded`. SQL Server y Oracle
  requieren una rama `MERGE` (ver §3.5).
- **`_normalize`** (`encino_orm/introspection/types.py`) mapea tipo crudo → datatype
  lógico; requiere ampliación para tipos de SQL Server y Oracle (ver §3.4).

---

## 3. Decisiones transversales

### 3.1. Registro tipado (`Engine` + `_ENGINES`)

```python
# encino_orm/engine.py
class Engine(str, Enum):
    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    MARIADB = "mariadb"     # reusa MysqlDb
    MSSQL = "mssql"         # SQL Server
    ORACLE = "oracle"       # Oracle XE/Free
```

```python
# encino_orm/pool.py
_ENGINES = {
    "sqlite": SqliteDb,
    "mysql": MysqlDb,
    "mariadb": MariadbDb,     # subclase fina de MysqlDb (o MysqlDb si se omite)
    "postgresql": PostgresDb,
    "mssql": MssqlDb,
    "oracle": OracleDb,
}
```

`engine_of`/`is_mysql`/`is_postgres` se extienden con `is_mariadb`/`is_mssql`/
`is_oracle` y el CLI hereda automáticamente las opciones desde `Engine`.

### 3.2. Traducción de placeholders (`_prepare`)

| Motor | Intermedio | Nativo | Implementación |
|-------|-----------|--------|----------------|
| SQL Server | `%(parameter_0000)s` | `?` | `_to_positional` (idéntico a SQLite) |
| Oracle | `%(parameter_0000)s` | `:1`, `:2`, … | regex → `:n` + lista posicional |
| MariaDB | `%(parameter_0000)s` | `%s` | hereda `MysqlDb._prepare` |

```python
# encino_orm/oracle.py
_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")

def _to_oracle(sql: str, params: dict) -> tuple[str, list]:
    values = []
    counter = [0]
    def repl(match):
        values.append(params[match.group(1)])
        n = counter[0] + 1
        counter[0] = n
        return f":{n}"
    return _PLACEHOLDER_RE.sub(repl, sql), values
```

### 3.3. Mapeo de filas a `dict`

SQL Server (`aioodbc`/`pyodbc`) y Oracle (`oracledb` thin) devuelven **tuplas**, no
dicts (a diferencia de `DictCursor`/`Row`). Se añade un helper compartido que usa
`cursor.description` para materializar dicts, preservando la clave en **minúsculas**
(igual que `DictCursor` de aiomysql):

```python
# encino_orm/_rows.py (nuevo, compartido)
def _rows_to_dicts(description, rows) -> list[dict]:
    cols = [d[0].lower() for d in description]
    return [dict(zip(cols, r)) for r in rows]
```

`fetch_all`/`fetch_one`/`fetch_many` de `MssqlDb` y `OracleDb` la usan.

### 3.4. Ampliación de `_normalize` (introspección)

`encino_orm/introspection/types.py` debe reconocer tipos de los nuevos motores:

| Tipo crudo | Motor | Mapeo |
|-----------|-------|-------|
| `nvarchar`/`nchar`/`varchar2`/`nvarchar2`/`long` | MSSQL/Oracle | `str` |
| `bit` | MSSQL | `bool` |
| `datetime2`/`smalldatetime` | MSSQL | `datetime` |
| `timestamp(6) with time zone` / `timestamp with local time zone` | Oracle | `datetime` |
| `number` (scale=0) | Oracle | `int` |
| `number` (scale>0) | Oracle | `numeric` |
| `varbinary`/`image`/`raw` | MSSQL/Oracle | `blob` |
| `uniqueidentifier` | MSSQL | `str` |
| `xml` | MSSQL | `str` |
| `longtext` (con CHECK json) | MariaDB | `json` (solo en `MariadbDb.columns_of`, ver §4) |

Estos son **aditivos** al conjunto existente (`_STR_TYPES`, `_INT_TYPES`, …) y no
alteran el comportamiento actual.

### 3.5. `ignore_duplicated` / `replace` y clave de conflicto (PK vs índice único)

SQL Server y Oracle **no tienen** `INSERT OR IGNORE` / `ON DUPLICATE KEY` /
`ON CONFLICT DO NOTHING`, y su `MERGE` admite **una sola** expresión `ON` (un
único predicado de conflicto). Esto obliga a distinguir la semántica de los dos
flags, que ya difiere entre los motores actuales:

| Flag | SQLite | MySQL | PostgreSQL | Semántica |
|------|--------|-------|------------|-----------|
| `ignore_duplicated` | `INSERT OR IGNORE` | `INSERT IGNORE` | `ON CONFLICT DO NOTHING` | **cualquier** clave única (PK o índice único) |
| `replace` | `INSERT OR REPLACE` | `REPLACE INTO` | `ON CONFLICT (col)` (explícito) | clave **explícita** (en PG, la 1ª columna) |

> **El problema con `MERGE ON (id)`:** si el modelo tiene un **índice único** no
> relacionado con la PK (p. ej. `email UNIQUE`) y la colisión es sobre `email`,
> un `MERGE ... ON (id = ...)` **no la detecta**: el registro cae en
> `WHEN NOT MATCHED THEN INSERT`, y la base lanza una violación de unicidad
> (SQL Server `2627`/`2601`, Oracle `ORA-00001`) en lugar de ignorar o
> reemplazar. Por eso los dos flags se resuelven de forma distinta:

**`ignore_duplicated=True` → capturar la violación de unicidad** (no `MERGE`),
reproduciendo fielmente "ignorar ante *cualquier* clave única" (PK o índice
único), igual que SQLite/MySQL/PG:

```python
# MssqlDb / OracleDb
def is_unique_violation(self, exc) -> bool:
    # MSSQL: 2627 (constraint PK/UNIQUE), 2601 (índice único)
    # Oracle: ORA-00001 (unique constraint violated)
    ...
```

En `execute()`, si la sentencia es un `INSERT ... ignore` y se captura una
violación de unicidad, se revierte el *statement* y se devuelve `0`. El chequeo
se acota **solo** a códigos de unicidad (no `FK` 547/ORA-02291 ni `CHECK`
547/ORA-02290) para no enmascarar otros errores.

**`replace=True` / `upsert` → `MERGE` con clave de conflicto explícita**
(`conflict`), coherente con PostgreSQL:

```sql
MERGE INTO t AS dst
USING (SELECT 1) AS src ON (dst.{conflict} = src.{conflict})
WHEN MATCHED THEN UPDATE SET c1 = src.c1, ...
WHEN NOT MATCHED THEN INSERT (cols) VALUES (vals);
```

`conflict` por defecto es la PK (`id`); para apuntar a un **índice único** el
desarrollador pasa `conflict=["email"]` (ya soportado por `Model.upsert`).
**Límite conocido** (idéntico a PostgreSQL): si la colisión real es sobre una
clave única **distinta** a la declarada en `conflict`, la rama de inserción
viola esa unicidad y el error **se propaga**; es el comportamiento esperado y
documentado de `ON CONFLICT (cols)`.

**Firma del builder** (aditiva y retrocompatible):

```python
# encino_orm/base.py — firma del contrato (aditiva)
def insert(self, tabla, data, ignore_duplicated=False, replace=False,
           conflict: list[str] | None = None): ...
```

- `conflict=None` + `replace=False` → comportamiento actual (SQLite/MySQL/PG sin cambios).
- `ignore_duplicated=True` → captura de violación de unicidad (MSSQL/Oracle).
- `replace=True` → `MERGE ON (conflict)` (MSSQL/Oracle), con `conflict` = PK por defecto.

`Model.insert`/`save`/`upsert` ya conocen la clave (PK por `_pk_fields()` o
`conflict` explícito) y la pasan al builder. La rama de `Model.upsert`
(`model.py:555`) añade `MERGE` para `MSSQL`/`ORACLE`, y `save()` usa
`ignore_duplicated`/`upsert` según el flujo existente.

---

## 4. MariaDB — objetivo de compatibilidad (reusa `MysqlDb`)

- **Driver**: `aiomysql` (protocolo MySQL) o `asyncmy` (opcional). **Sin cambios**.
- **Decisión**: **no se duplica la clase de motor**. Se añade `MariadbDb(MysqlDb)`
  con `dialect = "mariadb"` y **una sola** sobreescritura de introspección, porque
  MariaDB reporta `JSON` como `longtext` (alias con `CHECK (json_valid(...))`):

```python
# encino_orm/mariadb.py (nuevo)
from .mysql import MysqlDb

class MariadbDb(MysqlDb):
    dialect = "mariadb"

    async def columns_of(self, table):
        cols = await super().columns_of(table)
        # MariaDB: JSON es LONGTEXT con CHECK; normalizar a datatype json
        for c in cols:
            if c.datatype == "str" and c.raw_type.lower() == "longtext":
                c = c.replace(datatype="json")  # ColumnSpec es frozen → new
        return cols
```

- **DDL**: `DDL_MAP["mariadb"] = DDL_MAP["mysql"]` (MariaDB acepta `JSON`,
  `AUTO_INCREMENT`, `TINYINT(1)`, etc. idénticos).
- **Registro**: `DDL_MAP["mariadb"] = DDL_MAP["mysql"]` (o alias en `ddl_type`).
- **Valor**: validar que `MysqlDb` no se rompe contra MariaDB en CI (service
  `mariadb:11`), más que aportar dialecto nuevo.

---

## 5. Microsoft SQL Server Express — `MssqlDb`

### 5.1. Driver y conexión

- **Dependencia**: `aioodbc` + `pyodbc`, más el **ODBC Driver 18 for SQL Server**
  instalado en el host/runner.
- **Conexión** (kwargs de ODBC):

```python
async def connect(self, **kwargs):
    driver = kwargs.get("driver", "ODBC Driver 18 for SQL Server")
    server = kwargs["host"]
    port = kwargs.get("port", 1433)
    user = kwargs["user"]
    password = kwargs["password"]
    database = kwargs.get("db") or kwargs.get("database")
    conn_str = (
        f"DRIVER={{{driver}}};SERVER={server},{port};"
        f"UID={user};PWD={password};DATABASE={database};"
        "Encrypt=no;TrustServerCertificate=yes;"
    )
    self._connection = await aioodbc.connect(dsn=conn_str)
    self._connection.autocommit = False      # transacciones explícitas
    self._in_tx = False
```

> `Encrypt=no;TrustServerCertificate=yes` es **solo para pruebas locales**; en
> producción debe usarse `Encrypt=yes` con CA de confianza.

### 5.2. Ciclo de vida y transacciones

| Método | SQL/API |
|--------|---------|
| `commit` | `connection.commit()` |
| `rollback` | `connection.rollback()` |
| `save_point(name)` | `SAVE TRANSACTION name` |
| `rollback(save_point)` | `ROLLBACK TRANSACTION name` |
| `in_transaction` | flag interno `_in_tx` (pyodbc no expone estado de transacción) |

El flag `_in_tx` se pone `True` en `execute`/DML y `False` en `commit`/`rollback`
(patrón análogo a SQLite, que tampoco expone estado nativo).

### 5.3. `last_id` — `SCOPE_IDENTITY()`

```python
async def execute(self, qry) -> int:
    ...
    await cursor.execute(sql, values)
    self._in_tx = True
    rowcount = cursor.rowcount
    if sql.lstrip().upper().startswith("INSERT"):
        await cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
        self._last_id = (await cursor.fetchone())[0] or 0
    return rowcount
```

`SCOPE_IDENTITY()` es seguro a nivel de *scope* de sesión (no lee identidades de
triggers/otras sesiones como `@@IDENTITY`).

### 5.4. Paginación — `OFFSET … FETCH`

```python
async def fetch_many(self, qry, limit, page):
    offset = (page - 1) * limit
    sql = sql.rstrip().rstrip(";")
    # OFFSET/FETCH exige ORDER BY; se usa un orden estable neutro si no lo hay
    if "ORDER BY" not in sql.upper():
        sql += " ORDER BY (SELECT NULL)"
    sql += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
    ...
```

### 5.5. `ignore_duplicated` (captura de unicidad) / `replace` (`MERGE`) — ver §3.5

### 5.6. Introspección

```python
def _tables_sql(self):
    return ("SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE'")

async def columns_of(self, table):
    rows = await self.fetch_all(Query(
        "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, "
        "COLUMNPROPERTY(OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME), COLUMN_NAME, 'IsIdentity') AS is_identity "
        "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = {0}", [table]))
    ...
```

### 5.7. `is_lock_error`

```python
def is_lock_error(self, exc):
    code = None
    try:
        code = exc.args[1][0]   # pyodbc: args = (SQLSTATE, (code, msg))
    except Exception:
        return False
    return code in (1205, 1222)   # deadlock victim, lock timeout
```

---

## 6. Oracle XE — `OracleDb`

### 6.1. Driver y conexión

- **Dependencia**: `oracledb` (python-oracledb ≥ 2.0) en **modo thin** (por
  defecto; no requiere cliente nativo de Oracle) con soporte `asyncio`.
- **Conexión** (EZ-Connect):

```python
async def connect(self, **kwargs):
    host = kwargs["host"]; port = kwargs.get("port", 1521)
    service = kwargs.get("service_name", kwargs.get("db", "XEPDB1"))
    user = kwargs["user"]; password = kwargs["password"]
    dsn = oracledb.makedsn(host, port, service_name=service)
    self._connection = await oracledb.connect_async(user=user, password=password, dsn=dsn)
    self._connection.autocommit = False
    self._in_tx = False
```

### 6.2. Ciclo de vida y transacciones

| Método | SQL/API |
|--------|---------|
| `commit` | `connection.commit()` |
| `rollback` | `connection.rollback()` |
| `save_point(name)` | `SAVEPOINT name` |
| `rollback(save_point)` | `ROLLBACK TO name` |
| `in_transaction` | flag interno `_in_tx` |

### 6.3. `last_id` — `RETURNING … INTO` (decisión clave)

Oracle no expone `lastrowid` ni un `CURRVAL` sencillo con columnas `IDENTITY`. La
forma **segura y concurrente** es capturar el id con `RETURNING ... INTO` mediante
un bind de salida. Como `encino_orm` controla el DDL (columna de identidad `id`),
el builder emite el `RETURNING` y `execute` captura el valor:

```python
# builder (PK auto-incremental por defecto: id)
def insert(self, tabla, data, ignore_duplicated=False, replace=False, conflict=None):
    ...
    sql = f"INSERT INTO {tabla} ({cols}) VALUES ({placeholders})"
    if self._auto_pk_known(tabla):          # tabla con identidad `id` (vía DDL)
        sql += " RETURNING id INTO :ret_id"
    ...

# execute: detecta el bind de salida
async def execute(self, qry):
    sql, values = self._prepare(qry)
    out = self._connection.var(oracledb.NUMBER) if ":ret_id" in sql else None
    cur = await self._connection.cursor()
    await cur.execute(sql, values + [out] if out is not None else values)
    if out is not None:
        self._last_id = out.getvalue()[0]
    ...
```

- El `RETURNING` se aplica solo cuando el motor sabe que la tabla tiene una PK
  auto-incremental (se determina con `columns_of`/DDL generado por el propio ORM;
  por defecto se asume `id`). Alternativa documentada (rechazada por fragilidad):
  `SELECT seq.CURRVAL FROM dual`, que no aplica a `IDENTITY` columns.
- **Matiz**: Oracle requiere que el `INSERT ... RETURNING` **no** se combine con
  `MERGE`; cuando `ignore_duplicated`/`replace` estén activos se usa `MERGE` (§3.5)
  y `last_id` se resuelve con `SELECT id FROM t WHERE <conflict> = :n` tras el merge
  (o se deja sin id, ya que un upsert no garantiza inserción). Documentado en §10.

### 6.4. `ignore_duplicated` (captura de unicidad) / `replace` (`MERGE`) — ver §3.5

### 6.5. Paginación — `OFFSET … FETCH` (12c+)

```python
sql += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
```

### 6.6. Introspección

```python
def _tables_sql(self):
    return "SELECT table_name AS name FROM user_tables"

async def columns_of(self, table):
    rows = await self.fetch_all(Query(
        "SELECT column_name, data_type, data_length, data_precision, data_scale, "
        "nullable FROM user_tab_columns WHERE table_name = UPPER({0})", [table]))
    ...
```

> Oracle guarda identificadores en **mayúsculas**; `UPPER(:1)` en el filtro y
> `_safe_column`/comparaciones de nombres en minúsculas al normalizar.

### 6.7. `is_lock_error`

```python
def is_lock_error(self, exc):
    code = getattr(getattr(exc, "args", [None])[0], "code", None)
    return code in (60, 54, 8177)   # ORA-00060 deadlock, ORA-00054, ORA-08177
```

---

## 7. Mapeo DDL (`DDL_MAP`)

| datatype | sqlite | mysql/mariadb | postgresql | **mssql** | **oracle** |
|----------|--------|---------------|------------|-----------|------------|
| `pk` | `INTEGER PRIMARY KEY AUTOINCREMENT` | `INT AUTO_INCREMENT PRIMARY KEY` | `SERIAL PRIMARY KEY` | `INT IDENTITY(1,1) PRIMARY KEY` | `NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY` |
| `str` | `TEXT` | `VARCHAR(255)` | `TEXT` | `NVARCHAR(255)` | `VARCHAR2(255)` |
| `int` | `INTEGER` | `INT` | `INTEGER` | `INT` | `NUMBER(10)` |
| `bool` | `INTEGER` | `TINYINT(1)` | `BOOLEAN` | `BIT` | `NUMBER(1)` |
| `tinyint` | `INTEGER` | `TINYINT(1)` | `SMALLINT` | `TINYINT` | `NUMBER(3)` |
| `datetime` | `TEXT` | `DATETIME` | `TIMESTAMPTZ` | `DATETIME2` | `TIMESTAMP WITH TIME ZONE` |
| `date` | `TEXT` | `DATE` | `DATE` | `DATE` | `DATE` |
| `numeric` | `REAL` | `DECIMAL(10,2)` | `NUMERIC` | `DECIMAL(10,2)` | `NUMBER(10,2)` |
| `decimal` | `TEXT` | `DECIMAL(10,2)` | `NUMERIC` | `DECIMAL(10,2)` | `NUMBER(19,4)` |
| `float` | `REAL` | `FLOAT` | `DOUBLE PRECISION` | `FLOAT` | `BINARY_DOUBLE` |
| `blob` | `BLOB` | `BLOB` | `BYTEA` | `VARBINARY(MAX)` | `BLOB` |
| `json` | `TEXT` | `JSON` | `JSONB` | `NVARCHAR(MAX)` | `CLOB` |

> Notas: SQL Server no tiene tipo `JSON` (se usa `NVARCHAR(MAX)`); Oracle usa
> `CLOB` por portabilidad (XE 21c admite el tipo `JSON` nativo, opcional). Los
> `BOOLEAN`/`BIT` se serializan a `0/1` en Python (ya contemplado en `model.py`).

---

## 8. Funciones SQL portables (`db.fn`) — ampliación

`encino_orm/sql.py` (`SqlFunctions`) se amplía con las traducciones de los nuevos
dialectos para las funciones ya registradas (`now`, `date_add`, `date_sub`, …):

| Concepto | mssql | oracle |
|----------|-------|--------|
| `now()` | `GETDATE()` | `SYSDATE` |
| `length()` | `LEN()` | `LENGTH()` |
| `substring()` | `SUBSTRING(x,s,l)` | `SUBSTR(x,s,l)` |
| `concat()` | `CONCAT(a,b)` | `a \|\| b` |
| `random()` | `NEWID()` | `DBMS_RANDOM.VALUE` |
| `uuid()` | `NEWID()` | `SYS_GUID()` |
| `year/…` | `DATEPART(YEAR, x)` | `EXTRACT(YEAR FROM x)` |

Sin cambios de firma; solo se añaden ramas por `dialect` en `SqlFunctions`.

---

## 9. Resumen de cambios por archivo

| Archivo | Cambio |
|---------|--------|
| `encino_orm/engine.py` | `Engine.MARIADB/MSSQL/ORACLE` + predicados `is_mariadb/is_mssql/is_oracle`. |
| `encino_orm/mariadb.py` | **NUEVO**: `MariadbDb(MysqlDb)` (solo `dialect` + `columns_of` con `longtext→json`). |
| `encino_orm/mssql.py` | **NUEVO**: `MssqlDb` (`aioodbc`): `_prepare` (`?`), `_rows_to_dicts`, `SCOPE_IDENTITY`, `MERGE`, `OFFSET/FETCH`, introspección, `is_lock_error`, `is_unique_violation`. |
| `encino_orm/oracle.py` | **NUEVO**: `OracleDb` (`oracledb` thin async): `_prepare` (`:n`), `RETURNING INTO`, `MERGE`, `FETCH`, introspección (`user_tab_columns`), `is_lock_error`, `is_unique_violation`. |
| `encino_orm/_rows.py` | **NUEVO**: helper `_rows_to_dicts(description, rows)`. |
| `encino_orm/base.py` | `insert(..., conflict=None)` (opcional, retrocompatible). |
| `encino_orm/pool.py` | Registro en `_ENGINES` de `mariadb`/`mssql`/`oracle`. |
| `encino_orm/model/types.py` | `DDL_MAP["mariadb"]` (alias de mysql), `["mssql"]`, `["oracle"]`. |
| `encino_orm/introspection/types.py` | `_normalize` ampliado (nvarchar, varchar2, bit, datetime2, number, raw, uniqueidentifier, xml, …). |
| `encino_orm/model/model.py` | Rama `MERGE` en `upsert` para `MSSQL`/`ORACLE`; pasar `conflict` en `insert`/`save`. |
| `encino_orm/sql.py` | Funciones portables para `mssql`/`oracle`. |
| `encino_orm/transfer.py` | Aceptar los nuevos dialectos (o documentar que `transfer` a Oracle/MSSQL queda pendiente). |
| `encino_orm/__init__.py` | Exportar `MariadbDb`, `MssqlDb`, `OracleDb`. |
| `pyproject.toml` | Extras `mssql = ["aioodbc>=0.5","pyodbc>=5.0"]`, `oracle = ["oracledb>=2.0"]` y `all-db` (conveniencia). |
| `encino_orm/mssql.py` / `oracle.py` | **Import perezoso del driver** (solo en `connect()`); las clases y su registro importan sin el extra instalado. |

---

## 10. Decisiones / ambigüedades

| # | Punto | Decisión |
|---|-------|----------|
| 1 | MariaDB: clase nueva vs reuso | **Reuso** (`MariadbDb(MysqlDb)`) con única sobreescritura de `columns_of`; no se duplica el driver. |
| 2 | `ignore_duplicated`/`replace` en MSSQL/Oracle | `ignore` → **capturar violación de unicidad** (2627/2601, ORA-00001); `replace` → **`MERGE`** + `conflict` explícito (PK por defecto). |
| 3 | `last_id` en Oracle | **`RETURNING id INTO :ret_id`** con bind de salida; no `CURRVAL`. En `MERGE` (upsert), sin id garantizado. |
| 4 | `last_id` en SQL Server | **`SCOPE_IDENTITY()`** en la misma sesión. |
| 5 | `in_transaction` en MSSQL/Oracle | **Flag interno** `_in_tx` (los drivers no exponen estado nativo). |
| 6 | Paginación MSSQL/Oracle | `OFFSET … FETCH`; en MSSQL se añade `ORDER BY (SELECT NULL)` si falta. |
| 7 | `bool` en Oracle | `NUMBER(1)` (Oracle SQL no tiene `BOOLEAN`); serialización `0/1` en Python. |
| 8 | `json` en MSSQL/Oracle | `NVARCHAR(MAX)` / `CLOB` (texto); deserialización a `dict` en Python (ya existente). |
| 9 | `transfer.py` cross-engine a nuevos motores | **Fase 2**; la Fase 1 lo documenta como no soportado (error claro). |
| 10 | Identificadores en Oracle | Mayúsculas en catálogo; normalizar a minúsculas en `columns_of`. |
| 11 | ODBC Driver de SQL Server | Requisito de host documentado; sin driver, la conexión falla con mensaje claro. |
| 12 | Índice único no-PK como clave de conflicto | `replace`/`upsert` aceptan `conflict=["col"]`; una colisión sobre otra clave única **distinta** se propaga (igual que PG `ON CONFLICT (cols)`). |
| 13 | Instalación core vs a petición | MariaDB en **core** (reusa `aiomysql`); MSSQL/Oracle como **extras** (`mssql`/`oracle`) con import perezoso (ver §11). |

---

## 11. Dependencias e instalación (¿core o a petición?)

**Decisión: los motores se instalan "a petición" según el costo de su driver, no
de forma uniforme.**

| Motor | Driver Python | ¿En core? | Sistema (extra) | Justificación |
|-------|---------------|-----------|-----------------|---------------|
| MariaDB | `aiomysql` (ya en core) | **Sí (sin extra)** | — | **Costo cero**: reusa el driver de MySQL ya instalado; es una subclase, no una dependencia nueva. |
| SQL Server | `aioodbc` + `pyodbc` | **No → extra `mssql`** | **ODBC Driver 18 for SQL Server** | `pyodbc` es un binario compilado (sin rueda en todas las plataformas) **y** exige un driver de sistema que pip no puede instalar. Imponerlo en core rompería instalaciones que no lo usan. |
| Oracle | `oracledb>=2.0` | **No → extra `oracle`** | ninguna (thin mode) | Driver niche/enterprise con peso propio; no justifica cargarlo a todo usuario. |

```toml
# pyproject.toml
[project.optional-dependencies]
mssql  = ["aioodbc>=0.5", "pyodbc>=5.0"]
oracle = ["oracledb>=2.0"]
all-db = ["aioodbc>=0.5", "pyodbc>=5.0", "oracledb>=2.0"]  # conveniencia
```

**Por qué no todo al core:** los tres drivers actuales (`aiosqlite`, `aiomysql`,
`asyncpg`) son puros o con ruedas universales y de uso muy común, por eso siguen
en core (y **no se mueven** a extras: sería un *breaking change*). MSSQL es el
caso distinto: su dependencia real es **de sistema** (ODBC Driver), imposible de
resolver con pip, por lo que **es inherentemente opt-in**. Oracle, aunque se
instala por pip, es opcional por peso y nicho.

**Requisito de arquitectura — imports perezosos.** Como los drivers de MSSQL y
Oracle no están en core, las clases `MssqlDb`/`OracleDb` y su registro en
`_ENGINES`/`Engine` deben ser **importables sin el driver instalado**:

```python
# encino_orm/mssql.py — NO importar aioodbc/pyodbc a nivel de módulo
class MssqlDb(Db):
    async def connect(self, **kwargs):
        try:
            import aioodbc          # import perezoso: solo se exige al conectar
        except ImportError as e:
            raise ConnectionError(
                "MssqlDb requiere el extra 'mssql': pip install encino-orm[mssql]"
            ) from e
        ...
```

- `import encino_orm` **siempre** funciona, con o sin extras.
- `create_db("mssql")` / `create_db("oracle")` fallan **solo al conectar** con un
  mensaje claro que indica el extra a instalar (`pip install encino-orm[mssql]`).
- El import perezoso aplica también a las clases de excepción usadas en
  `is_lock_error`/`is_unique_violation` (referencias `pyodbc.Error`/`oracledb`).

Esto mantiene el `__init__.py` ligero (los motores opcionales se importan sin
efecto colateral) y alinea la instalación con el patrón de extras ya existente
(`security`, `http`, `graphql`).

---

## 12. Estrategia de testing

### 12.1. Modelo de ejecución: imágenes **pre-aprovisionadas** (no testcontainers)

Las pruebas **no** levantan los contenedores: se conectan a un servidor **ya en
ejecución** y, si no responde, **se omiten** (`pytest.skip`). Es el mismo patrón
que `tests/test_mysql.py`/`tests/test_postgresql.py`.

- **Local**: levantar la imagen **antes** de correr la suite:

  ```bash
  docker run -d --name mariadb-test -p 3306:3306 \
    -e MARIADB_ROOT_PASSWORD=admin -e MARIADB_DATABASE=encino_orm_test mariadb:11

  docker run -d --name mssql-test -p 1433:1433 \
    -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='Admin_123' \
    mcr.microsoft.com/mssql/server:2022-latest

  docker run -d --name oracle-test -p 1521:1521 \
    -e ORACLE_PASSWORD=admin gvenzl/oracle-xe:21-slim
  ```

- **CI** (`.github/workflows/ci.yml`): el bloque `services:` levanta
  `mariadb:11` y `mssql/server:2022` (con *health-check*); Oracle XE queda
  **off-CI** por su peso (~720 MB, arranque lento) y se corre manual.
- **Sin servidor** → los tests se omiten silenciosamente (no fallan).

> **Testcontainers** (`testcontainers-python`, spin-up automático en fixture)
> queda como **alternativa futura opt-in** (marcador `-m docker`), útil sobre todo
> para MariaDB (ligera). No se adopta por defecto para mantener consistencia con
> MySQL/PG y porque MSSQL/Oracle son imágenes pesadas con arranque lento; para
> ellas el pre-aprovisionado evita pull+arranque por sesión.

### 12.2. Pruebas

- **Fixture por motor** que se **omite** si el servidor no está disponible
  (`pytest.skip`), idéntico a `tests/test_mysql.py`/`tests/test_postgresql.py`:
  - `tests/test_mariadb.py` — apunta `MariadbDb` a `mariadb:11` (service en CI).
  - `tests/test_mssql.py` — `MssqlDb` contra `mcr.microsoft.com/mssql/server:2022`
    (service con `ACCEPT_EULA=Y` + `MSSQL_SA_PASSWORD`); `skip` si no hay driver ODBC.
  - `tests/test_oracle.py` — `OracleDb` contra `gvenzl/oracle-xe:21-slim`; `skip` si no está.
- **Unitarios sin servidor** (patrón de `tests/test_postgresql.py::TestPostgresInternal`):
  `_prepare` (placeholders), builders (`insert`/`update`/`delete` con `MERGE`),
  `_rows_to_dicts`, `is_lock_error`, `is_unique_violation`.
- **Ciclo de vida/transacciones/CRUD/migraciones** contra el motor real (matriz de
  `test_mysql.py` adaptada).
- **Regresión**: la suite completa existente (sqlite/mysql/postgresql) debe
  permanecer en verde.

### 12.3. Credenciales por motor (variables de entorno)

Las credenciales se alimentan por **variables de entorno** con el prefijo
`ENCINO_ORM_*`, y cada `tests/test_<motor>.py` define un dict de configuración
que lee `os.getenv(...)` con valores por defecto locales (patrón de
`tests/test_mysql.py`/`tests/test_postgresql.py`):

```python
# tests/test_mssql.py (patrón; ídem mariadb/oracle)
import os
MSSQL_CONFIG = {
    "host": os.getenv("ENCINO_ORM_MSSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("ENCINO_ORM_MSSQL_PORT", "1433")),
    "user": os.getenv("ENCINO_ORM_MSSQL_USER", "sa"),
    "password": os.getenv("ENCINO_ORM_MSSQL_PASSWORD", "Admin_123"),
    "db": os.getenv("ENCINO_ORM_MSSQL_DB", "encino_orm_test"),
    "driver": os.getenv("ENCINO_ORM_MSSQL_DRIVER", "ODBC Driver 18 for SQL Server"),
}
```

| Motor | Variables de entorno | Valores por defecto (local) |
|-------|----------------------|------------------------------|
| **MariaDB** | `ENCINO_ORM_MARIADB_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `3306` / `root` / `admin` / `encino_orm_test` |
| **SQL Server** | `ENCINO_ORM_MSSQL_HOST/PORT/USER/PASSWORD/DB/DRIVER` | `127.0.0.1` / `1433` / `sa` / `Admin_123` / `encino_orm_test` / `ODBC Driver 18 for SQL Server` |
| **Oracle** | `ENCINO_ORM_ORACLE_HOST/PORT/SERVICE/USER/PASSWORD` | `127.0.0.1` / `1521` / `XEPDB1` / `system` / `admin` |

> Los valores por defecto deben coincidir con los `docker run` de §12.1 (ej.
> `MSSQL_SA_PASSWORD='Admin_123'`, `ORACLE_PASSWORD=admin`). En CI, `.github/
> workflows/ci.yml` exporta las mismas variables en el paso *Run tests* (como ya
> hace con `ENCINO_ORM_MYSQL_*`/`ENCINO_ORM_POSTGRES_*`), apuntando al servicio.
>
> **Credenciales especiales** (no conexión, sino arranque del contenedor):
> `ACCEPT_EULA=Y` + `MSSQL_SA_PASSWORD` (SQL Server) y `ORACLE_PASSWORD` (Oracle).
> Ninguna llave de acceso adicional (ver `prompts/analisys-12.md` §4).

---

## 13. Fases de implementación

| Fase | Alcance | Criterios |
|------|---------|-----------|
| **1** | `_rows.py`, `_normalize` ampliado, `Engine` + `_ENGINES` + exports, `DDL_MAP`, extras en `pyproject.toml`. | Registro tipado sin romper motores actuales. |
| **2** | `MssqlDb` completo + `tests/test_mssql.py` (+ service en CI). | `create_db("mssql")` CRUD/`last_id`/migraciones en verde contra Express. |
| **3** | `OracleDb` completo + `tests/test_oracle.py` (XE `slim`). | `create_db("oracle")` CRUD/`last_id`(`RETURNING`)/migraciones en verde. |
| **4** | `MariadbDb` + `tests/test_mariadb.py` (+ service en CI). | La suite MySQL pasa contra MariaDB sin cambios. |
| **5** | `upsert`/`save` con `MERGE` (rama en `model.py`), `db.fn` para mssql/oracle, docs (`engines.md`, `README`, `index.md`). | `upsert` idempotente en MSSQL/Oracle; funciones portables correctas. |
