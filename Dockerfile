# =============================================================================
# ESSEN — MMCOE Canteen Backend
# Production Dockerfile for Render deployment with Supabase PostgreSQL
# =============================================================================

# Use slim Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# =============================================================================
# ENVIRONMENT — defaults only, real values set in Render dashboard
# Never hardcode real secrets here — this file is committed to GitHub
# =============================================================================
ENV FLASK_ENV=production
ENV FLASK_DEBUG=0
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# DATABASE_URL, SECRET_KEY, FIREBASE_PROJECT_ID etc.
# are injected by Render at runtime — do NOT set them here

# =============================================================================
# DEPENDENCIES
# =============================================================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# APP FILES
# Copy everything EXCEPT files listed in .dockerignore
# =============================================================================
COPY . .

# =============================================================================
# PORT
# Render expects port 10000 by default but we use 5000 — tell Render via
# the PORT env var or just expose 5000 and set it in Render dashboard
# =============================================================================
EXPOSE 5000

# =============================================================================
# START COMMAND
# Use gunicorn in production (not Flask dev server)
# Workers: 2 is safe for Render free tier (512MB RAM)
# Timeout: 120s for slow cold starts on free tier
# =============================================================================
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--log-level", "warning", "app:app"]