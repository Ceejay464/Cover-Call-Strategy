import pandas as pd

class CoverCallStrategy:

    def __init__(self, quantity, etf_quantity=None, level=1):
        """
        quantity: 期权张数（卖出Call的张数）
        etf_quantity: ETF持仓数量（张数 * 10000 = 实际份额）
        level: 虚值档位，1=虚一档，2=虚二档，以此类推
        """
        self.entry_date = None
        self.exit_date = None
        self.quantity = quantity
        self.etf_quantity = etf_quantity if etf_quantity is not None else quantity
        self.level = level  # ✅ 新增：虚值档位参数
        self.next_entry_date = None
        self.roll_date = None
        
        # ===== 行权控制 =====
        self.lock_expiry = None      # 当前持仓的到期日
        self.exercised = False       # 标记当天是否已行权
        
    # =========================================================
    def close_all_options(self, option_snapshot, option_position, portfolio):
        """平仓所有期权"""
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

        return orders

    # =========================================================
    def generate_signal(self, timestamp, underlying_snapshot, option_snapshot, portfolio, option_db):

        orders = []
        date = pd.Timestamp(timestamp).normalize()

        if option_snapshot is None or option_snapshot.empty:
            return orders

        spot = underlying_snapshot.iloc[0]["close"]

        # =====================================================
        # 获取近月到期链
        # =====================================================
        front_chain = option_db.get_front_expiry_chain(option_snapshot)
        if front_chain is None or front_chain.empty:
            return orders

        second_chain = option_db.get_second_expiry_chain(option_snapshot)

        # =====================================================
        # 获取虚值Call（根据 level 参数）
        #   level=1: 虚一档
        #   level=2: 虚二档
        #   level=-1: 实一档（价内）
        # =====================================================
        atm_strike = option_db.get_atm_strike(front_chain, spot)
        call_otm, _ = option_db.get_option_pair_by_level(front_chain, atm_strike, level=self.level)
        
        if call_otm is None or call_otm.empty:
            return orders

        call = call_otm.iloc[0]
        front_expiry = pd.Timestamp(call["expire_date"]).normalize()

        # =====================================================
        # 获取当前持仓状态
        # =====================================================
        current_position = portfolio.get_positions()
        underlying_position = current_position["underlying"]
        option_position = current_position["options"]

        has_option_position = any(option_position[oid]["quantity"] != 0 for oid in option_position)

        # =====================================================
        # BLOCK: re-entry control
        # =====================================================
        if self.next_entry_date is not None:
            if isinstance(self.next_entry_date, str):
                self.next_entry_date = pd.Timestamp(self.next_entry_date).normalize()
            if date < self.next_entry_date:
                return orders

        # =====================================================
        # RULE 1: 到期行权（策略内部控制）
        # =====================================================
        if self.lock_expiry is not None and not self.exercised:

            expiry = pd.Timestamp(self.lock_expiry).normalize()

            if date >= expiry:

                print(f"\n{'='*60}")
                print(f"[EXERCISE] 到期日: {self.lock_expiry} | 当前日期: {date}")
                print(f"  虚值档位: {self.level}")
                print(f"{'='*60}")

                # ===== 行权前持仓 =====
                print(f"  行权前期权持仓: {len(option_position)} 个合约")
                for oid, pos in option_position.items():
                    print(f"    {oid}: {pos['quantity']} 张 | 到期: {pos['expire_date']}")

                # ===== 执行行权 =====
                portfolio.exercise_options(
                    timestamp=date,
                    spot_price=spot,
                    option_date=option_snapshot
                )

                self.exercised = True

                # ===== 行权后持仓 =====
                current_pos_after = portfolio.get_positions()
                underlying_after = current_pos_after["underlying"]
                option_after = current_pos_after["options"]

                print(f"\n  [行权后] ETF持仓: {underlying_after} 份")
                print(f"  [行权后] 期权持仓: {len(option_after)} 个合约")

                # =====================================================
                # 行权后重新建仓（Roll到次近月）
                # =====================================================
                target_etf_shares = self.etf_quantity * 10000
                
                print(f"\n  🔄 行权后重新建仓（Roll到次近月）...")
                
                if second_chain is not None and not second_chain.empty:
                    atm_strike_new = option_db.get_atm_strike(second_chain, spot)
                    call_new, _ = option_db.get_option_pair_by_level(second_chain, atm_strike_new, level=self.level)
                    
                    if call_new is not None and not call_new.empty:
                        new_call = call_new.iloc[0]
                        new_expiry = pd.Timestamp(new_call["expire_date"]).normalize()
                        
                        # 补足ETF持仓
                        if underlying_after < target_etf_shares:
                            buy_qty = target_etf_shares - underlying_after
                            orders.append({
                                "instrument": "underlying",
                                "quantity": buy_qty
                            })
                            print(f"     ETF: +{buy_qty}份 @ {spot:.4f} (补足到 {target_etf_shares}份)")
                        elif underlying_after > target_etf_shares:
                            sell_qty = underlying_after - target_etf_shares
                            orders.append({
                                "instrument": "underlying",
                                "quantity": -sell_qty
                            })
                            print(f"     ETF: -{sell_qty}份 @ {spot:.4f} (减少到 {target_etf_shares}份)")
                        else:
                            print(f"     ETF: 持仓正好 {target_etf_shares}份，无需调整")
                        
                        # 卖出新的虚值Call
                        orders.append({
                            "instrument": "option",
                            "order_book_id": new_call["order_book_id"],
                            "quantity": -self.quantity,
                            "price": new_call["close"],
                            "expire_date": new_call["expire_date"],
                            "option_type": "Call"
                        })
                        
                        # 更新状态
                        self.lock_expiry = new_expiry
                        portfolio.set_position_expire_date(new_expiry)
                        portfolio.set_position_strike(new_call["strike_price"])
                        self.entry_date = date
                        self.next_entry_date = None
                        self.exercised = False
                        
                        print(f"  ✅ 重新建仓成功:")
                        print(f"     新Call: {new_call['order_book_id']} | 行权价: {new_call['strike_price']} | 到期: {new_expiry} | 权利金: {new_call['close']}")
                    else:
                        self.lock_expiry = None
                        self.exercised = False
                        self.next_entry_date = date + pd.Timedelta(days=1)
                        portfolio.set_position_expire_date(None)
                        portfolio.set_position_strike(None)
                        print(f"  ⚠️ 未找到次近月Call，等待下一个交易日重新建仓")
                else:
                    self.lock_expiry = None
                    self.exercised = False
                    self.next_entry_date = date + pd.Timedelta(days=1)
                    portfolio.set_position_expire_date(None)
                    portfolio.set_position_strike(None)
                    print(f"  ⚠️ 没有次近月合约，等待下一个交易日重新建仓")

                print(f"{'='*60}\n")
                
                # 重置行权标记
                self.exercised = False
                
                return orders

        # =====================================================
        # RULE 2: 到期日检查（如果 lock_expiry 为 None，但持仓还在）
        # =====================================================
        if self.lock_expiry is None and has_option_position:
            position_expire_date = portfolio.get_position_expire_date()
            if position_expire_date is not None:
                if isinstance(position_expire_date, str):
                    position_expire_date = pd.Timestamp(position_expire_date).normalize()
                self.lock_expiry = position_expire_date

        # =====================================================
        # RULE 3: 初始开仓 / 重新建仓（非到期日）
        # =====================================================
        if not has_option_position:
            
            if date >= front_expiry:
                return orders

            # =====================================================
            # 1. 买入ETF底仓
            # =====================================================
            etf_shares = self.etf_quantity * 10000
            
            if underlying_position < etf_shares:
                buy_qty = etf_shares - underlying_position
                if buy_qty > 0:
                    orders.append({
                        "instrument": "underlying",
                        "quantity": buy_qty
                    })
            elif underlying_position > etf_shares:
                sell_qty = underlying_position - etf_shares
                if sell_qty > 0:
                    orders.append({
                        "instrument": "underlying",
                        "quantity": -sell_qty
                    })
            elif underlying_position == 0:
                orders.append({
                    "instrument": "underlying",
                    "quantity": etf_shares
                })

            # =====================================================
            # 2. 卖出虚值Call（根据 level 参数）
            # =====================================================
            orders.append({
                "instrument": "option",
                "order_book_id": call["order_book_id"],
                "quantity": -self.quantity,
                "price": call["close"],
                "expire_date": call["expire_date"],
                "option_type": "Call"
            })

            # =====================================================
            # 3. 更新状态
            # =====================================================
            self.entry_date = date
            self.lock_expiry = front_expiry
            portfolio.set_position_expire_date(front_expiry)
            portfolio.set_position_strike(call["strike_price"])
            self.next_entry_date = None
            self.roll_date = None
            self.exercised = False

            print(f"INITIAL ENTRY: {date} | 买入ETF {etf_shares}份 | 卖出Call: {call['order_book_id']} | 行权价: {call['strike_price']} | 到期: {front_expiry} | 权利金: {call['close']} | 虚值档位: {self.level}")

        return orders