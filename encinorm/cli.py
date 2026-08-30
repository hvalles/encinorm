"""CLI de encinorm (solo stdlib `argparse`).

Subcomando principal: `encinorm generate models <engine> [tablas...]`.
"""

import argparse
import asyncio
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="encinorm",
        description="Herramientas de encinorm (codegen desde la base de datos).",
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="genera código desde la base de datos")
    gen_sub = gen.add_subparsers(dest="subcommand")

    models = gen_sub.add_parser("models", help="genera modelos desde tablas existentes")
    models.add_argument("engine", choices=["sqlite", "mysql", "postgresql"])
    models.add_argument("tables", nargs="*", help="tablas a generar (default: todas)")
    models.add_argument("--folder", default="models", help="carpeta de salida (default: models)")
    models.add_argument("--database", help="archivo (sqlite) o nombre de BD (mysql/pg)")
    models.add_argument("--host", help="host (mysql/postgresql)")
    models.add_argument("--port", type=int, help="puerto (mysql/postgresql)")
    models.add_argument("--user", help="usuario (mysql/postgresql)")
    models.add_argument("--password", help="contraseña (mysql/postgresql)")

    return parser


def _conn_kwargs(args) -> dict:
    if args.engine == "sqlite":
        return {"database": args.database or ":memory:"}
    kw = {}
    if args.host:
        kw["host"] = args.host
    if args.port:
        kw["port"] = args.port
    if args.user:
        kw["user"] = args.user
    if args.password:
        kw["password"] = args.password
    if args.database:
        kw["db" if args.engine == "mysql" else "database"] = args.database
    return kw


async def _generate_models(args) -> int:
    from .introspection import generate_model, list_tables
    from .pool import create_db

    db = await create_db(args.engine, **_conn_kwargs(args))
    try:
        tables = args.tables or [r["name"] for r in (await list_tables(db)).rows]
        for table in tables:
            print(await generate_model(db, table, folder=args.folder))
        return 0
    finally:
        await db.close()


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "generate" and args.subcommand == "models":
        try:
            return asyncio.run(_generate_models(args))
        except Exception as exc:  # pragma: no cover - depende del entorno
            print(f"error: {exc}", file=sys.stderr)
            return 1
    parser.print_help()
    return 1
