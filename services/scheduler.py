"""
Background job scheduler using APScheduler.

Runs periodic tasks:
- Transaction expiry job (every 5 minutes)
- Node health check (every 30 seconds)
- Balance sync (every 2 minutes)
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger


class JobScheduler:
    """
    Scheduler for background jobs.
    """
    
    def __init__(self):
        """Initialize the scheduler."""
        self.scheduler = AsyncIOScheduler()
    
    def start(self):
        """Start the scheduler and register all jobs."""
        # Transaction expiry job - runs every 5 minutes
        self.scheduler.add_job(
            self._expire_transactions,
            IntervalTrigger(minutes=5),
            id="expire_transactions",
            replace_existing=True,
        )
        
        # Node health check - runs every 30 seconds
        self.scheduler.add_job(
            self._check_node_health,
            IntervalTrigger(seconds=30),
            id="check_node_health",
            replace_existing=True,
        )
        
        # Balance sync - runs every 2 minutes
        self.scheduler.add_job(
            self._sync_balances,
            IntervalTrigger(minutes=2),
            id="sync_balances",
            replace_existing=True,
        )
        
        self.scheduler.start()
    
    def shutdown(self):
        """Shutdown the scheduler gracefully."""
        self.scheduler.shutdown()
    
    async def _expire_transactions(self):
        """
        Find all PENDING transactions where expires_at < NOW().
        
        - Update status to EXPIRED
        - Send expiry email to proposer
        - Write to audit_log
        """
        from datetime import datetime, timezone
        import asyncio
        import httpx
        
        print(f"[scheduler] Running transaction expiry job at {datetime.now(timezone.utc)}")
        
        # Call the API to get and expire transactions
        # In production, this would directly access the database
        # For now, we log that this job ran
        print("[scheduler] Transaction expiry job completed")
    
    async def _check_node_health(self):
        """
        Ping all 5 TSS nodes.
        
        - Update node status cache
        - Alert if any node goes offline
        """
        # TODO: Implement in Phase 4
        pass
    
    async def _sync_balances(self):
        """
        Fetch live balance from Sepolia for all active vaults.
        
        - Cache in Redis or in-memory dict
        - Used by /vault/balance endpoint for fast response
        """
        # TODO: Implement in Phase 4
        pass
