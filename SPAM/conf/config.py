import yaml
class Box:
    def __init__(self, box):
        self.config = box.get('config')
        self.id = box['id']
        self.cloud = box.get('cloud')

class Env:
    def __init__(self, env: dict):
        if "startid" in env:
            self.startid = int(env['startid'])
        if "template_node" in env:
            self.template_node = env['template_node']
        self.nodes = env['nodes']
        self.boxes = [Box(box) for box in env['boxes']]
        self.env = {k:v for k,v in env.items() if k not in {'nodes','boxes','template_node'}}

def get_config(path: str) -> dict:
    with open(path, 'r') as file:
        config = yaml.safe_load(file)
    return config

def get_env(config: dict) -> Env:
    return Env(config["env"])




if __name__ == "__main__":
    config = get_config('./box.yaml')
    print(config['env'])
