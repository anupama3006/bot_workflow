import time

import psycopg2

from .logging import logger
from .settings import SETTINGS


class Postgress:
    def get_connection(self, retries=3, delay=2):
        attempt = 0
        while attempt < retries:
            try:
                conn = psycopg2.connect(
                    host=SETTINGS.agent_db_host,
                    database=SETTINGS.agent_db_name,
                    user=SETTINGS.agent_db_user,
                    password=SETTINGS.agent_db_password,
                    port=SETTINGS.agent_db_port,
                )
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    # Include workflow schema first, then existing schemas
                    search_path = f'{SETTINGS.workflow_schema},pipeline,{SETTINGS.cube_assist_schema},public'
                    cur.execute(f'SET search_path TO {search_path};')
                    conn.commit()
                return conn
            except psycopg2.OperationalError as e:
                if "password authentication failed" in str(e):
                    logger.error("Database connection failed: password authentication failed.")
                    attempt += 1
                    SETTINGS.reload()
                    if attempt < retries:
                        logger.info(f"Retrying database connection (attempt {attempt + 1}/{retries}) in {delay} seconds...")
                        time.sleep(delay)
                else:
                    raise

    def execute_query(self, query, params=None, fetch=False):
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(query, params)
                if fetch:
                    result = cur.fetchall()
                else:
                    result = None
                conn.commit()
                return result
        finally:
            if conn:
                conn.close()
