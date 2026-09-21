"""Provider-reported spending and explicitly estimated prepaid credit.

The report never makes network calls. A scheduled command refreshes a complete
snapshot, including spending outside this application's project.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import OpenAIBillingSync, OpenAICreditEntry, OpenAIDailyCost

UTC = dt_timezone.utc
ZERO = Decimal("0")


class BillingSyncError(Exception):
    """Credential-free error suitable for report and command output."""


def _fetch_costs(start, end, organization_id):
    """Fetch all pages without project filtering; reject invalid financial data."""
    params = {
        "start_time": int(start.timestamp()), "end_time": int(end.timestamp()),
        "bucket_width": "1d", "group_by": ["project_id"], "limit": 180,
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_ADMIN_KEY}",
        "OpenAI-Organization": organization_id,
    }
    rows = defaultdict(lambda: ZERO)
    seen_pages = set()
    seen_buckets = set()
    while True:
        try:
            response = requests.get(
                "https://api.openai.com/v1/organization/costs",
                params=params, headers=headers, timeout=(10, 60), allow_redirects=False,
            )
        except requests.RequestException:
            raise BillingSyncError("OpenAI cost synchronization could not connect. Retry the sync.") from None
        if response.status_code != 200:
            raise BillingSyncError(f"OpenAI cost synchronization returned HTTP {response.status_code}.")
        try:
            payload = response.json(parse_float=Decimal)
            if not isinstance(payload["data"], list) or not isinstance(payload["has_more"], bool):
                raise ValueError
            for bucket in payload["data"]:
                bucket_start = datetime.fromtimestamp(bucket["start_time"], UTC)
                bucket_end = datetime.fromtimestamp(bucket["end_time"], UTC)
                # Buckets may straddle the exact query boundaries.
                if bucket_end <= start or bucket_start >= end or bucket_end <= bucket_start:
                    raise ValueError
                if bucket["start_time"] in seen_buckets:
                    raise ValueError
                seen_buckets.add(bucket["start_time"])
                if not isinstance(bucket["results"], list):
                    raise ValueError
                for result in bucket["results"]:
                    amount = result["amount"]
                    if amount["currency"] != "usd" or amount["value"] is None:
                        raise ValueError
                    value = Decimal(str(amount["value"]))
                    if not value.is_finite() or abs(value) >= Decimal("1000000000000"):
                        raise ValueError
                    project = result["project_id"] if result["project_id"] is not None else ""
                    if not isinstance(project, str) or len(project) > 255:
                        raise ValueError
                    rows[(bucket_start.date(), project)] += value
            if not payload["has_more"]:
                break
            page = payload["next_page"]
            if not isinstance(page, str) or not page or page in seen_pages:
                raise ValueError
            seen_pages.add(page)
            params["page"] = page
        except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError, OSError):
            raise BillingSyncError("OpenAI returned invalid or unsupported cost data; previous data retained.") from None
    return rows


def sync_costs(*, start_date=None):
    organization = settings.OPENAI_ORG_ID
    if not organization or not settings.OPENAI_ADMIN_KEY:
        raise BillingSyncError("Configure OPENAI_ORG_ID and OPENAI_ADMIN_KEY to synchronize costs.")
    now = timezone.now().astimezone(UTC).replace(microsecond=0)
    if start_date and start_date > now.date():
        raise BillingSyncError("The backfill start date cannot be in the future.")
    state, _ = OpenAIBillingSync.objects.get_or_create(organization_id=organization)
    # Re-fetch prior coverage so delayed charges/corrections replace old values.
    start_day = min(filter(None, [start_date, state.coverage_start, now.date() - timedelta(days=35)]))
    start = datetime.combine(start_day, time.min, UTC)
    balance = OpenAICreditEntry.objects.filter(
        organization_id=organization, kind=OpenAICreditEntry.Kind.BALANCE,
        effective_at__lt=now,
    ).first()
    try:
        daily = _fetch_costs(start, now, organization)
        spend_since_balance = None
        if balance:
            # Query the verification time, rather than prorating a daily bucket.
            balance_costs = _fetch_costs(balance.effective_at.replace(microsecond=0), now, organization)
            spend_since_balance = sum(balance_costs.values(), ZERO)
    except BillingSyncError as exc:
        OpenAIBillingSync.objects.filter(pk=state.pk).update(last_error=str(exc))
        raise
    with transaction.atomic():
        state = OpenAIBillingSync.objects.select_for_update().get(pk=state.pk)
        if state.costs_through and state.costs_through > now:
            return state  # A newer overlapping run already finished.
        OpenAIDailyCost.objects.filter(organization_id=organization, day__gte=start_day).delete()
        OpenAIDailyCost.objects.bulk_create([
            OpenAIDailyCost(organization_id=organization, day=day, project_id=project, amount_usd=amount)
            for (day, project), amount in daily.items()
        ])
        state.coverage_start = start_day
        state.costs_through = now
        state.last_success_at = timezone.now()
        state.last_error = ""
        state.balance_entry = balance
        state.spend_since_balance_usd = spend_since_balance
        state.save()
    return state


def billing_summary(start_date, end_date, *, model_name=None, now=None):
    now = (now or timezone.now()).astimezone(UTC)
    organization = settings.OPENAI_ORG_ID
    project = settings.OPENAI_PROJECT_ID
    state = OpenAIBillingSync.objects.filter(organization_id=organization).first() if organization else None
    balance = OpenAICreditEntry.objects.filter(
        organization_id=organization, kind=OpenAICreditEntry.Kind.BALANCE,
        effective_at__lte=now,
    ).first() if organization else None
    result = {
        "organization": organization, "project": project, "sync": state, "balance": balance,
        "reported_cost": None, "month_cost": None, "budget_progress": None,
        "budget_remaining": None, "remaining_credit": None, "days_remaining": None,
        "purchase_date": None, "average_7": None, "average_30": None,
        "status": "unavailable", "forecast_reason": "Synchronize OpenAI costs to enable forecasts.",
    }
    if not state or not state.costs_through:
        return result
    stale = now - state.costs_through > timedelta(hours=settings.LLM_BILLING_STALE_HOURS)
    result["stale"] = stale
    costs = OpenAIDailyCost.objects.filter(organization_id=organization)

    def total(first, last, *, project_only=False):
        if first < state.coverage_start or last > state.costs_through.date():
            return None
        qs = costs.filter(day__gte=first, day__lte=last)
        if project_only:
            if not project:
                return None
            qs = qs.filter(project_id=project)
        return qs.aggregate(value=Sum("amount_usd"))["value"] or ZERO

    if not model_name:
        result["reported_cost"] = total(start_date, end_date, project_only=True)
    result["month_cost"] = total(now.date().replace(day=1), now.date(), project_only=True)
    budget = Decimal(str(settings.LLM_USAGE_MONTHLY_BUDGET_USD or 0))
    if result["month_cost"] is not None and budget > 0:
        result["budget_progress"] = result["month_cost"] / budget * 100
        result["budget_remaining"] = budget - result["month_cost"]

    # Only complete UTC days contribute to the rate; idle days count too.
    day_end = min(now.date(), state.costs_through.date())
    for days in (7, 30):
        spend = total(day_end - timedelta(days=days), day_end - timedelta(days=1))
        if spend is not None:
            result[f"average_{days}"] = max(spend / days, ZERO)
    if not balance:
        result["forecast_reason"] = "Record a verified account balance to estimate remaining credit."
        return result
    if state.balance_entry_id != balance.pk or state.spend_since_balance_usd is None:
        result["forecast_reason"] = "Synchronize costs after recording the new balance."
        return result
    adjustments = OpenAICreditEntry.objects.filter(
        organization_id=organization, kind=OpenAICreditEntry.Kind.ADJUSTMENT,
        effective_at__gt=balance.effective_at, effective_at__lt=state.costs_through,
    ).aggregate(value=Sum("amount_usd"))["value"] or ZERO
    remaining = balance.amount_usd + adjustments - state.spend_since_balance_usd
    result["remaining_credit"] = remaining
    if stale or state.last_error:
        result["forecast_reason"] = "Cost data is stale or the latest sync failed. Refresh it before relying on a forecast."
        return result
    if now - balance.effective_at > timedelta(days=settings.LLM_BALANCE_STALE_DAYS):
        result["forecast_reason"] = "Verify the account balance again; the last check is too old."
        return result
    if remaining <= 0:
        result.update(days_remaining=ZERO, purchase_date=now.date(), status="urgent", forecast_reason="")
        return result
    if result["average_7"] is None:
        result["forecast_reason"] = "At least seven complete days of synchronized costs are needed."
        return result
    rate = max(result["average_7"], result["average_30"] or ZERO)
    if rate <= 0:
        result["forecast_reason"] = "No recent spending; a depletion date cannot be estimated."
        return result
    # Project forward from the spending snapshot for the forecast only.
    elapsed_days = Decimal(str((now - state.costs_through).total_seconds() / 86400))
    days_left = max(ZERO, remaining / rate - elapsed_days)
    result["days_remaining"] = days_left
    lead = settings.LLM_PURCHASE_LEAD_DAYS
    if days_left < 3650:  # Avoid overflowing dates for nearly idle accounts.
        result["purchase_date"] = now.date() + timedelta(days=max(0, int(days_left) - lead))
    result["status"] = ("urgent" if days_left <= settings.LLM_CREDIT_URGENT_DAYS else
                        "warning" if days_left <= settings.LLM_CREDIT_WARNING_DAYS else "ok")
    result["forecast_reason"] = ""
    return result
