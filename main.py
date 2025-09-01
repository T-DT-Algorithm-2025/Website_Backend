import utils
import core
import modules


if __name__ == '__main__':
    from core.global_params import flask_app, global_config
    flask_app.run('0.0.0.0', global_config['flask_port'])
