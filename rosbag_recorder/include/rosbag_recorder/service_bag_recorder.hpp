// Copyright 2025 ROBOTIS CO., LTD.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// Author: Woojin Wie, Kiwoong Park


#ifndef ROSBAG_RECORDER__SERVICE_BAG_RECORDER_HPP_
#define ROSBAG_RECORDER__SERVICE_BAG_RECORDER_HPP_

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <map>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp/generic_subscription.hpp>
#include <rosbag2_cpp/writer.hpp>
#include <rosbag2_storage/storage_options.hpp>

#include "rosbag_recorder/srv/send_command.hpp"


class ServiceBagRecorder : public rclcpp::Node
{
public:
  ServiceBagRecorder();

  // Callback groups for parallel processing with MultiThreadedExecutor
  rclcpp::CallbackGroup::SharedPtr camera_callback_group_;
  rclcpp::CallbackGroup::SharedPtr joint_callback_group_;
  rclcpp::CallbackGroup::SharedPtr other_callback_group_;
  rclcpp::CallbackGroup::SharedPtr service_callback_group_;

private:
  void handle_send_command(
    const std::shared_ptr<rosbag_recorder::srv::SendCommand::Request> req,
    std::shared_ptr<rosbag_recorder::srv::SendCommand::Response> res);

  void handle_prepare(const std::vector<std::string> & topics);
  void handle_start(const std::string & uri);
  void handle_stop();
  void handle_stop_and_delete();
  void handle_finish();

  void handle_serialized_message(
    const std::string & topic,
    const std::shared_ptr<rclcpp::SerializedMessage> & serialized_msg,
    const rclcpp::MessageInfo & message_info);

  std::vector<std::string> get_missing_topics(
    const std::map<std::string, std::vector<std::string>> & names_and_types);
  void create_topics_in_bag(
    const std::map<std::string, std::vector<std::string>> & names_and_types);
  void delete_bag_directory(const std::string & bag_uri);
  void create_subscriptions();
  rclcpp::QoS get_qos_for_topic(const std::string & topic);
  rclcpp::CallbackGroup::SharedPtr get_callback_group_for_topic(const std::string & topic);
  void log_statistics();

  rclcpp::Service<rosbag_recorder::srv::SendCommand>::SharedPtr send_command_srv_;

  std::vector<rclcpp::GenericSubscription::SharedPtr> subscriptions_;
  std::unique_ptr<rosbag2_cpp::Writer> writer_;
  std::unordered_map<std::string, std::string> type_for_topic_;

  // Track which topics are camera topics for callback group assignment
  std::unordered_set<std::string> camera_topics_;
  std::unordered_set<std::string> joint_topics_;

  std::atomic<bool> is_recording_ {false};
  std::string current_bag_uri_;
  std::vector<std::string> topics_to_record_ {};
  std::mutex mutex_;

  // Statistics for monitoring
  std::atomic<uint64_t> messages_received_{0};
  std::atomic<uint64_t> messages_written_{0};

  // Storage configuration
  static constexpr size_t CACHE_SIZE_BYTES = 1024 * 1024 * 1024;  // 1GB
  static constexpr const char * STORAGE_ID = "mcap";
};

#endif  // ROSBAG_RECORDER__SERVICE_BAG_RECORDER_HPP_
