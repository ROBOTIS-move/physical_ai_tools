// generated from rosidl_generator_c/resource/idl__description.c.em
// with input from physical_ai_interfaces:msg/TaskInfo.idl
// generated code does not contain a copyright notice

#include "physical_ai_interfaces/msg/detail/task_info__functions.h"

ROSIDL_GENERATOR_C_PUBLIC_physical_ai_interfaces
const rosidl_type_hash_t *
physical_ai_interfaces__msg__TaskInfo__get_type_hash(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_type_hash_t hash = {1, {
      0xb8, 0x04, 0x98, 0x36, 0xeb, 0x8a, 0x6b, 0xde,
      0x3c, 0x92, 0x7b, 0x3d, 0x5b, 0xc6, 0x4f, 0xc7,
      0xa7, 0xfb, 0x87, 0x1c, 0xa6, 0x11, 0x01, 0xc3,
      0x50, 0x0d, 0x4c, 0x25, 0x23, 0x9e, 0x9b, 0x70,
    }};
  return &hash;
}

#include <assert.h>
#include <string.h>

// Include directives for referenced types

// Hashes for external referenced types
#ifndef NDEBUG
#endif

static char physical_ai_interfaces__msg__TaskInfo__TYPE_NAME[] = "physical_ai_interfaces/msg/TaskInfo";

// Define type names, field names, and default values
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__task_name[] = "task_name";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__task_type[] = "task_type";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__user_id[] = "user_id";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__task_instruction[] = "task_instruction";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__policy_path[] = "policy_path";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__fps[] = "fps";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__tags[] = "tags";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__warmup_time_s[] = "warmup_time_s";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__episode_time_s[] = "episode_time_s";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__reset_time_s[] = "reset_time_s";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__num_episodes[] = "num_episodes";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__push_to_hub[] = "push_to_hub";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__private_mode[] = "private_mode";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__use_optimized_save_mode[] = "use_optimized_save_mode";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__record_inference_mode[] = "record_inference_mode";
static char physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__record_rosbag2[] = "record_rosbag2";

static rosidl_runtime_c__type_description__Field physical_ai_interfaces__msg__TaskInfo__FIELDS[] = {
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__task_name, 9, 9},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_STRING,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__task_type, 9, 9},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_STRING,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__user_id, 7, 7},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_STRING,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__task_instruction, 16, 16},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_STRING_UNBOUNDED_SEQUENCE,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__policy_path, 11, 11},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_STRING,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__fps, 3, 3},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_UINT8,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__tags, 4, 4},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_STRING_UNBOUNDED_SEQUENCE,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__warmup_time_s, 13, 13},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_UINT16,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__episode_time_s, 14, 14},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_UINT16,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__reset_time_s, 12, 12},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_UINT16,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__num_episodes, 12, 12},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_UINT16,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__push_to_hub, 11, 11},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_BOOLEAN,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__private_mode, 12, 12},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_BOOLEAN,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__use_optimized_save_mode, 23, 23},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_BOOLEAN,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__record_inference_mode, 21, 21},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_BOOLEAN,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__FIELD_NAME__record_rosbag2, 14, 14},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_BOOLEAN,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
};

const rosidl_runtime_c__type_description__TypeDescription *
physical_ai_interfaces__msg__TaskInfo__get_type_description(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static bool constructed = false;
  static const rosidl_runtime_c__type_description__TypeDescription description = {
    {
      {physical_ai_interfaces__msg__TaskInfo__TYPE_NAME, 35, 35},
      {physical_ai_interfaces__msg__TaskInfo__FIELDS, 16, 16},
    },
    {NULL, 0, 0},
  };
  if (!constructed) {
    constructed = true;
  }
  return &description;
}

static char toplevel_type_raw_source[] =
  "string task_name\n"
  "string task_type\n"
  "string user_id\n"
  "string[] task_instruction\n"
  "string policy_path\n"
  "uint8 fps\n"
  "string[] tags\n"
  "uint16 warmup_time_s    # [s]\n"
  "uint16 episode_time_s   # [s]\n"
  "uint16 reset_time_s     # [s]\n"
  "uint16 num_episodes\n"
  "bool push_to_hub\n"
  "bool private_mode\n"
  "bool use_optimized_save_mode\n"
  "bool record_inference_mode\n"
  "bool record_rosbag2";

static char msg_encoding[] = "msg";

// Define all individual source functions

const rosidl_runtime_c__type_description__TypeSource *
physical_ai_interfaces__msg__TaskInfo__get_individual_type_description_source(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static const rosidl_runtime_c__type_description__TypeSource source = {
    {physical_ai_interfaces__msg__TaskInfo__TYPE_NAME, 35, 35},
    {msg_encoding, 3, 3},
    {toplevel_type_raw_source, 339, 339},
  };
  return &source;
}

const rosidl_runtime_c__type_description__TypeSource__Sequence *
physical_ai_interfaces__msg__TaskInfo__get_type_description_sources(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_runtime_c__type_description__TypeSource sources[1];
  static const rosidl_runtime_c__type_description__TypeSource__Sequence source_sequence = {sources, 1, 1};
  static bool constructed = false;
  if (!constructed) {
    sources[0] = *physical_ai_interfaces__msg__TaskInfo__get_individual_type_description_source(NULL),
    constructed = true;
  }
  return &source_sequence;
}
