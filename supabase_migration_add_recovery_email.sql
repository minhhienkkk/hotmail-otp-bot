alter table public.accounts
add column if not exists recovery_email text;
