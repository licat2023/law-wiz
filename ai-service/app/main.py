from fastapi import FastAPI

from app.api.v1.agent import router

app = FastAPI(
    title="智法宝 AI Service"
)

app.include_router(router)