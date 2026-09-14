FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY alarm_service.py .
CMD ["python", "alarm_service.py"]