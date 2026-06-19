# Multi-stage build: one image serving the Django API + the built React SPA.
# Designed for Google Cloud Run (binds $PORT, defaults to 8080).

# --- Stage 1: build the React frontend ---------------------------------------
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty base URL => the SPA calls the API on the same origin (no CORS).
ENV VITE_API_BASE_URL=""
RUN npm run build

# --- Stage 2: Django backend + bundled SPA -----------------------------------
FROM python:3.12-slim AS backend
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# System deps for psycopg2 / pyarrow wheels are not needed (manylinux wheels),
# but keep build-essential out to stay slim.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend source.
COPY backend/ ./

# Bundle the compiled SPA so WhiteNoise can serve it (see settings.FRONTEND_DIST).
COPY --from=frontend /frontend/dist ./frontend_dist

# Collect Django's own static (admin, DRF) into STATIC_ROOT at build time.
RUN python manage.py collectstatic --noinput

EXPOSE 8080

# Run DB migrations on startup, then serve. Shell form so $PORT expands.
CMD python manage.py migrate --noinput && \
    gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 120
