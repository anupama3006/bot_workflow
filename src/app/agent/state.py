import json
import time
from asyncio import Task
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from a2a.server.events import EventQueue
from a2a.types import Message, TaskState

from app.utils.settings import SETTINGS


@dataclass
class CubeAssistBaseState:
    """Base class containing core conversation fields"""
    input: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = field(default_factory=dict)
    output: Optional[str] = None
    token: Optional[str] = None
    event_log: Optional[List[str]] = field(default_factory=list)
    context_id: Optional[str] = None
    is_new_conversation: bool = True
    status: str = "in_progress"


@dataclass
class WorkflowState(CubeAssistBaseState):
    """State for workflow execution"""
    workflow_id: str = None
    workflow_run_id: str = None
    workflow_name: Optional[str] = None
    worflow_exit_keywords: Optional[List[str]] = None
    current_step_run_id: Optional[str] = None
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


@dataclass
class AgentState(CubeAssistBaseState):
    """Agent state extending CubeAssist base state"""
    # for agent workflow state
    messages: List[Dict[str, Any]] = field(default_factory=list)
    available_tools: Optional[List[Dict[str, Any]]] = None
    agent_tools: Optional[List[str]] = None
    selected_tool: Optional[str] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    step: int = 0
    seen_decisions: Optional[Any] = None
    filter: Optional[Dict[str, Any]] = None
    agent_name: Optional[str] = None
    
    # for agent context
    task_id: Optional[str] = None
    task: Optional[Task] = None
    event_queue: EventQueue = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    call_back_function: Optional[Callable] = None
    conversation: Optional[list] = None
    current_state: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default mutable values"""
        if self.event_log is None:
            self.event_log = []

    def mark_end(self):
        self.end_time = time.time()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def get_initial_state():
        return AgentState(
            messages=[],
            input=None,
            output=json.dumps({}),
            event_log=[],
            available_tools=[],
            agent_tools=[],
            selected_tool=None,
            results=[],
            token="",
            step=0,
            seen_decisions=set(),
            status="in_progress",
            agent_name=SETTINGS.app_name,
            context_id=None,
            is_new_conversation=True,
            conversation=[],
            current_state={},
            start_time=time.time()
        )
