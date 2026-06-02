# Formula 1 Project - Setup Guide

Quick guide to get started with all the new improvements.

---

## Installation

### Frontend Setup

```bash
cd frontend

# Install dependencies (includes Playwright)
npm install

# Install Playwright browsers (for E2E tests)
npm run playwright:install
```

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies (optional)
pip install -e ".[dev]"
```

---

## 🏃 Running the Application

### Development Mode

**Frontend:**
```bash
cd frontend
npm run dev
```
Opens at: http://localhost:3000

**Backend:**
```bash
cd backend
python main.py
```
Runs at: http://localhost:8000

---

##  Running Tests

### Frontend Tests

**Unit Tests (Vitest):**
```bash
cd frontend
npm run test          # Run once
npm run test:watch    # Watch mode
```

**E2E Tests (Playwright):**
```bash
cd frontend
npm run test:e2e           # Headless mode
npm run test:e2e:ui        # Interactive UI mode
npm run test:e2e:headed    # With browser visible
```

### Backend Tests

```bash
cd backend
pytest                     # Run all tests
pytest --cov=backend       # With coverage
pytest tests/test_health.py  # Specific test
```

---

## Development Tools

### Linting

**Frontend:**
```bash
cd frontend
npm run lint
```

**Backend:**
```bash
cd backend
black src/          # Format code
isort src/          # Sort imports
mypy src/           # Type checking
flake8 src/         # Linting
```

### Building

**Frontend:**
```bash
cd frontend
npm run build       # Production build
npm run start       # Run production build
```

---

## Using New Features

### 1. Logging Service

```typescript
import { logger } from '@/lib/logger'

// In your components or API calls
logger.info('Action completed', { userId: 123 })
logger.error('Something failed', error, { context: 'data' })
logger.fetchError('sessions', error, { endpoint: '/api/sessions' })
```

### 2. Error Boundaries

Already added to root layout! Errors are automatically caught and displayed nicely.

To add custom error boundaries:
```typescript
import ErrorBoundary from '@/components/ErrorBoundary'

<ErrorBoundary>
  <YourComponent />
</ErrorBoundary>
```

### 3. Rate Limiting (Backend)

```python
from backend.middleware import rate_limit_moderate

@app.route('/api/v1/your-endpoint')
@rate_limit_moderate  # 50 requests per minute
def your_endpoint():
    return {'data': 'value'}
```

---

## Environment Variables

### Frontend (`.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Backend (`.env`)

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/f1db
SECRET_KEY=your-secret-key
DEBUG=true
```

---

## Project Structure

```
Formula 1/
├── frontend/
│   ├── app/                    # Next.js pages
│   ├── components/             # React components
│   │   └── ErrorBoundary.tsx   # ✨ NEW
│   ├── lib/
│   │   └── logger.ts           # ✨ NEW
│   ├── e2e/                    # ✨ NEW E2E tests
│   └── playwright.config.ts    # ✨ NEW
├── backend/
│   ├── src/backend/
│   │   ├── api/                # API endpoints
│   │   └── middleware/         # ✨ NEW
│   │       └── rate_limit.py   # ✨ NEW
│   ├── tests/                  # Backend tests
│   └── pyproject.toml          # ✨ NEW
└── Documentation files
```

---

## Troubleshooting

### Frontend Issues

**Port already in use:**
```bash
# Kill process on port 3000
# Windows:
netstat -ano | findstr :3000
taskkill /PID <PID> /F

# Mac/Linux:
lsof -ti:3000 | xargs kill -9
```

**Playwright browsers not installed:**
```bash
npm run playwright:install
```

### Backend Issues

**Database connection failed:**
- Check DATABASE_URL in .env
- Ensure PostgreSQL is running
- Verify database exists

**Import errors:**
- Ensure virtual environment is activated
- Check PYTHONPATH includes src/
- pyproject.toml should fix this automatically

---

## Documentation

- **Main README:** Project overview
- **FIXES_APPLIED.md:** Recent bug fixes
- **IMPROVEMENTS_COMPLETED.md:** New features added
- **PROJECT_SCAN_REPORT.md:** Full project analysis

---

## Quick Commands Reference

### Frontend
```bash
npm run dev              # Start dev server
npm run build            # Production build
npm run lint             # Run linter
npm run test             # Run unit tests
npm run test:e2e         # Run E2E tests
```

### Backend
```bash
python main.py           # Start server
pytest                   # Run tests
black src/               # Format code
```

---

## Verification

After setup, verify everything works:

1. **Frontend runs:** http://localhost:3000
2. **Backend runs:** http://localhost:8000/health
3. **Tests pass:** `npm run test` and `pytest`
4. **E2E tests work:** `npm run test:e2e`
5. **Theme toggle works:** Click sun/moon icon
6. **Logo shows:** Favicon image in navbar

---

## Getting Help

If you encounter issues:

1. Check the documentation files
2. Review error logs (now using logger service!)
3. Check browser console (F12)
4. Verify environment variables
5. Ensure all dependencies are installed

---

## You're Ready!

Everything is set up and ready to go. Start developing with:

```bash
# Terminal 1 - Backend
cd backend
python main.py

# Terminal 2 - Frontend
cd frontend
npm run dev
```

Visit http://localhost:3000 and start building!

---

**Happy Coding!**