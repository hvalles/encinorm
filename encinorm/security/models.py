"""Modelos de seguridad: `Rol`, `Roldet` y `RolUsuario`.

Las tres tablas son `Model` de encinorm (persistentes, validables, con
`enabled`/`created_at`/`updated_at` heredados y borrado lógico).
"""

from encinorm.model import Model, make_constraint

STR_50 = make_constraint(str, max_length=50)
STR_100 = make_constraint(str, max_length=100)

# Roles semilla (el id lo asigna el autoincremento en orden de inserción).
SEED_ROLES = ["Administrador", "Usuario Interno", "Público"]


class Rol(Model):
    _table = "roles"
    rol: STR_100(required=True)      # 1:Administrador, 2:Usuario Interno, 3:Público


class Roldet(Model):
    _table = "roles_det"
    rol_id: int | None = None
    modelo: STR_100(required=True)          # nombre de tabla (`_table`) o "*"
    # Prefijo `perm_` para no colisionar con los métodos de `Model`
    # (`update`/`delete`) ni con palabras reservadas SQL (`create`).
    perm_read: bool | None = None
    perm_create: bool | None = None
    perm_update: bool | None = None
    perm_delete: bool | None = None         # borrado lógico
    perm_remove: bool | None = None         # borrado físico


class RolUsuario(Model):
    _table = "roles_usuario"
    rol_id: int | None = None
    user_id: STR_50(required=True)          # identidad externa (claim `sub` del JWT)
    orden: int | None = None                # prioridad; menor = primero


async def create_tables(db, engine: str | None = None) -> None:
    """Crea las tablas de seguridad (`Rol`, `Roldet`, `RolUsuario`).

    `create_table()` es un método de instancia; como `Rol.rol`, `Roldet.modelo` y
    `RolUsuario.user_id` son obligatorios, se construye una instancia sin
    validación (`model_construct`) solo para invocar el DDL.
    """
    for model in (Rol, Roldet, RolUsuario):
        obj = model.model_construct()
        object.__setattr__(obj, "_db", db)
        await obj.create_table(engine)


async def seed_roles(db) -> list[int]:
    """Inserta los roles por defecto si la tabla está vacía.

    Devuelve los `id` asignados (1, 2, 3 en una tabla recién creada).
    """
    probe = Rol.model_construct()
    object.__setattr__(probe, "_db", db)
    if await probe.count() > 0:
        return []
    ids = []
    for nombre in SEED_ROLES:
        ids.append(await Rol(db, rol=nombre).insert())
    return ids
