# Production Environment Configuration

## Problem Identified

Your **production** (`.replit.app`) and **development** environments were sharing the same Redis database (database `0`), causing cross-contamination:

1. Production UI triggers job → Creates record in production database
2. Task goes to **shared Redis database 0**
3. **Dev worker** picks it up (also connected to database 0)
4. Dev worker can't find the data source in dev database
5. Production job stays stuck in "pending"

## Solution

Separate production and dev by using different Redis database numbers:
- **Development**: Redis database `0` (default)
- **Production**: Redis database `1`

---

## Setup Instructions for Production

### Step 1: Add Environment Variable in Production

In your Replit production deployment settings, add this **Replit Secret**:

```
Name: REDIS_DB
Value: 1
```

**How to add it:**
1. Go to your Replit project
2. Click on **"Secrets"** (lock icon in left sidebar)
3. Click **"+ New Secret"**
4. Enter:
   - Key: `REDIS_DB`
   - Value: `1`
5. Save

### Step 2: Deploy/Publish

After adding the secret, click **Publish** to deploy with the new configuration.

### Step 3: Verify Separation

After deployment, check the worker logs in production. You should see:

```
Built TLS Redis connection for magnetic-ray-22268.upstash.io:6379 (DB: 1)
```

And in development, you should see:

```
Built TLS Redis connection for magnetic-ray-22268.upstash.io:6379 (DB: 0)
```

---

## What This Fixes

✅ **Production jobs** → Production worker (Redis DB 1) → Production database
✅ **Dev jobs** → Dev worker (Redis DB 0) → Dev database
✅ No more cross-contamination
✅ Jobs transition properly: pending → running → completed/failed

---

## Testing After Setup

1. Trigger a job in **production**
2. Status should change: `pending` → `running` → `completed`/`failed`
3. Check production worker logs - should process correctly
4. Dev and production jobs won't interfere with each other

---

## Notes

- This keeps the same Redis server (Upstash) but uses different databases
- Redis supports 16 databases (0-15) by default
- Database 0 = dev, Database 1 = production
- This is a standard pattern for environment separation

---

## Troubleshooting

**If jobs still get stuck:**

1. Verify `REDIS_DB=1` secret exists in production
2. Check production worker logs show `(DB: 1)`
3. Restart production workers after adding the secret
4. Use cleanup script to remove old stuck jobs:
   ```bash
   python utils/cleanup_orphaned_jobs.py --execute
   ```
