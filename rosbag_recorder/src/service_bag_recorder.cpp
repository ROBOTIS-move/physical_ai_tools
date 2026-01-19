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
#include "rosbag2_cpp/writer.hpp"
#include "rosbag2_storage/topic_metadata.hpp"

#include "rosbag_recorder/service_bag_recorder.hpp"


ServiceBagRecorder::ServiceBagRecorder()
: rclcpp::Node("service_bag_recorder")
{
  RCLCPP_INFO(this->get_logger(), "Starting rosbag recorder node");

  send_command_srv_ = this->create_service<rosbag_recorder::srv::SendCommand>(
    "rosbag_recorder/send_command",
    std::bind(
      &ServiceBagRecorder::handle_send_command, this, std::placeholders::_1,
      std::placeholders::_2));
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

  if (is_recording_) {
    throw std::runtime_error("Already recording");
  }

  if (topics.empty()) {
    throw std::runtime_error("Topics are required");
  }

  try {
    topics_to_record_ = topics;

    auto names_and_types = this->get_topic_names_and_types();

    for (const auto & topic : topics_to_record_) {
      auto it = names_and_types.find(topic);
      const std::string & type = it->second.front();

      type_for_topic_[topic] = type;
    }

    // Create subscriptions for non-latched topics only
    // Latched topics will be subscribed in START to ensure they are recorded
    create_subscriptions();

    RCLCPP_INFO(
      this->get_logger(),
      "Recording prepared: topics=%zu",
      topics_to_record_.size());
  } catch (const std::exception & e) {
    writer_.reset();
    throw std::runtime_error(std::string("Failed to prepare recording: ") + e.what());
  }
}

void ServiceBagRecorder::handle_start(const std::string & uri)
{
  RCLCPP_INFO(this->get_logger(), "Start Rosbag recording");

  if (is_recording_) {
    throw std::runtime_error("Already recording");
  }

  if (uri.empty()) {
    throw std::runtime_error("Bag URI is required");
  }

  try {
    current_bag_uri_ = uri;

    // Check if a bag already exists at the specified path and delete it
    delete_bag_directory(current_bag_uri_);

    writer_ = std::make_unique<rosbag2_cpp::Writer>();
    writer_->open(current_bag_uri_);

    auto names_and_types = this->get_topic_names_and_types();
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

  is_recording_ = true;
  
  // Create subscriptions for latched topics after writer is ready
  // TRANSIENT_LOCAL topics will immediately deliver their messages
  create_latched_subscriptions();

  RCLCPP_INFO(
    this->get_logger(), "Recording started: uri=%s topics=%zu",
    current_bag_uri_.c_str(), topics_to_record_.size());
}

void ServiceBagRecorder::handle_stop()
{
  RCLCPP_INFO(this->get_logger(), "Stop Rosbag recording");

  if (!is_recording_) {
    throw std::runtime_error("Not recording");
  }

  try {
    writer_.reset();
    type_for_topic_.clear();
    current_bag_uri_.clear();
    is_recording_ = false;
    RCLCPP_INFO(this->get_logger(), "Recording stopped");
  } catch (const std::exception & e) {
    throw std::runtime_error(std::string("Failed to stop recording: ") + e.what());
  }
}

void ServiceBagRecorder::handle_stop_and_delete()
{
  RCLCPP_INFO(this->get_logger(), "Stop and delete Rosbag recording");

  if (!is_recording_) {
    throw std::runtime_error("Not recording");
  }

  try {
    is_recording_ = false;

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

  subscriptions_.clear();

  if (is_recording_) {
    handle_stop();
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
  RCLCPP_INFO(this->get_logger(), "Creating subscriptions for non-latched topics");

  // Create subscriptions for non-latched topics only
  for (const auto & [topic, type] : type_for_topic_) {
    // Skip latched topics - they will be subscribed in START
    if (is_latched_topic(topic)) {
      RCLCPP_INFO(this->get_logger(), "Skipping latched topic: %s", topic.c_str());
      continue;
    }

    auto options = rclcpp::SubscriptionOptions();
    auto qos = get_qos_for_topic(topic);
    auto sub = this->create_generic_subscription(
      topic,
      type,
      qos,
      [this, topic](std::shared_ptr<rclcpp::SerializedMessage> serialized_msg) {
        this->handle_serialized_message(topic, serialized_msg);
      },
      options);
    subscriptions_.push_back(sub);
    RCLCPP_INFO(this->get_logger(), "Subscribed to non-latched topic: %s", topic.c_str());
  }
}

void ServiceBagRecorder::create_latched_subscriptions()
{
  RCLCPP_INFO(this->get_logger(), "Creating subscriptions for latched topics");

  // Create subscriptions for latched topics only
  for (const auto & [topic, type] : type_for_topic_) {
    if (!is_latched_topic(topic)) {
      continue;
    }

    auto options = rclcpp::SubscriptionOptions();
    auto qos = get_qos_for_topic(topic);
    auto sub = this->create_generic_subscription(
      topic,
      type,
      qos,
      [this, topic](std::shared_ptr<rclcpp::SerializedMessage> serialized_msg) {
        this->handle_serialized_message(topic, serialized_msg);
      },
      options);
    subscriptions_.push_back(sub);
    RCLCPP_INFO(this->get_logger(), "Subscribed to latched topic: %s", topic.c_str());
  }
}

rclcpp::QoS ServiceBagRecorder::get_qos_for_topic(
  const std::string & topic)
{
  // Get publisher info to determine QoS settings
  auto publishers_info = this->get_publishers_info_by_topic(topic);

  if (!publishers_info.empty()) {
    // Check if any publisher uses TRANSIENT_LOCAL durability
    for (const auto & pub_info : publishers_info) {
      if (pub_info.qos_profile().durability() == rclcpp::DurabilityPolicy::TransientLocal) {
        RCLCPP_INFO(
          this->get_logger(),
          "Topic '%s' uses TRANSIENT_LOCAL durability, using matching QoS",
          topic.c_str());
        return rclcpp::QoS(rclcpp::KeepLast(10))
               .reliable()
               .transient_local();
      }
    }
  }

  // Use default QoS for other topics
  return rclcpp::QoS(100);
}

bool ServiceBagRecorder::is_latched_topic(const std::string & topic)
{
  auto publishers_info = this->get_publishers_info_by_topic(topic);

  for (const auto & pub_info : publishers_info) {
    if (pub_info.qos_profile().durability() == rclcpp::DurabilityPolicy::TransientLocal) {
      return true;
    }
  }
  return false;
}

void ServiceBagRecorder::flush_latched_messages()
{
  if (latched_message_buffer_.empty()) {
    return;
  }

  RCLCPP_INFO(
    this->get_logger(),
    "Flushing %zu buffered latched messages",
    latched_message_buffer_.size());

  for (const auto & [topic, buffered] : latched_message_buffer_) {
    if (writer_) {
      const auto it = type_for_topic_.find(topic);
      if (it != type_for_topic_.end()) {
        writer_->write(buffered.msg, topic, it->second, buffered.timestamp);
        RCLCPP_INFO(this->get_logger(), "Flushed latched message from: %s", topic.c_str());
      }
    }
  }

  latched_message_buffer_.clear();
}

rclcpp::Time ServiceBagRecorder::extract_timestamp(
  const std::shared_ptr<rclcpp::SerializedMessage> & serialized_msg,
  const std::string & message_type)
{
  const auto & rcl_msg = serialized_msg->get_rcl_serialized_message();
  const uint8_t * buffer = rcl_msg.buffer;
  size_t buffer_length = rcl_msg.buffer_length;

  // Need at least 12 bytes for CDR header (4) + sec (4) + nanosec (4)
  if (buffer_length < 12) {
    return this->now();
  }

  try {
    auto now_time = this->now();
    auto now_sec = now_time.seconds();
    
    // Messages with direct header at the start (most sensor_msgs, nav_msgs, trajectory_msgs)
    if (message_type == "sensor_msgs/msg/CompressedImage" ||
        message_type == "sensor_msgs/msg/Image" ||
        message_type == "sensor_msgs/msg/CameraInfo" ||
        message_type == "sensor_msgs/msg/JointState" ||
        message_type == "trajectory_msgs/msg/JointTrajectory" ||
        message_type == "nav_msgs/msg/Odometry")
    {
      // CDR format: 4 bytes encapsulation + header.stamp (sec + nanosec)
      // Assuming little-endian
      int32_t sec = *reinterpret_cast<const int32_t *>(buffer + 4);
      uint32_t nanosec = *reinterpret_cast<const uint32_t *>(buffer + 8);

      // Strict sanity check: timestamp should be very recent (within 1 year past to 1 day future)
      // Unix epoch: 1970-01-01, so reasonable timestamp > 1600000000 (2020-09-13)
      if (sec > 1600000000 && 
          sec >= (now_sec - 31536000) &&  // Within 1 year in past
          sec <= (now_sec + 86400) &&      // Within 24 hours in future
          nanosec < 1000000000)            // Valid nanoseconds
      {
        return rclcpp::Time(sec, nanosec);
      } else {
        RCLCPP_WARN_THROTTLE(
          this->get_logger(), *this->get_clock(), 10000,
          "Invalid timestamp in %s: sec=%d, nanosec=%u (now=%ld). Using reception time.",
          message_type.c_str(), sec, nanosec, static_cast<long>(now_sec));
      }
    }
    // TFMessage: has transforms[] array, need to extract first transform's header
    else if (message_type == "tf2_msgs/msg/TFMessage")
    {
      // CDR: 4 bytes encapsulation + 4 bytes array length + first element
      if (buffer_length < 16) {
        return this->now();
      }
      uint32_t array_length = *reinterpret_cast<const uint32_t *>(buffer + 4);
      if (array_length > 0) {
        // First transform's header starts at offset 8
        int32_t sec = *reinterpret_cast<const int32_t *>(buffer + 8);
        uint32_t nanosec = *reinterpret_cast<const uint32_t *>(buffer + 12);

        if (sec > 1600000000 && 
            sec >= (now_sec - 31536000) &&
            sec <= (now_sec + 86400) &&
            nanosec < 1000000000)
        {
          return rclcpp::Time(sec, nanosec);
        } else {
          RCLCPP_WARN_THROTTLE(
            this->get_logger(), *this->get_clock(), 10000,
            "Invalid timestamp in %s: sec=%d, nanosec=%u (now=%ld). Using reception time.",
            message_type.c_str(), sec, nanosec, static_cast<long>(now_sec));
        }
      }
    }
    // Messages without header: use reception time
    // geometry_msgs/msg/Twist, std_msgs/msg/String
  } catch (const std::exception & e) {
    RCLCPP_WARN_THROTTLE(
      this->get_logger(), *this->get_clock(), 5000,
      "Failed to extract timestamp from %s: %s. Using reception time.",
      message_type.c_str(), e.what());
  }

  // Fallback: use reception time
  return this->now();
}

void ServiceBagRecorder::handle_serialized_message(
  const std::string & topic,
  const std::shared_ptr<rclcpp::SerializedMessage> & serialized_msg)
{
  std::scoped_lock<std::mutex> lock(mutex_);

  // Only record if writer exists
  if (!writer_) {
    return;
  }

  const auto it = type_for_topic_.find(topic);
  if (it == type_for_topic_.end()) {
    return;
  }
  const std::string & type = it->second;
  
  // Extract timestamp from message header if available, based on message type
  rclcpp::Time timestamp = extract_timestamp(serialized_msg, type);
  
  writer_->write(serialized_msg, topic, type, timestamp);
}

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<ServiceBagRecorder>());
  rclcpp::shutdown();
  return 0;
}
