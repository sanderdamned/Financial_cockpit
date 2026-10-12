-- Add editable expense frequency and original planned amount to category budgets.
-- Safe to run repeatedly in Supabase SQL Editor.
alter table public.budgets
    add column if not exists budget_type text not null default 'monthly',
    add column if not exists period_months integer not null default 1,
    add column if not exists planned_amount numeric(14,2);

-- Existing budgets were monthly limits, so preserve their current meaning.
update public.budgets
set planned_amount = monthly_limit
where planned_amount is null;

alter table public.budgets
    alter column planned_amount set default 0,
    alter column planned_amount set not null;

alter table public.budgets
    drop constraint if exists budgets_budget_type_check;

alter table public.budgets
    add constraint budgets_budget_type_check
    check (budget_type in ('monthly', 'periodic', 'annual'));

alter table public.budgets
    drop constraint if exists budgets_period_months_check;

alter table public.budgets
    add constraint budgets_period_months_check
    check (period_months between 1 and 12);
