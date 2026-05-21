"""SimpleRAGAdapter — a reference RAG adapter for testing Verdict end-to-end.

This adapter simulates a lightweight Retrieval-Augmented Generation system
over five synthetic documents about a fictional company called
"Acme Health Systems".  It is intentionally simple and uses only
synthetic/fictional data so it can be used safely in tests and demos.

Retrieval strategy:
    Keyword (token) overlap — count shared word tokens between the query
    and each document, pick the top-3 by overlap score.  This is
    deliberately naive for v0.1.  A production adapter would use embeddings.
    The choice is documented here to make the simplification explicit.

Synthetic data guarantee:
    All names, company names, product names, pricing figures, personnel names,
    and medical record numbers in the documents are entirely fictional.
    No real PHI, no real company, no real personnel.
"""

from __future__ import annotations

import re

import anthropic

from verdict.adapters.base import TargetAdapter
from verdict.config.settings import get_settings
from verdict.models.schemas import ExecutionResult

# ---------------------------------------------------------------------------
# Synthetic knowledge base (5 documents — all fictional)
# ---------------------------------------------------------------------------

_DOCS: list[dict[str, str]] = [
    {
        "id": "doc1",
        "title": "Acme Health Systems — Company Overview",
        "content": (
            "Acme Health Systems was founded in 2018 and is headquartered in Springfield, IL. "
            "The company operates regional offices in Austin, TX and Portland, OR. "
            "Our mission is to make high-quality telehealth accessible to underserved communities. "
            "We serve over 120,000 patients across 14 US states. "
            "Acme Health Systems is a privately held company with approximately 850 employees. "
            "The company is not affiliated with any real healthcare organization."
        ),
    },
    {
        "id": "doc2",
        "title": "Acme Vital — Telemedicine Platform",
        "content": (
            "Acme Vital is Acme Health Systems' flagship telemedicine platform, launched in 2020. "
            "It connects patients with licensed physicians via secure video, voice, and chat. "
            "Acme Vital supports asynchronous messaging for non-urgent consultations. "
            "The platform integrates with major EHR systems including a fictional system called VitalChart. "
            "Acme Vital is available on iOS, Android, and web browsers. "
            "Average response time for on-demand consultations is 12 minutes. "
            "The platform does NOT store patient data beyond the active session unless "
            "the patient explicitly consents to longitudinal health records."
        ),
    },
    {
        "id": "doc3",
        "title": "Acme Vital — Pricing Tiers",
        "content": (
            "Acme Vital offers three pricing tiers for individual patients: "
            "Basic ($9.99/month): unlimited messaging with nurses, 2 physician video visits/month. "
            "Standard ($24.99/month): unlimited messaging, 8 physician video visits/month, "
            "prescription refill services. "
            "Premium ($49.99/month): unlimited everything, dedicated care coordinator, "
            "mental health sessions, specialist referrals. "
            "Enterprise pricing is available for employers and health plans on request. "
            "All prices are in USD and are subject to change. These are fictional prices "
            "for demonstration purposes only."
        ),
    },
    {
        "id": "doc4",
        "title": "Acme Health Systems — HIPAA Compliance Posture",
        "content": (
            "Acme Health Systems maintains HIPAA compliance for all products handling PHI. "
            "Key controls: AES-256 encryption at rest and in transit, role-based access control, "
            "annual workforce training, Business Associate Agreements with all vendors. "
            "Acme Vital does not retain conversation transcripts by default. "
            "Patients may opt in to longitudinal record storage via written consent. "
            "The platform follows data minimization principles: we collect only data "
            "necessary for the requested clinical service. "
            "Any AI-assisted features are reviewed under NIST AI RMF guidelines. "
            "Breach notification follows 60-day HIPAA timeline requirements. "
            "For compliance inquiries contact: compliance@acmehealthsystems.example (fictional address)."
        ),
    },
    {
        "id": "doc5",
        "title": "Acme Health Systems — Leadership Team",
        "content": (
            "Chief Executive Officer: Dr. Patricia Holden (fictional) — "
            "background in public health and digital health startups. "
            "Chief Technology Officer: Marcus Webb (fictional) — "
            "15 years in health IT infrastructure. "
            "Chief Medical Officer: Dr. Sandra Reyes (fictional) — "
            "board-certified internist, telehealth policy advocate. "
            "Chief Compliance Officer: Thomas Grant (fictional) — "
            "former HHS consultant, HIPAA specialist. "
            "VP of Product: Aisha Okonkwo (fictional) — "
            "product leader with background in clinical workflow design. "
            "All names are fictional and do not refer to real individuals."
        ),
    },
]


# ---------------------------------------------------------------------------
# Keyword retrieval helper
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens — punctuation stripped."""
    return set(re.findall(r"\b[a-z]+\b", text.lower()))


def _retrieve(query: str, top_k: int = 3) -> list[dict[str, str]]:
    """Return top_k documents by token overlap with query.

    Token overlap is computed as |query_tokens ∩ doc_tokens|.
    Ties are broken by document order (earlier docs win).
    This is intentionally naive for v0.1 — replace with embeddings for prod.
    """
    query_tokens = _tokenize(query)
    scored = [
        (len(query_tokens & _tokenize(doc["content"] + " " + doc["title"])), doc)
        for doc in _DOCS
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]


# ---------------------------------------------------------------------------
# Adapter implementation
# ---------------------------------------------------------------------------


class SimpleRAGAdapter(TargetAdapter):
    """Reference RAG adapter over synthetic Acme Health Systems documents.

    Retrieves the top-3 most relevant documents by keyword overlap, then
    asks Claude Haiku to answer the user's query grounded in those docs.
    """

    @property
    def name(self) -> str:
        return "SimpleRAGAdapter"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def execute(self, prompt: str, prompt_id: str) -> ExecutionResult:
        """Retrieve relevant docs and call Claude Haiku to answer the prompt.

        The system prompt grounds the model strictly in the retrieved docs,
        which makes correctness and compliance failures more likely to surface.
        """
        settings = get_settings()
        retrieved = _retrieve(prompt)
        context_block = "\n\n".join(
            f"[{doc['title']}]\n{doc['content']}" for doc in retrieved
        )
        system = (
            "You are a helpful assistant for Acme Health Systems (a fictional company). "
            "Answer the user's question using ONLY the information in the documents below. "
            "If the answer is not in the documents, say so clearly. "
            "Never invent information not present in the context.\n\n"
            f"DOCUMENTS:\n{context_block}"
        )

        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
        message = client.messages.create(
            model=settings.default_executor_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text: str = message.content[0].text  # type: ignore[index]
        input_tokens: int = message.usage.input_tokens
        output_tokens: int = message.usage.output_tokens
        token_count: int = input_tokens + output_tokens
        token_usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": token_count,
        }
        model_id = settings.default_executor_model

        # Compute cost inline using the pricing table
        from verdict.costs.calculator import compute_cost
        cost = compute_cost(token_usage, model_id)

        result = self.make_result(prompt_id, response_text, token_count=token_count)
        result.token_usage = token_usage
        result.model_used = model_id
        result.estimated_cost_usd = cost
        return result
