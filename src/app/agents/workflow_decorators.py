import uuid
import json
from datetime import datetime
from functools import wraps
from typing import Dict, Any, Optional, Callable
from app.utils.logging import logger
from app.utils.postgress import Postgress
from app.agent.wokflow_state import WorkflowState
from a2a.types import TaskState


def process_workflow_run(db: Optional[Postgress] = None):
    """
    Decorator to persist workflow step execution to workflow_run table using upsert.
    
    Args:
        db: Optional Postgress instance, creates new if not provided
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, step_detail: Dict[str, Any], workflow_state: WorkflowState) -> WorkflowState:
            # Initialize database connection if not provided
            if db is None:
                database = Postgress()
            else:
                database = db
            
            # Extract step and workflow information from WorkflowState fields
            step_id = step_detail.get("step_id")
            workflow_id = workflow_state.workflow_id
            workflow_run_id = workflow_state.workflow_run_id
            

            # Generate step_run_id for this execution
            if not workflow_state.current_step_run_id:
                workflow_state.current_step_run_id = str(uuid.uuid4())
            
            started_at = datetime.now()
            
            # Initial upsert with RUNNING status - removed schema reference
            initial_upsert_query = """
            INSERT INTO workflow_run (
                workflow_run_id, step_run_id, workflow_id, step_id, 
                started_at, status, workflow_state, 
                created_at, created_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (step_run_id) 
            DO UPDATE SET
                started_at = EXCLUDED.started_at,
                status = EXCLUDED.status,
                workflow_state = EXCLUDED.workflow_state,
                updated_at = EXCLUDED.created_at,
                updated_by = EXCLUDED.created_by
            """
            
            # Prepare initial workflow state (before step execution) - only workflow_state data
            initial_workflow_state = workflow_state.workflow_state
            
            initial_params = (
                workflow_run_id,
                workflow_state.current_step_run_id,
                workflow_id,
                step_id,
                started_at,
                TaskState.working.value,  # 'working'
                json.dumps(initial_workflow_state),
                started_at,
                "system"
            )
            
            try:
                # Insert/update initial record
                database.execute_query(initial_upsert_query, initial_params, fetch=False)
                logger.info(f"Created/updated workflow run record - Workflow: {workflow_run_id}, Step: {workflow_state.current_step_run_id}")
                
                # Execute the original function
                result_state = await func(self, step_detail, workflow_state)

                
                # Prepare final workflow state (after step execution) - only workflow_state data
                final_workflow_state = result_state.workflow_state
                
                # Determine execution status using TaskState enum values
                status = TaskState.completed.value  # 'completed' - default to completed
                success_response = None
                error_response = None
                
                # Check if step failed
                if hasattr(result_state, 'task_state') and result_state.task_state == TaskState.failed.value:
                    status = TaskState.failed.value  # 'failed'
                    error_response = {
                        "error": result_state.output,  
                        "step_id": step_id,
                        "workflow_run_id": workflow_run_id,
                        "step_run_id": workflow_state.current_step_run_id
                    }
                    final_workflow_state["execution_phase"] = "FAILED"
                elif hasattr(result_state, 'task_state') and result_state.task_state == TaskState.canceled.value:
                    status = TaskState.canceled.value  # 'canceled'
                    success_response = {
                        "success": True,
                        "step_completed": step_id,
                        "workflow_run_id": workflow_run_id,
                        "step_run_id": workflow_state.current_step_run_id,
                        "step_output": result_state.output,
                        "status": "canceled"
                    }
                    final_workflow_state["execution_phase"] = "CANCELED"
                elif hasattr(result_state, 'task_state') and result_state.task_state == TaskState.working.value:
                    status = TaskState.working.value  # 'working'
                    success_response = {
                        "success": True,
                        "step_completed": step_id,
                        "next_step": step_detail.get("next_step_id"),
                        "workflow_run_id": workflow_run_id,
                        "step_run_id": workflow_state.current_step_run_id,
                        "step_output": result_state.output,  
                        "status": "working"  # Still in progress
                    }
                elif hasattr(result_state, 'task_state') and result_state.task_state == TaskState.input_required:
                    status = TaskState.input_required.value  # 'input-required'
                    success_response = {
                        "success": True,
                        "step_completed": step_id,
                        "next_step": step_detail.get("next_step_id"),
                        "workflow_run_id": workflow_run_id,
                        "step_run_id": workflow_state.current_step_run_id,
                        "step_output": result_state.output,  
                        "status": "input-required"  # Waiting for user input
                    }
                else:
                    # Step completed successfully
                    status = TaskState.completed.value  # 'completed'
                    success_response = {
                        "success": True,
                        "step_completed": step_id,
                        "next_step": step_detail.get("next_step_id"),
                        "workflow_run_id": workflow_run_id,
                        "step_run_id": workflow_state.current_step_run_id,
                        "step_output": result_state.output,  
                        "status": "completed"
                    }
                
                # Final upsert with completion details - removed schema reference
                completion_upsert_query = """
                INSERT INTO workflow_run (
                    workflow_run_id, step_run_id, workflow_id, step_id, 
                    started_at, completed_at, status, 
                    workflow_state, success_response, error_response,
                    created_at, created_by, updated_at, updated_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (step_run_id) 
                DO UPDATE SET
                    completed_at = EXCLUDED.completed_at,
                    status = EXCLUDED.status,
                    workflow_state = EXCLUDED.workflow_state,
                    success_response = EXCLUDED.success_response,
                    error_response = EXCLUDED.error_response,
                    updated_at = EXCLUDED.updated_at,
                    updated_by = EXCLUDED.updated_by
                """
                
                completed_at = datetime.now()
                completion_params = (
                    workflow_run_id,
                    workflow_state.current_step_run_id,
                    workflow_id,
                    step_id,
                    started_at,
                    completed_at,
                    status,  # Now uses correct TaskState enum value
                    json.dumps(final_workflow_state),
                    json.dumps(success_response) if success_response else None,
                    json.dumps(error_response) if error_response else None,
                    started_at,  
                    "system",    
                    completed_at,  
                    "system"
                )
                
                database.execute_query(completion_upsert_query, completion_params, fetch=False)
                logger.info(f"Completed workflow run record - Step: {workflow_state.current_step_run_id} with status: {status}")
                
                if result_state.task_state != TaskState.input_required:
                    result_state.current_step_run_id = str(uuid.uuid4())
                return result_state
                
            except Exception as e:
                # Handle execution errors with upsert
                logger.error(f"Error in step execution {step_id}: {e}", exc_info=True)
                
                completed_at = datetime.now()
                error_data = {
                    "error": str(e),
                    "failure_message": step_detail.get("failure_message", "Step execution failed"),
                    "step_id": step_id,
                    "workflow_run_id": workflow_run_id,
                    "step_run_id": workflow_state.current_step_run_id,
                    "exception_type": type(e).__name__
                }
                
                # Error workflow state - store in workflow_state column (not output_workflow_state)
                error_workflow_state = {
                   "inputs": workflow_state.workflow_state,
                    "status": TaskState.failed.value,  # 'failed'
                    "output": workflow_state.output,
                    "step_ids": workflow_state.step_ids,
                    "next_step_ids": workflow_state.next_step_ids,
                    "start_step_id": workflow_state.start_step_id,
                    "workflow_id": workflow_state.workflow_id,
                    "workflow_run_id": workflow_state.workflow_run_id,
                    "current_step_run_id": workflow_state.current_step_run_id,
                    "execution_phase": "ERROR",
                    "error_details": error_data
                }
                
                # Error upsert - removed output_workflow_state column and schema reference
                error_upsert_query = """
                INSERT INTO workflow_run (
                    workflow_run_id, step_run_id, workflow_id, step_id, 
                    started_at, completed_at, status, 
                    workflow_state, error_response,
                    created_at, created_by, updated_at, updated_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (step_run_id) 
                DO UPDATE SET
                    completed_at = EXCLUDED.completed_at,
                    status = EXCLUDED.status,
                    workflow_state = EXCLUDED.workflow_state,
                    error_response = EXCLUDED.error_response,
                    updated_at = EXCLUDED.updated_at,
                    updated_by = EXCLUDED.updated_by
                """
                
                error_params = (
                    workflow_run_id,
                    workflow_state.current_step_run_id,
                    workflow_id,
                    step_id,
                    started_at,
                    completed_at,
                    TaskState.failed.value,  # 'failed'
                    json.dumps(error_workflow_state),  # Store in workflow_state column
                    json.dumps(error_data),
                    started_at,  # created_at
                    "system",    # created_by
                    completed_at,  # updated_at
                    "system"     # updated_by
                )
                
                database.execute_query(error_upsert_query, error_params, fetch=False)
                logger.info(f"Updated workflow run record: {workflow_state.current_step_run_id} with ERROR status")

                raise e

        
        return wrapper
    return decorator