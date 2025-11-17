# Deduplication Records Created Despite Incomplete Processing

## Problem Summary

Papers are being marked as "processed" in the deduplication system even though their vectors never made it to Pinecone. This causes them to be incorrectly skipped as "duplicates" on subsequent processing runs.

## Root Cause

**Celery Task Timeouts (3 hours)** are killing long-running jobs before all papers finish processing:

1. Job starts processing 200 papers
2. Successfully processes papers 1-38 (✅ Pinecone, ✅ Chunks, ✅ Dedup)
3. **Timeout occurs at 3 hours**
4. Papers 39-200 are in various incomplete states:
   - Some have chunks saved but no Pinecone vectors
   - Some have dedup records but processing never finished
   - Some have both chunks AND dedup records but no Pinecone vectors

**Why this happens:**
- Each paper's processing creates independent database transactions
- When `save_chunks()` commits, chunks persist
- When `record_or_update_paper()` commits, dedup record persists
- But Pinecone upload might not have completed yet
- Celery timeout kills the task, leaving inconsistent state

## Immediate Solution

### Step 1: Clean Up Orphaned Records

Use the provided cleanup scripts to remove dedup records for incomplete batches:

```bash
# For Nov 13 batch (Product 7)
python delete_dedup_by_daterange.py --product-id 7 \
    --start "2025-11-13 11:35:00" \
    --end "2025-11-13 11:45:00" \
    --execute

# For Nov 16 batch (Product 7)  
python delete_dedup_by_daterange.py --product-id 7 \
    --start "2025-11-16 04:00:00" \
    --end "2025-11-16 05:00:00" \
    --execute
```

**Important:** Run these in your **production environment**, not development.

### Step 2: Verify Before Running

Always run with `--dry-run` first to see what will be deleted:

```bash
python delete_dedup_by_daterange.py --product-id 7 \
    --start "2025-11-13 11:35:00" \
    --end "2025-11-13 11:45:00" \
    --dry-run
```

### Step 3: Reprocess Papers

After cleanup, run your processing job again. Those papers will now be treated as new.

## Prevention Strategies

### Option 1: Reduce Batch Size
Process fewer papers per job to avoid timeouts:
- Current: 200 papers → 3+ hours
- Recommended: 50 papers per job → ~45 minutes

### Option 2: Increase Timeout
Modify Celery configuration:
```python
# In celeryconfig.py
task_time_limit = 21600  # 6 hours instead of 3
```

### Option 3: Add Checkpointing
Modify batch processing to save progress periodically and resume from last checkpoint.

### Option 4: Verify Pinecone Before Dedup Record
Add verification step before creating dedup record:
```python
# After Pinecone upload
if not verify_vectors_in_pinecone(file_id, namespace):
    raise Exception("Pinecone upload verification failed")
# Only then create dedup record
record_or_update_paper(...)
```

## Available Cleanup Tools

### 1. `cleanup_orphaned_dedup_records.py`
Removes records with no chunks (true orphans):
```bash
python cleanup_orphaned_dedup_records.py --product-id 7 --execute
```

### 2. `delete_dedup_by_daterange.py`
Surgical removal by date range:
```bash
python delete_dedup_by_daterange.py --product-id 7 \
    --start "YYYY-MM-DD HH:MM:SS" \
    --end "YYYY-MM-DD HH:MM:SS" \
    --execute
```

### 3. `backfill_processed_papers.py`
**DO NOT USE for this issue.** This script is for the opposite problem (completed papers missing dedup records).

## Technical Details

**Why separate transactions?**
- Each `get_db_transaction()` context automatically commits when it exits
- `save_chunks()` → commits transaction 1
- `record_or_update_paper()` → commits transaction 2
- If timeout happens between them, transaction 1 persists but transaction 2 might not complete

**Why can't we rollback?**
- PostgreSQL transactions can't span across different context managers
- Even if we used one big transaction, Celery timeout kills the Python process
- Killed processes can't run rollback code

**The real issue:**
Cross-system consistency (PostgreSQL + Pinecone) is hard to maintain when timeouts occur.

## Monitoring for Future Issues

Check for orphaned records periodically:
```bash
# Run this monthly
python cleanup_orphaned_dedup_records.py --dry-run > orphans_report.txt
```

If you see recurring orphans:
1. Reduce batch size
2. Increase timeout
3. Investigate why processing is so slow

## Questions?

- **Q: Will this delete successfully processed papers?**
  A: No. The date-range script only deletes records created in the specific timeframe you specify.

- **Q: Will I lose parsed data?**
  A: No. Chunks remain in the database. Reprocessing can be faster if parsing is cached.

- **Q: Can I use SQL directly instead?**
  A: Yes, but scripts are safer with dry-run preview.

