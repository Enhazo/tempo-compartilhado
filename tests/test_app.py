import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = main.create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(main, "engine", engine)
    main.SessionLocal.configure(bind=engine)
    main.Base.metadata.create_all(engine)
    with TestClient(main.app) as test_client:
        yield test_client
    main.Base.metadata.drop_all(engine)
    engine.dispose()


def test_health(client):
    assert client.get('/health').json() == {'status': 'ok'}


def test_favorite_round_trip_and_duplicate_is_idempotent(client):
    payload = {'name': 'Lisboa', 'country': 'Portugal', 'latitude': 38.72, 'longitude': -9.14}
    first = client.post('/api/favorites', params=payload)
    second = client.post('/api/favorites', params=payload)
    assert first.status_code == 201
    assert second.json()['id'] == first.json()['id']
    listed = client.get('/api/favorites').json()
    assert len(listed) == 1 and listed[0]['name'] == 'Lisboa'
    assert client.delete(f"/api/favorites/{listed[0]['id']}").status_code == 204
    assert client.get('/api/favorites').json() == []


def test_rejects_invalid_coordinates(client):
    response = client.post('/api/favorites', params={'name': 'Invalid', 'latitude': 91, 'longitude': 0})
    assert response.status_code == 422


def test_search_validates_query_before_external_request(client):
    response = client.get('/api/cities/search', params={'q': 'a'})
    assert response.status_code == 422


def test_forecast_rejects_out_of_range_coordinates(client):
    response = client.get('/api/forecast', params={'latitude': -91, 'longitude': 0})
    assert response.status_code == 422


def test_city_comparison_validates_matching_coordinates(client):
    response = client.get('/api/compare', params=[('latitude', 10), ('latitude', 20), ('longitude', 30)])
    assert response.status_code == 422


def test_city_comparison_rejects_out_of_range_values(client):
    response = client.get('/api/compare', params=[('latitude', 100), ('latitude', 20), ('longitude', 30), ('longitude', 40)])
    assert response.status_code == 422


def test_city_comparison_fetches_current_weather(monkeypatch, client):
    async def fake_get(self, url, params=None):
        class Response:
            def raise_for_status(self): pass
            def json(self): return [{'current': {'temperature_2m': 20}, 'timezone': 'Europe/Lisbon'}, {'current': {'temperature_2m': 25}, 'timezone': 'Europe/Madrid'}]
        return Response()
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        get = fake_get
    monkeypatch.setattr(main.httpx, 'AsyncClient', FakeClient)
    response = client.get('/api/compare', params=[('latitude', 38), ('latitude', 40), ('longitude', -9), ('longitude', -3)])
    assert response.status_code == 200
    assert len(response.json()['cities']) == 2


def test_home_renders_in_portuguese(client):
    response = client.get('/')
    assert response.status_code == 200
    assert 'O mundo lá fora' in response.text


def test_city_page_escapes_untrusted_city_name(monkeypatch, client):
    async def fake_forecast(latitude, longitude):
        return {'timezone': 'UTC', 'current': {'time': '2026-11-20T12:00', 'temperature_2m': 20, 'apparent_temperature': 20, 'relative_humidity_2m': 50, 'is_day': 1, 'precipitation': 0, 'weather_code': 0, 'wind_speed_10m': 4}, 'current_units': {'temperature_2m': '°C', 'wind_speed_10m': 'km/h', 'precipitation': 'mm'}, 'hourly': {'time': ['2026-11-20T12:00'], 'temperature_2m': [20], 'precipitation_probability': [0]}, 'daily': {'time': [], 'weather_code': [], 'temperature_2m_max': [], 'temperature_2m_min': [], 'precipitation_probability_max': []}}
    monkeypatch.setattr(main, 'get_forecast', fake_forecast)
    response = client.get('/city/0/0', params={'name': '<script>alert(1)</script>'})
    assert response.status_code == 200
    assert '<script>alert(1)</script>' not in response.text
    assert 'Céu limpo' in response.text


def test_city_page_handles_null_and_missing_forecast_series(monkeypatch, client):
    async def fake_forecast(latitude, longitude):
        return {'timezone': 'UTC', 'current': {'time': '2026-11-20T12:00', 'temperature_2m': None, 'apparent_temperature': None, 'relative_humidity_2m': None, 'precipitation': None, 'weather_code': 0, 'wind_speed_10m': None}, 'current_units': {'temperature_2m': '°C', 'wind_speed_10m': 'km/h', 'precipitation': 'mm'}, 'hourly': {'time': ['2026-11-20T12:00', '2026-11-20T13:00'], 'temperature_2m': [None, 20]}, 'daily': {'time': ['2026-11-20'], 'weather_code': [None], 'temperature_2m_max': [None], 'temperature_2m_min': [10], 'precipitation_probability_max': [None]}}
    monkeypatch.setattr(main, 'get_forecast', fake_forecast)
    response = client.get('/city/0/0', params={'name': 'Teste'})
    assert response.status_code == 200
    assert '💧 None%' not in response.text
    assert 'None mm' not in response.text
