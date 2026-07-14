import pandas as pd

class OptionWheelStrategy:

    def __init__(self, quantity=1, level=1):
        """
        quantity: 期权张数
        level: 虚值档位（正数=虚值，负数=实值）
        """
        self.quantity = quantity
        self.level = level

        # 锁定当前持仓对应期权到期日
        self.lock_expiry = None

        # 防止重复行权
        self.exercised = False

        # 跟踪当前阶段：'cash' 或 'holding'
        self.phase = 'cash'  # 'cash' 表示持有现金阶段，'holding' 表示持有ETF阶段

    # =========================================================
    # ETF价格
    # =========================================================
    def get_trade_price(self, snapshot):
        return snapshot.iloc[0]["close"]

    # =========================================================
    # 主逻辑
    # =========================================================
    def generate_signal(self, timestamp, underlying_snapshot, option_snapshot, portfolio, option_db):

        date = pd.Timestamp(timestamp).normalize()
        orders = []

        if option_snapshot is None or option_snapshot.empty:
            return orders

        # =====================================================
        # ETF spot
        # =====================================================
        spot = self.get_trade_price(underlying_snapshot)

        # =====================================================
        # front chain
        # =====================================================
        front_chain = option_db.get_front_expiry_chain(option_snapshot)
        if front_chain is None or front_chain.empty:
            return orders

        # =====================================================
        # ATM strike
        # =====================================================
        atm_strike = option_db.get_atm_strike(front_chain, spot)

        # =====================================================
        # option selection
        #   - 虚值Call (OTM Call) 和 虚值Put (OTM Put)
        #   - 实值Call (ITM Call) 用于备选
        # =====================================================
        call_otm, put_otm = option_db.get_option_pair_by_level(
            front_chain, atm_strike, level=self.level
        )

        call_itm, put_itm = option_db.get_option_pair_by_level(
            front_chain, atm_strike, level=-self.level
        )

        has_level_option = (call_otm is not None and put_otm is not None)

        if has_level_option:
            call_otm = call_otm.iloc[0]
            put_otm = put_otm.iloc[0]

        # =====================================================
        # portfolio
        # =====================================================
        pos = portfolio.get_positions()
        underlying_pos = pos["underlying"]
        option_pos = pos["options"]

        has_option = len(option_pos) > 0

        # =====================================================
        # 到期行权（只执行一次）
        # =====================================================
        if self.lock_expiry is not None and not self.exercised:

            expiry = pd.Timestamp(self.lock_expiry).normalize()

            if date >= expiry:

                print(f"\n{'='*60}")
                print(f"[EXERCISE] 到期日: {self.lock_expiry} | 当前日期: {date}")
                print(f"{'='*60}")

                # 执行行权
                portfolio.exercise_options(
                    timestamp=date,
                    spot_price=spot,
                    option_date=option_snapshot
                )

                self.exercised = True

                # 检查行权后状态
                pos_after = portfolio.get_positions()
                underlying_after = pos_after["underlying"]

                print(f"[行权后] ETF持仓: {underlying_after} 份")

                # 重置状态
                self.lock_expiry = None
                self.exercised = False

                # 更新阶段
                if underlying_after == 0:
                    self.phase = 'cash'
                    print("[阶段切换] 现金阶段 (Cash Phase)")
                else:
                    self.phase = 'holding'
                    print("[阶段切换] 持仓阶段 (Holding Phase)")

                return orders

        # =====================================================
        # CASH 阶段：卖 Put（现金担保）
        # =====================================================
        if underlying_pos == 0:
            self.phase = 'cash'

            if (not has_option) and has_level_option:

                # 确保在到期日之前开仓
                if pd.Timestamp(put_otm["expire_date"]) > date:

                    orders.append({
                        "instrument": "option",
                        "order_book_id": put_otm["order_book_id"],
                        "quantity": -self.quantity,  # 负数 = 卖出
                        "price": put_otm["close"],
                        "expire_date": put_otm["expire_date"],
                        "option_type": "Put"
                    })

                    self.lock_expiry = put_otm["expire_date"]

                    print(f"\n[SELL PUT] {date} {put_otm['order_book_id']}")
                    print(f"  行权价: {put_otm['strike_price']}")
                    print(f"  权利金: {put_otm['close']:.4f}")
                    print(f"  到期日: {self.lock_expiry}")

                    return orders

        # =====================================================
        # HOLDING ETF：卖 Call（备兑）
        # =====================================================
        else:
            self.phase = 'holding'

            if (not has_option) and has_level_option:

                # 检查ETF持仓是否足够
                required = self.quantity * portfolio.get_multiplier()

                if underlying_pos >= required:

                    # 确保在到期日之前开仓
                    if pd.Timestamp(call_otm["expire_date"]) > date:

                        orders.append({
                            "instrument": "option",
                            "order_book_id": call_otm["order_book_id"],
                            "quantity": -self.quantity,  # 负数 = 卖出
                            "price": call_otm["close"],
                            "expire_date": call_otm["expire_date"],
                            "option_type": "Call"
                        })

                        self.lock_expiry = call_otm["expire_date"]

                        print(f"\n[SELL CALL] {date} {call_otm['order_book_id']}")
                        print(f"  行权价: {call_otm['strike_price']}")
                        print(f"  权利金: {call_otm['close']:.4f}")
                        print(f"  到期日: {self.lock_expiry}")
                        print(f"  ETF持仓: {underlying_pos} 份")

                        return orders

        return orders