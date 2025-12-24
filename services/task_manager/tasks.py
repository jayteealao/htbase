import os
import logging
import httpx
from celery import shared_task
from task_manager import ArchiverTaskManager # This will be refactored
from archivers.factory import ArchiverFactory
from core.config import get_settings
from core.command_runner import CommandRunner
from tempfile import TemporaryDirectory
from pathlib import Path

# --- Service URLs ---
DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://data:8000")
STORAGE_SERVICE_URL = os.environ.get("STORAGE_SERVICE_URL", "http://storage:8000")

# --- Configure logging ---
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- Refactored Task Manager ---
# In this new architecture, the Task Manager's job is to orchestrate the workflow
# by calling other services. It no longer has direct access to the database or file system.
class MicroserviceArchiverTaskManager:
    def __init__(self, settings, data_client, storage_client, command_runner):
        self.settings = settings
        self.data_client = data_client
        self.storage_client = storage_client
        self.command_runner = command_runner
        # We need a way to create archivers without direct db/storage access
        # The factory needs to be adapted or replaced. For now, we assume it can be created.
        self.archiver_factory = ArchiverFactory(
            settings, command_runner, file_storage_providers=[], db_storage=None
        )
        self.archiver_factory.register_all() # Method to register archivers like in the monolith

    def run_archive(self, archived_url_id: int, url: str):
        logger.info(f"Starting archive process for URL ID {archived_url_id}: {url}")

        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            for archiver_name, archiver in self.archiver_factory.create_all().items():
                logger.info(f"Running archiver: {archiver_name}")
                try:
                    # The archiver's `archive` method will save files to the local `output_dir`
                    result = archiver.archive(url, output_dir=output_dir)

                    if result.success and result.saved_path:
                        # Upload artifact to Storage Service
                        artifact_path = f"{archived_url_id}/{archiver_name}/{Path(result.saved_path).name}"
                        with open(result.saved_path, "rb") as f:
                            files = {'file': (artifact_path, f)}
                            self.storage_client.post(f"/files/{artifact_path}", files=files)

                        # Create artifact record in Data Service
                        artifact_data = {
                            "archived_url_id": archived_url_id,
                            "archiver": archiver_name,
                            "success": True,
                            "saved_path": artifact_path,
                            "status": "completed",
                            "size_bytes": os.path.getsize(result.saved_path),
                        }
                        self.data_client.post("/artifacts", json=artifact_data)
                        logger.info(f"Successfully processed and saved artifact for {archiver_name}")

                    else:
                        logger.error(f"Archiver {archiver_name} failed. Exit code: {result.exit_code}")
                        # Optionally create a failed artifact record

                except Exception as e:
                    logger.error(f"An error occurred while running archiver {archiver_name}: {e}")

@shared_task(name='task_manager.tasks.start_archive')
def start_archive(url: str, item_id: str):
    logger.info(f"Received archive task for URL: {url} with ID: {item_id}")

    with httpx.Client() as data_client, httpx.Client() as storage_client:
        # Set base URLs for clients
        data_client.base_url = DATA_SERVICE_URL
        storage_client.base_url = STORAGE_SERVICE_URL

        try:
            # 1. Create URL record
            response = data_client.post("/urls", json={"url": url, "item_id": item_id, "name": "Archive"})
            response.raise_for_status()
            url_record = response.json()
            archived_url_id = url_record['id']
            logger.info(f"Created ArchivedUrl record with ID: {archived_url_id}")

            # 2. Run the archive process
            settings = get_settings()
            command_runner = CommandRunner(debug=True)
            task_manager = MicroserviceArchiverTaskManager(settings, data_client, storage_client, command_runner)
            task_manager.run_archive(archived_url_id, url)

            logger.info(f"Archive process for {url} completed successfully.")
            return {"status": "success", "archived_url_id": archived_url_id}

        except Exception as e:
            logger.error(f"Archive task failed for URL {url}: {e}")
            return {"status": "error", "message": str(e)}
