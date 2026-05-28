from bson import ObjectId


def resolve_user_role(user: dict) -> str:
    role = user.get("role")
    roles = user.get("roles", [])
    if isinstance(roles, list) and "admin" in roles:
        return "admin"

    if role in {"user", "admin"}:
        return role

    return "user"


def normalize_document(document: dict) -> dict:
    normalized = dict(document)
    if "_id" in normalized:
        normalized["id"] = str(normalized.pop("_id"))
    for key, value in list(normalized.items()):
        if isinstance(value, ObjectId):
            normalized[key] = str(value)
    return normalized
