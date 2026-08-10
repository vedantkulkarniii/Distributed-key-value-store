"""
Comprehensive test suite for command parser.

Tests:
- JSON parsing and validation
- Command operation support (SET, GET, DELETE, SCAN, CAS)
- Batch processing
- Error handling
- Statistics tracking
"""

import pytest
import json
from src.raft.command_parser import (
    CommandParser,
    ParseError,
    ValidationError,
    CommandNormalizer,
    CommandValidator
)


class TestCommandParserBasics:
    """Test basic parser operations."""
    
    @pytest.fixture
    def parser(self):
        return CommandParser()
    
    def test_parser_initialization(self, parser):
        """Test parser initialization."""
        assert parser is not None
        stats = parser.get_statistics()
        assert stats["total_parsed"] == 0
    
    def test_parse_simple_json(self, parser):
        """Test parsing simple JSON."""
        json_str = '{"operation": "SET", "key": "x", "value": "10"}'
        result = parser.parse_json(json_str)
        
        assert result is not None
        assert result["operation"] == "SET"
        assert result["key"] == "x"
        assert result["value"] == "10"
    
    def test_parse_invalid_json(self, parser):
        """Test parsing invalid JSON."""
        json_str = '{"operation": "SET"'  # Invalid JSON
        
        with pytest.raises(ParseError):
            parser.parse_json(json_str)


class TestCommandValidation:
    """Test command validation."""
    
    @pytest.fixture
    def parser(self):
        return CommandParser()
    
    def test_validate_set_command(self, parser):
        """Test validating SET command."""
        cmd = {"operation": "SET", "key": "x", "value": "10"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is True
        assert error is None
    
    def test_validate_get_command(self, parser):
        """Test validating GET command."""
        cmd = {"operation": "GET", "key": "x"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is True
        assert error is None
    
    def test_validate_delete_command(self, parser):
        """Test validating DELETE command."""
        cmd = {"operation": "DELETE", "key": "x"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is True
        assert error is None
    
    def test_validate_scan_command(self, parser):
        """Test validating SCAN command."""
        cmd = {"operation": "SCAN"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is True
        assert error is None
    
    def test_validate_cas_command(self, parser):
        """Test validating CAS command."""
        cmd = {"operation": "CAS", "key": "x", "value": "20"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is True
        assert error is None
    
    def test_validate_missing_operation(self, parser):
        """Test validation with missing operation."""
        cmd = {"key": "x", "value": "10"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is False
        assert "operation" in error.lower()
    
    def test_validate_set_missing_key(self, parser):
        """Test SET validation missing key."""
        cmd = {"operation": "SET", "value": "10"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is False
    
    def test_validate_get_missing_key(self, parser):
        """Test GET validation missing key."""
        cmd = {"operation": "GET"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is False
    
    def test_validate_unknown_operation(self, parser):
        """Test validation with unknown operation."""
        cmd = {"operation": "UNKNOWN", "key": "x"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        assert is_valid is False
        assert "unknown" in error.lower()


class TestParseAndValidate:
    """Test combined parse and validate."""
    
    @pytest.fixture
    def parser(self):
        return CommandParser()
    
    def test_parse_and_validate_valid(self, parser):
        """Test parse and validate with valid command."""
        json_str = '{"operation": "SET", "key": "x", "value": "10"}'
        is_valid, cmd, error = parser.parse_and_validate(json_str)
        
        assert is_valid is True
        assert cmd is not None
        assert error is None
        assert cmd["operation"] == "SET"
    
    def test_parse_and_validate_invalid_json(self, parser):
        """Test parse and validate with invalid JSON."""
        json_str = '{"operation": "SET"'
        is_valid, cmd, error = parser.parse_and_validate(json_str)
        
        assert is_valid is False
        assert cmd is None
        assert error is not None
    
    def test_parse_and_validate_invalid_command(self, parser):
        """Test parse and validate with invalid command."""
        json_str = '{"operation": "SET"}'  # Missing key
        is_valid, cmd, error = parser.parse_and_validate(json_str)
        
        assert is_valid is False
        assert cmd is None
        assert error is not None


class TestSerializeResult:
    """Test result serialization."""
    
    @pytest.fixture
    def parser(self):
        return CommandParser()
    
    def test_serialize_success_result(self, parser):
        """Test serializing success result."""
        serialized = parser.serialize_command_result(success=True, value={"key": "x", "value": 10})
        
        assert serialized is not None
        parsed = json.loads(serialized)
        assert parsed["success"] is True
    
    def test_serialize_error_result(self, parser):
        """Test serializing error result."""
        serialized = parser.serialize_command_result(success=False, error="Key not found")
        
        assert serialized is not None
        parsed = json.loads(serialized)
        assert parsed["success"] is False
        assert "Key not found" in parsed["error"]


class TestBatchProcessing:
    """Test batch command processing."""
    
    @pytest.fixture
    def parser(self):
        return CommandParser()
    
    def test_validate_batch_valid(self, parser):
        """Test validating batch of valid commands."""
        commands = [
            {"operation": "SET", "key": "a", "value": "1"},
            {"operation": "GET", "key": "a"},
            {"operation": "DELETE", "key": "a"}
        ]
        
        results = parser.validate_batch(commands)
        
        assert len(results) == 3
        for is_valid, error in results:
            assert is_valid is True
            assert error is None
    
    def test_validate_batch_mixed(self, parser):
        """Test validating batch with mixed valid/invalid."""
        commands = [
            {"operation": "SET", "key": "a", "value": "1"},
            {"operation": "GET"},  # Missing key
            {"operation": "DELETE", "key": "a"}
        ]
        
        results = parser.validate_batch(commands)
        
        assert len(results) == 3
        assert results[0][0] is True  # Valid
        assert results[1][0] is False  # Invalid
        assert results[2][0] is True  # Valid
    
    def test_validate_empty_batch(self, parser):
        """Test validating empty batch."""
        commands = []
        results = parser.validate_batch(commands)
        
        assert len(results) == 0


class TestStatistics:
    """Test statistics tracking."""
    
    @pytest.fixture
    def parser(self):
        return CommandParser()
    
    def test_statistics_initial(self, parser):
        """Test initial statistics."""
        stats = parser.get_statistics()
        
        assert stats["total_parsed"] == 0
        assert stats["parse_errors"] == 0
        assert stats["validation_errors"] == 0
    
    def test_statistics_after_parsing(self, parser):
        """Test statistics after parsing commands."""
        parser.parse_and_validate('{"operation": "SET", "key": "x", "value": "10"}')
        parser.parse_and_validate('{"operation": "invalid"')
        
        stats = parser.get_statistics()
        
        assert stats["total_parsed"] >= 1


class TestCommandNormalizer:
    """Test command normalization."""
    
    def test_normalize_empty_dict(self):
        """Test normalizing empty dict."""
        result = CommandNormalizer.normalize({})
        assert isinstance(result, dict)
    
    def test_normalize_set_command(self):
        """Test normalizing SET command."""
        cmd = {"operation": "set", "key": "x", "value": "10"}
        result = CommandNormalizer.normalize(cmd)
        
        # Operation should be uppercase
        assert result["operation"] == "SET"
        assert result["key"] == "x"
        assert result["value"] == "10"
    
    def test_normalize_with_whitespace(self):
        """Test normalization trims whitespace."""
        cmd = {"operation": "SET", "key": "  x  ", "value": "  data  "}
        result = CommandNormalizer.normalize(cmd)
        
        # Whitespace should be trimmed
        assert result["key"] == "x"
        assert result["value"] == "data"


class TestCommandValidator:
    """Test command validator."""
    
    def test_validator_initialization(self):
        """Test validator initialization."""
        validator = CommandValidator(strict_mode=False)
        assert validator is not None
    
    def test_validator_strict_mode(self):
        """Test validator strict mode."""
        validator = CommandValidator(strict_mode=True)
        assert validator is not None
    
    def test_validate_with_context(self):
        """Test validation with context."""
        validator = CommandValidator()
        cmd = {"operation": "SET", "key": "x", "value": "10"}
        
        is_valid, errors = validator.validate_with_context(cmd)
        assert is_valid is True
        assert len(errors) == 0


class TestComplexScenarios:
    """Test complex usage scenarios."""
    
    @pytest.fixture
    def parser(self):
        return CommandParser()
    
    def test_rapid_parsing(self, parser):
        """Test rapid parsing of commands."""
        for i in range(100):
            json_str = f'{{"operation": "SET", "key": "k{i}", "value": "{i}"}}'
            is_valid, cmd, error = parser.parse_and_validate(json_str)
            assert is_valid is True
    
    def test_large_value_parsing(self, parser):
        """Test parsing with large values."""
        large_value = "x" * 100000  # 100KB
        cmd = {"operation": "SET", "key": "x", "value": large_value}
        
        json_str = json.dumps(cmd)
        is_valid, parsed_cmd, error = parser.parse_and_validate(json_str)
        
        assert is_valid is True
        assert len(parsed_cmd["value"]) == 100000
    
    def test_special_characters_in_key(self, parser):
        """Test special characters in keys."""
        special_key = "user:123:profile:name"
        cmd = {"operation": "SET", "key": special_key, "value": "test"}
        
        json_str = json.dumps(cmd)
        is_valid, parsed_cmd, error = parser.parse_and_validate(json_str)
        
        assert is_valid is True
        assert parsed_cmd["key"] == special_key
    
    def test_nested_json_values(self, parser):
        """Test storing JSON as string values."""
        nested_value = json.dumps({"name": "alice", "age": 30, "tags": ["admin", "user"]})
        cmd = {"operation": "SET", "key": "user:1", "value": nested_value}
        
        json_str = json.dumps(cmd)
        is_valid, parsed_cmd, error = parser.parse_and_validate(json_str)
        
        assert is_valid is True
        assert isinstance(parsed_cmd["value"], str)


class TestEdgeCases:
    """Test edge cases."""
    
    @pytest.fixture
    def parser(self):
        return CommandParser()
    
    def test_null_key_or_value(self, parser):
        """Test handling null values."""
        cmd = {"operation": "SET", "key": None, "value": "data"}
        is_valid, _ = parser.validate_command_dict(cmd)
        
        # Null key should be invalid for SET
        assert is_valid is False
    
    def test_empty_string_value(self, parser):
        """Test empty string value."""
        cmd = {"operation": "SET", "key": "x", "value": ""}
        is_valid, error = parser.validate_command_dict(cmd)
        
        # Empty string should be valid
        assert is_valid is True
    
    def test_very_long_key_validation(self, parser):
        """Test very long key."""
        cmd = {"operation": "SET", "key": "x" * 2000, "value": "data"}
        is_valid, error = parser.validate_command_dict(cmd)
        
        # Should fail due to length limit
        assert is_valid is False
        assert "exceed" in error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
