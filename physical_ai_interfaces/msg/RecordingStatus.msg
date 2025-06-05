########################################
# Constants
########################################
# phase
uint8 NONE = 0
uint8 ON_WARM_UP = 1
uint8 ON_RESET = 2
uint8 ON_EPISODE = 3

string task_name
uint8_t phase      # (0: NONE, 1: ON_WARM_UP, 2: ON_RESET 3: ON_EPISODE)
uint8_t progress   # (0 ~ 100)
uint16_t num_episodes
uint16_t current_episode_number
string repo_id