# Créditos

Este proyecto fue desarrollado con la asistencia de las siguientes herramientas
de inteligencia artificial:

## OpenCode

- **Sitio:** <https://opencode.ai>
- **Rol:** agente de codificación en terminal utilizado para explorar el
  repositorio, redactar e implementar los cambios del núcleo ORM, las capas de
  producto (REST, GraphQL, seguridad, codegen), la documentación de usuario y los
  documentos de diseño.

## DeepSeek V4 Pro

- **Modelo:** `deepseek/deepseek-v4-pro`
- **Rol:** modelo de lenguaje que impulsa la generación de código, el análisis de
  los documentos `prompts/analisys-*.md` y la redacción de `docs/*.md`.

## Dependencias y ecosistema

El proyecto se apoya en las siguientes bibliotecas de código abierto:

| Biblioteca           | Uso                                        |
|----------------------|--------------------------------------------|
| `pydantic`           | Validación y modelos de datos.             |
| `aiosqlite`          | Driver asíncrono de SQLite.                |
| `aiomysql`           | Driver asíncrono de MySQL.                 |
| `asyncpg`            | Driver asíncrono de PostgreSQL.            |
| `fastapi`            | Capa REST (extra `http`/`security`).       |
| `PyJWT`              | Tokens JWT (extra `security`).             |
| `strawberry-graphql` | Capa GraphQL (extra `graphql`).            |
| `pytest`             | Suite de pruebas (dev).                    |
| `httpx`              | Cliente de pruebas ASGI (dev).             |

Gracias a los mantenedores de estas herramientas por su trabajo.
