########################################
# Constants
########################################
# phase
uint8 NONE = 0
uint8 WARMING_UP = 1
uint8 RESETTING = 2
uint8 RECORDING = 3
uint8 STOPED = 4

TaskInfo task_info
uint8_t phase                   # (0: NONE, 1: WARMING_UP, 2: RESETTING 3: RECORDING, 4: STOPED)
uint16_t total_time             # [s]
uint16_t proceed_time           # [s]
uint16_t num_episodes
uint16_t current_episode_number
float32 used_storage_size       # [GB]
float32 total_storage_size      # [GB]
