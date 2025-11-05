# Production Environment Configuration

## Problem Identified

Your **production** (`.replit.app`) and **development** environments were sharing the same Redis database (database `0`), causing cross-contamination:

1. Production UI triggers job → Creates record in production database
2. Task goes to **shared Redis database 0**
3. **Dev worker** picks it up (also connected to database 0)
4. Dev worker can't find the data source in dev database
5. Production job stays stuck in "pending"

## Solution ✅

The system now **automatically detects** the environment and uses different Redis databases:
- **Development**: Redis database `0` (default)
- **Production**: Redis database `1` (auto-detected)

**No manual configuration needed!** The code checks for Replit deployment indicators and automatically routes to the correct database.

---

## How Auto-Detection Works

The system checks these environment variables:
- `REPLIT_DEPLOYMENT=1` → Production
- `REPL_SLUG` ends with `.replit.app` → Production
- `REPLIT_DOMAINS` contains `replit.app` → Production

If any of these are true, it uses Redis database `1`. Otherwise, it defaults to database `0`.

---

## Verification Steps

### Development Environment
Check your dev worker logs for:
```
Configuring Redis connection (Environment: DEVELOPMENT, TLS: True, DB: 0)
```

### Production Environment
After publishing, check production worker logs for:
```
Configuring Redis connection (Environment: PRODUCTION, TLS: True, DB: 1)
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
