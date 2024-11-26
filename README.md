# Radar Backend

FastAPI-based backend service for content analysis and conversation management.

## Tech Stack
- FastAPI
- PostgreSQL
- Poetry
- Alembic (migrations)
- Docker

## Local Development

### Prerequisites
- Python 3.9+
- Poetry
- PostgreSQL

### Setup Database
1. Run the setup script:
```bash
psql -U postgres -f setup.sql
```

2. Create `.env`:
```bash
DATABASE_URL=postgresql://myuser:postgres@localhost:5432/radar_demo
ENV=dev
```

### Install Dependencies
```bash
poetry install
```

### Run Migrations
```bash
poetry run alembic upgrade head
```

### Start Server
```bash
poetry run uvicorn main:app --reload --port 3001
```

## Docker Deployment

Build and run:
```bash
docker build -t radar-backend .
docker run -p 3001:3001 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/dbname \
  radar-backend
```

## API Endpoints

### Content Analysis
- `POST /api/analyze` - Analyze URL content
- `GET /api/conversations/{id}` - Get conversation history
- `POST /api/conversations/{id}/messages` - Add message to conversation
- `POST /api/share` - Share conversation

### System
- `GET /api/health` - Health check

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `ENV` - Environment (dev/prod)

## Development

### Run Tests
```bash
poetry run pytest
```

### Database Migrations
Create new migration:
```bash
poetry run alembic revision -m "description"
```

Apply migrations:
```bash
poetry run alembic upgrade head
```

Rollback:
```bash
poetry run alembic downgrade -1
```
