import os
import unittest
from unittest.mock import patch
import asyncio
import threading
import time
from uuid import uuid4
import httpx
import uvicorn


from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.client import A2AClient
from a2a.client.card_resolver import A2ACardResolver
from a2a.types import JSONRPCErrorResponse, Message, MessageSendParams, SendMessageRequest, DataPart

from app.utils.agent_message import AgentInputMessage, AgentOutputMessage


def lazy_import(module_name):
    import importlib
    return importlib.import_module(module_name)

class A2AIntegrationTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = os.environ.get('ENV')
        if cls.env != 'local':
            print("Skipping setup as ENV is not 'local'")
            return  # Exit early if ENV is not 'local'
        
        global TestUtils, logger, WorkflowAgentExecutor, SETTINGS
        TestUtils=lazy_import('app.utils.test_utils').TestUtils
        
        cls.agent_name = os.environ.get('APP_NAME','')
        cls.aws_region = os.environ.get('AWS_REGION', 'us-west-2')
        cls.db_port_forward_proc = TestUtils.start_port_forwarding('cubeassist-cubeassistdb-dev-usw2-aurora-postgres.cluster-cv42o40koqas.us-west-2.rds.amazonaws.com', 5432, 8888, cls.aws_region)
        cls.mcp_port_forward_proc = TestUtils.start_port_forwarding('cubeassist-mcp.assist.one.cubedev.toyota.com', 8080, 8081,cls.aws_region)

        SETTINGS=lazy_import('app.utils.settings').SETTINGS
        logger = lazy_import('app.utils.logging').logger
        WorkflowAgentExecutor=lazy_import('app.a2a.server').WorkflowAgentExecutor
        
        cls.agent_local_url = "http://localhost:8080"
        cls.agent_remote_url = "http://localhost:8080"
        SETTINGS.cubeassist_mcp_server_url = 'http://localhost:8081/mcp'
        cls.token = os.environ.get('USER_TOKEN') 

    @classmethod
    def tearDownClass(cls):
        """
        Clean up all port forwarding processes.
        """
        processes_to_terminate = [
            'db_port_forward_proc',
            'mcp_port_forward_proc', 
            'pipeline_agent_port_forward_proc',
            'nso_agent_port_forward_proc',
            'vdm_agent_port_forward_proc',
            'agent_port_forward_proc'  # Added for remote agent port forwarding
        ]
        
        for proc_name in processes_to_terminate:
            if hasattr(cls, proc_name):
                try:
                    proc = getattr(cls, proc_name)
                    if proc:
                        proc.terminate()
                        logger.info(f"Terminated {proc_name}")
                except Exception as e:
                    logger.warning(f"Error terminating {proc_name}: {e}")
        
        # Clean up server thread
        if hasattr(cls, 'server_thread'):
            try:
                cls.server_thread.join(timeout=3)
                logger.info("Server thread joined")
            except Exception as e:
                logger.warning(f"Error joining server thread: {e}")

    @classmethod
    def start_local_server(cls):
        def run():
            with patch('app.utils.agent_registry.AgentRegistry.get_url', return_value="http://localhost:8080"):
                executor = WorkflowAgentExecutor(cls.agent_name)
                request_handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
                server_app = A2AStarletteApplication(agent_card=executor.public_agent_card, http_handler=request_handler)
                app = server_app.build()
                config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, log_level="info", loop="asyncio")
                server = uvicorn.Server(config)
                cls.uvicorn_server = server
                server.run()

        cls.server_thread = threading.Thread(target=run, daemon=True)
        cls.server_thread.start()
        time.sleep(10)

    @unittest.skipIf(os.environ.get("ENV") != "local", "Skipping test in not in local environment")    
    async def test_workflow_agent(self):
        """
        Test remote workflow agent functionality with multi-turn workflow execution.
        """

        self.start_local_server()

        
        headers = {"Authorization": f"Bearer {self.token}"}
        timeout = httpx.Timeout(16000.0, connect=10.0)
        
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as httpx_client:
            # Resolve agent card for remote agent
            resolver = A2ACardResolver(httpx_client, self.agent_remote_url)
            agent_card = await resolver.get_agent_card()
            
            # Override URL if needed for testing environment
            if agent_card.url.lower() != self.agent_remote_url.lower():
                agent_card.url = self.agent_remote_url
                
            client = A2AClient(httpx_client, agent_card)
            
            context_id = uuid4().hex
            task_id = uuid4().hex
            is_new_conversation = True
            
            for input in self.get_multi_turn_workflow_test_cases():

                agent_input = AgentInputMessage()
                agent_input.is_new_conversation = is_new_conversation
                agent_input.token = self.token
                agent_input.task_id = task_id
                agent_input.context_id = context_id
                agent_input.workflow_id = "SOLD_ORDER_VEHICLE_SWAP"

                if (type(input) == dict):
                    agent_input.input_data = input
                else:
                    agent_input.input = input

                

                message = Message(
                    role="user", 
                    parts=[DataPart(kind="data", data=agent_input.model_dump(), metadata={})], 
                    messageId=uuid4().hex
                )
                
                    
                request = SendMessageRequest(
                    id=str(uuid4()), 
                    params=MessageSendParams(message=message)
                )
                
                logger.info(f"Sending remote workflow message: {input}")
                print(request.model_dump_json(indent=2))
                
                try:
                    resp = await client.send_message(request)
                    
                    # Handle workflow state transitions
                    if hasattr(resp.root, 'result') and resp.root.result:
                        result = resp.root.result.parts[0].root.data
                        agent_output = AgentOutputMessage(**result)
                        
                        # Update context and task IDs based on response state
                        if agent_output.task_state == 'input-required':
                            logger.info(f"Workflow requires input - task_id: {agent_input.task_id}, context_id: {agent_input.context_id}")
                        else:
                            # Reset task_id for new workflow but keep context for conversation continuity
                            task_id= uuid4().hex
                            logger.info(f"Workflow completed - context_id: {agent_input.context_id}")
                    
                    # Handle error responses
                    if isinstance(resp.root, JSONRPCErrorResponse):
                        error_data = resp.root.error.model_dump(exclude_none=True)
                        logger.error(f"Error response from remote workflow agent: {error_data}")
                    else:
                        msg = resp.root.result
                        logger.info(f"Remote workflow response: {msg}")
                        
                except Exception as e:
                    logger.error(f"Error sending message to remote workflow agent: {e}", exc_info=True)
                    # Continue with next test case instead of failing completely
                    continue

    def get_multi_turn_workflow_test_cases(self):
        return [
            "SOLD_ORDER_VEHICLE_SWAP",
            #{"recomendation_selected": "Go to Previous Step"},
            {"selected_region":"Central Area"},
            #{"recomendation_selected": "Go to Previous Step"},
            "SO2025000016097",
            "4T1DAACK0TU239008",
            #"SOLD_ORDER_VEHICLE_SWAP",
            #"San Francisco Region",
            #"SO2025100973690",

            # "SOLD_ORDER_VEHICLE_SWAP",
            # "San Francisco Region",
            # "SO2025100973690",
            # "4T1DAACK0TU239005",
        ]