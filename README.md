# Real-Time Event Booking Platform

A production-oriented event booking platform inspired by BookMyShow, built with FastAPI, PostgreSQL, React, and TypeScript.

The project focuses on backend engineering and production-style workflows, including authentication, event and seat management, reservation lifecycle, concurrency control, payment processing, background jobs, automated testing, containerization, and CI/CD automation.

## Current Status

**Implemented:**

- FastAPI backend REST APIs
- React frontend with TypeScript and Vite
- User authentication and authorization
- Venue and event management
- Venue seat management and event-specific inventory
- Reservation lifecycle and temporary seat holds
- Concurrent booking protection
- Razorpay payment order and verification integration
- Razorpay webhook processing
- Redis and Celery background processing
- PostgreSQL integration testing with Testcontainers
- Automated backend test suite
- Backend and frontend Dockerization
- Multi-service Docker Compose infrastructure
- GitHub Actions CI pipeline
- Automated Docker image publishing to GitHub Container Registry (GHCR)

**Current engineering focus:** Preparing for AWS cloud deployment, production security, and automated continuous deployment.

**Cloud deployment status:** Not deployed to AWS or another production cloud environment yet.

**Payment testing status:** Payment integration is implemented. End-to-end Razorpay sandbox verification requires valid Razorpay test credentials.

## Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.12 |
| Backend Framework | FastAPI |
| Frontend | React 19, TypeScript |
| Frontend Build Tool | Vite |
| Web Server | Nginx |
| Database | PostgreSQL 18 |
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
| CI/CD | GitHub Actions |
| Container Registry | GitHub Container Registry (GHCR) |
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

**Note:** Valid Razorpay test credentials are required to perform an actual sandbox checkout. Never commit payment credentials to Git.

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
                       Nginx
                         |
                         v
                    FastAPI API
                         |
              +----------+----------+
              |          |          |
              v          v          v
          PostgreSQL   Redis     Razorpay
                         |
                    Celery Worker
                         ^
                         |
                    Celery Beat
```

The application runs as separate Docker Compose services:

- `frontend` — React production build served by Nginx
- `api` — FastAPI application
- `db` — PostgreSQL database
- `redis` — Redis message broker
- `worker` — Celery background task worker
- `beat` — Celery scheduled task service
- `migrate` — One-time Alembic database migration service

## Repository Structure

```text
real-time-event-booking-platform/
|
|-- app/
|   |-- main.py
|   |-- database.py
|   |-- models.py
|   |-- schemas.py
|   |-- routers/
|   |-- services/
|   |-- tasks/
|   |-- celery_app.py
|   |-- dependencies.py
|
|-- frontend/
|   |-- src/
|   |-- public/
|   |-- Dockerfile
|   |-- nginx.conf
|   |-- package.json
|
|-- migrations/
|   |-- versions/
|
|-- test/
|   |-- conftest.py
|   |-- test_*.py
|
|-- .github/
|   |-- workflows/
|       |-- ci.yml
|
|-- Dockerfile
|-- .dockerignore
|-- compose.yaml
|-- pyproject.toml
|-- uv.lock
|-- alembic.ini
|-- .env.example
|-- .gitignore
|-- README.md
```

## Project Setup

### Prerequisites

For local development:

- Python 3.12
- uv
- Node.js and npm
- PostgreSQL
- Docker Desktop with Docker Compose
- Git

For containerized execution, Docker Desktop is sufficient for running the application services.

### 1. Clone the repository

```bash
git clone https://github.com/Rahulxzy/real-time-event-booking-platform.git

cd real-time-event-booking-platform
```

### 2. Configure environment variables

Create a `.env` file in the project root.

Configure the PostgreSQL connection and authentication settings:

```dotenv
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=event_booking_db
DATABASE_USER=postgres
DATABASE_PASSWORD=your_local_database_password

JWT_SECRET_KEY=replace_with_a_secure_random_secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

REDIS_URL=redis://localhost:6379/0

RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
RAZORPAY_WEBHOOK_SECRET=your_razorpay_webhook_secret
RAZORPAY_CURRENCY=INR
```

Use strong local secrets and valid provider credentials where required.

Never commit `.env` or real credentials to Git.

### 3. Local development setup

Install backend dependencies:

```bash
uv sync
```

Create the PostgreSQL database:

```sql
CREATE DATABASE event_booking_db;
```

Apply database migrations:

```bash
uv run alembic upgrade head
```

Start Redis:

```bash
docker compose up -d redis
```

Start the FastAPI application:

```bash
uv run uvicorn app.main:app --reload
```

Start the Celery worker in a separate terminal:

```bash
uv run celery -A app.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

Start Celery Beat in another terminal:

```bash
uv run celery -A app.celery_app:celery_app beat --loglevel=INFO
```

Start the React frontend:

```bash
cd frontend
npm ci
npm run dev
```

Vite normally serves the frontend at:

```text
http://localhost:5173
```

### 4. API Documentation

Once the backend is running:

- API documentation: http://127.0.0.1:8000/docs
- Alternative documentation: http://127.0.0.1:8000/redoc
- Health check: http://127.0.0.1:8000/health

## Running with Docker Compose

The complete application can be run using Docker Compose.

### Prerequisites

- Docker Desktop
- Docker Compose
- Configured root `.env` file

For containerized execution, the Compose configuration overrides the database and Redis hostnames with their internal service names.

### Start the application

Build and start all services:

```bash
docker compose up -d --build
```

This starts:

- PostgreSQL
- Redis
- Database migration service
- FastAPI
- Celery worker
- Celery Beat
- React frontend served by Nginx

### Application URLs

| Service | URL |
|---|---|
| React Frontend | http://localhost:3000 |
| FastAPI API | http://localhost:8000 |
| Swagger Documentation | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

### Useful Docker Compose commands

Check service status:

```bash
docker compose ps
```

View application logs:

```bash
docker compose logs -f api
```

View worker logs:

```bash
docker compose logs -f worker
```

View frontend logs:

```bash
docker compose logs -f frontend
```

Stop services without deleting persistent volumes:

```bash
docker compose down
```

Restart services:

```bash
docker compose up -d
```

**Important:** PostgreSQL and Redis use named Docker volumes for persistent data. Avoid `docker compose down -v` unless you intentionally want to delete the associated database and Redis volumes.

## Testing

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

- Starts a disposable PostgreSQL 18 container for integration tests.
- Used for PostgreSQL-specific behavior, including transactions and concurrency.
- Tests database connection and migration upgrade/downgrade behavior.
- Does not require a manually maintained local test database.
- Requires Docker to be running.

The Testcontainers PostgreSQL container is automatically managed during the pytest session.

## Continuous Integration

GitHub Actions automatically validates changes pushed to the `main` branch and pull requests targeting `main`.

The CI workflow is located at:

```text
.github/workflows/ci.yml
```

### CI Pipeline

**1. Backend Tests**

- Set up Python 3.12
- Install dependencies using uv
- Run the complete pytest suite
- Execute PostgreSQL integration tests through Testcontainers

**2. Frontend Lint and Build**

- Set up Node.js 22
- Install dependencies using `npm ci`
- Run Oxlint
- Build the production frontend using TypeScript and Vite

**3. Docker Image Build**

- Build the FastAPI backend Docker image
- Build the React frontend Docker image

**4. Publish Images to GHCR**

- Authenticate using GitHub Actions `GITHUB_TOKEN`
- Publish backend and frontend images to GitHub Container Registry
- Publish only after successful CI jobs
- Publish images on successful pushes to `main`, not on pull requests

### Verified CI Results

The CI pipeline has successfully completed all four jobs:

- Backend Tests
- Frontend Lint and Build
- Docker Image Build
- Publish Images to GHCR

The workflow is configured to run automatically on relevant pushes and pull requests.

## Docker Images — GitHub Container Registry

The backend and frontend Docker images are published to GHCR.

**Backend image:**

```text
ghcr.io/rahulxzy/real-time-event-booking-platform-backend
```

**Frontend image:**

```text
ghcr.io/rahulxzy/real-time-event-booking-platform-frontend
```

Both images use two tags:

- `latest` — Latest successfully published image from the main branch
- Git commit SHA — Immutable version identifier for a specific source revision

Pull the backend image:

```bash
docker pull ghcr.io/rahulxzy/real-time-event-booking-platform-backend:latest
```

Pull the frontend image:

```bash
docker pull ghcr.io/rahulxzy/real-time-event-booking-platform-frontend:latest
```

These images are available through the project's GitHub Packages section.

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
| POST | `/events/{event_id}/inventory` | Initialize event inventory |
| GET | `/events/{event_id}/seats` | List event seats |
| POST | `/reservations` | Create a reservation |
| GET | `/reservations/me` | List user reservations |
| GET | `/reservations/{reservation_id}` | Retrieve a reservation |
| POST | `/reservations/{reservation_id}/cancel` | Cancel a reservation |
| POST | `/payments/orders` | Create a payment order |
| POST | `/payments/verify` | Verify checkout payment |
| POST | `/webhooks/razorpay` | Process Razorpay webhooks |

Authentication is required for protected operations. Refer to `/docs` for complete API documentation.

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
- Docker-based application packaging
- Multi-service Docker Compose orchestration
- Automated CI with GitHub Actions
- Versioned Docker image publishing through GHCR
- Git commits representing completed and tested milestones

## Roadmap

### Cloud Deployment

- AWS account and infrastructure setup
- EC2-based application deployment
- Production Docker Compose configuration
- Production environment and secret management
- Domain and HTTPS configuration
- Reverse proxy and production networking
- Persistent storage and database backups

### Continuous Deployment

- Automated deployment after successful CI
- Pull and deploy versioned images from GHCR
- Deployment health checks
- Rollback strategy

### Observability and Reliability

- Centralized application logging
- Monitoring and health checks
- Error tracking and alerts
- Production security improvements
- Backup and recovery strategy

## License

No license has been specified yet.
