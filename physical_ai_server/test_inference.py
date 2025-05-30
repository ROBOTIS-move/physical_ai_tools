"""
Enhanced inference test with automatic configuration management

This script demonstrates the enhanced configuration management system that
automatically loads pretrained model configurations and merges them with
user-provided settings.
"""

import logging
from physical_ai_server.policy import PolicyFactory

# Set up logging for detailed information
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

# User configuration - only specify what you want to override
user_config = {
    'device': 'cuda',
    'policy_type': 'act',
    'model': {
        'chunk_size': 100,  # Override if needed
        'camera_names': ["top"]  # Specify cameras
    },
    'inference': {
        'batch_size': 1
    }
}

# Path to pretrained model
model_path = '/home/elicer/.cache/huggingface/hub/models--Dongkkka--act_model_ffw/snapshots/2124b18a2a8edf748eeeeb6d853e290f3edd0ecd/pretrained_model'

print("=" * 80)
print("ENHANCED ACT POLICY INFERENCE TEST")
print("=" * 80)

try:
    # Create policy with enhanced configuration management
    # The system will automatically load pretrained model config and merge with user config
    print("\n1. Creating ACT policy with enhanced configuration management...")
    policy = PolicyFactory.create_policy(
        'act', 
        config_dict=user_config,
        pretrained_model_path=model_path,  # This enables automatic config loading
        merge_strategy="user_priority"     # User config takes priority over pretrained
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
    
    # Test configuration update
    print("\n7. Testing Configuration Update:")
    print("-" * 60)
    
    # Update some configuration
    new_config = {'inference': {'batch_size': 2}}
    policy.update_config(new_config, merge_with_pretrained=True)
    print("✓ Configuration updated successfully")
    
    updated_info = policy.get_model_info()
    print(f"Updated batch size: {updated_info['config_summary']['inference_config']['batch_size']}")
    
    # Save current configuration for future use
    print("\n8. Saving Enhanced Configuration:")
    print("-" * 60)
    
    config_save_path = "enhanced_act_config.yaml"
    policy.save_current_config(config_save_path)
    print(f"✓ Configuration saved to: {config_save_path}")
    
    print("\n" + "=" * 80)
    print("ENHANCED CONFIGURATION TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    
    print("\nKey Benefits of Enhanced Configuration Management:")
    print("• Automatic pretrained model configuration loading")
    print("• Intelligent merging of user and pretrained configurations")
    print("• Configuration validation and fallback mechanisms")
    print("• Comprehensive model information reporting")
    print("• Dynamic configuration updates")
    print("• Configuration persistence and sharing")

except Exception as e:
    print(f"\n❌ Error during inference test: {e}")
    import traceback
    traceback.print_exc()
    
    print("\nTroubleshooting Tips:")
    print("1. Check if the model path exists and is accessible")
    print("2. Verify CUDA availability if using GPU")
    print("3. Ensure all required dependencies are installed")
    print("4. Check the logs for detailed error information")
