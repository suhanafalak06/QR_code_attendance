# main.py
import json
import uuid
import pandas as pd
import io
from flask import Flask, render_template, request, jsonify, send_file
from datetime import datetime, timedelta

app = Flask(__name__)

# In-memory data store
attendance_records = {}
valid_qr_codes = {}
scan_history = {}  # Track scan attempts by IP/device
timetables = {}  # Store timetables
classes = {}  # Store class information

def get_current_date():
    return datetime.now().strftime('%Y-%m-%d')

def check_scan_limit(client_ip):
    """
    Check if the client IP has exceeded scan limits (1 scan per 30 minutes)
    """
    current_time = datetime.now()
    

    if client_ip not in scan_history:
        scan_history[client_ip] = []
    
    # Remove scans older than 30 minutes
    cutoff_time = current_time - timedelta(minutes=30)
    scan_history[client_ip] = [
        scan_time for scan_time in scan_history[client_ip] 
        if scan_time > cutoff_time
    ]
    
    # Check if user has already made 1 scan in the last 30 minutes
    if len(scan_history[client_ip]) >= 1:
        next_allowed_time = scan_history[client_ip][0] + timedelta(minutes=30)
        return False, f"You can only scan 1 QR code per 30 minutes. Next scan allowed at: {next_allowed_time.strftime('%H:%M:%S')}"
    
    return True, ""

def record_scan_attempt(client_ip):
    """
    Record a successful scan attempt
    """
    current_time = datetime.now()
    if client_ip not in scan_history:
        scan_history[client_ip] = []
    scan_history[client_ip].append(current_time)

@app.route('/')
def home():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/api/generate_qr', methods=['POST'])
def generate_qr():
    """
    Generates a QR code URL for attendance marking and stores it as valid.
    """
    try:
        data = request.json or {}
        
        qr_id = str(uuid.uuid4())
        qr_data = {
            "id": qr_id,
            "class_name": data.get("class_name", "Computer Science 101"),
            "classroom": data.get("classroom", "Room 205"),
            "instructor": data.get("instructor", "Dr. Smith"),
            "subject": data.get("subject", ""),
            "time_slot": data.get("time_slot", ""),
            "day": data.get("day", ""),
            "timetable_id": data.get("timetable_id", ""),
            "timestamp": datetime.now().isoformat(),
            "expiry": (datetime.now() + timedelta(minutes=30)).isoformat(),
        }
        valid_qr_codes[qr_id] = qr_data
        # Generate QR code URL (replace with your server address as needed)
        server_url = request.host_url.rstrip('/')
        qr_url = f"{server_url}/attend?qrId={qr_id}"
        return jsonify({"qr_data": qr_data, "qr_url": qr_url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/attend', methods=['GET', 'POST'])
def attend_form():
    """
    Web form for students to enter USN ID and name after scanning QR code.
    """
    qr_id = request.args.get('qrId')
    error = None
    success = None
    client_ip = request.remote_addr
    
    if request.method == 'POST':
        # Check scan limit before processing
        can_scan, limit_message = check_scan_limit(client_ip)
        if not can_scan:
            error = limit_message
        else:
            student_id = request.form.get('studentId')
            student_name = request.form.get('studentName')
            
            if not student_id or not student_name:
                error = "Please enter both USN ID and Name."
            elif qr_id not in valid_qr_codes:
                error = "Invalid or expired QR code."
            else:
                # Check QR code expiry
                qr_data = valid_qr_codes[qr_id]
                if datetime.fromisoformat(qr_data['expiry']) < datetime.now():
                    del valid_qr_codes[qr_id]
                    error = "QR code has expired."
                else:
                    # Mark attendance
                    today = get_current_date()
                    if today not in attendance_records:
                        attendance_records[today] = []
                    
                    if any(record['studentId'] == student_id for record in attendance_records[today]):
                        error = "Attendance already marked for this USN today."
                    else:
                        new_record = {
                            "time": datetime.now().strftime('%H:%M:%S'),
                            "studentId": student_id,
                            "studentName": student_name,
                            "status": "Present",
                            "method": "qr"
                        }
                        attendance_records[today].append(new_record)
                        
                        # Record the successful scan attempt
                        record_scan_attempt(client_ip)
                        
                        success = "Attendance recorded successfully!"
    
    return render_template('attend_form.html', qr_id=qr_id, error=error, success=success)

@app.route('/api/check_scan_limit', methods=['GET'])
def check_scan_limit_api():
    """
    API endpoint to check scan limits for a client
    """
    client_ip = request.remote_addr
    can_scan, message = check_scan_limit(client_ip)
    
    remaining_scans = 1 - len(scan_history.get(client_ip, []))
    
    return jsonify({
        "can_scan": can_scan,
        "message": message,
        "remaining_scans": remaining_scans,
        "reset_time": (scan_history[client_ip][0] + timedelta(minutes=30)).isoformat() if scan_history.get(client_ip) else None
    })

@app.route('/api/timetables', methods=['GET'])
def get_timetables():
    """
    Get all timetables
    """
    return jsonify(timetables)

@app.route('/api/current_class', methods=['POST'])
def get_current_class():
    """
    Get the current class from a timetable based on current time and day
    """
    try:
        data = request.json
        timetable_id = data.get('timetable_id')
        
        if not timetable_id or timetable_id not in timetables:
            return jsonify({"error": "Timetable not found"}), 404
        
        timetable = timetables[timetable_id]
        current_time = datetime.now()
        current_day = current_time.strftime('%A').lower()
        current_hour = current_time.hour
        current_minute = current_time.minute
        current_time_minutes = current_hour * 60 + current_minute
        
        # Define time slots (in minutes from midnight)
        time_slots = [
            {"start": 8*60 + 30, "end": 9*60 + 30, "slot": 0},    # 8:30-9:30
            {"start": 9*60 + 30, "end": 10*60 + 30, "slot": 1},   # 9:30-10:30
            {"start": 10*60 + 45, "end": 11*60 + 45, "slot": 2},  # 10:45-11:45 (after tea break)
            {"start": 11*60 + 45, "end": 12*60 + 45, "slot": 3},  # 11:45-12:45
            {"start": 13*60 + 30, "end": 14*60 + 30, "slot": 4},  # 1:30-2:30 (after lunch)
            {"start": 14*60 + 30, "end": 15*60 + 30, "slot": 5},  # 2:30-3:30
            {"start": 15*60 + 30, "end": 16*60 + 30, "slot": 6},  # 3:30-4:30
            {"start": 16*60 + 30, "end": 17*60 + 30, "slot": 7},  # 4:30-5:30
        ]
        
        # Find current time slot
        current_slot = None
        for slot_info in time_slots:
            if slot_info["start"] <= current_time_minutes <= slot_info["end"]:
                current_slot = slot_info["slot"]
                break
        
        if current_slot is None:
            return jsonify({"message": "No class at current time", "is_break": True})
        
        # Check if there's a class scheduled
        if current_day in timetable.get('schedule', {}):
            day_schedule = timetable['schedule'][current_day]
            if current_slot < len(day_schedule):
                class_info = day_schedule[current_slot]
                if class_info.get('subject'):
                    return jsonify({
                        "class_info": class_info,
                        "day": current_day,
                        "slot": current_slot,
                        "timetable_id": timetable_id,
                        "timetable_name": timetable.get('name', 'Untitled'),
                        "is_break": False
                    })
        
        return jsonify({"message": "No class scheduled at current time", "is_break": False})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/timetables', methods=['POST'])
def save_timetable():
    """
    Save a timetable
    """
    try:
        data = request.json
        timetable_id = data.get('id')
        if not timetable_id:
            return jsonify({"error": "Timetable ID is required"}), 400
        
        timetables[timetable_id] = data
        
        # Also save to a JSON file for persistence
        import json
        try:
            with open('timetables.json', 'w') as f:
                json.dump(timetables, f, indent=2)
        except Exception as e:
            print(f"Error saving to file: {e}")
        
        return jsonify({"message": "Timetable saved successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/timetables/<timetable_id>', methods=['DELETE'])
def delete_timetable(timetable_id):
    """
    Delete a timetable
    """
    try:
        if timetable_id in timetables:
            del timetables[timetable_id]
            
            # Save to file
            import json
            try:
                with open('timetables.json', 'w') as f:
                    json.dump(timetables, f, indent=2)
            except Exception as e:
                print(f"Error saving to file: {e}")
            
            return jsonify({"message": "Timetable deleted successfully"})
        else:
            return jsonify({"error": "Timetable not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def load_timetables_from_file():
    """
    Load timetables from JSON file on startup
    """
    global timetables
    import json
    try:
        with open('timetables.json', 'r') as f:
            timetables = json.load(f)
        print(f"Loaded {len(timetables)} timetables from file")
    except FileNotFoundError:
        print("No timetables file found, starting with empty timetables")
        timetables = {}
    except Exception as e:
        print(f"Error loading timetables: {e}")
        timetables = {}

def load_classes_from_file():
    """
    Load classes from JSON file on startup
    """
    global classes
    import json
    try:
        with open('classes.json', 'r') as f:
            classes = json.load(f)
        print(f"Loaded {len(classes)} classes from file")
    except FileNotFoundError:
        print("No classes file found, starting with empty classes")
        classes = {}
    except Exception as e:
        print(f"Error loading classes: {e}")
        classes = {}

@app.route('/api/classes', methods=['GET'])
def get_classes():
    """
    Get all classes
    """
    return jsonify(classes)

@app.route('/api/classes', methods=['POST'])
def save_class():
    """
    Save a class
    """
    try:
        data = request.json
        class_id = data.get('id')
        if not class_id:
            return jsonify({"error": "Class ID is required"}), 400
        
        classes[class_id] = data
        
        # Also save to a JSON file for persistence
        import json
        try:
            with open('classes.json', 'w') as f:
                json.dump(classes, f, indent=2)
        except Exception as e:
            print(f"Error saving classes to file: {e}")
        
        return jsonify({"message": "Class saved successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/classes/<class_id>', methods=['DELETE'])
def delete_class(class_id):
    """
    Delete a class
    """
    try:
        if class_id in classes:
            del classes[class_id]
            
            # Save to file
            import json
            try:
                with open('classes.json', 'w') as f:
                    json.dump(classes, f, indent=2)
            except Exception as e:
                print(f"Error saving classes to file: {e}")
            
            return jsonify({"message": "Class deleted successfully"})
        else:
            return jsonify({"error": "Class not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/classes/timetable/<timetable_id>', methods=['GET'])
def get_classes_for_timetable(timetable_id):
    """
    Get all classes associated with a specific timetable
    """
    try:
        timetable_classes = {k: v for k, v in classes.items() if v.get('timetable_id') == timetable_id}
        return jsonify(timetable_classes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/attend', methods=['POST'])
def record_attendance():
    """
    Records a student's attendance. Validates QR code data if provided.
    """
    try:
        data = request.json
        student_id = data.get('studentId')
        student_name = data.get('studentName')
        method = data.get('method')
        qr_id = data.get('qrId')

        if not student_id or not student_name or not method:
            return jsonify({"error": "Missing student information"}), 400

        # Check for duplicate entry for today's date and student ID
        today = get_current_date()
        if today not in attendance_records:
            attendance_records[today] = []

        if any(record['studentId'] == student_id for record in attendance_records[today]):
            return jsonify({"error": "Student already marked present today."}), 409

        # QR code validation
        if method == 'qr' and qr_id:
            if qr_id not in valid_qr_codes:
                return jsonify({"error": "Invalid QR code."}), 403
            
            qr_data = valid_qr_codes[qr_id]
            if datetime.fromisoformat(qr_data['expiry']) < datetime.now():
                del valid_qr_codes[qr_id]
                return jsonify({"error": "QR code has expired."}), 403

        new_record = {
            "time": datetime.now().strftime('%H:%M:%S'),
            "studentId": student_id,
            "studentName": student_name,
            "status": "Present",
            "method": method
        }

        attendance_records[today].append(new_record)
        
        return jsonify({"message": "Attendance recorded successfully!", "record": new_record})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/attendance', methods=['GET'])
def get_attendance():
    """
    Retrieves all attendance records for today.
    """
    today = get_current_date()
    return jsonify(attendance_records.get(today, []))

@app.route('/api/export_excel', methods=['GET'])
def export_excel():
    """
    Exports today's attendance data to an Excel file.
    """
    today = get_current_date()
    data = attendance_records.get(today, [])

    if not data:
        return jsonify({"error": "No attendance data to export."}), 404

    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Attendance', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Attendance_Report_{today}.xlsx"
    )

if __name__ == '__main__':
    # Load timetables and classes from file on startup
    load_timetables_from_file()
    load_classes_from_file()
    app.run(host='0.0.0.0', port=5000, debug=True)