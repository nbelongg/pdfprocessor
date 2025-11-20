-- Migration: Add CASCADE constraints to prevent orphaned records
-- Date: 2025-11-20
-- Description: Adds ON DELETE CASCADE to source_paper_mapping foreign key
--              to automatically clean up mapping records when a paper is deleted

-- Step 1: Drop existing foreign key constraint
-- Note: Replace 'source_paper_mapping_paper_id_fkey' with actual constraint name if different
-- You can find the actual name with: \d source_paper_mapping in psql

ALTER TABLE source_paper_mapping
DROP CONSTRAINT IF EXISTS source_paper_mapping_paper_id_fkey;

-- Step 2: Add new foreign key constraint with CASCADE
ALTER TABLE source_paper_mapping
ADD CONSTRAINT source_paper_mapping_paper_id_fkey
    FOREIGN KEY (paper_id)
    REFERENCES processed_papers(id)
    ON DELETE CASCADE;

-- Verification query (run after migration):
-- SELECT conname, confdeltype
-- FROM pg_constraint
-- WHERE conrelid = 'source_paper_mapping'::regclass
--   AND conname = 'source_paper_mapping_paper_id_fkey';
-- Expected: confdeltype = 'c' (CASCADE)

COMMENT ON CONSTRAINT source_paper_mapping_paper_id_fkey ON source_paper_mapping IS
'Foreign key with CASCADE delete - automatically removes mapping when parent paper is deleted';
