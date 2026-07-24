"""Advanced Exit Strategy"""
class AdvancedExitManager:
    def __init__(self):
        self.name = "advanced_exits"
    
    def calculate_exit_levels(self, entry_price, stop_loss, direction):
        risk = abs(entry_price - stop_loss)
        if direction.value == "long":
            tp1 = entry_price + (risk * 1.0)
            tp2 = entry_price + (risk * 2.0)
            tp3 = entry_price + (risk * 3.0)
            return {
                "entry": entry_price,
                "stop_loss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "trailing_stop_pct": 0.02,
                "sell_pct": [0.3, 0.3, 0.4]
            }
        else:
            tp1 = entry_price - (risk * 1.0)
            tp2 = entry_price - (risk * 2.0)
            tp3 = entry_price - (risk * 3.0)
            return {
                "entry": entry_price,
                "stop_loss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "trailing_stop_pct": 0.02,
                "sell_pct": [0.3, 0.3, 0.4]
            }
