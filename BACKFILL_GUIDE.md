# Backfill Missing `processed_papers` Records

## 🎯 **What This Script Does**

The `backfill_processed_papers.py` script fixes the **102 missing deduplication records** in your production database.

**The Problem:**
- 107 PDFs successfully parsed and uploaded to Pinecone
- Only 5 PDFs have records in `processed_papers` table  
- 102 PDFs are "orphaned" - in Pinecone but missing from deduplication tracking

**The Cause:**
- Celery worker timeout (30 minutes) killed jobs mid-batch
- PDFs were uploaded to Pinecone successfully
- But `record_processed_paper()` never executed before timeout
- Result: Chunks in Pinecone, but no deduplication records

**The Solution:**
- Backfill script creates missing `processed_papers` records
- Uses metadata from `parsed_documents` and `processing_chunks`
- Prevents system from reprocessing these 102 PDFs

---

## 📋 **How the Script Works**

### **Step 1: Find PDFs with Chunks**
Queries `processing_chunks` table to find all file_ids that have chunks (meaning they completed the full pipeline and uploaded to Pinecone).

### **Step 2: Find Existing Records**
Queries `processed_papers` table to see which file_ids already have deduplication records.

### **Step 3: Calculate Missing**
Identifies the gap - which file_ids are in chunks but NOT in processed_papers.

### **Step 4: Backfill Missing Records**
For each missing file_id:
1. Gets metadata from `parsed_documents` (title, authors, etc.)
2. Gets chunk info (namespace, source_id)
3. Generates content_hash for deduplication
4. Calculates metadata_fingerprint
5. Creates `processed_papers` record
6. Creates `source_paper_mapping` record

---

## 🚀 **How to Run on Production**

### **Important: Development vs Production**

Your development database has:
- 5 `parsed_documents`
- 5 `processed_papers`
- 0 `processing_chunks` (no chunks uploaded)
- **Result**: Nothing to backfill ✅

Your production database has:
- 107 `parsed_documents`
- 5 `processed_papers`
- Lots of chunks in Pinecone
- **Result**: ~102 records to backfill 🎯

**Run this script on PRODUCTION, not development!**

---

## 📝 **Step-by-Step Instructions**

### **Step 1: Preview Changes (Dry-Run Mode)**

First, run in dry-run mode to see what would be backfilled WITHOUT making any changes:

```bash
python backfill_processed_papers.py --dry-run
```

**Expected Output:**
```
================================================================================
DRY-RUN MODE: No changes will be made to the database
================================================================================

📊 Step 1: Finding all PDFs that have chunks...
INFO - Found 102 unique file_ids in processing_chunks

📊 Step 2: Finding existing processed_papers records...
INFO - Found 5 existing records in processed_papers

📊 Step 3: Analysis complete!
  Total PDFs with chunks: 102
  Already in processed_papers: 5
  Missing from processed_papers: 97

📊 Step 4: Backfilling 97 missing records...

[1/97] Processing 1m_LmuGJ22dTZOKQm5N8cn-WnG7j2Rhup...
[DRY-RUN] Would create processed_papers record:
  File ID: 1m_LmuGJ22dTZOKQm5N8cn-WnG7j2Rhup
  Title: Chapter Six - Community and Drug Distributor Perceptions...
  Authors: Heather Melanie R. Ames, Meike Zuske...
  Content Hash: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  Namespace: default
  Source: ABCD Google (ID: 5)
  Fingerprint: a7f5c2d8e4b1...

[2/97] Processing 1aEUD4_8N5wgNdzTUJRMsOBlYXDqgLHXA...
...

================================================================================
BACKFILL SUMMARY
================================================================================
Total missing records:     97
Successfully backfilled:   97
Skipped (no metadata):     0
Errors:                    0
================================================================================

💡 This was a DRY-RUN. No changes were made to the database.
   To apply these changes, run with --execute flag:
   python backfill_processed_papers.py --execute
```

**Review the output carefully:**
- ✅ Check that file_ids look correct
- ✅ Verify titles and authors make sense
- ✅ Confirm source names match your data sources
- ⚠️ Note any errors or skipped records

---

### **Step 2: Execute Backfill (Apply Changes)**

If the dry-run looks good, run with `--execute` to actually create the records:

```bash
python backfill_processed_papers.py --execute
```

**Expected Output:**
```
================================================================================
EXECUTE MODE: Changes will be applied to the database
================================================================================

📊 Step 1: Finding all PDFs that have chunks...
INFO - Found 102 unique file_ids in processing_chunks

📊 Step 2: Finding existing processed_papers records...
INFO - Found 5 existing records in processed_papers

📊 Step 3: Analysis complete!
  Total PDFs with chunks: 102
  Already in processed_papers: 5
  Missing from processed_papers: 97

📊 Step 4: Backfilling 97 missing records...

[1/97] Processing 1m_LmuGJ22dTZOKQm5N8cn-WnG7j2Rhup...
✅ Created processed_papers record (ID: 123) for 1m_LmuGJ22dTZOKQm5N8cn-WnG7j2Rhup
✅ Created source_paper_mapping for source 5

[2/97] Processing 1aEUD4_8N5wgNdzTUJRMsOBlYXDqgLHXA...
✅ Created processed_papers record (ID: 124) for 1aEUD4_8N5wgNdzTUJRMsOBlYXDqgLHXA
✅ Created source_paper_mapping for source 7
...

================================================================================
BACKFILL SUMMARY
================================================================================
Total missing records:     97
Successfully backfilled:   97
Skipped (no metadata):     0
Errors:                    0
================================================================================

✅ Backfill completed successfully!
✅ 97 records added to processed_papers table
✅ Your deduplication system is now complete!
```

---

### **Step 3: Verify Results**

After running the backfill, verify in your production database:

#### **Query 1: Check Total Counts**
```sql
SELECT 
    (SELECT COUNT(*) FROM parsed_documents) as parsed_docs,
    (SELECT COUNT(*) FROM processed_papers) as processed_papers,
    (SELECT COUNT(DISTINCT file_id) FROM processing_chunks) as docs_with_chunks;
```

**Expected Result:**
```
 parsed_docs | processed_papers | docs_with_chunks 
-------------+------------------+------------------
         107 |              102 |              102
```

All three should now match (or be very close)!

#### **Query 2: Verify No More Orphans**
```sql
-- Find parsed_documents NOT in processed_papers
SELECT COUNT(*) as orphaned_count
FROM parsed_documents pd
LEFT JOIN processed_papers pp ON pd.file_id = pp.drive_file_id
WHERE pp.drive_file_id IS NULL;
```

**Expected Result:**
```
 orphaned_count 
----------------
              0
```

Should be 0 (or only a few if some had errors)!

#### **Query 3: Check Sample Records**
```sql
-- View some backfilled records
SELECT 
    drive_file_id,
    paper_title,
    authors,
    pinecone_namespace,
    processed_at
FROM processed_papers
ORDER BY processed_at DESC
LIMIT 10;
```

Verify the data looks correct.

---

## ⚠️ **Important Notes**

### **Safety Features:**
- ✅ **Idempotent**: Safe to run multiple times (uses `ON CONFLICT DO NOTHING`)
- ✅ **Dry-run default**: Won't make changes unless you use `--execute`
- ✅ **Non-destructive**: Only adds records, never deletes
- ✅ **Transaction-safe**: Uses database transactions, rolls back on errors

### **What Gets Backfilled:**
- ✅ `processed_papers` records with proper deduplication data
- ✅ `source_paper_mapping` records linking papers to sources
- ✅ Metadata fingerprints for change detection
- ✅ Content hashes for deduplication

### **What Won't Be Backfilled:**
- PDFs that don't have chunks (never completed processing)
- PDFs missing from `parsed_documents` table
- PDFs already in `processed_papers` (skipped automatically)

---

## 🔧 **Troubleshooting**

### **"Found 0 unique file_ids in processing_chunks"**
**Cause:** You're running on development database, not production.  
**Solution:** Make sure you're connected to production database.

### **"No parsed_document found for XXX, skipping"**
**Cause:** The file_id has chunks but no parsed_document record.  
**Impact:** This PDF will be skipped (can't backfill without metadata).  
**Action:** Investigate why parsed_document is missing for this file_id.

### **"Skipped (no metadata): X"**
**Cause:** Some PDFs are missing required metadata.  
**Action:** Review the logs to see which file_ids were skipped and why.

### **Script takes a long time**
**Normal:** Processing 100+ records takes ~2-5 minutes.  
**Optimize:** The script processes sequentially for safety, but this is normal for a one-time operation.

---

## 📊 **What This Fixes**

### **Before Backfill:**
```
System State:
- 107 PDFs parsed ✅
- 102 PDFs in Pinecone ✅
- 5 deduplication records ❌
- Risk: System thinks 102 PDFs were never processed
- Impact: Might try to reprocess them (wasting API calls)
```

### **After Backfill:**
```
System State:
- 107 PDFs parsed ✅
- 102 PDFs in Pinecone ✅
- 102 deduplication records ✅
- Result: System knows all PDFs are processed
- Impact: Won't reprocess, deduplication works correctly
```

---

## 🎉 **Success Indicators**

After running the backfill successfully, you should see:

1. ✅ **No more orphaned PDFs** - All chunks have corresponding processed_papers records
2. ✅ **Deduplication working** - System won't try to reprocess these 102 PDFs
3. ✅ **Scheduler safe** - Can run scheduled jobs without worrying about duplicates
4. ✅ **Database consistent** - All tables properly synchronized

---

## 📞 **Next Steps**

1. ✅ **Run backfill on production** (this guide)
2. ✅ **Verify results** with SQL queries
3. ✅ **Test scheduler** - Try running a scheduled job
4. ✅ **Monitor** - Watch for any reprocessing attempts

**Your deduplication system will now be complete!** 🚀
