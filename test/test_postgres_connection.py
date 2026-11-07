def test_postgres_connection(testcontainers_postgres_client):
    response = testcontainers_postgres_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"