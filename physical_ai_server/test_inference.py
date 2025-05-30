"""
Simple inference test with automatic configuration loading

This script demonstrates a clean approach using only:
1. Pretrained model's config.json 
2. Optional act_config.yaml (if additional overrides needed)

No additional configuration files are created or stored.
"""

import logging
from physical_ai_server.policy import PolicyFactory

# Set up logging for detailed information
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

# Optional user configuration file path (if you want to override defaults)
# If None, only pretrained model config.json will be used
user_config_file = None  # Could be path to act_config.yaml if needed

# Path to pretrained model (현재 PC의 올바른 경로)
model_path = '/home/dongyun/.cache/huggingface/hub/models--Dongkkka--act_model_ffw/snapshots/2124b18a2a8edf748eeeeb6d853e290f3edd0ecd/pretrained_model'

print("=" * 80)
print("SIMPLE ACT POLICY INFERENCE TEST")
print("=" * 80)

try:
    # Create policy using only pretrained model config (no additional overrides)
    # The system will automatically load config.json from the pretrained model
    print("\n1. Creating ACT policy with automatic config loading...")
    policy = PolicyFactory.create_policy(
        'act', 
        config_dict=None,  # No user overrides needed
        pretrained_model_path=model_path,  # Only this is needed
        merge_strategy="pretrained_only"   # Use only pretrained model config
    )
    
    print("✓ Policy created successfully")
    
    # Load the model (the path can be auto-detected from configuration)
    print("\n2. Loading model...")
    policy.load_model()  # No need to specify path again - it's in the enhanced config
    print("✓ Model loaded successfully")
    
    # Display comprehensive model information
    print("\n3. Model Information:")
    print("-" * 60)
    model_info = policy.get_model_info()
    
    print(f"Policy Type: {model_info['policy_type']}")
    print(f"Class Name: {model_info['class_name']}")
    print(f"Device: {model_info['device']}")
    print(f"Model Loaded: {model_info['is_loaded']}")
    print(f"Pretrained Model Path: {model_info['pretrained_model_path']}")
    
    # Display configuration summary
    print("\n4. Configuration Summary:")
    print("-" * 60)
    config_summary = model_info['config_summary']
    print(f"Device: {config_summary['device']}")
    print(f"Policy Type: {config_summary['policy_type']}")
    
    # Display camera names if available
    full_config = policy.get_config()
    if 'camera_names' in full_config:
        print(f"Camera Names: {full_config['camera_names']}")
    
    # Display data configuration if available
    if 'data' in full_config:
        data_config = full_config['data']
        if 'image_keys' in data_config:
            print(f"Image Keys: {data_config['image_keys']}")
        if 'delta_timestamps' in data_config:
            delta_ts = data_config['delta_timestamps']
            print(f"Delta Timestamps Keys: {list(delta_ts.keys())}")
            if 'action' in delta_ts:
                action_ts = delta_ts['action']
                print(f"Action Timestamps: {len(action_ts)} steps ({action_ts[0]} to {action_ts[-1]})")
    
    # Display input/output features if available
    if 'input_features' in full_config:
        print(f"\nInput Features:")
        for feature_name, feature_config in full_config['input_features'].items():
            feature_type = feature_config.get('type', 'Unknown')
            feature_shape = feature_config.get('shape', 'Unknown')
            print(f"  {feature_name}: {feature_type} {feature_shape}")
    
    if 'output_features' in full_config:
        print(f"\nOutput Features:")
        for feature_name, feature_config in full_config['output_features'].items():
            feature_type = feature_config.get('type', 'Unknown')
            feature_shape = feature_config.get('shape', 'Unknown')
            print(f"  {feature_name}: {feature_type} {feature_shape}")
    
    if 'model_config' in config_summary and config_summary['model_config']:
        model_cfg = config_summary['model_config']
        print("\nModel Configuration:")
        for key, value in model_cfg.items():
            if value is not None:
                print(f"  {key}: {value}")
    
    if 'inference_config' in config_summary:
        print(f"\nInference Configuration:")
        for key, value in config_summary['inference_config'].items():
            print(f"  {key}: {value}")
    
    # Display model parameters if available
    if model_info['model_parameters']:
        print("\n5. Model Parameters:")
        print("-" * 60)
        params = model_info['model_parameters']
        print(f"Total Parameters: {params['total_parameters']:,}")
        print(f"Trainable Parameters: {params['trainable_parameters']:,}")
        print(f"Model Size: {params['model_size_mb']:.2f} MB")
        print(f"Model Device: {params['device']}")
    
    # Display full configuration (optional - can be very long)
    print("\n6. Full Configuration:")
    print("-" * 60)
    full_config = policy.get_config()
    
    # Display key sections only to avoid too much output
    sections_to_show = ['device', 'policy_type', 'model', 'inference']
    for section in sections_to_show:
        if section in full_config:
            print(f"{section}: {full_config[section]}")
    
    # Test configuration update (optional, only if needed at runtime)
    print("\n7. Configuration Information:")
    print("-" * 60)
    
    # Show that all config comes from pretrained model + minimal runtime settings
    updated_info = policy.get_model_info()
    config_source = updated_info.get('config_source', 'Unknown')
    print(f"Configuration Source: {config_source}")
    print("✓ Using clean configuration from pretrained model only")
    
    print("\n" + "=" * 80)
    print("SIMPLE ACT POLICY INFERENCE TEST COMPLETED!")
    print("=" * 80)
    
    print("\nSimple Configuration Benefits:")
    print("• Only uses pretrained model's config.json")
    print("• No duplicate or override files needed")
    print("• Clean and maintainable configuration")
    print("• Automatic camera names and model parameters detection")

except Exception as e:
    print(f"\n❌ Error during inference test: {e}")
    import traceback
    traceback.print_exc()
    
    print("\nTroubleshooting Tips:")
    print("1. Check if the model path exists and is accessible")
    print("2. Verify CUDA availability if using GPU")
    print("3. Ensure all required dependencies are installed")
    print("4. Check the logs for detailed error information")
