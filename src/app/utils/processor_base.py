import inspect
import time
from abc import ABC, abstractmethod
from typing import Any
import json
from app.utils.logging import logger


class ProcessorBase(ABC):
    def __init__(self):
        self._caller: str | None = None

    @abstractmethod
    def _process(self, *args, **kwargs) -> Any:
        pass

    def process(self, *args, **kwargs) -> Any:
        caller = inspect.stack()[1].function  # Get the calling function name
        self._caller = caller  # Save for child access
        self.before_process(*args, **kwargs)
        start_time = time.time()
        logger.info(f"{self.__class__.__name__} started processing. Called from: {self._caller}")
        try:
            result = self._process(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in VehicleListingAll: {e}", exc_info=True)
            result = self._create_error_message(e, self.__class__.__name__)
        end_time = time.time()
        execution_time = end_time - start_time
        logger.info(f"{self.__class__.__name__} finished processing in {execution_time:.2f} seconds. Called from: {self._caller}")
        self.after_process(result)
        result=json.dumps(result,indent=2)
        return result

    def before_process(self, *args, **kwargs):
        pass

    def after_process(self, result: Any):
        pass
    def _create_error_message(self,e, method_name: str) -> dict:
        return { 'output': { 'data': { "method_name": method_name}, 'status': 'error', 'error': str(e)} }

