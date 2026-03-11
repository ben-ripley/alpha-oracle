FROM python:3.11-slim

WORKDIR /app

# Install build deps + TA-Lib C library (required by ta-lib Python package)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential wget \
    && wget -q https://github.com/TA-Lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz \
    && tar xzf ta-lib-0.6.4-src.tar.gz \
    && cd ta-lib-0.6.4 \
    && ./configure --prefix=/usr \
    && make -j$(nproc) \
    && make install \
    && cd .. && rm -rf ta-lib-0.6.4 ta-lib-0.6.4-src.tar.gz \
    && rm -rf /var/lib/apt/lists/*

# Copy source first — setuptools needs src/ to find packages
COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
