# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os

from flask import Flask ,current_app
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from importlib import import_module

from apps.events import socketio, events_init
from apscheduler.schedulers.background import BackgroundScheduler
from flask_cors import CORS 

db = SQLAlchemy()
login_manager = LoginManager()


def register_extensions(app):

    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)


def register_blueprints(app):
    for module_name in ('authentication', 'home'):
        module = import_module('apps.{}.routes'.format(module_name))
        app.register_blueprint(module.blueprint)


def configure_database(app):

    @app.before_first_request
    def initialize_database():
        try:
            db.create_all()
        except Exception as e:

            print('> Error: DBMS Exception: ' + str(e) )

            # fallback to SQLite
            basedir = os.path.abspath(os.path.dirname(__file__))
            app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'db.sqlite3')

            print('> Fallback to SQLite ')
            db.create_all()

    @app.teardown_request
    def shutdown_session(exception=None):
        db.session.remove()

    #gọi hàm thực hiện lịch và kiểm tra esp còn kết nối không
    # register_scheduler_job(app)
    # check(app)

# Thêm hàm đăng ký công việc lên lịch
def register_scheduler_job(app):
    from .rule import scheduler ,check_conditions 
    scheduler.add_job(check_conditions, 'interval', seconds=5)
    # Bắt đầu lịch
    scheduler.start()
# Thêm hàm đăng ký công việc kiểm tra connect
def check(app):
    from .events import scheduler ,check_connect
    scheduler.add_job(check_connect, 'interval', seconds= 10)
    scheduler.start()

broker = "scalemodelvn.com"    # Địa chỉ broker và đường dẫn đến file chứng chỉ CA
ca_cert_file = "/home/mhv/Downloads/WEB-main/emqxsl_ca.pem"  # Đường dẫn đến file chứng chỉ CA

def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)
    register_extensions(app)
    register_blueprints(app)
    configure_database(app)
    socketio.init_app(app)
    CORS (app)
    events_init(broker, ca_cert_file )
    return app
