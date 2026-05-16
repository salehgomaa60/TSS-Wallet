"""Initial migration - create all tables

Revision ID: 001
Revises: 
Create Date: 2025-04-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # companies table
    op.create_table(
        'companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('plan', sa.String(50), server_default='starter'),
        sa.Column('threshold', sa.Integer, nullable=False, server_default='2'),
        sa.Column('total_signers', sa.Integer, nullable=False, server_default='3'),
        sa.Column('contract_address', sa.String(42), nullable=True),
        sa.Column('eth_address', sa.String(42), nullable=True),
        sa.Column('group_public_key', postgresql.JSONB(), nullable=True),
        sa.Column('dkg_session_id', sa.String(64), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )
    
    # users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('node_id', sa.Integer, nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    
    # transactions table
    op.create_table(
        'transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('proposed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('to_address', sa.String(42), nullable=False),
        sa.Column('value_wei', sa.BigInteger(), nullable=False),
        sa.Column('value_eth', sa.Numeric(20, 8), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='PENDING'),
        sa.Column('tx_hash', sa.String(66), nullable=True),
        sa.Column('raw_transaction', sa.Text(), nullable=True),
        sa.Column('signing_session', sa.String(64), nullable=True),
        sa.Column('participating_nodes', postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column('proposed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('etherscan_url', sa.String(255), nullable=True),
    )
    
    # approvals table
    op.create_table(
        'approvals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('node_id', sa.Integer(), nullable=True),
        sa.Column('partial_signature', postgresql.JSONB(), nullable=True),
        sa.Column('signed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('ip_address', sa.String(45), nullable=True),
    )
    op.create_unique_constraint('uq_approval_tx_user', 'approvals', ['transaction_id', 'user_id'])
    
    # audit_log table
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    
    # invitations table
    op.create_table(
        'invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('node_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(255), unique=True, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )
    
    # Create indexes for performance
    op.create_index('ix_companies_email', 'companies', ['email'])
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_company_id', 'users', ['company_id'])
    op.create_index('ix_transactions_company_id', 'transactions', ['company_id'])
    op.create_index('ix_transactions_status', 'transactions', ['status'])
    op.create_index('ix_approvals_transaction_id', 'approvals', ['transaction_id'])
    op.create_index('ix_audit_log_company_id', 'audit_log', ['company_id'])
    op.create_index('ix_audit_log_timestamp', 'audit_log', ['timestamp'])
    op.create_index('ix_invitations_token', 'invitations', ['token'])


def downgrade() -> None:
    # Drop in reverse order to respect foreign keys
    op.drop_table('invitations')
    op.drop_table('audit_log')
    op.drop_table('approvals')
    op.drop_table('transactions')
    op.drop_table('users')
    op.drop_table('companies')
