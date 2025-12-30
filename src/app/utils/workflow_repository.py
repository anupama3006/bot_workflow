from typing import Optional, List, Dict, Any, Tuple
import json
from app.utils.logging import logger
from app.utils.postgress import Postgress
from a2a.types import TaskState


class WorkflowRepository:
    """
    Data Access Object for workflow-related database operations.
    Handles all SQL queries and database interactions for workflows and steps.
    """

    def __init__(self):
        self.db = Postgress()

    def get_workflow_with_steps(self, workflow_id: str, user_roles: List[str]) -> Optional[List[Tuple]]:
        """
        Retrieve workflow details along with its steps by workflow_id from database.
        Joins workflows and steps tables, including USER_INPUT and SYSTEM_ACTION step details.
        
        Args:
            workflow_id: Unique workflow identifier
            user_roles: User role to check access permissions
            
        Returns:
            Raw database result rows or None if not found/accessible
        """
        placeholders = ','.join(['%s'] * len(user_roles))
        query = f"""
        SELECT 
            w.workflow_id, 
            w.name, 
            w.description, 
            w.access_roles,
            w.is_enabled,
            w.workflow_exit_keywords,
            w.created_at AS workflow_created_at, 
            w.created_by AS workflow_created_by, 
            w.updated_at AS workflow_updated_at, 
            w.updated_by AS workflow_updated_by,
            s.step_id,
            s.type,
            s.task_description,
            s.next_step_id,
            s.created_at AS step_created_at,
            s.created_by AS step_created_by,
            s.updated_at AS step_updated_at,
            s.updated_by AS step_updated_by,
            ui.user_message,
            ui.expected_data_key,
            ui.orchestration_rules,
            sa.name AS action_name,
            sa.inputs AS action_inputs,
            sa.output_mapping,
            sa.success_mapping,
            sa.error_mapping,
            sa.type AS action_type
        FROM workflows w
        LEFT JOIN steps s ON w.workflow_id = s.workflow_id
        LEFT JOIN step_user_interaction ui ON ui.step_id = s.step_id 
            AND ui.workflow_id = s.workflow_id 
            AND s.type IN ('USER_INPUT','FINAL_RESPONSE')
        LEFT JOIN step_system_action sa ON sa.step_id = s.step_id 
            AND sa.workflow_id = s.workflow_id 
            AND s.type = 'SYSTEM_ACTION'
        WHERE w.workflow_id = %s
        AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(access_roles[1]::jsonb) AS role
            WHERE role.value in ({placeholders})
        )
        AND w.is_enabled = TRUE
        ORDER BY s.step_id
        """
        
        params = (workflow_id, *user_roles)
        
        try:
            result = self.db.execute_query(query, params, fetch=True)
            
            if not result or len(result) == 0:
                logger.warning(f"Workflow '{workflow_id}' not found or user roles '{user_roles}' do not have access")
                return None
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to get workflow by ID '{workflow_id}': {e}", exc_info=True)
            raise

    def get_all_workflows_for_role(self, user_roles: List[str]) -> List[Tuple]:
        """
        Retrieve all workflows accessible by the given user role.
        
        Args:
            user_roles: User role to check access permissions
            
        Returns:
            List of database result rows for workflows accessible to the user role
        """
        placeholders = ','.join(['%s'] * len(user_roles))
        query = f"""
        SELECT 
            w.workflow_id, 
            w.name, 
            w.description, 
            w.access_roles,
            w.is_enabled,
            w.workflow_exit_keywords,
            w.created_at, 
            w.created_by, 
            w.updated_at, 
            w.updated_by,
            COUNT(s.step_id) as step_count
        FROM workflows w
        LEFT JOIN steps s ON w.workflow_id = s.workflow_id
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text(access_roles[1]::jsonb) AS role
            WHERE role.value  IN ({placeholders})

        )
        AND w.is_enabled = TRUE
        GROUP BY w.workflow_id, w.name, w.description, w.access_roles, w.is_enabled, w.workflow_exit_keywords,
                 w.created_at, w.created_by, w.updated_at, w.updated_by
        ORDER BY w.name
        """
        
        params = (*user_roles,)
        
        try:
            result = self.db.execute_query(query, params, fetch=True)
            
            if not result or len(result) == 0:
                logger.info(f"No workflows found for user roles '{user_roles}'")
                return []
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to get workflows for roles '{user_roles}': {e}", exc_info=True)
            raise

    def get_input_required_workflow_run(self, workflow_run_id: str) -> Optional[Tuple]:
        """
        Get the workflow_id, step_id, step_run_id, and workflow_state that requires input 
        for the given workflow run. Returns data from the latest input-required record.
        
        Args:
            workflow_run_id: Workflow run ID to query
            
        Returns:
            Database result tuple with workflow_id, step_id, step_run_id, and workflow_state 
            that requires input, or None if no input-required step found
        """
        query = """
        SELECT workflow_id, step_id, step_run_id, workflow_state
        FROM workflow_run 
        WHERE workflow_run_id = %s 
        AND status = %s
        ORDER BY created_at DESC
        LIMIT 1
        """
        
        params = (workflow_run_id, TaskState.input_required.value)
        
        try:
            results = self.db.execute_query(query, params, fetch=True)
            
            if results:
                logger.info(f"Found input-required step for workflow_run_id: {workflow_run_id}")
                return results[0]
            else:
                logger.info(f"No input-required step found for workflow_run_id: {workflow_run_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get input-required step for workflow_run_id '{workflow_run_id}': {e}", exc_info=True)
            raise