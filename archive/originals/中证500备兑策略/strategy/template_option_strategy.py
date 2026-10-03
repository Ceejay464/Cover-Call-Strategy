import pandas as pd

class TemplateOptionStrategy:

    def __init__(self, quantity):
        self.entry_date = None
        self.exit_date = None
        self.quantity = 1  # ✅ 改为 1 张，避免资金压力过大
        self.next_entry_date = None

    # =========================================================
    def close_all_options(self, option_snapshot, option_position, portfolio):

        orders = []

        for oid in list(option_position.keys()):

            pos = option_position[oid]
            qty = pos["quantity"]

            if qty == 0:
                continue

            option_row = option_snapshot[option_snapshot["order_book_id"] == oid]
            if option_row.empty:
                continue

            option = option_row.iloc[0]

            orders.append({
                "instrument": "option",
                "order_book_id": oid,
                "quantity": -qty,
                "price": option["close"],
                "expire_date": option["expire_date"],
                "option_type": option["option_type"]
            })

        # ✅ 修复：在循环外重置 strike
        portfolio.set_position_strike(None)
        portfolio.set_position_expire_date(None)

        return orders

    # =========================================================
    def generate_signal(self, timestamp, underlying_snapshot, option_snapshot, portfolio, option_db):

        orders = []

        # 统一将 timestamp 转换为 Timestamp
        date = pd.Timestamp(timestamp).normalize()

        if option_snapshot is None or option_snapshot.empty:
            return orders

        spot = underlying_snapshot.iloc[0]["close"]

        # =====================================================
        # front chain
        # =====================================================
        front_chain = option_db.get_front_expiry_chain(option_snapshot)
        if front_chain is None or front_chain.empty:
            return orders

        # =====================================================
        # ATM selection
        # =====================================================
        atm_strike = option_db.get_atm_strike(front_chain, spot)
        atm_call, atm_put = option_db.get_atm_pair(front_chain, atm_strike)

        if atm_call is None or atm_put is None:
            return orders

        call = atm_call.iloc[0]
        put = atm_put.iloc[0]

        # 确保 front_expiry 是 Timestamp
        front_expiry = pd.Timestamp(call["expire_date"]).normalize()

        # =====================================================
        # positions
        # =====================================================
        current_position = portfolio.get_positions()
        underlying_position = current_position["underlying"]
        option_position = current_position["options"]

        has_position = any(option_position[oid]["quantity"] != 0 for oid in option_position)

        # =====================================================
        # BLOCK: re-entry control
        # =====================================================
        if self.next_entry_date is not None:
            if isinstance(self.next_entry_date, str):
                self.next_entry_date = pd.Timestamp(self.next_entry_date).normalize()
            if date < self.next_entry_date:
                return orders

        # =====================================================
        # RULE 1: EXPIRY ROLL
        # =====================================================
        position_expire_date = portfolio.get_position_expire_date()

        if has_position and position_expire_date is not None:
            if isinstance(position_expire_date, str):
                position_expire_date = pd.Timestamp(position_expire_date).normalize()
                portfolio.set_position_expire_date(position_expire_date)
            
            if date >= position_expire_date:
                print("EXPIRY ROLL:", date)

                orders.extend(self.close_all_options(option_snapshot, option_position, portfolio))

                if underlying_position != 0:
                    orders.append({
                        "instrument": "underlying",
                        "quantity": -underlying_position
                    })

                self.entry_date = None
                self.next_entry_date = date + pd.Timedelta(days=1)

                return orders

        # =====================================================
        # RULE 2: ENTRY (跨式策略 Straddle)
        # =====================================================
        if not has_position:

            if date >= front_expiry:
                return orders

            # 买入 Call
            orders.append({
                "instrument": "option",
                "order_book_id": call["order_book_id"],
                "quantity": self.quantity,  # 正数 = 买入
                "price": call["close"],
                "expire_date": call["expire_date"],
                "option_type": "Call"
            })

            # 买入 Put
            orders.append({
                "instrument": "option",
                "order_book_id": put["order_book_id"],
                "quantity": self.quantity,  # 正数 = 买入
                "price": put["close"],
                "expire_date": put["expire_date"],
                "option_type": "Put"
            })

            # 买入 ETF 底仓
            orders.append({
                "instrument": "underlying",
                "quantity": self.quantity * 10000
            })

            # =================================================
            # UPDATE STATE (IMPORTANT)
            # =================================================
            self.entry_date = date
            portfolio.set_position_expire_date(front_expiry)
            portfolio.set_position_strike(atm_strike)

            self.next_entry_date = None

            print(f"ENTRY ATM STRADDLE: {date} | strike: {atm_strike} | expire_date: {front_expiry}")

        return orders