"""ORM models, organized by domain.

Importing this module registers all models with SQLAlchemy metadata,
which Alembic needs for autogenerate.
"""

from src.core.db.models.advertiser import Advertiser
from src.core.db.models.end_user import EndUser
from src.core.db.models.campaign import Campaign, CampaignResource
from src.core.db.models.checker_bot import CheckerBot
from src.core.db.models.publisher import Publisher, PublisherApiToken, PublisherBot
from src.core.db.models.resource_issue import ResourceIssue
from src.core.db.models.transaction import Transaction
from src.core.db.models.verification_log import VerificationLog
from src.core.db.models.webhook import WebhookDelivery, WebhookEndpoint

__all__ = [
    "Advertiser",
    "EndUser",
    "Campaign",
    "CampaignResource",
    "CheckerBot",
    "Publisher",
    "PublisherApiToken",
    "PublisherBot",
    "ResourceIssue",
    "Transaction",
    "VerificationLog",
    "WebhookDelivery",
    "WebhookEndpoint",
]
