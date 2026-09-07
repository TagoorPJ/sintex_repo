"""Feature categories and their Evolve API signals."""

FEATURE_EVENTS = {
    "rewards.balance": ("Rewards: Balance Check", "My Rewards"),
    "rewards.tier": ("Rewards: Tier Status", "My Rewards"),
    "rewards.transactions": ("Rewards: Transaction History", "My Rewards"),
    "rewards.statement": ("Rewards: Reward Statement", "My Rewards"),
    "upload.scan_qr": ("Upload Purchase: QR Flow Completed", "Upload Purchase"),
    "upload.create_claim": ("Upload Purchase: Claim Created", "Upload Purchase"),
    "upload.claim_status": ("Upload Purchase: Claim Status", "Upload Purchase"),
    "support.ticket": ("Support: Ticket Raised", "Support"),
    "product_help.rag_search": ("Product Help: RAG Search", "Product Help"),
}

COMPLETION_DETECTION_METHOD = "completed_action"
FAILURE_DETECTION_METHOD = "failed_action"
FEATURE_RESULT_METHODS = (COMPLETION_DETECTION_METHOD, FAILURE_DETECTION_METHOD)

API_FEATURE_EVENTS = {
    "evolve.balance_inquiry": "rewards.balance",
    "evolve.points_history": "rewards.transactions",
    "evolve.tier_status": "rewards.tier",
    "evolve.reward_statement": "rewards.statement",
    "evolve.capture_qr": "upload.scan_qr",
    "evolve.claim_create": "upload.create_claim",
    "evolve.claim_status": "upload.claim_status",
    "evolve.support_ticket": "support.ticket",
}
