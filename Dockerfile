FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python make_data.py && python make_data_real.py
ENV SAMPLE_MODE=1 HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["python", "run.py"]
