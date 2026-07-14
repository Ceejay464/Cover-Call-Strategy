import pandas as pd

class OptionDatabase:
    def __init__(self, underlying_df: pd.DataFrame, option_df: pd.DataFrame):

        self.underlying_df = underlying_df.sort_values('date').copy()
        self.option_df = option_df.sort_values('date').copy()

        self.option_by_date = dict(tuple(self.option_df.groupby("date")))

    def get_chain(self, timestamp: str) -> pd.DataFrame | None:
        """
        获取某一天的全部期权链
        """
        return self.option_by_date.get(timestamp)

    def get_spot(self, date: str) -> float | None:
        """
        获取某一天的标的价格（收盘价或指定价格列）
        """
        row = self.underlying_df[self.underlying_df["date"] == date]
        # ✅ 修复：添加空值检查
        if row.empty:
            return None
        return float(row["close"].values[0])

    def split_by_expiry_date(self, option_day: pd.DataFrame) -> dict:
        """
        input: option_day 来自 self.option_by_date.get(timestamp)
        将单日期权链按 expiry_date 分组
        return: dict[expiry_date -> DataFrame]
        """
        df = option_day.copy()
        grouped = dict(tuple(df.groupby("expire_date")))
        return grouped

    def get_front_expiry_chain(self, option_day):
        expiry_dict = self.split_by_expiry_date(option_day)
        if not expiry_dict:
            return None
        front_expiry = min(expiry_dict.keys())
        return expiry_dict[front_expiry]

    def get_second_expiry_chain(self, option_day):
        expiry_dict = self.split_by_expiry_date(option_day)
        if not expiry_dict:
            return None
        sorted_expiries = sorted(expiry_dict.keys())
        second_expiry = sorted_expiries[1]
        return expiry_dict[second_expiry]

    def get_atm_strike(self, expire_chain: pd.DataFrame, spot: float):
        """
        spot: get_spot()
        输入：单个 expiry 的 option chain
        输出：ATM strike
        """
        df = expire_chain.copy()
        df["dist"] = (df["strike_price"] - spot).abs()
        atm_row = df.loc[df["dist"].idxmin()]
        return atm_row["strike_price"]

    def get_atm_pair(self, expire_chain: pd.DataFrame, atm_strike):
        """
        输入：
            expiry_chain: 单个 expiry 的 option chain
            atm_strike: ATM 行权价
        输出：
            atm_call, atm_put 数据类型：<class 'pandas.DataFrame'>
        """
        df = expire_chain.copy()
        atm_df = df[df["strike_price"] == atm_strike]
        if atm_df.empty:
            return None, None
        atm_call = atm_df[atm_df["option_type"].str.lower() == "call"]
        atm_put = atm_df[atm_df["option_type"].str.lower() == "put"]
        if atm_call.empty:
            atm_call = None
        if atm_put.empty:
            atm_put = None
        return atm_call, atm_put

    def get_option_pair_by_level(self, expire_chain, atm_strike, level=0):
        '''
        1 -> 虚一档Call和实一档Put
        2 -> 虚二档Call和实二档Put
        ................
        '''
        df = expire_chain.copy()
        strikes = sorted(df["strike_price"].unique())
        closest_strike = min(strikes, key=lambda x: abs(x - atm_strike))
        atm_index = strikes.index(closest_strike)
        target_index = atm_index + level
        if target_index < 0 or target_index >= len(strikes):
            return None, None
        target_strike = strikes[target_index]
        call = df[(df["strike_price"] == target_strike) & (df["option_type"] == "Call")]
        put = df[(df["strike_price"] == target_strike) & (df["option_type"] == "Put")]
        if call.empty or put.empty:
            return None, None
        return call, put