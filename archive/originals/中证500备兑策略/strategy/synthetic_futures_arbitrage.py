import pandas as pd

class SyntheticFuturesBasisArbitrageStrategy:

    def __init__(self, upper_threshold, down_threshold, quantity):
        """
        upper_threshold: 开仓阈值（升水），例如 0.002 表示 0.2%
        down_threshold: 平仓阈值，例如 0.001 表示 0.1%
        quantity: 期权张数
        """
        self.entry_date = None
        self.lock_expiry = None
        self.upper_threshold = upper_threshold
        self.down_threshold = down_threshold
        self.quantity = quantity

    # =========================================================
    # 获取日频成交价（收盘价）
    # =========================================================
    def get_trade_price(self, snapshot):
        return snapshot.iloc[0]["close"]

    # =========================================================
    # 平仓所有持仓
    # =========================================================
    def _close_all(self, option_snapshot, option_pos, underlying_pos, portfolio):

        orders = []

        # =========================
        # ETF 平仓
        # =========================
        if underlying_pos != 0:
            orders.append({
                "instrument": "underlying",
                "quantity": -underlying_pos
            })

        # =========================
        # 期权平仓
        # =========================
        for oid, pos in option_pos.items():

            # 从option_snapshot中查找对应的期权
            option_row = option_snapshot[option_snapshot["order_book_id"] == oid]
            if option_row.empty:
                continue

            option = option_row.iloc[0]

            orders.append({
                "instrument": "option",
                "order_book_id": oid,
                "quantity": -pos["quantity"],  # 平仓
                "price": option["close"],
                "expire_date": option["expire_date"],
                "option_type": option["option_type"]
            })

        # =========================
        # RESET PORTFOLIO STATE
        # =========================
        portfolio.set_position_strike(None)
        portfolio.set_position_expire_date(None)

        return orders

    # =========================================================
    # 状态重置
    # =========================================================
    def _reset(self):
        self.entry_date = None
        self.lock_expiry = None

    # =========================================================
    # 主逻辑
    # =========================================================
    def generate_signal(self, timestamp, underlying_snapshot, option_snapshot, portfolio, option_db):

        date = pd.Timestamp(timestamp).normalize()
        orders = []

        if option_snapshot is None or option_snapshot.empty:
            return orders

        # =========================================================
        # 1. ETF 收盘价
        # =========================================================
        spot = self.get_trade_price(underlying_snapshot)

        # =========================================================
        # 2. front expiry + ATM
        # =========================================================
        front_chain = option_db.get_front_expiry_chain(option_snapshot)
        if front_chain is None or front_chain.empty:
            return orders

        atm_strike = option_db.get_atm_strike(front_chain, spot)
        atm_call, atm_put = option_db.get_atm_pair(front_chain, atm_strike)

        if atm_call is None or atm_put is None:
            return orders

        call = atm_call.iloc[0]
        put = atm_put.iloc[0]

        call_price = call["close"]
        put_price = put["close"]

        # 确保到期日是 Timestamp
        front_expiry = pd.Timestamp(call["expire_date"]).normalize()

        # =========================================================
        # 3. synthetic futures price (put-call parity proxy)
        #    synthetic_futures = call_price - put_price + strike
        # =========================================================
        synthetic_futures = call_price - put_price + atm_strike

        basis = (synthetic_futures - spot) / spot

        # =========================================================
        # 4. 仓位状态
        # =========================================================
        pos = portfolio.get_positions()
        underlying_pos = pos["underlying"]
        option_pos = pos["options"]

        has_position = (underlying_pos != 0) or (len(option_pos) > 0)

        # =========================================================
        # 5. 强制平仓（到期日）
        # =========================================================
        if has_position and self.lock_expiry is not None:

            # 确保 lock_expiry 是 Timestamp
            if isinstance(self.lock_expiry, str):
                self.lock_expiry = pd.Timestamp(self.lock_expiry).normalize()

            if date >= self.lock_expiry:

                print(f"今天期权到期，平仓：{date}")
                orders += self._close_all(option_snapshot, option_pos, underlying_pos, portfolio)
                self._reset()
                return orders

        # =========================================================
        # 6. 平仓信号（basis 回落）
        # =========================================================
        if has_position:

            if basis <= self.down_threshold:
                print(f"今天spread变小，平仓：{date} | basis: {basis:.4%}")
                orders += self._close_all(option_snapshot, option_pos, underlying_pos, portfolio)
                self._reset()
                return orders

        # =========================================================
        # 7. 开仓信号（升水）
        # =========================================================
        if not has_position:

            # 确保是在到期日之前开仓
            if basis >= self.upper_threshold and date < front_expiry:

                print(f"今天开仓：{date} | basis: {basis:.4%} | 到期日：{front_expiry}")

                # =========================
                # ETF 多头（买入）
                # =========================
                etf_shares = self.quantity * 10000
                orders.append({
                    "instrument": "underlying",
                    "quantity": etf_shares
                })

                # =========================
                # 合成期货空头
                #   卖出 Call（空头）
                #   买入 Put（多头）
                # =========================
                orders.append({
                    "instrument": "option",
                    "order_book_id": call["order_book_id"],
                    "quantity": -self.quantity,  # 负数 = 卖出
                    "price": call_price,
                    "expire_date": call["expire_date"],
                    "option_type": "Call"
                })

                orders.append({
                    "instrument": "option",
                    "order_book_id": put["order_book_id"],
                    "quantity": self.quantity,  # 正数 = 买入
                    "price": put_price,
                    "expire_date": put["expire_date"],
                    "option_type": "Put"
                })

                # =========================
                # 记录状态
                # =========================
                self.entry_date = date
                self.lock_expiry = front_expiry

                portfolio.set_position_strike(atm_strike)
                portfolio.set_position_expire_date(front_expiry)

                print(f"  开仓详情：")
                print(f"    ETF: +{etf_shares}份 @ {spot:.4f}")
                print(f"    卖出Call: {call['order_book_id']} @ {call_price:.4f}")
                print(f"    买入Put: {put['order_book_id']} @ {put_price:.4f}")
                print(f"    合成期货价格: {synthetic_futures:.4f}")
                print(f"    基差: {basis:.4%}")

        return orders