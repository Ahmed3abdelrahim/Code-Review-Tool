from fastapi import HTTPException


def validate_rate(percent: float) -> float:
    if not 0 <= percent <= 100:
        raise HTTPException(status_code=422, detail="rate must be between 0 and 100")
    return percent
