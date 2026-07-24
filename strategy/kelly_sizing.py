"""Kelly Criterion Position Sizing"""
class KellySizing:
    def __init__(self, win_rate=0.60, avg_win=1.5, avg_loss=1.0):
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss
    
    def calculate_kelly_fraction(self):
        p = self.win_rate
        q = 1 - p
        b = self.avg_win / self.avg_loss
        f_star = (b * p - q) / b
        return max(0, f_star * 0.25)
    
    def get_position_size(self, account_size, confidence, base_risk_pct=0.02):
        kelly_fraction = self.calculate_kelly_fraction()
        adjusted_risk = base_risk_pct * (confidence ** 0.5)
        position_size = kelly_fraction * adjusted_risk * account_size
        return min(position_size, account_size * 0.02)
