import streamlit as st
import duckdb
import pandas as pd
from datetime import datetime
import pytz

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS AWE_DB.peminjaman (
            id SERIAL,
            barcode VARCHAR,
            tanggal_kedatangan DATE,
            nama_barang VARCHAR,
            jenis_berat VARCHAR,
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
    with st.form("pinjam_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            barcode = st.text_input("Barcode Utama")
            nama_barang = st.text_input("Nama Barang")
            tgl_datang = st.date_input("Tanggal Kedatangan")
        
        with col2:
            jenis_berat = st.selectbox("Jenis Berat", ["Gram", "Kilogram", "Unit", "Set"])
            jenis_item = st.text_input("Jenis Item")
            seri_input = st.text_area("Daftar Seri/Set Item", help="Pisahkan dengan koma (contoh: S01, S02, S03)")

        submit_pinjam = st.form_submit_button("Simpan Data Peminjaman")

        if submit_pinjam:
            if barcode and seri_input:
                conn = get_connection()
                waktu_wib = get_wib_now()
                # Memisahkan seri item berdasarkan koma
                list_seri = [s.strip() for s in seri_input.split(",")]
                
                for seri in list_seri:
                    conn.execute("""
                        INSERT INTO AWE_DB.peminjaman (barcode, tanggal_kedatangan, nama_barang, jenis_berat, jenis_item, seri_item, waktu_pinjam)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (barcode, tgl_datang, nama_barang, jenis_berat, jenis_item, seri, waktu_wib))
                
                conn.close()
                st.success(f"✅ Berhasil menginput {len(list_seri)} item dengan Barcode: {barcode}")
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
                """, (waktu_kembali, input_barcode_kembali))
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
                st.rerun()  # Pastikan streamlit >= 1.27.0
    else:
        st.info("Belum ada data tersedia.")
```
