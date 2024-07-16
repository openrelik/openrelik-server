from fastapi import APIRouter

from config import config

router = APIRouter()


@router.get("/system/")
def get_system_config():
    llms = config.get("llms", [])
    active_llms = [
        service for service in llms.values() if service.get("enabled", False)
    ]
    data_types = [
        "text/csv",
        "text/json",
    ]
    return {"active_llms": active_llms, "data_types": data_types}
