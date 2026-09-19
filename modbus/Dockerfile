FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir "pymodbus==3.6.9" aiohttp
COPY modbus_server.py .
EXPOSE 5020
CMD ["python", "modbus_server.py"]