FROM python:3.12-slim

WORKDIR /app

# Install ALL build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    libpng-dev \
    libjpeg-dev \
    libfreetype6-dev \
    libffi-dev \
    libssl-dev \
    swig \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt

# Copy source code
COPY . .

# Create data directory
RUN mkdir -p /app/data/stockai_data

# Environment variables
ENV FLASK_ENV=production
ENV FLASK_DEBUG=0
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Start with gunicorn
CMD cd backend && gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile -
