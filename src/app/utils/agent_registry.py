import json

from a2a.types import AgentSkill

from app.utils.postgress import Postgress


class AgentRegistry:
    _instances = {}
    _agent_data_cache = {}
    
    def __new__(self, agent_name: str):
        if agent_name not in self._instances:
            self._instances[agent_name] = super().__new__(self)
        return self._instances[agent_name]

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        if agent_name not in self._agent_data_cache:
            self._agent_data_cache = self._get_agent_data(agent_name)

    def _get_agent_data(self, agent_name: str) -> dict:
        tools = []
        db = Postgress()
        query = """
            SELECT a.agent_id, a.name, a.description, a.skills, a.a2a_endpoint, mt."name"    
            FROM supplychain_assist.agent a
            LEFT OUTER JOIN supplychain_assist.agent_tools at on a.agent_id  = at.agent_id 
            LEFT OUTER JOIN supplychain_assist.mcp_tools mt on mt.tool_id  = at.tool_id  
            WHERE a.name = %s
        """
        rows = db.execute_query(query, params=(agent_name,), fetch=True)
        first_row = rows[0]
        for row in rows:
           tools.append(row[5])

        return {'agent_id': first_row[0], 'name': first_row[1], 'description': first_row[2], 'skills': first_row[3], 'endpoint': first_row[4], 'tools': tools}

    def get_name(self) -> str:
        return self._agent_data_cache.get('name', '')

    def get_description(self) -> str:
        return self._agent_data_cache.get('description', '')

    def get_url(self) -> str:
        return self._agent_data_cache.get('endpoint', '')

    def get_skills(self) -> list[AgentSkill]:
        skills_data = self._agent_data_cache.get('skills', [])

        # Parse JSON if string
        if isinstance(skills_data, str):
            skills_data = json.loads(skills_data)

        skills = []
        for skill in skills_data:
            skills.append(
                AgentSkill(
                    id=skill.get('id', ''), name=skill.get('name', ''), description=skill.get('description', ''), tags=skill.get('tags', []), examples=skill.get('examples', [])
                )
            )
        return skills

    def get_tool(self) -> str:
        return self._agent_data_cache.get('tools', '')

