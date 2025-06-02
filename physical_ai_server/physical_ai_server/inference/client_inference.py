import torch
import zmq
from io import BytesIO

class ClientInference:
    def __init__(self, server_address: str = "*", port: int = ):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://{host}:{port}")



inference_manager = InferenceManager(
    policy_type="act",
    policy_path="/home/dongyun/.cache/huggingface/hub/models--Dongkkka--act_model_ffw/snapshots/2124b18a2a8edf748eeeeb6d853e290f3edd0ecd/pretrained_model",
    device="cuda")

image = np.zeros((480, 640, 3), dtype=np.uint8)
images = {
    "cam_head": image,
    "cam_wrist_1": image,
    "cam_wrist_2": image,
}

state = np.zeros(16, dtype=np.float32)

action = inference_manager.predict(
    images=images,
    state=state,
    task_instruction="Sample task"
)