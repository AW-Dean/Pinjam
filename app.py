import streamlit as st
import duckdb
import pandas as pd
from datetime import datetime
import pytz
import json

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="AWE Peminjaman Barang", layout="wide")

# --- KONEKSI MOTHERDUCK ---
def get_connection():
    try:
        # Mengambil token dari Streamlit Secrets
        md_token = st.secrets["MOTHERDUCK_TOKEN"]
        # Koneksi ke root MotherDuck dulu agar aman
        return duckdb.connect(f"md:?motherduck_token={md_token}")
    except KeyError:
        st.error("❌ Secrets 'MOTHERDUCK_TOKEN' tidak ditemukan. Sila tambahkan di Settings > Secrets pada Streamlit Cloud.")
        st.stop()

# --- INISIALISASI DATABASE ---
def init_db():
    conn = get_connection()
    # Buat database dan tabel jika belum ada
    conn.execute("CREATE DATABASE IF NOT EXISTS AWE_DB")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS AWE_DB.seq_id")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS AWE_DB.peminjaman (
            id INTEGER PRIMARY KEY,
            barcode VARCHAR,
            tanggal_kedatangan DATE,
            nama_barang VARCHAR,
            berat_gr INTEGER,
            jenis_item VARCHAR,
            seri_item VARCHAR,
            status VARCHAR DEFAULT 'Dipinjam',
            waktu_pinjam TIMESTAMP,
            waktu_kembali TIMESTAMP
        )
    """)
    conn.close()

# --- UTILS ---
def get_wib_now():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

init_db()

st.title("📦 Sistem Manajemen Peminjaman (AWE_DB)")

tab1, tab2, tab3 = st.tabs(["📝 Form Peminjaman", "🔄 Pengembalian", "📊 Data Peminjaman"])

# --- TAB 1: FORM PEMINJAMAN ---
with tab1:
    st.subheader("Input Peminjaman Barang")
    
    # Ambil daftar opsi dari tabel product_catalog
    conn_options = get_connection()
    try:
        catalog_options = conn_options.execute("SELECT DISTINCT product_name FROM AWE_DB.product_catalog ORDER BY product_name").df()['product_name'].tolist()
    except Exception:
        catalog_options = []  # Fallback jika tabel belum ada
    conn_options.close()

    with st.form("pinjam_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            barcode = st.text_input("Barcode Utama")
            nama_barang = st.text_input("Nama Barang")
            tgl_datang = st.date_input("Tanggal Kedatangan")
        
        with col2:
            berat_gr = st.number_input("Berat dalam satuan gr", min_value=0, step=10)
            jenis_item = st.text_input("Jenis Item")
            # Menggunakan multiselect untuk input multiple seri
            list_seri = st.multiselect(
                "Pilih Item dari Katalog", 
                options=catalog_options,
                help="Pilih satu atau lebih seri item"
            )

        submit_pinjam = st.form_submit_button("Simpan Data Peminjaman")

        if submit_pinjam:
            if barcode and list_seri:
                conn = get_connection()
                waktu_wib = get_wib_now()
                
                # Mengirim data seri sebagai JSON string ke database
                conn.execute("""
                    INSERT INTO AWE_DB.peminjaman (id, barcode, tanggal_kedatangan, nama_barang, berat_gr, jenis_item, seri_item, waktu_pinjam)
                    VALUES (nextval('AWE_DB.seq_id'), ?, ?, ?, ?, ?, ?, ?)
                """, (barcode, tgl_datang, nama_barang, berat_gr, jenis_item, json.dumps(list_seri), waktu_wib.replace(tzinfo=None)))
                
                conn.close()
                st.success(f"✅ Berhasil menginput data Barcode: {barcode} dengan {len(list_seri)} seri dalam format JSON.")
            else:
                st.error("❌ Barcode dan Seri Item tidak boleh kosong!")

# --- TAB 2: PENGEMBALIAN ---
with tab2:
    st.subheader("Form Pengembalian")
    input_barcode_kembali = st.text_input("Scan Barcode untuk Pengembalian")
    
    if input_barcode_kembali:
        conn = get_connection()
        # Cari data yang statusnya masih 'Dipinjam'
        query = "SELECT id, seri_item, nama_barang, waktu_pinjam FROM AWE_DB.peminjaman WHERE barcode = ? AND status = 'Dipinjam'"
        data_kembali = conn.execute(query, (input_barcode_kembali,)).df()
        
        if not data_kembali.empty:
            st.write("Detail Barang yang Dipinjam:")
            st.dataframe(data_kembali, use_container_width=True)
            
            if st.button("Setujui Pengembalian (Semua Seri)"):
                waktu_kembali = get_wib_now()
                conn.execute("""
                    UPDATE AWE_DB.peminjaman 
                    SET status = 'Kembali', waktu_kembali = ? 
                    WHERE barcode = ? AND status = 'Dipinjam'
                """, (waktu_kembali.replace(tzinfo=None), input_barcode_kembali))
                conn.close()
                st.success(f"✅ Barcode {input_barcode_kembali} berhasil dikembalikan pada {waktu_kembali.strftime('%Y-%m-%d %H:%M:%S')} WIB")
                st.rerun()
        else:
            st.warning("⚠️ Tidak ada item aktif yang dipinjam dengan barcode tersebut.")
            conn.close()

# --- TAB 3: LIHAT DATA (EDIT & HAPUS) ---
with tab3:
    st.subheader("Daftar Riwayat Peminjaman")
    conn = get_connection()
    df = conn.execute("SELECT * FROM AWE_DB.peminjaman ORDER BY waktu_pinjam DESC").df()
    conn.close()

    if not df.empty:
        st.dataframe(df, use_container_width=True)
        
        st.divider()
        st.subheader("Aksi Data")
        col_edit, col_delete = st.columns(2)
        
        with col_edit:
            st.write("📝 **Edit Nama Barang**")
            id_edit = st.number_input("Masukkan ID untuk Edit", min_value=0, step=1, key="edit_id_input")
            nama_baru = st.text_input("Nama Barang Baru", key="edit_nama_input")
            if st.button("Update Nama"):
                if nama_baru:
                    conn = get_connection()
                    conn.execute("UPDATE AWE_DB.peminjaman SET nama_barang = ? WHERE id = ?", (nama_baru, id_edit))
                    conn.close()
                    st.success(f"ID {id_edit} berhasil diupdate.")
                    st.rerun()

        with col_delete:
            st.write("🗑️ **Hapus Data**")
            id_hapus = st.number_input("Masukkan ID untuk Hapus", min_value=0, step=1, key="delete_id_input")
            if st.button("Hapus Data Permanen", type="primary", key="delete_btn"):
                conn = get_connection()
                conn.execute("DELETE FROM AWE_DB.peminjaman WHERE id = ?", (id_hapus,))
                conn.close()
                st.warning(f"Data ID {id_hapus} telah dihapus.")
                st.rerun()
    else:
        st.info("Belum ada data tersedia.")