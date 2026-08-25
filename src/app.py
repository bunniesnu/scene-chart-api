from fastapi import FastAPI

from src.routes import charts, debug

app = FastAPI()

app.include_router(charts.router)
app.include_router(debug.router)