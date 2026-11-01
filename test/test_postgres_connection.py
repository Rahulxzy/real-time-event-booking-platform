def test_postgres_connection(postgres_client):
    response = postgres_client.get("/health")

    assert response.status_code == 200