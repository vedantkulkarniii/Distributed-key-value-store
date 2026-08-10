"""
Command Parser and Validation for Distributed KV Store.

Handles parsing, validating, and serializing commands for RPC
and HTTP interfaces. Ensures type safety and comprehensive error handling.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Raised when command parsing fails."""
    pass


class ValidationError(Exception):
    """Raised when command validation fails."""
    pass


class CommandParser:
    """
    Parses and validates commands for the state machine.
    
    Supports:
    - JSON deserialization from RPC/HTTP
    - Command validation (type checking, required fields)
    - Error handling and reporting
    - Command serialization for responses
    """
    
    # Supported operations
    VALID_OPERATIONS = {"SET", "GET", "DELETE", "SCAN", "CAS"}
    
    # Field requirements per operation
    OPERATION_FIELDS = {
        "SET": {"required": ["key", "value"], "optional": []},
        "GET": {"required": ["key"], "optional": []},
        "DELETE": {"required": ["key"], "optional": []},
        "SCAN": {"required": [], "optional": ["prefix"]},
        "CAS": {"required": ["key", "value"], "optional": ["expected_value"]},
    }
    
    # Type constraints
    FIELD_TYPES = {
        "operation": str,
        "key": (str, type(None)),
        "value": (str, type(None)),
        "expected_value": (str, type(None)),
        "prefix": (str, type(None)),
    }
    
    # Maximum lengths to prevent abuse
    MAX_KEY_LENGTH = 1024
    MAX_VALUE_LENGTH = 1024 * 1024  # 1MB
    MAX_PREFIX_LENGTH = 256
    
    def __init__(self):
        """Initialize the command parser."""
        self.parse_count = 0
        self.error_count = 0
        self.validation_error_count = 0
    
    def parse_json(self, json_str: str) -> Dict[str, Any]:
        """
        Parse JSON string to dictionary.
        
        Args:
            json_str: JSON string containing command
            
        Returns:
            Parsed dictionary
            
        Raises:
            ParseError: If JSON is invalid
        """
        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                raise ParseError("Expected JSON object (dictionary)")
            return data
        except json.JSONDecodeError as e:
            self.error_count += 1
            raise ParseError(f"Invalid JSON: {str(e)}")
        except Exception as e:
            self.error_count += 1
            raise ParseError(f"Failed to parse JSON: {str(e)}")
    
    def validate_command_dict(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate command dictionary.
        
        Args:
            data: Command dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check operation exists
        if "operation" not in data:
            return False, "Missing 'operation' field"
        
        operation = data["operation"]
        
        # Validate operation is string and in valid list
        if not isinstance(operation, str):
            return False, f"Operation must be string, got {type(operation).__name__}"
        
        if operation not in self.VALID_OPERATIONS:
            return False, f"Unknown operation: {operation}. Valid: {self.VALID_OPERATIONS}"
        
        # Get operation requirements
        requirements = self.OPERATION_FIELDS.get(operation, {})
        required_fields = requirements.get("required", [])
        optional_fields = requirements.get("optional", [])
        
        # Check required fields
        for field in required_fields:
            if field not in data:
                return False, f"Operation '{operation}' requires field '{field}'"
        
        # Validate field types
        for field, value in data.items():
            if field == "operation":
                continue
            
            if field not in self.FIELD_TYPES:
                return False, f"Unknown field: {field}"
            
            expected_type = self.FIELD_TYPES[field]
            if not isinstance(value, expected_type):
                type_names = expected_type if isinstance(expected_type, tuple) else (expected_type,)
                type_str = " or ".join(t.__name__ for t in type_names)
                return False, f"Field '{field}' must be {type_str}, got {type(value).__name__}"
        
        # Validate field lengths
        if "key" in data and data["key"] is not None:
            if len(data["key"]) > self.MAX_KEY_LENGTH:
                return False, f"Key exceeds maximum length {self.MAX_KEY_LENGTH}"
        
        if "value" in data and data["value"] is not None:
            if len(data["value"]) > self.MAX_VALUE_LENGTH:
                return False, f"Value exceeds maximum length {self.MAX_VALUE_LENGTH}"
        
        if "prefix" in data and data["prefix"] is not None:
            if len(data["prefix"]) > self.MAX_PREFIX_LENGTH:
                return False, f"Prefix exceeds maximum length {self.MAX_PREFIX_LENGTH}"
        
        # Operation-specific validation
        if operation == "SET":
            if not data.get("key"):
                return False, "SET requires non-empty key"
            if data.get("value") is None:
                return False, "SET requires value"
        
        elif operation == "GET":
            if not data.get("key"):
                return False, "GET requires non-empty key"
        
        elif operation == "DELETE":
            if not data.get("key"):
                return False, "DELETE requires non-empty key"
        
        elif operation == "SCAN":
            # SCAN is allowed with no prefix (scans all keys)
            pass
        
        elif operation == "CAS":
            if not data.get("key"):
                return False, "CAS requires non-empty key"
            if data.get("value") is None:
                return False, "CAS requires value"
            # expected_value is allowed to be None (matching missing keys)
        
        return True, None
    
    def parse_and_validate(self, json_str: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Parse and validate command in one step.
        
        Args:
            json_str: JSON string containing command
            
        Returns:
            Tuple of (success, command_dict, error_message)
        """
        self.parse_count += 1
        
        try:
            # Parse JSON
            data = self.parse_json(json_str)
            
            # Validate
            is_valid, error_msg = self.validate_command_dict(data)
            if not is_valid:
                self.validation_error_count += 1
                return False, None, error_msg
            
            return True, data, None
            
        except ParseError as e:
            return False, None, str(e)
        except Exception as e:
            self.error_count += 1
            return False, None, f"Unexpected error: {str(e)}"
    
    def serialize_command_result(
        self,
        success: bool,
        value: Optional[Any] = None,
        error: Optional[str] = None,
        version: Optional[int] = None,
    ) -> str:
        """
        Serialize command result to JSON.
        
        Args:
            success: Whether command succeeded
            value: Result value (if applicable)
            error: Error message (if failed)
            version: Version/timestamp
            
        Returns:
            JSON string
        """
        result = {
            "success": success,
            "value": value,
            "error": error,
            "version": version,
        }
        
        # Remove None values for cleaner JSON
        result = {k: v for k, v in result.items() if v is not None or k == "success"}
        
        try:
            return json.dumps(result)
        except TypeError as e:
            # Handle non-serializable values
            logger.error(f"Failed to serialize result: {e}")
            return json.dumps({
                "success": False,
                "error": f"Failed to serialize result: {str(e)}",
            })
    
    def validate_batch(self, commands: List[Dict[str, Any]]) -> List[Tuple[bool, Optional[str]]]:
        """
        Validate a batch of commands.
        
        Args:
            commands: List of command dictionaries
            
        Returns:
            List of (is_valid, error_message) tuples
        """
        results = []
        for cmd in commands:
            is_valid, error_msg = self.validate_command_dict(cmd)
            results.append((is_valid, error_msg))
        return results
    
    def get_statistics(self) -> Dict[str, int]:
        """
        Get parsing statistics.
        
        Returns:
            Dictionary with parse/error counts
        """
        return {
            "total_parsed": self.parse_count,
            "parse_errors": self.error_count,
            "validation_errors": self.validation_error_count,
            "successful": self.parse_count - self.error_count - self.validation_error_count,
        }


class CommandNormalizer:
    """
    Normalizes command data for consistent handling.
    
    Handles:
    - Empty string to None conversion
    - Whitespace trimming
    - Case normalization
    """
    
    @staticmethod
    def normalize(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize command data.
        
        Args:
            data: Command dictionary
            
        Returns:
            Normalized dictionary
        """
        normalized = dict(data)
        
        # Normalize operation to uppercase
        if "operation" in normalized:
            normalized["operation"] = normalized["operation"].upper()
        
        # Normalize string fields (trim whitespace, convert empty to None)
        for field in ["key", "prefix", "value", "expected_value"]:
            if field in normalized and isinstance(normalized[field], str):
                # Trim whitespace
                normalized[field] = normalized[field].strip()
                # Keep empty strings as-is for explicit empty values
        
        return normalized


class CommandValidator:
    """
    Advanced command validation with detailed error reporting.
    
    Provides:
    - Semantic validation
    - Consistency checking
    - Performance validation
    """
    
    def __init__(self, strict_mode: bool = False):
        """
        Initialize validator.
        
        Args:
            strict_mode: If True, apply stricter validation rules
        """
        self.strict_mode = strict_mode
        self.validation_errors: List[str] = []
    
    def validate_with_context(
        self,
        command: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Validate command with optional context.
        
        Args:
            command: Command dictionary
            context: Optional context (e.g., current state)
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        self.validation_errors = []
        
        operation = command.get("operation")
        key = command.get("key")
        value = command.get("value")
        
        # Semantic validation
        if operation in ("GET", "DELETE"):
            if not key:
                self.validation_errors.append(f"{operation} requires non-empty key")
        
        if operation == "SET":
            if not key or value is None:
                self.validation_errors.append("SET requires non-empty key and value")
            
            if self.strict_mode and len(key) < 1:
                self.validation_errors.append("Key must be at least 1 character")
        
        if operation == "SCAN":
            prefix = command.get("prefix", "")
            if prefix and len(prefix) > 256:
                self.validation_errors.append("Prefix too long (max 256 chars)")
        
        if operation == "CAS":
            if not key:
                self.validation_errors.append("CAS requires non-empty key")
            if value is None:
                self.validation_errors.append("CAS requires value")
        
        return len(self.validation_errors) == 0, self.validation_errors
