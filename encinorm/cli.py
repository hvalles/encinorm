"""CLI de encinorm (solo stdlib `argparse`).

Subcomandos: `encinorm generate models <engine> [tablas...]` y
`encinorm copy <src-engine> <dst-engine> [tablas...]`.
"""

import argparse
import asyncio
import sys


def _add_conn_args(parser, prefix: str, label: str):
    def flag(name):
        return f"--{prefix}-{name}" if prefix else f"--{name}"

    parser.add_argument(flag("database"), help=f"archivo (sqlite) o nombre de BD {label}")
    parser.add_argument(flag("host"), help=f"host {label} (mysql/postgresql)")
    parser.add_argument(flag("port"), type=int, help=f"puerto {label} (mysql/postgresql)")
    parser.add_argument(flag("user"), help=f"usuario {label} (mysql/postgresql)")
    parser.add_argument(flag("password"), help=f"contraseña {label} (mysql/postgresql)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="encinorm",
        description="Herramientas de encinorm (codegen y copia de datos).",
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="genera código desde la base de datos")
    gen_sub = gen.add_subparsers(dest="subcommand")

    models = gen_sub.add_parser("models", help="genera modelos desde tablas existentes")
    models.add_argument("engine", choices=["sqlite", "mysql", "postgresql"])
    models.add_argument("tables", nargs="*", help="tablas a generar (default: todas)")
    models.add_argument("--folder", default="models", help="carpeta de salida (default: models)")
    _add_conn_args(models, "", "")

    copy = sub.add_parser("copy", help="copia tablas/BD completa entre bases de datos")
    copy.add_argument("src_engine", choices=["sqlite", "mysql", "postgresql"])
    copy.add_argument("dst_engine", choices=["sqlite", "mysql", "postgresql"])
    copy.add_argument("tables", nargs="*", help="tablas a copiar (default: todas)")
    copy.add_argument("--create", action="store_true", help="crea las tablas en destino")
    copy.add_argument("--truncate", action="store_true", help="vacía cada tabla destino antes de copiar")
    copy.add_argument("--no-preserve-ids", action="store_true",
                      help="no copiar la PK auto-incremental (dejar que el destino la asigne)")
    copy.add_argument("--no-disable-fk", action="store_true",
                      help="no desactivar las restricciones de FK durante la copia")
    _add_conn_args(copy, "src", "origen")
    _add_conn_args(copy, "dst", "destino")

    return parser


def _conn_kwargs(args) -> dict:
    return _conn_kwargs_prefixed(args, "engine", "")


def _conn_kwargs_prefixed(args, engine_attr: str, prefix: str) -> dict:
    engine = getattr(args, engine_attr)

    def get(name):
        full = f"{prefix}_{name}" if prefix else name
        return getattr(args, full, None)

    if engine == "sqlite":
        return {"database": get("database") or ":memory:"}
    kw = {}
    if get("host"):
        kw["host"] = get("host")
    if get("port"):
        kw["port"] = get("port")
    if get("user"):
        kw["user"] = get("user")
    if get("password"):
        kw["password"] = get("password")
    if get("database"):
        kw["db" if engine == "mysql" else "database"] = get("database")
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


async def _copy(args) -> int:
    from .pool import create_db
    from .transfer import copy_database

    src = await create_db(args.src_engine, **_conn_kwargs_prefixed(args, "src_engine", "src"))
    try:
        dst = await create_db(args.dst_engine, **_conn_kwargs_prefixed(args, "dst_engine", "dst"))
        try:
            result = await copy_database(
                src, dst, tables=args.tables or None,
                create=args.create, truncate=args.truncate,
                preserve_ids=not args.no_preserve_ids,
                disable_fk=not args.no_disable_fk,
            )
            for table, count in result.items():
                print(f"{table}: {count} filas")
            return 0
        finally:
            await dst.close()
    finally:
        await src.close()


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "generate" and args.subcommand == "models":
        try:
            return asyncio.run(_generate_models(args))
        except Exception as exc:  # pragma: no cover - depende del entorno
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if args.command == "copy":
        try:
            return asyncio.run(_copy(args))
        except Exception as exc:  # pragma: no cover - depende del entorno
            print(f"error: {exc}", file=sys.stderr)
            return 1
    parser.print_help()
    return 1
