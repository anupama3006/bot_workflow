from pydantic import BaseModel, Field
from typing import Optional,Tuple


class AgentInputMessage(BaseModel):
    """Pydantic object for agent input message data"""
    timestamp: Optional[float] = Field(None, description="Message timestamp")
    context_id: Optional[str] = Field(None, description="Context ID for conversation continuity")
    task_id: Optional[str] = Field(None, description="Task ID for workflow state management")
    is_new_conversation: Optional[bool] = Field(None, description="Whether this is a new conversation")
    user_id: Optional[str] = Field(None, description="User identifier")
    input: Optional[str] = Field(None, description="User input message")
    input_data: Optional[dict] = Field(None, description="Structured input data for the agent")
    workflow_id: Optional[str] = Field(None, description="Workflow identifier")
    token: Optional[str] = Field(None, description="Authentication token")
    user_roles: Optional[Tuple[str, ...]] = Field(None, description="User roles for access control")


class AgentOutputMessage(BaseModel):
    """Pydantic object for agent output message data"""
    workflow_id: Optional[str] = Field(None, description="Workflow identifier")
    workflow_name: Optional[str] = Field(None, description="Workflow name")
    output: Optional[dict] = Field(None, description="Agent output data")
    task_state: Optional[str] = Field(None, description="A2A task state")
    status: Optional[str] = Field(None, description="Workflow status")
    event_log: Optional[list] = Field(None, description="Event log for the workflow execution")