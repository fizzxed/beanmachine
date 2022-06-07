# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


import beanmachine.ppl.compiler.bmg_nodes as bn
from beanmachine.ppl.compiler.bm_graph_builder import BMGraphBuilder
from beanmachine.ppl.compiler.fix_problem import (
    Inapplicable,
    NodeFixer,
    NodeFixerResult,
)
from beanmachine.ppl.compiler.lattice_typer import LatticeTyper
from beanmachine.ppl.compiler.sizer import is_scalar, Sizer


def matrix_scale_fixer(bmg: BMGraphBuilder, sizer: Sizer) -> NodeFixer:
    """This node fixer attempts to rewrite binary multiplications that involve
    a matrix and a scalar into a matrix_scale node."""

    def fixer(n: bn.BMGNode) -> NodeFixerResult:
        # A matrix multiplication is fixable (to matrix_scale) if it is
        # a binary multiplication with non-singleton result size
        # and the size of one argument is matrix and the other is scalar
        if not isinstance(n, bn.MultiplicationNode) or len(n.inputs) != 2:
            return Inapplicable
        # Now let's check the sizes of the inputs
        input_scalars = [is_scalar(sizer[i]) for i in n.inputs]
        # If both are scalar, then there is nothing to do
        if all(input_scalars):
            return Inapplicable  # Both are scalar
        # If both are matrices, then there is nothing to do
        if all(not t for t in input_scalars):
            return Inapplicable  # Both are matrices
        # The return type of the node should be matrix
        assert not is_scalar(sizer[n])
        left, right = n.inputs
        if input_scalars[1]:
            scalar, matrix = right, left
        else:
            scalar, matrix = left, right
        return bmg.add_matrix_scale(scalar, matrix)

    return fixer


def trivial_matmul_fixer(bmg: BMGraphBuilder, typer: LatticeTyper) -> NodeFixer:
    """This node fixer attempts to rewrite matrix multiplications of two scalars
    into an ordinary multiplication."""

    def fixer(n: bn.BMGNode) -> NodeFixerResult:
        if not isinstance(n, bn.MatrixMultiplicationNode):
            return Inapplicable
        left = n.inputs[0]
        left_type = typer[left]
        if not left_type.is_singleton():
            return Inapplicable
        right = n.inputs[1]
        right_type = typer[right]
        if not right_type.is_singleton():
            return Inapplicable
        return bmg.add_multiplication(left, right)

    return fixer
