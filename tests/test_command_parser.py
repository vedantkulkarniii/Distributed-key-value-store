"""
Comprehensive tests for CommandParser, CommandNormalizer, and CommandValidator.

Tests cover:
- JSON parsing and validation
- Command validation per operation type
- Field type checking and length validation
- Batch validation
- Error handling and reporting
"""

import pytest
import json
from src.raft.command_parser import (
    CommandParser,
    CommandNormalizer,
    CommandValidator,
    ParseError,
    ValidationError,
)


class TestCommandParserParsing:
    """Test JSON parsing functionality."""
    
    def test_parse_valid_json(self):
        """Test parsing valid JSON."""
        parser = CommandParser()
        json_str = '{"operation": "SET", "key": "k1", "value": "v1"}'
        
        data = parser.parse_json(json_str)
        
        assert data["operation"] == "SET"
        assert data["key"] == "k1"
        assert data["value"] == "v1"
    
    def test_parse_invalid_json_raises_error(self):
        """Test that invalid JSON raises ParseError."""
        parser = CommandParser()
        
        with pytest.raises(ParseError):
            parser.parse_json("not valid json {")
    
    def test_parse_json_non_object_raises_error(self):
        """Test that non-object JSON raises ParseError."""
        parser = CommandParser()
        
        with pytest.raises(ParseError):
            parser.parse_json('["array"]')
    
    def test_parse_empty_json_object(self):
        """Test parsing empty JSON object."""
        parser = CommandParser()
        
        data = parser.parse_json('{}')
        
        assert data == {}
    
    def test_parse_count_increments(self):
        """Test that parse count increments."""
        parser = CommandParser()
        
        parser.parse_and_validate('{"operation": "SET", "key": "k1", "value": "v1"}')
        parser.parse_and_validate('{"operation": "GET", "key": "k1"}')
        
        assert parser.parse_count == 2


class TestCommandParserValidation:
    """Test command validation functionality."""
    
    def test_validate_valid_set_command(self):
        """Test validation of valid SET command."""
        parser = CommandParser()
        
        data = {"operation": "SET", "key": "k1", "value": "v1"}
        is_valid, error = parser.validate_command_dict(data)
        
        assert is_valid
        assert error is None
    
    def test_validate_missing_operation(self):
        """Test validation fails without operation."""
        parser = CommandParser()
        
        data = {"key": "k1", "value": "v1"}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
        assert "operation" in error.lower()
    
    def test_validate_unknown_operation(self):
        """Test validation fails with unknown operation."""
        parser = CommandParser()
        
        data = {"operation": "UNKNOWN", "key": "k1"}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
        assert "unknown operation" in error.lower()
    
    def test_validate_operation_not_string(self):
        """Test validation fails if operation not string."""
        parser = CommandParser()
        
        data = {"operation": 123, "key": "k1"}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
        assert "string" in error.lower()
    
    def test_validate_set_requires_key_and_value(self):
        """Test SET requires both key and value."""
        parser = CommandParser()
        
        # Missing value
        data = {"operation": "SET", "key": "k1"}
        is_valid, error = parser.validate_command_dict(data)
        assert not is_valid
        
        # Missing key
        data = {"operation": "SET", "value": "v1"}
        is_valid, error = parser.validate_command_dict(data)
        assert not is_valid
        
        # Empty key
        data = {"operation": "SET", "key": "", "value": "v1"}
        is_valid, error = parser.validate_command_dict(data)
        assert not is_valid
    
    def test_validate_get_requires_key(self):
        """Test GET requires key."""
        parser = CommandParser()
        
        data = {"operation": "GET"}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
        assert "key" in error.lower()
    
    def test_validate_delete_requires_key(self):
        """Test DELETE requires key."""
        parser = CommandParser()
        
        data = {"operation": "DELETE"}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
    
    def test_validate_scan_optional_prefix(self):
        """Test SCAN with optional prefix."""
        parser = CommandParser()
        
        # No prefix
        data = {"operation": "SCAN"}
        is_valid, error = parser.validate_command_dict(data)
        assert is_valid
        
        # With prefix
        data = {"operation": "SCAN", "prefix": "user:"}
        is_valid, error = parser.validate_command_dict(data)
        assert is_valid
    
    def test_validate_cas_requires_key_and_value(self):
        """Test CAS requires key and value."""
        parser = CommandParser()
        
        # Valid CAS
        data = {"operation": "CAS", "key": "k1", "value": "new", "expected_value": "old"}
        is_valid, error = parser.validate_command_dict(data)
        assert is_valid
        
        # CAS without value
        data = {"operation": "CAS", "key": "k1"}
        is_valid, error = parser.validate_command_dict(data)
        assert not is_valid
    
    def test_validate_unknown_field(self):
        """Test validation with unknown field."""
        parser = CommandParser()
        
        data = {"operation": "SET", "key": "k1", "value": "v1", "unknown": "field"}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
        assert "unknown field" in error.lower()
    
    def test_validate_key_length_limit(self):
        """Test key length limit enforcement."""
        parser = CommandParser()
        
        # Valid length
        data = {"operation": "SET", "key": "a" * 100, "value": "v1"}
        is_valid, error = parser.validate_command_dict(data)
        assert is_valid
        
        # Exceeds limit
        data = {"operation": "SET", "key": "a" * (1024 + 1), "value": "v1"}
        is_valid, error = parser.validate_command_dict(data)
        assert not is_valid
        assert "exceeds maximum length" in error.lower()
    
    def test_validate_value_length_limit(self):
        """Test value length limit enforcement."""
        parser = CommandParser()
        
        # Exceeds limit (1MB)
        data = {"operation": "SET", "key": "k1", "value": "v" * (1024 * 1024 + 1)}
        is_valid, error = parser.validate_command_dict(data)
        assert not is_valid
    
    def test_validate_prefix_length_limit(self):
        """Test prefix length limit enforcement."""
        parser = CommandParser()
        
        # Exceeds limit
        data = {"operation": "SCAN", "prefix": "p" * (256 + 1)}
        is_valid, error = parser.validate_command_dict(data)
        assert not is_valid
    
    def test_validate_field_types(self):
        """Test field type validation."""
        parser = CommandParser()
        
        # Key must be string or None
        data = {"operation": "GET", "key": 123}
        is_valid, error = parser.validate_command_dict(data)
        assert not is_valid
        assert "must be" in error.lower()


class TestParseAndValidate:
    """Test combined parse and validate functionality."""
    
    def test_parse_and_validate_success(self):
        """Test successful parse and validate."""
        parser = CommandParser()
        
        json_str = '{"operation": "SET", "key": "k1", "value": "v1"}'
        success, data, error = parser.parse_and_validate(json_str)
        
        assert success
        assert data is not None
        assert error is None
        assert data["operation"] == "SET"
    
    def test_parse_and_validate_parse_error(self):
        """Test parse error in combined call."""
        parser = CommandParser()
        
        json_str = "invalid json"
        success, data, error = parser.parse_and_validate(json_str)
        
        assert not success
        assert data is None
        assert error is not None
    
    def test_parse_and_validate_validation_error(self):
        """Test validation error in combined call."""
        parser = CommandParser()
        
        json_str = '{"operation": "SET", "key": "k1"}'  # Missing value
        success, data, error = parser.parse_and_validate(json_str)
        
        assert not success
        assert data is None
        assert error is not None


class TestSerializeResult:
    """Test command result serialization."""
    
    def test_serialize_success_result(self):
        """Test serializing successful result."""
        parser = CommandParser()
        
        json_str = parser.serialize_command_result(success=True, value="result")
        data = json.loads(json_str)
        
        assert data["success"]
        assert data["value"] == "result"
    
    def test_serialize_error_result(self):
        """Test serializing error result."""
        parser = CommandParser()
        
        json_str = parser.serialize_command_result(success=False, error="Something failed")
        data = json.loads(json_str)
        
        assert not data["success"]
        assert data["error"] == "Something failed"
    
    def test_serialize_with_version(self):
        """Test serializing with version."""
        parser = CommandParser()
        
        json_str = parser.serialize_command_result(success=True, value="v", version=5)
        data = json.loads(json_str)
        
        assert data["version"] == 5
    
    def test_serialize_removes_none_values(self):
        """Test that None values are removed."""
        parser = CommandParser()
        
        json_str = parser.serialize_command_result(success=True, value=None, error=None)
        data = json.loads(json_str)
        
        assert "value" not in data or data["value"] is None
        assert "error" not in data or data["error"] is None


class TestBatchValidation:
    """Test batch command validation."""
    
    def test_validate_batch_all_valid(self):
        """Test validating batch of all valid commands."""
        parser = CommandParser()
        
        commands = [
            {"operation": "SET", "key": "k1", "value": "v1"},
            {"operation": "GET", "key": "k2"},
            {"operation": "DELETE", "key": "k3"},
        ]
        
        results = parser.validate_batch(commands)
        
        assert len(results) == 3
        assert all(is_valid for is_valid, _ in results)
    
    def test_validate_batch_mixed(self):
        """Test validating batch with mixed valid/invalid."""
        parser = CommandParser()
        
        commands = [
            {"operation": "SET", "key": "k1", "value": "v1"},  # Valid
            {"operation": "GET"},  # Invalid (no key)
            {"operation": "DELETE", "key": "k3"},  # Valid
        ]
        
        results = parser.validate_batch(commands)
        
        assert len(results) == 3
        assert results[0][0]  # First valid
        assert not results[1][0]  # Second invalid
        assert results[2][0]  # Third valid


class TestStatistics:
    """Test parser statistics tracking."""
    
    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        parser = CommandParser()
        
        # Successful parse and validate
        parser.parse_and_validate('{"operation": "SET", "key": "k1", "value": "v1"}')
        
        # Failed parse
        try:
            parser.parse_and_validate('invalid')
        except:
            pass
        
        stats = parser.get_statistics()
        
        assert stats["total_parsed"] == 2
        assert stats["parse_errors"] >= 1


class TestCommandNormalizer:
    """Test command normalization."""
    
    def test_normalize_operation_uppercase(self):
        """Test that operation is normalized to uppercase."""
        data = {"operation": "set", "key": "k1", "value": "v1"}
        
        normalized = CommandNormalizer.normalize(data)
        
        assert normalized["operation"] == "SET"
    
    def test_normalize_key_whitespace(self):
        """Test that key whitespace is trimmed."""
        data = {"operation": "SET", "key": "  k1  ", "value": "v1"}
        
        normalized = CommandNormalizer.normalize(data)
        
        assert normalized["key"] == "k1"
    
    def test_normalize_value_preserved(self):
        """Test that value content is preserved."""
        data = {"operation": "SET", "key": "k1", "value": "  v1  "}
        
        normalized = CommandNormalizer.normalize(data)
        
        # Value with spaces is preserved (may be intentional)
        assert "v1" in normalized["value"]
    
    def test_normalize_empty_string_preserved(self):
        """Test that empty strings are preserved."""
        data = {"operation": "SET", "key": "", "value": "v1"}
        
        normalized = CommandNormalizer.normalize(data)
        
        assert normalized["key"] == ""


class TestCommandValidator:
    """Test advanced command validation."""
    
    def test_validator_valid_command(self):
        """Test validation of valid command."""
        validator = CommandValidator()
        
        command = {"operation": "SET", "key": "k1", "value": "v1"}
        is_valid, errors = validator.validate_with_context(command)
        
        assert is_valid
        assert len(errors) == 0
    
    def test_validator_invalid_set_no_key(self):
        """Test validation of SET without key."""
        validator = CommandValidator()
        
        command = {"operation": "SET", "value": "v1"}
        is_valid, errors = validator.validate_with_context(command)
        
        assert not is_valid
        assert len(errors) > 0
    
    def test_validator_strict_mode(self):
        """Test validator in strict mode."""
        validator = CommandValidator(strict_mode=True)
        
        command = {"operation": "SET", "key": "", "value": "v1"}
        is_valid, errors = validator.validate_with_context(command)
        
        assert not is_valid
    
    def test_validator_cas_with_expected_value(self):
        """Test CAS validation with expected value."""
        validator = CommandValidator()
        
        command = {"operation": "CAS", "key": "k1", "value": "new", "expected_value": "old"}
        is_valid, errors = validator.validate_with_context(command)
        
        assert is_valid
    
    def test_validator_scan_with_prefix(self):
        """Test SCAN validation with prefix."""
        validator = CommandValidator()
        
        command = {"operation": "SCAN", "prefix": "user:"}
        is_valid, errors = validator.validate_with_context(command)
        
        assert is_valid


class TestComplexScenarios:
    """Test complex parsing scenarios."""
    
    def test_parse_command_with_special_characters(self):
        """Test parsing command with special characters in value."""
        parser = CommandParser()
        
        json_str = '{"operation": "SET", "key": "k1", "value": "value with \\n newline and \\"quotes\\""}'
        success, data, error = parser.parse_and_validate(json_str)
        
        assert success
        assert '"' in data["value"]
    
    def test_parse_command_with_unicode(self):
        """Test parsing command with unicode characters."""
        parser = CommandParser()
        
        json_str = '{"operation": "SET", "key": "k1", "value": "Hello 世界 🌍"}'
        success, data, error = parser.parse_and_validate(json_str)
        
        assert success
        assert "世界" in data["value"]
    
    def test_parse_large_batch(self):
        """Test parsing large batch of commands."""
        parser = CommandParser()
        
        commands = [
            {"operation": "SET", "key": f"k{i}", "value": f"v{i}"}
            for i in range(100)
        ]
        
        results = parser.validate_batch(commands)
        
        assert len(results) == 100
        assert all(is_valid for is_valid, _ in results)
    
    def test_validation_preserves_command_dict(self):
        """Test that validation doesn't modify original command."""
        parser = CommandParser()
        
        original = {"operation": "SET", "key": "k1", "value": "v1"}
        data_copy = dict(original)
        
        is_valid, error = parser.validate_command_dict(original)
        
        assert original == data_copy


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_null_key_for_operations_requiring_key(self):
        """Test null key for operations that require key."""
        parser = CommandParser()
        
        data = {"operation": "GET", "key": None}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
    
    def test_null_value_for_set(self):
        """Test null value for SET."""
        parser = CommandParser()
        
        data = {"operation": "SET", "key": "k1", "value": None}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
    
    def test_cas_with_null_expected_value(self):
        """Test CAS with null expected value (matching null/missing keys)."""
        parser = CommandParser()
        
        data = {"operation": "CAS", "key": "k1", "value": "v1", "expected_value": None}
        is_valid, error = parser.validate_command_dict(data)
        
        # Should be valid - null expected value means "key should not exist"
        assert is_valid
    
    def test_very_long_key(self):
        """Test handling of very long key."""
        parser = CommandParser()
        
        long_key = "k" * 2000
        data = {"operation": "SET", "key": long_key, "value": "v1"}
        is_valid, error = parser.validate_command_dict(data)
        
        assert not is_valid
        assert "exceeds maximum length" in error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
