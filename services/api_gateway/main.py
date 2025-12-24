import os
import httpx
from fastapi import FastAPI, Request, Response, HTTPException

app = FastAPI(title="API Gateway")

# Get service URLs from environment variables
ARCHIVER_URL = os.environ.get("ARCHIVER_URL", "http://archiver:8000")
DATA_URL = os.environ.get("DATA_URL", "http://data:8000")
STORAGE_URL = os.environ.get("STORAGE_URL", "http://storage:8000")

async def _reverse_proxy(request: Request, target_url: str):
    """Helper function to perform the reverse proxy request."""
    async with httpx.AsyncClient() as client:
        headers = dict(request.headers)
        headers.pop("host", None)
        body = await request.body()

        rp_req = client.build_request(
            request.method,
            target_url,
            headers=headers,
            params=request.query_params,
            content=body,
            timeout=None,
        )
        rp_resp = await client.send(rp_req, stream=True)

        return Response(
            content=rp_resp.content,
            status_code=rp_resp.status_code,
            headers=dict(rp_resp.headers),
        )

@app.api_route("/{path:path}")
async def gateway_proxy(request: Request, path: str):
    """
    Main gateway logic. Routes requests to the appropriate backend service
    based on the request path.
    """
    if path == "archive":
        target_url = f"{ARCHIVER_URL}/archive"
        return await _reverse_proxy(request, target_url)

    if path.startswith("archiver/"):
        target_path = path.replace("archiver/", "", 1)
        target_url = f"{ARCHIVER_URL}/{target_path}"
        return await _reverse_proxy(request, target_url)

    elif path.startswith("data/"):
        target_path = path.replace("data/", "", 1)
        target_url = f"{DATA_URL}/{target_path}"
        return await _reverse_proxy(request, target_url)

    elif path.startswith("storage/"):
        target_path = path.replace("storage/", "", 1)
        target_url = f"{STORAGE_URL}/{target_path}"
        return await _reverse_proxy(request, target_url)

    else:
        raise HTTPException(status_code=404, detail=f"Endpoint not found for path: {path}")
