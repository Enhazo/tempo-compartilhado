from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'clima.db').as_posix()}")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Favorite(Base):
    __tablename__ = "favorite_cities"
    __table_args__ = (UniqueConstraint("latitude", "longitude", name="uq_favorite_coordinates"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    country: Mapped[str] = mapped_column(String(80), default="")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


app = FastAPI(title="Tempo Compartilhado", description="Explore e compare o clima em cidades do mundo todo", version="1.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def get_db():
    with SessionLocal() as db:
        yield db


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0), headers={"User-Agent": "ClimaVivo/1.0 (educational portfolio)"})


async def geocode_city(name: str) -> list[dict]:
    async with http_client() as client:
        try:
            response = await client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": name, "count": 6, "language": "pt", "format": "json"})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Não foi possível consultar o serviço de localização agora.") from exc
    results = response.json().get("results", [])
    return [{"name": item["name"], "country": item.get("country", ""), "admin1": item.get("admin1", ""), "latitude": item["latitude"], "longitude": item["longitude"], "timezone": item.get("timezone", "UTC")} for item in results]


def weather_description(code: int) -> str:
    if code == 0:
        return "Céu limpo"
    if code in (1, 2):
        return "Parcialmente nublado"
    if code == 3:
        return "Nublado"
    if code in (45, 48):
        return "Neblina"
    if code in (51, 53, 55, 56, 57):
        return "Garoa"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Chuva"
    if code in (71, 73, 75, 77, 85, 86):
        return "Neve"
    if code in (95, 96, 99):
        return "Trovoada"
    return "Condição variável"


async def get_forecast(latitude: float, longitude: float) -> dict:
    async with http_client() as client:
        try:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": latitude, "longitude": longitude, "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m", "hourly": "temperature_2m,precipitation_probability,weather_code", "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max", "timezone": "auto", "forecast_days": 5})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Não foi possível consultar a previsão agora. Tente novamente em instantes.") from exc
    return response.json()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/cities/search")
async def search_cities(q: str):
    q = q.strip()
    if len(q) < 2 or len(q) > 100:
        raise HTTPException(status_code=422, detail="Informe de 2 a 100 caracteres para pesquisar uma cidade.")
    return {"results": await geocode_city(q)}


@app.get("/api/forecast")
async def forecast(latitude: float, longitude: float):
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail="Coordenadas fora do intervalo válido.")
    return await get_forecast(latitude, longitude)


@app.get("/api/favorites")
def list_favorites(db: Session = Depends(get_db)):
    return [{"id": city.id, "name": city.name, "country": city.country, "latitude": city.latitude, "longitude": city.longitude} for city in db.scalars(select(Favorite).order_by(Favorite.name)).all()]


@app.post("/api/favorites", status_code=201)
def add_favorite(name: str, latitude: float, longitude: float, country: str = "", db: Session = Depends(get_db)):
    name = name.strip()
    if not name or len(name) > 120 or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail="Cidade ou coordenadas inválidas.")
    existing = db.scalar(select(Favorite).where(Favorite.latitude == latitude, Favorite.longitude == longitude))
    if existing:
        return {"id": existing.id, "name": existing.name, "country": existing.country, "latitude": existing.latitude, "longitude": existing.longitude}
    city = Favorite(name=name, country=country[:80], latitude=latitude, longitude=longitude)
    db.add(city)
    db.commit()
    db.refresh(city)
    return {"id": city.id, "name": city.name, "country": city.country, "latitude": city.latitude, "longitude": city.longitude}


@app.delete("/api/favorites/{city_id}", status_code=204)
def remove_favorite(city_id: int, db: Session = Depends(get_db)):
    city = db.get(Favorite, city_id)
    if city is None:
        raise HTTPException(status_code=404, detail="Cidade favorita não encontrada.")
    db.delete(city)
    db.commit()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    cities = db.scalars(select(Favorite).order_by(Favorite.name)).all()
    return templates.TemplateResponse(request, "index.html", {"cities": cities})


@app.get("/api/compare")
async def compare_cities(latitude: list[float] = Query(min_length=2, max_length=4), longitude: list[float] = Query(min_length=2, max_length=4)):
    if len(latitude) != len(longitude) or not 2 <= len(latitude) <= 4:
        raise HTTPException(status_code=422, detail="Informe de duas a quatro cidades para comparação.")
    if any(not (-90 <= lat <= 90) for lat in latitude) or any(not (-180 <= lon <= 180) for lon in longitude):
        raise HTTPException(status_code=422, detail="Coordenadas fora do intervalo válido.")
    async with http_client() as client:
        try:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": ",".join(map(str, latitude)), "longitude": ",".join(map(str, longitude)), "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m", "timezone": "auto"})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Não foi possível comparar o clima agora.") from exc
    payload = response.json()
    if isinstance(payload, dict):
        payload = [payload]
    return {"cities": [{"current": item.get("current", {}), "timezone": item.get("timezone", "UTC")} for item in payload]}


@app.get("/city/{latitude}/{longitude}", response_class=HTMLResponse)
async def city_page(request: Request, latitude: float, longitude: float, name: str, country: str = ""):
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail="Coordenadas inválidas.")
    data = await get_forecast(latitude, longitude)
    current = data.get("current") or {}
    current_time = str(current.get("time") or "")[:13]
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    start = next((i for i, value in enumerate(times) if str(value)[:13] == current_time), 0)
    def value_at(series, index):
        return series[index] if isinstance(series, list) and index < len(series) else None
    temperatures = hourly.get("temperature_2m") or []
    probabilities = hourly.get("precipitation_probability") or []
    hourly_next = [{"time": str(times[i])[11:16], "temperature": value_at(temperatures, i), "precipitation_probability": value_at(probabilities, i)} for i in range(start, min(start + 12, len(times)))]
    daily = data.get("daily") or {}
    day_times = daily.get("time") or []
    daily_days = [{"time": day_times[i], "weather_code": value_at(daily.get("weather_code") or [], i), "maximum": value_at(daily.get("temperature_2m_max") or [], i), "minimum": value_at(daily.get("temperature_2m_min") or [], i), "rain": value_at(daily.get("precipitation_probability_max") or [], i)} for i in range(len(day_times))]
    condition = weather_description(int(current.get("weather_code") if current.get("weather_code") is not None else -1))
    return templates.TemplateResponse(request, "weather.html", {"city": {"name": name[:120], "country": country[:80], "latitude": latitude, "longitude": longitude}, "forecast": data, "hourly_next": hourly_next, "daily_days": daily_days, "condition": condition})


@app.post("/favorites/add")
def add_favorite_form(name: str = Form(...), country: str = Form(""), latitude: float = Form(...), longitude: float = Form(...), db: Session = Depends(get_db)):
    name = name.strip()
    if not name or len(name) > 120 or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail="Cidade ou coordenadas inválidas.")
    if db.scalar(select(Favorite).where(Favorite.latitude == latitude, Favorite.longitude == longitude)) is None:
        db.add(Favorite(name=name, country=country[:80], latitude=latitude, longitude=longitude))
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/favorites/{city_id}/remove")
def remove_favorite_form(city_id: int, db: Session = Depends(get_db)):
    city = db.get(Favorite, city_id)
    if city:
        db.delete(city)
        db.commit()
    return RedirectResponse("/", status_code=303)
