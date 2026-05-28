import math
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def success_response(data) -> dict:
    return {"success": True, "data": data, "meta": {"timestamp": utc_now_iso()}}


def paginate_response(data: list, total: int, page: int, limit: int) -> dict:
    pages = math.ceil(total / limit) if total > 0 else 0
    return {
        "success": True,
        "data": data,
        "meta": {"page": page, "limit": limit, "total": total, "pages": pages, "timestamp": utc_now_iso()},
    }


class StatusUpdateRequest(BaseModel):
    status: str = Field(default="completed", pattern="^(pending|completed)$")

    model_config = {
        "json_schema_extra": {
            "example": {"status": "completed"}
        }
    }
