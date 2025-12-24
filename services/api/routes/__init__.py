from fastapi import APIRouter

from .saves import router as saves_router
from .tasks import router as tasks_router
from .admin import router as admin_router
from .ht import router as ht_router
from .misc import router as misc_router
from .commands import router as commands_router


router = APIRouter()
router.include_router(misc_router)
router.include_router(saves_router)
router.include_router(tasks_router)
router.include_router(admin_router)
router.include_router(ht_router)
router.include_router(commands_router)
