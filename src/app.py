from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from os import getenv

from src.routes import artist, charts, reports

app = FastAPI()

origins = getenv("FRONTEND_HOSTS", "").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(artist.router)
app.include_router(charts.router)
app.include_router(reports.router)