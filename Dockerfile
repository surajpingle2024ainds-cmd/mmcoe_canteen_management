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
# =============================================================================
ENV FLASK_ENV=production
ENV FLASK_DEBUG=0
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Render injects PORT automatically — default to 10000 if not set
ENV PORT=10000

# =============================================================================
# DEPENDENCIES
# =============================================================================
COPY requirements.txt .
# Upgrade pip first, then install pinned deps
RUN pip install --upgrade pip --no-cache-dir \
 && pip install --no-cache-dir -r requirements.txt

# =============================================================================
# APP FILES
# =============================================================================
COPY . .

# =============================================================================
# PORT — use Render's dynamic PORT env var
# =============================================================================
EXPOSE $PORT

# =============================================================================
# HEALTH CHECK — Docker/Render restarts container if /health stops responding
# interval: how often to check · timeout: max response wait · retries: before unhealthy
# =============================================================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-10000}/health')" || exit 1

# =============================================================================
# START — gunicorn binds to whatever port Render assigns via $PORT
# Workers: 2 is safe for Render free tier (512MB RAM)
# Timeout: 120s for slow cold starts on free tier
# preload: saves memory by loading app code once before forking workers
# =============================================================================
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --log-level warning --preload app:app