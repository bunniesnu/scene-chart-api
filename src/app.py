from fastapi import FastAPI

from src.routes import debug

app = FastAPI()

app.include_router(debug.router)