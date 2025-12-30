from functools import partial
import json
from typing import Dict, Any, Optional
from jinja2 import Environment, meta
from langgraph.graph import StateGraph, START, END
from a2a.types import TaskState
from app.models.validation_rule import ValidationRuleItem
from app.utils.decorators import timed
from app.utils.logging import logger
from app.utils.settings import SETTINGS
from app.utils.utilities import Utilities
from app.agent.wokflow_state import WorkflowState
import httpx
from app.agent.workflow_decorators import process_workflow_run
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import asyncio


class WorkflowExecutor:
    """
    Executes workflows step by step based on workflow definitions from database.
    Manages the execution flow and state transitions between steps.
    """

    def __init__(self):
        """
        Initialize the workflow executor.
        """
        self.current_workflow_id: Optional[str] = None
        self.graph: Optional[StateGraph] = None

    def build_graph(self, workflow_state: WorkflowState):
        """
        Build a LangGraph workflow from workflow state.
        
        Args:
            workflow_state: WorkflowState containing workflow definition and steps
            
        Returns:
            Compiled LangGraph workflow
        """
        
        # Create the graph
        graph = StateGraph(WorkflowState)
        
        # Get step information from workflow state
        step_ids = workflow_state.step_ids
        steps = workflow_state.steps
        start_step_id = workflow_state.start_step_id
        
        if not step_ids or not steps:
            logger.warning("No steps found in workflow state")
            return None
        
        logger.info(f"Building graph with steps: {step_ids}")
        logger.info(f"Start step: {start_step_id}")
        
        # Create step_ids_used_for_edges - ignore all steps before start_step_id
        step_ids_used_for_edges = []
        if start_step_id in step_ids:
            start_index = step_ids.index(start_step_id)
            step_ids_used_for_edges = step_ids[start_index:]
            logger.info(f"Steps used for edges (from start_step_id): {step_ids_used_for_edges}")
        else:
            # If start_step_id not found, use all steps
            step_ids_used_for_edges = step_ids
            logger.warning(f"start_step_id '{start_step_id}' not found in step_ids, using all steps")
        
        # Create mapping of step_id to step details
        step_details = {step.get("step_id"): step for step in steps}
        
        # Create a mapping of step_id to next_step_id
        step_to_next = {}
        for step in steps:
            step_id = step.get("step_id")
            next_step = step.get("next_step_id")
            step_to_next[step_id] = next_step
        
        # Add nodes for each step based on their actual type (use all step_ids for nodes)
        for step_id in step_ids:
            step_detail = step_details.get(step_id)
            if not step_detail:
                logger.warning(f"Step details not found for step_id: {step_id}")
                continue
                
            step_type = step_detail.get("type")
            
            # Map step types to handler methods with step info
            if step_type == "USER_INPUT":
                handler = partial(self.user_input_with_step, step_detail)
                graph.add_node(step_id, handler)
            elif step_type == "FINAL_RESPONSE":
                handler = partial(self.final_response_with_step, step_detail)
                graph.add_node(step_id, handler)
            elif step_type == "SYSTEM_ACTION":
                handler = partial(self.system_control_with_step, step_detail)
                graph.add_node(step_id, handler)
            else:
                logger.warning(f"Unknown step type '{step_type}' for step '{step_id}', defaulting to SYSTEM_ACTION")
                handler = partial(self.system_control_with_step, step_detail)
                graph.add_node(step_id, handler)
        
        # Add edges between steps with conditional logic (use step_ids_used_for_edges)
        if start_step_id:
            # Connect START to first step
            graph.add_edge(START, start_step_id)
            
            # Connect steps to each other with conditional routing - only for steps from start_step_id onwards
            for step_id in step_ids_used_for_edges:
                next_step = step_to_next.get(step_id)
                
                # Add conditional edge that checks workflow state status
                def should_continue(state: WorkflowState, current_step_id=step_id, next_step_id=next_step):
                    """
                    Determine the next step based on workflow state status.
                    
                    Args:
                        state: Current workflow state
                        current_step_id: ID of the current step
                        next_step_id: ID of the configured next step
                        
                    Returns:
                        Next step ID or END
                    """
                    logger.info(f"Step {current_step_id} completed with status: {state.task_state}")

                    logger.info(f"Here is the Go to Step Id: {state.go_to_step_id}")
                    
                    # Check if orchestration rule set a go_to_step_id
                    if hasattr(state, 'go_to_step_id') and state.go_to_step_id:
                        target_step_id = state.go_to_step_id
                        state.go_to_step_id=None
                        logger.info(f"Orchestration rule routing from {current_step_id} to {target_step_id}")
                        return target_step_id
                    
                    # Get status value
                    if hasattr(state.task_state, 'value'):
                        status_value = state.task_state.value
                    else:
                        status_value = str(state.task_state)
                    
                    # If status is input_required, go to END to pause workflow
                    if status_value == TaskState.input_required.value:
                        logger.info(f"Step {current_step_id} requires input, routing to END")
                        return END
                    elif status_value == TaskState.failed.value or status_value == TaskState.canceled.value:
                        logger.info(f"Step {current_step_id} {status_value}, routing to END")
                        return END
                    elif next_step_id and next_step_id in step_ids_used_for_edges:
                        logger.info(f"Step {current_step_id} completed, routing to next step: {next_step_id}")
                        return next_step_id
                    else:
                        # No next step or workflow completed
                        logger.info(f"Step {current_step_id} is final step, routing to END")
                        return END
                
                # Create the conditional mapping - include all possible step targets
                possible_targets = {END: END}  # Always include END
                
                # Add the normal next step if it exists
                if next_step and next_step in step_ids_used_for_edges:
                    possible_targets[next_step] = next_step
                
                # Add ALL step IDs as possible targets for orchestration rules
                for step_id_target in step_ids:
                    possible_targets[step_id_target] = step_id_target
                
                graph.add_conditional_edges(
                    step_id,
                    should_continue,
                    possible_targets
                )
        
        # Compile and store the graph
        compiled_graph = graph.compile()
        
        # Store current workflow info
        self.current_workflow_id = workflow_state.workflow_state.get("workflow_id")
        self.graph = compiled_graph
        
        logger.info(f"Graph compiled successfully for workflow: {self.current_workflow_id}")
        logger.info(f"Graph contains {len(step_ids)} nodes: {step_ids}")
        
        return compiled_graph

    async def execute(self, workflow_state: WorkflowState) -> WorkflowState:
        """
        Execute a workflow using the workflow state.
        
        Args:
            workflow_state: WorkflowState containing workflow definition, steps, and execution context
            
        Returns:
            Updated workflow state after execution
        """
        workflow_state=await self.graph.ainvoke(workflow_state)
        return workflow_state

    @timed("User Input Step")
    @process_workflow_run()
    async def user_input_with_step(self, step_detail: Dict[str, Any], workflow_state: WorkflowState) -> WorkflowState:
        """
        Handle user input step with step details.
        
        Args:
            step_detail: Current step information
            workflow_state: Current workflow state
            
        Returns:
            Updated workflow state with user input processing
        """
    
        step_id = step_detail.get("step_id")
        logger.info(f"Processing user input step: {step_id}")
        user_interaction=step_detail.get("user_interaction",{})
        workflow_id=workflow_state.workflow_id
        workflow_name=workflow_state.workflow_name
        workflow_exit_keywords=workflow_state.worflow_exit_keywords
        
        workflow_input_text = workflow_state.input
        workflow_input_data = workflow_state.input_data

        if workflow_input_text and workflow_input_text.lower() in [keyword.lower() for keyword in workflow_exit_keywords]:
            logger.info(f"Workflow exit keyword '{workflow_input_text}' received, terminating workflow.")
            workflow_state.task_state = TaskState.canceled.value
            workflow_state.output = {"summary": f"Workflow {workflow_id} ({workflow_name}) terminated."}
            return workflow_state

        # This means the workflow is a existing conversation waiting for user input (start_step_id is waiting conversation has started from)
        # if workflow_state.go_to_step_id is present, it means the workflow is being routed to a different step based on orchestration rules and not waiting for user input
        if not workflow_state.is_new_conversation and step_id == workflow_state.start_step_id and not workflow_state.go_to_step_id:
            expected_data_keys=user_interaction.get("expected_data_key", [])
            if workflow_input_data and len(expected_data_keys) > 0:
                for key in expected_data_keys:
                    if key in workflow_input_data:
                        workflow_state.workflow_state[key] = workflow_input_data[key]
            elif workflow_input_text and len(expected_data_keys) >= 1:
                expected_data_key = expected_data_keys[0] if expected_data_keys else None
                workflow_state.workflow_state[expected_data_key] = workflow_input_text

                if expected_data_key == "confirm_action" and workflow_input_text.lower() in ['no', 'n']:
                    logger.info(f"User declined confirmation, exiting workflow")
                    workflow_state.task_state = TaskState.canceled.value
                    workflow_state.output = {"summary": "Action cancelled by user"}
                    return workflow_state
            
            orchestration_rules = user_interaction.get("orchestration_rules", None)
            if orchestration_rules:
                for rule in orchestration_rules:
                    try:
                        # Handle new format with Jinja2 conditions
                        if "condition" in rule and "go_to_step" in rule:
                            condition_template = rule.get("condition")
                            target_step_id = rule.get("go_to_step")
                           
                            # Get all undeclared variables from template
                            template_env = Environment()
                            parsed_content = template_env.parse(condition_template)
                            template_variables = meta.find_undeclared_variables(parsed_content)
                            
                            logger.info(f"Template variables found: {template_variables}")
                            
                            # Create context with workflow state (direct field access)
                            context = workflow_state.workflow_state.copy()
                           
                            # Check if all required variables are available
                            missing_vars = []
                            for var in template_variables:
                                if var not in context:
                                    missing_vars.append(var)
                                                             
                            if missing_vars:
                                logger.warning(f"Orchestration rule condition '{condition_template}' references undefined variables: {missing_vars}. Skipping rule.")
                                continue
                            
                            # Use Jinja2 to evaluate the condition
                            template = template_env.from_string(condition_template)
                            
                            try:
                                # Render the condition and evaluate as boolean
                                rendered_condition = template.render(context)
                                logger.info(f"Rendered condition: {rendered_condition}")
                                
                                # Simple evaluation - check if condition evaluates to True
                                condition_result = eval(rendered_condition)
                                
                                if condition_result:
                                    logger.info(f"Orchestration rule matched: {condition_template}, routing to step {target_step_id}")
                                    workflow_state.go_to_step_id = target_step_id
                                    break  # Exit after first match
                            except Exception as eval_error:
                                logger.error(f"Error evaluating condition '{condition_template}': {eval_error}")
                                raise ValueError(f"Failed to evaluate orchestration rule condition '{condition_template}': {eval_error}")
                                
                    except Exception as e:
                        logger.error(f"Invalid orchestration rule data: {rule}, error: {e}")
                        raise ValueError(f"Invalid orchestration rule data: {rule}, error: {e}")

                            # Ensure all template variables are reset in workflow state so they are not available in the next run

                for temp_var in template_variables:
                    workflow_state.workflow_state[temp_var] = None
                    workflow_state.input_data[temp_var] = None

            workflow_state.task_state = TaskState.completed.value          

        else:
            # Reset go_to_step_id to avoid unintended routing in next steps
            workflow_state.go_to_step_id=None
            
            user_message = step_detail.get("user_interaction",{}).get("user_message", None)
            
            template_env = Environment()
            template = template_env.from_string(user_message)
            rendered_template = template.render(workflow_state.workflow_state)
            output={}
            try:
                output = json.loads(rendered_template)
            except json.JSONDecodeError:
                output["summary"] = rendered_template
            
            workflow_state.output = output
            workflow_state.task_state = TaskState.input_required.value
        
        return workflow_state
    
    async def call_tool(self, state, tool_input, is_remote):
        if is_remote:
            tool_input["token"] = state.token
            result = await self.remote_session.call_tool(state.selected_tool, tool_input)
        else:
            tool_input["token"] = state.token
            result = await self.session.call_tool(state.selected_tool, tool_input)
        result_dict = json.loads(result.content[0].text)
        return result_dict

    @timed("System Control Step")
    @process_workflow_run()
    async def system_control_with_step(self, step_detail: Dict[str, Any], workflow_state: WorkflowState) -> WorkflowState:
        """
        Handle system control/action step with step details.
        
        Args:
            step_detail: Current step information
            workflow_state: Current workflow state
            
        Returns:
            Updated workflow state with system action results
        """
        step_id = step_detail.get("step_id")
        logger.info(f"Processing system control step: {step_id}")
        
        # Access step details
        system_action = step_detail.get("system_action_details", {})
        
        failure_message = step_detail.get("failure_message")
        tool_input = system_action.get("inputs") 
        tool_name = system_action.get("name")
        error_mapping = system_action.get("error_mapping", {})
        output_mapping = system_action.get("output_mapping")

        tool_params = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
        
        if tool_params:
            logger.info(f"Original tool_params: {tool_params}")
            workflow_state.workflow_state["token"]=workflow_state.token
            workflow_state.workflow_state["user_id"] = workflow_state.user_id
            tool_params = Utilities.resolve_jsonpath_in_params(tool_params, workflow_state.workflow_state)
            del workflow_state.workflow_state["token"]
            del workflow_state.workflow_state["user_id"]
            logger.info(f"Resolved tool_params: {tool_params}")
        
        result = {}
        tool_output = {}
        
        try:
            async with asyncio.timeout(45):
                async with streamablehttp_client(SETTINGS.cubeassist_mcp_server_url) as (read, write, _):
                    async with ClientSession(read, write) as mcp_session:
                        logger.info(f"Initializing MCP session for tool: {tool_name}")
                        await mcp_session.initialize()
                        logger.info(f"MCP session initialized, calling tool: {tool_name} with params: {tool_params}")
                        result = await mcp_session.call_tool(tool_name, tool_params)
                        tool_output = result.content[0].text
                        if isinstance(tool_output, str):
                            tool_output = json.loads(tool_output)
                        logger.info(f"Tool {tool_name} executed successfully")

            # Check for error in tool output
            error_mapping = Utilities.resolve_jsonpath_in_params(error_mapping, tool_output)
            if error_mapping.get("error_status", None) == 'error':
                error_message = error_mapping.get("error_message", f"Tool {tool_name} returned error")
                logger.error(f"Tool returned error: {error_message}")
                raise Exception(error_message)

        except asyncio.TimeoutError:
            logger.error(f"MCP session timeout for tool: {tool_name}")
            workflow_state.task_state = TaskState.failed.value
            workflow_state.output = {"summary": f"Tool execution timeout: {tool_name}"}
            return workflow_state
        
        except Exception as e:
            logger.error(f"MCP session error for tool {tool_name}: {e}", exc_info=True)
            workflow_state.task_state = TaskState.failed.value
            workflow_state.output = {"summary": f"{str(e)}"}
            return workflow_state
        
        # Process success mapping
        success_mapping = system_action.get("success_mapping", {})
        if success_mapping and isinstance(success_mapping, dict):
            for key, json_path in success_mapping.items():
                workflow_state.inputs[key] = Utilities.extract_json_path_value(tool_output, json_path)
        
        # Process output_key mappings to extract values from tool_output
        if output_mapping and isinstance(output_mapping, dict):
            logger.info(f"Processing output mappings: {output_mapping}")
            
            for key, json_path in output_mapping.items():
                # Extract value using JSON path
                extracted_value = Utilities.extract_json_path_value(tool_output, json_path)
                
                # If the extracted value is a string, properly escape it for JSON
                if isinstance(extracted_value, str):
                    try:
                        # Use json.dumps to properly escape, then remove outer quotes
                        escaped_value = json.dumps(extracted_value)
                        # Remove the outer quotes that json.dumps adds
                        extracted_value = escaped_value[1:-1] if len(escaped_value) > 1 else extracted_value
                    except Exception as escape_error:
                        logger.warning(f"Could not escape value for key '{key}': {escape_error}")
                        # Fallback: basic manual escaping
                        extracted_value = extracted_value.replace('\n', '\\n').replace('"', '\\"')
                
                # Update workflow state inputs with the extracted value
                workflow_state.workflow_state[key] = extracted_value
                
                logger.info(f"Mapped '{key}' = {extracted_value} from path '{json_path}'")

        workflow_state.task_state = TaskState.completed.value
        return workflow_state

    @timed("Final Step")
    @process_workflow_run()
    async def final_response_with_step(self, step_detail: Dict[str, Any], workflow_state: WorkflowState) -> WorkflowState:
        """
        Handle final response step with step details.
        
        Args:
            step_detail: Current step information
            workflow_state: Current workflow state
            
        Returns:
            Updated workflow state with final response
        """
        step_id = step_detail.get("step_id")
        logger.info(f"Processing final response step: {step_id}")

        workflow_state.go_to_step_id=None
        
        # Get response template from step config
        user_message = step_detail.get("user_interaction", {}).get("user_message", None)
        
        if not user_message:
            logger.error(f"No response template found for step: {step_id}")
            workflow_state.task_state = TaskState.failed.value
            return workflow_state
        
        template_env = Environment()
        template = template_env.from_string(user_message)
        rendered_template = template.render(workflow_state.workflow_state)
        output={}
        try:
            output = json.loads(rendered_template)
        except json.JSONDecodeError:
            output["summary"] = rendered_template
        
        workflow_state.output = output
        workflow_state.task_state = TaskState.completed.value
        
        logger.info(f"Final response output: {output}")
        return workflow_state