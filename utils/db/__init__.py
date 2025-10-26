"""
Modular database operations package.

This package provides database operations organized by domain:
- products: Product management (CRUD, API keys)
- jobs: Processing jobs, chunks, metadata transformations, Celery jobs
- documents: Parsed documents, AI tagging, deduplication
- sources: Data sources and column mappings
- scheduling: Scheduled jobs and run tracking
- connection: Database connection utilities

For backward compatibility, all functions are re-exported at the package level.
Existing imports like `from utils.database import function_name` continue to work.
"""

# Connection utilities
from utils.db.connection import (
    get_db_connection,
    _row_to_dict,
)

# Product management
from utils.db.products import (
    init_products_table,
    get_products,
    get_product,
    create_product,
    update_product,
    delete_product,
    get_product_api_keys,
)

# Processing jobs and chunks
from utils.db.jobs import (
    create_processing_job,
    update_job_status,
    get_job_history,
    get_job_details,
    delete_job,
    save_chunks,
    get_job_chunks,
    mark_chunks_uploaded,
    save_metadata_transformation,
    get_metadata_transformations,
    delete_metadata_transformation,
    init_celery_tables,
    create_celery_job,
    update_celery_job_status,
    get_celery_job,
    get_all_celery_jobs,
    cancel_celery_job,
)

# Parsed documents and deduplication
from utils.db.documents import (
    save_parsed_document,
    get_parsed_document,
    get_parsed_text_for_rechunking,
    get_all_parsed_documents,
    update_document_tags,
    get_document_tags,
    is_document_tagged,
    check_paper_processed,
    check_paper_by_content_hash,
    record_processed_paper,
    update_processed_paper,
    get_deduplication_stats,
)

# Data sources and column mappings
from utils.db.sources import (
    create_data_source,
    get_data_sources,
    get_data_source,
    update_data_source,
    delete_data_source,
    update_last_processed,
    save_column_mapping,
    get_column_mappings,
    delete_column_mapping,
    get_column_mapping_dict,
)

# Scheduled jobs
from utils.db.scheduling import (
    create_scheduled_job,
    get_scheduled_job,
    get_all_scheduled_jobs,
    update_scheduled_job_status,
    update_scheduled_job_run_time,
    delete_scheduled_job,
    record_scheduled_job_run,
    update_scheduled_job_run,
    get_scheduled_job_runs,
)

# Define __all__ for explicit exports
__all__ = [
    # Connection
    'get_db_connection',
    '_row_to_dict',
    # Products
    'init_products_table',
    'get_products',
    'get_product',
    'create_product',
    'update_product',
    'delete_product',
    'get_product_api_keys',
    # Jobs
    'create_processing_job',
    'update_job_status',
    'get_job_history',
    'get_job_details',
    'delete_job',
    'save_chunks',
    'get_job_chunks',
    'mark_chunks_uploaded',
    'save_metadata_transformation',
    'get_metadata_transformations',
    'delete_metadata_transformation',
    'init_celery_tables',
    'create_celery_job',
    'update_celery_job_status',
    'get_celery_job',
    'get_all_celery_jobs',
    'cancel_celery_job',
    # Documents
    'save_parsed_document',
    'get_parsed_document',
    'get_parsed_text_for_rechunking',
    'get_all_parsed_documents',
    'update_document_tags',
    'get_document_tags',
    'is_document_tagged',
    'check_paper_processed',
    'check_paper_by_content_hash',
    'record_processed_paper',
    'update_processed_paper',
    'get_deduplication_stats',
    # Sources
    'create_data_source',
    'get_data_sources',
    'get_data_source',
    'update_data_source',
    'delete_data_source',
    'update_last_processed',
    'save_column_mapping',
    'get_column_mappings',
    'delete_column_mapping',
    'get_column_mapping_dict',
    # Scheduling
    'create_scheduled_job',
    'get_scheduled_job',
    'get_all_scheduled_jobs',
    'update_scheduled_job_status',
    'update_scheduled_job_run_time',
    'delete_scheduled_job',
    'record_scheduled_job_run',
    'update_scheduled_job_run',
    'get_scheduled_job_runs',
]
