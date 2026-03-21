from typing import Any, Optional


def success_response(data: Any) -> dict:
    return {"success": True, "data": data}


def paginated_response(data: Any, total: int, page: int, limit: int) -> dict:
    import math
    return {
        "success": True,
        "data": data,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "pages": math.ceil(total / limit) if limit > 0 else 1,
        },
    }


def error_response(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}
