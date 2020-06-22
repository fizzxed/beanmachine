# Copyright (c) Facebook, Inc. and its affiliates.
from typing import List, Optional

from beanmachine.ppl.inference.abstract_mh_infer import AbstractMHInference
from beanmachine.ppl.inference.proposer.single_site_random_walk_proposer import (
    SingleSiteRandomWalkProposer,
)
from beanmachine.ppl.model.utils import RVIdentifier
from beanmachine.ppl.world.world import TransformType


class SingleSiteRandomWalk(AbstractMHInference):
    """
    Implementation for SingleSiteNewtonianMonteCarlo
    """

    def __init__(
        self,
        step_size: float = 1.0,
        num_adapt_windows: int = 5,
        transform_type: TransformType = TransformType.NONE,
        transforms: Optional[List] = None,
    ):
        self.proposer_ = SingleSiteRandomWalkProposer(step_size, num_adapt_windows)
        super().__init__(self.proposer_, transform_type, transforms)

    def find_best_single_site_proposer(self, node: RVIdentifier):
        """
        Finds the best proposer for a node which is
        SingleSiteRandomWalkProposer for
        SingleSiteRandomWalk

        :param node: the node for which to return a proposer
        :returns: a proposer for the node
        """
        return self.proposer_
