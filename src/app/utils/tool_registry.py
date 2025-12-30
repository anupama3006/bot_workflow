from app.utils.logging import logger
from app.utils.postgress import Postgress


class ToolRegistry:
    """Tool registry with cached descriptions - Singleton implementation."""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if not ToolRegistry._initialized:
            self._template_cache = self._load_tool_descriptions()
            ToolRegistry._initialized = True
            logger.info("ToolRegistry singleton initialized")

    def get(self, tool_name: str) -> str:
        """Get description for a tool - uses cache."""
        descriptions = self._template_cache 
        description = descriptions.get(tool_name, "")

        if not description:
            logger.warning(f"No description found for tool: {tool_name}")

        return description

    def _load_tool_descriptions(self) -> dict:
        """Load all tool descriptions from database - CACHED."""
        try:
            db = Postgress()
            query = "SELECT name, description FROM supplychain_assist.mcp_tools"
            rows = db.execute_query(query, fetch=True)

            descriptions = {}
            for tool_name, description in rows:
                descriptions[tool_name] = description

            logger.info(f"✓ Cached {len(descriptions)} tool descriptions")
            return descriptions

        except Exception as e:
            logger.error(f"✗ Failed to load tool descriptions: {e}")
            return {}
