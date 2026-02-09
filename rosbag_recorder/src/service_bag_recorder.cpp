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


#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
#include <sstream>
#include <filesystem>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp/generic_subscription.hpp"
#include "rclcpp/executors/multi_threaded_executor.hpp"
#include "rosbag2_cpp/writer.hpp"
#include "rosbag2_storage/storage_options.hpp"

#include "rosbag_recorder/service_bag_recorder.hpp"


ServiceBagRecorder::ServiceBagRecorder()
: rclcpp::Node("service_bag_recorder")
{
  RCLCPP_INFO(this->get_logger(), "Starting rosbag recorder node");

  // Create callback groups for parallel processing
  camera_callback_group_ = this->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);
  joint_callback_group_ = this->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);
  other_callback_group_ = this->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);
  service_callback_group_ = this->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive);

  // Create service with dedicated callback group
  send_command_srv_ = this->create_service<rosbag_recorder::srv::SendCommand>(
    "rosbag_recorder/send_command",
    std::bind(
      &ServiceBagRecorder::handle_send_command, this, std::placeholders::_1,
      std::placeholders::_2),
    rmw_qos_profile_services_default,
    service_callback_group_);

  RCLCPP_INFO(this->get_logger(), "Rosbag recorder initialized with MultiThreadedExecutor support");
}

void ServiceBagRecorder::handle_send_command(
  const std::shared_ptr<rosbag_recorder::srv::SendCommand::Request> req,
  std::shared_ptr<rosbag_recorder::srv::SendCommand::Response> res)
{
  std::scoped_lock<std::mutex> lock(mutex_);

  RCLCPP_INFO(this->get_logger(), "Received command: %d", req->command);

  try {
    switch (req->command) {
      case rosbag_recorder::srv::SendCommand::Request::PREPARE:
        handle_prepare(req->topics);
        res->success = true;
        res->message = "Recording prepared";
        break;
      case rosbag_recorder::srv::SendCommand::Request::START:
        handle_start(req->uri);
        res->success = true;
        res->message = "Recording started";
        break;
      case rosbag_recorder::srv::SendCommand::Request::STOP:
        handle_stop();
        res->success = true;
        res->message = "Recording stopped";
        break;
      case rosbag_recorder::srv::SendCommand::Request::STOP_AND_DELETE:
        handle_stop_and_delete();
        res->success = true;
        res->message = "Recording stopped and bag deleted";
        break;
      case rosbag_recorder::srv::SendCommand::Request::FINISH:
        handle_finish();
        res->success = true;
        res->message = "Recording finished";
        break;
      default:
        res->success = false;
        res->message = "Invalid command";
        RCLCPP_ERROR(this->get_logger(), "Invalid command: %d", req->command);
        break;
    }
  } catch (const std::exception & e) {
    res->success = false;
    res->message = e.what();

    RCLCPP_ERROR(this->get_logger(), "Failed to execute command: %s", e.what());
  }
}

void ServiceBagRecorder::handle_prepare(const std::vector<std::string> & topics)
{
  RCLCPP_INFO(this->get_logger(), "Prepare Rosbag recording");

  if (is_recording_.load(std::memory_order_acquire)) {
    throw std::runtime_error("Already recording");
  }

  if (topics.empty()) {
    throw std::runtime_error("Topics are required");
  }

  try {
    topics_to_record_ = topics;

    auto names_and_types = this->get_topic_names_and_types();

    // Categorize topics for callback group assignment
    camera_topics_.clear();
    joint_topics_.clear();

    for (const auto & topic : topics_to_record_) {
      auto it = names_and_types.find(topic);
      if (it != names_and_types.end() && !it->second.empty()) {
        const std::string & type = it->second.front();
        type_for_topic_[topic] = type;

        // Categorize by topic name
        if (topic.find("image") != std::string::npos ||
          topic.find("camera") != std::string::npos)
        {
          camera_topics_.insert(topic);
        } else if (topic.find("joint") != std::string::npos ||
          topic.find("arm") != std::string::npos ||
          topic.find("head") != std::string::npos ||
          topic.find("lift") != std::string::npos)
        {
          joint_topics_.insert(topic);
        }
      }
    }

    // Create subscriptions early to start receiving data
    create_subscriptions();

    // Reset statistics
    messages_received_ = 0;
    messages_written_ = 0;

    RCLCPP_INFO(
      this->get_logger(),
      "Recording prepared: total=%zu, camera=%zu, joint=%zu",
      topics_to_record_.size(),
      camera_topics_.size(),
      joint_topics_.size());
  } catch (const std::exception & e) {
    writer_.reset();
    throw std::runtime_error(std::string("Failed to prepare recording: ") + e.what());
  }
}

void ServiceBagRecorder::handle_start(const std::string & uri)
{
  RCLCPP_INFO(
    this->get_logger(),
    "Start Rosbag recording: uri=%s topics_to_record=%zu subscriptions=%zu",
    uri.c_str(), topics_to_record_.size(), generic_subscriptions_.size());

  if (is_recording_.load(std::memory_order_acquire)) {
    throw std::runtime_error("Already recording");
  }

  if (uri.empty()) {
    throw std::runtime_error("Bag URI is required");
  }

  if (topics_to_record_.empty()) {
    throw std::runtime_error("No topics configured - PREPARE must be called first");
  }

  try {
    current_bag_uri_ = uri;

    // Check if a bag already exists at the specified path and delete it
    delete_bag_directory(current_bag_uri_);

    // Configure storage options for MCAP with optimized settings
    rosbag2_storage::StorageOptions storage_options;
    storage_options.uri = current_bag_uri_;
    storage_options.storage_id = STORAGE_ID;  // "mcap"
    storage_options.max_cache_size = CACHE_SIZE_BYTES;  // 500MB
    storage_options.max_bagfile_size = 0;  // No splitting to prevent message loss

    writer_ = std::make_unique<rosbag2_cpp::Writer>();
    writer_->open(storage_options);

    auto names_and_types = this->get_topic_names_and_types();
    RCLCPP_INFO(this->get_logger(), "Found %zu active topics in system", names_and_types.size());

    auto missing_topics = get_missing_topics(names_and_types);

    if (!missing_topics.empty()) {
      writer_.reset();
      type_for_topic_.clear();

      // Delete the bag folder since we can't record the requested topics
      RCLCPP_INFO(
        this->get_logger(),
        "Deleting bag directory due to missing topic types: %s",
        current_bag_uri_.c_str());
      delete_bag_directory(current_bag_uri_);
      current_bag_uri_.clear();

      std::ostringstream oss;
      oss << "Types not found for topics:";
      for (const auto & t : missing_topics) {
        oss << " " << t;
      }

      RCLCPP_INFO(this->get_logger(), "Failed to start recording: %s", oss.str().c_str());

      throw std::runtime_error(oss.str());
    }

    create_topics_in_bag(names_and_types);
  } catch (const std::exception & e) {
    throw std::runtime_error(std::string("Failed to start recording: ") + e.what());
  }

  // Set recording flag - messages will now be written to bag
  is_recording_.store(true, std::memory_order_release);

  RCLCPP_INFO(
    this->get_logger(), "Recording started: uri=%s topics=%zu storage=%s cache=%zuMB",
    current_bag_uri_.c_str(), topics_to_record_.size(), STORAGE_ID,
    CACHE_SIZE_BYTES / (1024 * 1024));
}

void ServiceBagRecorder::handle_stop()
{
  RCLCPP_INFO(this->get_logger(), "Stop Rosbag recording");

  // Handle gracefully when not recording (e.g., if START failed)
  if (!is_recording_.load(std::memory_order_acquire)) {
    RCLCPP_WARN(this->get_logger(), "Stop called but not recording - nothing to stop");
    return;
  }

  try {
    // Set flag first to stop callbacks from writing
    is_recording_.store(false, std::memory_order_release);

    // Log statistics before closing
    log_statistics();

    writer_.reset();
    type_for_topic_.clear();
    current_bag_uri_.clear();

    RCLCPP_INFO(this->get_logger(), "Recording stopped");
  } catch (const std::exception & e) {
    throw std::runtime_error(std::string("Failed to stop recording: ") + e.what());
  }
}

void ServiceBagRecorder::handle_stop_and_delete()
{
  RCLCPP_INFO(this->get_logger(), "Stop and delete Rosbag recording");

  // Handle gracefully when not recording (e.g., Cancel pressed before recording started)
  if (!is_recording_.load(std::memory_order_acquire)) {
    RCLCPP_INFO(this->get_logger(), "Not recording, nothing to delete");
    return;
  }

  try {
    // Set flag first to stop callbacks from writing
    is_recording_.store(false, std::memory_order_release);

    // Log statistics
    log_statistics();

    writer_.reset();
    type_for_topic_.clear();

    delete_bag_directory(current_bag_uri_);

    current_bag_uri_.clear();

    RCLCPP_INFO(this->get_logger(), "Recording stopped and bag deleted");
  } catch (const std::exception & e) {
    throw std::runtime_error(std::string("Failed to stop recording and delete bag: ") + e.what());
  }
}

void ServiceBagRecorder::handle_finish()
{
  RCLCPP_INFO(this->get_logger(), "Finish Rosbag recording");

  // Log final statistics
  log_statistics();

  // Note: Don't clear subscriptions here - keep them for next episode recording
  // Subscriptions will only be cleared when:
  // 1. A new PREPARE command is received (robot type changed)
  // 2. The node is destroyed (program shutdown)

  if (is_recording_.load(std::memory_order_acquire)) {
    is_recording_.store(false, std::memory_order_release);
    writer_.reset();
    current_bag_uri_.clear();
  }
}

std::vector<std::string> ServiceBagRecorder::get_missing_topics(
  const std::map<std::string, std::vector<std::string>> & names_and_types)
{
// Resolve types for requested topics
  std::vector<std::string> missing_topics;

  for (const auto & topic : topics_to_record_) {
    auto it = names_and_types.find(topic);

    if (it == names_and_types.end() || it->second.empty()) {
      missing_topics.push_back(topic);
      continue;
    }
  }
  return missing_topics;
}

void ServiceBagRecorder::create_topics_in_bag(
  const std::map<std::string, std::vector<std::string>> & names_and_types)
{
  if (!writer_) {
    RCLCPP_ERROR(this->get_logger(), "Writer not initialized");
    return;
  }

  if (topics_to_record_.empty()) {
    RCLCPP_ERROR(this->get_logger(), "No topics to record");
    return;
  }

  for (const auto & topic : topics_to_record_) {
    auto it = names_and_types.find(topic);
    const std::string & type = it->second.front();

    type_for_topic_[topic] = type;

    rosbag2_storage::TopicMetadata meta;
    meta.name = topic;
    meta.type = type;
    meta.serialization_format = rmw_get_serialization_format();

    writer_->create_topic(meta);
  }
}

void ServiceBagRecorder::delete_bag_directory(const std::string & bag_uri)
{
  if (bag_uri.empty()) {
    return;
  }

  std::filesystem::path bag_path(bag_uri);
  if (std::filesystem::exists(bag_path)) {
    std::filesystem::remove_all(bag_path);
    RCLCPP_INFO(
      this->get_logger(), "Deleted bag directory: %s",
      bag_uri.c_str());
  }
}

void ServiceBagRecorder::create_subscriptions()
{
  RCLCPP_INFO(this->get_logger(), "Creating subscriptions with callback groups");

  generic_subscriptions_.clear();

  // Create generic subscriptions for all topics
  for (const auto & [topic, type] : type_for_topic_) {
    auto options = rclcpp::SubscriptionOptions();
    options.callback_group = get_callback_group_for_topic(topic);

    auto qos = get_qos_for_topic(topic);

    auto sub = this->create_generic_subscription(
      topic,
      type,
      qos,
      [this, topic](
        std::shared_ptr<rclcpp::SerializedMessage> serialized_msg,
        const rclcpp::MessageInfo & message_info) {
        this->handle_serialized_message(topic, serialized_msg, message_info);
      },
      options);

    generic_subscriptions_.push_back(sub);

    std::string group_name = "other";
    if (camera_topics_.count(topic)) {
      group_name = "camera";
    } else if (joint_topics_.count(topic)) {
      group_name = "joint";
    }

    RCLCPP_INFO(
      this->get_logger(),
      "Subscribed to topic: %s (group: %s, depth: %zu)",
      topic.c_str(), group_name.c_str(), qos.depth());
  }
}

rclcpp::QoS ServiceBagRecorder::get_qos_for_topic(const std::string & topic)
{
  // Camera topics: large buffer for high-bandwidth data
  if (camera_topics_.count(topic)) {
    return rclcpp::QoS(rclcpp::KeepLast(2000))
           .reliable()
           .durability_volatile();
  }

  // Joint topics: medium buffer
  if (joint_topics_.count(topic)) {
    return rclcpp::QoS(rclcpp::KeepLast(1000))
           .reliable()
           .durability_volatile();
  }

  // Other topics (tf, etc.): standard buffer
  return rclcpp::QoS(rclcpp::KeepLast(500))
         .reliable()
         .durability_volatile();
}

rclcpp::CallbackGroup::SharedPtr ServiceBagRecorder::get_callback_group_for_topic(
  const std::string & topic)
{
  if (camera_topics_.count(topic)) {
    return camera_callback_group_;
  }
  if (joint_topics_.count(topic)) {
    return joint_callback_group_;
  }
  return other_callback_group_;
}

void ServiceBagRecorder::log_statistics()
{
  uint64_t received = messages_received_.load();
  uint64_t written = messages_written_.load();
  uint64_t dropped = (received > written) ? (received - written) : 0;

  RCLCPP_INFO(
    this->get_logger(),
    "Recording statistics - Received: %lu, Written: %lu, Dropped: %lu",
    received, written, dropped);

  if (dropped > 0) {
    RCLCPP_WARN(
      this->get_logger(),
      "WARNING: %lu messages were dropped during recording!", dropped);
  }
}

void ServiceBagRecorder::handle_serialized_message(
  const std::string & topic,
  const std::shared_ptr<rclcpp::SerializedMessage> & serialized_msg,
  const rclcpp::MessageInfo & message_info)
{
  // First check without lock - fast path for when not recording
  // is_recording_ is atomic, so this read is safe
  if (!is_recording_.load(std::memory_order_acquire)) {
    return;
  }

  messages_received_++;

  const auto it = type_for_topic_.find(topic);
  if (it == type_for_topic_.end()) {
    return;
  }
  const std::string & type = it->second;

  // Get timestamps from RMW
  const auto & rmw_info = message_info.get_rmw_message_info();

  // Use source_timestamp (when message was published) for rosbag timeline
  rclcpp::Time source_timestamp(rmw_info.source_timestamp, RCL_ROS_TIME);

  // Note: received_timestamp is also available via rmw_info.received_timestamp
  // MCAP format stores both: publishTime (source) and logTime (received)

  // Write to bag with lock - double-check writer_ inside lock to prevent race condition
  {
    std::scoped_lock<std::mutex> lock(mutex_);
    // Second check inside lock - writer_ may have been reset by handle_stop()
    if (!writer_) {
      return;
    }
    writer_->write(serialized_msg, topic, type, source_timestamp);
  }

  messages_written_++;
}

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  // Use MultiThreadedExecutor for parallel callback processing
  rclcpp::executors::MultiThreadedExecutor executor(
    rclcpp::ExecutorOptions(),
    4  // 4 threads: camera, joint, other, service
  );

  auto node = std::make_shared<ServiceBagRecorder>();
  executor.add_node(node);

  RCLCPP_INFO(node->get_logger(), "Running with MultiThreadedExecutor (4 threads)");

  executor.spin();
  rclcpp::shutdown();
  return 0;
}
