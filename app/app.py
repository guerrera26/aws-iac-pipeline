import os
import platform
import time
from datetime import datetime, timedelta, timezone

import psycopg2
from flask import Flask, Response, jsonify, request
from werkzeug.utils import secure_filename

import cleaner

app = Flask(__name__)

# Upload cap for the data-cleaning demo. nginx's client_max_body_size is set a
# little higher (ansible/templates/nginx-flaskapp.conf.j2) so oversized uploads
# get this app's JSON error rather than an nginx HTML error page.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

APP_VERSION = "1.2.0"
START_TIME = time.time()


def _get_db_password():
    """Resolve the DB password: directly from env (local/dev/CI-with-throwaway-db),
    or from SSM Parameter Store via the instance's IAM role (production EC2)."""
    if os.environ.get("DB_PASSWORD"):
        return os.environ["DB_PASSWORD"]

    ssm_param = os.environ.get("DB_PASSWORD_SSM_PARAM")
    if not ssm_param:
        return None

    import boto3  # imported lazily so local dev without AWS creds isn't affected

    client = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    response = client.get_parameter(Name=ssm_param, WithDecryption=True)
    return response["Parameter"]["Value"]


def get_db_connection():
    host = os.environ.get("DB_HOST")
    if not host:
        return None
    return psycopg2.connect(
        host=host,
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "appdb"),
        user=os.environ.get("DB_USER", "appadmin"),
        password=_get_db_password(),
        connect_timeout=5,
    )


@app.route("/health")
def health():
    """Liveness check: used by load balancers / monitoring to confirm the process is up."""
    return jsonify(status="ok"), 200


@app.route("/api/status")
def status():
    """Richer status payload: hostname, uptime, version — useful for debugging a live deploy."""
    uptime_seconds = round(time.time() - START_TIME, 2)
    return jsonify(
        hostname=platform.node(),
        uptime_seconds=uptime_seconds,
        version=APP_VERSION,
        server_time=datetime.now(timezone.utc).isoformat(),
    ), 200


@app.route("/api/visits")
def visits():
    """Backend/data demo: each request records a visit in Postgres and
    returns the running total — a minimal example of the app talking to
    a real relational database rather than just serving static JSON."""
    conn = get_db_connection()
    if conn is None:
        return jsonify(error="database not configured"), 503

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS visits (
                        id SERIAL PRIMARY KEY,
                        visited_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute("INSERT INTO visits DEFAULT VALUES")
                cur.execute("SELECT COUNT(*) FROM visits")
                total = cur.fetchone()[0]
        return jsonify(visits=total), 200
    finally:
        conn.close()


@app.route("/api/visits/summary")
def visits_summary():
    """Analytics endpoint: total visits, visits in the last 24h, and an
    hourly time series for the last 24 hours (zero-filled for hours with
    no traffic) — the aggregation query behind the frontend's chart."""
    conn = get_db_connection()
    if conn is None:
        return jsonify(error="database not configured"), 503

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM visits")
                total = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT date_trunc('hour', visited_at) AS hour, COUNT(*)
                    FROM visits
                    WHERE visited_at >= now() - interval '24 hours'
                    GROUP BY hour
                    ORDER BY hour
                    """
                )
                rows = cur.fetchall()

        counts_by_hour = {hour.replace(minute=0, second=0, microsecond=0): count for hour, count in rows}

        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        hourly = []
        for i in range(23, -1, -1):
            bucket = now - timedelta(hours=i)
            # counts_by_hour keys come back tz-aware from Postgres; compare on the naive
            # hour value since psycopg2 may return either depending on session tz config
            count = next(
                (c for h, c in counts_by_hour.items() if h.replace(tzinfo=None) == bucket.replace(tzinfo=None)),
                0,
            )
            hourly.append({"hour": bucket.strftime("%H:00"), "count": count})

        last_24h = sum(h["count"] for h in hourly)

        return jsonify(total=total, last_24h=last_24h, hourly=hourly), 200
    finally:
        conn.close()


@app.errorhandler(413)
def upload_too_large(_error):
    return jsonify(error=f"file too large (the limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"), 413


@app.route("/api/clean/sample")
def clean_sample():
    """A deliberately messy CSV so visitors can try the cleaner without uploading anything."""
    return Response(cleaner.SAMPLE_CSV, mimetype="text/csv")


@app.route("/api/clean", methods=["POST"])
def clean():
    """Data-cleaning demo: upload a CSV (multipart field 'file', optional JSON field
    'options') and get back a report of what was fixed, a before/after preview, and
    the cleaned CSV. Stateless — the file is processed in memory and is never
    written to disk or to the database."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(error="no file uploaded (send a CSV as the multipart field 'file')"), 400

    try:
        options = cleaner.parse_options(request.form.get("options"))
        result = cleaner.clean_csv(cleaner.decode_bytes(upload.read()), options)
    except cleaner.CleanerError as exc:
        return jsonify(error=str(exc)), 422

    safe_name = secure_filename(upload.filename) or "data.csv"
    result["filename"] = safe_name
    result["cleaned_filename"] = f"{os.path.splitext(safe_name)[0]}_cleaned.csv"
    return jsonify(result), 200


@app.route("/")
def index():
    return jsonify(
        message="AWS IaC Pipeline demo app",
        endpoints=[
            "/health",
            "/api/status",
            "/api/visits",
            "/api/visits/summary",
            "/api/clean",
            "/api/clean/sample",
        ],
    ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
