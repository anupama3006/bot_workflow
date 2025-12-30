

from app.agent.workflow_manager import WorkflowManager
from app.utils.agent_message import AgentInputMessage, AgentOutputMessage
from app.utils.decorators import timed


@timed("Pipeline Agent Worflow")
async def main(agent_input: AgentInputMessage) -> AgentOutputMessage:
    workflow_manager = WorkflowManager()
    agent_output=await workflow_manager.process_workflow(
                    agent_input=agent_input
                )
    return agent_output
