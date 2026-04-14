"""
Hardcoded knowledge base with keyword-based retrieval.
Replace/extend KNOWLEDGE_BASE with real content later.
"""

from typing import List, Dict

KNOWLEDGE_BASE: List[Dict] = [
    {
        "id": 1,
        "topic": "billing",
        "keywords": [
            "bill", "billing", "charge", "invoice", "payment",
            "cost", "price", "fee", "charged", "amount", "due",
        ],
        "text": (
            "Bills are generated on the 1st of every month and reflect usage from the previous billing cycle. "
            "You can view your current and past invoices in the Billing section of your account dashboard. "
            "Payments are automatically charged to your registered payment method on the due date shown on the invoice. "
            "If a payment fails, you will receive an email notification with a 7-day grace period to update your details."
        ),
    },
    {
        "id": 2,
        "topic": "refund",
        "keywords": [
            "refund", "money back", "reimbursement", "credit",
            "overcharged", "wrong charge", "dispute", "incorrect charge",
        ],
        "text": (
            "Refund requests are reviewed and processed within 5-7 business days once approved by our billing team. "
            "If you believe you have been incorrectly charged, please contact support with your invoice number and a brief description. "
            "Approved credits are applied to the next billing cycle; direct refunds go back to your original payment method. "
            "Disputes must be raised within 60 days of the invoice date."
        ),
    },
    {
        "id": 3,
        "topic": "outage",
        "keywords": [
            "outage", "down", "not working", "offline", "service disruption",
            "maintenance", "unavailable", "cannot access", "service down",
        ],
        "text": (
            "Planned maintenance windows are scheduled between 2:00 AM and 4:00 AM on the last Sunday of each month. "
            "Unplanned outages are communicated in real-time on our status page (status.example.com) and via email alerts. "
            "Our engineering team targets service restoration within 2 hours for critical disruptions. "
            "Affected customers automatically receive a prorated credit for any downtime exceeding our 99.9% SLA."
        ),
    },
    {
        "id": 4,
        "topic": "account",
        "keywords": [
            "account", "login", "password", "username", "sign in",
            "profile", "credentials", "locked", "access", "forgot password",
        ],
        "text": (
            "To reset your password, visit the login page and click 'Forgot Password'. "
            "A secure reset link will be emailed to your registered address within 2 minutes — check your spam folder if it doesn't arrive. "
            "Accounts lock after 5 consecutive failed login attempts; they automatically unlock after 15 minutes. "
            "To update your email address or username, go to Account Settings > Profile and verify with your current password."
        ),
    },
    {
        "id": 5,
        "topic": "plans",
        "keywords": [
            "plan", "upgrade", "downgrade", "subscription", "tier",
            "package", "pricing", "features", "change plan", "pro", "enterprise",
        ],
        "text": (
            "We offer three plans: Basic ($9.99/month), Professional ($24.99/month), and Enterprise (custom pricing). "
            "Upgrades take effect immediately and are prorated for the remaining days in your billing cycle. "
            "Downgrades apply at the start of the next billing cycle so you keep current features until then. "
            "Enterprise plans include a dedicated account manager, 99.99% SLA, custom integrations, and SSO support."
        ),
    },
    {
        "id": 6,
        "topic": "cancellation",
        "keywords": [
            "cancel", "cancellation", "terminate", "end subscription",
            "stop service", "close account", "delete account", "quit",
        ],
        "text": (
            "You can cancel your subscription at any time under Account Settings > Subscription Management. "
            "Your service remains fully active until the end of the current billing period — you won't be charged again. "
            "All account data is retained for 30 days post-cancellation, giving you time to export anything you need. "
            "Reactivating within 30 days restores your account and data; after that, data is permanently deleted."
        ),
    },
    {
        "id": 7,
        "topic": "support",
        "keywords": [
            "support", "help", "contact", "ticket", "agent", "assistance",
            "talk", "human", "reach", "speak to", "call",
        ],
        "text": (
            "Our support team is available 24/7 via live chat and email at support@example.com. "
            "Phone support is available Monday to Friday, 9:00 AM to 6:00 PM EST at 1-800-555-0100. "
            "Expected response times: live chat under 2 minutes, email within 4 hours, phone immediately during business hours. "
            "Professional and Enterprise customers receive priority queuing and a dedicated support line."
        ),
    },
    {
        "id": 8,
        "topic": "technical",
        "keywords": [
            "error", "bug", "crash", "slow", "performance", "technical",
            "issue", "problem", "broken", "fix", "not loading", "glitch",
        ],
        "text": (
            "For technical issues, start by clearing your browser cache (Ctrl+Shift+R / Cmd+Shift+R) and reloading. "
            "Check status.example.com for any ongoing incidents that might explain what you're seeing. "
            "If the problem persists, note the exact error message, the time it occurred, and your browser/OS version, "
            "then open a support ticket — our technical team responds to critical issues within 1 hour and standard ones within 24 hours."
        ),
    },
]


def retrieve(query: str, top_k: int = 2) -> List[Dict]:
    """
    Score each KB entry by keyword overlap with the query.
    Returns the top_k highest-scoring entries.
    Always returns at least one entry even if the score is zero.
    """
    query_lower = query.lower()
    scored: List[tuple] = []

    for entry in KNOWLEDGE_BASE:
        # Each keyword that appears in the query = 2 points
        # Each query word that partially overlaps a keyword = 1 point
        query_tokens = set(query_lower.split())
        exact_hits = sum(2 for kw in entry["keywords"] if kw in query_lower)
        partial_hits = sum(
            1
            for kw in entry["keywords"]
            for token in query_tokens
            if token in kw and token not in ("i", "a", "is", "the", "my", "me")
        )
        score = exact_hits + partial_hits
        scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Return top-k entries that scored > 0; fall back to the best match otherwise
    top = [e for s, e in scored[:top_k] if s > 0]
    return top if top else [scored[0][1]]
