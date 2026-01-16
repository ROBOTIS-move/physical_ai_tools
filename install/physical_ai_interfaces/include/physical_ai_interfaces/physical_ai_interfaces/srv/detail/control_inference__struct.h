// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from physical_ai_interfaces:srv/ControlInference.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "physical_ai_interfaces/srv/control_inference.h"


#ifndef PHYSICAL_AI_INTERFACES__SRV__DETAIL__CONTROL_INFERENCE__STRUCT_H_
#define PHYSICAL_AI_INTERFACES__SRV__DETAIL__CONTROL_INFERENCE__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

/// Struct defined in srv/ControlInference in the package physical_ai_interfaces.
typedef struct physical_ai_interfaces__srv__ControlInference_Request
{
  bool enable;
  bool pause_inference;
} physical_ai_interfaces__srv__ControlInference_Request;

// Struct for a sequence of physical_ai_interfaces__srv__ControlInference_Request.
typedef struct physical_ai_interfaces__srv__ControlInference_Request__Sequence
{
  physical_ai_interfaces__srv__ControlInference_Request * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} physical_ai_interfaces__srv__ControlInference_Request__Sequence;

// Constants defined in the message

// Include directives for member types
// Member 'message'
#include "rosidl_runtime_c/string.h"

/// Struct defined in srv/ControlInference in the package physical_ai_interfaces.
typedef struct physical_ai_interfaces__srv__ControlInference_Response
{
  bool success;
  rosidl_runtime_c__String message;
} physical_ai_interfaces__srv__ControlInference_Response;

// Struct for a sequence of physical_ai_interfaces__srv__ControlInference_Response.
typedef struct physical_ai_interfaces__srv__ControlInference_Response__Sequence
{
  physical_ai_interfaces__srv__ControlInference_Response * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} physical_ai_interfaces__srv__ControlInference_Response__Sequence;

// Constants defined in the message

// Include directives for member types
// Member 'info'
#include "service_msgs/msg/detail/service_event_info__struct.h"

// constants for array fields with an upper bound
// request
enum
{
  physical_ai_interfaces__srv__ControlInference_Event__request__MAX_SIZE = 1
};
// response
enum
{
  physical_ai_interfaces__srv__ControlInference_Event__response__MAX_SIZE = 1
};

/// Struct defined in srv/ControlInference in the package physical_ai_interfaces.
typedef struct physical_ai_interfaces__srv__ControlInference_Event
{
  service_msgs__msg__ServiceEventInfo info;
  physical_ai_interfaces__srv__ControlInference_Request__Sequence request;
  physical_ai_interfaces__srv__ControlInference_Response__Sequence response;
} physical_ai_interfaces__srv__ControlInference_Event;

// Struct for a sequence of physical_ai_interfaces__srv__ControlInference_Event.
typedef struct physical_ai_interfaces__srv__ControlInference_Event__Sequence
{
  physical_ai_interfaces__srv__ControlInference_Event * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} physical_ai_interfaces__srv__ControlInference_Event__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // PHYSICAL_AI_INTERFACES__SRV__DETAIL__CONTROL_INFERENCE__STRUCT_H_
