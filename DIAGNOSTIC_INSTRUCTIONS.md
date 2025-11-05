# 🔬 Production Diagnostic Instructions

This document provides step-by-step instructions for diagnosing why production jobs get stuck in "pending" status.

## 📋 Overview

We've implemented comprehensive logging at every stage of the task lifecycle:

1. **UI Task Submission** → Logs environment, Redis config, task queuing
2. **Celery Signal Handlers** → Logs when worker picks up task
3. **Task Execution** → Logs when task actually runs
4. **Database Operations** → Logs all status updates

## 🧪 Hypotheses Being Tested

| Hypothesis | What to Look For | Where to Check |
|------------|------------------|----------------|
| **H1: No Production Worker** | No worker logs | Replit deployment logs |
| **H2: Environment Mismatch** | UI uses `prod_` but worker uses `dev_` | UI logs + Worker logs |
| **H3: Signal Handler Failures** | DB connection errors in signal handlers | Worker logs |
| **H4: Task Submission Failures** | `apply_async()` exceptions | UI/Server logs |
| **H5: Worker DB Access Issues** | DB connection failures in worker | Worker logs |

---

## 🚀 Step-by-Step Diagnostic Procedure

### Step 1: Check Diagnostics Page

1. Navigate to **🔬 Diagnostics** page in the UI
2. Screenshot or record:
   - Environment Detection result
   - Redis Key Prefix
   - Celery Configuration
   - Database Connection Status

**What to verify:**
- Production should show: `Environment: PRODUCTION`
- Redis prefix should show: `prod_`
- Database connection should be: `WORKING`

---

### Step 2: Trigger a Test Job in Production

1. Go to **⚙️ Job Management** → **🚀 Trigger Processing** tab
2. Select any data source with a few papers
3. Click **Trigger Processing**
4. Note the Job ID from the success message

---

### Step 3: Collect UI/Server Logs

**Look for these log sections in production Server logs:**

```
================================================================================
ENVIRONMENT DIAGNOSTIC
================================================================================
Environment Detected: PRODUCTION
Redis Key Prefix: prod_
```

```
🚀🚀🚀🚀...
TASK SUBMISSION DIAGNOSTIC
🚀🚀🚀🚀...
Task ID: <job_id>
Environment: PRODUCTION
Redis Prefix: prod_
Expected Redis Key: prod_celery-task-meta-<job_id>
```

```
✅ apply_async() COMPLETED SUCCESSFULLY for task <job_id>
```

**Critical Questions:**
- ❓ Does environment detection show `PRODUCTION`?
- ❓ Does it show `prod_` prefix?
- ❓ Does `apply_async()` complete successfully?
- ❓ Are there any exceptions after apply_async?

---

### Step 4: Collect Worker Logs

**CRITICAL: Verify production worker is running!**

Check your Replit deployment for a **Worker** process. If there's no worker running in production, that's the problem!

**Look for these log sections in production Worker logs:**

```
Setting Celery key prefix: 'prod' for environment isolation
```

```
📡 SIGNAL HANDLER: task_prerun triggered for task <job_id>
```

```
👷👷👷👷...
WORKER TASK RECEIVED
👷👷👷👷...
Task ID: <job_id>
Worker Environment: PRODUCTION
Worker Redis Prefix: prod_
```

```
================================================================================
🎯 TASK EXECUTION STARTED: process_batch_task
================================================================================
Task ID (job_id): <job_id>
```

**Critical Questions:**
- ❓ Is the Worker process running in production?
- ❓ Does worker show `Environment: PRODUCTION`?
- ❓ Does worker show `prod_` prefix?
- ❓ Does the signal handler fire?
- ❓ Does the task execution start?
- ❓ Are there any DB connection errors?

---

### Step 5: Analyze the Logs

Compare the logs against these scenarios:

#### ✅ Scenario A: Everything Working (Job should complete)
```
UI:     Environment: PRODUCTION, Prefix: prod_
Worker: Environment: PRODUCTION, Prefix: prod_
        ↓
UI:     ✅ apply_async() COMPLETED
        ↓
Worker: 📡 SIGNAL HANDLER: task_prerun triggered
        ↓
Worker: 👷 WORKER TASK RECEIVED
        ↓
Worker: 🎯 TASK EXECUTION STARTED
        ↓
Worker: ✅ Status updated to 'running'
```

#### ❌ Scenario B: No Worker Running
```
UI:     Environment: PRODUCTION, Prefix: prod_
UI:     ✅ apply_async() COMPLETED
        ↓
Worker: (NO LOGS - worker not running!)
```
**FIX**: Start a Worker workflow in production deployment

#### ❌ Scenario C: Environment Mismatch
```
UI:     Environment: DEVELOPMENT, Prefix: dev_
Worker: Environment: PRODUCTION, Prefix: prod_
        ↓
UI:     ✅ apply_async() with dev_ prefix
        ↓
Worker: (Task never received - listening to prod_ only)
```
**FIX**: Verify environment detection logic

#### ❌ Scenario D: Signal Handler Failures
```
UI:     ✅ apply_async() COMPLETED
        ↓
Worker: 📡 SIGNAL HANDLER: task_prerun triggered
Worker: ❌ CRITICAL: Signal handler exception
Worker: ❌ Database connection failed
```
**FIX**: Check database credentials in production

#### ❌ Scenario E: Task Submission Failure
```
UI:     Environment: PRODUCTION, Prefix: prod_
UI:     ❌ apply_async() FAILED
UI:     ❌ Error: <exception details>
```
**FIX**: Check Redis connection from UI

---

## 📝 Log Collection Template

Use this template to collect and share diagnostic information:

```markdown
## Production Diagnostic Report

**Date/Time**: <timestamp>
**Job ID**: <job_id from test>

### Diagnostics Page
- Environment: <PRODUCTION or DEVELOPMENT>
- Redis Prefix: <prod_ or dev_>
- DB Connection: <WORKING or FAILED>

### UI/Server Logs
<paste relevant sections from server logs>

Key findings:
- Environment detection: 
- Task submission success:
- Any errors:

### Worker Logs  
<paste relevant sections from worker logs>

Key findings:
- Worker running:
- Environment:
- Signal handler fired:
- Task received:
- DB connection:

### Analysis
Which scenario matches? (A, B, C, D, or E)
```

---

## 🔧 Quick Fixes Based on Findings

### If Worker Not Running
1. Check Replit deployment configuration
2. Ensure Worker workflow is included in deployment
3. Start worker process manually if needed

### If Environment Mismatch
1. Check environment variables in production
2. Verify REPLIT_DEPLOYMENT, REPL_SLUG, REPLIT_DOMAINS
3. May need to add explicit environment flag

### If DB Connection Issues
1. Verify DATABASE_URL secret in production
2. Check PostgreSQL credentials
3. Test DB connection from diagnostics page

### If Redis Connection Issues
1. Verify REDIS_* secrets in production
2. Check TLS configuration
3. Verify Upstash Redis is accessible from production

---

## 💡 Additional Debugging Tips

1. **Compare Dev vs Prod**: Run same test in dev, compare logs
2. **Check Replit Logs**: Use Replit's built-in log viewer
3. **Redis CLI**: If possible, check Redis keys directly
4. **Database Query**: Check celery_jobs table directly

---

## 🆘 If All Else Fails

Collect:
1. Screenshot of Diagnostics page
2. Last 200 lines of Server logs (from triggering job)
3. Last 200 lines of Worker logs (from when job triggered)
4. Screenshot of stuck job in Job Management page

This will provide enough context to diagnose the root cause.
