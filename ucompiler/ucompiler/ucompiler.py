# Python AST to Pycopy VM bytecode compiler
#
# This module is part of Pycopy https://github.com/pfalcon/pycopy
# and pycopy-lib https://github.com/pfalcon/pycopy-lib projects.
#
# Copyright (c) 2019, 2020 Paul Sokolovsky
#
# The MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
import ast
import usymtable
from ubytecode import Bytecode, get_opcode_ns
import mpylib
import ulogging


log = ulogging.getLogger(__name__)

opc = get_opcode_ns()


class Compiler(ast.NodeVisitor):

    def __init__(self, symtab_map, filename="<file>"):
        self.filename = filename
        self.symtab_map = symtab_map
        # Symtab for current scope
        self.symtab = None
        self.bc = None

    def stmt_list_visit(self, lst):
        for s in lst:
            log.debug("%s", ast.dump(s))
            org_stk_ptr = self.bc.stk_ptr
            self.visit(s)
            # Each complete statement should have zero cumulative stack effect
            assert self.bc.stk_ptr == org_stk_ptr, "%d vs %d" % (self.bc.stk_ptr, org_stk_ptr)

    def visit_Module(self, node):
        self.symtab = self.symtab_map[node]
        self.bc = Bytecode()
        self.stmt_list_visit(node.body)
        self.bc.add(opc.LOAD_CONST_NONE)
        self.bc.add(opc.RETURN_VALUE)

    def visit_Expr(self, node):
        self.visit(node.value)
        self.bc.add(opc.POP_TOP)

    def visit_Call(self, node):
        assert not node.keywords
        self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        self.bc.add(opc.CALL_FUNCTION, len(node.args), 0)

    def visit_BinOp(self, node):
        binop_map = {
            ast.Add: opc.BINARY_ADD,
        }
        self.visit(node.left)
        self.visit(node.right)
        self.bc.add(binop_map[type(node.op)])

    def visit_Name(self, node):
        scope = self.symtab.get_scope(node.id)
        if isinstance(node.ctx, ast.Load):
            op = [opc.LOAD_NAME, opc.LOAD_GLOBAL, opc.LOAD_FAST_N, opc.LOAD_DEREF][scope]
        elif isinstance(node.ctx, ast.Store):
            op = [opc.STORE_NAME, opc.STORE_GLOBAL, opc.STORE_FAST_N, opc.STORE_DEREF][scope]
        else:
            assert 0

        if scope in (usymtable.SCOPE_FAST, usymtable.SCOPE_DEREF):
            id = self.symtab.get_fast_local(node.id)
            self.bc.add(op, id)
        else:
            self.bc.add(op, node.id)

    def visit_Num(self, node):
        assert isinstance(node.n, int)
        assert -2**30 < node.n < 2**30 - 1
        self.bc.load_int(node.n)

    def visit_Str(self, node):
        self.bc.add(opc.LOAD_CONST_OBJ, node.s)

    def visit_Bytes(self, node):
        self.bc.add(opc.LOAD_CONST_OBJ, node.s)


def compile_ast(tree, filename="<file>"):
    symtable_b = usymtable.SymbolTableBuilder()
    symtable_b.visit(tree)

    compiler = Compiler(symtable_b.symtab_map, filename)
    compiler.visit(tree)

    co = compiler.bc.get_codeobj()
    co.co_name = "<module>"
    co.co_filename = compiler.filename
    return co