# Scheduler Deployment Guide

This guide explains how to set up automated periodic processing of papers using Replit's cron job feature.

## Overview

The scheduler (`scheduler.py`) automatically processes new papers from your configured data sources on a regular schedule. It runs independently from the main Streamlit application.

## Prerequisites

1. **Data Sources Configured**: At least one data source set up in the app with column mappings
2. **Scheduled Jobs Created**: Use the Scheduling tab in the Data Sources section to configure schedules
3. **Google Service Account**: JSON credentials file available

## Environment Setup

### Required Environment Variables

Set these in your Replit deployment secrets:

```
LLAMA_CLOUD_API_KEY=your_llamaparse_api_key
PINECONE_API_KEY=your_pinecone_api_key
OPENAI_API_KEY=your_openai_api_key (if using OpenAI embeddings)
DATABASE_URL=your_postgres_connection_string
GOOGLE_CREDENTIALS_PATH=/path/to/service_account.json
```

### Google Credentials Setup

1. Upload your Google service account JSON file to the Replit workspace
2. Set the `GOOGLE_CREDENTIALS_PATH` environment variable to the file path
3. Example: `GOOGLE_CREDENTIALS_PATH=/home/runner/workspace/google_credentials.json`

## Running the Scheduler

### Manual Execution

Test the scheduler manually before setting up cron:

```bash
python scheduler.py
```

This will:
- Check for enabled scheduled jobs
- Process jobs that are due to run
- Update next run times
- Log all activity to the console

### Automated Cron Execution

To run the scheduler automatically on a regular schedule:

1. **Configure in `.replit` file**:

```toml
[[workflows]]
name = "Scheduler"
command = "python scheduler.py"
type = "cron"
schedule = "0 * * * *"  # Run every hour
```

2. **Cron Schedule Formats**:
   - `0 * * * *` - Every hour at minute 0
   - `0 0 * * *` - Daily at midnight
   - `0 */6 * * *` - Every 6 hours
   - `0 2 * * 1` - Weekly on Monday at 2 AM

3. **Deploy to Replit**:
   - Your cron job will run automatically according to the schedule
   - Check deployment logs to monitor execution

## How It Works

1. **Scheduler Wakes Up**: Runs on the configured cron schedule
2. **Checks for Due Jobs**: Finds all enabled scheduled jobs with `next_run_at <= now()`
3. **Fetches New Papers**: Gets papers since `last_processed_row` from each data source
4. **Processes with Deduplication**: Runs the full pipeline with automatic duplicate detection
5. **Records Results**: Saves run statistics and updates next run time
6. **Calculates Next Run**: Based on schedule type (hourly, daily, weekly, interval)

## Schedule Configuration

Configure schedules through the web UI (Data Sources → Scheduling tab):

### Schedule Types

1. **Hourly**: Runs every hour
2. **Daily**: Runs once per day at a specific hour (0-23)
3. **Weekly**: Runs once per week on a specific day and hour
4. **Interval**: Runs at custom intervals (e.g., every 6 hours, every 3 days)

### Settings

- **Max Papers per Run**: Limits how many new papers to process in each run (prevents overwhelming the system)
- **Enable/Disable**: Toggle scheduling on/off without deleting configuration
- **Job Name**: Descriptive name for tracking

## Monitoring

### View Run History

Check the Scheduling tab in the Data Sources section to view:
- Last run time
- Next scheduled run
- Total runs, successful runs, failed runs
- Detailed history of recent runs with statistics

### Logs

Monitor the scheduler logs in Replit:
- Go to the Deployments section
- View logs for the scheduler workflow
- Look for success/error messages

## Troubleshooting

### Common Issues

1. **No papers processed**:
   - Check that `last_processed_row` is less than total rows in the sheet
   - Verify the data source is active
   - Ensure the scheduled job is enabled

2. **Google credentials error**:
   - Verify `GOOGLE_CREDENTIALS_PATH` is set correctly
   - Check that the service account JSON file exists at that path
   - Ensure the service account has access to the Google Sheets

3. **API key errors**:
   - Verify all required API keys are set as environment variables
   - Check API key permissions and quotas

4. **Scheduler not running**:
   - Check the cron schedule in `.replit` file
   - Verify the deployment is active
   - Look for errors in deployment logs

## Best Practices

1. **Start with Small Batches**: Set `max_papers_per_run` to a small number initially (e.g., 10-50)
2. **Monitor First Runs**: Watch the first few automated runs to ensure everything works
3. **Schedule During Off-Peak**: For large batches, schedule during low-traffic hours
4. **Enable Deduplication**: Always keep deduplication layers enabled to save costs
5. **Review Run History**: Regularly check run history to catch and fix issues early

## Example Workflow

1. **Setup Data Source**: Create a Google Sheet with papers, configure in the app
2. **Configure Schedule**: Go to Scheduling tab, set up daily run at 2 AM
3. **Set Max Papers**: Limit to 100 papers per run
4. **Enable Schedule**: Turn on the scheduled job
5. **Monitor**: Check run history daily for the first week
6. **Adjust**: Fine-tune schedule and batch size based on results

## Security Notes

- Google service account credentials are sensitive - never commit them to version control
- Use Replit's secrets management for all API keys
- Regularly rotate API keys and service account credentials
- Review access permissions on Google Sheets regularly
