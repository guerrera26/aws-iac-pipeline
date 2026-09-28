import os
import platform
import time
from datetime import datetime, timezone

import psycopg2
from flask import Flask, jsonify

app = Flask(__name__)

APP_VERSION = "1.1.0"
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


@app.route("/")
def index():
    return jsonify(
        message="AWS IaC Pipeline demo app",
        endpoints=["/health", "/api/status", "/api/visits"],
    ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
