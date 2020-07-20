# Copyright (c) Facebook, Inc. and its affiliates.

"""This module takes a Bean Machine Graph builder and makes a best
effort attempt to transform the accumulated graph to meet the
requirements of the BMG type system. All possible transformations
are made; if there are nodes that cannot be represented in BMG
or cannot be made to meet type requirements, an error report is
returned."""

from beanmachine.ppl.compiler.bmg_nodes import (
    BMGNode,
    ConstantNode,
    DistributionNode,
    IndexNode,
    MapNode,
    MultiplicationNode,
    Observation,
    OperatorNode,
    Query,
    SampleNode,
)
from beanmachine.ppl.compiler.bmg_types import (
    Malformed,
    Natural,
    PositiveReal,
    Probability,
    Real,
    Requirement,
    UpperBound,
    meets_requirement,
    supremum,
    upper_bound,
)
from beanmachine.ppl.compiler.error_report import ErrorReport, Violation
from beanmachine.ppl.utils.bm_graph_builder import BMGraphBuilder
from torch import Tensor


class Fixer:
    """This class takes a Bean Machine Graph builder and attempts to
fix all the problems which prevent it from being a legal Bean Machine
Graph, such as violations of type system requirements or use of
unsupported operators.

The basic idea is that every *edge* in the graph has a *requirement*, such as
"the type of the input must be Probability".  We do a traversal of the input
edges of every node in the graph; if the input node meets the requirement,
it is unchanged. If it does not, then a new node that has the same semantics
that meets the requirement is returned. If there is no such node then an
error is added to the error report."""

    errors: ErrorReport
    bmg: BMGraphBuilder

    def __init__(self, bmg: BMGraphBuilder) -> None:
        self.errors = ErrorReport()
        self.bmg = bmg

    def _meet_constant_requirement(
        self, node: ConstantNode, requirement: Requirement, consumer: BMGNode, edge: str
    ) -> BMGNode:
        # If the constant node already meets the requirement, we're done.
        if meets_requirement(node.graph_type, requirement):
            return node

        # It does not meet the requirement. Is there a semantically equivalent node
        # that does meet the requirement?

        # The inf type is defined as the smallest type to which the node can be converted.
        # If the infimum type is smaller than or equal to the required type, then the
        # node can definitely be converted to a type which meets the requirement.

        if meets_requirement(node.inf_type, upper_bound(requirement)):

            # To what type should we convert the node to meet the requirement?
            # If the requirement is an exact bound, then that's the type we need to
            # convert to. If the requirement is an upper bound, there's no reason
            # why we can't just convert to that type.

            required_type = (
                requirement.bound
                if isinstance(requirement, UpperBound)
                else requirement
            )
            return self.bmg.add_constant_of_type(node.value, required_type)

        # We cannot convert this node to any type that meets the requirement.
        # Add an error.
        self.errors.add_error(Violation(node, requirement, consumer, edge))
        return node

    def _meet_distribution_requirement(
        self,
        node: DistributionNode,
        requirement: Requirement,
        consumer: BMGNode,
        edge: str,
    ) -> BMGNode:
        # The only edges which point to distributions are samples, and the requirement
        # on that edge is always met automatically.
        assert isinstance(consumer, SampleNode)
        assert requirement == node.inf_type
        return node

    def _meet_map_requirement(
        self, node: MapNode, requirement: Requirement, consumer: BMGNode, edge: str
    ) -> BMGNode:
        # The only edges which point to maps are indexes, and the requirement
        # on that edge is always met automatically.
        # TODO: We do not support map nodes in BMG yet, so:
        # TODO: (1) this code path is not exercised by any test case; when
        # TODO: we support map nodes, add a test case.
        # TODO: (2) until we do support map nodes in BMG, we should add an
        # TODO: error reporting pass to this code that detects map nodes
        # TODO: and gives an unsupported node type error.
        assert isinstance(consumer, IndexNode)
        assert requirement == node.inf_type
        return node

    def _convert_malformed_multiplication(
        self, node: MultiplicationNode, requirement: type, consumer: BMGNode, edge: str
    ) -> BMGNode:
        # We are given a malformed multiplication node which can be converted
        # to a semantically equivalent node that meets the given requirement.
        # Verify these preconditions.

        assert node.graph_type == Malformed
        assert supremum(node.inf_type, requirement) == requirement

        # Under what conditions can a multiplication be malformed?
        #
        # * Its operand types are not equal
        # * Its operand types are not probability or larger

        lgt = node.left.graph_type
        rgt = node.right.graph_type

        # Which of those conditions are possible at this point? Remember,
        # we visit nodes in topological order, so the requirements of the
        # left and right operands have already been met and they are converted
        # to their correct types.
        #
        # * If its operands were malformed, those malformations would have already
        #   been fixed. We never leave a reachable malformed node in the graph.

        assert lgt != Malformed and rgt != Malformed

        # * If its operands were any combination of natural, probability,
        #   positive real, real or tensor, then we would already have converted
        #   them both to the smallest possible common type larger than probability.
        #   They would therefore be equal.
        #
        # * Therefore, for this node to be malformed, at least one of its operands
        #   must be bool.

        assert lgt == bool or rgt == bool

        # * In that case, we can convert it to an if-then-else.

        if lgt == bool:
            zero = self.bmg.add_constant_of_type(0.0, rgt)
            if_then_else = self.bmg.add_if_then_else(node.left, node.right, zero)
            assert if_then_else.graph_type == rgt
        else:
            zero = self.bmg.add_constant_of_type(0.0, lgt)
            if_then_else = self.bmg.add_if_then_else(node.right, node.left, zero)
            assert if_then_else.graph_type == lgt

        # We have met the requirements of the if-then-else; the condition
        # is bool and the consequence and alternative are of the same type.
        # However, we might not yet have met the original requirement, which
        # we have not yet used in this method. We might need to put a to_real
        # on top of it, for instance.
        #
        # Recurse to ensure that is met.

        return self.meet_requirement(if_then_else, requirement, consumer, edge)

    def _convert_node(
        self, node: OperatorNode, requirement: type, consumer: BMGNode, edge: str
    ) -> BMGNode:
        # We have been given a node which does not meet a requirement,
        # but it can be converted to a node which does meet the requirement
        # that has the same semantics. Start by confirming those preconditions.
        assert node.graph_type != requirement
        assert supremum(node.inf_type, requirement) == requirement

        if isinstance(node, MultiplicationNode) and node.graph_type == Malformed:
            return self._convert_malformed_multiplication(
                node, requirement, consumer, edge
            )

        # Converting anything to tensor, real or positive real is easy;
        # there's already a node for that so just insert it on the edge
        # whose requirement is not met, and the requirement will be met.

        if requirement == Tensor:
            return self.bmg.add_to_tensor(node)
        if requirement == Real:
            return self.bmg.add_to_real(node)
        if requirement == PositiveReal:
            return self.bmg.add_to_positive_real(node)

        # We are not converting to tensor, float and positive real.
        # Our precondition is that the requirement is larger than
        # *something*, which means that it cannot be bool.
        # That means the requirement must be either natural or
        # probability. Verify this.

        assert requirement == Natural or requirement == Probability

        # Our precondition is that the requirement is larger than the
        # inf type of the node. The only inf type that meets that
        # condition is bool, so verify that.

        assert node.inf_type == bool

        # There is no "to natural" or "to probability" but since we have
        # a bool in hand, we can use an if-then-else as a conversion.

        zero = self.bmg.add_constant_of_type(0.0, requirement)
        one = self.bmg.add_constant_of_type(1.0, requirement)
        return self.bmg.add_if_then_else(node, one, zero)

    def _meet_operator_requirement(
        self, node: OperatorNode, requirement: Requirement, consumer: BMGNode, edge: str
    ) -> BMGNode:
        # If the operator node already meets the requirement, we're done.
        if meets_requirement(node.graph_type, requirement):
            return node

        # It does not meet the requirement. Can we convert this thing to a node
        # whose type does meet the requirement? Remember, the inf type is the
        # smallest type that this node is convertible to, so if the inf type
        # meets an upper bound requirement, then the conversion we want exists.

        it = node.inf_type

        if not meets_requirement(it, upper_bound(requirement)):
            # No; add an error.
            self.errors.add_error(Violation(node, requirement, consumer, edge))
            return node

        # We definitely can meet the requirement; it just remains to figure
        # out exactly how.
        #
        # There are now two possibilities:
        #
        # * The requirement is an exact requirement. We know that the node
        #   can be converted to that type, because its inf type meets an
        #   upper bound requirement. Convert it to that exact type.
        #
        # * The requirement is an upper-bound requirement, and the inf type
        #   meets it. Convert the node to the inf type.

        if isinstance(requirement, type):
            result = self._convert_node(node, requirement, consumer, edge)
        else:
            result = self._convert_node(node, it, consumer, edge)

        assert meets_requirement(result.graph_type, requirement)
        return result

    def meet_requirement(
        self, node: BMGNode, requirement: Requirement, consumer: BMGNode, edge: str
    ) -> BMGNode:
        """The consumer node consumes the value of the input node. The consumer's
requirement is given; the name of this edge is provided for error reporting."""

        if isinstance(node, Observation):
            raise AssertionError(
                "Unexpected graph topology; an observation is never an input"
            )
        if isinstance(node, Query):
            raise AssertionError("Unexpected graph topology; a query is never an input")
        if isinstance(node, ConstantNode):
            return self._meet_constant_requirement(node, requirement, consumer, edge)
        if isinstance(node, DistributionNode):
            return self._meet_distribution_requirement(
                node, requirement, consumer, edge
            )
        if isinstance(node, MapNode):
            return self._meet_map_requirement(node, requirement, consumer, edge)
        if isinstance(node, OperatorNode):
            return self._meet_operator_requirement(node, requirement, consumer, edge)
        raise AssertionError("Unexpected node type")

    def meet_all_requirements(self, node: BMGNode) -> None:
        requirements = node.requirements
        for i in range(len(requirements)):
            node.children[i] = self.meet_requirement(
                node.children[i], requirements[i], node, node.edges[i]
            )

    def fix_all_problems(self) -> None:
        nodes = self.bmg._traverse_from_roots()
        # TODO: Find nodes we do not support, and transform them
        # into nodes we do support when possible; produce an error
        # otherwise.
        for node in nodes:
            self.meet_all_requirements(node)


def fix_problems(bmg: BMGraphBuilder) -> ErrorReport:
    fixer = Fixer(bmg)
    fixer.fix_all_problems()
    return fixer.errors
