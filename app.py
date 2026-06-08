import streamlit as st
import duckdb
import pandas as pd
from datetime import datetime
import pytz
import json

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="AWE Peminjaman Barang", layout="wide")

# --- KONEKSI MOTHERDUCK ---
@st.cache_resource
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
def init_db(conn):
    # Dijalankan sekali untuk memastikan skema ada
    # Buat database dan tabel jika belum ada
    conn.execute("CREATE DATABASE IF NOT EXISTS AWE_DB")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS AWE_DB.seq_id")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS AWE_DB.peminjaman (
            id INTEGER PRIMARY KEY,
            barcode VARCHAR,
            tanggal_kedatangan DATE,
            nama_barang VARCHAR,
            berat_gr DOUBLE,
            warna_item VARCHAR,
            status VARCHAR DEFAULT 'Dipinjam',
            waktu_pinjam TIMESTAMP,
            waktu_kembali TIMESTAMP
        )
    """)

# --- UTILS ---
def get_wib_now():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

conn = get_connection()
init_db(conn)

st.title("📦 Sistem Manajemen Peminjaman (AWE_DB)")

tab1, tab2, tab3 = st.tabs(["📝 Form Peminjaman", "🔄 Pengembalian", "📊 Data Peminjaman"])

# --- TAB 1: FORM PEMINJAMAN ---
with tab1:
    st.subheader("Input Peminjaman Barang")
    
    col1, col2 = st.columns(2)
    with col1:
        barcode = st.text_input("Barcode Utama")
        nama_barang = st.text_input("Nama Barang")
        tgl_datang = st.date_input("Tanggal Kedatangan")
    
    with col2:
        # Input Multiple Warna
        list_warna = st.multiselect(
            "Pilih Warna Item",
            options=["Merah", "Biru", "Hijau", "Kuning", "Hitam", "Putih", "Silver", "Gold"],
            help="Pilih warna yang tersedia"
        )

    # Input Berat per Warna secara dinamis
    warna_with_berat = []
    total_berat = 0.0
    if list_warna:
        st.write("---")
        st.caption("Input Berat untuk masing-masing warna:")
        cols_warna = st.columns(len(list_warna))
        for i, warna in enumerate(list_warna):
            with cols_warna[i]:
                b = st.number_input(f"Berat {warna} (gr)", min_value=0.0, format="%.2f", key=f"w_{warna}")
                warna_with_berat.append({"warna": warna, "berat": b})
                total_berat += b
        st.info(f"**Total Berat Keseluruhan:** {total_berat:.2f} gr")
        st.write("---")

    if st.button("Simpan Data Peminjaman", type="primary", use_container_width=True):
        if barcode and warna_with_berat:
            waktu_wib = get_wib_now()
            conn.execute("""
                INSERT INTO AWE_DB.peminjaman (id, barcode, tanggal_kedatangan, nama_barang, berat_gr, warna_item, waktu_pinjam)
                VALUES (nextval('AWE_DB.seq_id'), ?, ?, ?, ?, ?, ?)
            """, (barcode, tgl_datang, nama_barang, total_berat, json.dumps(warna_with_berat), waktu_wib.replace(tzinfo=None)))
            
            st.success(f"✅ Berhasil menginput data Barcode: {barcode}")
            st.rerun()
        else:
            st.error("❌ Barcode dan minimal satu Warna harus diisi!")

# --- TAB 2: PENGEMBALIAN ---
with tab2:
    st.subheader("Form Pengembalian")
    input_barcode_kembali = st.text_input("Scan Barcode untuk Pengembalian", placeholder="Arahkan scanner ke barcode...")
    
    if input_barcode_kembali:
        # Cari data yang statusnya masih 'Dipinjam'
        query = "SELECT id, nama_barang, waktu_pinjam FROM AWE_DB.peminjaman WHERE barcode = ? AND status = 'Dipinjam'"
        data_kembali = conn.execute(query, (input_barcode_kembali,)).df()
        
        if not data_kembali.empty:
            st.write("Detail Barang yang Dipinjam:")
            st.dataframe(data_kembali, use_container_width=True)
            
            if st.button("✅ Setujui Pengembalian", type="primary"):
                waktu_kembali = get_wib_now()
                conn.execute("""
                    UPDATE AWE_DB.peminjaman 
                    SET status = 'Kembali', waktu_kembali = ? 
                    WHERE barcode = ? AND status = 'Dipinjam'
                """, (waktu_kembali.replace(tzinfo=None), input_barcode_kembali))
                st.success(f"✅ Barcode {input_barcode_kembali} berhasil dikembalikan pada {waktu_kembali.strftime('%Y-%m-%d %H:%M:%S')} WIB")
                st.rerun()
        else:
            st.warning("⚠️ Tidak ada item aktif yang dipinjam dengan barcode tersebut.")

# --- TAB 3: LIHAT DATA (EDIT & HAPUS) ---
with tab3:
    st.subheader("Daftar Riwayat Peminjaman")
    df = conn.execute("SELECT id, barcode, nama_barang, berat_gr, warna_item, status, waktu_pinjam, waktu_kembali FROM AWE_DB.peminjaman ORDER BY waktu_pinjam DESC").df()

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
                    conn.execute("UPDATE AWE_DB.peminjaman SET nama_barang = ? WHERE id = ?", (nama_baru, id_edit))
                    st.success(f"ID {id_edit} berhasil diupdate.")
                    st.rerun()

        with col_delete:
            st.write("🗑️ **Hapus Data**")
            id_hapus = st.number_input("Masukkan ID untuk Hapus", min_value=0, step=1, key="delete_id_input")
            if st.button("Hapus Data Permanen", type="primary", key="delete_btn"):
                conn.execute("DELETE FROM AWE_DB.peminjaman WHERE id = ?", (id_hapus,))
                st.warning(f"Data ID {id_hapus} telah dihapus.")
                st.rerun()
    else:
        st.info("Belum ada data tersedia.")