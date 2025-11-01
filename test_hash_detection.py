"""
Test hash-based paper detection system.

This test verifies:
1. Drive File ID extraction from various URL formats
2. Content hash generation
3. Row identifier extraction
4. Detection of unprocessed papers regardless of position
"""

import pandas as pd
from utils.row_identifier import (
    extract_drive_file_id,
    generate_content_hash,
    extract_row_identifier,
    get_unprocessed_row_indices
)
from utils.deduplication import generate_content_hash as dedup_generate_content_hash


def test_drive_file_id_extraction():
    """Test extraction of Drive File IDs from various URL formats."""
    print("Testing Drive File ID extraction...")
    
    test_cases = [
        ("https://drive.google.com/file/d/1a2b3c4d5e6f/view", "1a2b3c4d5e6f"),
        ("https://drive.google.com/open?id=abc123xyz", "abc123xyz"),
        ("https://docs.google.com/document/d/doc_id_here/edit", "doc_id_here"),
        ("https://drive.google.com/file/d/LONG-FILE-ID-WITH-DASHES/view?usp=sharing", "LONG-FILE-ID-WITH-DASHES"),
        ("", None),
        (None, None),
    ]
    
    passed = 0
    for url, expected in test_cases:
        result = extract_drive_file_id(url)
        if result == expected:
            print(f"  ✓ {url[:50]+'...' if url and len(url) > 50 else url} → {result}")
            passed += 1
        else:
            print(f"  ✗ {url} → Expected {expected}, got {result}")
    
    print(f"  Result: {passed}/{len(test_cases)} passed\n")
    return passed == len(test_cases)


def test_content_hash_generation():
    """Test content hash generation from metadata."""
    print("Testing content hash generation...")
    
    # Same content should produce same hash (title + authors only)
    hash1 = generate_content_hash(
        title="Neural Networks in AI",
        authors="Smith et al"
    )
    
    hash2 = generate_content_hash(
        title="Neural Networks in AI",
        authors="Smith et al"
    )
    
    if hash1 == hash2:
        print(f"  ✓ Same content produces same hash: {hash1}")
    else:
        print(f"  ✗ Hash mismatch: {hash1} != {hash2}")
        return False
    
    # Different content should produce different hash
    hash3 = generate_content_hash(
        title="Different Paper",
        authors="Jones et al"
    )
    
    if hash1 != hash3:
        print(f"  ✓ Different content produces different hash: {hash3}")
    else:
        print(f"  ✗ Different content produced same hash!")
        return False
    
    # Empty fields should still generate hash
    hash4 = generate_content_hash(title="Just a title")
    if hash4:
        print(f"  ✓ Partial content generates hash: {hash4}")
    else:
        print(f"  ✗ Failed to generate hash from partial content")
        return False
    
    print(f"  Result: All hash tests passed\n")
    return True


def test_row_identifier_extraction():
    """Test identifier extraction from sheet rows."""
    print("Testing row identifier extraction...")
    
    # Create test data
    test_data = {
        'Title': ['Paper A', 'Paper B', 'Paper C', '', 'Paper E', ''],
        'Authors': ['Smith et al', 'Jones et al', 'Brown et al', 'Wilson et al', 'Davis et al', ''],
        'Year': ['2024', '2023', '2024', '2022', '2024', '2023'],
        'PDF Link': [
            'https://drive.google.com/file/d/FILE_ID_1/view',
            '',  # No drive link - should use content hash
            'https://drive.google.com/file/d/FILE_ID_3/view',
            '',  # Has authors, no title - should use content hash
            'https://drive.google.com/file/d/FILE_ID_5/view',
            ''   # Truly empty row (no title, no authors)
        ],
        'URL': ['url1', 'url2', 'url3', '', 'url5', '']
    }
    
    df = pd.DataFrame(test_data)
    
    column_mappings = {
        'title': 'Title',
        'authors': 'Authors',
        'year': 'Year',
        'drive_link': 'PDF Link',
        'url': 'URL'
    }
    
    passed = 0
    total = 0
    
    # Test row 0: Should extract Drive File ID
    total += 1
    id0 = extract_row_identifier(df.iloc[0], column_mappings)
    if id0 == 'FILE_ID_1':
        print(f"  ✓ Row 0: Extracted Drive File ID: {id0}")
        passed += 1
    else:
        print(f"  ✗ Row 0: Expected FILE_ID_1, got {id0}")
    
    # Test row 1: Should generate content hash (no drive link)
    total += 1
    id1 = extract_row_identifier(df.iloc[1], column_mappings)
    if id1 and id1 != 'FILE_ID_1':  # Should be different from FILE_ID_1
        print(f"  ✓ Row 1: Generated content hash: {id1}")
        passed += 1
    else:
        print(f"  ✗ Row 1: Failed to generate content hash")
    
    # Test row 3: Has authors but no title - should still generate hash
    total += 1
    id3 = extract_row_identifier(df.iloc[3], column_mappings)
    if id3 and id3 not in ['FILE_ID_1', 'FILE_ID_3']:
        print(f"  ✓ Row 3: Generated hash from authors only: {id3[:16]}...")
        passed += 1
    else:
        print(f"  ✗ Row 3: Expected content hash, got {id3}")
    
    # Test row 5: Truly empty row (no title, no authors) should return None
    total += 1
    id5 = extract_row_identifier(df.iloc[5], column_mappings)
    if id5 is None:
        print(f"  ✓ Row 5: Empty row returns None")
        passed += 1
    else:
        print(f"  ✗ Row 5: Expected None for empty row, got {id5}")
    
    print(f"  Result: {passed}/{total} tests passed\n")
    return passed == total


def test_unprocessed_detection():
    """Test detection of unprocessed papers."""
    print("Testing unprocessed paper detection...")
    
    # Create test sheet data with papers at various positions
    test_data = {
        'Title': [
            'Paper 1 (processed)',
            'Paper 2 (new)',
            'Paper 3 (processed)',
            'Paper 4 (new)',
            'Paper 5 (processed)'
        ],
        'Authors': ['Author A', 'Author B', 'Author C', 'Author D', 'Author E'],
        'Year': ['2024', '2024', '2024', '2024', '2024'],
        'PDF Link': [
            'https://drive.google.com/file/d/ID_1/view',
            'https://drive.google.com/file/d/ID_2/view',
            'https://drive.google.com/file/d/ID_3/view',
            'https://drive.google.com/file/d/ID_4/view',
            'https://drive.google.com/file/d/ID_5/view'
        ]
    }
    
    df = pd.DataFrame(test_data)
    
    column_mappings = {
        'title': 'Title',
        'authors': 'Authors',
        'year': 'Year',
        'drive_link': 'PDF Link'
    }
    
    # Simulate processed papers (rows 0, 2, 4)
    processed_ids = {'ID_1', 'ID_3', 'ID_5'}
    
    # Find unprocessed papers
    unprocessed = get_unprocessed_row_indices(
        sheet_data=df,
        column_mappings=column_mappings,
        processed_identifiers=processed_ids,
        max_papers=None
    )
    
    # Should detect rows 1 and 3 (ID_2 and ID_4)
    expected = [1, 3]
    if unprocessed == expected:
        print(f"  ✓ Detected unprocessed papers at rows: {unprocessed}")
        print(f"  ✓ Successfully detected mid-sheet insertions")
    else:
        print(f"  ✗ Expected rows {expected}, got {unprocessed}")
        return False
    
    # Test max_papers limit
    limited = get_unprocessed_row_indices(
        sheet_data=df,
        column_mappings=column_mappings,
        processed_identifiers=processed_ids,
        max_papers=1
    )
    
    if len(limited) == 1 and limited[0] == 1:
        print(f"  ✓ max_papers limit working: returned {len(limited)} paper")
    else:
        print(f"  ✗ max_papers limit failed: expected 1 paper, got {len(limited)}")
        return False
    
    print(f"  Result: All detection tests passed\n")
    return True


def test_backward_compatibility():
    """Test that hash function matches existing deduplication system."""
    print("Testing backward compatibility with deduplication.py...")
    
    test_cases = [
        ("Neural Networks in AI", "Smith et al"),
        ("Machine Learning", "Jones et al"),
        ("Deep Learning Survey", "Brown, Davis, Wilson"),
        ("", "Author Only"),  # Empty title
        ("Title Only", ""),   # Empty authors
        ("", ""),            # Both empty
    ]
    
    passed = 0
    for title, authors in test_cases:
        # Generate hash using new row_identifier module
        new_hash = generate_content_hash(title=title, authors=authors)
        
        # Generate hash using existing deduplication module
        dedup_hash = dedup_generate_content_hash(paper_title=title, authors=authors)
        
        if new_hash == dedup_hash:
            print(f"  ✓ Match: '{title[:30]}...' + '{authors[:20]}...'")
            passed += 1
        else:
            print(f"  ✗ Mismatch for '{title}' + '{authors}':")
            print(f"    New:   {new_hash}")
            print(f"    Dedup: {dedup_hash}")
    
    print(f"  Result: {passed}/{len(test_cases)} test cases matched\n")
    return passed == len(test_cases)


def run_all_tests():
    """Run all tests."""
    print("="*60)
    print("HASH-BASED PAPER DETECTION TEST SUITE")
    print("="*60 + "\n")
    
    results = []
    
    # Run tests
    results.append(("Drive File ID Extraction", test_drive_file_id_extraction()))
    results.append(("Content Hash Generation", test_content_hash_generation()))
    results.append(("Backward Compatibility", test_backward_compatibility()))
    results.append(("Row Identifier Extraction", test_row_identifier_extraction()))
    results.append(("Unprocessed Paper Detection", test_unprocessed_detection()))
    
    # Summary
    print("="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nOverall: {passed}/{total} test suites passed")
    print("="*60)
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
