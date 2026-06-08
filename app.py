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

    # Migrasi Kolom (Hanya dijalankan jika kolom belum ada di tabel lama)
    columns = conn.execute("PRAGMA table_info('AWE_DB.peminjaman')").df()
    if 'warna_item' not in columns['name'].values:
        conn.execute("ALTER TABLE AWE_DB.peminjaman ADD COLUMN warna_item VARCHAR")
    
    # Hapus kolom usang secara bersih
    for col in ['seri_item', 'jenis_item']:
        if col in columns['name'].values:
            conn.execute(f"ALTER TABLE AWE_DB.peminjaman DROP COLUMN {col}")

# --- UTILS ---
def get_wib_now():
    return datetime.now(pytz.timezone('Asia/Jakarta'))

# --- DATA ACCESS LAYER (DATABASE OPERATIONS) ---
def db_add_peminjaman(conn, barcode, tgl, nama, berat, warna_list, waktu):
    conn.execute("""
        INSERT INTO AWE_DB.peminjaman (id, barcode, tanggal_kedatangan, nama_barang, berat_gr, warna_item, waktu_pinjam)
        VALUES (nextval('AWE_DB.seq_id'), ?, ?, ?, ?, ?, ?)
    """, (barcode, tgl, nama, berat, json.dumps(warna_list), waktu.replace(tzinfo=None)))

def db_get_active_loan(conn, barcode):
    return conn.execute("""
        SELECT id, nama_barang, warna_item, berat_gr, waktu_pinjam 
        FROM AWE_DB.peminjaman 
        WHERE barcode = ? AND status = 'Dipinjam'
    """, (barcode,)).df()

def db_process_return(conn, barcode, waktu):
    conn.execute("""
        UPDATE AWE_DB.peminjaman 
        SET status = 'Kembali', waktu_kembali = ? 
        WHERE barcode = ? AND status = 'Dipinjam'
    """, (waktu.replace(tzinfo=None), barcode))

def db_get_all_history(conn):
    return conn.execute("""
        SELECT id, barcode, nama_barang, warna_item, berat_gr, status, waktu_pinjam, waktu_kembali 
        FROM AWE_DB.peminjaman 
        ORDER BY waktu_pinjam DESC
    """).df()

def db_update_nama(conn, id_item, nama_baru):
    conn.execute("UPDATE AWE_DB.peminjaman SET nama_barang = ? WHERE id = ?", (nama_baru, id_item))

def db_delete_item(conn, id_item):
    conn.execute("DELETE FROM AWE_DB.peminjaman WHERE id = ?", (id_item,))

# --- BUSINESS LOGIC ---
def format_warna_display(json_str):
    try:
        data = json.loads(json_str)
        return " | ".join([f"{d['warna']}: {d['berat']}g" for d in data])
    except:
        return json_str

conn = get_connection()
init_db(conn)

st.title("📦 Sistem Manajemen Peminjaman (AWE_DB)")

tab1, tab2, tab3 = st.tabs(["📝 Form Peminjaman", "🔄 Pengembalian", "📊 Data Peminjaman"])

# Inisialisasi state untuk jumlah baris warna jika belum ada
if "rows_warna" not in st.session_state:
    st.session_state.rows_warna = 1

# --- TAB 1: FORM PEMINJAMAN ---
with tab1:
    st.subheader("Input Peminjaman Barang")
    
    # 1. Input Utama (Full Width/Satu Kontainer Penuh)
    barcode = st.text_input("Barcode Utama")
    nama_barang = st.text_input("Nama Barang")
    tgl_datang = st.date_input("Tanggal Kedatangan")

    st.write("---")
    
    # 2. Info diletakkan di atas rincian berat & warna
    st.info("Klik tombol 'Tambah Baris Warna' di bawah untuk menambah warna yang sama dengan berat berbeda.")

    st.markdown("##### ⚖️ Rincian Warna & Berat")
    warna_with_berat = []
    total_berat = 0.0
    
    # Loop baris input
    for i in range(st.session_state.rows_warna):
        c1, c2 = st.columns([2, 2])
        with c1:
            w_val = st.selectbox(f"Warna {i+1}", ["Semu", "Putih", "PB", "Puth Kapas"], key=f"warna_sel_{i}")
        with c2:
            b_val = st.number_input(f"Berat {i+1} (gr)", min_value=0.0, step=0.1, format="%.2f", key=f"berat_in_{i}")
        
        warna_with_berat.append({"warna": w_val, "berat": b_val})
        total_berat += b_val

    # Kontrol Baris
    col_btn1, col_btn2, _ = st.columns([1, 1, 2])
    with col_btn1:
        if st.button("➕ Tambah Baris"):
            st.session_state.rows_warna += 1
            st.rerun()
    with col_btn2:
        if st.button("🗑️ Hapus Baris") and st.session_state.rows_warna > 1:
            st.session_state.rows_warna -= 1
            st.rerun()

    st.success(f"**Total Berat Gabungan:** {total_berat:.2f} gr")
    st.write("---")

    if st.button("Simpan Data Peminjaman", type="primary", use_container_width=True):
        if barcode and nama_barang and total_berat > 0:
            waktu_wib = get_wib_now()
            db_add_peminjaman(conn, barcode, tgl_datang, nama_barang, total_berat, warna_with_berat, waktu_wib)

            # Reset baris ke 1 setelah simpan
            st.session_state.rows_warna = 1
            st.success(f"✅ Berhasil menginput data Barcode: {barcode}")
            st.rerun()
        else:
            st.error("❌ Barcode, Nama Barang, dan Berat Warna harus diisi dengan benar!")

# --- TAB 2: PENGEMBALIAN ---
with tab2:
    st.subheader("Form Pengembalian")
    
    input_barcode_kembali = st.text_input(
        "Scan Barcode untuk Pengembalian", 
        placeholder="Arahkan scanner ke barcode...",
        key="input_barcode_ret"
    )
    
    if input_barcode_kembali:
        data_kembali = db_get_active_loan(conn, input_barcode_kembali)
        
        if not data_kembali.empty:
            data_kembali['warna_item'] = data_kembali['warna_item'].apply(format_warna_display)
            st.write("Detail Barang yang Dipinjam:")
            st.dataframe(data_kembali, use_container_width=True, hide_index=True)

            if st.button("✅ Setujui Pengembalian", type="primary"):
                db_process_return(conn, input_barcode_kembali, get_wib_now())
                st.success(f"✅ Barcode {input_barcode_kembali} berhasil dikembalikan!")
                st.rerun()
        else:
            st.warning("⚠️ Tidak ada item aktif yang dipinjam dengan barcode tersebut.")

# --- TAB 3: LIHAT DATA (EDIT & HAPUS) ---
with tab3:
    st.subheader("Daftar Riwayat Peminjaman")
    df = db_get_all_history(conn)

    if not df.empty:
        # --- RINGKASAN DATA (CARDS) ---
        df_active = df[df['status'] == 'Dipinjam']
        total_items = len(df_active)
        total_weight = df_active['berat_gr'].sum()

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("📦 Total Barang Dipinjam", f"{total_items} Item")
        with col_m2:
            st.metric("⚖️ Total Berat Dipinjam", f"{total_weight:,.2f} gr")

        if not df_active.empty:
            st.markdown("###### 📋 Rincian Berat Kumulatif per Nama Barang (Status: Dipinjam)")
            df_sum = df_active.groupby('nama_barang')['berat_gr'].sum().reset_index(name="Total Berat (gr)")
            df_sum.rename(columns={'nama_barang': 'Nama Barang'}, inplace=True)
            st.dataframe(df_sum, use_container_width=True, hide_index=True)

        df_display = df.copy()
        df_display['warna_item'] = df_display['warna_item'].apply(format_warna_display)
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("Aksi Data")
        col_edit, col_delete = st.columns(2)
        
        with col_edit:
            st.write("📝 **Edit Nama Barang**")
            id_edit = st.number_input("Masukkan ID untuk Edit", min_value=0, step=1, key="edit_id_input")
            nama_baru = st.text_input("Nama Barang Baru", key="edit_nama_input")
            if st.button("Update Nama"):
                if nama_baru:
                    db_update_nama(conn, id_edit, nama_baru)
                    st.success(f"ID {id_edit} berhasil diupdate.")
                    st.rerun()

        with col_delete:
            st.write("🗑️ **Hapus Data**")
            id_hapus = st.number_input("Masukkan ID untuk Hapus", min_value=0, step=1, key="delete_id_input")
            if st.button("Hapus Data Permanen", type="primary", key="delete_btn"):
                db_delete_item(conn, id_hapus)
                st.warning(f"Data ID {id_hapus} telah dihapus.")
                st.rerun()
    else:
        st.info("Belum ada data tersedia.")