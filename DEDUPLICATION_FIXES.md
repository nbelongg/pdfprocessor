# Deduplication Logic Fixes

## Overview

This document describes critical bugs found in the deduplication system and the fixes applied.

**Date:** 2025-11-20
**Branch:** `claude/fix-deduplication-errors-014Fg4mFb4XCmtBgRhdHUEx8`

---

## Critical Bugs Fixed

### 1. Duplicate `record_processed_paper()` Implementations ⚠️ CRITICAL

**Problem:**
- Two different implementations existed with incompatible signatures
- Version A (`utils/deduplication.py`): Did NOT update `source_paper_mapping`
- Version B (`utils/db/documents.py`): DID update `source_paper_mapping`
- Main processing flow (`tasks.py`) used Version A
- Result: **Scheduler repeatedly reprocessed the same papers**

**Root Cause:**
The scheduler's `get_processed_identifiers_for_source()` uses an INNER JOIN with `source_paper_mapping`:
```sql
SELECT DISTINCT p.drive_file_id, p.content_hash
FROM processed_papers p
INNER JOIN source_paper_mapping spm ON p.id = spm.paper_id
WHERE spm.source_id = %s
```

Since Version A didn't create mapping records, the query returned empty results, causing infinite reprocessing.

**Fix:**
- Updated `utils/deduplication.py:record_processed_paper()` to accept optional `source_id` and `row_number`
- Added logic to insert/update `source_paper_mapping` when these parameters are provided
- Updated `tasks.py:_process_single_pdf_logic()` to pass `source_id` and `row_number`
- Updated `tasks.py:process_batch_task()` to pass these values through the call chain

**Files Changed:**
- `utils/deduplication.py` (lines 417-534)
- `tasks.py` (lines 157-168, 366-377, 650-661)

---

### 2. Namespace vs Product ID Scope Mismatch ⚠️ CRITICAL

**Problem:**
- `check_in_processed_papers()` checked by `product_id`
- `check_has_uploaded_chunks()` checked by `namespace`
- A product can have multiple namespaces
- Result: **False State 2 triggers** (reprocess already-successful papers)

**Example Scenario:**
```
Paper processed in namespace="production" for product_id=1
Later checked against namespace="staging" for product_id=1
Result:
  - in_processed=True (same product)
  - has_chunks=False (different namespace)
  - Triggers State 2: "Reprocess (previous upload failed)"
```

**Fix:**
- Updated `check_has_uploaded_chunks()` to accept `product_id` as primary scope
- Added logic to resolve `product_id` from namespace when not provided
- Uses `INNER JOIN` with `processed_papers` for product-scoped chunk checks
- Falls back to namespace-only check for legacy compatibility

**Files Changed:**
- `utils/deduplication.py` (lines 89-163, 377-380)

---

### 3. Orphaned `source_paper_mapping` Records 🔧 MEDIUM

**Problem:**
- `remove_from_processed_papers()` deleted from `processed_papers` table
- Did NOT clean up `source_paper_mapping` records
- Without CASCADE constraint, left orphaned mapping records

**Fix:**
- Updated function to query `paper_id` first
- Deletes from `source_paper_mapping` before deleting from `processed_papers`
- Logs number of mappings cleaned up
- Created migration script to add CASCADE constraint (recommended)

**Files Changed:**
- `utils/deduplication.py` (lines 252-322)
- `migrations/add_cascade_constraints.sql` (new file)

---

### 4. Empty Metadata Hash Collisions 🔧 MEDIUM

**Problem:**
- Papers with whitespace-only title/authors generated same hash
- Multiple empty papers matched each other as duplicates
- Example: `"   "` and `""` both hashed to same value

**Fix:**
- Added validation to `generate_content_hash()` in both files
- Returns empty string if both title AND authors are empty/whitespace
- Updated `check_by_content_hash()` to skip empty hashes
- Prevents false positives while maintaining backward compatibility

**Files Changed:**
- `utils/deduplication.py` (lines 29-55, 336-362)
- `utils/row_identifier.py` (lines 64-106)

---

### 5. Race Condition in Backfill 🔧 LOW

**Problem:**
- Two workers could detect State 3 simultaneously
- Both would attempt backfill for same paper
- Wasted resources with duplicate work (though ON CONFLICT prevented corruption)

**Fix:**
- Added early check for existing record before doing backfill work
- Returns existing `paper_id` if record already created
- Logs when concurrent worker already handled backfill

**Files Changed:**
- `utils/deduplication.py` (lines 177-220)

---

## Database Migration Required

To fully resolve orphaned records issue, apply the CASCADE constraint:

```bash
psql -d your_database -f migrations/add_cascade_constraints.sql
```

**What it does:**
- Adds `ON DELETE CASCADE` to `source_paper_mapping.paper_id` foreign key
- Automatically removes mapping records when parent paper is deleted
- Prevents orphaned records in future

**Verification:**
```sql
SELECT conname, confdeltype
FROM pg_constraint
WHERE conrelid = 'source_paper_mapping'::regclass
  AND conname = 'source_paper_mapping_paper_id_fkey';
```
Expected: `confdeltype = 'c'` (CASCADE)

---

## Testing Recommendations

### Unit Tests
1. Test `record_processed_paper()` creates both tables
2. Test `check_has_uploaded_chunks()` with product_id
3. Test `generate_content_hash()` with whitespace inputs
4. Test `remove_from_processed_papers()` cleanup

### Integration Tests
1. Run scheduler on source with previously processed papers
2. Verify no duplicate reprocessing
3. Test State 2 recovery (failed upload scenario)
4. Test State 3 recovery (timeout scenario)
5. Test cross-namespace isolation

### Manual Verification
```sql
-- Check source_paper_mapping is being populated
SELECT COUNT(*) FROM source_paper_mapping;

-- Check for orphaned mappings (should be 0 after migration)
SELECT COUNT(*) FROM source_paper_mapping spm
LEFT JOIN processed_papers pp ON spm.paper_id = pp.id
WHERE pp.id IS NULL;

-- Verify scheduler finds existing papers
SELECT * FROM processed_papers
WHERE drive_file_id IN (
  SELECT drive_file_id FROM source_paper_mapping
  WHERE source_id = 1
);
```

---

## Impact Assessment

### Before Fixes
- ❌ Scheduler reprocessed same papers indefinitely
- ❌ Cross-namespace papers incorrectly flagged for reprocessing
- ❌ Orphaned database records accumulated
- ❌ Empty papers matched each other as duplicates

### After Fixes
- ✅ Scheduler correctly skips processed papers
- ✅ Product scope correctly isolates namespaces
- ✅ Database cleanup prevents orphaned records
- ✅ Empty papers no longer match each other

---

## Backward Compatibility

All fixes maintain backward compatibility:

1. **Optional parameters** - `source_id` and `row_number` default to `None`
2. **Fallback logic** - Namespace check still works if product_id not available
3. **Hash algorithm unchanged** - Existing hashes remain valid
4. **ON CONFLICT handling** - Existing records not disrupted

---

## Code Review Checklist

- [x] Fix #1: source_paper_mapping populated in main flow
- [x] Fix #2: Consistent product_id scoping
- [x] Fix #3: Orphaned record cleanup
- [x] Fix #4: Whitespace validation
- [x] Fix #5: Race condition protection
- [x] Migration script created
- [x] Documentation complete
- [ ] Unit tests added
- [ ] Integration tests run
- [ ] Manual verification performed
- [ ] Database migration applied

---

## Related Files

### Modified
- `utils/deduplication.py` - Core deduplication logic
- `utils/row_identifier.py` - Hash generation for scheduler
- `tasks.py` - Main processing flow

### Created
- `migrations/add_cascade_constraints.sql` - Database migration
- `DEDUPLICATION_FIXES.md` - This document

---

## Contact

For questions about these fixes, refer to:
- This document
- Code comments in modified files
- Git commit history on branch `claude/fix-deduplication-errors-014Fg4mFb4XCmtBgRhdHUEx8`
