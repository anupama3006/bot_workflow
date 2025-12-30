
import os
import secrets
from dataclasses import dataclass

from .secret_manager import SecretManager
import psycopg2

@dataclass
class Settings:
    _instance = None
    # aws keys
    aws_region = os.environ.get("AWS_REGION")
    app_secret_id = None
    db_secret_id = os.environ.get("DB_SECRET_ID")

    # Database schema configurations
    workflow_schema: str = os.getenv("WORKFLOW_SCHEMA", "workflows")
    cube_assist_schema: str = os.getenv("CUBE_ASSIST_SCHEMA", "supplychain_assist")

    # llm keys
    llm_type = None #os.environ.get("LLM_TYPE")
    llm_model =None # os.environ.get("LLM_MODEL")
    openai_endpoint =None # os.environ.get("OPENAI_ENDPOINT")
    openai_api_version = None #os.environ.get("OPENAI_API_VERSION")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    llm_max_token = None#os.environ.get("LLM_MAX_TOKEN")
    llm_fetch_max_token = None#os.environ.get("LLM_FETCH_MAX_TOKEN")

    # application / agent keys
    python_exe = None#os.environ.get("PYTHON_EXE", "python")
    logging_level = None#os.environ.get("LOGGING_LEVEL", "DEBUG")
    app_logging_level = None#os.environ.get("APP_LOGGING_LEVEL", "INFO")
    app_name = os.environ.get("APP_NAME")
    env = os.environ.get("ENV", "local")
    agent_db_host = os.environ.get("DB_HOST")
    agent_db_name = os.environ.get("DB_NAME")
    agent_db_user =None# os.environ.get("DB_USER")
    agent_db_password = None#os.environ.get("DB_PASSWORD")
    agent_db_port =os.environ.get("DB_PORT")
    cubeassist_mcp_server_url = None #os.environ.get("CUBEASSIST_MCP_SERVER_URL")
    a2a_server_url = None #os.environ.get("A2A_SERVER_URL")'
    confidence = None #os.environ.get("CONFIDENCE_THRESHOLD", "0.7")
    temperature = None #os.environ.get("TEMPERATURE", "0.3")

    # pipeline keys:
    pipeline_graphql_url = None #os.environ.get("PIPELINE_GRAPHQL_URL")
    common_graphql_url = None #os.environ.get("COMMON_GRAPHQL_URL")
    pipeline_referer_url = None #os.environ.get("PIPELINE_ORIGIN_URL")
    pipeline_origin_url = None #os.environ.get("PIPELINE_REFERER_URL")

    def __init__(self):
        db_secrets = SecretManager.get_secrets(self.aws_region, self.db_secret_id)
        self.agent_db_user= db_secrets.get('username')
        self.agent_db_password = db_secrets.get('password')
        self.load_from_db()
        app_secrets = SecretManager.get_secrets(self.aws_region, self.app_secret_id)
        self.openai_api_key = app_secrets.get('OPENAI_API_KEY')
      
    def load_from_db(self):
        conn = psycopg2.connect(
            host=self.agent_db_host,
            database=self.agent_db_name,
            user=self.agent_db_user,
            password=self.agent_db_password,
            port=self.agent_db_port,
        )
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT a.agent_id, acs.key, acs.value
                    FROM supplychain_assist.agent a
                    INNER JOIN supplychain_assist.agent_config_store acs
                        ON a.agent_id = acs.agent_id
                    WHERE a.name = %s
                """
                cur.execute(query, (self.app_name,))
                rows = cur.fetchall()
                for row in rows:
                    _, key, value = row
                    key_lower = key.lower()
                    if hasattr(self, key_lower):
                        setattr(self, key_lower, value)
                    else:
                        continue
                        # raise AttributeError(f"Unknown configuration key from DB: {key}")
        finally:
            conn.close()

    def reload(self):
        Settings._instance = None


SETTINGS = Settings()