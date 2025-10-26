# Database Write Operation Refactoring Pattern

## Problem
Database write operations in utils/database.py need consistent error handling:
- Automatic rollback on errors
- Error categorization (transient vs permanent)
- Structured logging
- No connection leaks

## Solution: Two-Layer Pattern

### Layer 1: Context Manager (from utils/db_utils.py)
`get_db_transaction()` provides:
- Automatic commit on success
- Automatic rollback on exception
- Automatic connection cleanup

### Layer 2: Error Categorization Decorator
`@with_db_error_handling` provides:
- Catches psycopg2 exceptions
- Converts to DatabaseError or DatabaseTransientError
- Structured logging with function name

## OLD Pattern (Manual - 20+ lines per function)
```python
def create_something(name: str) -> int:
    """Create something in database."""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO items (name) VALUES (%s) RETURNING id",
                    (name,)
                )
                result = cur.fetchone()
                conn.commit()
                return result['id'] if result else None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except pg_errors.UniqueViolation as e:
        raise DatabaseError(f"Item already exists: {name}") from e
    except psycopg2.OperationalError as e:
        raise DatabaseTransientError(f"Connection error: {e}") from e
    except psycopg2.Error as e:
        logger.error(f"Error creating item {name}: {e}")
        raise DatabaseError(f"Database error: {e}") from e
```

## NEW Pattern (Context Manager + Decorator - 8 lines)
```python
from utils.db_utils import get_db_transaction, with_db_error_handling

@with_db_error_handling
def create_something(name: str) -> int:
    """Create something in database."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO items (name) VALUES (%s) RETURNING id",
                (name,)
            )
            result = cur.fetchone()
            return result['id'] if result else None
```

## Benefits of NEW Pattern
1. **60% less code** (20 lines → 8 lines)
2. **Automatic rollback** via context manager
3. **Automatic error categorization** via decorator
4. **Automatic logging** with function name
5. **Consistent across codebase** - impossible to forget steps
6. **Type-safe** - decorator preserves function signatures

## Migration Path for utils/database.py

### Functions Needing Update (24 remaining)
```
create_data_source
update_data_source
delete_data_source
delete_job
save_metadata_transformation
delete_metadata_transformation
save_column_mapping
delete_column_mapping
mark_chunks_uploaded
update_last_processed
record_processed_paper
update_processed_paper
create_scheduled_job
update_scheduled_job_status
update_scheduled_job_run_time
create_scheduled_job_run
update_scheduled_job_run
delete_scheduled_job
create_celery_job
update_celery_job_status
delete_old_celery_jobs
... (and more)
```

### Step-by-Step Migration
1. Import decorator: `from utils.db_utils import get_db_transaction, with_db_error_handling`
2. Add `@with_db_error_handling` decorator above function
3. Replace `get_db_connection()` with `get_db_transaction()`
4. Remove manual try/except/rollback/error handling
5. Test the function

### Example Migration

**BEFORE:**
```python
def delete_job(job_id: str):
    """Delete a processing job."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM processing_jobs WHERE job_id = %s", (job_id,))
            conn.commit()
    finally:
        conn.close()
```

**AFTER:**
```python
from utils.db_utils import get_db_transaction, with_db_error_handling

@with_db_error_handling
def delete_job(job_id: str):
    """Delete a processing job."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM processing_jobs WHERE job_id = %s", (job_id,))
```

## Validation Checklist
- [ ] Function has `@with_db_error_handling` decorator
- [ ] Uses `get_db_transaction()` instead of `get_db_connection()`
- [ ] No manual commit() calls (automatic via context manager)
- [ ] No manual rollback() calls (automatic via context manager)
- [ ] No manual error handling (automatic via decorator)
- [ ] Function is simpler and more readable
- [ ] Test passes

## Estimated Effort
- Per function: 2-3 minutes
- 24 functions remaining: ~1 hour total
- High confidence (mechanical application of pattern)
