from __future__ import annotations

import ast
import operator
from typing import Any

from app.tools.registry import BaseTool


class CalculatorPlus(BaseTool):
    name = "calculator_plus"
    description = "Extended calculator tool. Evaluate safe arithmetic expressions and return results."
    input_schema = {"type": "string"}

    def execute(self, params: Any) -> str:
        expression = params if isinstance(params, str) else str(params)
        operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }
        tree = ast.parse(expression, mode="eval")
        value = self._eval_node(tree.body, operators)
        return str(value)

    def _eval_node(self, node: Any, operators: dict) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](
                self._eval_node(node.left, operators),
                self._eval_node(node.right, operators),
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](self._eval_node(node.operand, operators))
        raise ValueError("unsupported expression")
