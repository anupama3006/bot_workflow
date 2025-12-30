import functools
from typing import Optional, List, Dict, Any,Tuple
from app.utils.agent_message import AgentInputMessage, AgentOutputMessage
from app.utils.logging import logger
from a2a.types import TaskState
import json
import asyncio
from typing import Optional, List, Dict, Any,Tuple
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from app.agent.wokflow_state import WorkflowState
from app.agent.workflow_executor import WorkflowExecutor
from app.utils.workflow_service import WorkflowService
from app.utils.settings import SETTINGS


class WorkflowManager:
    """
    Manager for workflow operations - retrieve, create, update workflows.
    Orchestrates workflow execution and delegates data operations to service layer.
    """

    def __init__(self):
        self.workflow_service = WorkflowService()
        self.workflow_executor = WorkflowExecutor()

    @staticmethod
    async def get_user_info(token: str) -> Tuple[str, List[str]]:
        """Retrieve user ID and roles from token via MCP call."""
        async with asyncio.timeout(100):
            async with streamablehttp_client(SETTINGS.cubeassist_mcp_server_url) as (read, write, _):
                async with ClientSession(read, write) as mcp_session:
                    await mcp_session.initialize()
                    result = await mcp_session.call_tool(
                        "get_user_info",
                        {"token": token}
                    )
                    user_info = json.loads(result.content[0].text)
                    user_id = user_info.get("output", {}).get("data", {}).get("userId")
                    user_roles = user_info.get("output", {}).get("data", {}).get("roles", [])
                    return user_id, user_roles

    @functools.lru_cache(maxsize=32)
    def get_steps_by_workflow_id(self, workflow_id: str, user_roles: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
        """
        Retrieve workflow details along with its steps by workflow_id from database.
        Joins workflows and steps tables, including USER_INPUT and SYSTEM_ACTION step details.
        
        Args:
            workflow_id: Unique workflow identifier (required)
            user_roles: User role to check access permissions (required)
            
        Returns:
            Dictionary containing workflow details and list of steps if found and accessible, None otherwise
            
        Raises:
            ValueError: If workflow_id or user_roles is not provided
        """
        return self.workflow_service.get_steps_by_workflow_id(workflow_id, user_roles)

    @functools.lru_cache(maxsize=16)
    def get_all_workflows(self, user_roles: Tuple[str, ...]) -> List[Dict[str, Any]]:
        """
        Retrieve all workflows accessible by the given user role.
        
        Args:
            user_roles: User role to check access permissions (required)
            
        Returns:
            List of dictionaries containing workflow details accessible to the user role
            
        Raises:
            ValueError: If user_roles is not provided
        """
        return self.workflow_service.get_all_workflows(user_roles)

    async def process_workflow(
        self,
        agent_input: AgentInputMessage
    ) -> AgentOutputMessage:
        try:
            user_id,user_roles = await WorkflowManager.get_user_info(agent_input.token)
            workflow_run_id=agent_input.task_id
            workflow_id=agent_input.workflow_id
            start_step_id = None
            step_run_id = None
            workflow_state_data = {}
            is_new_conversation = True


            input_required_data = self.get_input_required_step(workflow_run_id=workflow_run_id)
            if input_required_data:
                start_step_id = input_required_data["step_id"]
                workflow_id = input_required_data["workflow_id"]
                step_run_id = input_required_data["step_run_id"]
                workflow_state_data = input_required_data["workflow_state"]
                is_new_conversation = False
                    
            # Get workflow with steps
            workflow = self.get_steps_by_workflow_id(workflow_id, tuple(user_roles))
            
            if not workflow:
                raise ValueError(f"Workflow '{workflow_id}' not found or access denied for roles '{user_roles}'")
            
            # Extract step information
            steps = workflow.get("steps", [])
            step_ids = [step.get("step_id") for step in steps]
            next_step_ids = [step.get("next_step_id") for step in steps if step.get("next_step_id") is not None]
            
            if start_step_id is None:
                for step_id in step_ids:
                    if step_id not in next_step_ids:
                        start_step_id = step_id
                        break
            
            logger.info(f"Workflow '{workflow['name']}' - Step IDs: {step_ids}")
            logger.info(f"Workflow '{workflow['name']}' - Starting Step: {start_step_id}")
            
            if not workflow_state_data.get("workflow_name"):
                workflow_state_data["workflow_name"] = workflow.get("name")
                workflow_state_data["workflow_id"] = workflow_id

            # Initialize workflow state with full step information
            workflow_state = WorkflowState(
                workflow_id=workflow_id,
                workflow_run_id=workflow_run_id,
                workflow_name=workflow.get("name"),
                worflow_exit_keywords=workflow.get("workflow_exit_keywords", []),
                input=agent_input.input,
                input_data=agent_input.input_data or {},
                workflow_state=workflow_state_data,
                task_state=TaskState.working.value,
                output={},
                current_step_run_id=step_run_id,
                step_ids=step_ids,
                next_step_ids=next_step_ids,
                start_step_id=start_step_id,
                steps=steps,
                is_new_conversation=is_new_conversation,
                token=agent_input.token,
                user_id=user_id,
                user_roles=user_roles
            )

            # Build graph using workflow executor
            self.workflow_executor.graph = self.workflow_executor.build_graph(workflow_state)
            
            # Execute workflow
            workflow_state = await self.workflow_executor.execute(workflow_state=workflow_state)
            agent_output = AgentOutputMessage()
            agent_output.output = workflow_state["output"]
            agent_output.task_state = workflow_state["task_state"]
            agent_output.status = workflow_state["status"]
            agent_output.event_log = workflow_state["event_log"]
            agent_output.workflow_id = workflow_state["workflow_id"]
            agent_output.workflow_name = workflow_state["workflow_name"]
            
            return agent_output
            
        except ValueError as e:
            logger.error(f"Invalid workflow request: {e}")
            raise
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            raise

    def get_input_required_step(self, workflow_run_id: str) -> Optional[Dict[str, str]]:
        """
        Get the workflow_id, step_id, step_run_id, and workflow_state that requires input for the given workflow run.
        Returns data from the latest input-required record.
        
        Args:
            workflow_run_id: Workflow run ID to query
            
        Returns:
            Dictionary with workflow_id, step_id, step_run_id, and workflow_state that requires input, 
            or None if no input-required step found
            
        Raises:
            Exception: If database query fails
        """
        return self.workflow_service.get_input_required_step(workflow_run_id)