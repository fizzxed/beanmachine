// Copyright (c) Facebook, Inc. and its affiliates.
#pragma once
#include <string>
#include "beanmachine/graph/graph.h"

namespace beanmachine {
namespace distribution {

class Distribution : public graph::Node {
 public:
  static std::unique_ptr<Distribution> new_distribution(
      graph::DistributionType dist_type,
      graph::ValueType sample_type,
      const std::vector<graph::Node*>& in_nodes);

  Distribution(graph::DistributionType dist_type, graph::AtomicType sample_type)
      : graph::Node(graph::NodeType::DISTRIBUTION),
        dist_type(dist_type),
        sample_type(sample_type) {}
  Distribution(graph::DistributionType dist_type, graph::ValueType sample_type)
      : graph::Node(graph::NodeType::DISTRIBUTION),
        dist_type(dist_type),
        sample_type(sample_type) {}
  virtual graph::AtomicValue sample(std::mt19937& gen) const = 0;
  virtual void sample(
      std::mt19937& /* gen */,
      graph::AtomicValue& /* sample_value */) const {
    throw std::invalid_argument(
        "this method has not been implemented for this distribution.");
  }
  void eval(std::mt19937& /* */) override {
    throw std::runtime_error(
        "internal error: eval() is not implemented for distribution");
  }
  // tell the compiler that we want the base class log_prob method
  // as well as the new one in this class
  using graph::Node::log_prob;
  virtual double log_prob(const graph::AtomicValue& value) const = 0;
  // these function add the gradients to the passed in gradients
  virtual void gradient_log_prob_value(
      const graph::AtomicValue& value,
      double& grad1,
      double& grad2) const = 0;
  virtual void gradient_log_prob_value(
      const graph::AtomicValue& /* value */,
      Eigen::MatrixXd& /* grad1 */,
      Eigen::MatrixXd& /* grad2_diag */) const {
        throw std::invalid_argument(
            "this method has not been implemented for this distribution.");
      }
  virtual void gradient_log_prob_param(
      const graph::AtomicValue& value,
      double& grad1,
      double& grad2) const = 0;
  virtual void gradient_log_prob_param(
      const graph::AtomicValue& /* value */,
      Eigen::MatrixXd& /* grad1 */,
      Eigen::MatrixXd& /* grad2_diag */) const {
        throw std::invalid_argument(
            "this method has not been implemented for this distribution.");
      }
  graph::DistributionType dist_type;
  graph::ValueType sample_type;
};

} // namespace distribution
} // namespace beanmachine
