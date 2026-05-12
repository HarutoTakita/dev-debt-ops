from fastapi import APIRouter
from scalar_fastapi import Theme, get_scalar_api_reference

router = APIRouter()


@router.get("/docs", include_in_schema=False)
async def scalar_docs():
    """Render the Scalar API reference at `/api/docs` (dev + stg only)."""
    return get_scalar_api_reference(
        openapi_url="/api/openapi.json",
        title="Full-Stack App Template",
        theme=Theme.KEPLER,
        dark_mode=True,
        default_open_all_tags=True,
        order_schema_properties_by="preserve",
        hidden_clients={
            "c": True,
            "clojure": True,
            "csharp": True,
            "dart": True,
            "fsharp": True,
            "go": True,
            "http": True,
            "java": True,
            "js": True,
            "kotlin": True,
            "objc": True,
            "ocaml": True,
            "php": True,
            "powershell": True,
            "r": True,
            "ruby": True,
            "rust": True,
            "swift": True,
            "shell": ["httpie", "wget"],
            "python": ["python3", "requests"],
            "node": ["axios", "ofetch", "undici"],
        },
    )
