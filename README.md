# Boxup: Formula 1 Data Analytics Platform

A comprehensive Formula 1 telemetry and analytics platform that provides real-time race insights, performance analysis, and machine learning-powered predictions. Built with modern web technologies and a scalable microservices architecture.

## Overview

Boxup aggregates and visualizes Formula 1 telemetry data, driver performance metrics, and race analytics in real-time. The platform enables engineers, analysts, and enthusiasts to explore detailed telemetry traces, brake analysis, corner insights, and predictive models for championship standings and race outcomes.

## Key Features

- **Real-Time Telemetry Visualization**: Interactive speed traces, brake analysis, and corner-by-corner performance metrics
- **Race Analysis**: Comprehensive session data including qualifying segments, practice sessions, and race telemetry
- **Driver Performance Analytics**: Comparative analysis between drivers with sector breakdowns and performance matrices
- **Weather Integration**: Real-time weather conditions tracked throughout race sessions
- **Championship Predictions**: Machine learning models for predicting championship outcomes and race results
- **Responsive Dashboard**: Modern web interface with real-time updates and interactive visualizations
- **Data Ingestion Pipeline**: Automated data collection and processing from official F1 sources

## Tech Stack

### Frontend
- **Framework**: Next.js 16 (React 19)
- **Styling**: Tailwind CSS, PostCSS
- **Charts & Visualization**: Recharts, Plotly.js, react-d3-speedometer
- **Real-Time Updates**: Socket.io Client
- **Testing**: Vitest
- **Linting**: ESLint
- **Deployment**: Vercel

### Backend
- **Language**: Python 3
- **Framework**: Flask
- **Database**: PostgreSQL with TimescaleDB (time-series optimization)
- **Migrations**: Alembic
- **Message Queue**: Apache Kafka
- **Caching**: Redis
- **ML Tracking**: MLflow

### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Orchestration**: Kafka for event streaming
- **Database**: TimescaleDB for time-series telemetry data
- **UI Tools**: Kafka UI for message queue monitoring

## Project Structure

```
.
├── frontend/                 # Next.js web application
│   ├── app/                 # Page routes and layouts
│   ├── components/          # Reusable React components
│   ├── lib/                 # Utilities and API clients
│   └── types/               # TypeScript type definitions
├── backend/                 # Python Flask API
│   ├── src/backend/        # Core application logic
│   │   ├── api/            # API endpoints
│   │   ├── config.py       # Configuration management
│   │   └── extensions.py   # Database and service extensions
│   ├── migrations/         # Alembic database migrations
│   └── tests/              # Test suite
├── packages/
│   ├── ingestion/          # F1 data ingestion pipeline
│   ├── ml/                 # Machine learning models and training
│   └── workers/            # Background job processors
└── infra/                  # Infrastructure configuration
    ├── docker-compose.yml  # Local development environment
    └── postgres/           # Database initialization scripts
```

## Getting Started

### Prerequisites

- Node.js 18+ (for frontend)
- Python 3.9+ (for backend)
- Docker & Docker Compose (for infrastructure)
- PostgreSQL 15+ (or use Docker)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd "Formula 1"
   ```

2. **Start infrastructure services**
   ```bash
   cd infra
   docker-compose up -d
   ```
   This starts PostgreSQL, TimescaleDB, Kafka, and Kafka UI.

3. **Setup backend**
   ```bash
   cd backend
   pip install -r ../requirements.txt
   flask db upgrade  # Run migrations
   python main.py
   ```
   The backend API will be available at `http://localhost:8000`

4. **Setup frontend**
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```
   The frontend will be available at `http://localhost:3000`

## Configuration

Environment variables are managed through `.env` files. Key configurations:

- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection URL
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses
- `MLFLOW_TRACKING_URI`: MLflow server URL
- `AUTO_INGEST_ENABLED`: Enable automatic F1 data ingestion

## Development

### Running Tests

**Frontend:**
```bash
cd frontend
pnpm test
```

**Backend:**
```bash
cd backend
pytest
```

### Code Quality

**Frontend linting:**
```bash
cd frontend
pnpm lint
```

**Database Migrations:**
```bash
cd backend
alembic upgrade head
```

## API Documentation

The backend provides REST API endpoints for:

- `/api/sessions` - Race and practice session data
- `/api/drivers` - Driver information and statistics
- `/api/laps` - Lap telemetry and timing
- `/api/analysis` - Performance analysis and comparisons
- `/api/health` - Service health checks

## Deployment

The project is configured for deployment on:

- **Frontend**: Vercel (optimized for Next.js)
- **Backend**: Railway or similar container platforms
- **Infrastructure**: Kubernetes-ready with Docker Compose for local development

## Data Pipeline

1. **Ingestion**: Automated service pulls official F1 data
2. **Processing**: Data is validated, enriched, and stored in TimescaleDB
3. **Streaming**: Events are published to Kafka topics for real-time consumers
4. **Analysis**: ML models process telemetry for predictions
5. **Visualization**: Frontend retrieves and visualizes data via REST API

## Contributing

1. Create a feature branch (`git checkout -b feature/amazing-feature`)
2. Commit your changes (`git commit -m 'Add amazing feature'`)
3. Push to the branch (`git push origin feature/amazing-feature`)
4. Open a Pull Request

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). See the LICENSE file for details.

## Support

For issues, questions, or suggestions, please open an issue on the repository.

---

**Last Updated**: June 2026
