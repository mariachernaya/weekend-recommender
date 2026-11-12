import pytest
from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_page(client):
    """Тест: главная страница открывается"""
    response = client.get('/')
    assert response.status_code == 200

def test_events_page(client):
    """Тест: страница мероприятий открывается (по спец. URL)"""
    # Замените 'student' на ваш реальный логин для теста
    response = client.get('/student2024/users/')
    assert response.status_code == 200
    assert b'Все мероприятия' in response.data