import os
from fastapi import FastAPI, UploadFile, File, HTTPException, Response
from typing import Optional

# Adjust imports to the new service structure
from providers.file_storage import FileStorageProvider
from providers.local_file_storage import LocalFileStorage
from providers.gcs_file_storage import GCSFileStorage

# --- Pydantic Models & API ---
# (We might add models later if we need more complex request/response bodies)

# --- FastAPI Application ---
app = FastAPI(title="Storage Service")

# --- Storage Provider Initialization ---
def get_storage_provider() -> FileStorageProvider:
    provider_name = os.environ.get("STORAGE_PROVIDER", "local")

    if provider_name == "gcs":
        bucket_name = os.environ.get("GCS_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME must be set for the GCS provider")
        print(f"Using GCSFileStorage with bucket: {bucket_name}")
        return GCSFileStorage(bucket_name=bucket_name)

    elif provider_name == "local":
        root_dir = os.environ.get("LOCAL_STORAGE_ROOT_DIR", "/data")
        print(f"Using LocalFileStorage with root directory: {root_dir}")
        return LocalFileStorage(root_dir=root_dir)

    else:
        raise ValueError(f"Unsupported storage provider: {provider_name}")

storage_provider = get_storage_provider()

# --- API Endpoints ---
@app.post("/files/{path:path}")
async def upload_file(path: str, file: UploadFile = File(...)):
    """
    Uploads a file to the specified path in the configured storage provider.
    """
    try:
        contents = await file.read()
        await storage_provider.save(path, contents)
        return {"message": "File uploaded successfully", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.get("/files/{path:path}", response_class=Response)
async def download_file(path: str):
    """
    Downloads a file from the specified path.
    """
    try:
        file_content = await storage_provider.load(path)
        if file_content is None:
            raise HTTPException(status_code=404, detail="File not found")
        # You might want to determine the media type more intelligently
        return Response(content=file_content, media_type="application/octet-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")

@app.delete("/files/{path:path}")
async def delete_file(path: str):
    """
    Deletes a file from the specified path.
    """
    try:
        # Assuming the provider's delete method returns True on success
        if not await storage_provider.delete(path):
            raise HTTPException(status_code=404, detail="File not found or could not be deleted")
        return {"message": "File deleted successfully", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@app.get("/")
def read_root():
    return {"Hello": "Storage"}
