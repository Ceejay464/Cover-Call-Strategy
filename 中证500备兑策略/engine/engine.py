import pandas as pd

class BacktestEngine:

    def __init__(
        self,
        option_db,
        option_strategy,
        underlying_strategy,
        portfolio
    ):
        self.option_db = option_db
        self.option_strategy = option_strategy
        self.underlying_strategy = underlying_strategy
        self.portfolio = portfolio

        self.timeline = None
        self.results = []

    # ---------------------------------------------------------
    # Build timeline
    # ---------------------------------------------------------
    def prepare_timeline(self, start=None, end=None):

        times = self.option_db.underlying_df["date"].unique()
        times = sorted(times)

        if start is not None:
            start = pd.Timestamp(start)
            times = [t for t in times if pd.Timestamp(t) >= start]

        if end is not None:
            end = pd.Timestamp(end)
            times = [t for t in times if pd.Timestamp(t) <= end]

        self.timeline = times

    # ---------------------------------------------------------
    # Get snapshot
    # ---------------------------------------------------------
    def get_option_snapshot(self, date):
        chain = self.option_db.get_chain(date)
        if chain is None:
            return None
        return chain

    def get_underlying_snapshot(self, date):
        df = self.option_db.underlying_df
        snap = df[df["date"] == date]
        return snap

    # ---------------------------------------------------------
    # Execute orders
    # ---------------------------------------------------------
    def process_orders(self, orders, timestamp, spot_price):
        if not orders:
            return

        for order in orders:
            if order["instrument"] == "option":
                self.portfolio.update_option(
                    timestamp=timestamp,
                    option_id=order["order_book_id"],
                    quantity=order["quantity"],
                    price=order["price"],
                    expiry=order["expire_date"],
                    option_type=order["option_type"]
                )
            elif order["instrument"] == "underlying":
                self.portfolio.update_underlying(
                    timestamp=timestamp,
                    quantity=order["quantity"],
                    price=spot_price
                )

    # ---------------------------------------------------------
    # Main loop
    # ---------------------------------------------------------
    def run(self):

        if self.timeline is None:
            self.prepare_timeline()

        for date in self.timeline:
            # ✅ 修复：分开使用 date_ts 和 date_str
            date_ts = pd.Timestamp(date)
            date_str = date_ts.strftime('%Y-%m-%d')
            
            print(date_str)

            # ===== snapshot =====
            option_snapshot = self.get_option_snapshot(date_str)
            underlying_snapshot = self.get_underlying_snapshot(date_str)

            if option_snapshot is None or underlying_snapshot.empty:
                print("today no data")
                continue

            # ===== spot =====
            spot_price = self.option_db.get_spot(date_str)

            # ===== strategy =====
            option_orders = self.option_strategy.generate_signal(
                timestamp=date_ts,  # ✅ 传入 Timestamp
                underlying_snapshot=underlying_snapshot,
                option_snapshot=option_snapshot,
                portfolio=self.portfolio,
                option_db=self.option_db
            )

            self.process_orders(option_orders, date_str, spot_price)

            underlying_orders = self.underlying_strategy.generate_signal(
                timestamp=date_ts,  # ✅ 传入 Timestamp
                underlying_snapshot=underlying_snapshot,
                option_snapshot=option_snapshot,
                portfolio=self.portfolio,
                option_db=self.option_db
            )

            self.process_orders(underlying_orders, date_str, spot_price)

            # ===== equity =====
            self.portfolio.get_equity(
                timestamp=date_str,
                option_data=option_snapshot,
                underlying_price=spot_price
            )

            self.results.append({
                "timestamp": date_str,
                "equity": self.portfolio.equity_history[-1]["equity"]
            })

        return pd.DataFrame(self.results)