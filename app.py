from flask import Flask, redirect, render_template, request, url_for, jsonify, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid
import os
import io
import csv
import base64
import qrcode

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'tiket.db')
app.config['SECRET_KEY'] = 'mms-kajian-secret-key-2026'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login terlebih dahulu.'
login_manager.login_message_category = 'warning'


# ========================
# MODELS
# ========================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Tiket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kode = db.Column(db.String(10), unique=True, nullable=False)
    nama = db.Column(db.String(100), default="Peserta Kajian MMS")
    angkatan = db.Column(db.String(50))
    is_used = db.Column(db.Boolean, default=False)
    waktu_daftar = db.Column(db.DateTime, default=datetime.utcnow)
    waktu_scan = db.Column(db.DateTime, nullable=True)


class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ========================
# HELPER
# ========================

def get_kuota():
    """Get current registration quota from settings."""
    setting = Setting.query.filter_by(key='kuota').first()
    return int(setting.value) if setting else 70


def generate_qr_base64(data):
    """Generate QR code and return as base64 string."""
    img = qrcode.make(data)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


# ========================
# AUTH ROUTES
# ========================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin'))
        flash('Username atau password salah!', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Berhasil logout.', 'info')
    return redirect(url_for('login'))


# ========================
# PUBLIC ROUTES
# ========================

@app.route('/')
def home():
    return render_template('index.html', status=None)


@app.route('/scan/<kode_tiket>')
def scan(kode_tiket):
    tiket = Tiket.query.filter_by(kode=kode_tiket).first()
    if not tiket:
        return render_template('index.html', status='tidak ditemukan', kode=kode_tiket)
    if tiket.is_used:
        return render_template('index.html', status='telah terpakai', kode=kode_tiket,
                               nama_peserta=tiket.nama, angkatan_peserta=tiket.angkatan)
    else:
        tiket.is_used = True
        tiket.waktu_scan = datetime.utcnow()
        db.session.commit()
        return render_template('index.html', status='berhasil', kode=kode_tiket,
                               nama_peserta=tiket.nama, angkatan_peserta=tiket.angkatan)


@app.route('/cek_manual', methods=['POST'])
def cek_manual():
    kode = request.form.get('kode_input', '').strip()
    if kode:
        return redirect(url_for('scan', kode_tiket=kode))
    return redirect(url_for('home'))


@app.route('/daftar')
def halaman_daftar():
    kuota = get_kuota()
    total_terdaftar = Tiket.query.count()
    sisa_kuota = max(0, kuota - total_terdaftar)
    if total_terdaftar >= kuota:
        return render_template('habis.html', kuota=kuota)
    return render_template('daftar.html', sisa_kuota=sisa_kuota, total_terdaftar=total_terdaftar, kuota=kuota)


@app.route('/proses_daftar', methods=['POST'])
def proses_daftar():
    kuota = get_kuota()
    total_terdaftar = Tiket.query.count()
    if total_terdaftar >= kuota:
        return render_template('habis.html', kuota=kuota)

    nama = request.form.get('nama_input', '').strip()
    pilihan_kelas = request.form.get('kelas_input', '').strip()

    if not nama or not pilihan_kelas:
        flash('Nama dan angkatan wajib diisi!', 'danger')
        return redirect(url_for('halaman_daftar'))

    kode_otomatis = "MMS-" + str(uuid.uuid4()).upper()[:4]

    peserta_baru = Tiket(nama=nama, angkatan=pilihan_kelas, kode=kode_otomatis)
    db.session.add(peserta_baru)
    db.session.commit()

    qr_base64 = generate_qr_base64(kode_otomatis)

    return render_template('sukses.html', nama=nama, angkatan=pilihan_kelas,
                           kode=kode_otomatis, qr_base64=qr_base64)


@app.route('/cek', methods=['GET', 'POST'])
def cek_tiket():
    result = None
    kode_input = ''
    if request.method == 'POST':
        kode_input = request.form.get('kode_input', '').strip()
        tiket = Tiket.query.filter_by(kode=kode_input).first()
        if tiket:
            result = {
                'found': True,
                'nama': tiket.nama,
                'angkatan': tiket.angkatan,
                'kode': tiket.kode,
                'is_used': tiket.is_used,
                'waktu_daftar': tiket.waktu_daftar.strftime('%d %b %Y, %H:%M') if tiket.waktu_daftar else '-',
                'waktu_scan': tiket.waktu_scan.strftime('%d %b %Y, %H:%M') if tiket.waktu_scan else '-'
            }
        else:
            result = {'found': False}
    return render_template('cek_tiket.html', result=result, kode_input=kode_input)


@app.route('/form')
def form_data_diri():
    return render_template('form.html')


# ========================
# ADMIN ROUTES (Protected)
# ========================

@app.route('/admin')
@login_required
def admin():
    kuota = get_kuota()
    semua_tiket = Tiket.query.order_by(Tiket.waktu_daftar.desc()).all()
    total = len(semua_tiket)
    terpakai = sum(1 for t in semua_tiket if t.is_used)
    sisa = total - terpakai
    return render_template('admin.html', tiket=semua_tiket, total=total,
                           terpakai=terpakai, sisa=sisa, kuota=kuota)


@app.route('/admin/kuota', methods=['POST'])
@login_required
def set_kuota():
    new_kuota = request.form.get('kuota', '70').strip()
    try:
        new_kuota = int(new_kuota)
        if new_kuota < 1:
            flash('Kuota minimal 1!', 'danger')
            return redirect(url_for('admin'))
    except ValueError:
        flash('Kuota harus berupa angka!', 'danger')
        return redirect(url_for('admin'))

    setting = Setting.query.filter_by(key='kuota').first()
    if setting:
        setting.value = str(new_kuota)
    else:
        setting = Setting(key='kuota', value=str(new_kuota))
        db.session.add(setting)
    db.session.commit()
    flash(f'Kuota pendaftaran berhasil diubah menjadi {new_kuota}.', 'success')
    return redirect(url_for('admin'))


@app.route('/reset_semua', methods=['POST'])
@login_required
def reset_semua():
    Tiket.query.update({Tiket.is_used: False, Tiket.waktu_scan: None})
    db.session.commit()
    flash('Semua tiket berhasil direset!', 'success')
    return redirect(url_for('admin'))


@app.route('/reset_tiket/<int:tiket_id>', methods=['POST'])
@login_required
def reset_tiket(tiket_id):
    tiket = Tiket.query.get_or_404(tiket_id)
    tiket.is_used = False
    tiket.waktu_scan = None
    db.session.commit()
    flash(f'Tiket {tiket.kode} berhasil direset.', 'success')
    return redirect(url_for('admin'))


@app.route('/hapus_tiket/<int:tiket_id>', methods=['POST'])
@login_required
def hapus_tiket(tiket_id):
    tiket = Tiket.query.get_or_404(tiket_id)
    kode = tiket.kode
    db.session.delete(tiket)
    db.session.commit()
    flash(f'Tiket {kode} berhasil dihapus.', 'success')
    return redirect(url_for('admin'))


# ========================
# EXPORT ROUTES
# ========================

@app.route('/export/csv')
@login_required
def export_csv():
    tikets = Tiket.query.order_by(Tiket.waktu_daftar.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['No', 'Nama', 'Angkatan', 'Kode Tiket', 'Status', 'Waktu Daftar', 'Waktu Scan'])
    for i, t in enumerate(tikets, 1):
        writer.writerow([
            i, t.nama, t.angkatan, t.kode,
            'Hadir' if t.is_used else 'Belum Hadir',
            t.waktu_daftar.strftime('%d/%m/%Y %H:%M') if t.waktu_daftar else '-',
            t.waktu_scan.strftime('%d/%m/%Y %H:%M') if t.waktu_scan else '-'
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'rekap_tiket_mms_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@app.route('/export/excel')
@login_required
def export_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Rekap Tiket MMS"

    # Header styling
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="6B4C7A", end_color="6B4C7A", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    headers = ['No', 'Nama', 'Angkatan', 'Kode Tiket', 'Status', 'Waktu Daftar', 'Waktu Scan']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    tikets = Tiket.query.order_by(Tiket.waktu_daftar.desc()).all()
    for i, t in enumerate(tikets, 1):
        row = i + 1
        ws.cell(row=row, column=1, value=i).border = thin_border
        ws.cell(row=row, column=2, value=t.nama).border = thin_border
        ws.cell(row=row, column=3, value=t.angkatan).border = thin_border
        ws.cell(row=row, column=4, value=t.kode).border = thin_border
        ws.cell(row=row, column=5, value='Hadir' if t.is_used else 'Belum Hadir').border = thin_border
        ws.cell(row=row, column=6, value=t.waktu_daftar.strftime('%d/%m/%Y %H:%M') if t.waktu_daftar else '-').border = thin_border
        ws.cell(row=row, column=7, value=t.waktu_scan.strftime('%d/%m/%Y %H:%M') if t.waktu_scan else '-').border = thin_border

        # Color status
        status_cell = ws.cell(row=row, column=5)
        if t.is_used:
            status_cell.fill = PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid")
        else:
            status_cell.fill = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")

    # Auto-width columns
    for col in range(1, 8):
        max_len = max(len(str(ws.cell(row=r, column=col).value or '')) for r in range(1, len(tikets) + 2))
        ws.column_dimensions[chr(64 + col)].width = max(max_len + 4, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'rekap_tiket_mms_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )


@app.route('/export/pdf')
@login_required
def export_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.units import mm

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=20*mm, bottomMargin=20*mm)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    title = Paragraph("Rekap Tiket Kajian Offline MMS 2026", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 10*mm))

    # Table data
    tikets = Tiket.query.order_by(Tiket.waktu_daftar.desc()).all()
    data = [['No', 'Nama', 'Angkatan', 'Kode Tiket', 'Status', 'Waktu Daftar', 'Waktu Scan']]
    for i, t in enumerate(tikets, 1):
        data.append([
            str(i), t.nama, t.angkatan, t.kode,
            'Hadir' if t.is_used else 'Belum Hadir',
            t.waktu_daftar.strftime('%d/%m/%Y %H:%M') if t.waktu_daftar else '-',
            t.waktu_scan.strftime('%d/%m/%Y %H:%M') if t.waktu_scan else '-'
        ])

    col_widths = [30, 140, 70, 80, 70, 100, 100]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6B4C7A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F0F7')]),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'rekap_tiket_mms_{datetime.now().strftime("%Y%m%d")}.pdf'
    )


# ========================
# API ROUTES (for charts)
# ========================

@app.route('/api/stats')
@login_required
def api_stats():
    tikets = Tiket.query.all()

    # Per angkatan
    angkatan_data = {}
    for t in tikets:
        ang = t.angkatan or 'Lainnya'
        if ang not in angkatan_data:
            angkatan_data[ang] = {'total': 0, 'hadir': 0}
        angkatan_data[ang]['total'] += 1
        if t.is_used:
            angkatan_data[ang]['hadir'] += 1

    # Timeline scan (per jam)
    timeline = {}
    for t in tikets:
        if t.waktu_scan:
            hour_key = t.waktu_scan.strftime('%H:%M')
            timeline[hour_key] = timeline.get(hour_key, 0) + 1

    # Sort timeline
    sorted_timeline = dict(sorted(timeline.items()))

    total = len(tikets)
    hadir = sum(1 for t in tikets if t.is_used)

    return jsonify({
        'total': total,
        'hadir': hadir,
        'belum_hadir': total - hadir,
        'angkatan': angkatan_data,
        'timeline': sorted_timeline
    })


# ========================
# INIT
# ========================

with app.app_context():
    db.create_all()

    # Create default admin if not exists
    if not User.query.first():
        admin_user = User(username='admin')
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print("✅ Default admin created (admin/admin123)")

    # Create default kuota setting if not exists
    if not Setting.query.filter_by(key='kuota').first():
        db.session.add(Setting(key='kuota', value='70'))
        db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
