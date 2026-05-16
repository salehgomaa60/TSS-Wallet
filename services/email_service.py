"""
Email notification service using SendGrid.

Free tier: 100 emails per day.
"""

import os
from typing import Optional


class EmailService:
    """
    Service that sends transactional emails via SendGrid.
    """
    
    def __init__(self):
        """Initialize SendGrid client."""
        self.api_key = os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@tssvault.io")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        # TODO: Initialize SendGrid client
    
    async def send_invitation_email(
        self,
        to_email: str,
        company_name: str,
        invited_by: str,
        role: str,
        invite_token: str
    ) -> bool:
        """
        Send invitation email to a new executive.
        
        Subject: "You've been invited to [Company Name] TSS Vault"
        """
        # TODO: Implement in Phase 3
        raise NotImplementedError("Send invitation email - implement in Phase 3")
    
    async def send_approval_request_email(
        self,
        to_email: str,
        proposer_name: str,
        amount_eth: float,
        recipient_address: str,
        description: str,
        current_approvals: int,
        threshold: int,
        tx_id: str
    ) -> bool:
        """
        Send approval request to executives.
        
        Subject: "[Action Required] [Name] wants to send [X] ETH"
        """
        # TODO: Implement in Phase 4
        raise NotImplementedError("Send approval request email - implement in Phase 4")
    
    async def send_transaction_executed_email(
        self,
        to_emails: list,
        tx_id: str,
        amount_eth: float,
        recipient_address: str,
        approvers: list,
        etherscan_url: str,
        new_balance_eth: float
    ) -> bool:
        """
        Send notification that transaction was executed.
        
        Subject: "Transaction Executed — [X] ETH sent"
        """
        # TODO: Implement in Phase 4
        raise NotImplementedError("Send executed email - implement in Phase 4")
    
    async def send_transaction_expired_email(
        self,
        to_email: str,
        proposer_name: str,
        tx_id: str,
        amount_eth: float
    ) -> bool:
        """
        Send notification that a transaction expired.
        
        Subject: "Transaction Expired — Approval deadline missed"
        """
        # TODO: Implement in Phase 4
        raise NotImplementedError("Send expired email - implement in Phase 4")
    
    async def send_welcome_email(
        self,
        to_email: str,
        company_name: str,
        vault_address: str,
        eth_address: str
    ) -> bool:
        """
        Send welcome email after company registration.
        
        Subject: "Welcome to TSS Vault — Your vault is ready"
        """
        # TODO: Implement in Phase 3
        raise NotImplementedError("Send welcome email - implement in Phase 3")
