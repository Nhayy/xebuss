import requests
import time
import math
import json
import os
import jwt
import base64
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
import random

# =====================
# CẤU HÌNH - SỬ DỤNG ENVIRONMENT VARIABLES
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8045921530:AAFP7i_9yS3EYUDoIqWP3hsVOeutARFt8RI")
SCHEDULE_FILE = "schedule_config.json"
ADMIN_IDS = [7073749415]

if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("⚠️ CẢNH BÁO: Vui lòng set BOT_TOKEN trong Secrets!")
    print("💡 Vào Secrets tab và thêm BOT_TOKEN = your_actual_token")

# Cấu hình BOX
BOX_CONFIGS = {
    "box1": {
        "chat_id": "7073749415",
        "name": "Trạm 1",
        "buon_don_stations": ["Trạm Ngã 4 Buôn Đôn"],
        "huyen_stations": ["Trạm Chợ Huyện"]
    }
}

# =====================
# CẤU HÌNH API VÀ AUTO-REFRESH TOKEN
# =====================
API_URL = "http://apigateway.vietnamcnn.vn/api/v2/vehicleonline/getlistvehicleonline"
LOGIN_URL = "http://apigateway.vietnamcnn.vn/api/v1/authentication/validatelogin"

API_USERNAME = os.getenv("API_USERNAME", "htxcumill")
API_PASSWORD = os.getenv("API_PASSWORD", "12341234")

API_TOKEN = os.getenv("API_TOKEN", "")
TOKEN_REFRESH_BUFFER = 1800

def decode_jwt_payload(token):
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload
    except Exception as e:
        print(f"❌ Lỗi decode JWT: {e}")
        return None

def is_token_expired(token, buffer_seconds=TOKEN_REFRESH_BUFFER):
    if not token:
        return True
    try:
        payload = decode_jwt_payload(token)
        if not payload or 'exp' not in payload:
            return True
        exp_timestamp = payload['exp']
        current_timestamp = time.time()
        return current_timestamp >= (exp_timestamp - buffer_seconds)
    except Exception as e:
        print(f"❌ Lỗi kiểm tra token: {e}")
        return True

def login_and_get_token():
    global API_TOKEN
    try:
        print("🔑 Đang đăng nhập lấy token mới...")
        login_payload = {
            "userName": API_USERNAME,
            "password": API_PASSWORD,
            "appType": 4
        }
        headers = {
            "Content-Type": "application/json; charset=utf-8"
        }
        
        response = requests.post(
            "http://apigateway.vietnamcnn.vn/api/v1/authentication/login",
            json=login_payload, 
            headers=headers, 
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            data = result.get("Data") or result.get("data")
            
            new_token = None
            if isinstance(data, dict):
                if "11" in data and isinstance(data["11"], str) and data["11"].startswith("eyJ"):
                    new_token = data["11"]
                else:
                    for key, value in data.items():
                        if isinstance(value, str) and value.startswith("eyJ"):
                            new_token = value
                            break
                if not new_token:
                    new_token = data.get("Token") or data.get("token") or data.get("accessToken")
            elif isinstance(data, str) and data.startswith("eyJ"):
                new_token = data
            
            if not new_token:
                new_token = result.get("Token") or result.get("token")
            
            if new_token:
                API_TOKEN = new_token
                update_headers()
                payload = decode_jwt_payload(new_token)
                if payload and 'exp' in payload:
                    exp_time = datetime.fromtimestamp(payload['exp'], tz=pytz.timezone('Asia/Ho_Chi_Minh'))
                    print(f"✅ Lấy token mới thành công! Hết hạn: {exp_time.strftime('%d/%m/%Y %H:%M:%S')}")
                else:
                    print("✅ Lấy token mới thành công!")
                return True
            else:
                print(f"❌ Không tìm thấy token trong response")
        else:
            print(f"❌ Login error HTTP {response.status_code}")
        return False
    except Exception as e:
        print(f"❌ Lỗi đăng nhập: {e}")
        return False

def ensure_valid_token():
    global API_TOKEN
    if is_token_expired(API_TOKEN):
        print("⏰ Token hết hạn hoặc sắp hết hạn, đang refresh...")
        return login_and_get_token()
    return True

def update_headers():
    global HEADERS
    HEADERS = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}" if API_TOKEN else "",
    "Content-Type": "application/json; charset=utf-8"
}

PAYLOAD = {
    "userID": "890e5bf6-d7d7-4b5d-9f13-89ae56e93d63",
    "companyID": 87575,
    "xnCode": 46705,
    "userType": 4,
    "companyType": 3,
    "appID": 4,
    "languageID": 1
}

# =====================
# TRẠM XE VÀ DỮ LIỆU
# =====================
stations = {
    "Trạm Ngã 4 Buôn Đôn": (12.89607, 107.79033),
    "Trạm Chợ Huyện": (12.80411, 107.90301)
}

# Bán kính phát hiện xe (km) - chính xác hơn
DETECTION_RADIUS_NEAR = 0.5   # 500m - rất gần
DETECTION_RADIUS_FAR = 1.5    # 1.5km - đang đến

# Thời gian giữa các lần thông báo (giây)
NOTIFY_DELAYS = [0, 20, 30]  # Lần 1 ngay, lần 2 sau 20s, lần 3 sau 30s nữa

# Tracking thông báo theo từng xe
pending_notifications = {}  # {key: {'count': 0, 'next_time': timestamp, 'data': {...}}}

# Dữ liệu cache với giới hạn bộ nhớ
MAX_HISTORY_POINTS = 20  # Giảm từ 50 xuống 20
MAX_VEHICLES = 100       # Giới hạn số xe theo dõi
MAX_NOTIFICATIONS = 500  # Giới hạn thông báo cache

vehicle_history = defaultdict(list)
user_favorites = {}
daily_stats = defaultdict(int)
notified = {}
last_seen_vehicles = {}
pattern_data = defaultdict(list)
last_update_id = 0

# Rate limiting
last_api_call = 0
api_call_interval = 5  # seconds
last_telegram_call = {}

# Theo dõi xe mất tín hiệu
vehicle_signal_status = {}  # {plate: {'last_moving_time': datetime, 'last_speed': float, 'notified': bool, 'last_notify_time': datetime}}
SIGNAL_LOSS_THRESHOLD = 300  # 5 phút = 300 giây

# Danh sách lý do xe dừng/mất tín hiệu
SIGNAL_LOSS_REASONS = [
    "Xe đang dừng đón/trả khách",
    "Xe đang chờ đèn đỏ kéo dài",
    "Xe bị kẹt xe, ùn tắc giao thông",
    "Tài xế dừng nghỉ ngơi",
    "Xe gặp sự cố kỹ thuật nhẹ",
    "Vùng phủ sóng GPS yếu",
    "Thiết bị GPS tạm ngắt kết nối",
    "Xe đang đổ xăng/nhiên liệu",
    "Tài xế dừng giải quyết việc cá nhân",
    "Xe dừng tại trạm xe buýt",
    "Đường đang thi công/sửa chữa",
    "Xe chờ khách tại bến",
    "Thời tiết xấu, tạm dừng",
    "Kiểm tra an toàn phương tiện",
    "Đang chờ hướng dẫn từ bến xe"
]

# =====================
# HỆ THỐNG QUẢN LÝ LỊCH LINH HOẠT
# =====================
def load_custom_schedule():
    """Load lịch tùy chỉnh từ file JSON"""
    try:
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Lỗi load schedule: {e}")
    return {"custom_slots": [], "removed_slots": []}

def save_custom_schedule(schedule_data):
    """Lưu lịch tùy chỉnh vào file JSON"""
    try:
        with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
            json.dump(schedule_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Lỗi save schedule: {e}")
        return False

def add_schedule_slot(start_time, end_time, direction="to_huyen", weekdays=None):
    """Thêm khung giờ mới vào lịch"""
    schedule = load_custom_schedule()
    new_slot = {
        "start": start_time,
        "end": end_time,
        "direction": direction,
        "weekdays": weekdays or [0, 1, 2, 3, 4, 5],  # Mặc định thứ 2-7
        "created_at": datetime.now().isoformat()
    }
    schedule["custom_slots"].append(new_slot)
    return save_custom_schedule(schedule)

def remove_schedule_time(time_str):
    """Xóa khung giờ có start time tương ứng"""
    schedule = load_custom_schedule()
    original_count = len(schedule["custom_slots"])
    schedule["custom_slots"] = [
        slot for slot in schedule["custom_slots"] 
        if slot["start"] != time_str
    ]
    # Thêm vào danh sách đã xóa để bỏ qua lịch mặc định
    if time_str not in schedule["removed_slots"]:
        schedule["removed_slots"].append(time_str)
    
    if len(schedule["custom_slots"]) < original_count or time_str not in schedule.get("removed_slots", []):
        return save_custom_schedule(schedule)
    return True

def get_custom_schedule_slots():
    """Lấy danh sách khung giờ tùy chỉnh"""
    return load_custom_schedule()

def is_admin(user_id):
    """Kiểm tra user có phải admin không"""
    return user_id in ADMIN_IDS

# =====================
# HÀM TIỆN ÍCH CỐT LÕI (CẢI THIỆN)
# =====================
def is_valid_coordinate(lat, lon):
    """Kiểm tra tọa độ hợp lệ cho Việt Nam"""
    try:
        lat, lon = float(lat), float(lon)
        # Vietnam bounds với buffer
        return (8.0 <= lat <= 23.5) and (102.0 <= lon <= 110.0)
    except (TypeError, ValueError):
        return False

def is_valid_plate(plate):
    """Kiểm tra biển số xe hợp lệ"""
    if not plate or not isinstance(plate, str):
        return False
    plate = plate.strip()
    return len(plate) >= 3 and plate != "Unknown" and not plate.isspace()

def haversine(lat1, lon1, lat2, lon2):
    """Tính khoảng cách với error handling"""
    try:
        R = 6371  # km
        phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
        dphi = math.radians(float(lat2) - float(lat1))
        dlambda = math.radians(float(lon2) - float(lon1))
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    except (TypeError, ValueError, OverflowError):
        return float('inf')

def calculate_speed(plate, current_lat, current_lon, current_time):
    """Tính tốc độ với validation cải thiện"""
    try:
        if plate not in vehicle_history or len(vehicle_history[plate]) == 0:
            return 0
        
        last_record = vehicle_history[plate][-1]
        last_lat, last_lon, last_time = last_record
        
        distance = haversine(last_lat, last_lon, current_lat, current_lon)
        if distance == float('inf'):
            return 0
            
        time_diff = (current_time - last_time).total_seconds() / 3600  # hours
        
        if time_diff > 0 and time_diff < 1:  # Max 1 hour between points
            speed = distance / time_diff  # km/h
            return min(max(speed, 0), 120)  # 0-120 km/h range
        return 0
    except Exception as e:
        print(f"Lỗi tính tốc độ: {e}")
        return 0

def calculate_direction(lat1, lon1, lat2, lon2):
    """Tính hướng di chuyển với error handling"""
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        
        dlon = math.radians(lon2 - lon1)
        lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
        
        y = math.sin(dlon) * math.cos(lat2_rad)
        x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
        
        bearing = math.degrees(math.atan2(y, x))
        bearing = (bearing + 360) % 360
        
        directions = ["Bắc", "Đông Bắc", "Đông", "Đông Nam", "Nam", "Tây Nam", "Tây", "Tây Bắc"]
        return directions[int((bearing + 22.5) / 45) % 8]
    except (TypeError, ValueError, OverflowError):
        return "Không xác định"

def determine_bus_route(plate):
    """
    Xác định hướng xe dựa vào lịch sử di chuyển (Bắc/Nam).
    - Bắc → Nam (latitude giảm): Xe từ Ea Súp ra phố (đi lên huyện)
    - Nam → Bắc (latitude tăng): Xe từ phố về Ea Súp (về Buôn Đôn)
    
    Returns: 
        'to_huyen' - Đi lên huyện (Bắc→Nam)
        'to_buondon' - Về Buôn Đôn (Nam→Bắc)
        'unknown' - Không xác định
    """
    try:
        if plate not in vehicle_history or len(vehicle_history[plate]) < 3:
            return 'unknown'
        
        # Lấy 5 điểm gần nhất để tính xu hướng
        history = vehicle_history[plate][-5:]
        if len(history) < 3:
            return 'unknown'
        
        # Tính tổng thay đổi latitude
        total_lat_change = 0
        valid_changes = 0
        
        for i in range(1, len(history)):
            prev_lat = history[i-1][0]
            curr_lat = history[i][0]
            lat_diff = curr_lat - prev_lat
            
            # Chỉ tính nếu có thay đổi đáng kể (>0.0001 độ ~ 11m)
            if abs(lat_diff) > 0.0001:
                total_lat_change += lat_diff
                valid_changes += 1
        
        if valid_changes == 0:
            return 'unknown'
        
        avg_lat_change = total_lat_change / valid_changes
        
        # Ngưỡng: thay đổi trung bình > 0.0002 độ (~22m) mỗi lần đo
        if avg_lat_change < -0.0002:
            # Latitude giảm = đi về phía Nam = đi lên huyện (Ea Súp → phố)
            return 'to_huyen'
        elif avg_lat_change > 0.0002:
            # Latitude tăng = đi về phía Bắc = về Buôn Đôn (phố → Ea Súp)
            return 'to_buondon'
        else:
            return 'unknown'
            
    except Exception as e:
        print(f"Lỗi xác định hướng xe: {e}")
        return 'unknown'

def get_route_description(route, station_name):
    """Lấy mô tả hướng đi dựa vào route và trạm"""
    if route == 'to_huyen':
        return "🚌 Từ Ea Súp ra phố"
    elif route == 'to_buondon':
        return "🚌 Từ phố về Ea Súp"
    else:
        # Fallback dựa vào tên trạm
        if "Buôn Đôn" in station_name:
            return "🚌 Xe đang đến trạm"
        else:
            return "🚌 Xe đang đến trạm"

def get_expected_direction_by_time():
    """Xác định hướng đi dự kiến dựa vào thời gian trong ngày"""
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.now(tz).time()
    
    # Buổi sáng (5:00-12:00): Đi từ Ea Súp ra phố (lên huyện)
    if datetime.strptime("05:00", "%H:%M").time() <= now <= datetime.strptime("12:00", "%H:%M").time():
        return "to_huyen", "Huyện Ea Súp"
    # Buổi chiều (12:00-18:00): Về từ phố về Ea Súp (về Buôn Đôn)
    else:
        return "to_buondon", "Buôn Đôn"

def estimate_distance_to_destination(plate, destination):
    """Ước tính khoảng cách xe đến điểm đích"""
    try:
        if plate not in last_seen_vehicles:
            return None
        
        vehicle_data = last_seen_vehicles[plate]
        current_lat = vehicle_data['lat']
        current_lon = vehicle_data['lon']
        
        # Tọa độ đích
        destinations = {
            "Huyện Ea Súp": (12.80411, 107.90301),  # Trạm Chợ Huyện
            "Buôn Đôn": (12.89607, 107.79033)  # Trạm Ngã 4 Buôn Đôn
        }
        
        if destination in destinations:
            dest_lat, dest_lon = destinations[destination]
            distance = haversine(current_lat, current_lon, dest_lat, dest_lon)
            if distance != float('inf'):
                return round(distance, 1)
    except Exception as e:
        print(f"Lỗi estimate_distance: {e}")
    return None

def check_vehicle_signal_loss(vehicles):
    """Kiểm tra xe mất tín hiệu hoặc dừng quá lâu"""
    global vehicle_signal_status
    
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
    current_timestamp = time.time()
    alerts = []
    
    # Kiểm tra từng xe đang theo dõi
    for vehicle in vehicles:
        try:
            if not isinstance(vehicle, dict):
                continue
                
            plate = vehicle.get("9", "").strip()
            if not is_valid_plate(plate):
                continue
            
            lat = vehicle.get("2")
            lon = vehicle.get("3")
            if not is_valid_coordinate(lat, lon):
                continue
            
            lat, lon = float(lat), float(lon)
            
            # Tính tốc độ hiện tại
            current_speed = 0
            if plate in vehicle_history and len(vehicle_history[plate]) >= 2:
                last_pos = vehicle_history[plate][-1]
                prev_pos = vehicle_history[plate][-2]
                
                dist = haversine(prev_pos[0], prev_pos[1], last_pos[0], last_pos[1])
                time_diff = (last_pos[2] - prev_pos[2]).total_seconds() / 3600
                
                if time_diff > 0 and dist != float('inf'):
                    current_speed = min(dist / time_diff, 120)
            
            # Khởi tạo hoặc cập nhật trạng thái xe
            if plate not in vehicle_signal_status:
                vehicle_signal_status[plate] = {
                    'last_moving_time': current_time,
                    'last_speed': current_speed,
                    'notified': False,
                    'last_notify_time': None,
                    'last_position': (lat, lon)
                }
            
            status = vehicle_signal_status[plate]
            
            # Xe đang di chuyển (tốc độ > 3 km/h)
            if current_speed > 3:
                status['last_moving_time'] = current_time
                status['last_speed'] = current_speed
                status['notified'] = False
                status['last_position'] = (lat, lon)
            else:
                # Xe đang dừng - kiểm tra thời gian dừng
                stopped_duration = (current_time - status['last_moving_time']).total_seconds()
                
                # Nếu dừng quá 5 phút và chưa thông báo (hoặc đã quá 30 phút từ lần thông báo trước)
                should_notify = False
                if stopped_duration >= SIGNAL_LOSS_THRESHOLD:
                    if not status['notified']:
                        should_notify = True
                    elif status['last_notify_time']:
                        time_since_last_notify = (current_time - status['last_notify_time']).total_seconds()
                        if time_since_last_notify >= 1800:  # 30 phút
                            should_notify = True
                
                if should_notify:
                    # Xác định hướng đi dựa vào thời gian
                    expected_direction, destination = get_expected_direction_by_time()
                    
                    # Ước tính khoảng cách đến đích
                    distance_to_dest = estimate_distance_to_destination(plate, destination)
                    
                    # Ước tính thời gian còn lại (giả sử tốc độ trung bình 25km/h)
                    eta_text = ""
                    if distance_to_dest:
                        eta_minutes = int((distance_to_dest / 25) * 60)
                        if eta_minutes > 0:
                            eta_text = f"~{eta_minutes} phút"
                    
                    # Chọn lý do ngẫu nhiên
                    reason = random.choice(SIGNAL_LOSS_REASONS)
                    
                    # Tạo thông báo
                    stopped_minutes = int(stopped_duration / 60)
                    alert = {
                        'plate': plate,
                        'stopped_minutes': stopped_minutes,
                        'destination': destination,
                        'distance': distance_to_dest,
                        'eta': eta_text,
                        'reason': reason,
                        'position': (lat, lon)
                    }
                    alerts.append(alert)
                    
                    # Đánh dấu đã thông báo
                    status['notified'] = True
                    status['last_notify_time'] = current_time
            
        except Exception as e:
            print(f"Lỗi check signal loss: {e}")
            continue
    
    return alerts

def send_signal_loss_alerts(alerts):
    """Gửi thông báo xe mất tín hiệu"""
    for alert in alerts:
        msg = f"""⚠️ *CẢNH BÁO XE DỪNG QUÁ LÂU*

🚌 *Xe:* {alert['plate']}
⏱ *Thời gian dừng:* {alert['stopped_minutes']} phút
🎯 *Hướng đến:* {alert['destination']}"""
        
        if alert['distance']:
            msg += f"\n📏 *Còn cách:* {alert['distance']} km"
        
        if alert['eta']:
            msg += f"\n⏰ *Dự kiến:* {alert['eta']}"
        
        msg += f"\n\n❓ *Lý do có thể:* {alert['reason']}"
        
        # Gửi đến tất cả các box
        for box_config in BOX_CONFIGS.values():
            send_telegram(msg, box_config['chat_id'])

def estimate_arrival_time(plate, station_lat, station_lon):
    """Dự đoán thời gian đến trạm với validation"""
    try:
        if plate not in vehicle_history or len(vehicle_history[plate]) < 2:
            return None
        
        current_record = vehicle_history[plate][-1]
        current_lat, current_lon, current_time = current_record
        
        distance = haversine(current_lat, current_lon, station_lat, station_lon)
        if distance == float('inf') or distance > 50:  # Too far
            return None
        
        # Tính tốc độ trung bình từ tối đa 3 điểm gần nhất
        speeds = []
        history_points = min(3, len(vehicle_history[plate]))
        
        for i in range(1, history_points):
            try:
                prev_record = vehicle_history[plate][-i-1]
                curr_record = vehicle_history[plate][-i]
                
                prev_lat, prev_lon, prev_time = prev_record
                curr_lat, curr_lon, curr_time = curr_record
                
                point_distance = haversine(prev_lat, prev_lon, curr_lat, curr_lon)
                time_diff = (curr_time - prev_time).total_seconds() / 3600  # hours
                
                if 0 < time_diff <= 0.5 and 0 < point_distance <= 10:  # Reasonable bounds
                    speed = point_distance / time_diff
                    if 5 <= speed <= 80:  # Reasonable speed for buses
                        speeds.append(speed)
            except Exception:
                continue
        
        if not speeds:
            avg_speed = 25  # Default bus speed
        else:
            avg_speed = sum(speeds) / len(speeds)
        
        if avg_speed > 1:
            eta_hours = distance / avg_speed
            eta_minutes = int(eta_hours * 60)
            
            if 1 <= eta_minutes <= 60:  # 1-60 minutes range
                return eta_minutes
        
        return None
    except Exception as e:
        print(f"Lỗi tính ETA: {e}")
        return None

def get_stations_to_check(box_config):
    """Logic khung giờ theo lịch mới - hỗ trợ lịch tùy chỉnh"""
    try:
        tz = pytz.timezone("Asia/Ho_Chi_Minh")
        now_dt = datetime.now(tz)
        now = now_dt.time()
        weekday = now_dt.weekday()
        
        # Thứ 7 và Chủ nhật nghỉ
        if weekday in [5, 6]:
            day_name = "Thứ 7" if weekday == 5 else "Chủ nhật"
            return {}, f"Bot không hoạt động {day_name}"
        
        # Helper để lấy trạm Buôn Đôn
        def get_buon_don_stations():
            box_stations = {}
            for station_name in box_config["buon_don_stations"]:
                if station_name in stations:
                    box_stations[station_name] = stations[station_name]
            return box_stations
        
        # Helper để lấy trạm Huyện
        def get_huyen_stations():
            box_stations = {}
            for station_name in box_config["huyen_stations"]:
                if station_name in stations:
                    box_stations[station_name] = stations[station_name]
            return box_stations
        
        # Load lịch tùy chỉnh
        custom_schedule = load_custom_schedule()
        removed_slots = custom_schedule.get("removed_slots", [])
        
        # Kiểm tra khung giờ tùy chỉnh trước
        for slot in custom_schedule.get("custom_slots", []):
            try:
                start_time = datetime.strptime(slot["start"], "%H:%M").time()
                end_time = datetime.strptime(slot["end"], "%H:%M").time()
                
                if start_time <= now <= end_time:
                    if weekday in slot.get("weekdays", [0, 1, 2, 3, 4, 5]):
                        if slot.get("direction") == "to_huyen":
                            return get_buon_don_stations(), "Đi đến huyện (tùy chỉnh)"
                        else:
                            return get_huyen_stations(), "Đi về Buôn Đôn (tùy chỉnh)"
            except Exception:
                continue
        
        # ============ BUỔI SÁNG (Tất cả các ngày trừ CN) ============
        # 5:05-6:00: Đi từ Buôn Đôn lên Huyện
        if "05:05" not in removed_slots:
            if datetime.strptime("05:05", "%H:%M").time() <= now <= datetime.strptime("06:00", "%H:%M").time():
                return get_buon_don_stations(), "Đi đến huyện"
        
        # 10:20-10:50: Về từ Huyện về Buôn Đôn
        if "10:20" not in removed_slots:
            if datetime.strptime("10:20", "%H:%M").time() <= now <= datetime.strptime("10:50", "%H:%M").time():
                return get_huyen_stations(), "Đi về Buôn Đôn"
        
        # ============ THỨ 3-6 (Tue, Fri) - CHỈ SÁNG ============
        # weekday: 1=Tue, 4=Fri
        if weekday in [1, 4]:
            return {}, "Ngoài khung giờ (Thứ 3-6 chỉ sáng)"
        
        # ============ BUỔI CHIỀU - THỨ 2-4-5 (Mon, Wed, Thu) ============
        # weekday: 0=Mon, 2=Wed, 3=Thu
        
        # THỨ 2 (Monday - weekday 0)
        if weekday == 0:
            # 12:30-12:45: Đi lên huyện
            if "12:30" not in removed_slots:
                if datetime.strptime("12:30", "%H:%M").time() <= now <= datetime.strptime("12:45", "%H:%M").time():
                    return get_buon_don_stations(), "Đi đến huyện"
            # 15:15-16:30: Về Buôn Đôn
            if "15:15" not in removed_slots:
                if datetime.strptime("15:15", "%H:%M").time() <= now <= datetime.strptime("16:30", "%H:%M").time():
                    return get_huyen_stations(), "Đi về Buôn Đôn"
        
        # THỨ 4 (Wednesday - weekday 2)
        elif weekday == 2:
            # 12:30-12:45: Đi lên huyện
            if "12:30" not in removed_slots:
                if datetime.strptime("12:30", "%H:%M").time() <= now <= datetime.strptime("12:45", "%H:%M").time():
                    return get_buon_don_stations(), "Đi đến huyện"
            # 16:50-17:40: Về Buôn Đôn
            if "16:50" not in removed_slots:
                if datetime.strptime("16:50", "%H:%M").time() <= now <= datetime.strptime("17:40", "%H:%M").time():
                    return get_huyen_stations(), "Đi về Buôn Đôn"
        
        # THỨ 5 (Thursday - weekday 3)
        elif weekday == 3:
            # 12:30-12:45: Đi lên huyện (lần 1)
            if "12:30" not in removed_slots:
                if datetime.strptime("12:30", "%H:%M").time() <= now <= datetime.strptime("12:45", "%H:%M").time():
                    return get_buon_don_stations(), "Đi đến huyện"
            # 13:30-13:45: Đi lên huyện (lần 2 - thêm)
            if "13:30" not in removed_slots:
                if datetime.strptime("13:30", "%H:%M").time() <= now <= datetime.strptime("13:45", "%H:%M").time():
                    return get_buon_don_stations(), "Đi đến huyện (chuyến 2)"
            # 15:15-16:30: Về Buôn Đôn
            if "15:15" not in removed_slots:
                if datetime.strptime("15:15", "%H:%M").time() <= now <= datetime.strptime("16:30", "%H:%M").time():
                    return get_huyen_stations(), "Đi về Buôn Đôn"
        
        return {}, "Ngoài khung giờ"
    except Exception as e:
        print(f"Lỗi get_stations_to_check: {e}")
        return {}, "Lỗi khung giờ"

# =====================
# TELEGRAM API (CẢI THIỆN RATE LIMITING)
# =====================
def send_telegram(msg, chat_id=None, reply_to_message_id=None):
    """Gửi tin nhắn với rate limiting cải thiện"""
    global last_telegram_call
    
    if not msg or len(msg.strip()) == 0:
        return False
    
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️ Bot token chưa được cấu hình!")
        return False
        
    if len(msg) > 4096:
        msg = msg[:4093] + "..."
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    target_chats = [chat_id] if chat_id else [config["chat_id"] for config in BOX_CONFIGS.values()]
    
    success_count = 0
    for target_chat in target_chats:
        if not target_chat:
            continue
            
        # Rate limiting per chat
        now = time.time()
        chat_key = str(target_chat)
        if chat_key in last_telegram_call:
            time_since_last = now - last_telegram_call[chat_key]
            if time_since_last < 1:  # 1 second minimum between messages
                time.sleep(1 - time_since_last)
        
        last_telegram_call[chat_key] = time.time()
        
        data = {
            "chat_id": target_chat, 
            "text": msg, 
            "parse_mode": "Markdown"
        }
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        
        max_retries = 2  # Giảm từ 3 xuống 2
        for retry in range(max_retries):
            try:
                response = requests.post(url, data=data, timeout=15)  # Giảm timeout
                if response.status_code == 200:
                    success_count += 1
                    break
                elif response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    print(f"⏳ Rate limited, chờ {retry_after}s...")
                    time.sleep(min(retry_after, 5))  # Max 5s wait
                    continue
                else:
                    print(f"❌ Telegram error {response.status_code} for {target_chat}")
                    break
            except requests.exceptions.Timeout:
                print(f"⏰ Timeout sending to {target_chat}")
                if retry < max_retries - 1:
                    time.sleep(1)
            except Exception as e:
                print(f"💥 Telegram error for {target_chat}: {e}")
                break
    
    return success_count > 0

def send_telegram_to_box(msg, box_key, reply_to_message_id=None):
    """Gửi tin nhắn đến box cụ thể"""
    if box_key in BOX_CONFIGS:
        chat_id = BOX_CONFIGS[box_key]["chat_id"]
        return send_telegram(msg, chat_id, reply_to_message_id)
    return False

def get_telegram_updates():
    """Lấy tin nhắn mới từ Telegram với error handling"""
    global last_update_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 1}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            result = response.json()
            updates = result.get("result", [])
            if updates and isinstance(updates, list):
                last_update_id = updates[-1]["update_id"]
                return updates
    except Exception as e:
        print(f"Error getting updates: {e}")
    return []

# =====================
# XỬ LÝ LỆNH (GIỐNG NHƯ CŨ NHƯNG VỚI ERROR HANDLING TỐT HƠN)
# =====================
def handle_commands(updates):
    """Xử lý các lệnh từ người dùng với error handling cải thiện"""
    for update in updates:
        try:
            message = update.get("message", {})
            if not message:
                continue
                
            text = message.get("text", "")
            user_id = message.get("from", {}).get("id")
            message_id = message.get("message_id")
            user_name = message.get("from", {}).get("first_name", "Người dùng")
            chat_id = str(message.get("chat", {}).get("id", ""))
            
            # Xác định box
            current_box = None
            for box_key, config in BOX_CONFIGS.items():
                if config["chat_id"] == chat_id:
                    current_box = box_key
                    break
            
            if not current_box:
                continue
            
            # Xử lý thành viên mới/rời nhóm
            new_members = message.get("new_chat_members", [])
            for member in new_members:
                if not member.get("is_bot", True):
                    name = member.get("first_name", "Người dùng mới")
                    box_name = BOX_CONFIGS[current_box]["name"]
                    welcome_msg = f"🎉 Chào mừng *{name}* đã tham gia *{box_name}*!\n🚌 Bot sẽ thông báo khi xe buýt gần đến trạm\n💡 Gõ `/help` để xem các lệnh"
                    send_telegram(welcome_msg, chat_id)
            
            left_member = message.get("left_chat_member")
            if left_member and not left_member.get("is_bot", True):
                name = left_member.get("first_name", "Thành viên")
                goodbye_msg = f"👋 Tạm biệt *{name}*!"
                send_telegram(goodbye_msg, chat_id)
            
            # Xử lý lệnh
            if text.startswith("/"):
                command = text.split()[0].lower()
                
                if command == "/help":
                    box_name = BOX_CONFIGS[current_box]["name"]
                    box_stations = BOX_CONFIGS[current_box]["buon_don_stations"]
                    help_msg = f"""🤖 *Bot Xe Buýt - {box_name}*

📍 *Trạm chuyên biệt:* {', '.join(box_stations)}

🚌 *Lệnh chính:*
`/status` - Trạng thái bot
`/schedule` - Lịch hoạt động
`/stations` - Danh sách trạm
`/ping` - Kiểm tra bot

📊 *Thống kê:*
`/report` - Báo cáo hôm nay
`/stats` - Thống kê tuần

📍 *Trạm yêu thích:*
`/setfav [tên trạm]` - Đặt trạm yêu thích
`/myfav` - Xem trạm yêu thích
`/clearfav` - Xóa trạm yêu thích"""
                    
                    # Thêm lệnh admin nếu là admin
                    if is_admin(user_id):
                        help_msg += """

🔧 *Admin:*
`/setschedule HH:MM-HH:MM` - Thêm khung giờ
`/removetime HH:MM` - Xóa khung giờ
`/customschedule` - Xem lịch tùy chỉnh"""
                    
                    send_telegram(help_msg, chat_id, message_id)
                
                elif command == "/status":
                    box_config = BOX_CONFIGS[current_box]
                    active_stations, trip_type = get_stations_to_check(box_config)
                    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
                    
                    status_msg = f"""📊 *{box_config['name']} - Trạng thái*

⏰ *Thời gian:* {current_time.strftime('%H:%M:%S')}
🚌 *Trạng thái:* {'✅ Hoạt động' if active_stations else '❌ Ngoài giờ'}
📍 *Theo dõi:* {len(active_stations)} trạm
🎯 *Hướng:* {trip_type}
🔄 *Xe:* {len(last_seen_vehicles)}
📈 *Thông báo hôm nay:* {daily_stats[current_time.date()]}"""
                    
                    send_telegram(status_msg, chat_id, message_id)
                
                elif command == "/schedule":
                    schedule_msg = """📅 *Lịch Hoạt động*

🕐 *Thứ 3, 6 (Chỉ sáng):*
• 05:05-06:00: Buôn Đôn → Huyện
• 10:20-10:50: Huyện → Buôn Đôn

🕐 *Thứ 2 (Sáng + Chiều):*
• 05:05-06:00: Buôn Đôn → Huyện
• 10:20-10:50: Huyện → Buôn Đôn
• 12:30-12:45: Buôn Đôn → Huyện
• 15:15-16:30: Huyện → Buôn Đôn

🕐 *Thứ 4 (Sáng + Chiều):*
• 05:05-06:00: Buôn Đôn → Huyện
• 10:20-10:50: Huyện → Buôn Đôn
• 12:30-12:45: Buôn Đôn → Huyện
• 16:50-17:40: Huyện → Buôn Đôn

🕐 *Thứ 5 (Sáng + Chiều thêm chuyến):*
• 05:05-06:00: Buôn Đôn → Huyện
• 10:20-10:50: Huyện → Buôn Đôn
• 12:30-12:45: Buôn Đôn → Huyện
• 13:30-13:45: Buôn Đôn → Huyện (thêm)
• 15:15-16:30: Huyện → Buôn Đôn

🚫 *Thứ 7, Chủ nhật:* Nghỉ"""
                    send_telegram(schedule_msg, chat_id, message_id)
                
                elif command == "/stations":
                    stations_msg = "📍 *Danh sách Trạm:*\n\n"
                    for i, name in enumerate(stations.keys(), 1):
                        stations_msg += f"{i}. *{name}*\n"
                    send_telegram(stations_msg, chat_id, message_id)
                
                elif command.startswith("/setfav"):
                    parts = text.split(maxsplit=1)
                    if len(parts) > 1:
                        station_name = parts[1]
                        if any(station_name.lower() in name.lower() for name in stations.keys()):
                            if user_id not in user_favorites:
                                user_favorites[user_id] = []
                            if station_name not in user_favorites[user_id]:
                                user_favorites[user_id].append(station_name)
                                send_telegram(f"✅ Đã thêm *{station_name}* vào yêu thích!", chat_id, message_id)
                            else:
                                send_telegram(f"ℹ️ *{station_name}* đã có trong danh sách!", chat_id, message_id)
                        else:
                            send_telegram("❌ Không tìm thấy trạm. Dùng `/stations` để xem danh sách.", chat_id, message_id)
                    else:
                        send_telegram("❌ Nhập tên trạm. VD: `/setfav Bưu Điện`", chat_id, message_id)
                
                elif command == "/myfav":
                    if user_id in user_favorites and user_favorites[user_id]:
                        fav_msg = f"⭐ *Trạm yêu thích:*\n\n"
                        for i, station in enumerate(user_favorites[user_id], 1):
                            fav_msg += f"{i}. {station}\n"
                        send_telegram(fav_msg, chat_id, message_id)
                    else:
                        send_telegram("📭 Chưa có trạm yêu thích. Dùng `/setfav [tên trạm]`", chat_id, message_id)
                
                elif command == "/clearfav":
                    if user_id in user_favorites:
                        del user_favorites[user_id]
                        send_telegram(f"🗑️ Đã xóa trạm yêu thích!", chat_id, message_id)
                    else:
                        send_telegram("📭 Không có trạm yêu thích để xóa.", chat_id, message_id)
                
                elif command == "/ping":
                    ping_msg = f"🏓 Pong! ⏰ {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M:%S')}"
                    send_telegram(ping_msg, chat_id, message_id)
                
                # ===== LỆNH THỐNG KÊ =====
                elif command == "/report":
                    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
                    today = current_time.date()
                    today_count = daily_stats.get(today, 0)
                    
                    # Đếm số xe đã theo dõi
                    active_vehicles = len(last_seen_vehicles)
                    
                    report_msg = f"""📊 *BÁO CÁO HÔM NAY*
                    
📅 *Ngày:* {today.strftime('%d/%m/%Y')}
⏰ *Thời gian:* {current_time.strftime('%H:%M:%S')}

🚌 *Số xe đã theo dõi:* {active_vehicles}
📣 *Tổng thông báo:* {today_count}
📍 *Số trạm:* {len(stations)}

📈 *Chi tiết xe đang hoạt động:*"""
                    
                    if last_seen_vehicles:
                        for plate, data in list(last_seen_vehicles.items())[:10]:
                            last_time = data['time'].strftime('%H:%M')
                            report_msg += f"\n• {plate} - lần cuối: {last_time}"
                    else:
                        report_msg += "\n_Chưa có xe nào trong phiên_"
                    
                    send_telegram(report_msg, chat_id, message_id)
                
                elif command == "/stats":
                    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
                    today = current_time.date()
                    
                    stats_msg = f"""📈 *THỐNG KÊ 7 NGÀY QUA*

📅 *Đến ngày:* {today.strftime('%d/%m/%Y')}

📊 *Chi tiết theo ngày:*"""
                    
                    total_week = 0
                    day_names = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
                    
                    for i in range(6, -1, -1):
                        check_date = today - timedelta(days=i)
                        count = daily_stats.get(check_date, 0)
                        total_week += count
                        day_name = day_names[check_date.weekday()]
                        date_str = check_date.strftime('%d/%m')
                        
                        # Thanh tiến trình đơn giản
                        bar = "█" * min(count // 2, 10) if count > 0 else "░"
                        stats_msg += f"\n• *{day_name} ({date_str}):* {count} {bar}"
                    
                    stats_msg += f"""

📊 *Tổng tuần:* {total_week} thông báo
📈 *Trung bình:* {total_week // 7 if total_week else 0}/ngày"""
                    
                    send_telegram(stats_msg, chat_id, message_id)
                
                # ===== LỆNH ADMIN =====
                elif command == "/setschedule":
                    if not is_admin(user_id):
                        send_telegram("❌ Bạn không có quyền admin!", chat_id, message_id)
                    else:
                        parts = text.split()
                        if len(parts) >= 2:
                            time_range = parts[1]
                            # Parse thêm hướng nếu có
                            direction = "to_huyen"
                            if len(parts) >= 3:
                                if "huyen" in parts[2].lower() or "di" in parts[2].lower():
                                    direction = "to_huyen"
                                elif "buondon" in parts[2].lower() or "ve" in parts[2].lower():
                                    direction = "to_buondon"
                            
                            try:
                                if "-" in time_range:
                                    start_str, end_str = time_range.split("-")
                                    # Validate format
                                    datetime.strptime(start_str.strip(), "%H:%M")
                                    datetime.strptime(end_str.strip(), "%H:%M")
                                    
                                    if add_schedule_slot(start_str.strip(), end_str.strip(), direction):
                                        direction_text = "Đi huyện" if direction == "to_huyen" else "Về Buôn Đôn"
                                        send_telegram(f"✅ Đã thêm khung giờ *{start_str}-{end_str}* ({direction_text})", chat_id, message_id)
                                    else:
                                        send_telegram("❌ Lỗi khi lưu lịch!", chat_id, message_id)
                                else:
                                    send_telegram("❌ Sai format. VD: `/setschedule 12:30-12:45`", chat_id, message_id)
                            except ValueError:
                                send_telegram("❌ Sai format thời gian. VD: `/setschedule 12:30-12:45`", chat_id, message_id)
                        else:
                            send_telegram("❌ Nhập khung giờ. VD: `/setschedule 12:30-12:45`\nThêm hướng: `/setschedule 12:30-12:45 dihuyen`", chat_id, message_id)
                
                elif command == "/removetime":
                    if not is_admin(user_id):
                        send_telegram("❌ Bạn không có quyền admin!", chat_id, message_id)
                    else:
                        parts = text.split()
                        if len(parts) >= 2:
                            time_str = parts[1].strip()
                            try:
                                # Validate format
                                datetime.strptime(time_str, "%H:%M")
                                
                                if remove_schedule_time(time_str):
                                    send_telegram(f"✅ Đã xóa/tắt khung giờ bắt đầu lúc *{time_str}*", chat_id, message_id)
                                else:
                                    send_telegram("❌ Lỗi khi lưu thay đổi!", chat_id, message_id)
                            except ValueError:
                                send_telegram("❌ Sai format. VD: `/removetime 12:30`", chat_id, message_id)
                        else:
                            send_telegram("❌ Nhập thời gian. VD: `/removetime 12:30`", chat_id, message_id)
                
                elif command == "/customschedule":
                    schedule = load_custom_schedule()
                    custom_slots = schedule.get("custom_slots", [])
                    removed_slots = schedule.get("removed_slots", [])
                    
                    msg = "⚙️ *LỊCH TÙY CHỈNH*\n"
                    
                    if custom_slots:
                        msg += "\n➕ *Khung giờ đã thêm:*\n"
                        for slot in custom_slots:
                            direction_text = "→ Huyện" if slot.get("direction") == "to_huyen" else "→ Buôn Đôn"
                            msg += f"• {slot['start']}-{slot['end']} {direction_text}\n"
                    else:
                        msg += "\n_Chưa thêm khung giờ tùy chỉnh_\n"
                    
                    if removed_slots:
                        msg += "\n➖ *Khung giờ đã tắt:*\n"
                        for t in removed_slots:
                            msg += f"• Bắt đầu lúc {t}\n"
                    
                    if is_admin(user_id):
                        msg += "\n💡 *Hướng dẫn:*"
                        msg += "\n`/setschedule HH:MM-HH:MM` - Thêm"
                        msg += "\n`/removetime HH:MM` - Xóa"
                    
                    send_telegram(msg, chat_id, message_id)
                    
        except Exception as e:
            print(f"Lỗi xử lý lệnh: {e}")
            continue

# =====================
# TẠO NỘI DUNG THÔNG BÁO
# =====================
def get_greeting_message(route, notification_count):
    """Lấy lời chào dựa vào hướng đi và lần thông báo"""
    if route == 'to_huyen':
        greetings = [
            "Chúc Sếp ngày mới tốt lành, làm việc hiệu quả nhé!",
            "Sếp ơi chuẩn bị ra đón xe nào!",
            "Xe sắp đến rồi, Sếp nhớ mang đầy đủ đồ nhé!"
        ]
    else:  # to_buondon or unknown
        greetings = [
            "Chúc Sếp về nhà vui vẻ, nghỉ ngơi thật tốt!",
            "Sếp ơi xe về sắp đến rồi!",
            "Về đến nhà nhớ nghỉ ngơi nhé Sếp!"
        ]
    
    return greetings[min(notification_count, len(greetings) - 1)]

def create_notification_message(plate, station_name, dist, route, eta_text, current_time, notification_count):
    """Tạo nội dung thông báo dựa vào lần thông báo"""
    route_desc = get_route_description(route, station_name)
    greeting = get_greeting_message(route, notification_count)
    
    if notification_count == 0:
        # Lần 1: Thông báo đầy đủ
        msg = f"""🔔 *SẾP ƠI XE SẮP ĐẾN RỒI!!*

🚌 *Xe:* {plate}
📍 *Trạm:* {station_name}
📏 *Khoảng cách:* {dist:.2f} km
{route_desc}
⏱ *Dự kiến:* {eta_text}
⏰ *{current_time.strftime('%H:%M:%S')}*

💬 _{greeting}_"""
    
    elif notification_count == 1:
        # Lần 2 (sau 20s): Nhắc lại
        msg = f"""⚡ *NHẮC LẠI - XE ĐANG ĐẾN!*

🚌 *{plate}* còn *{dist:.2f} km*
📍 *{station_name}*
{route_desc}
⏱ {eta_text}

💬 _{greeting}_"""
    
    else:
        # Lần 3 (sau 30s nữa): Lần cuối
        msg = f"""🚨 *LẦN CUỐI - XE SẮP TỚI!*

🚌 *{plate}* - *{dist:.2f} km*
📍 *{station_name}*
{route_desc}

💬 _{greeting}_"""
    
    return msg

# =====================
# XỬ LÝ THÔNG BÁO THEO THỜI GIAN
# =====================
def process_pending_notifications():
    """Xử lý các thông báo đang chờ (lần 2, lần 3) với dữ liệu cập nhật"""
    global pending_notifications
    
    current_timestamp = time.time()
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
    keys_to_remove = []
    
    for key, data in list(pending_notifications.items()):
        if current_timestamp >= data['next_time']:
            count = data['count']
            plate = data['plate']
            station_name = data['station_name']
            
            # Kiểm tra nếu đã quá lâu (>2 phút), bỏ qua
            if current_timestamp - data.get('start_time', current_timestamp) > 120:
                keys_to_remove.append(key)
                continue
            
            if count < 3:
                # Cập nhật dữ liệu mới nếu có
                updated_dist = data['dist']
                updated_eta = data['eta_text']
                updated_route = data['route']
                
                # Lấy vị trí hiện tại của xe nếu có
                if plate in last_seen_vehicles:
                    vehicle_data = last_seen_vehicles[plate]
                    slat, slon = stations.get(station_name, (None, None))
                    if slat and slon:
                        new_dist = haversine(vehicle_data['lat'], vehicle_data['lon'], slat, slon)
                        if new_dist != float('inf'):
                            updated_dist = new_dist
                            
                            # Cập nhật ETA
                            eta = estimate_arrival_time(plate, slat, slon)
                            updated_eta = f"~{eta} phút" if eta else "Sắp đến"
                            
                            # Cập nhật hướng
                            updated_route = determine_bus_route(plate)
                
                # Gửi thông báo tiếp theo
                msg = create_notification_message(
                    plate,
                    station_name,
                    updated_dist,
                    updated_route,
                    updated_eta,
                    current_time,
                    count
                )
                
                send_success = send_telegram(msg, data['chat_id'])
                
                if send_success:
                    daily_stats[current_time.date()] += 1
                    
                    # Cập nhật cho lần tiếp theo
                    if count < 2:
                        data['count'] = count + 1
                        data['dist'] = updated_dist
                        data['eta_text'] = updated_eta
                        data['route'] = updated_route
                        next_delay = NOTIFY_DELAYS[count + 1] if count + 1 < len(NOTIFY_DELAYS) else 30
                        data['next_time'] = current_timestamp + next_delay
                    else:
                        keys_to_remove.append(key)
                else:
                    # Gửi thất bại, tăng retry count
                    data['retry_count'] = data.get('retry_count', 0) + 1
                    if data['retry_count'] >= 2:
                        # Đã thử 2 lần, bỏ qua
                        keys_to_remove.append(key)
                    else:
                        # Thử lại sau 5s
                        data['next_time'] = current_timestamp + 5
            else:
                keys_to_remove.append(key)
    
    for key in keys_to_remove:
        if key in pending_notifications:
            del pending_notifications[key]

# =====================
# XỬ LÝ XE (CẢI THIỆN PERFORMANCE)
# =====================
def process_vehicle_data(vehicles):
    """Xử lý dữ liệu xe với validation tốt hơn"""
    global pending_notifications
    
    if not vehicles or not isinstance(vehicles, list):
        return
        
    current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
    current_timestamp = time.time()
    
    # Xử lý các thông báo đang chờ
    process_pending_notifications()
    
    # Lấy trạm cho từng box
    box_stations = {}
    for box_key, box_config in BOX_CONFIGS.items():
        try:
            stations_to_check, trip_type = get_stations_to_check(box_config)
            if stations_to_check:
                box_stations[box_key] = {
                    'stations': stations_to_check,
                    'trip_type': trip_type,
                    'config': box_config
                }
        except Exception as e:
            print(f"Lỗi lấy trạm cho {box_key}: {e}")
            continue
    
    if not box_stations:
        return
    
    processed_count = 0
    for vehicle in vehicles:
        try:
            if not isinstance(vehicle, dict) or processed_count >= MAX_VEHICLES:
                continue
                
            plate = vehicle.get("9", "").strip()
            lat, lon = vehicle.get("2"), vehicle.get("3")
            
            # Validation
            if not is_valid_plate(plate) or not is_valid_coordinate(lat, lon):
                continue
            
            lat, lon = float(lat), float(lon)
            
            # Cập nhật lịch sử xe với giới hạn
            vehicle_history[plate].append((lat, lon, current_time))
            if len(vehicle_history[plate]) > MAX_HISTORY_POINTS:
                vehicle_history[plate] = vehicle_history[plate][-MAX_HISTORY_POINTS:]
            
            # Cập nhật xe cuối cùng
            last_seen_vehicles[plate] = {
                'lat': lat, 'lon': lon, 'time': current_time
            }
            
            # Xác định hướng xe (Bắc→Nam hoặc Nam→Bắc)
            route = determine_bus_route(plate)
            
            # Kiểm tra từng box
            for box_key, box_data in box_stations.items():
                stations_to_check = box_data['stations']
                trip_type = box_data['trip_type']
                chat_id = box_data['config']['chat_id']
                
                for station_name, (slat, slon) in stations_to_check.items():
                    dist = haversine(lat, lon, slat, slon)
                    if dist == float('inf'):
                        continue
                    
                    # Chỉ thông báo khi xe trong bán kính phát hiện (1.5km)
                    if dist <= DETECTION_RADIUS_FAR:
                        key = f"{plate}_{station_name}_{box_key}"
                        
                        # Kiểm tra cooldown (10 phút giữa các chuỗi thông báo)
                        if key not in notified or (current_time - notified[key]).total_seconds() > 600:
                            # Kiểm tra hướng xe có phù hợp với khung giờ không
                            # Nếu đang đi lên huyện thì route nên là 'to_huyen'
                            # Nếu đang về Buôn Đôn thì route nên là 'to_buondon'
                            
                            expected_route = None
                            if "huyện" in trip_type.lower():
                                expected_route = 'to_huyen'
                            elif "buôn đôn" in trip_type.lower():
                                expected_route = 'to_buondon'
                            
                            # Chỉ thông báo nếu hướng xe đúng hoặc chưa xác định được
                            if route == 'unknown' or route == expected_route:
                                eta = estimate_arrival_time(plate, slat, slon)
                                eta_text = f"~{eta} phút" if eta else "Sắp đến"
                                
                                # Tạo và gửi thông báo lần 1
                                msg = create_notification_message(
                                    plate, station_name, dist, route, eta_text, current_time, 0
                                )
                                
                                if send_telegram(msg, chat_id):
                                    notified[key] = current_time
                                    daily_stats[current_time.date()] += 1
                                    
                                    # Đăng ký thông báo lần 2 và 3
                                    pending_key = f"{key}_{current_timestamp}"
                                    pending_notifications[pending_key] = {
                                        'plate': plate,
                                        'station_name': station_name,
                                        'dist': dist,
                                        'route': route,
                                        'eta_text': eta_text,
                                        'chat_id': chat_id,
                                        'count': 1,  # Lần tiếp theo là lần 2
                                        'next_time': current_timestamp + NOTIFY_DELAYS[1],  # +20s
                                        'start_time': current_timestamp,
                                        'retry_count': 0
                                    }
                                    
                                    # Lưu pattern data với giới hạn
                                    if len(pattern_data[plate]) < 100:
                                        pattern_data[plate].append({
                                            'station': station_name,
                                            'time': current_time,
                                            'distance': dist,
                                            'box': box_key
                                        })
                        
            processed_count += 1
                        
        except Exception as e:
            print(f"Lỗi xử lý xe: {e}")
            continue

# =====================
# DỌN DẸP DỮ LIỆU (CẢI THIỆN)
# =====================
def cleanup_data():
    """Dọn dẹp dữ liệu với hiệu suất tốt hơn"""
    global pending_notifications
    try:
        current_time = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
        current_timestamp = time.time()
        cleanup_count = 0
        
        # Cleanup pending notifications (2 phút)
        expired_pending = [k for k, v in pending_notifications.items() 
                          if current_timestamp - v.get('next_time', 0) > 120]
        for key in expired_pending:
            del pending_notifications[key]
            cleanup_count += 1
        
        # Cleanup notifications (45 phút)
        cutoff_time = current_time - timedelta(minutes=45)
        expired_keys = [k for k, v in notified.items() if v < cutoff_time]
        for key in expired_keys:
            del notified[key]
            cleanup_count += 1
        
        # Cleanup vehicles (20 phút)
        cutoff_time = current_time - timedelta(minutes=20)
        expired_vehicles = [plate for plate, data in last_seen_vehicles.items() 
                          if data['time'] < cutoff_time]
        for plate in expired_vehicles:
            del last_seen_vehicles[plate]
            if plate in vehicle_history:
                del vehicle_history[plate]
            if plate in pattern_data:
                del pattern_data[plate]
            if plate in vehicle_signal_status:
                del vehicle_signal_status[plate]
            cleanup_count += 1
        
        # Giới hạn kích thước cache
        if len(notified) > MAX_NOTIFICATIONS:
            # Giữ lại những thông báo mới nhất
            sorted_items = sorted(notified.items(), key=lambda x: x[1], reverse=True)
            notified.clear()
            notified.update(dict(sorted_items[:MAX_NOTIFICATIONS//2]))
            cleanup_count += len(sorted_items) - MAX_NOTIFICATIONS//2
        
        # Cleanup daily stats (7 ngày)
        cutoff_date = current_time.date() - timedelta(days=7)
        expired_dates = [date for date in daily_stats.keys() if date < cutoff_date]
        for date in expired_dates:
            del daily_stats[date]
            cleanup_count += 1
        
        if cleanup_count > 0:
            print(f"🧹 Cleaned up {cleanup_count} items")
            
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

# =====================
# MAIN LOOP (CẢI THIỆN ERROR HANDLING + AUTO REFRESH TOKEN)
# =====================
def main():
    global last_api_call
    
    print("🔄 Khởi tạo token...")
    if not ensure_valid_token():
        print("❌ Không thể lấy token ban đầu! Bot sẽ thử lại...")
    
    # Startup messages
    if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        for box_key, box_config in BOX_CONFIGS.items():
            startup_msg = f"""🤖 *Bot Xe Buýt v3.0 - {box_config['name']}* khởi động!

⏰ *{datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%H:%M:%S')}*
🚌 *Theo dõi:* {len(stations)} trạm
🎯 *Chuyên biệt:* {', '.join(box_config['buon_don_stations'])}

✨ *Tính năng mới:*
• `/report` - Báo cáo hôm nay
• `/stats` - Thống kê tuần
• Cảnh báo xe mất tín hiệu GPS
• Admin: `/setschedule`, `/removetime`

💡 *Gõ /help để xem lệnh*"""
            
            send_telegram(startup_msg, box_config['chat_id'])
    
    print("🚀 Bot v3.0 khởi động thành công!")
    
    cleanup_counter = 0
    consecutive_errors = 0
    max_consecutive_errors = 5  # Giảm từ 10
    
    while True:
        try:
            current_time = time.time()
            
            # Xử lý lệnh Telegram (luôn hoạt động)
            try:
                updates = get_telegram_updates()
                if updates:
                    handle_commands(updates)
            except Exception as e:
                print(f"⚠️ Telegram error: {e}")
            
            # Kiểm tra xem có cần gọi API không
            should_check_buses = False
            for box_key, box_config in BOX_CONFIGS.items():
                stations_to_check, _ = get_stations_to_check(box_config)
                if stations_to_check:
                    should_check_buses = True
                    break
            
            if not should_check_buses:
                time.sleep(30)  # Giảm từ 60s
                continue
            
            # Rate limiting cho API
            if current_time - last_api_call < api_call_interval:
                time.sleep(api_call_interval - (current_time - last_api_call))
            
            # Đảm bảo token còn hiệu lực trước khi gọi API
            if not ensure_valid_token():
                print("❌ Không thể refresh token, bỏ qua lượt này...")
                consecutive_errors += 1
                time.sleep(30)
                continue
            
            # Gọi API
            response = requests.post(API_URL, headers=HEADERS, json=PAYLOAD, timeout=20)
            last_api_call = time.time()
            
            if response.status_code == 401:
                print("🔑 Token hết hạn, đang refresh...")
                if login_and_get_token():
                    continue
                else:
                    consecutive_errors += 1
                    time.sleep(30)
                    continue
            
            if response.status_code != 200:
                print(f"❌ API error: {response.status_code}")
                consecutive_errors += 1
                time.sleep(min(30 * consecutive_errors, 180))  # Max 3 phút
                continue
            
            try:
                res = response.json()
            except ValueError:
                print("❌ Invalid JSON response")
                consecutive_errors += 1
                time.sleep(30)
                continue
            
            # Reset error counter
            consecutive_errors = 0
            
            vehicles = res.get("Data", [])
            if vehicles:
                process_vehicle_data(vehicles)
                
                # Kiểm tra xe mất tín hiệu GPS (chỉ trong khung giờ hoạt động)
                try:
                    signal_alerts = check_vehicle_signal_loss(vehicles)
                    if signal_alerts:
                        send_signal_loss_alerts(signal_alerts)
                except Exception as e:
                    print(f"⚠️ Lỗi kiểm tra tín hiệu: {e}")
            
            # Cleanup mỗi 60 lần (5 phút)
            cleanup_counter += 1
            if cleanup_counter >= 60:
                cleanup_data()
                cleanup_counter = 0
            
            time.sleep(5)  # 5s interval
            
        except requests.exceptions.Timeout:
            print("⏰ API timeout")
            consecutive_errors += 1
            time.sleep(20)
        except requests.RequestException as e:
            print(f"🌐 Network error: {e}")
            consecutive_errors += 1
            time.sleep(min(30 * consecutive_errors, 180))
        except KeyboardInterrupt:
            print("🛑 Bot stopped by user")
            if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
                send_telegram("🛑 Bot đã dừng")
            break
        except Exception as e:
            print(f"💥 Unexpected error: {e}")
            consecutive_errors += 1
            
            if consecutive_errors >= max_consecutive_errors:
                print(f"🚨 Too many errors ({consecutive_errors}), pausing...")
                if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
                    send_telegram(f"🚨 Bot gặp {consecutive_errors} lỗi, tạm dừng 5 phút")
                time.sleep(300)  # 5 phút
                consecutive_errors = 0
            else:
                time.sleep(min(30 * consecutive_errors, 120))

if __name__ == "__main__":
    main()
