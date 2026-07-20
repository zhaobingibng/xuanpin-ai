FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --quiet

# Copy application code
COPY . .

# Install Playwright browsers
RUN uv run playwright install chromium --with-deps

# Create directories
RUN mkdir -p storage/cookies storage/crawler logs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start application
CMD ["uv", "run", "python", "startup.py"]
