from encinorm.exceptions import EncinormError


class ModelError(EncinormError):
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
