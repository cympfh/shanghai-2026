FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY streamlit_app.py .

# Expose Streamlit default port
EXPOSE 8096

# Set environment variable (can be overridden at runtime)
ENV SHANGHAI_SECRET_KEY=""

# Run Streamlit with base path /shanghai
CMD ["uv", "run", "streamlit", "run", "streamlit_app.py", "--server.baseUrlPath=/shanghai", "--server.port=8096", "--server.address=0.0.0.0"]
