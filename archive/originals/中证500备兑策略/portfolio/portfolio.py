import pandas as pd

'''
need feature in option_df:
order_book_id: (int64)
close: (float64)
'''
class Portfolio:
    def __init__(self, cash, multiplier=10000, option_cost=0.8, etf_cost_rate=0.0003, 
                 etf_min_cost=0, option_slippage=0.001, etf_slippage=0):

        # Core holdings
        self.option_positions = {}       # option_id -> {quantity, expiry, type}
        self.underlying_position = 0     # underlying ETF position
        self.cash = cash
        self.multiplier = multiplier

        # slippage
        self.option_slippage = option_slippage
        self.etf_slippage = etf_slippage

        # Transaction costs
        self.option_cost = option_cost
        self.etf_cost_rate = etf_cost_rate
        self.etf_min_cost = etf_min_cost

        # position_information_storage
        self.position_strike: float | None = None
        self.position_expire_date: pd.Timestamp | None = None

        # Extended features
        self.option_trade_history = []          # record option trade history
        self.underlying_trade_history = []      # record underlying trade history
        self.equity_history = []                # list of portfolio equity over time (per minute)

        # Trade PnL tracking
        self.open_trade_record = {}
        self.closed_trade_history = []


    # Option trade (open/add position)
    def update_option(self, timestamp, option_id, quantity, price, expiry, option_type):

        if option_id not in self.option_positions:
            self.option_positions[option_id] = {
                "quantity": 0,
                "expire_date": expiry,
                "option_type": option_type
            }

        pos = self.option_positions[option_id]
        pos["quantity"] += quantity

        # remove empty position
        if pos["quantity"] == 0:
            del self.option_positions[option_id]

        # =========================
        # Slippage
        # =========================
        if quantity > 0:
            trade_price = price * (1 + self.option_slippage)
        else:
            trade_price = price * (1 - self.option_slippage)

        # =========================
        # Cash update
        # =========================
        self.cash -= quantity * trade_price * self.multiplier

        # Transaction cost
        cost = abs(quantity) * self.option_cost
        self.cash -= cost

        # Record trade
        self.option_trade_history.append({
            "timestamp": timestamp,
            "instrument": "option",
            "id": option_id,
            "quantity": quantity,
            "market_price": price,
            "trade_price": trade_price,
            "option_type": option_type,
            "cost": cost
        })

        self.record_trade_pnl(
            timestamp=timestamp,
            instrument="option",
            trade_id=option_id,
            quantity=quantity,
            trade_price=trade_price,
            cost=cost
        )


    # Underlying ETF trade
    def update_underlying(self, timestamp, quantity, price):

        if price is None or pd.isna(price):
            return

        # =========================
        # Slippage
        # =========================
        if quantity > 0:
            trade_price = price * (1 + self.etf_slippage)
        else:
            trade_price = price * (1 - self.etf_slippage)

        self.underlying_position += quantity
        self.cash -= quantity * trade_price

        # Transaction cost
        cost = max(abs(quantity * trade_price) * self.etf_cost_rate, self.etf_min_cost) if quantity != 0 else 0
        self.cash -= cost

        self.underlying_trade_history.append({
            "timestamp": timestamp,
            "instrument": "underlying",
            "quantity": quantity,
            "market_price": price,
            "trade_price": trade_price,
            "cost": cost
        })

        # ✅ 修复：instrument 改为 "underlying"
        self.record_trade_pnl(
            timestamp=timestamp,
            instrument="underlying",
            trade_id="underlying",
            quantity=quantity,
            trade_price=trade_price,
            cost=cost
        )


    # Close all positions
    def close_positions(self, timestamp, option_snapshot, spot_price):
        """
        Close all positions (options + underlying)
        option_data: pd.DataFrame with columns ['order_book_id', 'close', 'expire_date', 'option_type']
        spot_price: current underlying price
        """

        # Close option positions
        price_map = option_snapshot.set_index("order_book_id")["close"].to_dict()

        for oid in list(self.option_positions.keys()):
            pos = self.option_positions[oid]
            qty = pos["quantity"]
            if qty == 0:
                continue

            price = price_map.get(oid, None)
            if price is None or pd.isna(price):
                continue  # optionally use intrinsic value

            # Close the option position
            self.update_option(
                timestamp=timestamp,
                option_id=oid,
                quantity=-qty,
                price=price,
                expiry=pos["expire_date"],
                option_type=pos["option_type"]
            )

        # Close underlying
        if self.underlying_position != 0:
            self.update_underlying(
                timestamp=timestamp,
                quantity=-self.underlying_position,
                price=spot_price
            )

        # ✅ 修复：使用正确的属性名 position_expire_date
        self.position_strike = None
        self.position_expire_date = None


    # Portfolio equity calculation
    def get_equity(self, timestamp, option_data, underlying_price):
        """
        option_data: pd.DataFrame with columns ['order_book_id', 'close'] 当天的期权市场快照
        underlying_price: current underlying price
        """
        equity = self.cash

        # Build price map
        price_map = option_data.set_index("order_book_id")["close"].to_dict()

        for oid, pos in self.option_positions.items():
            qty = pos["quantity"]
            if qty == 0:
                continue
            price = price_map.get(oid, None)
            if price is None or pd.isna(price):
                continue
            equity += qty * price * self.multiplier

        equity += self.underlying_position * underlying_price

        # Record equity
        self.equity_history.append({
            "timestamp": timestamp,
            "equity": equity
        })

        return equity


    def record_trade_pnl(self, timestamp, instrument, trade_id, quantity, trade_price, cost):

        key = (instrument, trade_id)

        # OPEN TRADE
        if key not in self.open_trade_record:
            self.open_trade_record[key] = {
                "entry_time": timestamp,
                "quantity": quantity,
                "entry_price": trade_price,
                "entry_cost": cost
            }

        # CLOSE TRADE
        else:
            open_trade = self.open_trade_record[key]
            entry_price = open_trade["entry_price"]
            entry_qty = open_trade["quantity"]

            # PnL
            pnl = (
                (trade_price - entry_price)
                * abs(quantity)
                * self.multiplier
            )

            # Short position
            if entry_qty < 0:
                pnl = -pnl

            pnl -= (
                open_trade["entry_cost"]
                + cost
            )

            # Save Closed Trade
            self.closed_trade_history.append({
                "instrument": instrument,
                "id": trade_id,
                "entry_time": open_trade["entry_time"],
                "exit_time": timestamp,
                "entry_price": entry_price,
                "exit_price": trade_price,
                "quantity": abs(quantity),
                "direction": "long" if entry_qty > 0 else "short",
                "pnl": pnl
            })

            # remove open trade
            del self.open_trade_record[key]


    def exercise_options(self, timestamp, spot_price, option_date):

        """
        ETF欧式期权到期行权
        只有到期日才会处理：
        - 多Call：价内 -> 买入标的
        - 多Put：价内 -> 卖出标的
        - 空Call：价内 -> 被行权卖出标的
        - 空Put：价内 -> 被行权买入标的
        价外全部作废
        """

        strike_map = option_date.set_index("order_book_id")["strike_price"].to_dict()

        for oid in list(self.option_positions.keys()):

            pos = self.option_positions[oid]

            qty = pos["quantity"]
            option_type = pos["option_type"]
            expiry = pd.to_datetime(pos["expire_date"])

            # =====================================================
            # 只有到期日才处理（欧式期权）
            # =====================================================
            if pd.to_datetime(timestamp) < expiry:
                continue

            strike = strike_map.get(oid)

            if strike is None:
                print(f"Warning: 无法获取 {oid} strike")
                continue

            exercise_qty = abs(qty) * self.multiplier

            # =====================================================
            # 多头期权
            # =====================================================
            if qty > 0:
                # Long Call
                if option_type == "Call":
                    if spot_price >= strike:
                        trade_qty = exercise_qty
                        self.update_underlying(
                            timestamp,
                            quantity=trade_qty,
                            price=strike
                        )
                        print(f"多头认购行权 | {oid} | +{trade_qty} underlying @ {strike}")
                    else:
                        print(f"多头认购，不行权 | {oid}")
                # Long Put
                else:
                    if spot_price <= strike:
                        trade_qty = -exercise_qty
                        self.update_underlying(
                            timestamp,
                            quantity=trade_qty,
                            price=strike
                        )
                        print(f"多头认沽行权 | {oid} | {trade_qty} underlying @ {strike}")
                    else:
                        print(f"多头认沽，不行权 | {oid}")

            # =====================================================
            # 空头期权
            # =====================================================
            else:
                # Short Call
                if option_type == "Call":
                    if spot_price >= strike:
                        trade_qty = -exercise_qty
                        self.update_underlying(
                            timestamp,
                            quantity=trade_qty,
                            price=strike
                        )
                        print(f"空头认购行权 | {oid} | {trade_qty} underlying @ {strike}")
                    else:
                        print(f"空头认购，不行权 | {oid}")
                # Short Put
                else:
                    if spot_price <= strike:
                        trade_qty = exercise_qty
                        self.update_underlying(
                            timestamp,
                            quantity=trade_qty,
                            price=strike
                        )
                        print(f"空头认沽行权 | {oid} | +{trade_qty} underlying @ {strike}")
                    else:
                        print(f"空头认沽，不行权 | {oid}")

            # =====================================================
            # 删除到期期权
            # =====================================================
            del self.option_positions[oid]


    # Get current positions
    def get_positions(self):
        return {
            "underlying": self.underlying_position,
            "options": self.option_positions
        }
    
    def set_position_strike(self, strike):
        self.position_strike = strike
        return None
    
    def set_position_expire_date(self, expire_date):
        self.position_expire_date = expire_date
        return None
    
    def get_position_strike(self):
        return self.position_strike
    
    def get_position_expire_date(self):
        return self.position_expire_date
    
    def get_multiplier(self):
        return self.multiplier

    # Get available cash
    def get_cash(self):
        return self.cash