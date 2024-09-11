import csv
import os
import io
from bson import ObjectId
from flask import Flask, session, flash, make_response, send_file, render_template, request, redirect, url_for
from PIL import Image
from xhtml2pdf import pisa
from pymongo import MongoClient, ASCENDING
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static'
app.secret_key = 'supersecretkey'

MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client.CollegeManagementSystem

# Collections
students_collection = db.students
faculty_collection = db.faculty
user_collection = db.user
results_collection = db.results

students_collection.create_index([('student_id', ASCENDING)], unique=True)
faculty_collection.create_index([('faculty_id', ASCENDING)], unique=True)
user_collection.create_index([('user_id', ASCENDING)], unique=True)
results_collection.create_index([('student_id', ASCENDING), ('subject_name', ASCENDING)], unique=True)


print("Indexes created successfully.")

# Verify indexes
def print_indexes(collection):
    indexes = collection.index_information()
    for index_name, index_info in indexes.items():
        print(f"{collection.name} index: {index_name} -> {index_info}")

print_indexes(students_collection)
print_indexes(faculty_collection)
print_indexes(user_collection)
print_indexes(results_collection)

@app.route('/print')
def print():
    students = list(students_collection.find())
    results = list(results_collection.find())
    faculty = list(faculty_collection.find())
    users = list(user_collection.find())
    return render_template('print.html', students=students, results=results, faculty=faculty, users=users)
        
def create_user_data():

    faculty_cursor = faculty_collection.find({})
    for faculty in faculty_cursor:
        user = {
            'user_id': faculty['faculty_id'],
            'email': faculty['email'],
            'password': faculty['password'],
            'type': 'faculty',
            'username': faculty['name']
        }
        
        user_collection.update_one(
            {'user_id': faculty['faculty_id']},
            {'$set': user},
            upsert=True
        )

    student_cursor = students_collection.find({})
    for student in student_cursor:
        user = {
            'user_id': student['student_id'],
            'email': student['email'],
            'password': student['password'],
            'type': 'student',
            'username': student['name']
        }
       
        user_collection.update_one(
            {'user_id': student['student_id']},
            {'$set': user},
            upsert=True
        )      
        
@app.route('/login_form')
def login_form():
    create_user_data()
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    user, user_type = check_credentials(email, password)
    if user:
        session['user_type'] = user_type
        session['user_id'] = user['user_id']
        session['username'] = user['username']
        flash(f'{user["username"]} logged in successfully!👍')
        return redirect(url_for('index'))

    return redirect(url_for('login_form'))

@app.route('/logout')
def logout():
    username = session.get('username')
    session.clear()  
    flash(f'{username} Logout successfully!!😁') 
    return redirect(url_for('index')) 

def get_faculty_batch(faculty_id):
    faculty = faculty_collection.find_one({'faculty_id': faculty_id})
    if faculty:
        return faculty.get('batch')
    return None

@app.route('/faculty/students', methods=['GET', 'POST'])
def faculty_studentsbranch():
    if 'user_type' in session and session['user_type'] == 'faculty':
        faculty_id = session['user_id']
        faculty_batch = get_faculty_batch(faculty_id)
        matched_students = []
        username = session.get('username')

        if faculty_batch:
            matched_students = list(students_collection.find({'batch': faculty_batch}))

        return render_template('student.html', username=username, students=matched_students)
    else:
        return redirect(url_for('login_form'))

def check_credentials(email, password):
    user = user_collection.find_one({'email': email, 'password': password})
    if user:
        return user, user['type']
    
    if email == "admin123@gmail.com" and password == "admin123":
        return {"user_id": "admin123", "username": "admin123", "type": "admin"}, "admin"

    return None, None

@app.route('/students/results/<student_id>/<int:width>*<int:height>')
def generate_image(student_id, width, height):
    filename = f"static/{student_id}.jpg"
    
    if os.path.exists(filename):
        img = Image.open(filename)
        img = img.convert('RGB')
        img_resized = img.resize((width, height))
        img_io = io.BytesIO()
        img_resized.save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    else:
        return "Image not found", 404

def convert_html_to_pdf(html_string):
    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.BytesIO(html_string.encode("UTF-8")), dest=result)
    return result.getvalue()

@app.route('/students/results/download/<student_id>')
def download_pdf(student_id):
    results = []
    student_name = ''
    batch = ''
    passorfail = '-'
    
    student_doc = students_collection.find_one({'student_id': student_id})
    if student_doc:
        student_name = student_doc['name']
        batch = student_doc['batch']
    
    results_cursor = results_collection.find({'student_id': student_id})
    for result_doc in results_cursor:
        results.append([
            result_doc['student_id'],
            result_doc['subject_name'],
            result_doc['total_marks'],
            result_doc['obtained_marks']
        ])
    
    for result in results:
        obtained_marks = int(result[3])
        total_marks = int(result[2])
        percentage = (obtained_marks / total_marks) * 100
        if percentage < 35:
            result.append('Fail')
        else:
            result.append('Pass')
    
    for result in results:
        if result[4] == 'Fail': 
            passorfail = 'Fail'
            break
        else:
            passorfail = 'Pass'

    rendered = render_template('result_student_pdf.html', student_name=student_name, student_id=student_id, results=results, batch=batch, passorfail=passorfail)
    
    pdf = convert_html_to_pdf(rendered)
    
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=results_{student_id}.pdf'
    
    return response

@app.route('/admin')
def admin_dashboard():
    user_type = session.get('user_type')
    return render_template('admin_index.html', user_type=user_type)

@app.route('/')
def index():
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    username = session.get('username')
    return render_template('index.html', user_type=user_type, user_id=user_id, username=username)

@app.route('/student')
def student():
    return render_template('student.html')

@app.route('/About')
def about():
    user_id=session.get('user_id')
    username=session.get('username')
    user_type = session.get('user_type')
    return render_template('about.html', user_id=user_id, user_type=user_type,username=username)

@app.route('/ContactUs')
def contactUs():
    user_id=session.get('user_id')
    username=session.get('username')
    user_type = session.get('user_type')
    return render_template('contact.html', user_id=user_id, user_type=user_type, username=username)

@app.route('/student-form')
def student_form():
    return render_template('student_form.html')

@app.route('/students')
def student_list():
    user_type = session.get('user_type')
    students = list(students_collection.find())
    return render_template('student.html', students=students, user_type=user_type)

@app.route('/faculty-form')
def faculty_form():
    subjects = get_subjects()
    return render_template('faculty_form.html', subjects=subjects)

@app.route('/faculty')
def faculty_list():
    user_type = session.get('user_type')
  
    faculties = list(faculty_collection.find())
    
    return render_template('faculty.html', faculties=faculties, user_type=user_type)

@app.route('/add_faculty', methods=['POST'])
def add_faculty():
    if request.method == 'POST':
        name = request.form['name']
        faculty_id = request.form['faculty_id']
        subject = request.form['subject']
        email = request.form['email']
        password = request.form['password']
        batch = request.form['batch']

        if faculty_collection.find_one({"faculty_id": faculty_id}):
            flash('Faculty ID must be unique.')
            return redirect(url_for('faculty_form'))

        faculty_collection.insert_one({
            "name": name,
            "faculty_id": faculty_id,
            "subject": subject,
            "email": email,
            "password": password,
            "batch": batch
        })

        flash('Faculty added successfully!')
        return redirect(url_for('faculty_list'))
    return render_template('faculty_form.html')


@app.route('/faculty/view/<faculty_id>')
def view_faculty(faculty_id):
    user_type = session.get('user_type')
    username = session.get('username')
    user_id = session.get('user_id')

    if user_type != 'admin' and user_id != faculty_id:
        return redirect(url_for('login_form'))

    faculty = faculty_collection.find_one({"faculty_id": faculty_id})
    
    if not faculty:
        flash('Faculty not found.')
        return redirect(url_for('faculty_list'))

    return render_template('view_faculty.html', username=username, faculty=faculty, user_type=user_type)

def get_subjects():
    
    all_results = results_collection.find()
    unique_subjects = set()

    for result in all_results:
        subject_name = result.get("subject_name", "")
        if subject_name:
            unique_subjects.add(subject_name)

    unique_subject_list = list(unique_subjects)
    return unique_subject_list


@app.route('/faculty/students/<faculty_id>')
def faculty_students(faculty_id):
    username = session.get('username')
    user_type = session.get('user_type')

    faculty = faculty_collection.find_one({"faculty_id": faculty_id})
    if not faculty:
        flash('Faculty not found.')
        return redirect(url_for('faculty_list'))
    faculty_batch = faculty.get('batch')
    students = list(students_collection.find({"batch": faculty_batch}))

    return render_template('student.html', students=students, faculty_id=faculty_id, user_type=user_type, username=username)

@app.route('/faculty/edit/<faculty_id>', methods=['GET', 'POST'])
def edit_faculty(faculty_id):
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    
    if user_type != 'admin' and user_id != faculty_id:
        return redirect(url_for('login_form'))

    faculty = faculty_collection.find_one({"faculty_id": faculty_id})
    if not faculty:
        flash('Faculty not found.')
        return redirect(url_for('faculty_list'))
    
    if request.method == 'POST':
        name = request.form['name']
        subject = request.form['subject']
        email = request.form['email']
        password = request.form['password']

        faculty_collection.update_one(
            {"faculty_id": faculty_id},
            {"$set": {
                "name": name,
                "subject": subject,
                "email": email,
                "password": password
            }}
        )
        
        flash('Faculty updated successfully!')
        return redirect(url_for('faculty_list'))

    subjects = get_subjects()
    return render_template('edit_faculty.html', faculty=faculty, subjects=subjects, user_type=user_type)

@app.route('/faculty/delete/<faculty_id>')
def delete_faculty(faculty_id):
    result = faculty_collection.delete_one({"faculty_id": faculty_id})
    
    if result.deleted_count == 0:
        flash('Faculty not found or could not be deleted.')
    else:
        user_result = user_collection.delete_one({"user_id": faculty_id})
        
        if user_result.deleted_count == 0:
            flash('Faculty deleted, but the corresponding user was not found or could not be deleted.')
        else:
            flash('Faculty and corresponding user deleted successfully!')
    
    return redirect(url_for('faculty_list'))

@app.route('/add', methods=['POST'])
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        student_id = request.form['student_id']
        batch = request.form['batch']
        email = request.form['email']
        password = request.form['password']
        subjects = request.form.getlist('subject_name')
        total_marks = request.form.getlist('total_marks')
        obtained_marks = request.form.getlist('obtained_marks')

        if students_collection.find_one({"student_id": student_id}):
            flash('Student ID must be unique.')
            return redirect(url_for('student_form'))

        faculty_dict = []
        faculties = faculty_collection.find({"subject": {"$in": subjects}})
        for faculty in faculties:
            faculty_dict.append(faculty['faculty_id'])

        student_data = {
            "name": name,
            "student_id": student_id,
            "batch": batch,
            "email": email,
            "password": password,
            "faculty_dict": faculty_dict
        }
        students_collection.insert_one(student_data)

        for subject, total, obtained in zip(subjects, total_marks, obtained_marks):
            result_data = {
                "student_id": student_id,
                "subject_name": subject,
                "total_marks": total,
                "obtained_marks": obtained
            }
            results_collection.insert_one(result_data)

        if 'image' not in request.files:
            flash('No file part')
            return redirect(url_for('student_form'))
        file = request.files['image']
        if file.filename == '':
            flash('No selected file')
            return redirect(url_for('student_form'))
        if file:
            filename = secure_filename(f"{student_id}.jpg")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        flash('Student added successfully!')
        return redirect(url_for('student_list'))
    return render_template('student.html')


@app.route('/edit_student/<student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    student = students_collection.find_one({"student_id": student_id})
    if request.method == 'POST':
        name = request.form['name']
        batch = request.form['batch']
        email = request.form['email']
        password = request.form['password']
        students_collection.update_one(
            {"student_id": student_id},
            {"$set": {
                "name": name,
                "batch": batch,
                "email": email,
                "password": password
            }}
        )
        flash('Student updated successfully!')
        return redirect(url_for('student_list'))
    return render_template('edit_student.html', student=student)

@app.route('/delete_student/<student_id>')
def delete_student(student_id):
    student_result = students_collection.delete_one({"student_id": student_id})
    
    if student_result.deleted_count == 0:
        flash('Student not found or could not be deleted.')
    else:
        user_result = user_collection.delete_one({"user_id": student_id})
        results_result = results_collection.delete_many({"student_id": student_id})
        
        if user_result.deleted_count == 0:
            flash('Student deleted, but the corresponding user was not found or could not be deleted.')
        else:
            flash('Student and corresponding user deleted successfully!')

        flash(f'Also deleted {results_result.deleted_count} result(s) associated with the student.')
    
    return redirect(url_for('student_list'))

@app.route('/students/results/<student_id>')
def view_results(student_id):
    username = session.get('username')
    user_id = session.get('user_id')
    user_type = session.get('user_type')

    if user_type == 'student' and user_id != student_id:
        flash('please login first!🤦‍♂️')
        return redirect(url_for('login_form'))

    student = students_collection.find_one({"student_id": student_id})
    if not student:
        flash('Student not found!')
        return redirect(url_for('student_list'))

    if user_type == 'faculty':
        faculty_batch = get_faculty_batch(user_id)
        if student['batch'] != faculty_batch:
            return redirect(url_for('login_form'))

    student_name = student['name']
    batch = student['batch']
    results = list(results_collection.find({"student_id": student_id}))

    passorfail = 'Pass'
    for result in results:
        if int(result['obtained_marks']) <= int(float(result['total_marks']) * 0.35):
            passorfail = 'Fail'
            break

    for result in results:
        obtained_marks = int(result['obtained_marks'])
        total_marks = int(result['total_marks'])
        percentage = (obtained_marks / total_marks) * 100
        result['status'] = 'Pass' if percentage >= 35 else 'Fail'

    faculty_subject = None
    if user_type == 'faculty':
        faculty_member = faculty_collection.find_one({"faculty_id": user_id})
        if faculty_member:
            faculty_subject = faculty_member['subject']

    return render_template('result_student.html', student_name=student_name, student_id=student_id, batch=batch, results=results, passorfail=passorfail, user_type=user_type, faculty_subject=faculty_subject, user_id=user_id, username=username)

@app.route('/students/results/add/<student_id>', methods=['POST'])
def add_result(student_id):
    subject_name = request.form['subject_name']
    total_marks = int(request.form['total_marks'])
    obtained_marks = int(request.form['obtained_marks'])

    result = {
        "student_id": student_id,
        "subject_name": subject_name,
        "total_marks": total_marks,
        "obtained_marks": obtained_marks
    }

    results_collection.insert_one(result)
        
    flash('Result added successfully!')
    return redirect(url_for('view_results', student_id=student_id))


@app.route('/students/results/edit/<student_id>/<result_id>', methods=['GET', 'POST'])
def edit_result(student_id, result_id):
    user_type = session.get('user_type')
    result = results_collection.find_one({"_id": ObjectId(result_id)})

    if request.method == 'POST':
        updated_result = {
            "subject": request.form['subject_name'],
            "total_marks": int(request.form['total_marks']),
            "obtained_marks": int(request.form['obtained_marks'])
        }
        
        results_collection.update_one({"_id": ObjectId(result_id)}, {"$set": updated_result})
        
        flash('Result updated successfully!')
        return redirect(url_for('view_results', student_id=student_id))

    return render_template('edit_result.html', result=result, student_id=student_id, user_type=user_type)


@app.route('/students/results/delete/<student_id>/<result_id>')
def delete_result(student_id, result_id):
    results_collection.delete_one({"_id": ObjectId(result_id)})

    flash('Result deleted successfully!')
    return redirect(url_for('view_results', student_id=student_id))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)