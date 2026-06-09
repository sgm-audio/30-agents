"""
Invoice system: Zoho Invoice + Stripe Payment Links integration.
Provides ZohoInvoiceClient, StripePaymentLink, and InvoicePipeline.
"""
import time
import uuid
from typing import Any, Optional

import httpx
import structlog
from core.config import settings
from core.redis_client import get_redis

log = structlog.get_logger(__name__)

ZOHO_API_BASE = "https://invoice.zoho.com/api/v3"
STRIPE_API_BASE = "https://api.stripe.com/v1"
DEFAULT_DEAL_AMOUNT = 500
DEFAULT_CURRENCY = "CAD"
DEFAULT_TAX_RATE = 0.05


class ZohoInvoiceClient:
    """Async client for Zoho Invoice API."""

    def __init__(
        self,
        org_id: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.org_id = org_id
        self.api_token = api_token
        self.redis = get_redis()
        self._configured = bool(org_id and api_token)

    @property
    def configured(self) -> bool:
        return self._configured

    async def _request(self, method: str, path: str, json_data: Optional[dict] = None) -> dict:
        if not self.configured:
            return {"error": "Zoho Invoice not configured. Set ZOHO_ORG_ID and ZOHO_API_TOKEN."}
        url = f"{ZOHO_API_BASE}{path}"
        headers = {
            "Authorization": f"Zoho-oauthtoken {self.api_token}",
            "X-com-zoho-invoice-organizationid": self.org_id,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, json=json_data)
                else:
                    return {"error": f"Unsupported method: {method}"}
                if resp.status_code in (200, 201):
                    return resp.json()
                log.warning("zoho.request_failed", status=resp.status_code, body=resp.text[:300])
                return {"error": f"Zoho API error: {resp.status_code}", "detail": resp.text[:300]}
        except Exception as e:
            log.error("zoho.request_error", error=str(e))
            return {"error": str(e)}

    async def create_contact(self, name: str, email: str, company: Optional[str] = None) -> dict:
        data = {
            "contact_name": name,
            "contact_persons": [{"email": email}],
        }
        if company:
            data["company_name"] = company
        result = await self._request("POST", "/contacts", data)
        if "contact" in result:
            contact = result["contact"]
            await self.redis.set(f"zoho:contact:{contact['contact_id']}", contact)
            return contact
        return result

    async def create_invoice(self, contact_id: str, items: list[dict], notes: Optional[str] = None) -> dict:
        line_items = []
        for item in items:
            line_items.append({
                "name": item.get("name", "Service"),
                "rate": item.get("rate", DEFAULT_DEAL_AMOUNT),
                "quantity": item.get("quantity", 1),
            })
        data = {
            "customer_id": contact_id,
            "line_items": line_items,
            "currency_code": DEFAULT_CURRENCY,
            "notes": notes or "",
        }
        result = await self._request("POST", "/invoices", data)
        if "invoice" in result:
            invoice = result["invoice"]
            await self.redis.set(f"zoho:invoice:{invoice['invoice_id']}", invoice)
            return invoice
        return result

    async def send_invoice(self, invoice_id: str) -> dict:
        result = await self._request("POST", f"/invoices/{invoice_id}/email", {})
        return result

    async def get_invoice(self, invoice_id: str) -> Optional[dict]:
        cached = await self.redis.get(f"zoho:invoice:{invoice_id}")
        if cached:
            return cached
        result = await self._request("GET", f"/invoices/{invoice_id}")
        if "invoice" in result:
            await self.redis.set(f"zoho:invoice:{invoice_id}", result["invoice"])
            return result["invoice"]
        return result

    async def list_invoices(self, status: Optional[str] = None) -> list[dict]:
        params = ""
        if status:
            params = f"?status={status}"
        result = await self._request("GET", f"/invoices{params}")
        return result.get("invoices", [])

    async def mark_as_paid(self, invoice_id: str) -> dict:
        result = await self._request("POST", f"/invoices/{invoice_id}/payment", {
            "amount": 0,
            "date": time.strftime("%Y-%m-%d"),
        })
        return result


class StripePaymentLink:
    """Async client for Stripe Payment Links API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.redis = get_redis()
        self._configured = bool(api_key)

    @property
    def configured(self) -> bool:
        return self._configured

    async def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        if not self.configured:
            return {"error": "Stripe not configured. Set STRIPE_API_KEY in .env."}
        url = f"{STRIPE_API_BASE}{path}"
        auth = httpx.BasicAuth(self.api_key, "")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                if method == "GET":
                    resp = await client.get(url, auth=auth)
                elif method == "POST":
                    resp = await client.post(url, auth=auth, data=data)
                else:
                    return {"error": f"Unsupported method: {method}"}
                if resp.status_code in (200, 201):
                    return resp.json()
                log.warning("stripe.request_failed", status=resp.status_code, body=resp.text[:300])
                return {"error": f"Stripe API error: {resp.status_code}", "detail": resp.text[:300]}
        except Exception as e:
            log.error("stripe.request_error", error=str(e))
            return {"error": str(e)}

    async def create_payment_link(
        self, amount: float, description: str, customer_email: Optional[str] = None
    ) -> dict:
        amount_cents = int(amount * 100)
        data = {
            "line_items[0][price_data][currency]": DEFAULT_CURRENCY.lower(),
            "line_items[0][price_data][product_data][name]": description,
            "line_items[0][price_data][unit_amount]": str(amount_cents),
            "line_items[0][quantity]": "1",
        }
        if customer_email:
            data["customer_email"] = customer_email
        result = await self._request("POST", "/payment_links", data)
        if "id" in result:
            await self.redis.set(f"stripe:payment:{result['id']}", result)
        return result

    async def create_customer(self, email: str, name: str, metadata: Optional[dict] = None) -> dict:
        data = {"email": email, "name": name}
        if metadata:
            for k, v in metadata.items():
                data[f"metadata[{k}]"] = str(v)
        result = await self._request("POST", "/customers", data)
        return result

    async def list_payments(self, limit: int = 100) -> list[dict]:
        result = await self._request("GET", f"/payment_intents?limit={limit}")
        return result.get("data", [])


class InvoicePipeline:
    """Chains Zoho + Stripe to create invoices with payment links from leads."""

    def __init__(
        self,
        zoho_org_id: Optional[str] = None,
        zoho_token: Optional[str] = None,
        stripe_key: Optional[str] = None,
    ):
        self.zoho = ZohoInvoiceClient(org_id=zoho_org_id, api_token=zoho_token)
        self.stripe = StripePaymentLink(api_key=stripe_key)
        self.redis = get_redis()

    async def deal_to_invoice(self, lead: dict, items: Optional[list[dict]] = None) -> dict:
        if not items:
            items = [{"name": "Website Redesign", "rate": DEFAULT_DEAL_AMOUNT, "quantity": 1}]

        name = lead.get("name", "Unknown")
        email = lead.get("email", "")
        company = lead.get("name", "")

        total = sum(item.get("rate", 0) * item.get("quantity", 1) for item in items)

        pipeline_id = str(uuid.uuid4())
        state = {
            "pipeline_id": pipeline_id,
            "lead_name": name,
            "lead_email": email,
            "items": items,
            "total": total,
            "status": "started",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        contact = await self.zoho.create_contact(name, email, company)
        if "error" in contact:
            state["status"] = "contact_failed"
            state["error"] = contact["error"]
            await self.redis.set(f"invoice:pipeline:{pipeline_id}", state, ex=90 * 86400)
            return state

        state["contact_id"] = contact.get("contact_id")
        state["status"] = "contact_created"

        invoice = await self.zoho.create_invoice(contact["contact_id"], items, notes="Generated by 30-Agent System")
        if "error" in invoice:
            state["status"] = "invoice_failed"
            state["error"] = invoice["error"]
            await self.redis.set(f"invoice:pipeline:{pipeline_id}", state, ex=90 * 86400)
            return state

        state["invoice_id"] = invoice.get("invoice_id")
        state["status"] = "invoice_created"

        if self.stripe.configured:
            payment = await self.stripe.create_payment_link(
                total, f"Services for {name}", email
            )
            if "error" not in payment:
                state["payment_link"] = payment.get("url", "")
                state["payment_id"] = payment.get("id", "")

        state["status"] = "ready"
        await self.redis.set(f"invoice:pipeline:{pipeline_id}", state, ex=90 * 86400)
        log.info("invoice.pipeline_complete", pipeline_id=pipeline_id, lead=name)
        return state

    async def check_payment_status(self, pipeline_id: str) -> str:
        state = await self.redis.get(f"invoice:pipeline:{pipeline_id}")
        if not state:
            return "unknown"
        return state.get("status", "unknown")

    async def handle_stripe_webhook(self, event: dict) -> dict:
        event_type = event.get("type", "")
        if event_type == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            payment_id = session.get("payment_link")
            if payment_id:
                await self.redis.set(f"stripe:webhook:{payment_id}", event, ex=90 * 86400)
                log.info("stripe.payment_received", payment_id=payment_id)
                return {"status": "payment_received", "payment_id": payment_id}
        return {"status": "ignored", "event_type": event_type}

    async def get_pipeline(self, pipeline_id: str) -> Optional[dict]:
        return await self.redis.get(f"invoice:pipeline:{pipeline_id}")

    async def list_pipelines(self) -> list[dict]:
        pipelines = []
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match="invoice:pipeline:*", count=50)
            for key in keys:
                data = await self.redis.get(key)
                if data:
                    pipelines.append(data)
            if cursor == 0:
                break
        return pipelines


def get_invoice_pipeline(
    zoho_org_id: Optional[str] = None,
    zoho_token: Optional[str] = None,
    stripe_key: Optional[str] = None,
) -> InvoicePipeline:
    return InvoicePipeline(
        zoho_org_id=zoho_org_id or getattr(settings, "zoho_org_id", None),
        zoho_token=zoho_token or getattr(settings, "zoho_api_token", None),
        stripe_key=stripe_key or settings.resend_api_key or getattr(settings, "stripe_api_key", None),
    )
