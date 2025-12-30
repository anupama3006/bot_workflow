from typing import Optional, List, Dict, Any
import functools
import json
from functools import partial
from langgraph.graph import StateGraph, START, END
from app.utils.logging import logger
from app.utils.workflow_repository import WorkflowRepository
from a2a.types import TaskState


class WorkflowService:
    """
    Service layer for workflow operations.
    Handles business logic and data transformation between repository and manager layers.
    """

    def __init__(self):
        self.repository = WorkflowRepository()

    @functools.lru_cache(maxsize=32)
    def get_steps_by_workflow_id(self, workflow_id: str, user_roles: tuple[str, ...]) -> Optional[Dict[str, Any]]:
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
        if not workflow_id:
            raise ValueError("workflow_id is required")
        if not user_roles:
            raise ValueError("user_roles is required")

        # Get raw data from repository
        result = self.repository.get_workflow_with_steps(workflow_id, user_roles)
        
        if not result:
            return None

        # Parse access_roles from first row (index 3)
        access_roles_raw = result[0][3]
        access_roles = []
        
        if access_roles_raw:
            try:
                if isinstance(access_roles_raw, str):
                    cleaned = access_roles_raw.strip('{}').strip('"')
                    access_roles = json.loads(cleaned)
                elif isinstance(access_roles_raw, list):
                    access_roles = access_roles_raw
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse access_roles for workflow {workflow_id}: {e}")
                access_roles = []
        
        # Build workflow dictionary with new fields
        workflow = {
            "workflow_id": result[0][0],
            "name": result[0][1],
            "description": result[0][2],
            "access_roles": access_roles,
            "is_enabled": result[0][4],  # New field
            "workflow_exit_keywords": result[0][5],  # New field
            "created_at": result[0][6].isoformat() if result[0][6] else None,  # Updated index
            "created_by": result[0][7] if result[0][7] else None,  # Updated index
            "updated_at": result[0][8].isoformat() if result[0][8] else None,  # Updated index
            "updated_by": result[0][9] if result[0][9] else None,  # Updated index
            "steps": []
        }
        
        # Parse steps from result rows - updated indices due to new columns
        for row in result:
            # Skip if no step (LEFT JOIN returned NULL) - index shifted to 10
            if row[10] is None:
                continue
                
            step = {
                "step_id": row[10],  # Updated index
                "type": row[11],     # Updated index
                "task_description": row[12],  # Updated index
                "next_step_id": row[13],      # Updated index (removed failure_message)
                "created_at": row[14].isoformat() if row[14] else None,  # Updated index
                "created_by": row[15] if row[15] else None,  # Updated index
                "updated_at": row[16].isoformat() if row[16] else None,  # Updated index
                "updated_by": row[17] if row[17] else None   # Updated index
            }
            
            # Add USER_INPUT specific details if available - updated indices
            if row[11] in ('USER_INPUT', 'FINAL_RESPONSE') and row[18] is not None:
                step["user_interaction"] = {
                    "user_message": row[18],        # ui.user_message
                    "expected_data_key": row[19],   # ui.expected_data_key
                    "orchestration_rules": row[20]  # ui.orchestration_rules (changed from validation_rules)
                }
            
            # Add SYSTEM_ACTION specific details if available - updated indices
            if row[11] == 'SYSTEM_ACTION' and row[21] is not None:  # Updated index
                step["system_action_details"] = {
                    "name": row[21],                    # sa.name (updated index)
                    "inputs": row[22],                  # sa.inputs (updated index)
                    "output_mapping": row[23],          # sa.output_mapping (updated index)
                    "success_mapping": row[24],         # sa.success_mapping (updated index)
                    "error_mapping": row[25],           # sa.error_mapping (updated index)
                    "action_type": row[26]              # sa.type (updated index)
                }
            
            workflow["steps"].append(step)
        
        logger.info(f"Retrieved workflow: {workflow['name']} with {len(workflow['steps'])} steps for roles '{user_roles}'")
        return workflow

    @functools.lru_cache(maxsize=32)
    def get_all_workflows(self, user_roles: tuple) -> List[Dict[str, Any]]:
        """
        Retrieve all workflows accessible by any of the given user roles.
        
        Args:
            user_roles: Tuple of user roles to check access permissions (required)
                       Examples: ("CUBE_E2E_ADMIN",) or ("CUBE_E2E_ADMIN", "InventoryManager")
        
        Returns:
            List of dictionaries containing workflow details accessible to any of the user roles
        
        Raises:
            ValueError: If user_roles is not provided or empty
        """
        if not user_roles or not isinstance(user_roles, tuple):
            raise ValueError("user_roles must be a non-empty tuple")

        workflows = []
        seen_workflow_ids = set()  # Prevent duplicates across roles
        
        # Loop through each role and get workflows for that role
        for user_role in user_roles:
            try:
                # Get raw data from repository for each role
                result = self.repository.get_all_workflows_for_role(user_role)
                
                if not result:
                    logger.info(f"No workflows found for user role '{user_role}'")
                    continue
                
                for row in result:
                    # Skip duplicates (workflow already added by previous role)
                    if row[0] in seen_workflow_ids:
                        continue
                    seen_workflow_ids.add(row[0])
                    
                    # Parse access_roles (index 3)
                    access_roles_raw = row[3]
                    access_roles = []
                    
                    if access_roles_raw:
                        try:
                            if isinstance(access_roles_raw, str):
                                cleaned = access_roles_raw.strip('{}').strip('"')
                                access_roles = json.loads(cleaned)
                            elif isinstance(access_roles_raw, list):
                                access_roles = access_roles_raw
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.warning(f"Failed to parse access_roles for workflow {row[0]}: {e}")
                            access_roles = []
                    
                    workflow = {
                        "workflow_id": row[0],
                        "name": row[1],
                        "description": row[2],
                        "access_roles": access_roles,
                        "is_enabled": row[4],  # New field
                        "workflow_exit_keywords": row[5],  # New field
                        "created_at": row[6].isoformat() if row[6] else None,  # Updated index
                        "created_by": row[7] if row[7] else None,  # Updated index
                        "updated_at": row[8].isoformat() if row[8] else None,  # Updated index
                        "updated_by": row[9] if row[9] else None,  # Updated index
                        "step_count": row[10] if row[10] else 0  # Updated index
                    }
                    
                    workflows.append(workflow)
                    
            except Exception as e:
                logger.error(f"Error getting workflows for roles '{user_roles}': {e}")
                # Continue with other roles even if one fails
                continue
        
        logger.info(f"Retrieved {len(workflows)} unique workflows across roles {user_roles}")
        return workflows

    def get_input_required_step(self, workflow_run_id: str) -> Optional[Dict[str, Any]]:
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
        # Get raw data from repository
        results = self.repository.get_input_required_workflow_run(workflow_run_id)
        
        if not results:
            return None

        workflow_id = results[0]
        step_id = results[1]
        step_run_id = results[2]
        workflow_state_raw = results[3]
        
        # JSONB field returns as dict already - no JSON parsing needed
        workflow_state = workflow_state_raw if workflow_state_raw else {}
        
        logger.info(f"Found input-required step: {step_id} in workflow: {workflow_id} (step_run_id: {step_run_id}) for workflow_run_id: {workflow_run_id}")
        return {
            "workflow_id": workflow_id,
            "step_id": step_id,
            "step_run_id": step_run_id,
            "workflow_state": workflow_state
        }