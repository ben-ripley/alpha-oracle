---
title: Getting Started
nav_order: 1
parent: Developer Guide
has_children: true
---

# Prerequisites

This page documents the system requirements and tools needed to run **alpha-oracle** in a local development environment.

## System Requirements

### Operating System

- **macOS** (10.15+)
- **Linux** (Ubuntu 20.04+, Debian 11+, Fedora 35+, or equivalent)
- **Windows** via WSL2 (Windows Subsystem for Linux 2)

> **Note**: Native Windows is not officially supported. Use WSL2 with Ubuntu 22.04 for best results.

### Hardware

- **CPU**: 4+ cores recommended (6+ for ML training)
- **RAM**: 8 GB minimum, 16 GB recommended (32 GB for large backtests)
- **Disk**: 20 GB free space (50+ GB for extensive historical data and Parquet cache)

## Required Software

### Python 3.11+

The project requires Python 3.11 or later. Check your version:

```bash
python3 --version
```

**Installation:**

- **macOS**: `brew install python@3.11`
- **Ubuntu/Debian**: `sudo apt install python3.11 python3.11-venv python3.11-dev`
- **Fedora**: `sudo dnf install python3.11`

### Node.js 18+ and npm

Required for the React dashboard frontend.

```bash
node --version  # Should be 18.x or higher
npm --version
```

**Installation:**

- **macOS**: `brew install node@18`
- **Linux**: Use [nvm](https://github.com/nvm-sh/nvm) or [NodeSource binaries](https://github.com/nodesource/distributions)
- **Windows (WSL2)**: Use nvm

### Docker and Docker Compose

The system uses Docker Compose to run infrastructure services ([TimescaleDB](../glossary.md#timescaledb), [Redis](../glossary.md#redis), [Prometheus](../glossary.md#prometheus), [Grafana](../glossary.md#grafana)).

```bash
docker --version         # Should be 24.0+
docker compose version   # Should be 2.20+
```

**Installation:**

- **macOS**: Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Linux**: Follow [Docker Engine installation](https://docs.docker.com/engine/install/) and [Docker Compose plugin](https://docs.docker.com/compose/install/linux/)
- **Windows (WSL2)**: Install Docker Desktop with WSL2 backend

> **Important**: Ensure the Docker daemon is running before starting the backend.

### Git

Version control for the repository.

```bash
git --version  # Should be 2.30+
```

**Installation:**

- **macOS**: `brew install git` (or use Xcode Command Line Tools)
- **Linux**: `sudo apt install git` (Ubuntu/Debian) or `sudo dnf install git` (Fedora)

## Optional Software

### IB Gateway or TWS

Required for **live or paper broker connections** to Interactive Brokers. Not needed for local development if you use the simulated broker (`SA_BROKER__PROVIDER=simulated`).

- **IB Gateway** (headless): Recommended for server deployments
  - Paper trading: port 4002
  - Live trading: port 4001
- **TWS** (Trader Workstation): GUI application
  - Paper trading: port 7497
  - Live trading: port 7496

**Download**: [Interactive Brokers Gateway/TWS](https://www.interactivebrokers.com/en/trading/tws.php)

> **Security**: Always test with paper trading first. Never commit IBKR credentials to version control.

### TA-Lib C Library

The Python `ta-lib` package (used for technical indicators) requires the TA-Lib C library. The project uses a fallback (`ta` library) if TA-Lib is unavailable, so it's **optional but recommended**.

**Installation:**

- **macOS**: `brew install ta-lib`
- **Ubuntu/Debian**:
  ```bash
  wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
  tar -xzf ta-lib-0.4.0-src.tar.gz
  cd ta-lib/
  ./configure --prefix=/usr
  make
  sudo make install
  ```
- **Fedora**: `sudo dnf install ta-lib-devel`

## Required Environment Variables

Create a `.env` file in the project root with the following variables:

### Core Configuration

```bash
# Alpha Vantage API key (required for market data backfill)
SA_ALPHA_VANTAGE_API_KEY=your_api_key_here
```

**Get a free API key**: [Alpha Vantage](https://www.alphavantage.co/support/#api-key)

### Optional Configuration

```bash
# Broker provider: "ibkr" (IB Gateway), "simulated" (in-memory), or anything else (demo stub)
SA_BROKER__PROVIDER=simulated

# IBKR connection (only if SA_BROKER__PROVIDER=ibkr)
SA_BROKER__IBKR__HOST=127.0.0.1
SA_BROKER__IBKR__PORT=4002          # IB Gateway paper=4002, live=4001
SA_BROKER__IBKR__CLIENT_ID=1
SA_BROKER__IBKR__ACCOUNT_ID=        # Leave blank for single-account setup

# Database (override docker-compose defaults)
SA_DATABASE__URL=postgresql+asyncpg://trader:dev_password@localhost:5432/stock_analysis

# Redis (override docker-compose defaults)
SA_REDIS__URL=redis://localhost:6379/0
```

> **Tip**: Copy `.env.example` (if provided) and fill in your API keys.

## Verify Prerequisites

Run the following commands to verify your setup:

```bash
# Python
python3 --version                  # 3.11+
python3 -m pip --version

# Node.js
node --version                     # 18+
npm --version

# Docker
docker --version                   # 24.0+
docker compose version             # 2.20+
docker ps                          # Should not error

# Git
git --version                      # 2.30+
```

## Next Steps

Proceed to [Local Development Setup](local-setup.md) to clone the repository and start the services.
