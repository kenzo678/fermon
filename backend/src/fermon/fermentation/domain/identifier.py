from fermon.fermentation.domain.errors import InvalidIdentifierError


def normalize_id(field: str, raw: object) -> str:
    """Strip an identifier; reject non-strings and blanks. Single source of truth."""
    if not isinstance(raw, str):
        raise InvalidIdentifierError(field, "must be a string")
    cleaned = raw.strip()
    if not cleaned:
        raise InvalidIdentifierError(field, "must not be blank")
    return cleaned
