// generated from rosidl_generator_c/resource/idl__description.c.em
// with input from physical_ai_interfaces:srv/SendCommand.idl
// generated code does not contain a copyright notice

#include "physical_ai_interfaces/srv/detail/send_command__functions.h"

ROSIDL_GENERATOR_C_PUBLIC_physical_ai_interfaces
const rosidl_type_hash_t *
physical_ai_interfaces__srv__SendCommand__get_type_hash(
  const rosidl_service_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_type_hash_t hash = {1, {
      0xe0, 0xa5, 0xe8, 0x4a, 0xfb, 0x2c, 0xa3, 0x9b,
      0xec, 0xef, 0x8f, 0xf8, 0xd1, 0xf2, 0x05, 0x77,
      0x16, 0xed, 0x6d, 0xb5, 0x06, 0xf6, 0x98, 0x1c,
      0x2e, 0xd8, 0x5e, 0x64, 0x62, 0xe3, 0x68, 0x92,
    }};
  return &hash;
}

ROSIDL_GENERATOR_C_PUBLIC_physical_ai_interfaces
const rosidl_type_hash_t *
physical_ai_interfaces__srv__SendCommand_Request__get_type_hash(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_type_hash_t hash = {1, {
      0x1e, 0x4c, 0x1c, 0x9d, 0x09, 0x0d, 0xf5, 0xb8,
      0xe3, 0xaa, 0xac, 0x97, 0x41, 0x40, 0xb7, 0x7e,
      0x9f, 0x39, 0xfd, 0x1b, 0x88, 0x3b, 0x2a, 0x54,
      0x08, 0xeb, 0xc2, 0xf7, 0xbe, 0x6e, 0x27, 0xab,
    }};
  return &hash;
}

ROSIDL_GENERATOR_C_PUBLIC_physical_ai_interfaces
const rosidl_type_hash_t *
physical_ai_interfaces__srv__SendCommand_Response__get_type_hash(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_type_hash_t hash = {1, {
      0x9c, 0xdc, 0x52, 0xbd, 0x3d, 0xa0, 0xc8, 0xa5,
      0xe8, 0x04, 0x8f, 0xf2, 0x0d, 0x05, 0x16, 0xae,
      0x01, 0x59, 0x78, 0x0c, 0x9b, 0xbf, 0x61, 0x59,
      0xb2, 0x73, 0x83, 0xf3, 0x12, 0x43, 0x40, 0xbc,
    }};
  return &hash;
}

ROSIDL_GENERATOR_C_PUBLIC_physical_ai_interfaces
const rosidl_type_hash_t *
physical_ai_interfaces__srv__SendCommand_Event__get_type_hash(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_type_hash_t hash = {1, {
      0x3b, 0x01, 0x2e, 0x20, 0x24, 0x23, 0x78, 0x84,
      0x09, 0x61, 0x76, 0x8a, 0xc9, 0xb9, 0x42, 0x75,
      0x0b, 0x77, 0xd2, 0x29, 0x9e, 0x17, 0x83, 0xe5,
      0x32, 0x85, 0xc8, 0xaf, 0xc9, 0x64, 0x13, 0x17,
    }};
  return &hash;
}

#include <assert.h>
#include <string.h>

// Include directives for referenced types
#include "physical_ai_interfaces/msg/detail/task_info__functions.h"
#include "service_msgs/msg/detail/service_event_info__functions.h"
#include "builtin_interfaces/msg/detail/time__functions.h"

// Hashes for external referenced types
#ifndef NDEBUG
static const rosidl_type_hash_t builtin_interfaces__msg__Time__EXPECTED_HASH = {1, {
    0xb1, 0x06, 0x23, 0x5e, 0x25, 0xa4, 0xc5, 0xed,
    0x35, 0x09, 0x8a, 0xa0, 0xa6, 0x1a, 0x3e, 0xe9,
    0xc9, 0xb1, 0x8d, 0x19, 0x7f, 0x39, 0x8b, 0x0e,
    0x42, 0x06, 0xce, 0xa9, 0xac, 0xf9, 0xc1, 0x97,
  }};
static const rosidl_type_hash_t physical_ai_interfaces__msg__TaskInfo__EXPECTED_HASH = {1, {
    0xb8, 0x04, 0x98, 0x36, 0xeb, 0x8a, 0x6b, 0xde,
    0x3c, 0x92, 0x7b, 0x3d, 0x5b, 0xc6, 0x4f, 0xc7,
    0xa7, 0xfb, 0x87, 0x1c, 0xa6, 0x11, 0x01, 0xc3,
    0x50, 0x0d, 0x4c, 0x25, 0x23, 0x9e, 0x9b, 0x70,
  }};
static const rosidl_type_hash_t service_msgs__msg__ServiceEventInfo__EXPECTED_HASH = {1, {
    0x41, 0xbc, 0xbb, 0xe0, 0x7a, 0x75, 0xc9, 0xb5,
    0x2b, 0xc9, 0x6b, 0xfd, 0x5c, 0x24, 0xd7, 0xf0,
    0xfc, 0x0a, 0x08, 0xc0, 0xcb, 0x79, 0x21, 0xb3,
    0x37, 0x3c, 0x57, 0x32, 0x34, 0x5a, 0x6f, 0x45,
  }};
#endif

static char physical_ai_interfaces__srv__SendCommand__TYPE_NAME[] = "physical_ai_interfaces/srv/SendCommand";
static char builtin_interfaces__msg__Time__TYPE_NAME[] = "builtin_interfaces/msg/Time";
static char physical_ai_interfaces__msg__TaskInfo__TYPE_NAME[] = "physical_ai_interfaces/msg/TaskInfo";
static char physical_ai_interfaces__srv__SendCommand_Event__TYPE_NAME[] = "physical_ai_interfaces/srv/SendCommand_Event";
static char physical_ai_interfaces__srv__SendCommand_Request__TYPE_NAME[] = "physical_ai_interfaces/srv/SendCommand_Request";
static char physical_ai_interfaces__srv__SendCommand_Response__TYPE_NAME[] = "physical_ai_interfaces/srv/SendCommand_Response";
static char service_msgs__msg__ServiceEventInfo__TYPE_NAME[] = "service_msgs/msg/ServiceEventInfo";

// Define type names, field names, and default values
static char physical_ai_interfaces__srv__SendCommand__FIELD_NAME__request_message[] = "request_message";
static char physical_ai_interfaces__srv__SendCommand__FIELD_NAME__response_message[] = "response_message";
static char physical_ai_interfaces__srv__SendCommand__FIELD_NAME__event_message[] = "event_message";

static rosidl_runtime_c__type_description__Field physical_ai_interfaces__srv__SendCommand__FIELDS[] = {
  {
    {physical_ai_interfaces__srv__SendCommand__FIELD_NAME__request_message, 15, 15},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_NESTED_TYPE,
      0,
      0,
      {physical_ai_interfaces__srv__SendCommand_Request__TYPE_NAME, 46, 46},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand__FIELD_NAME__response_message, 16, 16},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_NESTED_TYPE,
      0,
      0,
      {physical_ai_interfaces__srv__SendCommand_Response__TYPE_NAME, 47, 47},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand__FIELD_NAME__event_message, 13, 13},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_NESTED_TYPE,
      0,
      0,
      {physical_ai_interfaces__srv__SendCommand_Event__TYPE_NAME, 44, 44},
    },
    {NULL, 0, 0},
  },
};

static rosidl_runtime_c__type_description__IndividualTypeDescription physical_ai_interfaces__srv__SendCommand__REFERENCED_TYPE_DESCRIPTIONS[] = {
  {
    {builtin_interfaces__msg__Time__TYPE_NAME, 27, 27},
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__TYPE_NAME, 35, 35},
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Event__TYPE_NAME, 44, 44},
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Request__TYPE_NAME, 46, 46},
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Response__TYPE_NAME, 47, 47},
    {NULL, 0, 0},
  },
  {
    {service_msgs__msg__ServiceEventInfo__TYPE_NAME, 33, 33},
    {NULL, 0, 0},
  },
};

const rosidl_runtime_c__type_description__TypeDescription *
physical_ai_interfaces__srv__SendCommand__get_type_description(
  const rosidl_service_type_support_t * type_support)
{
  (void)type_support;
  static bool constructed = false;
  static const rosidl_runtime_c__type_description__TypeDescription description = {
    {
      {physical_ai_interfaces__srv__SendCommand__TYPE_NAME, 38, 38},
      {physical_ai_interfaces__srv__SendCommand__FIELDS, 3, 3},
    },
    {physical_ai_interfaces__srv__SendCommand__REFERENCED_TYPE_DESCRIPTIONS, 6, 6},
  };
  if (!constructed) {
    assert(0 == memcmp(&builtin_interfaces__msg__Time__EXPECTED_HASH, builtin_interfaces__msg__Time__get_type_hash(NULL), sizeof(rosidl_type_hash_t)));
    description.referenced_type_descriptions.data[0].fields = builtin_interfaces__msg__Time__get_type_description(NULL)->type_description.fields;
    assert(0 == memcmp(&physical_ai_interfaces__msg__TaskInfo__EXPECTED_HASH, physical_ai_interfaces__msg__TaskInfo__get_type_hash(NULL), sizeof(rosidl_type_hash_t)));
    description.referenced_type_descriptions.data[1].fields = physical_ai_interfaces__msg__TaskInfo__get_type_description(NULL)->type_description.fields;
    description.referenced_type_descriptions.data[2].fields = physical_ai_interfaces__srv__SendCommand_Event__get_type_description(NULL)->type_description.fields;
    description.referenced_type_descriptions.data[3].fields = physical_ai_interfaces__srv__SendCommand_Request__get_type_description(NULL)->type_description.fields;
    description.referenced_type_descriptions.data[4].fields = physical_ai_interfaces__srv__SendCommand_Response__get_type_description(NULL)->type_description.fields;
    assert(0 == memcmp(&service_msgs__msg__ServiceEventInfo__EXPECTED_HASH, service_msgs__msg__ServiceEventInfo__get_type_hash(NULL), sizeof(rosidl_type_hash_t)));
    description.referenced_type_descriptions.data[5].fields = service_msgs__msg__ServiceEventInfo__get_type_description(NULL)->type_description.fields;
    constructed = true;
  }
  return &description;
}
// Define type names, field names, and default values
static char physical_ai_interfaces__srv__SendCommand_Request__FIELD_NAME__command[] = "command";
static char physical_ai_interfaces__srv__SendCommand_Request__FIELD_NAME__task_info[] = "task_info";

static rosidl_runtime_c__type_description__Field physical_ai_interfaces__srv__SendCommand_Request__FIELDS[] = {
  {
    {physical_ai_interfaces__srv__SendCommand_Request__FIELD_NAME__command, 7, 7},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_UINT8,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Request__FIELD_NAME__task_info, 9, 9},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_NESTED_TYPE,
      0,
      0,
      {physical_ai_interfaces__msg__TaskInfo__TYPE_NAME, 35, 35},
    },
    {NULL, 0, 0},
  },
};

static rosidl_runtime_c__type_description__IndividualTypeDescription physical_ai_interfaces__srv__SendCommand_Request__REFERENCED_TYPE_DESCRIPTIONS[] = {
  {
    {physical_ai_interfaces__msg__TaskInfo__TYPE_NAME, 35, 35},
    {NULL, 0, 0},
  },
};

const rosidl_runtime_c__type_description__TypeDescription *
physical_ai_interfaces__srv__SendCommand_Request__get_type_description(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static bool constructed = false;
  static const rosidl_runtime_c__type_description__TypeDescription description = {
    {
      {physical_ai_interfaces__srv__SendCommand_Request__TYPE_NAME, 46, 46},
      {physical_ai_interfaces__srv__SendCommand_Request__FIELDS, 2, 2},
    },
    {physical_ai_interfaces__srv__SendCommand_Request__REFERENCED_TYPE_DESCRIPTIONS, 1, 1},
  };
  if (!constructed) {
    assert(0 == memcmp(&physical_ai_interfaces__msg__TaskInfo__EXPECTED_HASH, physical_ai_interfaces__msg__TaskInfo__get_type_hash(NULL), sizeof(rosidl_type_hash_t)));
    description.referenced_type_descriptions.data[0].fields = physical_ai_interfaces__msg__TaskInfo__get_type_description(NULL)->type_description.fields;
    constructed = true;
  }
  return &description;
}
// Define type names, field names, and default values
static char physical_ai_interfaces__srv__SendCommand_Response__FIELD_NAME__success[] = "success";
static char physical_ai_interfaces__srv__SendCommand_Response__FIELD_NAME__message[] = "message";

static rosidl_runtime_c__type_description__Field physical_ai_interfaces__srv__SendCommand_Response__FIELDS[] = {
  {
    {physical_ai_interfaces__srv__SendCommand_Response__FIELD_NAME__success, 7, 7},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_BOOLEAN,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Response__FIELD_NAME__message, 7, 7},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_STRING,
      0,
      0,
      {NULL, 0, 0},
    },
    {NULL, 0, 0},
  },
};

const rosidl_runtime_c__type_description__TypeDescription *
physical_ai_interfaces__srv__SendCommand_Response__get_type_description(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static bool constructed = false;
  static const rosidl_runtime_c__type_description__TypeDescription description = {
    {
      {physical_ai_interfaces__srv__SendCommand_Response__TYPE_NAME, 47, 47},
      {physical_ai_interfaces__srv__SendCommand_Response__FIELDS, 2, 2},
    },
    {NULL, 0, 0},
  };
  if (!constructed) {
    constructed = true;
  }
  return &description;
}
// Define type names, field names, and default values
static char physical_ai_interfaces__srv__SendCommand_Event__FIELD_NAME__info[] = "info";
static char physical_ai_interfaces__srv__SendCommand_Event__FIELD_NAME__request[] = "request";
static char physical_ai_interfaces__srv__SendCommand_Event__FIELD_NAME__response[] = "response";

static rosidl_runtime_c__type_description__Field physical_ai_interfaces__srv__SendCommand_Event__FIELDS[] = {
  {
    {physical_ai_interfaces__srv__SendCommand_Event__FIELD_NAME__info, 4, 4},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_NESTED_TYPE,
      0,
      0,
      {service_msgs__msg__ServiceEventInfo__TYPE_NAME, 33, 33},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Event__FIELD_NAME__request, 7, 7},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_NESTED_TYPE_BOUNDED_SEQUENCE,
      1,
      0,
      {physical_ai_interfaces__srv__SendCommand_Request__TYPE_NAME, 46, 46},
    },
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Event__FIELD_NAME__response, 8, 8},
    {
      rosidl_runtime_c__type_description__FieldType__FIELD_TYPE_NESTED_TYPE_BOUNDED_SEQUENCE,
      1,
      0,
      {physical_ai_interfaces__srv__SendCommand_Response__TYPE_NAME, 47, 47},
    },
    {NULL, 0, 0},
  },
};

static rosidl_runtime_c__type_description__IndividualTypeDescription physical_ai_interfaces__srv__SendCommand_Event__REFERENCED_TYPE_DESCRIPTIONS[] = {
  {
    {builtin_interfaces__msg__Time__TYPE_NAME, 27, 27},
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__msg__TaskInfo__TYPE_NAME, 35, 35},
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Request__TYPE_NAME, 46, 46},
    {NULL, 0, 0},
  },
  {
    {physical_ai_interfaces__srv__SendCommand_Response__TYPE_NAME, 47, 47},
    {NULL, 0, 0},
  },
  {
    {service_msgs__msg__ServiceEventInfo__TYPE_NAME, 33, 33},
    {NULL, 0, 0},
  },
};

const rosidl_runtime_c__type_description__TypeDescription *
physical_ai_interfaces__srv__SendCommand_Event__get_type_description(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static bool constructed = false;
  static const rosidl_runtime_c__type_description__TypeDescription description = {
    {
      {physical_ai_interfaces__srv__SendCommand_Event__TYPE_NAME, 44, 44},
      {physical_ai_interfaces__srv__SendCommand_Event__FIELDS, 3, 3},
    },
    {physical_ai_interfaces__srv__SendCommand_Event__REFERENCED_TYPE_DESCRIPTIONS, 5, 5},
  };
  if (!constructed) {
    assert(0 == memcmp(&builtin_interfaces__msg__Time__EXPECTED_HASH, builtin_interfaces__msg__Time__get_type_hash(NULL), sizeof(rosidl_type_hash_t)));
    description.referenced_type_descriptions.data[0].fields = builtin_interfaces__msg__Time__get_type_description(NULL)->type_description.fields;
    assert(0 == memcmp(&physical_ai_interfaces__msg__TaskInfo__EXPECTED_HASH, physical_ai_interfaces__msg__TaskInfo__get_type_hash(NULL), sizeof(rosidl_type_hash_t)));
    description.referenced_type_descriptions.data[1].fields = physical_ai_interfaces__msg__TaskInfo__get_type_description(NULL)->type_description.fields;
    description.referenced_type_descriptions.data[2].fields = physical_ai_interfaces__srv__SendCommand_Request__get_type_description(NULL)->type_description.fields;
    description.referenced_type_descriptions.data[3].fields = physical_ai_interfaces__srv__SendCommand_Response__get_type_description(NULL)->type_description.fields;
    assert(0 == memcmp(&service_msgs__msg__ServiceEventInfo__EXPECTED_HASH, service_msgs__msg__ServiceEventInfo__get_type_hash(NULL), sizeof(rosidl_type_hash_t)));
    description.referenced_type_descriptions.data[4].fields = service_msgs__msg__ServiceEventInfo__get_type_description(NULL)->type_description.fields;
    constructed = true;
  }
  return &description;
}

static char toplevel_type_raw_source[] =
  "########################################\n"
  "# Constants\n"
  "########################################\n"
  "# command\n"
  "uint8 IDLE = 0\n"
  "uint8 START_RECORD = 1\n"
  "uint8 START_INFERENCE = 2\n"
  "uint8 STOP = 3\n"
  "uint8 MOVE_TO_NEXT = 4\n"
  "uint8 RERECORD = 5\n"
  "uint8 FINISH = 6\n"
  "uint8 SKIP_TASK = 7\n"
  "\n"
  "uint8 command\n"
  "TaskInfo task_info\n"
  "---\n"
  "bool success\n"
  "string message";

static char srv_encoding[] = "srv";
static char implicit_encoding[] = "implicit";

// Define all individual source functions

const rosidl_runtime_c__type_description__TypeSource *
physical_ai_interfaces__srv__SendCommand__get_individual_type_description_source(
  const rosidl_service_type_support_t * type_support)
{
  (void)type_support;
  static const rosidl_runtime_c__type_description__TypeSource source = {
    {physical_ai_interfaces__srv__SendCommand__TYPE_NAME, 38, 38},
    {srv_encoding, 3, 3},
    {toplevel_type_raw_source, 328, 328},
  };
  return &source;
}

const rosidl_runtime_c__type_description__TypeSource *
physical_ai_interfaces__srv__SendCommand_Request__get_individual_type_description_source(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static const rosidl_runtime_c__type_description__TypeSource source = {
    {physical_ai_interfaces__srv__SendCommand_Request__TYPE_NAME, 46, 46},
    {implicit_encoding, 8, 8},
    {NULL, 0, 0},
  };
  return &source;
}

const rosidl_runtime_c__type_description__TypeSource *
physical_ai_interfaces__srv__SendCommand_Response__get_individual_type_description_source(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static const rosidl_runtime_c__type_description__TypeSource source = {
    {physical_ai_interfaces__srv__SendCommand_Response__TYPE_NAME, 47, 47},
    {implicit_encoding, 8, 8},
    {NULL, 0, 0},
  };
  return &source;
}

const rosidl_runtime_c__type_description__TypeSource *
physical_ai_interfaces__srv__SendCommand_Event__get_individual_type_description_source(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static const rosidl_runtime_c__type_description__TypeSource source = {
    {physical_ai_interfaces__srv__SendCommand_Event__TYPE_NAME, 44, 44},
    {implicit_encoding, 8, 8},
    {NULL, 0, 0},
  };
  return &source;
}

const rosidl_runtime_c__type_description__TypeSource__Sequence *
physical_ai_interfaces__srv__SendCommand__get_type_description_sources(
  const rosidl_service_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_runtime_c__type_description__TypeSource sources[7];
  static const rosidl_runtime_c__type_description__TypeSource__Sequence source_sequence = {sources, 7, 7};
  static bool constructed = false;
  if (!constructed) {
    sources[0] = *physical_ai_interfaces__srv__SendCommand__get_individual_type_description_source(NULL),
    sources[1] = *builtin_interfaces__msg__Time__get_individual_type_description_source(NULL);
    sources[2] = *physical_ai_interfaces__msg__TaskInfo__get_individual_type_description_source(NULL);
    sources[3] = *physical_ai_interfaces__srv__SendCommand_Event__get_individual_type_description_source(NULL);
    sources[4] = *physical_ai_interfaces__srv__SendCommand_Request__get_individual_type_description_source(NULL);
    sources[5] = *physical_ai_interfaces__srv__SendCommand_Response__get_individual_type_description_source(NULL);
    sources[6] = *service_msgs__msg__ServiceEventInfo__get_individual_type_description_source(NULL);
    constructed = true;
  }
  return &source_sequence;
}

const rosidl_runtime_c__type_description__TypeSource__Sequence *
physical_ai_interfaces__srv__SendCommand_Request__get_type_description_sources(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_runtime_c__type_description__TypeSource sources[2];
  static const rosidl_runtime_c__type_description__TypeSource__Sequence source_sequence = {sources, 2, 2};
  static bool constructed = false;
  if (!constructed) {
    sources[0] = *physical_ai_interfaces__srv__SendCommand_Request__get_individual_type_description_source(NULL),
    sources[1] = *physical_ai_interfaces__msg__TaskInfo__get_individual_type_description_source(NULL);
    constructed = true;
  }
  return &source_sequence;
}

const rosidl_runtime_c__type_description__TypeSource__Sequence *
physical_ai_interfaces__srv__SendCommand_Response__get_type_description_sources(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_runtime_c__type_description__TypeSource sources[1];
  static const rosidl_runtime_c__type_description__TypeSource__Sequence source_sequence = {sources, 1, 1};
  static bool constructed = false;
  if (!constructed) {
    sources[0] = *physical_ai_interfaces__srv__SendCommand_Response__get_individual_type_description_source(NULL),
    constructed = true;
  }
  return &source_sequence;
}

const rosidl_runtime_c__type_description__TypeSource__Sequence *
physical_ai_interfaces__srv__SendCommand_Event__get_type_description_sources(
  const rosidl_message_type_support_t * type_support)
{
  (void)type_support;
  static rosidl_runtime_c__type_description__TypeSource sources[6];
  static const rosidl_runtime_c__type_description__TypeSource__Sequence source_sequence = {sources, 6, 6};
  static bool constructed = false;
  if (!constructed) {
    sources[0] = *physical_ai_interfaces__srv__SendCommand_Event__get_individual_type_description_source(NULL),
    sources[1] = *builtin_interfaces__msg__Time__get_individual_type_description_source(NULL);
    sources[2] = *physical_ai_interfaces__msg__TaskInfo__get_individual_type_description_source(NULL);
    sources[3] = *physical_ai_interfaces__srv__SendCommand_Request__get_individual_type_description_source(NULL);
    sources[4] = *physical_ai_interfaces__srv__SendCommand_Response__get_individual_type_description_source(NULL);
    sources[5] = *service_msgs__msg__ServiceEventInfo__get_individual_type_description_source(NULL);
    constructed = true;
  }
  return &source_sequence;
}
