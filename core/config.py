import os
import yaml

def load_config():
    # 1. Prioritaskan config lokal di development
    local_config_path = os.path.join(os.getcwd(), 'config.yaml')
    global_config_path = '/etc/devopin-agent/config.yaml'

    if os.path.exists(local_config_path):
        print(f"[dev] Loading config from {local_config_path}")
        with open(local_config_path, 'r') as f:
            return yaml.safe_load(f)
    elif os.path.exists(global_config_path):
        print(f"[prod] Loading config from {global_config_path}")
        with open(global_config_path, 'r') as f:
            return yaml.safe_load(f)
    else:
        raise FileNotFoundError("Config file not found in both local and global paths")
