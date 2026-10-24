# Real-Time Event Booking Platform

A backend application for an event booking platform inspired by BookMyShow. The project is being developed incrementally, with a focus on backend engineering practices, database integrity, authentication, automated testing, and reliable booking workflows.

## Current Status

**Completed:** Foundation, Authentication, Venues & Events, Seat Management
**In progress:** Event-specific seat inventory and availability

## Tech Stack

- **Language:** Python 3.12
- **API framework:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy 2.x
- **Migrations:** Alembic
- **Validation and configuration:** Pydantic, pydantic-settings
- **Authentication:** JWT with PyJWT
- **Password hashing:** Argon2
- **Testing:** pytest
- **Package and environment management:** uv

## Implemented Features

### Authentication
- User registration and login
- Secure password hashing
- JWT-based authentication
- Current authenticated-user endpoint
- Request validation and authentication error handling

### Venues
- Create, list, retrieve, update, and delete venues
- Request validation and database-backed persistence

### Events
- Event CRUD operations
- Association between events and venues
- Start and end time validation, including timezone requirements
- Price and capacity validation

### Venue Seat Management
- Create seats within a venue
- List seats belonging to a venue
- Retrieve an individual seat
- Update and delete seats
- Prevent duplicate seat positions within the same venue
- Validate positive seat numbers
- Scope individual seat lookups to their venue

## Project Setup

### Prerequisites

Install the following before starting:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL
- Git

### 1. Clone the repository

```bash
git clone https://github.com/Rahulxzy/real-time-event-booking-platform.git
cd real-time-event-booking-platform
```

### 2. Install dependencies

```bash
uv sync
```

If your local environment requires a specific Python 3.12 patch release, make sure it is installed and selected for the project.

### 3. Configure environment variables

Create a `.env` file in the project root. Configure it with your local PostgreSQL credentials:

```dotenv
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=event_booking_db
DATABASE_USER=postgres
DATABASE_PASSWORD=your_local_database_password
```

Replace the example password with your own local database password. Never commit `.env` or real credentials to Git.

Create the PostgreSQL database if it does not already exist:

```sql
CREATE DATABASE event_booking_db;
```

Run this SQL using your PostgreSQL client or terminal. If you use a different database name or credentials, update `.env` accordingly.

### 4. Apply database migrations

```bash
uv run alembic upgrade head
```

This applies all migrations up to the latest revision.

### 5. Start the API

```bash
uv run fastapi dev app/main.py
```

The development server should display its local address in the terminal.

### 6. Explore the API

Once the server is running, open:

- Interactive API documentation: `http://127.0.0.1:8000/docs`
- Alternative API documentation: `http://127.0.0.1:8000/redoc`
- Health check: `http://127.0.0.1:8000/health`

## Running Tests

Run the complete test suite:

```bash
uv run pytest -v
```

The tests cover authentication, JWT handling, schema validation, password hashing, venue operations, and seat management.

Tests may require the database configuration or test database setup defined by the project. Follow the test fixtures and configuration in the repository when running them in a new environment.

## API Overview

The following routes have been implemented.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/register` | Register a user |
| POST | `/auth/login` | Log in and obtain a token |
| GET | `/auth/me` | Get the authenticated user |
| POST | `/venues` | Create a venue |
| GET | `/venues` | List venues |
| GET | `/venues/{venue_id}` | Retrieve a venue |
| PATCH | `/venues/{venue_id}` | Update a venue |
| DELETE | `/venues/{venue_id}` | Delete a venue |
| POST | `/events` | Create an event |
| GET | `/events` | List events |
| GET | `/events/{event_id}` | Retrieve an event |
| PATCH | `/events/{event_id}` | Update an event |
| DELETE | `/events/{event_id}` | Delete an event |
| POST | `/venues/{venue_id}/seats` | Create a seat |
| GET | `/venues/{venue_id}/seats` | List seats for a venue |
| GET | `/venues/{venue_id}/seats/{seat_id}` | Retrieve a seat |
| PATCH | `/venues/{venue_id}/seats/{seat_id}` | Update a seat |
| DELETE | `/venues/{venue_id}/seats/{seat_id}` | Delete a seat |

Use `/docs` to inspect request schemas, response models, validation rules, and authentication requirements. Authentication is required for protected operations.

## Database Migrations

Create a migration after changing SQLAlchemy models:

```bash
uv run alembic revision --autogenerate -m "describe your change"
```

Review the generated migration before applying it:

```bash
uv run alembic upgrade head
```

Do not assume an autogenerated migration is correct without reviewing its operations.

## Planned Work

The following features are planned and should not be considered implemented yet:

- Event-specific seat inventory and availability
- Seat reservations and booking lifecycle
- Concurrency control and double-booking prevention
- Payment integration
- Booking history and cancellation
- Real-time availability updates
- Ticket generation and email notifications
- Background jobs, caching, and rate limiting
- Docker, CI/CD, and cloud deployment

## Engineering Practices

This project is developed incrementally, with an emphasis on:

- Clear separation of API routes, schemas, database models, and dependencies
- Database constraints and version-controlled migrations
- Input validation and consistent HTTP error handling
- Automated tests for successful and unsuccessful requests
- Environment-based configuration and secret management
- Git commits that represent completed, tested milestones

## License

No license has been specified yet.
