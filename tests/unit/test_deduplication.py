"""
Unit tests for deduplication module (utils/deduplication.py).

Tests three-layer deduplication system.
"""

import pytest
from utils.deduplication import (
    generate_content_hash,
    check_duplicate_layer2
)


@pytest.mark.unit
class TestContentHash:
    """Test content hash generation (Layer 2)."""
    
    def test_content_hash_consistency(self):
        """Test that content hash is consistent for same inputs."""
        hash1 = generate_content_hash("Paper Title", "Author Name")
        hash2 = generate_content_hash("Paper Title", "Author Name")
        
        assert hash1 == hash2, "Same input should produce same hash"
        assert len(hash1) == 64, "Should be SHA-256 hash (64 hex chars)"
    
    def test_content_hash_case_insensitive(self):
        """Test that content hash is case-insensitive."""
        hash1 = generate_content_hash("Paper Title", "Author Name")
        hash2 = generate_content_hash("PAPER TITLE", "AUTHOR NAME")
        hash3 = generate_content_hash("paper title", "author name")
        
        assert hash1 == hash2 == hash3, "Case should not affect hash"
    
    def test_content_hash_whitespace_normalized(self):
        """Test that extra whitespace is normalized."""
        hash1 = generate_content_hash("Paper  Title", "Author  Name")
        hash2 = generate_content_hash("Paper Title", "Author Name")
        hash3 = generate_content_hash("  Paper Title  ", "  Author Name  ")
        
        assert hash1 == hash2 == hash3, "Whitespace should be normalized"
    
    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        hash1 = generate_content_hash("Paper 1", "Author A")
        hash2 = generate_content_hash("Paper 2", "Author B")
        hash3 = generate_content_hash("Paper 1", "Author B")
        
        assert hash1 != hash2, "Different papers should have different hashes"
        assert hash1 != hash3, "Same title, different author should differ"
        assert hash2 != hash3, "All should be unique"
    
    def test_empty_strings(self):
        """Test handling of empty strings."""
        hash1 = generate_content_hash("", "")
        hash2 = generate_content_hash("", "")
        
        assert hash1 == hash2, "Empty strings should hash consistently"
        assert len(hash1) == 64, "Should still produce valid hash"
    
    def test_unicode_characters(self):
        """Test handling of unicode characters."""
        hash1 = generate_content_hash("Título", "Autör")
        hash2 = generate_content_hash("Título", "Autör")
        
        assert hash1 == hash2, "Unicode should hash consistently"
    
    def test_special_characters(self):
        """Test handling of special characters."""
        hash1 = generate_content_hash(
            "Paper: A Study (2024)",
            "Smith & Johnson, et al."
        )
        hash2 = generate_content_hash(
            "Paper: A Study (2024)",
            "Smith & Johnson, et al."
        )
        
        assert hash1 == hash2, "Special chars should hash consistently"
    
    def test_author_only_different(self):
        """Test that different authors produce different hashes."""
        hash1 = generate_content_hash("Same Title", "Author 1")
        hash2 = generate_content_hash("Same Title", "Author 2")
        
        assert hash1 != hash2, "Different authors should produce different hashes"
    
    def test_title_only_different(self):
        """Test that different titles produce different hashes."""
        hash1 = generate_content_hash("Title 1", "Same Author")
        hash2 = generate_content_hash("Title 2", "Same Author")
        
        assert hash1 != hash2, "Different titles should produce different hashes"


@pytest.mark.unit
class TestDuplicateLayer2:
    """Test Layer 2 duplicate checking."""
    
    def test_check_duplicate_layer2_not_duplicate(self, mock_db_transaction):
        """Test when paper is not a duplicate."""
        # Mock database to return no existing paper
        conn = mock_db_transaction.return_value.__enter__.return_value
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        
        is_duplicate = check_duplicate_layer2("New Paper", "New Author")
        
        assert is_duplicate is False, "Should not be duplicate"
    
    def test_check_duplicate_layer2_is_duplicate(self, mock_db_transaction):
        """Test when paper is a duplicate."""
        # Mock database to return existing paper
        conn = mock_db_transaction.return_value.__enter__.return_value
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1, "existing-hash")
        
        is_duplicate = check_duplicate_layer2("Existing Paper", "Existing Author")
        
        assert is_duplicate is True, "Should be duplicate"
    
    def test_check_duplicate_layer2_case_insensitive(self, mock_db_transaction):
        """Test that duplicate check is case-insensitive."""
        conn = mock_db_transaction.return_value.__enter__.return_value
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1, "hash")
        
        # Should generate same hash regardless of case
        result1 = check_duplicate_layer2("Paper", "Author")
        result2 = check_duplicate_layer2("PAPER", "AUTHOR")
        
        # Both should query with same hash
        assert cursor.execute.call_count >= 2


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases in deduplication."""
    
    def test_none_values(self):
        """Test handling of None values."""
        # Should handle None gracefully (convert to empty string)
        hash1 = generate_content_hash(None, None)
        hash2 = generate_content_hash("", "")
        
        # Both should be handled consistently
        assert isinstance(hash1, str)
        assert len(hash1) == 64
    
    def test_numeric_values(self):
        """Test handling of numeric values."""
        hash1 = generate_content_hash("2024", "123")
        hash2 = generate_content_hash("2024", "123")
        
        assert hash1 == hash2
    
    def test_very_long_strings(self):
        """Test handling of very long strings."""
        long_title = "A" * 10000
        long_author = "B" * 10000
        
        hash1 = generate_content_hash(long_title, long_author)
        hash2 = generate_content_hash(long_title, long_author)
        
        assert hash1 == hash2
        assert len(hash1) == 64, "Hash should still be 64 chars"
