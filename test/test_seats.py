import pytest
from fastapi import status


def create_venue(client, auth_headers):
    response = client.post(
        "/venues",
        json={
            "name": "Test Cinema",
            "address": "123 Test Street",
            "city": "Delhi",
        },
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def test_create_seat(client, auth_headers):
    venue = create_venue(client, auth_headers)

    response = client.post(
        f"/venues/{venue['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["venue_id"] == venue["id"]
    assert data["row_label"] == "A"
    assert data["seat_number"] == 1


def test_create_duplicate_seat(client, auth_headers):
    venue = create_venue(client, auth_headers)
    payload = {"row_label": "A", "seat_number": 1}

    first = client.post(
        f"/venues/{venue['id']}/seats",
        json=payload,
        headers=auth_headers,
    )
    second = client.post(
        f"/venues/{venue['id']}/seats",
        json=payload,
        headers=auth_headers,
    )

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_409_CONFLICT


@pytest.mark.parametrize("seat_number", [0, -1])
def test_create_seat_with_invalid_number(
    client, auth_headers, seat_number
):
    venue = create_venue(client, auth_headers)

    response = client.post(
        f"/venues/{venue['id']}/seats",
        json={"row_label": "A", "seat_number": seat_number},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_seat_for_nonexistent_venue(client, auth_headers):
    response = client.post(
        "/venues/999999/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_list_venue_seats(client, auth_headers):
    venue = create_venue(client, auth_headers)

    for row, number in [("A", 1), ("A", 2), ("B", 1)]:
        response = client.post(
            f"/venues/{venue['id']}/seats",
            json={"row_label": row, "seat_number": number},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f"/venues/{venue['id']}/seats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 3


def test_create_seat_unauthenticated(client, auth_headers):
    venue = create_venue(client, auth_headers)

    response = client.post(
        f"/venues/{venue['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_list_seats_only_for_requested_venue(client, auth_headers):
    venue_a = create_venue(client, auth_headers)
    venue_b = create_venue(client, auth_headers)

    response_a = client.post(
        f"/venues/{venue_a['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )
    response_b = client.post(
        f"/venues/{venue_b['id']}/seats",
        json={"row_label": "B", "seat_number": 1},
        headers=auth_headers,
    )

    assert response_a.status_code == status.HTTP_201_CREATED
    assert response_b.status_code == status.HTTP_201_CREATED

    response = client.get(f"/venues/{venue_a['id']}/seats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["venue_id"] == venue_a["id"]
    assert data[0]["row_label"] == "A"


def test_get_single_seat(client, auth_headers):
    venue = create_venue(client, auth_headers)

    create_response = client.post(
        f"/venues/{venue['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    seat = create_response.json()

    response = client.get(
        f"/venues/{venue['id']}/seats/{seat['id']}"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == seat["id"]
    assert response.json()["row_label"] == "A"


def test_get_seat_from_wrong_venue_returns_404(client, auth_headers):
    venue_a = create_venue(client, auth_headers)
    venue_b = create_venue(client, auth_headers)

    create_response = client.post(
        f"/venues/{venue_a['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )
    seat = create_response.json()

    response = client.get(
        f"/venues/{venue_b['id']}/seats/{seat['id']}"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_update_seat(client, auth_headers):
    venue = create_venue(client, auth_headers)

    create_response = client.post(
        f"/venues/{venue['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )
    seat = create_response.json()

    response = client.patch(
        f"/venues/{venue['id']}/seats/{seat['id']}",
        json={"row_label": "B", "seat_number": 2},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["row_label"] == "B"
    assert response.json()["seat_number"] == 2


def test_update_seat_duplicate_returns_409(client, auth_headers):
    venue = create_venue(client, auth_headers)

    for row, number in [("A", 1), ("B", 1)]:
        response = client.post(
            f"/venues/{venue['id']}/seats",
            json={"row_label": row, "seat_number": number},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED

    seats = client.get(f"/venues/{venue['id']}/seats").json()
    seat_b = next(seat for seat in seats if seat["row_label"] == "B")

    response = client.patch(
        f"/venues/{venue['id']}/seats/{seat_b['id']}",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT


def test_update_seat_empty_payload_returns_422(client, auth_headers):
    venue = create_venue(client, auth_headers)

    create_response = client.post(
        f"/venues/{venue['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )
    seat = create_response.json()

    response = client.patch(
        f"/venues/{venue['id']}/seats/{seat['id']}",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_delete_seat(client, auth_headers):
    venue = create_venue(client, auth_headers)

    create_response = client.post(
        f"/venues/{venue['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )
    seat = create_response.json()

    response = client.delete(
        f"/venues/{venue['id']}/seats/{seat['id']}",
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT

    get_response = client.get(
        f"/venues/{venue['id']}/seats/{seat['id']}"
    )
    assert get_response.status_code == status.HTTP_404_NOT_FOUND


def test_delete_seat_without_token(client, auth_headers):
    venue = create_venue(client, auth_headers)

    create_response = client.post(
        f"/venues/{venue['id']}/seats",
        json={"row_label": "A", "seat_number": 1},
        headers=auth_headers,
    )
    seat = create_response.json()

    response = client.delete(
        f"/venues/{venue['id']}/seats/{seat['id']}"
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED