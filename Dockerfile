FROM python:3.12-slim

# Install SWI-Prolog
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        gnupg2 \
        curl && \
    curl -fsSL https://swi-prolog.org/swipl-apt.key | gpg --dearmor -o /usr/share/keyrings/swi-prolog.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/swi-prolog.gpg] https://swi-prolog.org/debian stable main" > /etc/apt/sources.list.d/swi-prolog.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends swi-prolog && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY euclid_mcp/ euclid_mcp/

# Install Python dependencies and package
RUN pip install --no-cache-dir . && \
    rm -rf /root/.cache

EXPOSE 8000

CMD ["python3", "-m", "euclid_mcp"]
