
from app.agent.state import AgentState
from app.utils.postgress import Postgress
from app.utils.utilities import Utilities


class AgentTrace:
    def __init__(self, conversation_id: str, agent_name: str, user_id: str = ''):
        self.conversation_id = conversation_id
        self.agent_name = agent_name
        self.user_id = user_id
        self.db = Postgress()

    def save_agent_interaction_trace(self, task_id: str, input_payload: str, output_payload: str, status: str, execution_duration: float, target_agent_name: str = '') -> None:
        query = """
            INSERT INTO supplychain_assist.agent_interaction_trace
            (context_id, task_id, source_agent_name, target_agent_name, input_payload, output_payload, status, execution_duration, execution_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
        """
        self.db.execute_query(query, params=(self.conversation_id, task_id, self.agent_name, target_agent_name, input_payload, 
                                             output_payload, status, execution_duration), 
                              fetch=False)

    def save_agent_mcp_interaction_trace(self, task_id: str, tool_name: str, input_payload: str, output_payload: str, status: str, execution_duration:float) -> None:
        query = """
            INSERT INTO supplychain_assist.agent_mcp_interaction_trace
            (context_id, task_id, agent_name, tool_name, input_payload, output_payload, status, execution_duration, execution_time)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, now())
        """
        self.db.execute_query(query, 
                              params=(self.conversation_id, task_id, self.agent_name, tool_name, Utilities.json_or_none(input_payload), 
                                            Utilities.json_or_none(output_payload), status, execution_duration), fetch=False)

    def save_agent_session( self, agent_state: AgentState, conversation_name: str = '') -> None:
        query = """
            INSERT INTO supplychain_assist.chat_session (context_id, conversation_name, user_id, 
                agent_name, conversation, current_state, started_at, ended_at )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, now(), now())
            ON CONFLICT (context_id, user_id, agent_name)
            DO UPDATE SET
                conversation = EXCLUDED.conversation,
                current_state = EXCLUDED.current_state,
                ended_at = now()
        """
        self.db.execute_query(
            query,
            params=( self.conversation_id, conversation_name, self.user_id, self.agent_name,
                Utilities.json_or_none(agent_state.conversation), Utilities.json_or_none(agent_state.current_state)),
            fetch=False
        )

    def load_agent_session(self, agent_state: AgentState) -> AgentState:
        query = """
            SELECT context_id, conversation_name, user_id, agent_name, conversation, current_state, started_at, ended_at
            FROM supplychain_assist.chat_session
            WHERE context_id = %s AND agent_name = %s
        """
        rows = self.db.execute_query(
            query,
            params=(self.conversation_id, self.agent_name),
            fetch=True
        )
        if not rows:
            agent_state.is_new_conversation = True
            return agent_state
        else:
            row = rows[0]
            agent_state.conversation = row[4] if row[4] else []
            agent_state.current_state = row[5] if row[5] else {}
            agent_state.is_new_conversation = False
            return agent_state
