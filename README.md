# Real-Time Event Booking Platform

A production-oriented event booking platform inspired by BookMyShow, built with FastAPI, PostgreSQL, React, and TypeScript.

The project focuses on backend engineering and production-style workflows, including authentication, event and seat management, reservation lifecycle, concurrency control, payment processing, background jobs, and automated testing.

## Current Status

**Implemented:**

- Backend REST APIs using FastAPI
- React frontend with TypeScript and Vite
- User authentication and authorization
- Venue and event management
- Venue seat management
- Event-specific seat inventory
- Reservation and seat-hold lifecycle
- Concurrent booking protection
- Razorpay payment order and verification integration
- Razorpay webhook processing
- Redis and Celery background processing
- PostgreSQL integration testing with Testcontainers
- Automated backend test suite

**Current engineering focus:**

Preparing the application for deployment by introducing containerization, production configuration, CI/CD, and cloud infrastructure.

**Deployment status:** Not deployed to production yet.

**Payment testing status:** Payment integration is implemented. End-to-end Razorpay sandbox verification requires valid Razorpay test credentials.

## Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.12 |
| Backend Framework | FastAPI |
| Frontend | React 19, TypeScript |
| Frontend Build Tool | Vite |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.x |
| Database Migrations | Alembic |
| Validation | Pydantic |
| Configuration | pydantic-settings |
| Authentication | JWT with PyJWT |
| Password Hashing | Argon2 |
| Payment Gateway | Razorpay |
| Background Processing | Celery |
| Message Broker | Redis |
| Containerization | Docker and Docker Compose |
| Backend Testing | pytest |
| PostgreSQL Integration Testing | Testcontainers |
| Python Package Management | uv |
| JavaScript Package Management | npm |

## Implemented Features

### Authentication

- User registration and login
- Secure password hashing using Argon2
- JWT-based authentication
- Authenticated-user endpoint
- Authentication and authorization checks

### Venues and Events

- Create, list, retrieve, update, and delete venues
- Event CRUD operations
- Associate events with venues
- Validate event start and end times
- Validate pricing and event capacity

### Venue Seat Management

- Create seats within a venue
- List, retrieve, update, and delete seats
- Prevent duplicate seat positions within a venue
- Validate positive seat numbers
- Scope individual seat lookups to their venue

### Event Seat Inventory

- Generate event-specific seat inventory from venue seats
- Track individual seat availability for an event
- Maintain separate inventory for different events

### Reservation System

- Reserve one or multiple seats
- Maintain reservation and reservation-seat records
- Temporary seat holds with a five-minute initial reservation window
- Checkout deadline management
- Maximum reservation hold of 15 minutes from creation
- Release seats when reservations expire or are cancelled
- Prevent double booking using PostgreSQL transactions and locking mechanisms
- Reservation history and ownership checks

### Payment Integration

- Razorpay payment order creation
- Payment signature verification
- Webhook signature verification
- Durable webhook event processing
- Idempotent handling of duplicate webhook events
- Payment status updates and reservation confirmation
- Store payment amounts in integer paise
- Validate payment amounts and provider order details

Payment confirmation is driven by verified server-side payment processing, not solely by frontend success responses.

**Note:** Valid Razorpay test credentials are required to perform an actual sandbox checkout. Do not commit payment credentials to Git.

### Background Processing

- Redis as the Celery message broker
- Celery worker for background task execution
- Celery Beat for scheduled task execution
- Periodic expiration of overdue reservations
- Database session management inside background tasks

### Frontend

- React and TypeScript application
- User authentication flow
- Event browsing and selection
- Event details
- Seat selection interface
- Reservation flow
- Booking history
- Razorpay Standard Checkout integration

## Architecture

```text
                  React Frontend
                        |
                        v
                  FastAPI Backend
                        |
           +------------+------------+
           |            |            |
           v            v            v
       PostgreSQL     Redis       Razorpay
           ^            |
           |            v
           |       Celery Worker
           |            ^
           |            |
           +------ Celery Beat
```

This is a simplified logical architecture. Redis is used as the Celery broker, while PostgreSQL stores application data.

The frontend communicates with the backend through HTTP APIs.

## Project Setup

### Prerequisites

Install the following:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- PostgreSQL
- Docker Desktop with Docker Compose
- Git

Docker is required for Redis and the Testcontainers-based PostgreSQL integration tests.

### 1. Clone the repository

```bash
git clone https://github.com/Rahulxzy/real-time-event-booking-platform.git

cd real-time-event-booking-platform
```

### 2. Install backend dependencies

```bash
uv sync
```

Use the Python version configured for the project. The development environment currently uses Python 3.12.13.

### 3. Configure environment variables

Create a `.env` file in the project root.

Configure the PostgreSQL connection using your local credentials:

```dotenv
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=event_booking_db
DATABASE_USER=postgres
DATABASE_PASSWORD=your_local_database_password
```

Also configure the Redis and Razorpay settings required by the application.

Use the exact setting names defined in the application's configuration. Never commit `.env` or real credentials to Git.

### 4. Create the PostgreSQL database

```sql
CREATE DATABASE event_booking_db;
```

Run this using your PostgreSQL client.

### 5. Apply database migrations

```bash
uv run alembic upgrade head
```

This applies all database migrations up to the latest revision.

### 6. Start Redis

Start Docker Desktop, then run:

```bash
docker compose up -d redis
```

Verify that Redis is responding:

```bash
docker compose exec redis redis-cli ping
```

Expected output:

```text
PONG
```

### 7. Start the FastAPI application

Open a terminal in the project root:

```bash
uv run uvicorn app.main:app --reload
```

Backend API:

```text
http://127.0.0.1:8000
```

### 8. Start the Celery worker

Open a separate terminal in the project directory:

```bash
uv run celery -A app.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

The `solo` pool is used for local development on Windows.

### 9. Start Celery Beat

Open another terminal:

```bash
uv run celery -A app.celery_app:celery_app beat --loglevel=INFO
```

Celery Beat schedules periodic reservation-expiration tasks, which are executed by the worker.

### 10. Start the React frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite will display the local frontend URL in the terminal, normally:

```text
http://localhost:5173
```

### 11. Explore the API

Once the FastAPI server is running:

- Interactive API documentation: http://127.0.0.1:8000/docs
- Alternative API documentation: http://127.0.0.1:8000/redoc
- Health check: http://127.0.0.1:8000/health

Use Swagger UI to inspect the current API routes, request schemas, response models, and authentication requirements.

## Running Tests

Run the complete backend test suite:

```bash
uv run pytest -v
```

### Testing Strategy

The project uses two database testing approaches.

**SQLite**

- Used for fast tests that do not depend on PostgreSQL-specific behavior.
- Suitable for general API and application logic tests.

**PostgreSQL with Testcontainers**

- Starts a disposable PostgreSQL container for integration tests.
- Used for PostgreSQL-specific behavior, including transaction and concurrency testing.
- Does not require a manually maintained local test database.
- Requires Docker Desktop to be running.

The Testcontainers PostgreSQL container is automatically managed during the pytest session.

**Latest verified backend test result:**

```text
167 passed, 16 warnings
```

This is the latest verified test result as of November 15, 2026. Warnings are primarily deprecation warnings and are not test failures.

## Database Migrations

Create a migration after changing SQLAlchemy models:

```bash
uv run alembic revision --autogenerate -m "describe your change"
```

Review the generated migration before applying it:

```bash
uv run alembic upgrade head
```

Useful Alembic commands:

Check the current migration revision:

```bash
uv run alembic current
```

View migration history:

```bash
uv run alembic history
```

Rollback one migration:

```bash
uv run alembic downgrade -1
```

Never assume an autogenerated migration is correct without reviewing its operations.

## API Overview

The following core routes are implemented:

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
| GET | `/venues/{venue_id}/seats` | List venue seats |
| GET | `/venues/{venue_id}/seats/{seat_id}` | Retrieve a seat |
| PATCH | `/venues/{venue_id}/seats/{seat_id}` | Update a seat |
| DELETE | `/venues/{venue_id}/seats/{seat_id}` | Delete a seat |
| POST | `/events/{event_id}/inventory` | Initialize event inventory |
| GET | `/events/{event_id}/seats` | List event seats |
| POST | `/reservations` | Create a reservation |
| GET | `/reservations/me` | List user reservations |
| GET | `/reservations/{reservation_id}` | Retrieve a reservation |
| POST | `/reservations/{reservation_id}/cancel` | Cancel a reservation |
| POST | `/payments/orders` | Create a payment order |
| POST | `/payments/verify` | Verify checkout payment |
| POST | `/webhooks/razorpay` | Process Razorpay webhooks |

Authentication is required for protected operations. Refer to `/docs` for the complete and current API documentation.

## Useful Docker Commands

Start Redis:

```bash
docker compose up -d redis
```

Stop Redis without deleting its persistent data:

```bash
docker compose stop redis
```

Start an existing Redis container:

```bash
docker compose start redis
```

View Redis logs:

```bash
docker compose logs -f redis
```

Check running containers:

```bash
docker compose ps
```

Avoid `docker compose down -v` unless you intentionally want to delete the associated persistent volumes.

**Note:** The current Docker Compose setup is used for Redis and development/testing dependencies. Full application containerization is part of the upcoming deployment work.

## Engineering Practices

The project follows these engineering practices:

- Separation of API routes, schemas, models, services, and dependencies
- SQLAlchemy 2.x typed ORM patterns
- Version-controlled database migrations
- Database constraints and transaction management
- Secure authentication and password hashing
- Idempotent payment and webhook processing
- Concurrency protection for seat reservations
- Background processing with Celery
- Environment-based configuration and secret management
- Automated unit and integration testing
- Git commits representing completed and tested milestones

## Roadmap

The next engineering milestones are:

### Containerization

- Dockerfile for the FastAPI backend
- Dockerfile for the React frontend
- Complete Docker Compose architecture
- Container health checks
- Persistent volumes and service networking
- Production environment configuration

### CI/CD

- GitHub Actions workflows
- Automated linting and testing
- Docker image builds
- Container registry integration
- Automated deployment pipeline

### Cloud Deployment

- AWS infrastructure setup
- Application deployment
- Managed PostgreSQL
- Redis deployment
- Domain and HTTPS configuration
- Reverse proxy and production networking

### Observability and Reliability

- Centralized application logging
- Monitoring and health checks
- Error tracking
- Production security improvements
- Backup and recovery strategy

## License

No license has been specified yet.
