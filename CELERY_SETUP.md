# Celery Background Job Queue Setup Guide

## Overview
Your PDF processing pipeline now includes a Celery-based background job queue system that enables:
- **Scalable Processing**: Handle 100-200+ papers in parallel without blocking the UI
- **Fault Tolerance**: Automatic retries with exponential backoff for failed tasks
- **Long-Running Jobs**: Process batches that take hours without browser timeouts
- **Job Monitoring**: Track job progress, view history, and monitor active workers

## Architecture

### Components
1. **Streamlit Server** (`app.py`) - Web UI and job submission
2. **Celery Workers** (`celeryconfig.py`, `tasks.py`) - Background task processors
3. **Redis** - Message broker and result backend
4. **PostgreSQL** - Job tracking and metadata storage

### Data Flow
```
User → Streamlit UI → Celery Task Queue → Redis → Celery Workers → PostgreSQL + Pinecone
```

## Setup Instructions

### Step 1: Set Up Redis (Upstash Recommended)

Since Replit doesn't provide built-in Redis, you'll need to use **Upstash Redis** (serverless, free tier available):

1. **Create Upstash Account**
   - Go to https://upstash.com
   - Sign up for a free account

2. **Create Redis Database**
   - Click "Create Database"
   - Choose a region (prefer `us-east-1` for best performance)
   - Select "TLS Enabled" (required for security)
   - Click "Create"

3. **Get Connection Details**
   - On the database dashboard, copy:
     - **Endpoint** (looks like: `example-12345.upstash.io`)
     - **Port** (usually `6379` or `xxxxx`)
     - **Password** (click "Show" to reveal)

### Step 2: Configure Replit Secrets

Add the following secrets to your Replit project (Tools → Secrets):

```
REDIS_HOST=your-upstash-endpoint.upstash.io
REDIS_PORT=6379
REDIS_PASSWORD=your-upstash-password
REDIS_USE_TLS=true
```

**Example:**
```
REDIS_HOST=usw1-example-12345.upstash.io
REDIS_PORT=6379
REDIS_PASSWORD=AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPp
REDIS_USE_TLS=true
```

### Step 3: Verify Worker is Running

After setting the secrets:

1. The Worker workflow should auto-restart
2. Check the "Console" output for the Worker workflow
3. You should see:
   ```
   [tasks]
     . tasks.process_batch_task
     . tasks.process_pdf_task
   
   [2025-10-25 16:00:00,000: INFO/MainProcess] Connected to redis://...
   [2025-10-25 16:00:00,000: INFO/MainProcess] ready.
   ```

4. If you see connection errors, double-check your Redis secrets

### Step 4: Test the System

1. **Select Papers**
   - Go to "📁 Select Files" page
   - Choose your data source
   - Select PDFs to process

2. **Submit Background Job**
   - Go to "⚙️ Job Queue" page
   - Click "Submit to Background Queue"
   - You'll get a Task ID

3. **Monitor Progress**
   - Switch to "📊 Active Jobs" tab
   - Click "Refresh" to see updates
   - Watch the progress counter

4. **Check Results**
   - Once complete, go to "📜 Job History" tab
   - View processing results and any errors

## Usage Guide

### Submitting Jobs

**Option 1: Background Queue (Recommended for Large Batches)**
- Navigate to "⚙️ Job Queue" → "Submit Job"
- Best for: 10+ papers, long-running batches
- Benefits: No browser timeout, can close browser

**Option 2: Synchronous Processing (Legacy)**
- Navigate to "🚀 Process & Upload"
- Best for: Quick tests, <5 papers
- Limitations: Browser must stay open

### Monitoring Jobs

**Active Jobs Tab**
- Shows currently running and pending jobs
- Displays real-time progress
- Click "Refresh" for latest status

**Job History Tab**
- Shows completed and failed jobs
- View detailed results
- Check error messages for failed jobs

### Job Lifecycle

1. **Pending** - Job submitted, waiting for worker
2. **Running** - Worker processing the job
3. **Progress** - Showing current progress (e.g., "3/10 PDFs processed")
4. **Completed** - Successfully finished
5. **Failed** - Error occurred (check error message)

## Configuration

### Worker Settings (celeryconfig.py)

```python
# Concurrency: Number of parallel workers
worker_concurrency = 3  # Process 3 PDFs simultaneously

# Task time limits
task_time_limit = 1800  # 30 minutes hard limit
task_soft_time_limit = 1500  # 25 minutes soft limit

# Retry settings
task_max_retries = 3  # Retry failed tasks up to 3 times
task_default_retry_delay = 60  # Wait 60 seconds between retries
```

### Scaling Workers

To process more papers in parallel:

1. Edit `celeryconfig.py`
2. Change `worker_concurrency` (e.g., from 3 to 5)
3. Restart the Worker workflow

**Memory Considerations:**
- Each worker uses ~200-500MB RAM
- Replit free tier: 4GB RAM → safe limit is 3-5 workers
- Replit paid tier: More RAM → can increase to 10+ workers

## Troubleshooting

### Worker Won't Start

**Symptom:** Worker workflow shows "FAILED"

**Check:**
1. Redis secrets are set correctly
2. View Worker logs: Look for connection errors
3. Test Redis connection:
   ```python
   import redis
   r = redis.from_url(os.getenv('REDIS_URL'))
   r.ping()  # Should return True
   ```

**Common Fixes:**
- Double-check `REDIS_HOST`, `REDIS_PASSWORD`
- Ensure `REDIS_USE_TLS=true` for Upstash
- Verify Upstash database is active

### Jobs Stay in "Pending" Forever

**Symptom:** Submitted jobs never start processing

**Causes:**
1. Worker is not running
2. Redis connection issue
3. Worker crashed

**Fix:**
1. Check Worker workflow status
2. Restart Worker workflow manually
3. Check Worker logs for errors

### Tasks Failing with Errors

**Symptom:** Jobs show "Failed" status with errors

**Debug:**
1. Go to "📜 Job History"
2. Find the failed job
3. Read the error message
4. Common issues:
   - Missing API keys (LlamaParse, OpenAI, Pinecone)
   - Google credentials not set
   - Invalid PDF files
   - Network timeouts

**Fix:**
- Ensure all product API keys are configured
- Check individual PDF files for corruption
- Review retry logs for transient vs permanent errors

### Performance Issues

**Symptom:** Jobs taking too long

**Optimizations:**
1. **Increase Workers**: Edit `celeryconfig.py` concurrency
2. **Batch Size**: Process smaller batches (50 papers at a time)
3. **Chunk Size**: Reduce chunk size to create fewer embeddings
4. **Embedding Model**: Use `text-embedding-3-small` instead of `large`

## Advanced Features

### Task Retry Logic

Tasks automatically retry on failure:
- **Retry 1**: Wait 1 second, retry
- **Retry 2**: Wait 2 seconds, retry
- **Retry 3**: Wait 4 seconds, retry
- **Final Fail**: Mark as failed, log error

Customize in `tasks.py`:
```python
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
```

### Job Priorities

Future feature: Add priority queues
```python
# High priority
task.apply_async(queue='high_priority')

# Normal priority
task.apply_async(queue='pdf_processing')
```

### Scheduled Processing

Combine with cron jobs for automatic processing:
```python
# In celeryconfig.py
celery_app.conf.beat_schedule = {
    'process-new-papers-daily': {
        'task': 'tasks.process_batch_task',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    },
}
```

## Monitoring Tools

### Flower (Optional)

Flower is installed but not configured by default. To enable:

1. Add workflow:
   ```
   Command: celery -A celeryconfig flower --port=5555
   ```

2. Access at: `https://your-repl-name.replit.app:5555`

3. View:
   - Worker status
   - Task history
   - Performance metrics

### Database Queries

Check job stats directly:
```sql
-- Count jobs by status
SELECT status, COUNT(*) FROM celery_jobs GROUP BY status;

-- Recent failed jobs
SELECT * FROM celery_jobs 
WHERE status = 'failed' 
ORDER BY created_at DESC 
LIMIT 10;

-- Average processing time
SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) as avg_seconds
FROM celery_jobs 
WHERE status = 'completed';
```

## Cost Considerations

### Upstash Redis (Free Tier)
- 10,000 commands/day
- 256MB storage
- Sufficient for: 20-50 jobs/day with 10-50 papers each

### Replit Resources
- Free tier: 4GB RAM, shared CPU
- Hacker plan: 8GB RAM, faster CPU
- Recommended: Hacker plan for 100+ paper batches

### API Costs (External)
- **LlamaParse**: $0.003/page (major cost)
- **OpenAI Embeddings**: $0.00002/1K tokens (minor cost)
- **Pinecone**: Free tier or paid based on vectors

**Example Cost for 100 Papers:**
- 100 papers × 10 pages = 1,000 pages
- LlamaParse: 1,000 × $0.003 = $3.00
- Embeddings: ~$0.50
- **Total: ~$3.50**

## Support

### Logs
- **Worker Logs**: Workflow Console (Worker)
- **Application Logs**: Workflow Console (Server)
- **Database Logs**: Check PostgreSQL query logs

### Key Files
- `celeryconfig.py` - Celery configuration
- `tasks.py` - Task definitions
- `worker.py` - Worker startup
- `utils/database.py` - Job tracking functions
- `app.py` - Job Queue UI (line 1249+)

### Next Steps
1. Configure Redis secrets
2. Test with small batch (2-3 papers)
3. Monitor job progress
4. Scale to larger batches
5. Set up scheduled processing (optional)

---

**Need Help?** Check the Worker logs first, then verify Redis connection.
