"""
Sentry configuration for error tracking and monitoring.

This module initializes Sentry SDK for the application with proper
configuration for production error tracking, performance monitoring,
and custom context.
"""

import os
import logging
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

logger = logging.getLogger(__name__)


def init_sentry():
    """
    Initialize Sentry SDK for error tracking.
    
    Features:
    - Automatic error capture from exceptions
    - Breadcrumb tracking for debugging context
    - Performance/transaction monitoring (10% sample rate)
    - Celery task integration
    - Custom logging integration
    
    Environment Variables:
    - SENTRY_DSN: Sentry Data Source Name (required for activation)
    - SENTRY_ENVIRONMENT: Environment name (dev, staging, production)
    - SENTRY_TRACES_SAMPLE_RATE: Performance monitoring sample rate (0.0-1.0)
    
    Usage:
        # In app.py or celeryconfig.py:
        from utils.sentry_config import init_sentry
        init_sentry()
    """
    sentry_dsn = os.getenv('SENTRY_DSN')
    
    if not sentry_dsn:
        logger.info("Sentry DSN not configured. Error tracking disabled.")
        return
    
    environment = os.getenv('SENTRY_ENVIRONMENT', 'development')
    traces_sample_rate = float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1'))
    
    # Configure logging integration
    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Send errors and above as events
    )
    
    try:
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            
            # Integrations
            integrations=[
                sentry_logging,
                CeleryIntegration(),
            ],
            
            # Send default PII (personally identifiable information)
            send_default_pii=False,
            
            # Custom before_send hook to add context
            before_send=before_send_hook,
            
            # Release tracking (optional)
            release=os.getenv('SENTRY_RELEASE', 'unknown'),
        )
        
        logger.info(f"✅ Sentry initialized: environment={environment}, traces_sample_rate={traces_sample_rate}")
        
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")


def before_send_hook(event, hint):
    """
    Custom hook to modify events before sending to Sentry.
    
    Use this to:
    - Filter out sensitive data
    - Add custom context
    - Ignore certain errors
    
    Args:
        event: The error event
        hint: Additional context about the error
        
    Returns:
        Modified event or None to discard
    """
    # Example: Add custom tags
    if 'tags' not in event:
        event['tags'] = {}
    
    # Add job context if available
    if 'extra' in event and 'job_id' in event.get('extra', {}):
        event['tags']['job_id'] = event['extra']['job_id']
    
    # Example: Filter out specific errors
    if 'exception' in event:
        exc_type = event['exception'].get('values', [{}])[0].get('type', '')
        
        # Don't send known non-critical errors
        if exc_type in ['KeyboardInterrupt', 'SystemExit']:
            return None
    
    return event


def capture_exception_with_context(exception, context=None):
    """
    Capture an exception with additional context.
    
    Args:
        exception: The exception to capture
        context: Dictionary of additional context (job_id, file_id, etc.)
        
    Example:
        try:
            process_pdf(file_id)
        except Exception as e:
            capture_exception_with_context(e, {
                'job_id': job_id,
                'file_id': file_id,
                'filename': filename
            })
    """
    if context:
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(exception)
    else:
        sentry_sdk.capture_exception(exception)


def capture_message_with_context(message, level='info', context=None):
    """
    Capture a message with additional context.
    
    Args:
        message: The message to capture
        level: Severity level ('debug', 'info', 'warning', 'error', 'fatal')
        context: Dictionary of additional context
        
    Example:
        capture_message_with_context(
            'Processing taking longer than expected',
            level='warning',
            context={'job_id': job_id, 'duration': 1200}
        )
    """
    if context:
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_message(message, level=level)
    else:
        sentry_sdk.capture_message(message, level=level)
