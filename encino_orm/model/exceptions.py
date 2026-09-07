from encino_orm.exceptions import EncinoOrmError


class ModelError(EncinoOrmError):
    pass


class FailOnUpdate(ModelError):
    pass


class ValidationError(ModelError):
    pass


class NotFoundError(ModelError):
    pass


class RelationshipError(ModelError):
    pass


class DuplicateReferenceError(RelationshipError):
    pass


class DuplicateAliasError(ModelError):
    pass


class DuplicateColumnAliasError(ModelError):
    pass
