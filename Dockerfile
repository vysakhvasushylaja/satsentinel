FROM node:22-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:$PATH"
COPY . .
RUN cd meterless-starter && npm install --no-audit --no-fund && npm run setup
RUN python make_data.py && python make_data_real.py
ENV SAMPLE_MODE=1 HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["python", "run.py"]
