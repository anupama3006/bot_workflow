import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, Message, Role, Part, DataPart
from starlette.middleware.cors import CORSMiddleware
from uuid import uuid4
from app.agent.run import main
from app.utils.logging import logger
from app.utils.settings import SETTINGS
from app.agent.workflow_manager import WorkflowManager
from app.utils.agent_message import AgentInputMessage

class WorkflowAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent_name = 'workflow_agent'
        
        self.public_agent_card = AgentCard(
            name='Workflow Agent',
            description='An agent that executes workflow tasks and returns structured results',
            url='http://localhost:8080',
            version='1.0.0',
            default_input_modes=['data'],
            default_output_modes=['data'],
            capabilities=AgentCapabilities(streaming=True),
            skills=[],
            supports_authenticated_extended_card=False,
        )
        self.workflow_manager = WorkflowManager()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            method = context.call_context.state.get("method").strip()
            logger.info(f"Received request with context_id: {context.context_id}, task_id: {context.task_id}, method: {method}")
            
            # Extract data from the message parts and populate AgentInputMessage
            if context.message and context.message.parts and len(context.message.parts) > 0:
                message_data = context.message.parts[0].root.data
                
                # Create AgentInputMessage from the extracted data
                agent_input = AgentInputMessage(**message_data)
                

                agent_output = await main(agent_input=agent_input)
                metadata = {}
                metadata[self.agent_name]  = {
                    "event_log": agent_output.event_log,
                    "workflow_id": agent_input.workflow_id,
                    "workflow_name": agent_output.workflow_name
                }
                
                part = Part(root=DataPart(kind="data", data=agent_output.model_dump(), metadata=metadata))
                message = Message( role=Role.agent,
                    message_id=str(uuid4()),
                    task_id=agent_input.task_id,
                    context_id=agent_input.context_id,
                    parts = [part]
                )

                await event_queue.enqueue_event(message)
                
            else:
                raise Exception("No message parts found in context")

        except Exception as e:
            logger.error(f'Unexpected error: {e}', exc_info=True)
            raise e


    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ValueError('cancel not supported')

    

if __name__ == '__main__':
    agent_name = SETTINGS.app_name
    
    agent_executor = WorkflowAgentExecutor(agent_name)
    request_handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=InMemoryTaskStore())
    server_app = A2AStarletteApplication(agent_card=agent_executor.public_agent_card, http_handler=request_handler)
    app = server_app.build()
    app.add_middleware( CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    uvicorn.run(app, host='0.0.0.0', port=8080)
