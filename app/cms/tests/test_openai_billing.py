from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from cms.models import LLMUsageRecord, Media, OpenAIBillingSync, OpenAICreditEntry, OpenAIDailyCost
from cms.openai_billing import BillingSyncError, billing_summary, sync_costs

UTC = dt_timezone.utc
NOW = datetime(2026, 9, 20, 12, tzinfo=UTC)
SETTINGS = dict(
    OPENAI_ADMIN_KEY="test-admin-secret", OPENAI_ORG_ID="org-test", OPENAI_PROJECT_ID="proj-app",
    LLM_USAGE_MONTHLY_BUDGET_USD=Decimal("120"), LLM_BILLING_STALE_HOURS=24,
    LLM_BALANCE_STALE_DAYS=30, LLM_CREDIT_WARNING_DAYS=14, LLM_CREDIT_URGENT_DAYS=7,
    LLM_PURCHASE_LEAD_DAYS=7,
)


def page(day, amounts, *, has_more=False, next_page=None):
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return {"data": [{"start_time": int(start.timestamp()),
                      "end_time": int((start + timedelta(days=1)).timestamp()),
                      "results": [{"project_id": project, "amount": {"value": value, "currency": "usd"}}
                                  for project, value in amounts]}],
            "has_more": has_more, "next_page": next_page}


def response(payload, status=200):
    return Mock(status_code=status, json=Mock(return_value=payload))


@override_settings(**SETTINGS)
class CostSyncTests(TestCase):
    def setUp(self):
        timer = patch("cms.openai_billing.timezone.now", return_value=NOW)
        timer.start()
        self.addCleanup(timer.stop)

    @patch("cms.openai_billing.requests.get")
    def test_pagination_corrections_and_organization_scope(self, get):
        first = page(NOW - timedelta(days=2), [("proj-app", "1.125"), (None, "0.005")],
                     has_more=True, next_page="next")
        second = page(NOW - timedelta(days=1), [("proj-other", "2")])
        calls = []

        def fetch(url, **kwargs):
            calls.append(dict(kwargs["params"]))
            return response(second if "page" in kwargs["params"] else first)

        get.side_effect = fetch
        state = sync_costs()
        self.assertEqual(OpenAIDailyCost.objects.count(), 3)
        self.assertEqual(calls[1]["page"], "next")
        self.assertNotIn("project_ids", calls[0])
        self.assertEqual(get.call_args.kwargs["headers"]["OpenAI-Organization"], "org-test")
        self.assertEqual(state.costs_through, NOW)
        other = OpenAIDailyCost.objects.create(organization_id="org-other", project_id="proj-app",
                                             day=NOW.date(), amount_usd=99)
        get.side_effect = None
        get.return_value = response(page(NOW - timedelta(days=1), [("proj-app", "3.2")]))
        sync_costs()
        sync_costs()
        self.assertEqual(OpenAIDailyCost.objects.filter(organization_id="org-test").count(), 1)
        self.assertEqual(OpenAIDailyCost.objects.get(organization_id="org-test").amount_usd, Decimal("3.2"))
        self.assertTrue(OpenAIDailyCost.objects.filter(pk=other.pk).exists())

    @patch("cms.openai_billing.requests.get")
    def test_exact_balance_time_and_all_projects(self, get):
        verified = NOW - timedelta(days=2, hours=3)
        balance = OpenAICreditEntry.objects.create(organization_id="org-test", kind="balance",
                                                  amount_usd=100, effective_at=verified, note="Verified")
        get.side_effect = [response(page(NOW - timedelta(days=2), [("proj-app", "10")])),
                           response(page(NOW - timedelta(days=2), [("proj-app", "1"), ("other", "4")]))]
        state = sync_costs()
        self.assertEqual(get.call_args.kwargs["params"]["start_time"], int(verified.timestamp()))
        self.assertEqual(state.balance_entry_id, balance.pk)
        self.assertEqual(state.spend_since_balance_usd, 5)

    @patch("cms.openai_billing.requests.get")
    def test_failed_later_page_preserves_previous_snapshot_and_sanitizes_error(self, get):
        old = NOW - timedelta(hours=1)
        state = OpenAIBillingSync.objects.create(organization_id="org-test", costs_through=old,
                                                last_success_at=old, coverage_start=old.date())
        cost = OpenAIDailyCost.objects.create(organization_id="org-test", project_id="proj-app",
                                             day=old.date(), amount_usd=9)
        get.side_effect = [response(page(NOW, [("proj-app", "2")], has_more=True, next_page="p2")),
                           requests.Timeout("test-admin-secret")]
        with self.assertRaises(BillingSyncError):
            sync_costs()
        state.refresh_from_db()
        cost.refresh_from_db()
        self.assertEqual(state.costs_through, old)
        self.assertEqual(state.last_success_at, old)
        self.assertEqual(cost.amount_usd, 9)
        self.assertNotIn("test-admin-secret", state.last_error)
        self.assertIn("could not connect", state.last_error)

    @patch("cms.openai_billing.requests.get")
    def test_invalid_data_is_not_imported(self, get):
        for amount in ("NaN", "Infinity", None, "not money"):
            with self.subTest(amount=amount):
                get.return_value = response(page(NOW, [("proj-app", amount)]))
                with self.assertRaises(BillingSyncError):
                    sync_costs()
        payload = page(NOW, [("proj-app", "1")])
        payload["data"][0]["results"][0]["amount"]["currency"] = "eur"
        get.return_value = response(payload)
        with self.assertRaises(BillingSyncError):
            sync_costs()
        self.assertFalse(OpenAIDailyCost.objects.exists())
        self.assertIsNone(OpenAIBillingSync.objects.get().last_success_at)

    @patch("cms.openai_billing.requests.get")
    def test_repeated_cursor_is_rejected(self, get):
        get.side_effect = [response(page(NOW - timedelta(days=1), [], has_more=True, next_page="same")),
                           response(page(NOW, [], has_more=True, next_page="same"))]
        with self.assertRaises(BillingSyncError):
            sync_costs()

    @patch("cms.openai_billing.requests.get")
    def test_empty_success_means_zero_and_clears_previous_error(self, get):
        OpenAIBillingSync.objects.create(organization_id="org-test", last_error="old failure")
        get.return_value = response({"data": [], "has_more": False, "next_page": None})
        state = sync_costs()
        self.assertEqual(state.last_error, "")
        summary = billing_summary(NOW.date(), NOW.date(), now=NOW)
        self.assertEqual(summary["reported_cost"], 0)
        self.assertEqual(summary["average_7"], 0)
        self.assertIsNone(summary["remaining_credit"])

    @override_settings(OPENAI_ADMIN_KEY="")
    @patch("cms.openai_billing.requests.get")
    def test_missing_config_does_not_call_api(self, get):
        with self.assertRaises(CommandError):
            call_command("sync_openai_costs", stdout=StringIO())
        get.assert_not_called()

    @patch("cms.openai_billing.requests.get")
    def test_balance_query_failure_does_not_replace_daily_costs(self, get):
        balance = OpenAICreditEntry.objects.create(
            organization_id="org-test", kind="balance", amount_usd=100,
            effective_at=NOW - timedelta(days=1), note="Verified",
        )
        old = NOW - timedelta(hours=1)
        state = OpenAIBillingSync.objects.create(
            organization_id="org-test", costs_through=old, coverage_start=old.date(),
            balance_entry=balance, spend_since_balance_usd=2,
        )
        get.side_effect = [response(page(NOW, [("proj-app", "9")])), response({}, status=403)]
        with self.assertRaises(BillingSyncError):
            sync_costs()
        state.refresh_from_db()
        self.assertEqual(state.costs_through, old)
        self.assertEqual(state.spend_since_balance_usd, 2)
        self.assertFalse(OpenAIDailyCost.objects.exists())
        self.assertIn("403", state.last_error)

    @patch("cms.openai_billing.requests.get")
    def test_future_backfill_rejected(self, get):
        with self.assertRaises(BillingSyncError):
            sync_costs(start_date=(NOW + timedelta(days=1)).date())
        get.assert_not_called()

    @patch("cms.openai_billing.requests.get")
    def test_command_backfill(self, get):
        get.return_value = response({"data": [], "has_more": False})
        output = StringIO()
        call_command("sync_openai_costs", "--since", "2026-07-01", stdout=output)
        self.assertEqual(OpenAIBillingSync.objects.get().coverage_start.isoformat(), "2026-07-01")
        self.assertIn("synchronized", output.getvalue())


@override_settings(**SETTINGS)
class BillingSummaryTests(TestCase):
    def setUp(self):
        self.balance = OpenAICreditEntry.objects.create(
            organization_id="org-test", kind="balance", amount_usd=100,
            effective_at=NOW - timedelta(days=5), note="Verified in billing",
        )
        self.state = OpenAIBillingSync.objects.create(
            organization_id="org-test", coverage_start=(NOW - timedelta(days=35)).date(),
            costs_through=NOW, last_success_at=NOW, balance_entry=self.balance, spend_since_balance_usd=20,
        )
        for days in range(1, 31):
            for project, amount in [("proj-app", 1), ("proj-other", 3)]:
                OpenAIDailyCost.objects.create(organization_id="org-test", project_id=project,
                                               day=(NOW - timedelta(days=days)).date(), amount_usd=amount)
        OpenAIDailyCost.objects.create(organization_id="org-test", project_id="proj-app",
                                       day=NOW.date(), amount_usd=5)
        OpenAIDailyCost.objects.create(organization_id="other-org", project_id="proj-app",
                                       day=NOW.date(), amount_usd=999)

    def summary(self, **kwargs):
        return billing_summary(NOW.date() - timedelta(days=30), NOW.date(), now=NOW, **kwargs)

    def test_scope_and_forecast(self):
        summary = self.summary()
        self.assertEqual(summary["reported_cost"], 35)
        self.assertEqual(summary["month_cost"], 24)
        self.assertEqual(summary["budget_progress"], 20)
        self.assertEqual(summary["budget_remaining"], 96)
        self.assertEqual(summary["remaining_credit"], 80)
        self.assertEqual(summary["average_7"], 4)
        self.assertEqual(summary["average_30"], 4)
        self.assertEqual(summary["days_remaining"], 20)
        self.assertEqual(summary["purchase_date"], (NOW + timedelta(days=13)).date())
        self.assertEqual(summary["status"], "ok")

    def test_history_and_model_filters_do_not_change_current_status(self):
        normal = self.summary()
        filtered = billing_summary(NOW.date() - timedelta(days=30), NOW.date() - timedelta(days=20),
                                   model_name="gpt-4o", now=NOW)
        self.assertIsNone(filtered["reported_cost"])
        for key in ("remaining_credit", "days_remaining", "month_cost", "budget_progress"):
            self.assertEqual(filtered[key], normal[key])

    def test_ledger_adjustments_and_baseline_boundary(self):
        for offset, amount, org in [(-6, 999, "org-test"), (-4, 50, "org-test"),
                                    (-3, -10, "org-test"), (1, 999, "org-test"), (-2, 999, "other-org")]:
            OpenAICreditEntry.objects.create(organization_id=org, kind="adjustment", amount_usd=amount,
                                             effective_at=NOW + timedelta(days=offset), note="Adjustment")
        self.assertEqual(self.summary()["remaining_credit"], 120)

    def test_new_baseline_requires_sync(self):
        OpenAICreditEntry.objects.create(organization_id="org-test", kind="balance", amount_usd=200,
                                         effective_at=NOW - timedelta(days=1), note="Recheck")
        self.assertIsNone(self.summary()["remaining_credit"])
        self.assertIsNone(self.summary()["days_remaining"])

    def test_stale_or_failed_sync_suppresses_forecast(self):
        self.state.last_error = "Could not connect"
        self.state.save()
        self.assertIsNone(self.summary()["days_remaining"])
        self.state.last_error = ""
        self.state.costs_through = NOW - timedelta(days=2)
        self.state.save()
        self.assertTrue(self.summary()["stale"])
        self.assertIsNone(self.summary()["days_remaining"])

    @override_settings(LLM_BALANCE_STALE_DAYS=3)
    def test_old_balance_suppresses_forecast(self):
        self.assertIsNone(self.summary()["days_remaining"])
        self.assertIn("Verify", self.summary()["forecast_reason"])

    def test_zero_spend_is_not_infinite_credit(self):
        OpenAIDailyCost.objects.filter(organization_id="org-test").delete()
        self.assertEqual(self.summary()["average_7"], 0)
        self.assertIsNone(self.summary()["days_remaining"])

    def test_insufficient_coverage_is_not_zero(self):
        self.state.coverage_start = (NOW - timedelta(days=3)).date()
        self.state.save()
        summary = self.summary()
        self.assertIsNone(summary["reported_cost"])
        self.assertIsNone(summary["average_7"])
        self.assertIsNone(summary["days_remaining"])

    def test_alert_thresholds_and_exhausted_credit(self):
        for spend, days, status in [(44, 14, "warning"), (72, 7, "urgent"), (100, 0, "urgent"), (110, 0, "urgent")]:
            self.state.spend_since_balance_usd = spend
            self.state.save()
            with self.subTest(spend=spend):
                summary = self.summary()
                self.assertEqual(summary["days_remaining"], days)
                self.assertEqual(summary["status"], status)

    def test_higher_recent_rate_used_and_idle_days_count(self):
        OpenAIDailyCost.objects.filter(organization_id="org-test").delete()
        OpenAIDailyCost.objects.create(organization_id="org-test", project_id="proj-app",
                                       day=(NOW - timedelta(days=1)).date(), amount_usd=70)
        summary = self.summary()
        self.assertEqual(summary["average_7"], 10)
        self.assertEqual(summary["days_remaining"], 8)

    @override_settings(OPENAI_PROJECT_ID="")
    def test_no_project_does_not_mislabel_org_spend(self):
        self.assertIsNone(self.summary()["reported_cost"])
        self.assertIsNone(self.summary()["month_cost"])
        self.assertEqual(self.summary()["remaining_credit"], 80)


@override_settings(**SETTINGS)
class BillingReportTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(username="billing-staff", is_staff=True)
        self.url = reverse("admin-chatgpt-usage")
        user_patch = patch("cms.models.get_current_user", return_value=self.staff)
        user_patch.start()
        self.addCleanup(user_patch.stop)

    @patch("cms.openai_billing.requests.get")
    def test_report_renders_without_network_or_fake_balance(self, get):
        self.client.force_login(self.staff)
        media = Media.objects.create(media_location="uploads/report.png")
        LLMUsageRecord.objects.create(media=media, model_name="gpt-4o", prompt_tokens=100,
                                      completion_tokens=20, total_tokens=120, remaining_quota_usd=999)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "120")
        self.assertContains(response, "OpenAI-reported project cost")
        self.assertNotContains(response, "Remaining quota")
        self.assertNotContains(response, "$999")
        self.assertNotContains(response, "Record balance or top-up")
        self.assertIsNone(response.context["billing"]["remaining_credit"])
        get.assert_not_called()

    def test_anonymous_and_nonstaff_cannot_access_report(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.staff.is_staff = False
        self.staff.save()
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    @patch("cms.openai_billing.timezone.now", return_value=NOW)
    def test_forecast_and_budget_render_and_filters_are_independent(self, now):
        self.client.force_login(self.staff)
        balance = OpenAICreditEntry.objects.create(
            organization_id="org-test", kind="balance", amount_usd=20,
            effective_at=NOW - timedelta(days=5), note="Verified",
        )
        OpenAIBillingSync.objects.create(
            organization_id="org-test", coverage_start=(NOW - timedelta(days=35)).date(),
            costs_through=NOW, last_success_at=NOW, balance_entry=balance, spend_since_balance_usd=10,
        )
        OpenAIDailyCost.objects.create(organization_id="org-test", project_id="proj-app",
                                       day=(NOW - timedelta(days=1)).date(), amount_usd=14)
        response = self.client.get(self.url)
        self.assertContains(response, "5.0 days")
        self.assertContains(response, "Urgent:")
        self.assertContains(response, "$10.00")
        historical = self.client.get(self.url, {"start_date": "2026-01-01", "end_date": "2026-01-02"})
        self.assertContains(historical, "5.0 days")
        self.assertIsNone(historical.context["billing"]["reported_cost"])
        self.assertEqual(historical.context["billing"]["month_cost"], 14)

    def test_ledger_admin_requires_permission(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:cms_openaicreditentry_add")).status_code, 403)
        self.staff.is_superuser = True
        self.staff.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Record balance or top-up")
        response = self.client.get(reverse("admin:cms_openaicreditentry_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "org-test")

    def test_credit_entries_validate_and_admin_is_append_only(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        entry = OpenAICreditEntry(organization_id="org-test", kind="balance", amount_usd=-1,
                                  effective_at=NOW - timedelta(days=1), note="Check")
        with self.assertRaises(ValidationError):
            entry.full_clean()
        entry.kind = "adjustment"
        entry.full_clean()
        entry.effective_at = datetime.now(UTC) + timedelta(days=1)
        with self.assertRaises(ValidationError):
            entry.full_clean()
        request = RequestFactory().get("/")
        self.staff.is_superuser = True
        request.user = self.staff
        admin = site._registry[OpenAICreditEntry]
        self.assertFalse(admin.has_change_permission(request, entry))
        self.assertFalse(admin.has_delete_permission(request, entry))
