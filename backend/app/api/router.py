from fastapi import APIRouter

from app.api import auth, files, projects, users, workflow


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(files.router)
api_router.include_router(users.router)
api_router.include_router(workflow.router)

