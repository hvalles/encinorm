import json
import re
import types
import weakref
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, ClassVar, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from encinorm.base import Db
from encinorm.context import resolve_db
from encinorm.query import Query

from .exceptions import (
    DuplicateReferenceError,
    FailOnUpdate,
    RelationshipError,
    ValidationError,
)
from .filter import Filter
from .references import HasMany, Reference
from .scope import current_scope

_MISSING = object()
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIELD_ADAPTERS = weakref.WeakKeyDictionary()  # cls -> {field: TypeAdapter}
_COLUMN_MAPS = weakref.WeakKeyDictionary()     # cls -> {field: columna}


def _serialize(value):
    if isinstance(value, datetime):
        # normaliza a UTC-naive para almacenamiento uniforme entre motores
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat(sep=" ")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return value


def _base_type(annotation):
    if hasattr(annotation, "__metadata__"):  # Annotated[...]
        annotation = get_args(annotation)[0]
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    args = get_args(annotation)
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        return non_none[0] if non_none else args[0]
    return args[0]


def _types_compatible(model_dt: str, db_dt: str, engine: str) -> bool:
    """Indica si el datatype lógico del modelo es compatible con el tipo de la BD."""
    if model_dt == db_dt:
        return True
    if {model_dt, db_dt} == {"bool", "int"}:
        return True          # bool se almacena como int/tinyint en todos los motores
    if engine == "sqlite" and model_dt in ("datetime", "date") and db_dt == "str":
        return True          # SQLite guarda datetime/date como TEXT
    return False


def _set_private(obj, name, value):
    object.__setattr__(obj, name, value)


class Model(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    _table: ClassVar[str] = ""
    _fields_disabled: ClassVar[list] = []
    _hooks: ClassVar[dict] = {}
    _references_def: ClassVar[dict] = {}
    _has_many_def: ClassVar[dict] = {}
    _indexes: ClassVar[list] = []
    _primary_key: ClassVar[tuple[str, ...]] = ("id",)

    id: int | None = None
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        base = cls.__bases__[0] if cls.__bases__ else None
        inherited = getattr(base, "_hooks", {}) if base else {}
        hooks = {k: list(v) for k, v in inherited.items()}
        for name, member in cls.__dict__.items():
            hook = getattr(member, "_encinorm_hook", None)
            if hook:
                hooks.setdefault(hook, []).append(name)
        cls._hooks = hooks

    @classmethod
    def add_index(cls, idx) -> "Model":
        """Registra un índice (clase `Index`) para generarlo en `create_table`."""
        cls._indexes = list(cls._indexes) + [idx]
        return cls

    def __init__(self, db: Db = None, **kwargs):
        super().__init__(**kwargs)
        _set_private(self, "_db", db)
        _set_private(self, "__exists", False)
        _set_private(self, "__loading", False)
        _set_private(self, "_references", {})
        _set_private(self, "_has_many", {})
        fields = type(self).model_fields
        _set_private(
            self,
            "__dirties",
            [k for k in kwargs if k in fields and not k.startswith("_")],
        )
        for name, spec in type(self)._references_def.items():
            self.add_reference(
                name, spec["model"], spec["match_keys"], spec.get("on_delete")
            )
        for name, spec in type(self)._has_many_def.items():
            self.add_has_many(name, spec["model"], spec["foreign_key"])

    def __setattr__(self, name, value):
        loading = bool(self.__dict__.get("__loading", False))
        is_field = name in type(self).model_fields and not name.startswith("_")
        if is_field and not loading:
            current = self.__dict__.get(name, _MISSING)
            if current is _MISSING or current != value:
                dirties = list(self.__dict__.get("__dirties", []) or [])
                if name not in dirties:
                    dirties.append(name)
                    _set_private(self, "__dirties", dirties)
        super().__setattr__(name, value)

    def _get_db(self) -> "Db":
        """Resuelve (y cachea) la conexión del modelo.

        Si no se pasó `db` al construirlo, se resuelve de forma implícita:
        transacción activa del pool → `bind()`/`session()` → `set_default_db()`.
        """
        db = object.__getattribute__(self, "_db")
        if db is None:
            db = resolve_db()
            _set_private(self, "_db", db)
        return db

    # --- estado (acceso recomendado con guion simple) ---
    @property
    def _exists(self) -> bool:
        return object.__getattribute__(self, "__exists")

    @property
    def _dirties(self) -> list:
        return object.__getattribute__(self, "__dirties")

    # --- mapeo de columnas ---
    @classmethod
    def _column_map(cls) -> dict:
        mapping = _COLUMN_MAPS.get(cls)
        if mapping is None:
            mapping = cls._build_column_map()
            _COLUMN_MAPS[cls] = mapping
        return mapping

    @classmethod
    def _build_column_map(cls) -> dict:
        if cls._table and not _IDENTIFIER_RE.match(cls._table):
            raise ValueError(f"nombre de tabla inválido: {cls._table!r}")
        mapping = {}
        for name, info in cls.model_fields.items():
            if name.startswith("_"):
                continue
            if name in cls._fields_disabled:
                continue
            col = name
            for meta in getattr(info, "metadata", None) or []:
                col_name = getattr(meta, "name", None)
                if col_name:
                    if not _IDENTIFIER_RE.match(col_name):
                        raise ValueError(f"nombre de columna inválido: {col_name!r}")
                    col = col_name
            mapping[name] = col
        return mapping

    @classmethod
    def _col(cls, field: str) -> str:
        return cls._column_map().get(field, field)

    @classmethod
    def _field_of(cls, col: str):
        for field, c in cls._column_map().items():
            if c == col:
                return field
        return col

    @classmethod
    def _pk_fields(cls) -> tuple[str, ...]:
        """Nombres de campo (lógicos) que forman la clave primaria."""
        return tuple(getattr(cls, "_primary_key", ("id",)))

    @classmethod
    def _pk_cols(cls) -> tuple[str, ...]:
        """Columnas físicas de la clave primaria (respetando `Column.name`)."""
        return tuple(cls._col(f) for f in cls._pk_fields())

    @classmethod
    def _is_auto_pk(cls) -> bool:
        """True si la PK es el surrogate auto-incremental ``id``."""
        return cls._pk_fields() == ("id",)

    @classmethod
    def _new_instance(cls, db: Db) -> "Model":
        obj = cls.model_construct()
        _set_private(obj, "_db", db)
        _set_private(obj, "__exists", False)
        _set_private(obj, "__dirties", [])
        _set_private(obj, "__loading", True)
        _set_private(obj, "_references", {})
        _set_private(obj, "_has_many", {})
        for name, spec in cls._references_def.items():
            obj.add_reference(name, spec["model"], spec["match_keys"], spec.get("on_delete"))
        for name, spec in cls._has_many_def.items():
            obj.add_has_many(name, spec["model"], spec["foreign_key"])
        return obj

    def _from_db(self, field: str, value):
        if value is None:
            return None
        info = type(self).model_fields.get(field)
        if info is None:
            return value
        base = _base_type(info.annotation)
        if base is datetime:
            if isinstance(value, str):
                value = datetime.fromisoformat(value)
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
            return value
        if base is date and isinstance(value, str):
            return date.fromisoformat(value)
        if base is bool and isinstance(value, int):
            return bool(value)
        if base is Decimal and not isinstance(value, Decimal):
            return Decimal(str(value))
        if base in (dict, list) and isinstance(value, str):
            return json.loads(value)
        return value

    @staticmethod
    def _normalize_keys(keys, default=("id",)):
        if keys is None:
            keys = default
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split(",") if k.strip()]
        return list(keys)

    # --- referencias ---
    def add_reference(self, name, model_class, match_keys, on_delete=None) -> "Model":
        if name in self._references or name in self._has_many:
            raise DuplicateReferenceError(f"la referencia '{name}' ya existe")
        if name in type(self).model_fields:
            raise DuplicateReferenceError(f"'{name}' colisiona con un campo del modelo")
        match_keys = dict(match_keys)
        if set(match_keys.keys()) != set(model_class._pk_fields()):
            raise RelationshipError(
                f"match_keys {sorted(match_keys.keys())!r} no coinciden con la "
                f"clave primaria {model_class._pk_fields()!r} de {model_class.__name__}"
            )
        self._references[name] = Reference(name, model_class, match_keys, on_delete)
        return self

    def add_has_many(self, name, model_class, foreign_key) -> "Model":
        if name in self._has_many or name in self._references:
            raise DuplicateReferenceError(f"la relación '{name}' ya existe")
        if name in type(self).model_fields:
            raise DuplicateReferenceError(f"'{name}' colisiona con un campo del modelo")
        hm = HasMany(name, model_class, foreign_key)
        if set(hm.match_keys.keys()) != set(type(self)._pk_fields()):
            raise RelationshipError(
                f"foreign_key de '{name}' no coincide con la clave primaria "
                f"{type(self)._pk_fields()!r} de {type(self).__name__}"
            )
        self._has_many[name] = hm
        return self

    def __getitem__(self, name):
        if name in self._has_many:
            return self._resolve_has_many(name)
        return self._resolve_reference(name)

    async def _resolve_reference(self, name) -> "Model":
        ref = self._references[name]
        key_vals = {remote: getattr(self, local) for remote, local in ref.match_keys.items()}
        if ref._cached is not None and ref._cached_keys == key_vals:
            return ref._cached
        remote_kwargs = {remote: key_vals[remote] for remote in ref.match_keys}
        obj = ref.model_class(db=self._get_db(), **remote_kwargs)
        obj = await obj.load(keys=list(ref.match_keys.keys()))
        ref._cached = obj
        ref._cached_keys = key_vals
        return obj

    async def _resolve_has_many(self, name) -> list:
        from .filter import Filter

        hm = self._has_many[name]
        key_vals = tuple(getattr(self, p) for p in hm.match_keys)
        if hm._cached is not None and hm._cached_key == key_vals:
            return hm._cached

        f = None
        for parent_f, child_f in hm.match_keys.items():
            eq = Filter.eq(child_f, getattr(self, parent_f))
            f = eq if f is None else f & eq
        cursor = hm.model_class.model_construct()
        _set_private(cursor, "_db", self._get_db())
        children = await cursor.search(f)
        hm._cached = children
        hm._cached_key = key_vals
        return children

    # --- hooks ---
    async def _run_hooks(self, hook_name: str, *args):
        for method_name in type(self)._hooks.get(hook_name, []):
            await getattr(self, method_name)(*args)

    async def _transactional(self, action: str, fn):
        await self._run_hooks(f"before_{action}")

        async def attempt():
            async with self._get_db().transaction():
                result = await fn()
                await self._run_hooks("before_commit", action)
                return result

        try:
            result = await self._get_db().retry(attempt)
        except Exception:
            await self._run_hooks("after_transaction_fail", action)
            raise
        await self._run_hooks("after_commit")
        return result

    # --- validación ---
    @classmethod
    def _field_adapter(cls, field: str):
        per_class = _FIELD_ADAPTERS.get(cls)
        if per_class is None:
            per_class = {}
            _FIELD_ADAPTERS[cls] = per_class
        adapter = per_class.get(field)
        if adapter is None:
            info = cls.model_fields[field]
            metadata = getattr(info, "metadata", None) or []
            annotation = Annotated[info.annotation, *metadata] if metadata else info.annotation
            adapter = TypeAdapter(annotation)
            per_class[field] = adapter
        return adapter

    async def validate(self, fields=None) -> dict | None:
        model = type(self)
        model_fields = model.model_fields
        target = list(model_fields) if fields is None else [f for f in fields if f in model_fields]
        errors = {}
        for field in target:
            try:
                model._field_adapter(field).validate_python(getattr(self, field, None))
            except PydanticValidationError as exc:
                e = exc.errors()[0]
                errors[field] = f"{e['msg']} | valor actual {e.get('input')}"
        return errors or None

    # --- CRUD ---
    async def insert(self, *, ignore_duplicated: bool = False, replace: bool = False) -> int:
        errs = await self.validate()
        if errs:
            raise ValidationError(errs)
        now = datetime.now(timezone.utc)
        _set_private(self, "__loading", True)
        self.created_at = now
        self.updated_at = now
        _set_private(self, "__loading", False)

        auto = type(self)._is_auto_pk()
        data = {}
        for field, col in self._column_map().items():
            if auto and field == "id":
                continue
            data[col] = _serialize(getattr(self, field))

        async def do_insert():
            qry = self._get_db().insert(self._table, data, ignore_duplicated, replace)
            await self._get_db().execute(qry)
            return await self._get_db().last_id()

        new_id = await self._transactional("insert", do_insert)

        if auto:
            _set_private(self, "__loading", True)
            self.id = new_id
            _set_private(self, "__loading", False)
        _set_private(self, "__exists", True)
        _set_private(self, "__dirties", [])
        return new_id if auto else 0

    async def save(self, keys=None) -> int:
        """Inserta si no existe; actualiza si ya existe (find-or-create)."""
        keys = self._normalize_keys(keys, type(self)._pk_fields())
        existing = await self.load(keys=keys)
        if existing._exists:
            return await self.update(keys=keys)
        return await self.insert()

    @classmethod
    async def insert_many(cls, db=None, rows: list[dict] = None, *, chunk: int = 500) -> int:
        """Inserta varios registros en una transacción (multi-filas `VALUES`).

        Devuelve el total de filas insertadas. Los registros se particionan en
        *chunks* de `chunk` para no exceder el límite de parámetros del motor.
        """
        if not rows:
            return 0
        db = db or resolve_db()
        col_map = cls._column_map()
        auto = cls._is_auto_pk()
        fields = [f for f in col_map if not (auto and f == "id")]
        columns = [col_map[f] for f in fields]
        now = datetime.now(timezone.utc)

        total = 0
        async with db.transaction():
            for start in range(0, len(rows), chunk):
                batch = rows[start:start + chunk]
                params = []
                row_sqls = []
                for row in batch:
                    merged = dict(row)
                    if "enabled" in col_map and "enabled" not in merged:
                        merged["enabled"] = True
                    if "created_at" in col_map and "created_at" not in merged:
                        merged["created_at"] = now
                    if "updated_at" in col_map and "updated_at" not in merged:
                        merged["updated_at"] = now
                    base = len(params)
                    row_sqls.append(
                        "(" + ",".join(f"{{{base + i}}}" for i in range(len(columns))) + ")"
                    )
                    params.extend(_serialize(merged.get(f)) for f in fields)
                sql = (
                    f"INSERT INTO {cls._table} ({','.join(columns)}) VALUES "
                    + ",".join(row_sqls)
                )
                await db.execute(Query(sql, params))
                total += len(batch)
        return total

    async def upsert(self, conflict: list[str] | None = None, values: dict | None = None) -> int:
        """`INSERT ... ON CONFLICT (conflict) DO UPDATE ...` (o `ON DUPLICATE KEY`).

        `conflict` son nombres de **campo** que definen el conflicto (`None` ->
        clave primaria). `values` son los campos a actualizar en caso de conflicto
        (`None` -> todos los no conflictivos con el valor recién insertado).
        Devuelve filas afectadas.
        """
        if conflict is None:
            conflict = list(type(self)._pk_fields())
        now = datetime.now(timezone.utc)
        col_map = self._column_map()
        for auto in ("created_at", "updated_at"):
            if auto in col_map and getattr(self, auto) is None:
                _set_private(self, "__loading", True)
                setattr(self, auto, now)
                _set_private(self, "__loading", False)

        auto_pk = type(self)._is_auto_pk()
        data = {}
        for field, col in col_map.items():
            if auto_pk and field == "id":
                continue
            data[col] = _serialize(getattr(self, field))
        cols = list(data.keys())
        insert_vals = list(data.values())
        conflict_cols = [self._col(c) for c in conflict]

        dialect = getattr(self._get_db(), "dialect", "sqlite") or "sqlite"

        if values is None:
            created_col = col_map.get("created_at")
            update_cols = [c for c in cols if c not in conflict_cols and c != created_col]
            params = insert_vals
            if dialect == "mysql":
                set_sql = ", ".join(f"{c} = VALUES({c})" for c in update_cols)
            else:
                set_sql = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        else:
            mapped = {self._col(f): _serialize(v) for f, v in values.items()}
            update_cols = list(mapped.keys())
            params = insert_vals + list(mapped.values())
            offset = len(insert_vals)
            set_sql = ", ".join(
                f"{c} = {{{offset + i}}}" for i, c in enumerate(update_cols)
            )

        placeholders = ",".join(f"{{{i}}}" for i in range(len(cols)))
        if dialect == "mysql":
            sql = (
                f"INSERT INTO {self._table} ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON DUPLICATE KEY UPDATE {set_sql}"
            )
        else:
            sql = (
                f"INSERT INTO {self._table} ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT ({','.join(conflict_cols)}) DO UPDATE SET {set_sql}"
            )

        async def do_upsert():
            async with self._get_db().transaction():
                return await self._get_db().execute(Query(sql, params))

        count = await self._get_db().retry(do_upsert)
        _set_private(self, "__exists", True)
        _set_private(self, "__dirties", [])
        return count

    async def load(self, keys=None) -> "Model":
        keys = self._normalize_keys(keys, type(self)._pk_fields())
        params = []
        clauses = []
        for k in keys:
            col = self._col(k)
            clauses.append(f"{col} = {{{len(params)}}}")
            params.append(_serialize(getattr(self, k)))
        sql = f"SELECT * FROM {self._table} WHERE {' AND '.join(clauses)}"
        row = await self._get_db().fetch_one(Query(sql, params))

        obj = self._new_instance(self._get_db())
        if row is not None:
            for field, col in self._column_map().items():
                if col in row:
                    setattr(obj, field, self._from_db(field, row[col]))
            _set_private(obj, "__exists", True)
        else:
            _set_private(obj, "__exists", False)
        _set_private(obj, "__loading", False)
        _set_private(obj, "__dirties", [])
        return obj

    async def update(self, keys=None, data=None) -> int:
        keys = self._normalize_keys(keys, type(self)._pk_fields())
        if data is None:
            data = list(self.__dict__.get("__dirties", []) or [])
        else:
            data = list(data)
        if not data:
            data = [f for f in self._column_map() if f not in ("id", "created_at")]
        data = [f for f in data if f not in ("id", "created_at") and not f.startswith("_")]

        errs = await self.validate(fields=data)
        if errs:
            raise ValidationError(errs)

        key_dict = {}
        for k in keys:
            val = getattr(self, k)
            if val is None:
                raise FailOnUpdate(f"llave '{k}' sin valor para identificar el registro")
            key_dict[self._col(k)] = _serialize(val)

        values = {}
        for f in data:
            values[self._col(f)] = _serialize(getattr(self, f))
        values[self._col("updated_at")] = _serialize(datetime.now(timezone.utc))

        async def do_update():
            qry = self._get_db().update(self._table, key_dict, values)
            count = await self._get_db().execute(qry)
            if count == 0:
                raise FailOnUpdate(f"update en '{self._table}' no afectó ningún registro")
            return count

        count = await self._transactional("update", do_update)
        _set_private(self, "__dirties", [])
        return count

    async def delete(self, keys=None, physical: bool = False) -> bool:
        keys = self._normalize_keys(keys, type(self)._pk_fields())
        key_dict = {}
        for k in keys:
            val = getattr(self, k)
            if val is None:
                raise FailOnUpdate(f"llave '{k}' sin valor para identificar el registro")
            key_dict[self._col(k)] = _serialize(val)

        async def do_delete():
            if physical:
                qry = self._get_db().delete(self._table, key_dict)
            else:
                qry = self._get_db().update(self._table, key_dict, {self._col("enabled"): False})
            await self._get_db().execute(qry)

        await self._transactional("delete", do_delete)
        _set_private(self, "__exists", False)
        _set_private(self, "__dirties", [])
        return True

    def _effective_filter(self, filter, include_deleted: bool = False):
        """Combina el filtro del usuario con el soft-delete y el `scope` activo."""
        f = filter
        if not include_deleted and "enabled" in self._column_map():
            enabled = Filter.eq("enabled", True)
            f = enabled if f is None else f & enabled
        s = current_scope()
        if s is not None:
            f = s if f is None else f & s
        return f

    async def search(self, filter=None, columns=None, limit=None, page: int = 1,
                     sort_by: list | None = None, include_deleted: bool = False) -> list:
        columns = columns or ["*"]
        cols_sql = ", ".join(columns)
        filter = self._effective_filter(filter, include_deleted)
        where = ""
        params = []
        if filter is not None:
            mapped = filter.map_fields(self._column_map())
            frag, params = mapped.to_sql()
            where = f" WHERE {frag}"
        sql = f"SELECT {cols_sql} FROM {self._table}{where}"
        if sort_by:
            sql += f" ORDER BY {self._render_sort(sort_by)}"
        if limit is not None:
            offset = (page - 1) * limit
            sql += f" LIMIT {limit} OFFSET {offset}"
        rows = await self._get_db().fetch_all(Query(sql, params))

        results = []
        for row in rows:
            obj = self._new_instance(self._get_db())
            for col, value in row.items():
                field = self._field_of(col)
                if field in type(self).model_fields:
                    setattr(obj, field, self._from_db(field, value))
            _set_private(obj, "__loading", False)
            _set_private(obj, "__exists", True)
            _set_private(obj, "__dirties", [])
            results.append(obj)
        return results

    async def count(self, filter=None, include_deleted: bool = False) -> int:
        """Devuelve el número de registros que cumplen el filtro (para paginar)."""
        filter = self._effective_filter(filter, include_deleted)
        where = ""
        params = []
        if filter is not None:
            mapped = filter.map_fields(self._column_map())
            frag, params = mapped.to_sql()
            where = f" WHERE {frag}"
        sql = f"SELECT COUNT(*) FROM {self._table}{where}"
        row = await self._get_db().fetch_one(Query(sql, params))
        return row["COUNT(*)"] if row else 0

    async def paginate(self, filter=None, limit: int = 10, page: int = 1, columns=None,
                       sort_by: list | None = None, include_deleted: bool = False):
        """Devuelve un `Records` con la página y el total de registros del filtro."""
        from .records import Records

        total = await self.count(filter, include_deleted=include_deleted)
        rows = await self.search(filter, columns=columns, limit=limit, page=page,
                                 sort_by=sort_by, include_deleted=include_deleted)
        return Records(rows=rows, total=total, limit=limit, page=page)

    @classmethod
    def _render_sort(cls, sort_by) -> str:
        """Traduce una lista de orden a la cláusula `ORDER BY`.

        Cada elemento puede ser ``"campo"`` (ASC), ``"-campo"`` (DESC),
        ``"+campo"`` (ASC) o una tupla ``(campo, "asc" | "desc")``. Los nombres de
        campo se resuelven contra el mapa de columnas y se validan.
        """
        col_map = cls._column_map()
        parts = []
        for spec in sort_by:
            if isinstance(spec, (tuple, list)):
                if len(spec) != 2:
                    raise ValueError(f"especificación de orden inválida: {spec!r}")
                name, direction = spec
            else:
                s = str(spec).strip()
                if s.startswith("-"):
                    name, direction = s[1:], "DESC"
                elif s.startswith("+"):
                    name, direction = s[1:], "ASC"
                else:
                    name, direction = s, "ASC"
            col = col_map.get(name, name)
            if not _IDENTIFIER_RE.match(col):
                raise ValueError(f"columna de orden inválida: {col!r}")
            direction = str(direction).upper()
            if direction not in ("ASC", "DESC"):
                raise ValueError(f"dirección de orden inválida: {direction!r}")
            parts.append(f"{col} {direction}")
        return ", ".join(parts)

    def query(self):
        """Devuelve un `QueryBuilder` ligado a la conexión del modelo."""
        from .query_builder import QueryBuilder

        return QueryBuilder(type(self), self._get_db())

    async def create_table(self, engine: str = None):
        """Genera y aplica el DDL de la tabla (e índices) vía `to_ddl` + `migrate`."""
        from .types import indexes_ddl, to_ddl

        engine = engine or getattr(self._get_db(), "dialect", "sqlite") or "sqlite"
        ddl = to_ddl(type(self), engine)
        await self._get_db().migrate(f"create_{self._table}", Query(ddl, []))
        for name, idx_ddl in indexes_ddl(type(self), engine):
            await self._get_db().migrate(f"create_index_{name}", Query(idx_ddl, []))

    async def sync_schema(self, engine: str = None, drop_missing: bool = False,
                          alter_types: bool = False) -> dict:
        """Sincroniza el esquema con ``_column_map()`` vía ``ALTER TABLE``.

        Añade columnas faltantes; con ``drop_missing=True`` elimina las que ya no
        están en el modelo; con ``alter_types=True`` cambia el tipo de las columnas
        cuyo tipo difiere (no soportado en SQLite). Devuelve
        ``{"added": [...], "dropped": [...], "changed": [...]}``.
        """
        from .types import _field_datatype, ddl_type

        engine = engine or getattr(self._get_db(), "dialect", "sqlite") or "sqlite"
        existing = await self._existing_columns_info(engine)
        model_cols = self._column_map()

        added = []
        for field, col in model_cols.items():
            if col in existing or (field == "id" and type(self)._is_auto_pk()):
                continue
            dt = _field_datatype(type(self), field, type(self).model_fields[field])
            ddl = ddl_type(dt, engine)
            await self._get_db().execute(
                Query(f"ALTER TABLE {self._table} ADD COLUMN {col} {ddl}", [])
            )
            added.append(col)

        dropped = []
        if drop_missing:
            for col in set(existing) - set(model_cols.values()):
                await self._get_db().execute(
                    Query(f"ALTER TABLE {self._table} DROP COLUMN {col}", [])
                )
                dropped.append(col)

        changed = []
        if alter_types:
            for c in (await self.diff_schema(engine))["changed"]:
                col = c["column"]
                ddl = ddl_type(c["model"], engine)
                if engine == "postgresql":
                    await self._get_db().execute(
                        Query(f"ALTER TABLE {self._table} ALTER COLUMN {col} TYPE {ddl}", [])
                    )
                elif engine == "mysql":
                    await self._get_db().execute(
                        Query(f"ALTER TABLE {self._table} MODIFY COLUMN {col} {ddl}", [])
                    )
                else:
                    raise NotImplementedError(
                        "alter_types no soporta SQLite (requiere recrear la tabla)"
                    )
                changed.append(col)

        return {"added": added, "dropped": dropped, "changed": changed}

    async def diff_schema(self, engine: str = None) -> dict:
        """Compara el modelo contra la BD sin aplicar cambios.

        Devuelve ``{"added": [...], "dropped": [...], "changed": [...]}``; cada
        elemento de ``changed`` es ``{"field", "column", "model", "db"}``.
        """
        from encinorm.introspection.types import _normalize

        from .types import _field_datatype

        engine = engine or getattr(self._get_db(), "dialect", "sqlite") or "sqlite"
        existing = await self._existing_columns_info(engine)
        model_cols = self._column_map()

        added = []
        dropped = [c for c in existing if c not in model_cols.values()]
        changed = []
        for field, col in model_cols.items():
            if field == "id" and type(self)._is_auto_pk():
                continue
            if col not in existing:
                added.append(col)
                continue
            dt = _field_datatype(type(self), field, type(self).model_fields[field])
            db_dt = _normalize(existing[col])[0]
            if not _types_compatible(dt, db_dt, engine):
                changed.append({"field": field, "column": col, "model": dt, "db": db_dt})

        return {"added": added, "dropped": dropped, "changed": changed}

    async def _existing_columns_info(self, engine: str) -> dict:
        """Devuelve ``{nombre_columna: tipo_crudo}`` de la tabla en la BD."""
        if engine == "sqlite":
            rows = await self._get_db().fetch_all(Query(f"PRAGMA table_info({self._table})", []))
            return {r["name"]: (r["type"] or "") for r in rows}
        if engine == "mysql":
            rows = await self._get_db().fetch_all(Query(f"SHOW COLUMNS FROM {self._table}", []))
            return {r["Field"]: r["Type"] for r in rows}
        if engine == "postgresql":
            rows = await self._get_db().fetch_all(
                Query(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = {0}",
                    [self._table],
                )
            )
            return {r["column_name"]: r["data_type"] for r in rows}
        raise NotImplementedError(f"diff_schema no soporta el motor {engine!r}")

    async def _existing_columns(self, engine: str) -> set:
        return set((await self._existing_columns_info(engine)).keys())

    @classmethod
    async def batch_reference(cls, models, name: str):
        """Carga la referencia `name` para todos los `models` en UNA consulta.

        Evita el N+1 al resolver la misma referencia sobre una colección.
        Soporta referencias de una o varias llaves (FK compuesta).
        """
        models = list(models)
        if not models:
            return
        ref = models[0]._references.get(name)
        if ref is None:
            raise RelationshipError(f"referencia '{name}' no registrada")

        from .filter import Filter

        remote_fields = list(ref.match_keys.keys())
        local_fields = [ref.match_keys[r] for r in remote_fields]

        if len(remote_fields) == 1:
            remote_field, local_field = remote_fields[0], local_fields[0]
            key_vals = {getattr(m, local_field) for m in models}
            key_vals.discard(None)
            if not key_vals:
                return
            rows = await ref.model_class(db=models[0]._get_db()).search(
                Filter.in_(remote_field, list(key_vals))
            )
            remote_index = {getattr(r, remote_field): r for r in rows}
            for m in models:
                val = getattr(m, local_field)
                if val is not None and val in remote_index:
                    m_ref = m._references[name]
                    m_ref._cached = remote_index[val]
                    m_ref._cached_keys = {remote_field: val}
            return

        pairs = {
            tuple(getattr(m, lf) for lf in local_fields)
            for m in models
            if all(getattr(m, lf) is not None for lf in local_fields)
        }
        if not pairs:
            return

        cond = None
        for pair in pairs:
            sub = None
            for rf, val in zip(remote_fields, pair):
                eq = Filter.eq(rf, val)
                sub = eq if sub is None else sub & eq
            cond = sub if cond is None else cond | sub

        rows = await ref.model_class(db=models[0]._get_db()).search(cond)
        remote_index = {tuple(getattr(r, rf) for rf in remote_fields): r for r in rows}
        for m in models:
            key = tuple(getattr(m, lf) for lf in local_fields)
            if key in remote_index:
                m_ref = m._references[name]
                m_ref._cached = remote_index[key]
                m_ref._cached_keys = dict(zip(remote_fields, key))

    @classmethod
    async def batch_has_many(cls, models, name: str):
        """Carga la colección `has_many` `name` para todos los `models` en UNA consulta.

        Evita el N+1 al resolver la misma colección sobre una lista de padres.
        Soporta FK simple y compuesta.
        """
        from .filter import Filter

        models = list(models)
        if not models:
            return
        hm = models[0]._has_many.get(name)
        if hm is None:
            raise RelationshipError(f"has_many '{name}' no registrada")

        parent_fields = list(hm.match_keys.keys())
        child_fields = [hm.match_keys[p] for p in parent_fields]

        if len(parent_fields) == 1:
            parent_field, child_field = parent_fields[0], child_fields[0]
            parent_ids = {getattr(m, parent_field) for m in models}
            parent_ids.discard(None)
            if not parent_ids:
                return

            cursor = hm.model_class.model_construct()
            _set_private(cursor, "_db", models[0]._get_db())
            children = await cursor.search(Filter.in_(child_field, list(parent_ids)))

            groups = {}
            for c in children:
                groups.setdefault(getattr(c, child_field), []).append(c)
            for m in models:
                key = getattr(m, parent_field)
                m._has_many[name]._cached = groups.get(key, [])
                m._has_many[name]._cached_key = (key,)
            return

        pairs = {
            tuple(getattr(m, p) for p in parent_fields)
            for m in models
            if all(getattr(m, p) is not None for p in parent_fields)
        }
        if not pairs:
            return

        cond = None
        for pair in pairs:
            sub = None
            for cf, val in zip(child_fields, pair):
                eq = Filter.eq(cf, val)
                sub = eq if sub is None else sub & eq
            cond = sub if cond is None else cond | sub

        cursor = hm.model_class.model_construct()
        _set_private(cursor, "_db", models[0]._get_db())
        children = await cursor.search(cond)

        groups = {}
        for c in children:
            key = tuple(getattr(c, cf) for cf in child_fields)
            groups.setdefault(key, []).append(c)
        for m in models:
            key = tuple(getattr(m, p) for p in parent_fields)
            m._has_many[name]._cached = groups.get(key, [])
            m._has_many[name]._cached_key = key

