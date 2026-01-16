// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from physical_ai_interfaces:srv/ControlInference.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "physical_ai_interfaces/srv/control_inference.hpp"


#ifndef PHYSICAL_AI_INTERFACES__SRV__DETAIL__CONTROL_INFERENCE__BUILDER_HPP_
#define PHYSICAL_AI_INTERFACES__SRV__DETAIL__CONTROL_INFERENCE__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "physical_ai_interfaces/srv/detail/control_inference__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace physical_ai_interfaces
{

namespace srv
{

namespace builder
{

class Init_ControlInference_Request_pause_inference
{
public:
  explicit Init_ControlInference_Request_pause_inference(::physical_ai_interfaces::srv::ControlInference_Request & msg)
  : msg_(msg)
  {}
  ::physical_ai_interfaces::srv::ControlInference_Request pause_inference(::physical_ai_interfaces::srv::ControlInference_Request::_pause_inference_type arg)
  {
    msg_.pause_inference = std::move(arg);
    return std::move(msg_);
  }

private:
  ::physical_ai_interfaces::srv::ControlInference_Request msg_;
};

class Init_ControlInference_Request_enable
{
public:
  Init_ControlInference_Request_enable()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ControlInference_Request_pause_inference enable(::physical_ai_interfaces::srv::ControlInference_Request::_enable_type arg)
  {
    msg_.enable = std::move(arg);
    return Init_ControlInference_Request_pause_inference(msg_);
  }

private:
  ::physical_ai_interfaces::srv::ControlInference_Request msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::physical_ai_interfaces::srv::ControlInference_Request>()
{
  return physical_ai_interfaces::srv::builder::Init_ControlInference_Request_enable();
}

}  // namespace physical_ai_interfaces


namespace physical_ai_interfaces
{

namespace srv
{

namespace builder
{

class Init_ControlInference_Response_message
{
public:
  explicit Init_ControlInference_Response_message(::physical_ai_interfaces::srv::ControlInference_Response & msg)
  : msg_(msg)
  {}
  ::physical_ai_interfaces::srv::ControlInference_Response message(::physical_ai_interfaces::srv::ControlInference_Response::_message_type arg)
  {
    msg_.message = std::move(arg);
    return std::move(msg_);
  }

private:
  ::physical_ai_interfaces::srv::ControlInference_Response msg_;
};

class Init_ControlInference_Response_success
{
public:
  Init_ControlInference_Response_success()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ControlInference_Response_message success(::physical_ai_interfaces::srv::ControlInference_Response::_success_type arg)
  {
    msg_.success = std::move(arg);
    return Init_ControlInference_Response_message(msg_);
  }

private:
  ::physical_ai_interfaces::srv::ControlInference_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::physical_ai_interfaces::srv::ControlInference_Response>()
{
  return physical_ai_interfaces::srv::builder::Init_ControlInference_Response_success();
}

}  // namespace physical_ai_interfaces


namespace physical_ai_interfaces
{

namespace srv
{

namespace builder
{

class Init_ControlInference_Event_response
{
public:
  explicit Init_ControlInference_Event_response(::physical_ai_interfaces::srv::ControlInference_Event & msg)
  : msg_(msg)
  {}
  ::physical_ai_interfaces::srv::ControlInference_Event response(::physical_ai_interfaces::srv::ControlInference_Event::_response_type arg)
  {
    msg_.response = std::move(arg);
    return std::move(msg_);
  }

private:
  ::physical_ai_interfaces::srv::ControlInference_Event msg_;
};

class Init_ControlInference_Event_request
{
public:
  explicit Init_ControlInference_Event_request(::physical_ai_interfaces::srv::ControlInference_Event & msg)
  : msg_(msg)
  {}
  Init_ControlInference_Event_response request(::physical_ai_interfaces::srv::ControlInference_Event::_request_type arg)
  {
    msg_.request = std::move(arg);
    return Init_ControlInference_Event_response(msg_);
  }

private:
  ::physical_ai_interfaces::srv::ControlInference_Event msg_;
};

class Init_ControlInference_Event_info
{
public:
  Init_ControlInference_Event_info()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ControlInference_Event_request info(::physical_ai_interfaces::srv::ControlInference_Event::_info_type arg)
  {
    msg_.info = std::move(arg);
    return Init_ControlInference_Event_request(msg_);
  }

private:
  ::physical_ai_interfaces::srv::ControlInference_Event msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::physical_ai_interfaces::srv::ControlInference_Event>()
{
  return physical_ai_interfaces::srv::builder::Init_ControlInference_Event_info();
}

}  // namespace physical_ai_interfaces

#endif  // PHYSICAL_AI_INTERFACES__SRV__DETAIL__CONTROL_INFERENCE__BUILDER_HPP_
