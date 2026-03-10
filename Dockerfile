# Use Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Database configuration (override at runtime)
ENV DATABASE_URL=mysql+pymysql://root:password@host.docker.internal:3306/canteen_db
ENV SECRET_KEY=mmcoe-secret-key-2025-super-secure

# Copy dependency file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy ALL backend files
COPY . .

# Expose Flask port
EXPOSE 5000

# Run the app
CMD ["python", "app.py"]
