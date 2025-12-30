from pydantic import BaseModel
from typing import Dict, Any, List, Literal, Optional
from a2a.types import TaskState

class ValidationRuleItem(BaseModel):
    """Individual validation rule item."""
    rule_type: Literal["present_in_list", "regex"]
    list_name: Optional[str] = None
    field_to_validate: str
    validation_message: Dict[str, Any]
    regex: Optional[str] = None
    result_task_state: TaskState

class ValidationRule(BaseModel):
    """Validation rule model as a list of validation rule items."""
    rules: List[ValidationRuleItem]



