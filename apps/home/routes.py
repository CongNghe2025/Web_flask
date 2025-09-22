# -*- encoding: utf-8 -*-

import json
import os
from operator import and_

import requests
from apps.home import blueprint
from flask import Response, render_template, request, jsonify ,redirect ,url_for, make_response, session
from flask_login import login_required
from jinja2 import TemplateNotFound

from flask_socketio import emit
from sqlalchemy.sql import func ,desc
from apps import db
import pandas as pd
from apps.events import client
from datetime import datetime, timedelta
from apps.home.model import Eco_park_long_an, Ct20_hd222025
from apps.authentication.models import Users

UPLOAD_FOLDER = "/home/mhv/Downloads"
##################---------TOPIC điều khiển mô hình ECO_PARK thực tế----------------###################
ECO_PARK_LONG_AN_TOPIC_ONE = 'CT04-HD042025/192.168.100.101/request/one'
ECO_PARK_LONG_AN_TOPIC_ALL = 'CT04-HD042025/192.168.100.101/request/all'
ECO_PARK_LONG_AN_TOPIC_EFF = 'CT04-HD042025/192.168.100.101/request/eff'
ECO_PARK_LONG_AN_TOPIC_CHECK_CONNECTION = 'CT04-HD042025/192.168.100.101/controller_connected'
##################---------TOPIC điều khiển mô hình ECO_PARK giả lập----------------###################
ECO_PARK_TOPIC_ONE = 'ecopark/192.168.100.101/request/one'
ECO_PARK_TOPIC_ALL = 'ecopark/192.168.100.101/request/all'
ECO_PARK_TOPIC_EFF = 'ecopark/192.168.100.101/request/eff'
##################---------TOPIC điều khiển mô hình CT20-HD222025-----------------###################
CT20_HD222025_TOPIC_ONE = 'CT20_HD222025/192.168.100.101/request/one'
CT20_HD222025_TOPIC_ALL = 'CT20_HD222025/192.168.100.101/request/all'
CT20_HD222025_TOPIC_EFF = 'CT20_HD222025/192.168.100.101/request/eff'

MODEL_MAP = {
    'CT20_HD222025': Ct20_hd222025,
    # ... thêm các prefix khác và Model tương ứng
}

def publish(channels, topic, value, rs_value=None):
    # import json cần phải ở cấp độ global hoặc ở đây
    payload = {
        "channels": channels,
        "value": value # <--- Dùng giá trị 'value' truyền vào
    }
    if rs_value is not None:
        payload["rs"] = rs_value
    client.publish(topic, json.dumps(payload))

@blueprint.route('/index', methods=['GET'])
@login_required

def index():
    return render_template('home/index.html', segment='index') 

# @blueprint.route('/edit_condition/<int:id>')
# def render_condition(id):
#     return render_template('home/edit_condition.html', id=id)


@blueprint.route('/<path:template>')
@login_required
def route_template(template):

    try:

        if not template.endswith('.html'):
            template += '.html'
        # Detect the current page
        segment = get_segment(request)
        

        # Serve the file (if exists) from app/templates/home/FILE.html
        return render_template("home/" + template, segment=segment)

    except TemplateNotFound:
        return render_template('home/page-404.html'), 404

    except:
        return render_template('home/page-500.html'), 500

# Helper - Extract current page name from request
def get_segment(request):
    try:
        segment = request.path.split('/')[-1]
        if segment == '':
            segment = 'index'
        return segment
    except:
        return None


# API nhận topic và gửi dữ liệu lên MQTT
@blueprint.route('/post_mqtt', methods=['POST'])
# @login_required
def post_mqtt():
    try:
        data = request.get_json()
        topic = data.get('topic')
        data.pop('topic', None)   # Loại bỏ topic khỏi dữ liệu để gửi phần còn lại
        
        json_payload = json.dumps(data)
        client.publish(topic, payload=(json_payload))

        return jsonify({'message': f"Successfully sent data to {topic}."}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@blueprint.route('/post_eff', methods=['POST'])
# @login_required
def post_eff():
    try:
        data = request.get_json()
        json_payload = json.dumps(data)
        client.publish("CT04-HD042025/192.168.100.101/request/eff", payload=(json_payload))

        return jsonify({'message': f"Successfully sent data"}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# API nhận topic và gửi dữ liệu lên MQTT
@blueprint.route('/post_mqtt_one', methods=['POST'])
# @login_required
def post_mqtt_one():
    try:
        data = request.get_json()
        json_payload = json.dumps(data)
        client.publish("CT04-HD042025/192.168.100.101/request/one", payload=(json_payload))

        return jsonify({'message': f"Successfully sent data"}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

            
@blueprint.route("/send_midi", methods=["POST"])
def send_midi():
    try:
        data = request.get_json()
        channel = int(data["channel"]) - 1  # MIDI Channel từ 1-16 -> 0-15
        note = int(data["note"])
        velocity = int(data["velocity"])
        
        midi_code = [144 + channel, note, velocity]  # 144 = Note ON trên Channel 1
        client.publish("modelx/192.168.90.55/midi", ",".join(map(str, midi_code)))

        return jsonify({"message": "MIDI Sent", "data": midi_code}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

#################                                            #################
##################---------API DU AN ECO PARK LONG AN -------################
#################                                            #################

#Add dữ liệu ECO PARK LONG AN từ file excel đã có sẵn
@blueprint.route('/CT04-HD042025/192.168.100.101/add_data', methods=['POST'])  
def add_data_ecopark():
    filename = 'db.xlsx'
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    if not os.path.exists(filepath):
        return jsonify({"error": f"File {filename} not found"}), 404

    try:
        data_frame = pd.read_excel(filepath, sheet_name='DATABASE')
        data_list = data_frame.to_dict(orient='records')

        created_records = []
        updated_records = []
        errors = []

        for index, record in enumerate(data_list):
            try:
                id = record.get('id')
                if not id:
                    raise Exception("Missing ID")

                # Lấy các trường từ Excel
                fields = {
                    'building_name': record.get('building_name', ''),
                    'building_type': record.get('building_type', ''),
                    'amenity_type': record.get('amenity_type', ''),
                    'zone_name': record.get('zone_name', ''),
                    'amenity': record.get('amenity', ''),
                    'zone': record.get('zone', ''),
                    'direction': record.get('direction', ''),
                    'bedroom': record.get('bedroom', ''),
                    'price': record.get('price', ''),
                    'status': record.get('status', ''),
                }

                # Tìm bản ghi đã tồn tại
                existing = Eco_park_long_an.query.filter_by(id=id).first()

                if existing:
                    # Cập nhật các trường
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    existing.save()
                    updated_records.append(id)
                else:
                    # Tạo mới
                    new_record = Eco_park_long_an(id=id, **fields)
                    new_record.save()
                    created_records.append(id)

            except Exception as e:
                errors.append({"index": index, "error": str(e)})

        return jsonify({
            "created_ids": created_records,
            "updated_ids": updated_records,
            "errors": errors
        }), 200 if not errors else 207

    except Exception as e:
        return jsonify({"error": f"Failed to process file: {str(e)}"}), 500
    


# Helper function to publish MQTT
def publish_mqtt(channels):
    payload = {
        "channels": channels,
        "value": 1
    }
    import json
    client.publish(ECO_PARK_LONG_AN_TOPIC_ONE, json.dumps(payload))

# Generic function to handle dynamic filters
def search_and_publish(field_value_map):
    try:
        conditions = []
        for field, value in field_value_map.items():
            column_attr = getattr(Eco_park_long_an, field)

            if field == "zone_name":
                # Match any zone_name that starts with "Phân khu 8"
                conditions.append(column_attr.ilike(f"%{value}%"))
            else:
                conditions.append(column_attr == value)

        results = Eco_park_long_an.query.filter(*conditions).all()

        channels = [record.id for record in results]

        if channels:
            publish_mqtt(channels)

        data = [{
            "id": r.id,
            "building_name": r.building_name,
            "building_type": r.building_type,
            "amenity_type": r.amenity_type,
            "zone_name": r.zone_name,
            "zone": r.zone,
            "amenity": r.amenity
        } for r in results]

        return jsonify({"records": data, "count": len(data)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@blueprint.route('/CT04-HD042025/192.168.100.101/amenity/<amenity>', methods=['GET'])
def search_by_amenity(amenity):
    return search_and_publish({'amenity': amenity})

@blueprint.route('/CT04-HD042025/192.168.100.101/amenity/<amenity>/<amenity_type>', methods=['GET'])
def search_by_amenity_and_type(amenity, amenity_type):
    return search_and_publish({'amenity': amenity, 'amenity_type': amenity_type})


@blueprint.route('/CT04-HD042025/192.168.100.101/zone/<zone>', methods=['GET'])
def search_by_zone(zone):
    return search_and_publish({'zone': zone})

@blueprint.route('/CT04-HD042025/192.168.100.101/zone/<zone>/<zone_name>', methods=['GET'])
def search_by_zone_and_name(zone, zone_name):
    return search_and_publish({'zone': zone, 'zone_name': zone_name})

@blueprint.route('/CT04-HD042025/192.168.100.101/zone/<zone>/<zone_name>/<building_type>', methods=['GET'])
def search_by_zone_name_type(zone, zone_name, building_type):
    return search_and_publish({'zone': zone, 'zone_name': zone_name, 'building_type': building_type})

@blueprint.route('/CT04-HD042025/192.168.100.101/zone/<zone>/<zone_name>/<building_type>/<building_name>', methods=['GET'])
def search_by_full_path(zone, zone_name, building_type, building_name):
    return search_and_publish({
        'zone': zone,
        'zone_name': zone_name,
        'building_type': building_type,
        'building_name': building_name
    })  

@blueprint.route("/CT04-HD042025/192.168.100.101/eff/<int:id_eff>/<int:value>", methods=["POST"]) 
def publish_eff(id_eff, value):
    try:
        payload = {
            "id": id_eff,
            "value": value
        }

        client.publish(ECO_PARK_LONG_AN_TOPIC_EFF, json.dumps(payload))

        return jsonify({
            "status": "success",
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
@blueprint.route("/CT04-HD042025/192.168.100.101/all/<int:value>", methods=["POST"]) 
def publish_all(value):
    try:
        payload = {
            "value": value
        }

        client.publish(ECO_PARK_LONG_AN_TOPIC_ALL, json.dumps(payload))

        return jsonify({
            "status": "success",
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
#################                                                                           #################
##################---------API CỦA WEBSITE MẪU SỬ DỤNG DATABASE CỦA ECO PARK LONG AN -------################
#################                                                                           #################
def get_clean_distinct_values(column, is_numeric=False):
    invalid_strings = ["", " ", "NaN", "nan", "null", "None", "N", "-", "--"]

    query = db.session.query(column).distinct()

    if is_numeric:
        query = query.filter(column.isnot(None))
    else:
        # Loại bỏ None và các chuỗi rác ngay trong SQL
        conditions = [column.isnot(None)]
        for inval in invalid_strings:
            conditions.append(func.trim(func.lower(column)) != inval.lower())
        query = query.filter(*conditions)

    results = query.all()
    return sorted([val for (val,) in results])

@blueprint.route('ecopark/192.168.100.101/filter_type', methods=['GET']) 
def get_filters():
    filters = {
        "status": get_clean_distinct_values( Eco_park_long_an.status),
        "price": get_clean_distinct_values(Eco_park_long_an.price, is_numeric=True),
        "bedroom": get_clean_distinct_values( Eco_park_long_an.bedroom, is_numeric=True),
        "direction": get_clean_distinct_values( Eco_park_long_an.direction),
        "building_type": get_clean_distinct_values( Eco_park_long_an.building_type),
        "zone_name": get_clean_distinct_values( Eco_park_long_an.zone_name),
        "amenity_type": get_clean_distinct_values( Eco_park_long_an.amenity_type),
    }
    return jsonify(filters)

@blueprint.route('ecopark/192.168.100.101/filter', methods=['POST']) 
def ecopark_filter_properties_by_json():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request must be JSON"}), 400

    query = Eco_park_long_an.query
    # Xử lý min_price và max_price trước
    min_price = data.get("min_price")
    max_price = data.get("max_price")

    try:
        if min_price is not None:
            min_price = int(min_price)
            query = query.filter(Eco_park_long_an.price >= min_price)

        if max_price is not None:
            max_price = int(max_price)
            query = query.filter(Eco_park_long_an.price <= max_price)
    except ValueError:
        return jsonify({"error": "min_price and max_price must be numeric"}), 400

    # Tránh lọc price 2 lần nếu đã lọc bằng min_price/max_price
    skip_price_filter = "min_price" in data or "max_price" in data

    # Duyệt toàn bộ key trong payload và lọc nếu có
    for key, value in data.items():
        if not value or key in ["min_price", "max_price"]:
            continue

        if key == 'price' and not skip_price_filter:
            if isinstance(value, str) and '-' in value:
                try:
                    min_val, max_val = map(int, value.split('-'))
                    query = query.filter(
                        Eco_park_long_an.price >= min_val,
                        Eco_park_long_an.price <= max_val
                    )
                except ValueError:
                    return jsonify({"error": "Invalid price range format. Use 'min-max'"}), 400
            else:
                try:
                    query = query.filter(Eco_park_long_an.price == int(value))
                except ValueError:
                    return jsonify({"error": "Price must be numeric"}), 400

        elif key == 'bedroom':
            query = query.filter(Eco_park_long_an.bedroom == str(value))

        else:
            try:
                query = query.filter(getattr(Eco_park_long_an, key) == str(value))
            except AttributeError:
                return jsonify({"error": f"Invalid filter field: {key}"}), 400

    results = query.all()

    # Trả JSON, không cần to_dict
    result_json = [
        {
            "id": r.id,
            "building_name": r.building_name,
            "zone_name": r.zone_name,
            "building_type": r.building_type,
            "direction": r.direction,
            "amenity_type": r.amenity_type,
            "bedroom": r.bedroom,
            "price": r.price,
            "status": r.status
        }
        for r in results
    ]
    channels = [record.id for record in results]
    if channels:
        ecopark_publish_mqtt(channels)

    return jsonify(result_json)

# Helper function to publish MQTT
def ecopark_publish_mqtt(channels):
    payload = {
        "channels": channels,
        "value": 1
    }
    import json
    client.publish(ECO_PARK_TOPIC_ONE, json.dumps(payload))

# Generic function to handle dynamic filters
def ecopark_search_and_publish(field_value_map):
    try:
        conditions = []
        for field, value in field_value_map.items():
            column_attr = getattr(Eco_park_long_an, field)

            if field == "zone_name":
                # Match any zone_name that starts with "Phân khu 8"
                conditions.append(column_attr.ilike(f"%{value}%"))
            else:
                conditions.append(column_attr == value)

        results = Eco_park_long_an.query.filter(*conditions).all()

        channels = [record.id for record in results]

        if channels:
            ecopark_publish_mqtt(channels)

        data = [{
            "id": r.id,
            "building_name": r.building_name,
            "building_type": r.building_type,
            "amenity_type": r.amenity_type,
            "zone_name": r.zone_name,
            "zone": r.zone,
            "amenity": r.amenity,
            "bedroom": r.bedroom,
            "direction": r.direction,
            "price": r.price,
            "status": r.status
        } for r in results]

        return jsonify({"records": data, "count": len(data)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@blueprint.route('/ecopark/192.168.100.101/amenity/<amenity>', methods=['GET'])
def ecopark_search_by_amenity(amenity):
    return search_and_publish({'amenity': amenity})

@blueprint.route('/ecopark/192.168.100.101/amenity/<amenity>/<amenity_type>', methods=['GET'])
def ecopark_search_by_amenity_and_type(amenity, amenity_type):
    return search_and_publish({'amenity': amenity, 'amenity_type': amenity_type})


@blueprint.route('/ecopark/192.168.100.101/zone/<zone>', methods=['GET'])
def ecopark_search_by_zone(zone):
    return search_and_publish({'zone': zone})

@blueprint.route('/ecopark/192.168.100.101/zone/<zone>/<zone_name>', methods=['GET'])
def ecopark_search_by_zone_and_name(zone, zone_name):
    return search_and_publish({'zone': zone, 'zone_name': zone_name})

@blueprint.route('/ecopark/192.168.100.101/zone/<zone>/<zone_name>/<building_type>', methods=['GET'])
def ecopark_search_by_zone_name_type(zone, zone_name, building_type):
    return search_and_publish({'zone': zone, 'zone_name': zone_name, 'building_type': building_type})

@blueprint.route('/ecopark/192.168.100.101/zone/<zone>/<zone_name>/<building_type>/<building_name>', methods=['GET'])
def ecopark_search_by_full_path(zone, zone_name, building_type, building_name):
    return search_and_publish({
        'zone': zone,
        'zone_name': zone_name,
        'building_type': building_type,
        'building_name': building_name
    })  

@blueprint.route("/ecopark/192.168.100.101/eff/<int:id_eff>/<int:value>", methods=["POST"]) 
def ecopark_publish_eff(id_eff, value):
    try:
        payload = {
            "id": id_eff,
            "value": value
        }

        client.publish(ECO_PARK_TOPIC_EFF, json.dumps(payload))

        return jsonify({
            "status": "success",
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
@blueprint.route("/ecopark/192.168.100.101/all/<int:value>", methods=["POST"]) 
def ecopark_publish_all(value):
    try:
        payload = {
            "value": value
        }

        client.publish(ECO_PARK_TOPIC_ALL, json.dumps(payload))

        return jsonify({
            "status": "success",
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
#################                                                                           #################
##################---------API ĐIỀU KHIỂN CỦA CT20-HD222025 -------################
#################

@blueprint.route('/<string:prefix>/all/<int:value>', methods=['POST'])
def get_all_records_dynamic(prefix, value):
    try:
        DynamicModel = MODEL_MAP.get(prefix)
        if not DynamicModel:
            return jsonify({'error': f'Không tìm thấy model cho prefix: {prefix}'}), 404
        all_records = db.session.query(DynamicModel).all()
        result = []
        ids = []
        for record in all_records:
            record_data = {}
            for column in record.__table__.columns.keys():
                record_data[column] = getattr(record, column)
            result.append(record_data)
            ids.append(record.id)
            
        topic_one = build_dynamic_topic(prefix, "one")
        publish(ids, topic_one, value)       
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': f'Đã xảy ra lỗi: {str(e)}'}), 500

@blueprint.route('/CT20-HD222025/upload_db', methods=['POST'])
def upload_db_CT20_HD222025():
    if 'excel_file' not in request.files:
        return jsonify({'error': 'Không tìm thấy file nào được tải lên'}), 400

    file = request.files['excel_file']
    sheet_name = 'DATABASE'
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Chỉ chấp nhận file Excel (.xlsx, .xls)'}), 400

    try:
        # Chọn engine phù hợp
        if file.filename.endswith('.xlsx'):
            df = pd.read_excel(file, sheet_name=sheet_name, engine='openpyxl')
        else:
            df = pd.read_excel(file, sheet_name=sheet_name, engine='xlrd')

        updated_count = 0
        created_count = 0

        for _, row in df.iterrows():
            row_data = row.to_dict()
            record_id = row_data.get('id')

            # Bỏ qua các bản ghi không có id
            if not record_id or pd.isna(record_id):
                continue

            # Chuyển NaN -> None để tránh lỗi khi insert
            clean_data = {k: (None if pd.isna(v) else v) for k, v in row_data.items()}

            # Tìm bản ghi theo ID
            record = db.session.query(Ct20_hd222025).filter_by(id=int(record_id)).first()

            if record:
                # Cập nhật
                for key, value in clean_data.items():
                    if key != 'id' and value is not None and hasattr(record, key):
                        setattr(record, key, value)
                updated_count += 1
            else:
                # Tạo mới
                new_record = Ct20_hd222025(**clean_data)
                db.session.add(new_record)
                created_count += 1

        db.session.commit()

        return jsonify({
            'message': 'Cập nhật dữ liệu từ Excel thành công!',
            'created': created_count,
            'updated': updated_count
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()  # In lỗi chi tiết ra console
        db.session.rollback()
        return jsonify({'error': f'Đã xảy ra lỗi: {str(e)}'}), 500

@blueprint.route('/<string:prefix>/filter/<int:gt>', methods=['GET'])
def filter_data_dynamic(prefix, gt):
    try:
        DynamicModel = MODEL_MAP.get(prefix)
        if not DynamicModel:
            return jsonify({'error': f'Không tìm thấy model cho prefix: {prefix}'}), 404
        
        rs_param = request.args.get('rs', type=int)
        filters = request.args
        search_conditions = []
        
        for key, value in filters.items(multi=True):
            if hasattr(DynamicModel, key) and key != 'rs': # Bỏ qua 'rs' trong phần lọc DB
                values = request.args.getlist(key)
                
                if len(values) > 1:
                    search_conditions.append(getattr(DynamicModel, key).in_(values))
                elif values:
                    search_conditions.append(getattr(DynamicModel, key) == values[0])

        results = db.session.query(DynamicModel).filter(*search_conditions).all()
        response_data = []
        ids = []
        for record in results:
            record_data = {}
            for column in record.__table__.columns.keys():
                record_data[column] = getattr(record, column)

            response_data.append(record_data)
            ids.append(record.id)
            
        dynamic_topic = build_dynamic_topic(prefix, "one")
        publish(ids, dynamic_topic, gt, rs_value=rs_param) 
        return jsonify(response_data), 200

    except Exception as e:
        return jsonify({'error': f'Đã xảy ra lỗi: {str(e)}'}), 500
    
def build_dynamic_topic(prefix, sub_topic):
    """
    Hàm tạo topic MQTT dựa trên prefix động từ URL.
    
    Ví dụ:
    prefix = 'CT04-HD042025'
    sub_topic = 'request/eff'
    Kết quả: 'CT04-HD042025/192.168.100.101/request/eff'
    """
    # Bạn có thể giữ IP cố định hoặc cũng làm nó động
    return f"{prefix}/192.168.100.101/request/{sub_topic}"

# API đã sửa: chấp nhận tham số dynamic 'prefix'
@blueprint.route("/<string:prefix>/eff/<int:id_eff>/<int:value>", methods=["POST"])
def publish_eff_dynamic(prefix, id_eff, value):
    try:
        # 1. Xây dựng Topic dynamic
        topic_eff = build_dynamic_topic(prefix, "eff")
        payload = {
            "id": id_eff,
            "value": value
        }

        # 3. Publish lên Topic dynamic
        client.publish(topic_eff, json.dumps(payload))

        return jsonify({
            "status": "success",
            "topic": topic_eff, # Trả về topic để dễ debug
            "payload": payload
        }), 200

    except Exception as e:
        # Nếu publish bị lỗi (ví dụ: client chưa kết nối)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    