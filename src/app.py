from fastapi import FastAPI

from src.routes import artist, charts

app = FastAPI()

app.include_router(artist.router)
app.include_router(charts.router)