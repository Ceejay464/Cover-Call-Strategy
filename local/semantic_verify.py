import ast,json,hashlib
class ReaderTextNormalizer(ast.NodeTransformer):
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):return None
        return self.generic_visit(node)
    def visit_Call(self,node):
        name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
        if name in {'print','write_log','ValueError','RuntimeError','KeyError'}:
            node=self.generic_visit(node)
            def message(v):
                if isinstance(v,ast.Constant) and isinstance(v.value,str):return ast.Constant(value='<reader text>')
                if isinstance(v,ast.JoinedStr):
                    return ast.Tuple(elts=[x for x in v.values if isinstance(x,ast.FormattedValue)],ctx=ast.Load())
                return v
            node.args=[message(x) for x in node.args]
            for kw in node.keywords:kw.value=message(kw.value)
            return node
        if name in {'ValueError','RuntimeError','KeyError'}:
            node=self.generic_visit(node)
            node.args=[ast.Constant(value='<exception text>') if isinstance(x,ast.Constant) and isinstance(x.value,str) else x for x in node.args]
            return node
        return self.generic_visit(node)
    def visit_FormattedValue(self,node):
        node=self.generic_visit(node)
        if isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
            node.value=ast.Constant(value='<formatted display label>')
        return node
    def visit_JoinedStr(self,node):
        node=self.generic_visit(node)
        # F-string reader labels are normalized; all evaluated expressions and their fields remain.
        node.values=[x for x in node.values if not isinstance(x,ast.Constant)]
        return node
    def visit_Constant(self,node):
        if node.value in ('调仓执行: ','Execute rebalancing: ',' 策略日志输出 ',' Strategy log output '):return ast.Constant(value='<rebalance log prefix>')
        if node.value in ('动态现金管理','Dynamic cash management','直接缩放权重','Direct weight scaling'):
            return ast.Constant(value='<capital mode label>')
        if node.value in ('日期=%{x}<br>','Date=%{x}<br>','净值=%{y:,.2f}<extra></extra>','NAV=%{y:,.2f}<extra></extra>'):
            return ast.Constant(value='<hover label>')
        return node

def fingerprint(source):
    tree=ReaderTextNormalizer().visit(ast.parse(source))
    return hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest()
