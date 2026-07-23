"""
Backtesting Engine — replay historical data and compute performance metrics.

This module replays price bars and evaluates strategy performance in
hindsight, computing Sharpe ratio, Sortino ratio, max drawdown, win rate, etc.

Usage:
    runner = BacktestRunner(broker, strategy, symbols=["BTC-USD"])
    results = runner.run_backtest(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=10000,
    )
    print(results)
    results.export_csv("backtest_results.csv")
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any
import json

from broker.interface import BrokerInterface
from models.all import (
    BacktestResult, HistoricalPrice, Trade as TradeModel
)
from paper_trading.engine import PaperTradingEngine, PositionSizeConfig
from paper_trading.portfolio import PaperPortfolio, ClosedTrade
from strategy.base import Strategy, PriceBar
from database.connection import session_scope

logger = logging.getLogger("backtesting")


class BacktestResults:
    """Encapsulates backtest results and metrics."""
    
    def __init__(
        self,
        strategy_name: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        final_equity: float,
        trades: List[ClosedTrade],
    ):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.final_equity = final_equity
        self.trades = trades
        
        # Calculate metrics
        self.total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100
        self.total_trades = len(trades)
        self.winning_trades = sum(1 for t in trades if t.pnl > 0)
        self.losing_trades = sum(1 for t in trades if t.pnl < 0)
        self.win_rate_pct = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        # Profit factor: sum of winning trades / sum of losing trades
        winning_sum = sum(t.pnl for t in trades if t.pnl > 0)
        losing_sum = abs(sum(t.pnl for t in trades if t.pnl < 0))
        self.profit_factor = winning_sum / losing_sum if losing_sum > 0 else float('inf') if winning_sum > 0 else 0
        
        # Sharpe ratio (simplified: daily returns)
        daily_pnl = self._calculate_daily_pnl()
        self.sharpe_ratio = self._calculate_sharpe_ratio(daily_pnl) if daily_pnl else 0
        self.sortino_ratio = self._calculate_sortino_ratio(daily_pnl) if daily_pnl else 0
        
        # Max drawdown
        self.max_drawdown_pct = self._calculate_max_drawdown()
        
        # CAGR (Compound Annual Growth Rate)
        years = (end_date - start_date).days / 365.25
        self.cagr_pct = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0
    
    def _calculate_daily_pnl(self) -> Dict[datetime, float]:
        """Calculate P&L by day."""
        daily = {}
        for trade in self.trades:
            day = trade.closed_at.date()
            daily[day] = daily.get(day, 0) + trade.pnl
        return daily
    
    def _calculate_sharpe_ratio(self, daily_pnl: Dict) -> float:
        """Calculate Sharpe ratio (returns / volatility, assuming 0% risk-free rate)."""
        if not daily_pnl:
            return 0
        
        returns = list(daily_pnl.values())
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5
        
        if std_dev == 0:
            return 0
        
        # Annualized (252 trading days)
        return (mean_return / std_dev) * (252 ** 0.5)
    
    def _calculate_sortino_ratio(self, daily_pnl: Dict) -> float:
        """Calculate Sortino ratio (like Sharpe but only penalizes downside volatility)."""
        if not daily_pnl:
            return 0
        
        returns = list(daily_pnl.values())
        mean_return = sum(returns) / len(returns)
        
        # Only downside volatility
        downside_returns = [r for r in returns if r < mean_return]
        downside_variance = sum((r - mean_return) ** 2 for r in downside_returns) / len(returns) if downside_returns else 0
        downside_std_dev = downside_variance ** 0.5
        
        if downside_std_dev == 0:
            return 0
        
        # Annualized
        return (mean_return / downside_std_dev) * (252 ** 0.5)
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from peak."""
        if not self.trades:
            return 0
        
        # Sort trades by close date
        sorted_trades = sorted(self.trades, key=lambda t: t.closed_at)
        equity_curve = [self.initial_capital]
        
        for trade in sorted_trades:
            equity_curve.append(equity_curve[-1] + trade.pnl)
        
        peak = equity_curve[0]
        max_dd = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    def __str__(self) -> str:
        return (
            f"Backtest Results: {self.strategy_name} on {self.symbol}\n"
            f"  Period: {self.start_date.date()} to {self.end_date.date()}\n"
            f"  Initial Capital: ${self.initial_capital:,.2f}\n"
            f"  Final Equity: ${self.final_equity:,.2f}\n"
            f"  Return: {self.total_return_pct:+.2f}%\n"
            f"  Trades: {self.total_trades} (W: {self.winning_trades}, L: {self.losing_trades})\n"
            f"  Win Rate: {self.win_rate_pct:.1f}%\n"
            f"  Profit Factor: {self.profit_factor:.2f}\n"
            f"  Sharpe Ratio: {self.sharpe_ratio:.2f}\n"
            f"  Sortino Ratio: {self.sortino_ratio:.2f}\n"
            f"  Max Drawdown: {self.max_drawdown_pct:.2f}%\n"
            f"  CAGR: {self.cagr_pct:.2f}%"
        )
    
    def export_csv(self, filepath: str) -> None:
        """Export trades to CSV."""
        import csv
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Symbol", "Side", "Quantity", "Entry Price", "Exit Price",
                "Entry Time", "Exit Time", "P&L", "P&L %", "Exit Reason"
            ])
            for trade in self.trades:
                writer.writerow([
                    trade.symbol, trade.side, float(trade.quantity),
                    float(trade.entry_price), float(trade.exit_price),
                    trade.entry_time, trade.exit_time,
                    float(trade.pnl), f"{trade.pnl_pct:.2f}%", trade.exit_reason
                ])
        logger.info(f"Exported {len(self.trades)} trades to {filepath}")
    
    def save_to_db(self) -> int:
        """Save backtest results to database."""
        with session_scope() as session:
            result = BacktestResult(
                strategy_name=self.strategy_name,
                symbol=self.symbol,
                start_date=self.start_date,
                end_date=self.end_date,
                initial_capital=Decimal(str(self.initial_capital)),
                final_equity=Decimal(str(self.final_equity)),
                total_return_pct=self.total_return_pct,
                sharpe_ratio=self.sharpe_ratio,
                sortino_ratio=self.sortino_ratio,
                max_drawdown_pct=self.max_drawdown_pct,
                win_rate_pct=self.win_rate_pct,
                profit_factor=self.profit_factor,
                total_trades=self.total_trades,
                winning_trades=self.winning_trades,
                losing_trades=self.losing_trades,
                cagr_pct=self.cagr_pct,
                extra_data=json.dumps(self.__dict__, default=str),
            )
            session.add(result)
            session.flush()
            return result.id


class BacktestRunner:
    """Runs backtests against historical data."""
    
    def __init__(
        self,
        broker: BrokerInterface,
        strategy: Strategy,
        symbols: List[str],
    ):
        self.broker = broker
        self.strategy = strategy
        self.symbols = symbols
    
    def run_backtest(
        self,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10_000,
        granularity: str = "ONE_HOUR",
    ) -> BacktestResults:
        """
        Run a backtest over a date range.
        
        Currently uses live API to fetch historical data. In production,
        you'd load from the HistoricalPrice table instead.
        """
        logger.info(
            f"Starting backtest: {self.strategy.__class__.__name__} "
            f"{start_date.date()} to {end_date.date()}"
        )
        
        # Initialize portfolio
        portfolio = PaperPortfolio(starting_cash=initial_capital)
        engine = PaperTradingEngine(
            broker=self.broker,
            strategy=self.strategy,
            portfolio=portfolio,
            sizing=PositionSizeConfig(),
        )
        
        # Fetch and replay bars for each symbol
        for symbol in self.symbols:
            logger.info(f"Replaying {symbol}...")
            try:
                # Fetch historical bars (in production, load from HistoricalPrice table)
                bars = self._fetch_historical_bars(
                    symbol, start_date, end_date, granularity
                )
                
                for bar in bars:
                    # Run strategy on each bar
                    engine.on_bars(symbol, [bar])
            
            except Exception as exc:
                logger.error(f"Error replaying {symbol}: {exc}")
                continue
        
        # Collect results
        results = BacktestResults(
            strategy_name=self.strategy.__class__.__name__,
            symbol=",".join(self.symbols),
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_equity=portfolio.equity,
            trades=portfolio.closed_trades,
        )
        
        logger.info(f"Backtest complete:\n{results}")
        return results
    
    def _fetch_historical_bars(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str,
    ) -> List[PriceBar]:
        """Fetch historical bars from database or API."""
        # TODO: Load from HistoricalPrice table first
        # For now, fetch from live API (will fail for historical dates)
        try:
            bars_dict = self.broker.get_candles(
                symbol, granularity=granularity, limit=5000
            )
            return [
                PriceBar(
                    timestamp=datetime.fromtimestamp(b["start"], tz=timezone.utc),
                    open=b["open"], high=b["high"], low=b["low"],
                    close=b["close"], volume=b["volume"],
                )
                for b in bars_dict
                if start_date <= datetime.fromtimestamp(b["start"], tz=timezone.utc) <= end_date
            ]
        except Exception as exc:
            logger.warning(f"Could not fetch bars for {symbol}: {exc}")
            return []
