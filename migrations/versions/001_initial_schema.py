"""Initial migration - create all tables

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-07-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ENUM types
    orderstatuses = postgresql.ENUM('PENDING', 'APPROVED', 'REJECTED', 'SUBMITTED', 'FILLED', 'CANCELLED', 'FAILED', name='orderstatus')
    orderstatuses.create(op.get_bind(), checkfirst=True)
    
    tradestatuses = postgresql.ENUM('OPEN', 'CLOSED', name='tradestatus')
    tradestatuses.create(op.get_bind(), checkfirst=True)
    
    exitreasons = postgresql.ENUM('STOP_LOSS', 'PROFIT_TARGET', 'MANUAL', 'RISK_LIMIT', 'EMERGENCY_STOP', name='exitreason')
    exitreasons.create(op.get_bind(), checkfirst=True)
    
    # Create tables
    op.create_table(
        'trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('strategy_name', sa.String(100), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('entry_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('exit_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exit_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('pnl', sa.Numeric(20, 8), nullable=False),
        sa.Column('pnl_pct', sa.Float(), nullable=False),
        sa.Column('fee_paid', sa.Numeric(20, 8), nullable=False),
        sa.Column('exit_reason', exitreasons, nullable=False),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trades_symbol'), 'trades', ['symbol'], unique=False)
    
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('broker_order_id', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('order_type', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('filled_quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('limit_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('stop_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('avg_fill_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('status', orderstatuses, nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_response', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('broker_order_id')
    )
    op.create_index(op.f('ix_orders_broker_order_id'), 'orders', ['broker_order_id'], unique=False)
    op.create_index(op.f('ix_orders_symbol'), 'orders', ['symbol'], unique=False)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)
    
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('avg_entry_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('current_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('stop_loss', sa.Numeric(20, 8), nullable=True),
        sa.Column('profit_target', sa.Numeric(20, 8), nullable=True),
        sa.Column('strategy_name', sa.String(100), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('unrealized_pnl', sa.Numeric(20, 8), nullable=True),
        sa.Column('unrealized_pnl_pct', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol')
    )
    op.create_index(op.f('ix_positions_symbol'), 'positions', ['symbol'], unique=False)
    
    op.create_table(
        'signals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('strategy_name', sa.String(100), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('entry_zone_low', sa.Numeric(20, 8), nullable=False),
        sa.Column('entry_zone_high', sa.Numeric(20, 8), nullable=False),
        sa.Column('stop_loss', sa.Numeric(20, 8), nullable=False),
        sa.Column('profit_target', sa.Numeric(20, 8), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('technical_explanation', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_signals_symbol'), 'signals', ['symbol'], unique=False)
    
    op.create_table(
        'approval_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('strategy_name', sa.String(100), nullable=False),
        sa.Column('signal_id', sa.Integer(), nullable=True),
        sa.Column('order_type', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('quantity', sa.Numeric(20, 8), nullable=False),
        sa.Column('limit_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('stop_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('estimated_cost', sa.Numeric(20, 8), nullable=False),
        sa.Column('estimated_fee', sa.Numeric(20, 8), nullable=False),
        sa.Column('risk_metrics', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_reason', sa.Text(), nullable=True),
        sa.Column('submitted_to_broker_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('broker_order_id', sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('broker_order_id')
    )
    op.create_index(op.f('ix_approval_queue_symbol'), 'approval_queue', ['symbol'], unique=False)
    op.create_index(op.f('ix_approval_queue_status'), 'approval_queue', ['status'], unique=False)
    
    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cash', sa.Numeric(20, 8), nullable=False),
        sa.Column('equity', sa.Numeric(20, 8), nullable=False),
        sa.Column('total_positions_value', sa.Numeric(20, 8), nullable=False),
        sa.Column('open_positions_count', sa.Integer(), nullable=False),
        sa.Column('closed_trades_count', sa.Integer(), nullable=False),
        sa.Column('daily_pnl', sa.Numeric(20, 8), nullable=False),
        sa.Column('total_pnl', sa.Numeric(20, 8), nullable=False),
        sa.Column('total_return_pct', sa.Float(), nullable=False),
        sa.Column('drawdown_pct', sa.Float(), nullable=False),
        sa.Column('max_exposure_pct', sa.Float(), nullable=False),
        sa.Column('extra_metadata', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table(
        'risk_limits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('daily_loss_limit', sa.Numeric(20, 8), nullable=False),
        sa.Column('max_position_size_pct', sa.Float(), nullable=False),
        sa.Column('max_portfolio_exposure_pct', sa.Float(), nullable=False),
        sa.Column('max_concurrent_positions', sa.Integer(), nullable=False),
        sa.Column('risk_per_trade_pct', sa.Float(), nullable=False),
        sa.Column('max_consecutive_losses', sa.Integer(), nullable=False),
        sa.Column('trade_cooldown_seconds', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('updated_by', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('user', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    
    op.create_table(
        'backtest_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('strategy_name', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('initial_capital', sa.Numeric(20, 8), nullable=False),
        sa.Column('final_equity', sa.Numeric(20, 8), nullable=False),
        sa.Column('total_return_pct', sa.Float(), nullable=False),
        sa.Column('sharpe_ratio', sa.Float(), nullable=True),
        sa.Column('sortino_ratio', sa.Float(), nullable=True),
        sa.Column('max_drawdown_pct', sa.Float(), nullable=False),
        sa.Column('win_rate_pct', sa.Float(), nullable=False),
        sa.Column('profit_factor', sa.Float(), nullable=False),
        sa.Column('total_trades', sa.Integer(), nullable=False),
        sa.Column('winning_trades', sa.Integer(), nullable=False),
        sa.Column('losing_trades', sa.Integer(), nullable=False),
        sa.Column('cagr_pct', sa.Float(), nullable=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_backtest_results_strategy_name'), 'backtest_results', ['strategy_name'], unique=False)
    
    op.create_table(
        'historical_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('open', sa.Numeric(20, 8), nullable=False),
        sa.Column('high', sa.Numeric(20, 8), nullable=False),
        sa.Column('low', sa.Numeric(20, 8), nullable=False),
        sa.Column('close', sa.Numeric(20, 8), nullable=False),
        sa.Column('volume', sa.Numeric(20, 8), nullable=False),
        sa.Column('granularity', sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('timestamp')
    )
    op.create_index(op.f('ix_historical_prices_symbol'), 'historical_prices', ['symbol'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_historical_prices_symbol'), table_name='historical_prices')
    op.drop_table('historical_prices')
    op.drop_index(op.f('ix_backtest_results_strategy_name'), table_name='backtest_results')
    op.drop_table('backtest_results')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('risk_limits')
    op.drop_table('portfolio_snapshots')
    op.drop_index(op.f('ix_approval_queue_status'), table_name='approval_queue')
    op.drop_index(op.f('ix_approval_queue_symbol'), table_name='approval_queue')
    op.drop_table('approval_queue')
    op.drop_index(op.f('ix_signals_symbol'), table_name='signals')
    op.drop_table('signals')
    op.drop_index(op.f('ix_positions_symbol'), table_name='positions')
    op.drop_table('positions')
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_index(op.f('ix_orders_symbol'), table_name='orders')
    op.drop_index(op.f('ix_orders_broker_order_id'), table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_trades_symbol'), table_name='trades')
    op.drop_table('trades')
    
    op.execute('DROP TYPE IF EXISTS exitreason')
    op.execute('DROP TYPE IF EXISTS tradestatus')
    op.execute('DROP TYPE IF EXISTS orderstatus')
