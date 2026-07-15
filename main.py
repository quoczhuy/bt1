"""
=======================================================================
PHẦN 1: BÁO CÁO PHÂN TÍCH VÀ THIẾT KẾ GIẢI PHÁP
=======================================================================
6.1. Phân tích dữ liệu đầu vào và đầu ra:
- Dữ liệu lấy từ request body: student_id, course_id (khi POST /enrollments).
- Dữ liệu cần truy vấn từ CSDL: 
    + Thông tin Student (tồn tại?, status).
    + Thông tin Course (tồn tại?, status, max_students).
    + Bản ghi Enrollment để kiểm tra trùng lặp.
    + Số lượng Enrollment hiện tại của Course để kiểm tra sức chứa.

- Điều kiện trả về 404 (Not Found):
    + Không tìm thấy sinh viên (Student không tồn tại).
    + Không tìm thấy khóa học (Course không tồn tại).

- Điều kiện trả về 400 (Bad Request):
    + Trạng thái sinh viên là INACTIVE.
    + Trạng thái khóa học là CLOSED.
    + Sinh viên đã đăng ký khóa học này trước đó (trùng lặp).
    + Số lượng sinh viên đã đăng ký >= max_students (khóa học đã đầy).

- Khi nào được phép tạo Enrollment:
    + Khi tất cả các điều kiện 404 và 400 ở trên đều không vi phạm.
=======================================================================
PHẦN 2: TRIỂN KHAI SOURCE CODE HOÀN CHỈNH
=======================================================================
"""

from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from datetime import datetime

# ==========================================
# 1. CẤU HÌNH DATABASE (MySQL + SQLAlchemy)
# ==========================================
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:password@localhost:3306/school_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 2. ĐỊNH NGHĨA MODELS (Database)
# ==========================================
class Student(Base):
    __tablename__ = "students"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False) # ACTIVE hoặc INACTIVE
    
    # Quan hệ với bảng Enrollment
    enrollments = relationship("Enrollment", back_populates="student")

class Course(Base):
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    max_students = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False) # OPEN hoặc CLOSED
    
    # Quan hệ với bảng Enrollment
    enrollments = relationship("Enrollment", back_populates="course")

class Enrollment(Base):
    __tablename__ = "enrollments"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    
    # Quan hệ ngược lại
    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")

# Tạo bảng trong CSDL (Trong thực tế nên dùng Alembic để migrate)
Base.metadata.create_all(bind=engine)

# ==========================================
# 3. ĐỊNH NGHĨA SCHEMAS (Pydantic)
# ==========================================
class EnrollmentCreate(BaseModel):
    student_id: int
    course_id: int

class EnrollmentResponse(BaseModel):
    id: int
    student_id: int
    course_id: int
    enrolled_at: datetime

    class Config:
        orm_mode = True

class CourseResponse(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True

class StudentCoursesResponse(BaseModel):
    student_id: int
    full_name: str
    courses: list[CourseResponse]

# ==========================================
# 4. KHỞI TẠO FASTAPI & DEPENDENCIES
# ==========================================
app = FastAPI(title="Course Enrollment API")

# Dependency lấy Database Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 5. APIs
# ==========================================

@app.post("/enrollments", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
def create_enrollment(enrollment_data: EnrollmentCreate, db: Session = Depends(get_db)):
    # Lấy thông tin Student và Course
    student = db.query(Student).filter(Student.id == enrollment_data.student_id).first()
    course = db.query(Course).filter(Course.id == enrollment_data.course_id).first()
    
    # 1. Kiểm tra tồn tại (Trả về 404)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sinh viên không tồn tại.")
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khóa học không tồn tại.")
        
    # 2. Kiểm tra trạng thái hợp lệ (Trả về 400)
    if student.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sinh viên không trong trạng thái ACTIVE.")
    if course.status != "OPEN":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Khóa học đã đóng (CLOSED).")
        
    # 3. Kiểm tra đăng ký trùng lặp (Trả về 400)
    existing_enrollment = db.query(Enrollment).filter(
        Enrollment.student_id == student.id, 
        Enrollment.course_id == course.id
    ).first()
    if existing_enrollment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sinh viên đã đăng ký khóa học này rồi.")
        
    # 4. Kiểm tra sức chứa của khóa học (Trả về 400)
    current_enrollments_count = db.query(Enrollment).filter(Enrollment.course_id == course.id).count()
    if current_enrollments_count >= course.max_students:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Khóa học đã đủ số lượng đăng ký tối đa.")
        
    # 5. Tạo đăng ký mới
    new_enrollment = Enrollment(
        student_id=student.id,
        course_id=course.id,
        enrolled_at=datetime.now()
    )
    db.add(new_enrollment)
    db.commit()
    db.refresh(new_enrollment)
    
    return new_enrollment


@app.get("/students/{student_id}/courses", response_model=StudentCoursesResponse)
def get_student_courses(student_id: int, db: Session = Depends(get_db)):
    # Tìm sinh viên
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sinh viên không tồn tại.")
    
    # Lấy danh sách các khóa học mà sinh viên đã đăng ký
    enrollments = db.query(Enrollment).filter(Enrollment.student_id == student.id).all()
    course_ids = [e.course_id for e in enrollments]
    
    # Lấy thông tin các khóa học
    courses = db.query(Course).filter(Course.id.in_(course_ids)).all()
    
    # Trả về theo schema yêu cầu
    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "courses": [{"id": c.id, "name": c.name} for c in courses]
    }