-- Migration: Add Loop Detection and Budget Guard fields
-- Date: 2025-01-05
-- Description: Adds retry tracking, budget warnings, and stall detection fields

-- JobModel: Loop & Budget Tracking
ALTER TABLE jobs ADD COLUMN retry_count INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN last_failed_step_id TEXT;
ALTER TABLE jobs ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN budget_warnings_sent TEXT DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN replan_count INTEGER DEFAULT 0;
ALTER TABLE jobs ADD COLUMN last_progress_at TIMESTAMP;

-- JobStepModel: Retry & Edit Tracking
ALTER TABLE job_steps ADD COLUMN retry_count INTEGER DEFAULT 0;
ALTER TABLE job_steps ADD COLUMN edit_history TEXT DEFAULT '[]';
ALTER TABLE job_steps ADD COLUMN failure_reason TEXT;
