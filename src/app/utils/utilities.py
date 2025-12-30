import json
from typing import Any, Optional, Dict, List
import re
from app.utils.logging import logger

from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.ext import parse as jsonpath_ext_parse

class Utilities:

    @staticmethod
    def json_or_none(payload: Any) -> Optional[str]:
        if payload is None:
            return None
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return None



    @staticmethod
    def _resolve_recursive_reference(data: dict, ref_path: str) -> Any:
        """
        Resolve references like $..selected_order_id or $.selected_order_id in the data
        """
        from app.utils.logging import logger

        if ref_path.startswith('$..'):
            field_name = ref_path[3:]
            # Recursive search
            def find_field_recursive(obj, field):
                results = []
                if isinstance(obj, dict):
                    if field in obj:
                        results.append(obj[field])
                    for value in obj.values():
                        results.extend(find_field_recursive(value, field))
                elif isinstance(obj, list):
                    for item in obj:
                        results.extend(find_field_recursive(item, field))
                return results
            results = find_field_recursive(data, field_name)
        elif ref_path.startswith('$.'):
            # Direct child of root
            field_name = ref_path[2:]
            results = [data.get(field_name)] if field_name in data else []
        else:
            logger.warning(f"Reference path '{ref_path}' not supported")
            return None

        logger.debug(f"Resolved reference '{ref_path}' -> {results}")
        return results[0] if results else None

    @staticmethod
    def _handle_complex_filter(data: dict, json_path: str) -> List[Any]:
        """
        Handle complex filter expressions manually when JSONPath library fails
        """
        from app.utils.logging import logger
        
        try:
            # Fixed pattern - removed problematic boundaries
            filter_pattern = r'\$\.([^[]+)\[\?\(@\.([^=\s]+)\s*==\s*(\$\.\.?[^)]+)\)\]\.(.+)'
            match = re.match(filter_pattern, json_path)
            
            if not match:
                logger.warning(f"Complex filter pattern not recognized: {json_path}")
                return []

            array_field = match.group(1)  # vehicles
            filter_field = match.group(2)  # soldOrderNumber  
            reference_path = match.group(3)  # $..selected_order_id
            target_field = match.group(4)  # productionVIN
            
            # Get the array to filter
            array_data = data.get(array_field, [])
            if not isinstance(array_data, list):
                logger.warning(f"Expected array for field '{array_field}', got {type(array_data)}")
                return []
            
            # Resolve the reference value
            reference_value = Utilities._resolve_recursive_reference(data, reference_path)
            if reference_value is None:
                logger.warning(f"Could not resolve reference '{reference_path}'")
                return []
            
            logger.info(f"Filter criteria: {filter_field} == {reference_value}")
            
            # Filter the array and extract target field
            results = []
            for item in array_data:
                if isinstance(item, dict) and item.get(filter_field) == reference_value:
                    target_value = item.get(target_field)
                    if target_value is not None:
                        results.append(target_value)
                        logger.info(f"Found match: {item.get(filter_field)} == {reference_value} -> {target_value}")
            
            return results
        
        except Exception as e:
            logger.error(f"Complex filter processing failed: {e}", exc_info=True)
            return []

    @staticmethod
    def extract_json_path_value(data: Dict[str, Any], json_path: str) -> Any:
        """
        Extract value from nested dictionary using JSONPath notation.
        Supports complex JSONPath expressions including filters and recursive descent.
        
        Args:
            data: Dictionary to extract from
            json_path: JSONPath expression
            
        Returns:
            Extracted value or list of values, None if not found
        """
        if not json_path:
            return None

        from app.utils.logging import logger
        
        try:
            # Handle complex filter expressions manually
            if '[?(@.' in json_path and '$.' in json_path and '==' in json_path:
                logger.info(f"Handling complex filter expression: {json_path}")
                results = Utilities._handle_complex_filter(data, json_path)
                
                if not results:
                    return None
                elif len(results) == 1:
                    return results[0]
                else:
                    return results
            
            # Try with jsonpath-ng first (better filter support)
            try:
                # Use extended parser for filter expressions
                if '[?' in json_path:
                    jsonpath_expr = jsonpath_ext_parse(json_path)
                else:
                    jsonpath_expr = jsonpath_parse(json_path)
                
                matches = jsonpath_expr.find(data)
                
                if not matches:
                    return None
                
                # Extract values
                results = [match.value for match in matches]
                
                # Return single value if only one match, otherwise return list
                if len(results) == 1:
                    return results[0]
                else:
                    return results
                    
            except Exception as e:
                logger.warning(f"jsonpath-ng failed for '{json_path}': {e}, trying fallback")
                # Fall through to manual handling
            
        except Exception as e:
            logger.warning(f"JSONPath extraction failed for '{json_path}': {str(e)}")
            return None

    @staticmethod
    def resolve_jsonpath_in_params(tool_input: Any, workflow_data: dict) -> Any:
        """
        Recursively resolve JSONPath expressions in tool parameters using workflow state data.
        Now supports complex JSONPath expressions with filters, comparisons, and recursive descent.
        """
        from app.utils.logging import logger
        
        def is_jsonpath_expression(value: str) -> bool:
            """Check if a string looks like a JSONPath expression"""
            if not isinstance(value, str):
                return False
            
            # Enhanced JSONPath patterns including complex expressions
            jsonpath_patterns = [
                value.startswith('$.'),           # $.field.subfield
                value.startswith('$['),           # $[0].field or $['key']
                value == '$',                     # Root reference
                value.startswith('$..'),          # Recursive descent
                '[?' in value,                    # Filter expressions
                '==' in value and '$' in value,   # Comparison expressions
                '!=' in value and '$' in value,   # Not equal comparisons
                '<' in value and '$' in value,    # Less than comparisons
                '>' in value and '$' in value,    # Greater than comparisons
                '[*]' in value,                   # Wildcard array access
                '..' in value and '$' in value,   # Recursive descent anywhere
            ]
            
            return any(jsonpath_patterns)
        
        def resolve_value(value: Any, data: dict) -> Any:
            """Resolve a single value if it's a JSONPath expression"""
            if is_jsonpath_expression(value):
                try:
                    resolved = Utilities.extract_json_path_value(data, value)
                    if resolved is not None:
                        logger.debug(f"Resolved JSONPath '{value}' -> {resolved}")
                        return resolved
                    else:
                        logger.debug(f"JSONPath '{value}' resolved to None/empty, keeping original")
                        return value
                except Exception as e:
                    logger.warning(f"Failed to resolve JSONPath '{value}': {e}")
                    return value
            return value
        
        # Handle different input types
        if isinstance(tool_input, dict):
            resolved_dict = {}
            for key, value in tool_input.items():
                if isinstance(value, (dict, list)):
                    # Recursively process nested structures
                    resolved_dict[key] = Utilities.resolve_jsonpath_in_params(value, workflow_data)
                else:
                    # Try to resolve the value
                    resolved_dict[key] = resolve_value(value, workflow_data)
            return resolved_dict
        
        elif isinstance(tool_input, list):
            resolved_list = []
            for item in tool_input:
                if isinstance(item, (dict, list)):
                    # Recursively process nested structures
                    resolved_list.append(Utilities.resolve_jsonpath_in_params(item, workflow_data))
                else:
                    # Try to resolve the item
                    resolved_list.append(resolve_value(item, workflow_data))
            return resolved_list
        
        elif isinstance(tool_input, str):
            # Single string value - check if it's a JSONPath
            return resolve_value(tool_input, workflow_data)
        
        else:
            # Other types (int, float, bool, None) - return as-is
            return tool_input

    @staticmethod
    def validate_jsonpath_expression(json_path: str, sample_data: dict = None) -> bool:
        """
        Validate if a JSONPath expression is syntactically correct.
        """
        try:
            if '[?' in json_path:
                jsonpath_ext_parse(json_path)
            else:
                jsonpath_parse(json_path)
            
            if sample_data:
                Utilities.extract_json_path_value(sample_data, json_path)
            
            return True
        except Exception:
            return False

    @staticmethod
    def get_all_jsonpath_matches(data: dict, json_path: str) -> list:
        """
        Get all matches for a JSONPath expression, always returning a list.
        """
        try:
            result = Utilities.extract_json_path_value(data, json_path)
            if result is None:
                return []
            elif isinstance(result, list):
                return result
            else:
                return [result]
        except Exception as e:
            
            logger.warning(f"JSONPath query failed for '{json_path}': {e}")
            return []

