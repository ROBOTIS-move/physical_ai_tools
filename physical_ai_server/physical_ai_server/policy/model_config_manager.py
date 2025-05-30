from typing import Dict, Any, Optional, Union
import os
import json
import yaml
from pathlib import Path
import logging


class ModelConfigManager:
    """
    Enhanced configuration manager for handling pretrained model configurations
    and merging them with user-provided configurations.
    
    This class provides automatic configuration loading from pretrained models,
    intelligent merging of configurations, validation, and fallback mechanisms.
    """
    
    def __init__(self):
        """Initialize the ModelConfigManager"""
        self.logger = logging.getLogger(__name__)
    
    def load_pretrained_config(self, model_path: str) -> Dict[str, Any]:
        """
        Load configuration from a pretrained model directory or file.
        
        Args:
            model_path: Path to the pretrained model directory or checkpoint file
            
        Returns:
            Dictionary containing the loaded configuration
            
        Raises:
            FileNotFoundError: If no valid configuration file is found
            ValueError: If configuration file format is invalid
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path does not exist: {model_path}")
        
        config_data = {}
        
        # If model_path is a file, look for config in the same directory
        if os.path.isfile(model_path):
            model_dir = os.path.dirname(model_path)
        else:
            model_dir = model_path
        
        # Try to find configuration files in order of preference
        config_candidates = [
            'config.json',
            'policy_config.json', 
            'model_config.json',
            'config.yaml',
            'config.yml',
            'configuration.json'
        ]
        
        config_file_found = None
        for config_file in config_candidates:
            config_path = os.path.join(model_dir, config_file)
            if os.path.exists(config_path):
                config_file_found = config_path
                break
        
        if config_file_found:
            try:
                if config_file_found.endswith(('.json',)):
                    with open(config_file_found, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                elif config_file_found.endswith(('.yaml', '.yml')):
                    with open(config_file_found, 'r', encoding='utf-8') as f:
                        config_data = yaml.safe_load(f)
                
                self.logger.info(f"Loaded pretrained config from: {config_file_found}")
                
            except Exception as e:
                self.logger.warning(f"Failed to load config from {config_file_found}: {e}")
        
        # Try to extract config from checkpoint file if available
        if not config_data and os.path.isfile(model_path) and model_path.endswith(('.pt', '.pth')):
            try:
                import torch
                checkpoint = torch.load(model_path, map_location='cpu')
                if 'config' in checkpoint:
                    config_data = checkpoint['config']
                    self.logger.info(f"Loaded config from checkpoint: {model_path}")
            except Exception as e:
                self.logger.warning(f"Failed to load config from checkpoint {model_path}: {e}")
        
        return config_data if config_data else {}
    
    def merge_configs(self, 
                     pretrained_config: Dict[str, Any], 
                     user_config: Dict[str, Any],
                     merge_strategy: str = "user_priority") -> Dict[str, Any]:
        """
        Merge pretrained configuration with user-provided configuration.
        
        Args:
            pretrained_config: Configuration loaded from pretrained model
            user_config: User-provided configuration
            merge_strategy: Strategy for merging conflicts
                - "user_priority": User config overrides pretrained config
                - "pretrained_priority": Pretrained config takes precedence
                - "smart_merge": Intelligent merging based on field types
            
        Returns:
            Merged configuration dictionary
        """
        if not pretrained_config:
            return user_config.copy()
        
        if not user_config:
            return pretrained_config.copy()
        
        if merge_strategy == "user_priority":
            merged = pretrained_config.copy()
            # Extract camera names from pretrained config if available
            pretrained_cameras = self._extract_camera_names_from_input_features(pretrained_config)
            if pretrained_cameras:
                merged['camera_names'] = pretrained_cameras
            merged.update(user_config)
            # If user didn't specify camera_names but pretrained has them, keep pretrained ones
            if pretrained_cameras and 'camera_names' not in user_config:
                merged['camera_names'] = pretrained_cameras
            
        elif merge_strategy == "pretrained_priority":
            merged = user_config.copy()
            # Extract camera names from pretrained config if available
            pretrained_cameras = self._extract_camera_names_from_input_features(pretrained_config)
            if pretrained_cameras:
                pretrained_config['camera_names'] = pretrained_cameras
            merged.update(pretrained_config)
            
        elif merge_strategy == "smart_merge":
            merged = self._smart_merge_configs(pretrained_config, user_config)
            
        else:
            raise ValueError(f"Unknown merge strategy: {merge_strategy}")
        
        # Always preserve critical user preferences
        critical_user_fields = ['device', 'policy_type', 'inference']
        for field in critical_user_fields:
            if field in user_config:
                merged[field] = user_config[field]
        
        self.logger.info(f"Merged configs using strategy: {merge_strategy}")
        return merged
    
    def _smart_merge_configs(self, 
                           pretrained_config: Dict[str, Any], 
                           user_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform intelligent merging of configurations.
        
        This method applies different merging strategies based on the field type
        and semantic meaning of configuration parameters.
        """
        merged = pretrained_config.copy()
        
        # Extract camera names from pretrained config input_features if available
        pretrained_cameras = self._extract_camera_names_from_input_features(pretrained_config)
        if pretrained_cameras:
            merged['camera_names'] = pretrained_cameras
            self.logger.info(f"Extracted camera names from pretrained config: {pretrained_cameras}")
        
        for key, user_value in user_config.items():
            if key not in merged:
                # New field from user config
                merged[key] = user_value
                
            elif isinstance(user_value, dict) and isinstance(merged[key], dict):
                # Recursively merge nested dictionaries
                merged[key] = self._smart_merge_configs(merged[key], user_value)
                
            elif key in ['device', 'policy_type', 'batch_size', 'num_inference_steps']:
                # User preferences always take priority for these fields
                merged[key] = user_value
                
            elif key == 'camera_names':
                # For camera_names, use pretrained if available, otherwise user config
                if pretrained_cameras:
                    merged[key] = pretrained_cameras
                    self.logger.info(f"Using pretrained camera names: {pretrained_cameras}")
                else:
                    merged[key] = user_value
                    self.logger.info(f"Using user-provided camera names: {user_value}")
                
            elif key in ['model', 'architecture'] and isinstance(user_value, dict):
                # For model configs, merge intelligently
                if isinstance(merged[key], dict):
                    model_config = merged[key].copy()
                    model_config.update(user_value)
                    merged[key] = model_config
                else:
                    merged[key] = user_value
                    
            else:
                # Default: user config takes priority
                merged[key] = user_value
        
        return merged
    
    def _extract_camera_names_from_input_features(self, config: Dict[str, Any]) -> Optional[list]:
        """
        Extract camera names from input_features configuration.
        
        This method looks for camera-related keys in the input_features section
        and extracts the camera names from observation.images.* keys.
        
        Args:
            config: Configuration dictionary containing input_features
            
        Returns:
            List of camera names if found, None otherwise
        """
        if 'input_features' not in config:
            return None
        
        input_features = config['input_features']
        camera_names = []
        
        for key, feature_config in input_features.items():
            # Look for observation.images.camera_name pattern
            if key.startswith('observation.images.') and feature_config.get('type') == 'VISUAL':
                # Extract camera name from the key
                camera_name = key.replace('observation.images.', '')
                camera_names.append(camera_name)
        
        # Sort camera names for consistency
        camera_names.sort()
        
        if camera_names:
            self.logger.info(f"Extracted {len(camera_names)} camera names from input_features: {camera_names}")
            return camera_names
        
        return None
    
    def validate_merged_config(self, 
                             config: Dict[str, Any], 
                             policy_type: str) -> Dict[str, Any]:
        """
        Validate and sanitize the merged configuration.
        
        Args:
            config: The merged configuration to validate
            policy_type: Type of policy (act, diffusion, pi0, gr00t_n1)
            
        Returns:
            Validated and potentially corrected configuration
            
        Raises:
            ValueError: If critical configuration fields are missing or invalid
        """
        validated_config = config.copy()
        
        # Ensure policy_type is set
        if 'policy_type' not in validated_config:
            validated_config['policy_type'] = policy_type
        
        # Validate device setting
        if 'device' not in validated_config:
            import torch
            validated_config['device'] = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        # Policy-specific validation
        if policy_type == 'act':
            validated_config = self._validate_act_config(validated_config)
        elif policy_type == 'diffusion':
            validated_config = self._validate_diffusion_config(validated_config)
        elif policy_type == 'pi0':
            validated_config = self._validate_pi0_config(validated_config)
        elif policy_type == 'gr00t_n1':
            validated_config = self._validate_gr00t_config(validated_config)
        
        self.logger.info(f"Validated config for policy type: {policy_type}")
        return validated_config
    
    def _validate_act_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate ACT-specific configuration parameters"""
        validated = config.copy()
        
        # Ensure model section exists
        if 'model' not in validated:
            validated['model'] = {}
        
        model_config = validated['model']
        
        # Set default ACT parameters if missing
        act_defaults = {
            'chunk_size': 100,
            'kl_weight': 10.0,
            'hidden_dim': 512,
            'dim_feedforward': 3200,
            'enc_layers': 4,
            'dec_layers': 7,
            'nheads': 8,
            'backbone': 'resnet18'
        }
        
        for key, default_value in act_defaults.items():
            if key not in model_config:
                model_config[key] = default_value
        
        return validated
    
    def _validate_diffusion_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Diffusion Policy-specific configuration parameters"""
        validated = config.copy()
        
        # Ensure inference section exists
        if 'inference' not in validated:
            validated['inference'] = {}
        
        inference_config = validated['inference']
        
        # Set default diffusion parameters
        if 'num_inference_steps' not in inference_config:
            inference_config['num_inference_steps'] = 20
        
        if 'batch_size' not in inference_config:
            inference_config['batch_size'] = 1
        
        return validated
    
    def _validate_pi0_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Pi0-specific configuration parameters"""
        validated = config.copy()
        
        # Ensure model section exists
        if 'model' not in validated:
            validated['model'] = {}
        
        return validated
    
    def _validate_gr00t_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate GR00T N1-specific configuration parameters"""
        validated = config.copy()
        
        # Ensure inference section exists
        if 'inference' not in validated:
            validated['inference'] = {}
        
        inference_config = validated['inference']
        
        # Set default sequence length
        if 'sequence_length' not in inference_config:
            inference_config['sequence_length'] = 50
        
        return validated
    
    def create_enhanced_config(self, 
                             model_path: Optional[str] = None,
                             user_config: Optional[Dict[str, Any]] = None,
                             policy_type: str = 'act',
                             merge_strategy: str = "user_priority") -> Dict[str, Any]:
        """
        Create an enhanced configuration by loading pretrained config and merging with user config.
        
        Args:
            model_path: Path to pretrained model (optional)
            user_config: User-provided configuration (optional)
            policy_type: Type of policy
            merge_strategy: Strategy for merging configurations
            
        Returns:
            Enhanced and validated configuration
        """
        # Load pretrained configuration if model path is provided
        pretrained_config = {}
        if model_path:
            try:
                pretrained_config = self.load_pretrained_config(model_path)
            except Exception as e:
                self.logger.warning(f"Failed to load pretrained config: {e}")
        
        # Use empty dict if user_config is None
        if user_config is None:
            user_config = {}
        
        # Merge configurations
        merged_config = self.merge_configs(pretrained_config, user_config, merge_strategy)
        
        # Validate the merged configuration
        validated_config = self.validate_merged_config(merged_config, policy_type)
        
        return validated_config
    
    def save_config(self, config: Dict[str, Any], save_path: str) -> None:
        """
        Save configuration to a file.
        
        Args:
            config: Configuration dictionary to save
            save_path: Path where to save the configuration
        """
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        if save_path.suffix.lower() == '.json':
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        elif save_path.suffix.lower() in ['.yaml', '.yml']:
            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        else:
            # Default to JSON
            with open(save_path.with_suffix('.json'), 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Saved configuration to: {save_path}")
