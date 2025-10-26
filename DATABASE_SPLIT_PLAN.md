# Database Module Split Plan

## Objective
Split `utils/database.py` (1277 lines, 57 functions) into logical modules for better maintainability.

## Current State
- **Single file**: `utils/database.py` with all database operations
- **Dependencies**: ~10 files import from database (app.py, tasks.py, scheduler.py, page_modules/*)
- **Function categories**: Processing jobs, chunks, data sources, products, scheduled jobs, celery tracking

## Proposed Structure

### Module Organization

```
utils/db/
├── __init__.py              # Re-export all functions for backward compatibility
├── connection.py            # ✅ CREATED - Connection utilities (2 functions)
├── processing.py            # Processing jobs, chunks, parsed docs (~15 functions)
├── sources.py               # Data sources, column mappings, scheduled jobs (~20 functions)
└── products.py              # Product management, celery jobs (~15 functions)
```

### Migration Strategy

**Phase 1: Create Modules** (Estimated: 30 mins)
1. ✅ `connection.py` - Already created
2. `processing.py` - Extract:
   - `create_processing_job`, `update_job_status`
   - `save_chunks`, `mark_chunks_uploaded`
   - `save_parsed_document`, `get_parsed_document`, `get_parsed_text_for_rechunking`
   - `update_document_tags`, `get_document_tags`, `is_document_tagged`
   - `get_all_parsed_documents`
   - `get_job_history`, `get_job_details`, `get_job_chunks`, `delete_job`

3. `sources.py` - Extract:
   - Data Sources: `create_data_source`, `get_data_sources`, `get_data_source`, `update_data_source`, `delete_data_source`, `update_last_processed`
   - Column Mappings: `save_column_mapping`, `get_column_mappings`, `get_column_mapping_dict`, `delete_column_mapping`
   - Metadata Transforms: `save_metadata_transformation`, `get_metadata_transformations`, `delete_metadata_transformation`
   - Scheduled Jobs: `create_scheduled_job`, `get_scheduled_job`, `get_all_scheduled_jobs`, `update_scheduled_job_status`, `update_scheduled_job_run_time`, `record_scheduled_job_run`, `update_scheduled_job_run`, `get_scheduled_job_runs`, `delete_scheduled_job`
   - Processed Papers: `record_processed_paper`, `update_processed_paper`, `get_deduplication_stats`

4. `products.py` - Extract:
   - Products: `init_products_table`, `get_products`, `get_product`, `create_product`, `update_product`, `delete_product`, `get_product_api_keys`
   - Celery: `init_celery_tables`, `create_celery_job`, `update_celery_job_status`, `get_celery_job`, `get_all_celery_jobs`, `cancel_celery_job`

**Phase 2: Create __init__.py** (Estimated: 10 mins)
- Import all functions from submodules
- Re-export them at package level
- **This maintains backward compatibility** - existing imports still work!

Example:
```python
# utils/db/__init__.py
from .connection import get_db_connection, _row_to_dict
from .processing import create_processing_job, update_job_status, ...
from .sources import create_data_source, get_data_sources, ...
from .products import get_products, create_product, ...

__all__ = [
    'get_db_connection', '_row_to_dict',
    'create_processing_job', 'update_job_status',
    # ... all other functions
]
```

**Phase 3: Update database.py** (Estimated: 5 mins)
Option A: Delete and replace with import re-exports (backward compatible)
```python
# utils/database.py
from utils.db import *
```

Option B: Deprecate with warning
```python
# utils/database.py  
import warnings
warnings.warn("utils.database is deprecated, use utils.db instead", DeprecationWarning)
from utils.db import *
```

**Phase 4: Optional - Update Imports** (Estimated: 30-60 mins)
Gradually update imports in consuming files:
- `app.py`
- `tasks.py`  
- `scheduler.py`
- `page_modules/*.py` (10 files)

This is OPTIONAL because Phase 2 ensures backward compatibility.

## Benefits

1. **Better Organization**: Related functions grouped together
2. **Easier Navigation**: ~250-350 lines per module vs 1277 in one file
3. **Clear Boundaries**: Processing vs Sources vs Products
4. **Maintainability**: Easier to find and modify specific functionality
5. **Backward Compatible**: Existing imports continue to work

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Breaking imports | Use __init__.py re-exports for backward compatibility |
| Circular dependencies | Keep modules focused, connection.py has no dependencies |
| Test failures | Run full test suite after each phase |
| Merge conflicts | Complete in single session while code is fresh |

## Testing Strategy

After each phase:
1. Run: `python test_error_handling.py` (targeted tests)
2. Start app: Check Server and Worker logs for import errors
3. Smoke test: Open app, navigate to each page
4. Full test: Run end-to-end processing test

## Rollback Plan

If issues arise:
1. Revert new files in utils/db/
2. Keep utils/database.py as-is
3. No changes to consuming files needed (backward compatible)

## Estimated Time
- **Minimum (backward compatible)**: ~45 minutes (Phases 1-3)
- **Full migration**: ~1.5-2 hours (all phases)

## Recommendation

**Implement Phases 1-3 only** (backward compatible split):
- Creates clean modules
- Maintains all existing imports
- Low risk, high benefit
- Can optionally do Phase 4 later
