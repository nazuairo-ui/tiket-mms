from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
import uuid
import os

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tiket.db'
db = SQLAlchemy(app)


class Tiket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kode = db.Column(db.String(10), unique=True, nullable=False)
    nama = db.Column(db.String(100), default="Peserta Kajian MMS")
    angkatan = db.Column(db.String(50))
    is_used = db.Column(db.Boolean, default=False)


@app.route('/')
def home():
    return render_template('index.html', status=None)


@app.route('/scan/<kode_tiket>')
def scan(kode_tiket):

    tiket = Tiket.query.filter_by(kode=kode_tiket).first()

    if not tiket:
        return render_template('index.html', status='tiket tidak ditemukan', kode=kode_tiket)

    if tiket.is_used:
        return render_template('index.html', status='telah terpakai', kode=kode_tiket)
    else:
        tiket.is_used = True
        db.session.commit()
        return render_template('index.html', status='berhasil', kode=kode_tiket)


@app.route('/admin')
def admin():
    semua_tiket = Tiket.query.all()
    total = len(semua_tiket)
    terpakai = Tiket.query.filter_by(is_used=True).count()
    sisa = total - terpakai
    return render_template('admin.html', tiket=semua_tiket, total=total, terpakai=terpakai, sisa=sisa)


@app.route('/reset_semua')
def reset_semua():
    Tiket.query.update({Tiket.is_used: False})
    db.session.commit()
    return redirect(url_for('admin'))


@app.route('/cek_manual', methods=['POST'])
def cek_manual():
    kode = request.form.get('kode_input')
    return redirect(url_for('scan', kode_tiket=kode))


@app.route('/daftar')
def halaman_daftar():
    total_terdaftar = Tiket.query.count()

    if total_terdaftar >= 70:
        return render_template('habis.html')

    return render_template('daftar.html')


@app.route('/form')
def form_data_diri():
    return render_template('form.html')


@app.route('/proses_daftar', methods=['POST'])
def proses_daftar():

    total_terdaftar = Tiket.query.count()
    if total_terdaftar >= 70:
        return render_template('habis.html')

    nama = request.form.get('nama_input')

    kode_otomatis = "MMS-" + str(uuid.uuid4()).upper()[:4]

    pilihan_kelas = request.form.get('kelas_input')

    print("--- DEBUG DATA ---")
    print(f"Nama yang diterima: {nama}")
    print(f"Angkatan yang diterima: {pilihan_kelas}")
    print("------------------")

    peserta_baru = Tiket(nama=nama, angkatan=pilihan_kelas, kode=kode_otomatis)
    db.session.add(peserta_baru)
    db.session.commit()

    return render_template('sukses.html', nama=nama, angkatan=pilihan_kelas, kode=kode_otomatis)


with app.app_context():
    db.create_all()

    if not Tiket.query.first():

        db.session.commit()
        semua = Tiket.query.all()
        for t in semua:
            print(f"Tiket Terdaftar: {t.kode}")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
