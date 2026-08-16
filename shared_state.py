"""Shared state between the scheduler thread and the FastAPI dashboard.
Both run in the same process, so a simple module-level reference works."""

_portfolio = None
_broker = None

def set_portfolio(portfolio):
    global _portfolio
    _portfolio = portfolio

def get_portfolio():
    return _portfolio

def set_broker(broker):
    global _broker
    _broker = broker

def get_broker():
    return _broker
