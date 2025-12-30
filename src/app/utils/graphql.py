
import json
from typing import Any, Dict

import requests

from .settings import SETTINGS


class GraphQLClient:
    def __init__(self, token: str = None):
        self.token = token

    def invoke(self, payload: Dict[str, Any] | str, url_type: str = "pipeline") -> Dict[str, Any]:
        # Select URL based on url_type
        if url_type == "pipeline":
            url = SETTINGS.pipeline_graphql_url
        elif url_type == "api-common":
            url = SETTINGS.common_graphql_url
        else:
            raise ValueError(f"Unknown url_type: {url_type}")

        # Convert string payload to dict
        if isinstance(payload, str):
            payload = json.loads(payload)

        headers = {
            "accept": "*/*",
            "authorization": f"{self.token}",
            "content-type": "application/json",
            "origin": SETTINGS.pipeline_origin_url,
            "referer": SETTINGS.pipeline_referer_url,
            "x-path": "/",
            "priority": "u=1, i",
            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            raise RuntimeError(f"Request failed with status {response.status_code}: {response.text}")
