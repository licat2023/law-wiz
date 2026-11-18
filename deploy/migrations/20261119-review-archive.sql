-- Apply once to an existing business database before starting the archive-enabled backend.
ALTER TABLE review_task
    ADD COLUMN archived_at DATETIME(3) NULL AFTER finished_at,
    ADD INDEX idx_review_task_user_archive (user_id, archived_at, created_at);

ALTER TABLE file_object
    ADD COLUMN purge_requested_at DATETIME(3) NULL AFTER deleted_at,
    ADD INDEX idx_file_pending_purge (purge_requested_at, id);
