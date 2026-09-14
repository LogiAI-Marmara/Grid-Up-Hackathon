# Grid-Up collection service — on-premise image.
#
# Public cloud is forbidden for this project (see the decision record), so this
# image assumes nothing about the internet at run time: no managed database, no
# hosted queue, no external API. It talks to a PostgreSQL it is pointed at and to
# nothing else.
#
# BUILD CONTEXT IS THE REPOSITORY ROOT, not this folder. The service imports the
# shared contracts from /sozlesmeler, and that folder must be in the image:
#
#     docker build -f toplama/Dockerfile -t gridup/toplama:1.0.0 .
#
# Run against the file backend (no database needed, for a smoke test):
#
#     docker run --rm -p 8000:8000 -e TOPLAMA_KAYIT=dosya \
#         -v "$PWD/veri:/veri" -e TOPLAMA_DOSYA_DIZIN=/veri gridup/toplama:1.0.0
#
# Run against PostgreSQL 16 (the reference database; track C's compose file wires
# the two together):
#
#     docker run --rm -d --name gridup-db \
#         -e POSTGRES_PASSWORD=gridup -e POSTGRES_DB=gridup postgres:16
#     docker exec -i gridup-db psql -U postgres -d gridup < toplama/migrations/001_sema_ve_referans.sql
#     docker exec -i gridup-db psql -U postgres -d gridup < toplama/migrations/002_olcum.sql
#     docker exec -i gridup-db psql -U postgres -d gridup < toplama/migrations/003_termal.sql
#     docker run --rm -p 8000:8000 --link gridup-db \
#         -e TOPLAMA_KAYIT=postgres \
#         -e DATABASE_URL=postgresql://postgres:gridup@gridup-db:5432/gridup \
#         gridup/toplama:1.0.0

FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: the image layer should not carry .pyc files.
# PYTHONUNBUFFERED: logs must reach `docker logs` immediately, or a demo is
# debugged blind.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/toplama \
    TOPLAMA_KAYIT=postgres \
    TOPLAMA_DOSYA_DIZIN=/veri \
    TOPLAMA_HOST=0.0.0.0 \
    TOPLAMA_PORT=8000

WORKDIR /app

# Dependencies first, in their own layer: they change far less often than the
# code, so a code edit does not reinstall the world.
COPY toplama/requirements.txt /app/toplama/requirements.txt
RUN pip install --no-cache-dir -r /app/toplama/requirements.txt

# The two folders the service needs, keeping the repository layout so that
# `parents[2]` still resolves to the root inside the container.
COPY sozlesmeler/ /app/sozlesmeler/
COPY toplama/ /app/toplama/

# Not root. The service writes nothing except the optional JSONL volume.
RUN useradd --create-home --uid 10001 gridup \
    && mkdir -p /veri \
    && chown -R gridup:gridup /veri /app
USER gridup

EXPOSE 8000

# /saglik reports the storage backend too, so an unhealthy container is one that
# cannot write, not merely one whose process is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys,json; \
r=json.load(urllib.request.urlopen('http://127.0.0.1:8000/saglik', timeout=4)); \
sys.exit(0 if r['depo']['durum'] == 'hazir' else 1)"

CMD ["python", "-m", "uvicorn", "toplama.uygulama:uygulama", "--host", "0.0.0.0", "--port", "8000"]
