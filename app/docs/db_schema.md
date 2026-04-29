# Database schema 

## Table: tasks

| Field | Description | Type | Nullable |  Unique | Primary Key |
| --- | --- | --- | --- | --- | --- |
| `id` | Unique identifier for each task (Primary Key) | INTEGER | False | None | True |
| `uuid` | Universally unique identifier for each task | VARCHAR | False | None | False |
| `status` | Current status of the task | VARCHAR | False | None | False |
| `result` | JSON data representing the result of the task | JSON | True | None | False |
| `file_name` | Name of the file associated with the task | VARCHAR | True | None | False |
| `url` | URL of the file associated with the task | VARCHAR | True | None | False |
| `callback_url` | Callback URL to POST results to | VARCHAR | True | None | False |
| `audio_duration` | Duration of the audio in seconds | FLOAT | True | None | False |
| `language` | Language of the file associated with the task | VARCHAR | True | None | False |
| `task_type` | Type/category of the task | VARCHAR | False | None | False |
| `task_params` | Parameters of the task | JSON | True | None | False |
| `duration` | Duration of the task execution | FLOAT | True | None | False |
| `start_time` | Start time of the task execution | DATETIME | True | None | False |
| `end_time` | End time of the task execution | DATETIME | True | None | False |
| `error` | Error message, if any, associated with the task | VARCHAR | True | None | False |
| `created_at` | Date and time of creation (UTC, tz-aware) | DATETIME | False | None | False |
| `updated_at` | Date and time of last update (UTC, tz-aware) | DATETIME | False | None | False |
| `progress_percentage` | Current progress percentage (0-100) | INTEGER | True | None | False |
| `progress_stage` | Current processing stage (queued, transcribing, aligning, diarizing, complete) | VARCHAR | True | None | False |
| `user_id` | Owning user (nullable until Phase 12 backfill) | INTEGER | True | None | False |
## Table: users

| Field | Description | Type | Nullable |  Unique | Primary Key |
| --- | --- | --- | --- | --- | --- |
| `id` | Unique identifier for each user (Primary Key) | INTEGER | False | None | True |
| `email` | User email address (unique, login identifier) | VARCHAR | False | True | False |
| `password_hash` | Argon2id hash of the user's password | VARCHAR | False | None | False |
| `plan_tier` | Subscription tier (free/trial/pro/team) | VARCHAR | False | None | False |
| `stripe_customer_id` | Stripe customer ID (populated in v1.3) | VARCHAR | True | True | False |
| `token_version` | Token version for logout-all-devices invalidation | INTEGER | False | None | False |
| `trial_started_at` | When the 7-day trial counter started (first API key) | DATETIME | True | None | False |
| `created_at` | Date and time of creation (UTC, tz-aware) | DATETIME | False | None | False |
| `updated_at` | Date and time of last update (UTC, tz-aware) | DATETIME | False | None | False |
## Table: api_keys

| Field | Description | Type | Nullable |  Unique | Primary Key |
| --- | --- | --- | --- | --- | --- |
| `id` | Unique identifier for each API key (Primary Key) | INTEGER | False | None | True |
| `user_id` | Owning user (FK → users.id) | INTEGER | False | None | False |
| `name` | User-supplied label for the API key | VARCHAR | False | None | False |
| `prefix` | First 8 chars of the API key (indexed for bearer lookup) | VARCHAR(8) | False | None | False |
| `hash` | SHA-256 hex digest of the full key | VARCHAR(64) | False | None | False |
| `scopes` | Comma-separated scopes (default: transcribe) | VARCHAR | False | None | False |
| `created_at` | Date and time of creation (UTC, tz-aware) | DATETIME | False | None | False |
| `last_used_at` | When the key was most recently presented (UTC, tz-aware) | DATETIME | True | None | False |
| `revoked_at` | Soft-delete timestamp; NULL means active (UTC, tz-aware) | DATETIME | True | None | False |
## Table: subscriptions

| Field | Description | Type | Nullable |  Unique | Primary Key |
| --- | --- | --- | --- | --- | --- |
| `id` | Unique identifier for each subscription (Primary Key) | INTEGER | False | None | True |
| `user_id` | Owning user (FK → users.id) | INTEGER | False | None | False |
| `stripe_subscription_id` | Stripe subscription ID (populated by webhook in v1.3) | VARCHAR | True | True | False |
| `plan` | Stripe plan/price identifier | VARCHAR | True | None | False |
| `status` | Stripe subscription status string | VARCHAR | True | None | False |
| `current_period_start` | Subscription period start (UTC, tz-aware) | DATETIME | True | None | False |
| `current_period_end` | Subscription period end (UTC, tz-aware) | DATETIME | True | None | False |
| `cancelled_at` | Soft-cancel timestamp (UTC, tz-aware) | DATETIME | True | None | False |
| `created_at` | Date and time of creation (UTC, tz-aware) | DATETIME | False | None | False |
| `updated_at` | Date and time of last update (UTC, tz-aware) | DATETIME | False | None | False |
## Table: usage_events

| Field | Description | Type | Nullable |  Unique | Primary Key |
| --- | --- | --- | --- | --- | --- |
| `id` | Unique identifier for each usage event (Primary Key) | INTEGER | False | None | True |
| `user_id` | Owning user (FK → users.id) | INTEGER | False | None | False |
| `task_id` | Originating task (FK → tasks.id) | INTEGER | True | None | False |
| `gpu_seconds` | GPU compute seconds consumed | FLOAT | True | None | False |
| `file_seconds` | Audio file duration in seconds | FLOAT | True | None | False |
| `model` | Model identifier used for this transcription | VARCHAR | True | None | False |
| `idempotency_key` | UNIQUE key for Stripe webhook replay safety | VARCHAR | False | True | False |
| `created_at` | Date and time of creation (UTC, tz-aware) | DATETIME | False | None | False |
## Table: rate_limit_buckets

| Field | Description | Type | Nullable |  Unique | Primary Key |
| --- | --- | --- | --- | --- | --- |
| `id` | Unique identifier for each bucket (Primary Key) | INTEGER | False | None | True |
| `bucket_key` | Unique bucket identifier (e.g. user:42:hour) | VARCHAR | False | True | False |
| `tokens` | Remaining tokens in the bucket | INTEGER | False | None | False |
| `last_refill` | Last refill timestamp (UTC, tz-aware) | DATETIME | False | None | False |
## Table: device_fingerprints

| Field | Description | Type | Nullable |  Unique | Primary Key |
| --- | --- | --- | --- | --- | --- |
| `id` | Unique identifier for each fingerprint (Primary Key) | INTEGER | False | None | True |
| `user_id` | Owning user (FK → users.id) | INTEGER | False | None | False |
| `cookie_hash` | SHA-256 hash of the session cookie value | VARCHAR(64) | False | None | False |
| `ua_hash` | SHA-256 hash of the User-Agent header | VARCHAR(64) | False | None | False |
| `ip_subnet` | IP /24 (IPv4) or /64 (IPv6) prefix | VARCHAR | False | None | False |
| `device_id` | Browser-stored UUID (localStorage) | VARCHAR | False | None | False |
| `created_at` | Date and time of creation (UTC, tz-aware) | DATETIME | False | None | False |
