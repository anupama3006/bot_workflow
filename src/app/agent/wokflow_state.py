from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from a2a.types import Message, TaskState
from app.agent.state import CubeAssistBaseState


@dataclass
class WorkflowState(CubeAssistBaseState):
    """State for workflow execution"""
    workflow_id: str = None
    workflow_run_id: str = None
    workflow_name: Optional[str] = None
    worflow_exit_keywords: Optional[List[str]] = None
    current_step_run_id: Optional[str] = None
    go_to_step_id: Optional[str] = None
    workflow_state: Dict[str, Any] = field(default_factory=dict)
    task_state: TaskState = TaskState.working.value
    output: Dict[str, Any] = field(default_factory=dict)
    step_ids: List[str] = field(default_factory=list)
    next_step_ids: List[str] = field(default_factory=list)
    start_step_id: Optional[str] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)
    run_id: Optional[str] = None
    user_id: str = None
    user_roles: Tuple[str, ...] = field(default_factory=tuple)