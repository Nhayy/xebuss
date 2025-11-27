from flask import Flask, render_template_string
import threading
import time
import os

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bus Bot Status</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 16px;
            backdrop-filter: blur(10px);
        }
        h1 { font-size: 24px; margin-bottom: 8px; }
        .status { 
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 14px;
            background: #4ade80;
            color: #000;
        }
        .schedule-item {
            padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .schedule-item:last-child { border: none; }
        .day { font-weight: 600; color: #60a5fa; }
        .time { color: #94a3b8; font-size: 14px; margin-top: 4px; }
        .off { color: #f87171; }
        .footer { text-align: center; color: #64748b; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🚌 Bus Bot v3.0</h1>
            <span class="status">Đang chạy</span>
        </div>
        
        <div class="card">
            <h2 style="margin-bottom:16px">📅 Lịch hoạt động</h2>
            <div class="schedule-item">
                <div class="day">Thứ 2</div>
                <div class="time">05:05-06:00, 10:20-10:50, 12:30-12:45, 15:15-16:30</div>
            </div>
            <div class="schedule-item">
                <div class="day">Thứ 3, 6</div>
                <div class="time">05:05-06:00, 10:20-10:50</div>
            </div>
            <div class="schedule-item">
                <div class="day">Thứ 4</div>
                <div class="time">05:05-06:00, 10:20-10:50, 12:30-12:45, 16:50-17:40</div>
            </div>
            <div class="schedule-item">
                <div class="day">Thứ 5</div>
                <div class="time">05:05-06:00, 10:20-10:50, 12:30-12:45, 13:30-13:45, 15:15-16:30</div>
            </div>
            <div class="schedule-item">
                <div class="day off">Thứ 7, CN</div>
                <div class="time">Nghỉ</div>
            </div>
        </div>
        
        <div class="card">
            <h2 style="margin-bottom:12px">💬 Lệnh Telegram</h2>
            <div class="time">/help - Xem tất cả lệnh</div>
            <div class="time">/status - Trạng thái hiện tại</div>
            <div class="time">/report - Báo cáo hôm nay</div>
            <div class="time">/stats - Thống kê tuần</div>
        </div>
        
        <div class="footer">Bus Bot - Theo dõi xe buýt Buôn Đôn</div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/health')
def health():
    return {'status': 'ok', 'version': '3.0'}

def run_web():
    app.run(host='0.0.0.0', port=5000)

def run_bot():
    import main
    main.main()

if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    time.sleep(2)
    run_web()
