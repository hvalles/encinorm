# Docker — Imágenes y configuración para pruebas

Cómo levantar los motores de base de datos contemplados por `encino_orm` en
contenedores Docker, con los **usuarios, contraseñas y puertos** que esperan las
pruebas de integración (`tests/test_*.py`).

Las pruebas **no** levantan los contenedores: se conectan a un servidor ya en
ejecución y se omiten (`pytest.skip`) si no responde. Los valores por defecto de
cada prueba se alimentan por variables de entorno `ENCINO_ORM_*` (ver
[§Variables de entorno](#variables-de-entorno)).

---

## Imágenes de los motores contemplados

| Motor | Imagen | Puerto | Tamaño (aprox.) | Notas |
|-------|--------|--------|-----------------|-------|
| SQLite | — (sin Docker) | — | — | Usa `:memory:` o un archivo local. |
| MySQL | `mysql:8.0` | 3306 | ~223 MB | Usado en CI. |
| MariaDB | `mariadb:11` | 3306 | ~99 MB | Drop-in del protocolo MySQL. |
| PostgreSQL | `postgres:16-alpine` | 5432 | ~111 MB | Usado en CI. |
| SQL Server Express | `mcr.microsoft.com/mssql/server:2022-latest` | 1433 | ~596 MB | Requiere EULA + contraseña `sa` compleja + ≥ 2 GB RAM. |
| Oracle XE | `gvenzl/oracle-xe:21-slim` | 1521 | ~720 MB | En Docker Hub (sin `docker login`). |
| Redis | `redis:latest` | 6379 | ~30 MB | Para `RedisCacheBackend` (extra `cache`). |

> Los tamaños son los **comprimidos** medidos con `docker manifest inspect`
> (linux/amd64); el consumo en disco es mayor. Detalle completo en
> `prompts/analisys-12.md`.

---

## 1. SQLite

No requiere Docker. Las pruebas usan `SqliteDb` con `database=":memory:"`.

---

## 2. MySQL

```bash
docker run -d --name mysql-test -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=admin \
  -e MYSQL_ROOT_HOST=% \
  -e MYSQL_DATABASE=encino_orm_test \
  mysql:8.0
```

| Variable de la imagen | Valor |
|-----------------------|-------|
| `MYSQL_ROOT_PASSWORD` | `admin` |
| `MYSQL_DATABASE` | `encino_orm_test` |
| `MYSQL_ROOT_HOST` | `%` (permite conexión remota) |

**Conexión para las pruebas** (`tests/test_mysql.py`): usuario `root`, contraseña
`admin`, base `encino_orm_test`.

---

## 3. MariaDB

```bash
docker run -d --name mariadb-test -p 3306:3306 \
  -e MARIADB_ROOT_PASSWORD=admin \
  -e MARIADB_DATABASE=encino_orm_test \
  mariadb:11
```

| Variable de la imagen | Valor |
|-----------------------|-------|
| `MARIADB_ROOT_PASSWORD` | `admin` |
| `MARIADB_DATABASE` | `encino_orm_test` |

**Conexión para las pruebas** (`tests/test_mariadb.py`): usuario `root`,
contraseña `admin`, base `encino_orm_test`. Reusa el driver `aiomysql` (protocolo
MySQL), por lo que no requiere dependencias extra.

---

## 4. PostgreSQL

```bash
docker run -d --name postgres-test -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=admin \
  -e POSTGRES_DB=encino_orm_test \
  postgres:16-alpine
```

| Variable de la imagen | Valor |
|-----------------------|-------|
| `POSTGRES_USER` | `postgres` |
| `POSTGRES_PASSWORD` | `admin` |
| `POSTGRES_DB` | `encino_orm_test` |

**Conexión para las pruebas** (`tests/test_postgresql.py`): usuario `postgres`,
contraseña `admin`, base `encino_orm_test`.

---

## 5. SQL Server Express

```bash
docker run -d --name mssql-test -p 1433:1433 \
  -e ACCEPT_EULA=Y \
  -e MSSQL_SA_PASSWORD='Admin_123' \
  mcr.microsoft.com/mssql/server:2022-latest
```

| Variable de la imagen | Valor |
|-----------------------|-------|
| `ACCEPT_EULA` | `Y` (**obligatoria**; la imagen no arranca sin aceptarla) |
| `MSSQL_SA_PASSWORD` | `Admin_123` (mín. 8 caracteres: mayúscula + minúscula + dígito + símbolo) |

> La imagen no crea la base `encino_orm_test`; la crea el *fixture* de la prueba
> con `IF DB_ID('encino_orm_test') IS NULL CREATE DATABASE ...`.
> Requiere ≥ 2 GB de RAM y, en el host, el **ODBC Driver 18 for SQL Server** para
> que funcione el driver `aioodbc`.

**Conexión para las pruebas** (`tests/test_mssql.py`): usuario `sa`, contraseña
`Admin_123`, base `encino_orm_test`, driver `ODBC Driver 18 for SQL Server`.

Instalar el extra: `pip install -e ".[mssql]"`.

> **TLS (por defecto seguro):** el motor conecta con `Encrypt=yes` y
> `TrustServerCertificate=no`. El contenedor local usa un **certificado
> autofirmado**, por lo que las pruebas activan
> `ENCINO_ORM_MSSQL_TRUST_CERT=true` para confiar en él. En producción, usa un
> certificado válido o pasa `trust_server_certificate=True`/`encrypt=False`
> explícitamente a `MssqlDb.connect(...)`.

### 5.1. Instalar el driver ODBC en el host

Además del extra de Python (`aioodbc`/`pyodbc`), el host necesita el
**ODBC Driver 18 for SQL Server**. Sin él, `pyodbc` falla con:

```
IM002 ... [Microsoft][Administrador de controladores ODBC]
No se encuentra el nombre del origen de datos y no se especificó
ningún controlador predeterminado (SQLDriverConnect)
```

**Windows**

1. Descargar "Microsoft ODBC Driver 18 for SQL Server" desde
   <https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server>
   e instalar el `.msi`.
2. Verificar que quedó registrado:

```bash
uv run python -c "import pyodbc; print('ODBC Driver 18 for SQL Server' in pyodbc.drivers())"
```

Si imprime `False`, cerrar y abrir la terminal (o reiniciar) para que el `PATH`
se refresque.

**Linux (Debian/Ubuntu)**

```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
sudo add-apt-repository "$(wget -qO- https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list)"
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

**macOS**

```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
ACCEPT_EULA=Y brew install msodbcsql18
```

> Si el único driver disponible es el heredado `SQL Server` (no recomendado),
> se puede forzar con `ENCINO_ORM_MSSQL_DRIVER='SQL Server'`, aunque puede dar
> problemas con tipos modernos (`datetime2`, `uniqueidentifier`, etc.).

---

## 6. Oracle XE

```bash
docker run -d --name oracle-test -p 1521:1521 \
  -e ORACLE_PASSWORD=admin \
  gvenzl/oracle-xe:21-slim
```

| Variable de la imagen | Valor |
|-----------------------|-------|
| `ORACLE_PASSWORD` | `admin` (se aplica a `SYS` y `SYSTEM`) |

> Service name por defecto: `XEPDB1` (Oracle XE 21c). El arranque es lento
> (minutos la primera vez). La imagen está en Docker Hub y **no requiere
> `docker login`**.

**Conexión para las pruebas** (`tests/test_oracle.py`): host `127.0.0.1`, puerto
`1521`, service `XEPDB1`, usuario `system`, contraseña `admin`.

Instalar el extra: `pip install -e ".[oracle]"`.

---

## 7. Redis

```bash
docker run -d --name redis-test -p 6379:6379 redis:latest
```

**Conexión para las pruebas** (`tests/test_redis_cache.py`): URL
`redis://127.0.0.1:6379`.

Instalar el extra: `pip install -e ".[cache]"`.

---

## Variables de entorno

Cada `tests/test_<motor>.py` lee estas variables (con los valores por defecto de
la tabla). En CI se exportan en el paso *Run tests*.

| Motor | Variables de entorno | Valores por defecto (local) |
|-------|----------------------|------------------------------|
| MySQL | `ENCINO_ORM_MYSQL_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `3306` / `root` / `admin` / `encino_orm_test` |
| MariaDB | `ENCINO_ORM_MARIADB_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `3306` / `root` / `admin` / `encino_orm_test` |
| PostgreSQL | `ENCINO_ORM_POSTGRES_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `5432` / `postgres` / `admin` / `encino_orm_test` |
| SQL Server | `ENCINO_ORM_MSSQL_HOST/PORT/USER/PASSWORD/DB/DRIVER/TRUST_CERT` | `127.0.0.1` / `1433` / `sa` / `Admin_123` / `encino_orm_test` / `ODBC Driver 18 for SQL Server` / `true` |
| Oracle | `ENCINO_ORM_ORACLE_HOST/PORT/SERVICE/USER/PASSWORD` | `127.0.0.1` / `1521` / `XEPDB1` / `system` / `admin` |
| Redis | `ENCINO_ORM_REDIS_URL` | `redis://127.0.0.1:6379` |

Ejemplo (Linux/macOS):

```bash
export ENCINO_ORM_MSSQL_PASSWORD='Admin_123'
uv run pytest tests/test_mssql.py
```

---

## docker-compose.yml (opcional)

```yaml
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: admin
      MYSQL_ROOT_HOST: "%"
      MYSQL_DATABASE: encino_orm_test
    ports: ["3306:3306"]

  mariadb:
    image: mariadb:11
    environment:
      MARIADB_ROOT_PASSWORD: admin
      MARIADB_DATABASE: encino_orm_test
    ports: ["3307:3306"]

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: admin
      POSTGRES_DB: encino_orm_test
    ports: ["5432:5432"]

  mssql:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      ACCEPT_EULA: "Y"
      MSSQL_SA_PASSWORD: "Admin_123"
    ports: ["1433:1433"]

  oracle:
    image: gvenzl/oracle-xe:21-slim
    environment:
      ORACLE_PASSWORD: admin
    ports: ["1521:1521"]

  redis:
    image: redis:latest
    ports: ["6379:6379"]
```

> MariaDB y MySQL comparten protocolo; si se levantan ambos a la vez, usa puertos
> distintos y ajusta `ENCINO_ORM_MARIADB_PORT`/`ENCINO_ORM_MYSQL_PORT` en
> consecuencia.

---

## Ejecutar las pruebas

```bash
# levantar el (los) motor(es) con `docker run` (secciones anteriores)…
# levantar todos los servicios con el docker-compose.yml junto al README.md
docker compose up -d

# suite completa (los servidores no disponibles se omiten automáticamente)
uv run pytest

# solo un motor
uv run pytest tests/test_mssql.py
uv run pytest tests/test_oracle.py
uv run pytest tests/test_mariadb.py
```
