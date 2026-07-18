begin;

-- Logs created before the integrated pipeline used UUID/varchar ids.  Archive
-- that table instead of performing a lossy cast.  The archive is intentionally
-- read-only from application code.
do $migration$
declare
    current_id_type text;
    legacy_constraint text;
begin
    select data_type
      into current_id_type
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'LogsAgent'
       and column_name = 'id';

    if current_id_type is not null and current_id_type <> 'bigint' then
        if to_regclass('public."LogsAgent_legacy_uuid"') is not null then
            raise exception
                'LogsAgent still has a non-bigint id and LogsAgent_legacy_uuid already exists';
        end if;

        alter table public."LogsAgent" rename to "LogsAgent_legacy_uuid";

        select conname
          into legacy_constraint
          from pg_constraint
         where conrelid = 'public."LogsAgent_legacy_uuid"'::regclass
           and contype = 'p'
         limit 1;
        if legacy_constraint is not null then
            execute format(
                'alter table public."LogsAgent_legacy_uuid" rename constraint %I to %I',
                legacy_constraint,
                'LogsAgent_legacy_uuid_pkey'
            );
        end if;
    end if;
end
$migration$;

create table if not exists public."LogsAgent" (
    id bigint primary key,
    "FinanceLogs" jsonb,
    "RiskLogs" jsonb,
    "DecisionLogs" jsonb,
    "ValidatorLogs" jsonb,
    created_at timestamptz not null default now()
);

comment on table public."LogsAgent" is
    'Operational logs only. Handoff data lives in public.context.';
comment on column public."LogsAgent".id is
    'Same bigint identifier as public.context.session_id for one pipeline run.';

-- Logs contain tool arguments and operational context.  Direct PostgreSQL
-- service connections continue to work; unauthenticated Data API access does not.
alter table public."LogsAgent" enable row level security;

commit;
