import json

import boto3


class SecretManager:
    @staticmethod
    def get_secrets(aws_region: str, secret_id: str) -> dict:
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=aws_region)
        get_secret_value_response = client.get_secret_value(SecretId=secret_id)
        if "SecretString" in get_secret_value_response:
            secret_dict = json.loads(get_secret_value_response["SecretString"])
            return secret_dict
