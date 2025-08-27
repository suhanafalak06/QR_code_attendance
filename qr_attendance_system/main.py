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

def get_current_date():
    return datetime.now().strftime('%Y-%m-%d')

@app.route('/')
def home():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/api/generate_qr', methods=['POST'])
def generate_qr():
    """
    Generates a new, time-stamped QR code payload and stores it as valid.
    The payload includes a unique ID and an expiration time.
    """
    try:
        qr_id = str(uuid.uuid4())
        qr_data = {
            "id": qr_id,
            "class_name": "Computer Science 101",
            "classroom": "Room 205",
            "instructor": "Dr. Smith",
            "timestamp": datetime.now().isoformat(),
            "expiry": (datetime.now() + timedelta(minutes=30)).isoformat(),
        }
        
        valid_qr_codes[qr_id] = qr_data
        
        return jsonify({"qr_data": qr_data})
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
    app.run(debug=True)